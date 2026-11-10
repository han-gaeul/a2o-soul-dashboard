#!/usr/bin/env python
"""A2O SOUL 지표 수집 + 대시보드 데이터 생성.

  python collector/collect.py           # 수집 → 알림 → data/dashboard.json 생성 (YOUTUBE_API_KEY 필요)
  python collector/collect.py --build   # 수집 없이 dashboard.json만 다시 생성 (yml 수정 반영)

data/registry.json  발견한 영상·채널 메타데이터
data/history.json   {키: {지표: {KST 날짜: 값}}} — 날짜별 마지막 값
data/dashboard.json 사이트가 읽는 집계 결과
"""
import argparse
import json
import math
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import instagram  # noqa: E402
import notify  # noqa: E402
import youtube  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
KST = timezone(timedelta(hours=9))

CATEGORIES = {"mv": "MV", "fancam": "직캠", "content": "콘텐츠"}
GROUP_PATTERN = r"A2O ?SOUL|A20 ?SOUL|에이투오 ?소울"
# 데뷔 전 연습생 유닛(LTB·HTB)과 세계관(SOULITE) — 소속사 채널(filter: soul)에서만 사용
PREDEBUT_PATTERN = r"\bLTB\b|\bHTB\b|SOULITE"
FANCAM_PATTERN = re.compile(r"직캠|fan ?cam|focus|세로캠|vertical", re.I)
NEW_VIDEO_ALERT_HOURS = 72


# ---------- 설정 ----------

def read_yml(name):
    p = ROOT / name
    return (yaml.safe_load(p.read_text("utf-8")) or {}) if p.exists() else {}


def load_config():
    cfg = read_yml("targets.yml")
    cfg["channels"] = cfg.get("channels") or []
    cfg["instagram"] = cfg.get("instagram") or []
    cfg["videos"] = cfg.get("videos") or []
    cfg["debut_date"] = str(cfg.get("debut_date") or "")
    # MV로 인정하는 채널 (mv: true). 그 밖의 채널에 올라온 MV는 콘텐츠로
    cfg["mv_channels"] = {c["id"] for c in cfg["channels"] if c.get("mv") and c.get("id")}

    members = read_yml("members.yml").get("members") or []
    cfg["members"] = members
    names = {m["name"] for m in members}
    # 멤버 이름 → 정규식 (영문은 대소문자 무시, 한글은 앞뒤에 다른 한글이 없을 때만)
    cfg["member_patterns"] = {m["name"]: member_pattern(m) for m in members}

    for v in cfg["videos"]:
        if v.get("member"):
            v["member"] = str(v["member"]).upper()
            if v["member"] not in names:
                sys.exit(f"targets.yml: 알 수 없는 멤버 {v['member']} (영상 {v['id']})")
        if v.get("category") and v["category"] not in CATEGORIES:
            sys.exit(f"targets.yml: category는 mv/fancam/content 중 하나 (영상 {v['id']})")

    events = read_yml("schedule.yml").get("events") or []
    for e in events:
        e["date"] = str(e.get("date", ""))
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", e["date"]) or not e.get("title"):
            sys.exit(f"schedule.yml: date(YYYY-MM-DD)와 title이 필요해요: {e}")
        if e.get("time") is not None:
            e["time"] = str(e["time"])
    cfg["events"] = events
    return cfg


def member_pattern(m):
    """멤버 한 명의 모든 표기를 묶은 정규식 문자열."""
    spellings = [str(s) for s in [m["name"], m.get("ko"), *(m.get("aliases") or [])] if s]
    alts = []
    for s in spellings:
        body = re.escape(s).replace(r"\-", "[- ]?").replace(r"\ ", "[- ]?")
        if re.search(r"[가-힣]", s):
            # 두 글자 이상이면 '제트의', '소라가'처럼 조사가 붙어도 인식. 한 글자(문, 준)는 '문의', '준비' 오인식 때문에 단독일 때만
            particle = r"(?:의|가|는|은|이|와|과|랑|도|를|을|에게|한테)?" if len(s) >= 2 else ""
            alts.append(rf"(?<![가-힣]){body}{particle}(?![가-힣])")
        else:  # 'SONO의'처럼 한글 조사가 붙어도 잡히게 \b 대신 영문자 경계 사용
            alts.append(rf"(?<![A-Za-z]){body}(?![A-Za-z])")
    return "(?:" + "|".join(alts) + ")"


