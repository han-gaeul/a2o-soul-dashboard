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
import unicodedata
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import announce  # noqa: E402
import instagram  # noqa: E402
import notify  # noqa: E402
import rules  # noqa: E402
import xposts  # noqa: E402
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
    cfg["x"] = [str(u).lstrip("@") for u in (cfg.get("x") or [])]
    cfg["videos"] = cfg.get("videos") or []
    cfg["debut_date"] = str(cfg.get("debut_date") or "")
    # MV로 인정하는 채널 (mv: true). 그 밖의 채널에 올라온 MV는 콘텐츠로
    cfg["mv_channels"] = {c["id"] for c in cfg["channels"] if c.get("mv") and c.get("id")}

    members_yml = read_yml("members.yml")
    cfg["group_links"] = members_yml.get("group_links") or []
    cfg["group_posts"] = members_yml.get("group_posts") or []
    members = members_yml.get("members") or []
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

    cfg["series"] = [(str(x["name"]), re.compile(str(x["pattern"]), re.I)) for x in cfg.get("series") or []]
    load_fan_files(cfg)
    return cfg


def _dt(value, what):
    """'YYYY-MM-DD HH:MM' 또는 'YYYY-MM-DD' → 정규화 문자열."""
    v = str(value or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}( \d{2}:\d{2})?", v):
        sys.exit(f"{what}: 날짜는 'YYYY-MM-DD' 또는 'YYYY-MM-DD HH:MM' 형식이어야 해요: {value!r}")
    return v


def load_fan_files(cfg):
    """응원 탭(votes/charts/support)과 입덕 가이드(guide) 설정."""
    votes = read_yml("votes.yml")
    cfg["votes"] = []
    for v in votes.get("votes") or []:
        cfg["votes"].append({**v, "start": _dt(v.get("start") or v.get("end"), "votes.yml start"),
                             "end": _dt(v.get("end"), "votes.yml end")})
    cfg["streaming"] = [{"title": str(x.get("title", "")), "note": str(x.get("note") or ""),
                         "links": {str(k): str(u) for k, u in (x.get("links") or {}).items() if u}}
                        for x in votes.get("streaming") or []]
    cfg["charts"] = [{"song": str(c.get("song", "")), "service": str(c.get("service", "")), "type": str(c.get("type") or ""),
                      "ranks": sorted((str(d), int(r)) for d, r in (c.get("ranks") or {}).items())}
                     for c in read_yml("charts.yml").get("charts") or []]
    cfg["supports"] = []
    for x in read_yml("support.yml").get("supports") or []:
        cfg["supports"].append({**{k: str(v) for k, v in x.items() if v is not None},
                                "start": _dt(x.get("start"), "support.yml start"),
                                "end": _dt(x.get("end") or x.get("start"), "support.yml end")})
    howto = read_yml("howto.yml")
    keep = ("show", "when", "pre", "live", "note", "url")
    cfg["howto"] = {"checked": str(howto.get("checked") or ""),
                    "voting": [{k: str(v[k]) for k in keep if v.get(k)} for v in howto.get("voting") or [] if v.get("show")],
                    "streaming": [{"title": str(s["title"]), "steps": [str(x) for x in s.get("steps") or []]}
                                  for s in howto.get("streaming") or [] if s.get("title")]}
    info = read_yml("info.yml")
    cfg["info"] = {
        "lore": [str(x) for x in info.get("lore") or []],
        "albums": [{"title": str(a["title"]), "type": str(a.get("type") or ""), "date": str(a.get("date") or ""),
                    "time": str(a.get("time") or ""), "tracks": [str(x) for x in a.get("tracks") or []],
                    "focus": [str(x) for x in a.get("focus") or []],
                    "versions": [str(x) for x in a.get("versions") or []],
                    "links": {str(k): str(v) for k, v in (a.get("links") or {}).items() if str(v).startswith("https://")}}
                   for a in info.get("albums") or [] if a.get("title")],
        "photo_labels": {str(k): str(v) for k, v in (info.get("photo_labels") or {}).items()},
        "records": [{"date": str(x["date"]), "title": str(x["title"]), "url": str(x.get("url") or "")}
                    for x in info.get("records") or [] if x.get("date") and x.get("title")],
        "shops": [{"label": str(x["label"]), "url": str(x["url"]), "note": str(x.get("note") or "")}
                  for x in info.get("shops") or [] if x.get("label") and str(x.get("url", "")).startswith("https://")],
    }
    guide = read_yml("guide.yml")
    cfg["guide"] = {"course": [{"id": str(c["id"]), "note": str(c.get("note") or "")} for c in guide.get("course") or []],
                    "tips": {str(k).upper(): str(v) for k, v in (guide.get("tips") or {}).items()}}


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


