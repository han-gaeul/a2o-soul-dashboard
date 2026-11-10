#!/usr/bin/env python
"""A2O SOUL 지표 수집 + 대시보드 데이터 생성.

  python collector/collect.py           # 수집 후 data/dashboard.json 생성 (YOUTUBE_API_KEY 필요)
  python collector/collect.py --build   # 수집 없이 dashboard.json만 다시 생성 (targets.yml 수정 반영)

data/registry.json  발견한 영상·채널 메타데이터
data/history.json   {키: {지표: {KST 날짜: 값}}} — 날짜별 마지막 값
data/dashboard.json 사이트가 읽는 집계 결과
"""
import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import instagram  # noqa: E402
import youtube  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
KST = timezone(timedelta(hours=9))

MEMBERS = [
    "MOON", "SORA", "SEOHA", "GAKU", "TEO", "JUNE", "LUCIEN", "HANSUNG",
    "TAI", "SEE-ONE", "SONO", "ALURE", "ZAI", "AYDEN", "ZET",
]
# 그룹명은 대소문자 무시, 멤버 이름은 일반 단어(moon, june)와 안 겹치게 대문자 단어만
SOUL_FILTER = (
    r"A2O ?SOUL|A20 ?SOUL|에이투오 ?소울|"
    r"(?-i:\b(?:" + "|".join(m.replace("-", "-?") for m in MEMBERS) + r")\b)"
)
CATEGORIES = {"mv": "MV", "fancam": "직캠", "content": "콘텐츠"}


# ---------- 공통 ----------

def load_json(name, default):
    p = DATA / name
    return json.loads(p.read_text("utf-8")) if p.exists() else default


def save_json(name, obj):
    DATA.mkdir(exist_ok=True)
    (DATA / name).write_text(json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=True) + "\n", "utf-8")


def load_config():
    cfg = yaml.safe_load((ROOT / "targets.yml").read_text("utf-8")) or {}
    cfg.setdefault("channels", [])
    cfg["instagram"] = cfg.get("instagram") or []
    cfg["videos"] = cfg.get("videos") or []
    for v in cfg["videos"]:
        if v.get("member"):
            v["member"] = str(v["member"]).upper()
            if v["member"] not in MEMBERS:
                sys.exit(f"targets.yml: 알 수 없는 멤버 {v['member']} (영상 {v['id']})")
        if v.get("category") and v["category"] not in CATEGORIES:
            sys.exit(f"targets.yml: category는 mv/fancam/content 중 하나 (영상 {v['id']})")
    return cfg


def compile_filter(f):
    if not f:
        return None
    return re.compile(SOUL_FILTER if str(f).lower() == "soul" else f, re.I)


def guess_category(title, duration_s):
    if duration_s is not None and duration_s <= 60:  # 쇼츠
        return "content"
    t = title.upper()
    if "TEASER" in t or "티저" in title:
        return "content"
    if "M/V" in t or re.search(r"\bMV\b", t) or "MUSIC VIDEO" in t:
        return "mv"
    return "content"


# ---------- 수집 ----------

def collect(cfg):
    registry = load_json("registry.json", {})
    for k in ("videos", "channels", "instagram"):
        registry.setdefault(k, {})
    history = load_json("history.json", {})
    today = datetime.now(KST).date().isoformat()

    def record(key, metric, value):
        if value is not None:
            history.setdefault(key, {}).setdefault(metric, {})[today] = value

    # 채널 + 업로드 자동 등록
    channels = {c["id"]: c for c in cfg["channels"]}
    for cid, d in youtube.fetch_channels(channels).items():
        registry["channels"][cid] = {"title": d["title"]}
        record(f"ch:{cid}", "subscribers", d["subscribers"])
        record(f"ch:{cid}", "views", d["views"])
        pattern = compile_filter(channels[cid].get("filter"))
        for up in youtube.fetch_uploads(d["uploads_playlist"]):
            if up["id"] in registry["videos"]:
                continue
            if pattern and not pattern.search(up["title"]):
                continue
            registry["videos"][up["id"]] = {"title": up["title"], "published_at": up["published_at"], "channel_id": cid}
            print(f"[YT] 새 영상: {up['title']}")
    for cid in set(channels) - set(registry["channels"]):
        print(f"[YT] 채널을 찾을 수 없음: {cid}")

    # 영상 지표
    overrides = {v["id"]: v for v in cfg["videos"]}
    ids = (set(registry["videos"]) | set(overrides)) - {i for i, o in overrides.items() if o.get("active") is False}
    found = youtube.fetch_videos(sorted(ids))
    for vid, d in found.items():
        reg = registry["videos"].setdefault(vid, {})
        reg.update({k: d[k] for k in ("title", "published_at", "channel_id", "channel_title", "duration_s")})
        for metric in ("views", "likes", "comments"):
            record(f"yt:{vid}", metric, d[metric])
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

    registry["collected_at"] = datetime.now(KST).isoformat(timespec="minutes")
    save_json("registry.json", registry)
    save_json("history.json", history)
    print(f"수집 완료: 영상 {len(found)}개, 채널 {len(channels)}개 ({registry['collected_at']})")