def member_regex(cfg):
    pats = list(cfg["member_patterns"].values())
    return "|".join(pats) if pats else None


def compile_filter(cfg, f):
    if not f:
        return None
    key = str(f).lower()
    if key == "group":
        return re.compile(GROUP_PATTERN, re.I)
    if key == "soul":
        m = member_regex(cfg)
        return re.compile(GROUP_PATTERN + "|" + PREDEBUT_PATTERN + (f"|{m}" if m else ""), re.I)
    return re.compile(f, re.I)


def detect_members(cfg, title):
    return [name for name, pat in cfg["member_patterns"].items() if re.search(pat, title, re.I)]


def is_short(title, duration_s):
    """쇼츠 추정: 60초 이하, 또는 3분 이하면서 제목에 #shorts."""
    if duration_s is None:
        return False
    return duration_s <= 60 or (duration_s <= 180 and bool(re.search(r"#shorts?\b", title, re.I)))


def classify(cfg, title, duration_s):
    """(category, member)"""
    if FANCAM_PATTERN.search(title):
        found = detect_members(cfg, title)
        return "fancam", (found[0] if len(found) == 1 else "")
    if duration_s is not None and duration_s <= 60:  # 쇼츠
        return "content", ""
    t = title.upper()
    if "TEASER" in t or "티저" in title:
        return "content", ""
    if "M/V" in t or re.search(r"\bMV\b", t) or "MUSIC VIDEO" in t:
        return "mv", ""
    return "content", ""


# ---------- 돌파 기준 ----------

def view_milestones():
    ms = [100_000, 500_000]
    ms += [n * 1_000_000 for n in range(1, 10)]
    ms += [n * 10_000_000 for n in range(1, 10)]
    ms += [n * 100_000_000 for n in range(1, 21)]
    return ms


def subscriber_milestones():
    return [n * 100_000 for n in range(1, 100)]


def crossed(prev, cur, milestones):
    if prev is None or cur is None:
        return None
    hit = [m for m in milestones if prev < m <= cur]
    return hit[-1] if hit else None


def next_milestone(v):
    return next((m for m in view_milestones() if m > (v or 0)), None)


def kr_num(n):
    if n >= 100_000_000:
        return f"{n / 100_000_000:g}억"
    if n >= 10_000:
        return f"{n / 10_000:g}만"
    return f"{n:,}"


# ---------- 공통 ----------

def kst_date(iso):
    """ISO(UTC) → KST 날짜 문자열. 없으면 빈 문자열."""
    if not iso:
        return ""
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(KST).date().isoformat()


def load_json(name, default):
    p = DATA / name
    return json.loads(p.read_text("utf-8")) if p.exists() else default


def save_json(name, obj):
    DATA.mkdir(exist_ok=True)
    (DATA / name).write_text(json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=True) + "\n", "utf-8")


def resolve_video(cfg, registry, vid, overrides):
    reg = registry["videos"][vid]
    ov = overrides.get(vid, {})
    cat, member = classify(cfg, reg["title"], reg.get("duration_s"))
    if cat == "mv" and cfg["mv_channels"] and reg.get("channel_id") not in cfg["mv_channels"]:
        cat = "content"
    cat = ov.get("category") or cat
    if cat != "fancam":
        return cat, ""
    if ov.get("member"):
        return cat, ov["member"]
    found = detect_members(cfg, reg["title"])
    return cat, (found[0] if len(found) == 1 else "")


# ---------- 수집 ----------

def purge_unofficial(cfg, registry, history, channel_ids):
    """등록 채널 밖의 영상(예전 검색 수집분 등)을 registry·history에서 제거."""
    keep_ids = {v["id"] for v in cfg["videos"]}
    drop = [vid for vid, reg in registry["videos"].items()
            if vid not in keep_ids and reg.get("channel_id") not in channel_ids]
    for vid in drop:
        registry["videos"].pop(vid)
        history.pop(f"yt:{vid}", None)
    for k in ("search_scan", "channel_subs"):
        registry.pop(k, None)
    return len(drop)