def local_img(path):
    """site/img/ 아래 실제로 있는 파일만 사용 (외부 URL 불가)."""
    rel = str(path or "").lstrip("/")
    if not rel.startswith("img/") or ".." in rel:
        return ""
    return rel if (ROOT / "site" / rel).is_file() else ""


IMG_EXT = (".jpg", ".jpeg", ".png", ".webp")


SIGN_LABELS = {"서명", "사인", "sign", "signature"}


def auto_photos(m):
    """site/img/members/ 에 멤버 이름이 들어간 파일 자동 연결 (members.yml 안 고쳐도 됨).
    파일 이름을 _ 나 - 로 나눈 조각 중 하나가 멤버 이름(영문·한글)이면 그 멤버 사진.
      문.jpg / moon.jpg      → 대표 사진
      서명_문.svg             → 서명
      슈퍼스타_문.webp 등      → 추가 사진(역대 프로필·퀴즈), 나머지 조각이 라벨. 대표 사진이 없으면 첫 번째가 대표
    (맥에서 올린 한글 파일명은 자모가 분리돼 있어서 NFC로 맞춰서 비교)"""
    folder = ROOT / "site" / "img" / "members"
    if not folder.is_dir():
        return {"photo": "", "signature": "", "extra": []}
    keys = {unicodedata.normalize("NFC", k).lower() for k in (m["name"], str(m.get("ko") or "")) if k}
    out = {"photo": "", "signature": "", "extra": []}
    for f in sorted(folder.iterdir(), key=lambda f: unicodedata.normalize("NFC", f.name)):
        if f.suffix.lower() not in IMG_EXT + (".svg",):
            continue
        parts = [x for x in re.split(r"[_\-]", unicodedata.normalize("NFC", f.stem).lower()) if x]
        if not keys & set(parts):
            continue
        rel = f"img/members/{f.name}"
        label = " ".join(x for x in parts if x not in keys)
        if label in SIGN_LABELS:
            out["signature"] = out["signature"] or rel
        elif not label and f.suffix.lower() != ".svg":
            out["photo"] = out["photo"] or rel
        elif f.suffix.lower() != ".svg":
            out["extra"].append({"label": label, "photo": rel})
    if not out["photo"] and out["extra"]:
        out["photo"] = out["extra"][0]["photo"]
    return out


IG_POST = re.compile(r"^https://(www\.)?instagram\.com/(p|reel)/[\w-]+/?")


def profile_history(m):
    out = []
    for h in m.get("profile_history") or []:
        item = {"label": str(h.get("label") or "")}
        if h.get("photo") and local_img(h["photo"]):
            item["photo"] = local_img(h["photo"])
        elif h.get("instagram") and IG_POST.match(str(h["instagram"])):
            item["instagram"] = str(h["instagram"])
        else:
            continue
        out.append(item)
    return out


def in_unit(member, video):
    """제목에 멤버가 속했던 연습생 유닛(LTB·HTB)이 있고, 그 시기에 소속이었는지."""
    # 'A2O LTB DAVID'처럼 유닛 뒤에 다른 사람 이름이 붙은 개인 영상은 유닛 전체로 보지 않음
    if re.search(r"\b(?:LTB|HTB|LTG|HTG)\s+(?!A2O\b)[A-Z]{2,}\b", video["title"]):
        return False
    day = kst_date(video.get("published_at"))
    for u in member.get("units") or []:
        if (re.search(rf"\b{re.escape(str(u['unit']))}\b", video["title"])
                and day >= str(u.get("since") or "") and day <= str(u.get("until") or "9999")):
            return True
    return False


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



# ---------- 응원법·음방 회차·기록 ----------

FANCHANT = re.compile(r"fan\s?chant|응원법", re.I)
SHOW_WEEKDAY = {"더쇼": 1, "쇼챔피언": 2, "엠카운트다운": 3, "뮤직뱅크": 4, "음악중심": 5, "인기가요": 6}