# ---------- 집계 ----------

def build(cfg):
    registry = load_json("registry.json", {"videos": {}, "channels": {}, "instagram": {}})
    history = load_json("history.json", {})

    def points(key, metric):
        return sorted(history.get(key, {}).get(metric, {}).items())

    def last_delta(pts):
        if not pts:
            return None, None
        last = pts[-1][1]
        return last, (last - pts[-2][1] if len(pts) >= 2 else None)

    kpis, accounts = [], []
    for c in cfg["channels"]:
        if not c.get("kpi", True):
            continue
        pts = points(f"ch:{c['id']}", "subscribers")
        value, delta = last_delta(pts)
        name = registry["channels"].get(c["id"], {}).get("title", c["id"])
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
    videos = []
    for vid, reg in registry["videos"].items():
        ov = overrides.get(vid, {})
        if ov.get("active") is False or "title" not in reg:
            continue
        pts = points(f"yt:{vid}", "views")
        value, delta = last_delta(pts)
        videos.append({
            "id": vid,
            "title": ov.get("title") or reg["title"],
            "category": ov.get("category") or guess_category(reg["title"], reg.get("duration_s")),
            "member": ov.get("member", ""),
            "published_at": reg.get("published_at"),
            "channel": reg.get("channel_title") or registry["channels"].get(reg.get("channel_id"), {}).get("title", ""),
            "views": value,
            "delta": delta,
            "likes": last_delta(points(f"yt:{vid}", "likes"))[0],
            "points": pts,
        })

    mvs = sorted((v for v in videos if v["category"] == "mv"), key=lambda v: v["views"] or 0, reverse=True)
    kpis.append({
        "label": "MV 총 조회수", "sub": f"{len(mvs)}편",
        "value": sum(v["views"] or 0 for v in mvs),
        "delta": sum(v["delta"] or 0 for v in mvs) or None,
    })

    fancam = {}
    for v in videos:
        if v["category"] == "fancam" and v["member"]:
            r = fancam.setdefault(v["member"], {"member": v["member"], "views": 0, "delta": 0, "count": 0})
            r["views"] += v["views"] or 0
            r["delta"] += v["delta"] or 0
            r["count"] += 1

    recent = sorted(videos, key=lambda v: v["published_at"] or "", reverse=True)[:12]

    dashboard = {
        "updated_at": registry.get("collected_at"),
        "debut_date": str(cfg.get("debut_date", "")),
        "kpis": kpis,
        "accounts": accounts,
        "mvs": mvs,
        "fancam": sorted(fancam.values(), key=lambda r: r["views"], reverse=True),
        "recent": [{k: v[k] for k in ("id", "title", "category", "member", "published_at", "channel", "views", "delta")}
                   for v in recent],
        "categories": CATEGORIES,
    }
    save_json("dashboard.json", dashboard)
    print(f"dashboard.json 생성: 영상 {len(videos)}개 (MV {len(mvs)}, 직캠 멤버 {len(fancam)}명)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true", help="수집 없이 dashboard.json만 생성")
    args = ap.parse_args()
    cfg = load_config()
    if not args.build:
        collect(cfg)
    build(cfg)


if __name__ == "__main__":
    main()