def collect(cfg, rescan=False):
    registry = load_json("registry.json", {})
    for k in ("videos", "channels", "instagram", "handles"):
        registry.setdefault(k, {})
    history = load_json("history.json", {})
    now = datetime.now(KST)
    today = now.date().isoformat()
    events = []  # 알림 문구

    def record(key, metric, value):
        """오늘 값을 저장하고, 저장 직전의 최신 값을 돌려줌."""
        if value is None:
            return None
        series = history.setdefault(key, {}).setdefault(metric, {})
        prev = series[max(series)] if series else None
        series[today] = value
        return prev

    # 채널 ID 확정 (handle → id, 결과 캐시)
    channels = {}
    for c in cfg["channels"]:
        cid = c.get("id")
        if not cid and c.get("handle"):
            h = c["handle"].lstrip("@")
            cid = registry["handles"].get(h) or youtube.resolve_handle(h)
            if not cid:
                print(f"[YT] 핸들을 찾을 수 없음: @{h}")
                continue
            registry["handles"][h] = cid
        channels[cid] = c

    # 채널 지표 + 업로드 자동 등록
    # 처음(또는 --rescan)에는 업로드 전체를 훑고, 이후엔 직전 스캔의 최신 업로드 3일 전까지만 확인
    scan = registry.setdefault("scan", {})
    if rescan:
        scan.clear()
    for cid, d in youtube.fetch_channels(channels).items():
        registry["channels"][cid] = {"title": d["title"]}
        prev = record(f"ch:{cid}", "subscribers", d["subscribers"])
        record(f"ch:{cid}", "views", d["views"])
        if channels[cid].get("kpi"):
            m = crossed(prev, d["subscribers"], subscriber_milestones())
            if m:
                events.append(f"🎉 {d['title']} 유튜브 구독자 {kr_num(m)} 돌파!")
        pattern = compile_filter(cfg, channels[cid].get("filter"))
        # 필터(멤버 표기 포함)가 바뀌면 그 채널은 자동으로 처음부터 다시 훑기
        sig = registry.setdefault("scan_filter", {})
        cur_sig = pattern.pattern if pattern else ""
        if sig.get(cid) != cur_sig:
            scan.pop(cid, None)
            sig[cid] = cur_sig
        since = None
        if scan.get(cid):
            since = (date.fromisoformat(scan[cid][:10]) - timedelta(days=3)).isoformat()
        uploads = youtube.fetch_uploads(d["uploads_playlist"], since=since)
        newest = max((u["published_at"] for u in uploads if u["published_at"]), default=None)
        if newest and newest > scan.get(cid, ""):
            scan[cid] = newest
        print(f"[YT] {d['title']}: 업로드 {len(uploads)}개 확인" + (f" ({since} 이후)" if since else " (전체)"))
        for up in uploads:
            if up["id"] in registry["videos"]:
                continue
            if pattern and not pattern.search(up["title"]):
                # 소속사 채널(filter: soul) 전체 스캔 때는 걸러진 제목을 로그에 남겨 필터 점검용으로
                if since is None and str(channels[cid].get("filter")).lower() == "soul":
                    print(f"[YT]   제외: {up['published_at'][:10] if up['published_at'] else '-'} {up['title']}")
                continue
            registry["videos"][up["id"]] = {"title": up["title"], "published_at": up["published_at"], "channel_id": cid}
            print(f"[YT] 새 영상: {up['title']}")
    for cid in set(channels) - set(registry["channels"]):
        print(f"[YT] 채널을 찾을 수 없음: {cid}")

    # 등록된 공식 채널 영상과 targets.yml에 직접 적은 영상만 유지
    removed = purge_unofficial(cfg, registry, history, set(channels))
    if removed:
        print(f"[정리] 등록 채널이 아닌 영상 {removed}개 삭제")

    # 영상 지표
    overrides = {v["id"]: v for v in cfg["videos"]}
    inactive = {i for i, o in overrides.items() if o.get("active") is False}
    ids = (set(registry["videos"]) | set(overrides)) - inactive
    known_before = {i for i in ids if registry["videos"].get(i, {}).get("duration_s") is not None
                    or f"yt:{i}" in history}
    found = youtube.fetch_videos(sorted(ids))
    for vid, d in found.items():
        reg = registry["videos"].setdefault(vid, {})
        reg.update({k: d[k] for k in ("title", "published_at", "channel_id", "channel_title", "duration_s")})
        prev = record(f"yt:{vid}", "views", d["views"])
        for metric in ("likes", "comments"):
            record(f"yt:{vid}", metric, d[metric])

        cat, member = resolve_video(cfg, registry, vid, overrides)
        label = f"[{member or CATEGORIES[cat]}] {d['title']}"
        url = f"https://youtu.be/{vid}"
        if vid not in known_before and d["published_at"]:
            age = now - datetime.fromisoformat(d["published_at"].replace("Z", "+00:00"))
            if age <= timedelta(hours=NEW_VIDEO_ALERT_HOURS):
                events.append(f"🆕 새 영상 {label}\n{url}")
        if cat in ("mv", "fancam"):
            m = crossed(prev, d["views"], view_milestones())
            if m:
                events.append(f"🎉 {label} 조회수 {kr_num(m)} 돌파!\n{url}")
    for vid in sorted(ids - set(found)):
        print(f"[YT] 영상을 찾을 수 없음(비공개/삭제?): {vid}")

    # 인스타
    if instagram.enabled():
        for username in cfg["instagram"]:
            try:
                d = instagram.fetch_account(username)
            except Exception as e:  # noqa: BLE001
                print(f"[IG] {username} 실패: {e}")
                continue
            registry["instagram"][username] = {"name": d["name"]}
            record(f"ig:{username}", "followers", d["followers"])
            record(f"ig:{username}", "media_count", d["media_count"])
    else:
        print("[IG] 토큰 없음 — 건너뜀")

    registry["collected_at"] = now.isoformat(timespec="minutes")
    save_json("registry.json", registry)
    save_json("history.json", history)
    print(f"수집 완료: 영상 {len(found)}개, 채널 {len(channels)}개 ({registry['collected_at']})")

    if events:
        print("알림:\n  " + "\n  ".join(e.replace("\n", " ") for e in events))
        notify.send(events)