def song_of(title):
    m = re.search(r"['‘’\"“”＜<]([^'‘’\"“”＞>]{2,40})['‘’\"“”＞>]", title)
    return m.group(1).strip() if m else ""


def broadcast_date(title):
    """제목 속 방송일: 2026.10.15 / _2026.10.15 / 261021 (YYMMDD)."""
    m = re.search(r"(20\d\d)[./-](\d{1,2})[./-](\d{1,2})", title)
    if m:
        y, mo, d = map(int, m.groups())
    else:
        m = re.search(r"(?<!\d)(2\d)(0[1-9]|1[0-2])([0-3]\d)(?!\d)", title)
        if not m:
            return None
        y, mo, d = 2000 + int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return None


def build_episodes(videos, slim):
    """음방 회차별 무대·직캠: (방송, 방송일)로 묶음. 제목에 방송일이 있는 영상만 (쇼츠·1분직캠 등은 제외)."""
    eps = {}
    for v in videos:
        show = v["show"]
        if show == "M2" and re.search(r"MCOUNTDOWN|엠카", v["title"], re.I):
            show = "엠카운트다운"
        if show not in SHOW_WEEKDAY or v["short"]:
            continue
        d = broadcast_date(v["title"])
        if not d:
            continue
        ep = eps.setdefault((show, d), {"show": show, "date": d, "ep": "", "videos": []})
        m = re.search(r"EP\.?\s?(\d+)", v["title"], re.I)
        if m and not ep["ep"]:
            ep["ep"] = m.group(1)
        ep["videos"].append(v)
    out = []
    for ep in sorted(eps.values(), key=lambda e: e["date"], reverse=True):
        # 무대(풀캠 포함) 먼저, 단체 직캠, 멤버 직캠 순
        ep["videos"].sort(key=lambda v: (v["category"] == "fancam", bool(v["member"]), v["member"], v["published_at"] or ""))
        out.append({**ep, "videos": [{k: v[k] for k in slim} for v in ep["videos"]]})
    return out



def anniversaries(debut):
    """데뷔 100일 단위(1000일까지) + 매년 데뷔 기념일(5주년까지). 데뷔일이 1일째."""
    if not debut:
        return []
    d0 = date.fromisoformat(debut)
    out = [{"date": (d0 + timedelta(days=n - 1)).isoformat(), "title": f"🎉 데뷔 {n}일"} for n in range(100, 1001, 100)]
    out += [{"date": d0.replace(year=d0.year + y).isoformat(), "title": f"🎉 데뷔 {y}주년"} for y in range(1, 6)]
    return [{**a, "type": "기념일", "auto": True, "anniv": True} for a in sorted(out, key=lambda a: a["date"])]


def build_timeline(cfg, videos, episodes, subs=()):
    """기록: 데뷔·발매·첫 음방(자동) + 조회수·구독자 돌파(수집 기록 기준) + info.yml records(직접 입력)."""
    items = []
    if cfg["debut_date"]:
        items.append({"date": cfg["debut_date"], "kind": "debut", "title": "데뷔"})
    for a in cfg["info"]["albums"]:
        if a["date"]:
            items.append({"date": a["date"], "kind": "release", "title": f"{a['type']} '{a['title']}' 발매".strip()})
    firsts = {}
    for ep in episodes:
        firsts[ep["show"]] = min(firsts.get(ep["show"], ep["date"]), ep["date"])
    for show, d in firsts.items():
        items.append({"date": d, "kind": "show", "title": f"첫 {show} 무대"})
    ms = view_milestones()
    for v in videos:
        if v["category"] != "mv":
            continue
        pts = v["points"]
        for (_, a), (d, b) in zip(pts, pts[1:]):
            for m in ms:
                if a < m <= b and m >= 1_000_000:
                    items.append({"date": d, "kind": "views", "title": f"{song_of(v['title']) or 'MV'} MV {kr_num(m)}뷰 돌파",
                                  "url": f"https://youtu.be/{v['id']}"})
    today = datetime.now(KST).date().isoformat()
    for a in anniversaries(cfg["debut_date"]):
        if a["date"] <= today:
            items.append({"date": a["date"], "kind": "anniv", "title": a["title"]})
    for pts in subs:
        for (_, a), (d, b) in zip(pts, pts[1:]):
            m = crossed(a, b, subscriber_milestones())
            if m:
                items.append({"date": d, "kind": "subs", "title": f"유튜브 구독자 {kr_num(m)} 돌파"})
    for x in cfg["info"]["records"]:
        items.append({"date": x["date"], "kind": "record", "title": x["title"], "url": x["url"]})
    seen, out = set(), []
    for it in sorted(items, key=lambda x: x["date"], reverse=True):
        if (it["date"], it["title"]) not in seen:
            seen.add((it["date"], it["title"]))
            out.append(it)
    return out


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

def kst_datetime(iso):
    """ISO(UTC) → 'YYYY-MM-DD HH:MM' (KST)."""
    if not iso:
        return ""
    return datetime.fromisoformat(iso.replace("Z", "+00:00").replace("+0000", "+00:00")).astimezone(KST).strftime("%Y-%m-%d %H:%M")


def auto_items(today):
    """announcements.json → (자동 반영 일정, 공지 정보, 확인 필요 목록)."""
    store = load_json("announcements.json", {})
    events, notices, pending = [], [], []
    seen_ev, seen_pend = set(), set()
    for pid, post in sorted(store.get("posts", {}).items(), key=lambda kv: kv[1].get("timestamp") or "", reverse=True):
        posted = kst_datetime(post.get("timestamp"))[:10]
        for i in post.get("items", []):
            row = {**i, "post": post.get("permalink"), "posted": posted, "label": announce.KINDS.get(i["kind"], "기타")}
            future = (i.get("end_date") or i.get("date") or "9999") >= today
            if i["confidence"] < announce.AUTO_CONFIDENCE:
                key = (i.get("date"), i["title"])
                if future and key not in seen_pend and posted >= (date.fromisoformat(today) - timedelta(days=30)).isoformat():
                    seen_pend.add(key)
                    pending.append(row)
                continue
            if i.get("date") and i["date"] >= today and (i["date"], i["title"]) not in seen_ev:
                seen_ev.add((i["date"], i["title"]))
                events.append({"date": i["date"], "time": i.get("time"), "type": row["label"], "title": i["title"],
                               "url": i.get("url") or post.get("permalink"), "auto": True})
            if i["kind"] in ("ticket", "merch", "release", "concert", "fanmeeting", "event") and future:
                notices.append(row)
    return events, notices[:20], pending


def youtube_upcoming(registry, today):
    """예정된 유튜브 라이브·프리미어 → 일정."""
    out = []
    for vid, reg in registry.get("videos", {}).items():
        if reg.get("live_status") != "upcoming" or not reg.get("scheduled_start"):
            continue
        when = kst_datetime(reg["scheduled_start"])
        if when[:10] >= today:
            out.append({"date": when[:10], "time": when[11:], "type": "라이브", "title": reg.get("title", ""),
                        "url": f"https://www.youtube.com/watch?v={vid}", "auto": True})
    return out


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
        reg.update({k: d[k] for k in ("title", "published_at", "channel_id", "channel_title", "duration_s",
                                      "live_status", "scheduled_start")})
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

    # 공식 공지(인스타·X) → 일정 후보. ANTHROPIC_API_KEY 있으면 AI, 없으면 규칙(rules.py)
    store = load_json("announcements.json", {})
    use_ai = announce.enabled()
    extract, limit = (None, 15) if use_ai else (rules.extract, 100)
    print(f"[공지] 추출 방식: {'AI' if use_ai else '규칙'}")
    if instagram.enabled():
        for username in cfg["instagram"]:
            try:
                media = instagram.fetch_media(username)
            except Exception as e:  # noqa: BLE001
                print(f"[공지] IG {username} 게시물 조회 실패: {e}")
                continue
            # 피드·멤버 언급용 최근 게시물 (이미지는 저장하지 않음 — 본문·링크·반응 수만)
            registry.setdefault("ig_posts", {})[username] = [
                {"id": m["id"], "caption": (m.get("caption") or "")[:1000], "timestamp": m.get("timestamp"),
                 "permalink": m.get("permalink"), "likes": m.get("like_count"), "comments": m.get("comments_count")}
                for m in media]
            announce.run(media, store, today, kst_datetime, extract, limit)
    if xposts.enabled():
        xstate = store.setdefault("x", {})
        for username in cfg["x"]:
            st = xstate.setdefault(username, {})
            try:
                st.setdefault("id", xposts.user_id(username))
                posts = xposts.fetch_posts(st["id"], username, since_id=st.get("since_id"))
            except Exception as e:  # noqa: BLE001
                print(f"[공지] X @{username} 조회 실패: {e}")
                continue
            print(f"[공지] X @{username} 새 글 {len(posts)}개")
            if posts:
                st["since_id"] = max(posts, key=lambda p: int(p["tweet_id"]))["tweet_id"]
                announce.run(posts, store, today, kst_datetime, extract, limit)
    elif cfg["x"]:
        print("[공지] X_BEARER_TOKEN 없음 — X 건너뜀")
    save_json("announcements.json", store)

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