# ---------- 집계 ----------

def forecast(pts, window_days=7):
    """최근 window_days 평균 일일 증가량과 다음 목표까지 남은 일수."""
    if len(pts) < 2:
        return None
    last_d, last_v = date.fromisoformat(pts[-1][0]), pts[-1][1]
    base = next(((d, v) for d, v in pts if (last_d - date.fromisoformat(d)).days <= window_days), pts[0])
    days = (last_d - date.fromisoformat(base[0])).days
    if days <= 0 or last_v <= base[1]:
        return None
    rate = (last_v - base[1]) / days
    target = next_milestone(last_v)
    if not target:
        return None
    return {"rate": round(rate), "target": target, "days": math.ceil((target - last_v) / rate)}


def build(cfg):
    registry = load_json("registry.json", {"videos": {}, "channels": {}, "instagram": {}, "handles": {}})
    history = load_json("history.json", {})

    def points(key, metric):
        return sorted(history.get(key, {}).get(metric, {}).items())

    def last_delta(pts):
        if not pts:
            return None, None
        last = pts[-1][1]
        return last, (last - pts[-2][1] if len(pts) >= 2 else None)

    def channel_id(c):
        return c.get("id") or registry.get("handles", {}).get(str(c.get("handle", "")).lstrip("@"))

    kpis, accounts = [], []
    for c in cfg["channels"]:
        cid = channel_id(c)
        if not c.get("kpi") or not cid:
            continue
        pts = points(f"ch:{cid}", "subscribers")
        value, delta = last_delta(pts)
        name = registry["channels"].get(cid, {}).get("title", cid)
        kpis.append({"label": "유튜브 구독자", "sub": name, "value": value, "delta": delta})
        accounts.append({"name": f"유튜브 구독자 · {name}", "points": pts})
    for u in cfg["instagram"]:
        pts = points(f"ig:{u}", "followers")
        if not pts:
            continue
        value, delta = last_delta(pts)
        kpis.append({"label": "인스타 팔로워", "sub": f"@{u}", "value": value, "delta": delta})
        accounts.append({"name": f"인스타 팔로워 · @{u}", "points": pts})

    overrides = {v["id"]: v for v in cfg["videos"]}
    tracked = {channel_id(c) for c in cfg["channels"]}
    videos = []
    for vid, reg in registry["videos"].items():
        ov = overrides.get(vid, {})
        if ov.get("active") is False or "title" not in reg:
            continue
        if vid not in overrides and reg.get("channel_id") not in tracked:  # 공식 채널 영상만
            continue
        cat, member = resolve_video(cfg, registry, vid, overrides)
        pts = points(f"yt:{vid}", "views")
        value, delta = last_delta(pts)
        videos.append({
            "id": vid,
            "title": ov.get("title") or reg["title"],
            "category": cat,
            "member": member,
            "published_at": reg.get("published_at"),
            "channel": reg.get("channel_title") or registry["channels"].get(reg.get("channel_id"), {}).get("title", ""),
            "views": value,
            "delta": delta,
            "points": pts,
            "short": is_short(reg["title"], reg.get("duration_s")),
            "predebut": bool(cfg["debut_date"] and kst_date(reg.get("published_at")) < cfg["debut_date"]),
            "members": detect_members(cfg, reg["title"]),
        })

    slim = ("id", "title", "category", "member", "published_at", "channel", "views", "delta", "short", "predebut")

    mvs = sorted((v for v in videos if v["category"] == "mv"), key=lambda v: v["published_at"] or "", reverse=True)
    for v in mvs:
        v["forecast"] = forecast(v["points"])

    fancams = sorted((v for v in videos if v["category"] == "fancam"), key=lambda v: v["published_at"] or "", reverse=True)
    members = []
    for m in cfg["members"]:
        mine = [v for v in fancams if v["member"] == m["name"]]
        members.append({
            "name": m["name"],
            "nationality": m.get("nationality", ""),
            "fancam_count": len(mine),
            "fancam_views": sum(v["views"] or 0 for v in mine),
            "fancam_delta": sum(v["delta"] or 0 for v in mine) or None,
            "fancams": [{k: v[k] for k in slim} for v in mine],
            "predebut": [{k: v[k] for k in slim}
                         for v in sorted(videos, key=lambda v: v["published_at"] or "", reverse=True)
                         if v["predebut"] and m["name"] in v["members"]],
        })

    kpis.append({
        "label": "MV 총 조회수", "sub": f"{len(mvs)}편",
        "value": sum(v["views"] or 0 for v in mvs),
        "delta": sum(v["delta"] or 0 for v in mvs) or None,
    })
    kpis.append({
        "label": "직캠 총 조회수", "sub": f"{len(fancams)}개",
        "value": sum(v["views"] or 0 for v in fancams),
        "delta": sum(v["delta"] or 0 for v in fancams) or None,
    })

    recent = sorted((v for v in videos if v["category"] != "fancam"),
                    key=lambda v: v["published_at"] or "", reverse=True)[:12]
    today = datetime.now(KST).date().isoformat()

    dashboard = {
        "updated_at": registry.get("collected_at"),
        "debut_date": cfg["debut_date"],
        "kpis": kpis,
        "accounts": accounts,
        "mvs": mvs,
        "members": members,
        "videos": [{k: v[k] for k in slim} for v in sorted(videos, key=lambda v: v["published_at"] or "", reverse=True)],
        "recent": [{k: v[k] for k in slim} for v in recent],
        "events": sorted((e for e in cfg["events"] if e["date"] >= today),
                         key=lambda e: (e["date"], e.get("time") or "")),
        "categories": CATEGORIES,
    }
    save_json("dashboard.json", dashboard)
    print(f"dashboard.json 생성: 영상 {len(videos)}개 (MV {len(mvs)}, 직캠 {len(fancams)}), 일정 {len(dashboard['events'])}개")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true", help="수집 없이 dashboard.json만 생성")
    ap.add_argument("--rescan", action="store_true", help="채널 업로드를 처음부터 다시 훑기 (필터·멤버 표기 바꾼 뒤)")
    args = ap.parse_args()
    cfg = load_config()
    if not args.build:
        collect(cfg, rescan=args.rescan)
    build(cfg)


if __name__ == "__main__":
    main()