def now_kst_str():
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M")


def _ics_escape(t):
    return str(t).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def write_pending(pending):
    """확신도 낮은 자동 추출 항목 → data/pending.md (워크플로가 GitHub 이슈로 올림)."""
    path = DATA / "pending.md"
    if not pending:
        path.unlink(missing_ok=True)
        return
    lines = ["공식 인스타·X 공지에서 자동으로 뽑았지만 확신이 낮아 사이트에 바로 넣지 않은 항목이에요.",
             "맞으면 `schedule.yml`(일정)이나 `targets.yml` 등에 옮겨 적고, 아니면 무시하세요. 다음 수집 때 이 이슈가 갱신돼요.", "",
             "| 종류 | 내용 | 날짜 | 장소 | 확신 | 원문 |", "|---|---|---|---|---|---|"]
    for p in pending:
        when = " ".join(x for x in [p.get("date") or "", p.get("time") or ""] if x) or "-"
        lines.append(f"| {p['label']} | {p['title']} | {when} | {p.get('place') or '-'} | {p['confidence']:.0%} | [게시물]({p.get('post')}) |")
    path.write_text("\n".join(lines) + "\n", "utf-8")


def write_calendar(cfg, extra_events=()):
    """일정·생일·투표 마감·서포트를 iCal(.ics)로 → 휴대폰 캘린더 구독용."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//A2O SOUL Tracker//KO", "CALSCALE:GREGORIAN",
             "METHOD:PUBLISH", "X-WR-CALNAME:A2O SOUL", "X-WR-TIMEZONE:Asia/Seoul", "REFRESH-INTERVAL;VALUE=DURATION:PT6H",
             "BEGIN:VTIMEZONE", "TZID:Asia/Seoul", "BEGIN:STANDARD", "DTSTART:19700101T000000",
             "TZOFFSETFROM:+0900", "TZOFFSETTO:+0900", "TZNAME:KST", "END:STANDARD", "END:VTIMEZONE"]

    def event(uid, summary, start, end=None, all_day=False, rrule=None, url=None, desc=None):
        lines.extend(["BEGIN:VEVENT", f"UID:{uid}@a2o-soul-tracker", f"DTSTAMP:{stamp}"])
        if all_day:
            lines.append(f"DTSTART;VALUE=DATE:{start.replace('-', '')}")
            nxt = (date.fromisoformat(end or start) + timedelta(days=1)).isoformat()
            lines.append(f"DTEND;VALUE=DATE:{nxt.replace('-', '')}")
        else:
            fmt = lambda v: v.replace("-", "").replace(" ", "T").replace(":", "") + "00"
            lines.append(f"DTSTART;TZID=Asia/Seoul:{fmt(start)}")
            lines.append(f"DTEND;TZID=Asia/Seoul:{fmt(end or start)}")
        lines.append(f"SUMMARY:{_ics_escape(summary)}")
        if rrule:
            lines.append(f"RRULE:{rrule}")
        if url:
            lines.append(f"URL:{url}")
        if desc:
            lines.append(f"DESCRIPTION:{_ics_escape(desc)}")
        lines.append("END:VEVENT")

    for i, e in enumerate(list(cfg["events"]) + list(extra_events)):
        label = f"[{e['type']}] " if e.get("type") else ""
        if e.get("time") and re.fullmatch(r"\d{2}:\d{2}", e["time"]):
            st = f"{e['date']} {e['time']}"
            en = (datetime.strptime(st, "%Y-%m-%d %H:%M") + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M")
            event(f"event-{e['date']}-{i}", label + e["title"], st, en, url=e.get("url"))
        else:
            event(f"event-{e['date']}-{i}", label + e["title"], e["date"], all_day=True, url=e.get("url"))
    for m in cfg["members"]:
        bd = str(m.get("birthday") or "")
        if re.fullmatch(r"\d{2}-\d{2}", bd):
            year = cfg["debut_date"][:4] or "2026"
            event(f"birthday-{m['name']}", f"🎂 {m['name']} 생일", f"{year}-{bd}", all_day=True, rrule="FREQ=YEARLY")
    for i, v in enumerate(cfg["votes"]):
        end = v["end"] if " " in v["end"] else v["end"] + " 23:59"
        event(f"vote-{i}-{end}", f"🗳 {v.get('show', '')} {v.get('title', '투표')} 마감".strip(), end, url=v.get("url"),
              desc=f"앱: {v['app']}" if v.get("app") else None)
    for i, x in enumerate(cfg["supports"]):
        who = f"{x['member']} " if x.get("member") else ""
        event(f"support-{i}-{x['start']}", f"☕ {who}{x.get('kind', '')} {x.get('title', '')}".strip(),
              x["start"][:10], x["end"][:10], all_day=True, url=x.get("url"), desc=x.get("place"))
    lines.append("END:VCALENDAR")
    # 75바이트 줄 접기는 생략해도 주요 캘린더 앱에서 정상 동작
    (DATA / "calendar.ics").write_text("\r\n".join(lines) + "\r\n", "utf-8")


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
        kpis.append({"key": "yt_subs", "label": "유튜브 구독자", "sub": name, "value": value, "delta": delta})
        accounts.append({"name": f"유튜브 구독자 · {name}", "points": pts})
    for u in cfg["instagram"]:
        pts = points(f"ig:{u}", "followers")
        if not pts:
            continue
        value, delta = last_delta(pts)
        kpis.append({"key": "ig_followers", "label": "인스타 팔로워", "sub": f"@{u}", "value": value, "delta": delta})
        accounts.append({"name": f"인스타 팔로워 · @{u}", "points": pts})

    # 공식 인스타 피드 (최신순) + 멤버 언급
    ig_feed = []
    for u, posts in (registry.get("ig_posts") or {}).items():
        if u not in cfg["instagram"]:
            continue
        for m in posts:
            text = (m.get("caption") or "").strip()
            ig_feed.append({"account": u, "at": kst_datetime(m.get("timestamp")), "text": text[:300],
                            "more": len(text) > 300, "url": m.get("permalink"), "likes": m.get("likes"),
                            "comments": m.get("comments"), "members": detect_members(cfg, text)})
    ig_feed.sort(key=lambda x: x["at"], reverse=True)

    overrides = {v["id"]: v for v in cfg["videos"]}
    tracked = {channel_id(c) for c in cfg["channels"]}
    shows = {channel_id(c): str(c["show"]) for c in cfg["channels"] if c.get("show")}
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
            "series": next((name for name, pat in cfg["series"] if pat.search(reg["title"])), ""),
            "show": shows.get(reg.get("channel_id"), ""),
        })

    slim = ("id", "title", "category", "member", "published_at", "channel", "views", "delta", "short", "predebut",
            "series", "show")
    for v in videos:
        v["fanchant"] = bool(FANCHANT.search(v["title"]))
    episodes = build_episodes(videos, slim)
    timeline = build_timeline(cfg, videos, episodes, [pts for a in accounts if a['name'].startswith('유튜브') for pts in [a['points']]])

    mvs = sorted((v for v in videos if v["category"] == "mv"), key=lambda v: v["published_at"] or "", reverse=True)
    for v in mvs:
        v["forecast"] = forecast(v["points"])

    fancams = sorted((v for v in videos if v["category"] == "fancam"), key=lambda v: v["published_at"] or "", reverse=True)
    members = []
    for m in cfg["members"]:
        mine = [v for v in fancams if v["member"] == m["name"]]
        auto = auto_photos(m)
        members.append({
            "name": m["name"],
            "ko": m.get("ko", ""),
            "nationality": m.get("nationality", ""),
            "birth_year": m.get("birth_year"),
            "position": m.get("position") or "",
            "nicknames": m.get("nicknames") or [],
            "career": m.get("career") or [],
            "notes": m.get("notes") or [],
            "instagram_posts": [str(u) for u in (m.get("instagram_posts") or [])],
            "ig_mentions": [{k: x[k] for k in ("at", "text", "more", "url")} for x in ig_feed if m["name"] in x["members"]][:10],
            "photo": local_img(m.get("photo")) or auto["photo"],
            "signature": local_img(m.get("signature")) or auto["signature"],
            "birthday": str(m.get("birthday") or ""),
            "profile_history": profile_history(m) + [{**x, "label": cfg["info"]["photo_labels"].get(x["label"], x["label"])}
                                                     for x in auto["extra"]
                                                     if x["photo"] not in {h.get("photo") for h in profile_history(m)}],
            "fancam_count": len(mine),
            "fancam_views": sum(v["views"] or 0 for v in mine),
            "fancam_delta": sum(v["delta"] or 0 for v in mine) or None,
            "fancams": [{k: v[k] for k in slim} for v in mine],
            "predebut": [{k: v[k] for k in slim}
                         for v in sorted(videos, key=lambda v: v["published_at"] or "", reverse=True)
                         if v["predebut"] and (m["name"] in v["members"] or (not v["members"] and in_unit(m, v)))],
        })

    kpis.append({
        "key": "mv_total", "count": len(mvs), "label": "MV 총 조회수", "sub": f"{len(mvs)}편",
        "value": sum(v["views"] or 0 for v in mvs),
        "delta": sum(v["delta"] or 0 for v in mvs) or None,
    })
    kpis.append({
        "key": "fancam_total", "count": len(fancams), "label": "직캠 총 조회수", "sub": f"{len(fancams)}개",
        "value": sum(v["views"] or 0 for v in fancams),
        "delta": sum(v["delta"] or 0 for v in fancams) or None,
    })

    by_id = {v["id"]: v for v in videos}
    today = datetime.now(KST).date().isoformat()
    auto_events, notices, pending = auto_items(today)
    seen = {(e["date"], e["title"]) for e in cfg["events"]}
    annivs = anniversaries(cfg["debut_date"])
    soon = (date.fromisoformat(today) + timedelta(days=120)).isoformat()
    all_events = sorted([e for e in cfg["events"] if e["date"] >= today]
                        + [e for e in auto_events + youtube_upcoming(registry, today) if (e["date"], e["title"]) not in seen]
                        + [a for a in annivs if today <= a["date"] <= soon],
                        key=lambda e: (e["date"], e.get("time") or ""))
    write_pending(pending)
    recent = sorted((v for v in videos if v["category"] != "fancam"),
                    key=lambda v: v["published_at"] or "", reverse=True)[:12]
    today = datetime.now(KST).date().isoformat()

    dashboard = {
        "updated_at": registry.get("collected_at"),
        "debut_date": cfg["debut_date"],
        "kpis": kpis,
        "accounts": accounts,
        "ig_feed": ig_feed[:20],
        "mvs": mvs,
        "members": members,
        "group_links": cfg["group_links"],
        "group_posts": [str(u) for u in cfg.get("group_posts") or []],
        "videos": [{k: v[k] for k in slim} for v in sorted(videos, key=lambda v: v["published_at"] or "", reverse=True)],
        "recent": [{k: v[k] for k in slim} for v in recent],
        "fanchants": [{**{k: v[k] for k in slim}, "song": song_of(v["title"])}
                      for v in sorted(videos, key=lambda v: v["published_at"] or "", reverse=True) if v["fanchant"]],
        "episodes": episodes,
        "timeline": timeline,
        "events": all_events,
        "notices": notices,
        "categories": CATEGORIES,
        "feedback_url": str(cfg.get("feedback_url") or ""),
        "votes": [v for v in cfg["votes"] if v["end"] >= now_kst_str()],
        "streaming": cfg["streaming"],
        "charts": cfg["charts"],
        "supports": sorted((x for x in cfg["supports"] if x["end"] >= today), key=lambda x: x["start"]),
        "howto": cfg["howto"],
        "info": cfg["info"],
        "guide": {"course": [{**c, **{k: by_id[c["id"]][k] for k in slim}}
                             for c in cfg["guide"]["course"] if c["id"] in by_id],
                  "tips": cfg["guide"]["tips"]},
    }
    save_json("dashboard.json", dashboard)
    write_calendar(cfg, [e for e in all_events if e.get("auto") and not e.get("anniv")] + annivs)
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
