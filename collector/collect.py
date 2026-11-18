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
import os
import re
from urllib.parse import quote
import urllib.parse
import unicodedata
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests
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
    cfg["x_fans"] = [str(u).lstrip("@") for u in (cfg.get("x_fans") or [])]
    cfg["x_vendors"] = [{"handle": str(v["handle"]).lstrip("@"), "name": str(v.get("name") or v["handle"])}
                        for v in (cfg.get("x_vendors") or []) if isinstance(v, dict) and v.get("handle")]
    cfg["x_vote_accounts"] = [str(u).lstrip("@") for u in (cfg.get("x_vote_accounts") or [])]
    cfg["x_media"] = [{"handle": str(v["handle"]).lstrip("@"), "name": str(v.get("name") or v["handle"])}
                      for v in (cfg.get("x_media") or []) if isinstance(v, dict) and v.get("handle")]
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
    sp = votes.get("stream_playlist") or {}
    songs = {str(k): {"title": bool(v.get("title")), "time": str(v.get("time") or ""),
                      "ids": {p: str(v[p]) for p in ("melon", "genie", "bugs", "flo") if v.get(p)}}
             for k, v in (sp.get("songs") or {}).items() if isinstance(v, dict)}
    tracks = []
    for x in sp.get("tracks") or []:
        name = x if isinstance(x, str) else (x.get("song") if isinstance(x, dict) else None)
        if name:
            info = songs.get(str(name), {})
            tracks.append({"song": str(name), "title": info.get("title", bool(isinstance(x, dict) and x.get("title"))),
                           "time": info.get("time", ""), "ids": info.get("ids", {})})
    cfg["stream_playlist"] = {"title": str(sp.get("title") or ""), "desc": str(sp.get("desc") or ""), "tracks": tracks,
                              "tips": [str(x) for x in sp.get("tips") or []]} if tracks else {}
    cfg["charts"] = [{"song": str(c.get("song", "")), "service": str(c.get("service", "")), "type": str(c.get("type") or ""),
                      "ranks": sorted((str(d), int(r)) for d, r in (c.get("ranks") or {}).items())}
                     for c in read_yml("charts.yml").get("charts") or []]
    # 차트 입력 화면(chart.html)으로 들어온 순위 — 날짜별 마지막 순위로 그래프에 합침
    by = {}
    for x in load_json("chart_entries.json", []):
        if x.get("song") and x.get("service") and x.get("at"):
            by.setdefault((str(x["song"]), str(x["service"])), []).append(x)
    for (song, service), xs in by.items():
        xs.sort(key=lambda x: x["at"])
        days = {}
        for x in xs:
            if x.get("rank"):
                days[x["at"][:10]] = int(x["rank"])
            else:
                days.pop(x["at"][:10], None)
        c = next((c for c in cfg["charts"] if c["song"] == song and c["service"] == service), None)
        if not c:
            c = {"song": song, "service": service, "type": "", "ranks": []}
            cfg["charts"].append(c)
        c["ranks"] = sorted({**dict(c["ranks"]), **days}.items())
    # 알림용: 직전 입력과 비교해 첫 진입(차트 밖→순위)·10계단 이상 상승
    cfg["chart_moves"] = []
    for (song, service), xs in by.items():
        for prev, cur in zip([None] + xs[:-1], xs):
            if not cur.get("rank"):
                continue
            p_rank = (prev or {}).get("rank")
            kind = "new" if not p_rank else "up" if p_rank - cur["rank"] >= 10 else None
            if kind:
                cfg["chart_moves"].append({"song": song, "service": service, "rank": cur["rank"], "prev": p_rank, "at": cur["at"], "kind": kind})
    cfg["supports"] = []
    for x in read_yml("support.yml").get("supports") or []:
        cfg["supports"].append({**{k: str(v) for k, v in x.items() if v is not None},
                                "start": _dt(x.get("start"), "support.yml start"),
                                "end": _dt(x.get("end") or x.get("start"), "support.yml end")})
    tr = read_yml("translations.yml") or {}
    cfg["tr"] = {str(k): {str(l): str(x) for l, x in (v or {}).items() if x} for k, v in tr.items() if isinstance(v, dict)}
    howto = read_yml("howto.yml")
    keep = ("show", "when", "pre", "live", "note", "url")
    cfg["howto"] = {"checked": str(howto.get("checked") or ""),
                    "voting": [{k: str(v[k]) for k in keep if v.get(k)} for v in howto.get("voting") or [] if v.get("show")],
                    "streaming": [{"title": str(s["title"]), "steps": [str(x) for x in s.get("steps") or []],
                                   **({"global": True} if s.get("global") else {})}
                                  for s in howto.get("streaming") or [] if s.get("title")]}
    info = read_yml("info.yml")
    cfg["info"] = {
        "lore": [str(x) for x in info.get("lore") or []],
        "albums": [{"title": str(a["title"]), "type": str(a.get("type") or ""), "date": str(a.get("date") or ""),
                    "time": str(a.get("time") or ""), "tracks": [str(x) for x in a.get("tracks") or []],
                    "focus": [str(x) for x in a.get("focus") or []],
                    "note": str(a.get("note") or ""),
                    "versions": [str(x) for x in a.get("versions") or []],
                    "links": {str(k): str(v) for k, v in (a.get("links") or {}).items() if str(v).startswith("https://")}}
                   for a in info.get("albums") or [] if a.get("title")],
        "photo_labels": {str(k): str(v) for k, v in (info.get("photo_labels") or {}).items()},
        "fanchant_call": {"song": str((info.get("fanchant_call") or {}).get("song") or ""),
                          "lines": [[str(x) for x in ln] for ln in (info.get("fanchant_call") or {}).get("lines") or []]}
        if info.get("fanchant_call") else None,
        "fanchant_guides": [{"song": str(g.get("song") or ""), "src": str(g["src"]),
                             **{k: str(g[k]) for k in ("full", "post", "video") if g.get(k)}}
                            for g in info.get("fanchant_guides") or [] if isinstance(g, dict) and g.get("src")],
        "photocard_credit": {str(k): str(v) for k, v in (info.get("photocard_credit") or {}).items()},
        "photocard_order": [str(x) for x in info.get("photocard_order") or []],
        "wins": [{"date": str(x["date"]), "show": str(x["show"]), "ep": str(x.get("ep") or ""), "url": str(x.get("url") or ""),
                  "image": str(x.get("image") or ""), "image_post": str(x.get("image_post") or ""),
                  "tags": str(x.get("tags") or ""), "og": str(x.get("og") or "")}
                 for x in info.get("wins") or [] if x.get("date") and x.get("show")],
        "records": [{"date": str(x["date"]), "title": str(x["title"]), "url": str(x.get("url") or "")}
                    for x in info.get("records") or [] if x.get("date") and x.get("title")],
        "shops": [{"label": str(x["label"]), "url": str(x["url"]), "note": str(x.get("note") or ""), "kind": str(x.get("kind") or ""),
                   "langs": [str(l) for l in x.get("langs") or []]}
                  for x in info.get("shops") or [] if x.get("label") and str(x.get("url", "")).startswith("https://")],
        "offline_stores": [{"name": str(x["name"]), "area": str(x.get("area") or ""), "handle": str(x.get("handle") or "").lstrip("@"),
                            "versions": str(x.get("versions") or ""), "date": str(x.get("date") or ""),
                            "langs": [str(l) for l in x.get("langs") or []], **{k: str(x[k]) for k in ("url", "site") if str(x.get(k) or "").startswith("https://")},
                            **({"lat": float(x["lat"]), "lng": float(x["lng"]), "approx": bool(x.get("approx"))} if x.get("lat") and x.get("lng") else {}),
                            **({"addr": str(x["addr"])} if x.get("addr") else {})}
                           for x in info.get("offline_stores") or [] if isinstance(x, dict) and x.get("name")],
        # 어디서나 살 수 있는 체인 음반 매장 (지도에서 가까운 지점 찾기)
        "chain_stores": [{"name": str(x["name"]), "note": str(x.get("note") or ""), "q": str(x.get("q") or x["name"]),
                          "langs": [str(l) for l in x.get("langs") or []]}
                         for x in info.get("chain_stores") or [] if isinstance(x, dict) and x.get("name")],
        "offline_stores_credit": str(info.get("offline_stores_credit") or ""),
        "vote_apps": [{"name": str(x["name"]), "android": str(x.get("android") or "") if str(x.get("android") or "").startswith("https://")
                       else "https://play.google.com/store/search?c=apps&q=" + quote(str(x.get("q") or x["name"])),
                       **{k: str(x[k]) for k in ("ios",) if str(x.get(k) or "").startswith("https://")}}
                      for x in info.get("vote_apps") or [] if x.get("name")],
        # 음방 생방송 보는 곳 (방송사 온에어) — show: 일정·투표 제목에 들어가는 이름
        "show_live": [{"show": str(x["show"]), "label": str(x.get("label") or ""), "url": str(x["url"])}
                      for x in info.get("show_live") or [] if x.get("show") and str(x.get("url", "")).startswith("https://")],
    }
    guide = read_yml("guide.yml")
    cfg["guide"] = {"course": [{"id": str(c["id"]), "note": str(c.get("note") or "")} for c in guide.get("course") or []],
                    "tips": {str(k).upper(): str(v) for k, v in (guide.get("tips") or {}).items()},
                    "beginner": [{"title": str(b["title"]), "items": [str(x) for x in b.get("items") or []]}
                                 for b in guide.get("beginner") or [] if b.get("title")]}


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
        return {"photo": "", "signature": "", "signs": [], "extra": []}
    keys = {unicodedata.normalize("NFC", k).lower() for k in (m["name"], str(m.get("ko") or "")) if k}
    out = {"photo": "", "signature": "", "signs": [], "extra": []}
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
            out["signs"].append((label, rel))
        elif not label and f.suffix.lower() != ".svg":
            out["photo"] = out["photo"] or rel
        elif f.suffix.lower() != ".svg":
            out["extra"].append({"label": label, "photo": rel})
    if not out["photo"] and out["extra"]:
        out["photo"] = out["extra"][0]["photo"]
    return out


def photocards(cfg):
    """site/img/photocards/버전_이름.webp (예: SOUL_문.webp, 예판특전_메이크스타_문.webp) → [{version, label, member, src}]."""
    folder = ROOT / "site" / "img" / "photocards"
    if not folder.is_dir():
        return []
    keymap = {}
    for m in cfg["members"]:
        for k in (m["name"], str(m.get("ko") or "")):
            if k:
                keymap[unicodedata.normalize("NFC", k).lower()] = m["name"]
    out = []
    for f in sorted(folder.iterdir(), key=lambda f: unicodedata.normalize("NFC", f.name)):
        if f.suffix.lower() not in IMG_EXT:
            continue
        parts = [x for x in unicodedata.normalize("NFC", f.stem).split("_") if x]
        member = next((keymap[x.lower()] for x in parts if x.lower() in keymap), None)
        rest = [x for x in parts if x.lower() not in keymap]
        if not member or not rest:
            continue
        out.append({"version": rest[0], "label": " ".join(rest[1:]), "member": member,
                    "src": "img/photocards/" + urllib.parse.quote(f.name)})
    order = {m["name"]: i for i, m in enumerate(cfg["members"])}
    vorder = [str(v) for v in ((cfg.get("info") or {}).get("photocard_order") or [])]
    vrank = lambda v: vorder.index(v) if v in vorder else len(vorder)
    out.sort(key=lambda x: (vrank(x["version"]), x["version"], x["label"], order.get(x["member"], 99)))
    return out



def ig_images(m):
    """인스타 게시물 → 사진 주소 (캐러셀은 앞 4장, 영상은 제외). 주소는 며칠 뒤 만료돼서 매 수집마다 새로 받음."""
    if m.get("media_type") == "IMAGE" and m.get("media_url"):
        return [m["media_url"]]
    if m.get("media_type") == "CAROUSEL_ALBUM":
        kids = (m.get("children") or {}).get("data", [])
        return [k["media_url"] for k in kids if k.get("media_type") == "IMAGE" and k.get("media_url")][:10]
    return []


# 멤버 사진이 아닌 글(사녹 집합 장소·공지·발매/예약 안내 포스터·일정표·트랙리스트 등)은 사진 모음에서 뺌
NOT_MEMBER_PHOTO = re.compile(r"^\s*\[(📍|🔔|📢|📌|🗓|📅)\]|사전녹화|사후녹화|인원 체크|PRE-?ORDER|RELEASE\s*\||is now available|"
                              r"TRACK\s*LIST|SCHEDULE|TIMETABLE|스케줄|트랙리스트|공지|안내|NOTICE", re.I)


def photo_feed(cfg, registry, store, limit=600):
    """공식 인스타·X 사진 게시물 → [{src, url, at, account, members, text}] 최신순."""
    out = []
    src_posts = {**(registry.get("ig_posts") or {}), **(registry.get("ig_photos") or {})}
    for u, posts in src_posts.items():
        if u not in cfg["instagram"]:
            continue
        for m in posts:
            text = (m.get("caption") or "").strip()
            if NOT_MEMBER_PHOTO.search(text):
                continue
            for i, src in enumerate(m.get("images") or []):
                out.append({"src": src, "url": m.get("permalink"), "at": kst_datetime(m.get("timestamp")), "account": "ig",
                            "members": detect_members(cfg, text), "text": text.split("\n")[0][:80], "n": i})
    x_posts = {x["id"]: x for posts in (registry.get("x_photos") or {}).values() for x in posts}
    for pid, post in (store.get("posts") or {}).items():
        if pid.startswith("x:") and post.get("images") and pid not in x_posts:
            x_posts[pid] = post
    for pid, post in x_posts.items():
        text = (post.get("caption") or "").strip()
        if NOT_MEMBER_PHOTO.search(text):
            continue
        for i, src in enumerate(post.get("images") or []):
            out.append({"src": src, "url": post.get("permalink"), "at": kst_datetime(post.get("timestamp")), "account": "x",
                        "members": detect_members(cfg, text), "text": text.split("\n")[0][:80], "n": i})
    out.sort(key=lambda x: (x["at"], -x["n"]), reverse=True)
    return out[:limit]


NOTICE_KIND = [("place", re.compile(r"^\s*\[📍\]|인원 체크")),
               ("prerec", re.compile(r"사전녹화|사후녹화|참여자 안내|공개방송")),
               ("release", re.compile(r"PRE-?ORDER|RELEASE\s*\||is now available|TRACK\s*LIST|트랙리스트", re.I)),
               ("schedule", re.compile(r"SCHEDULE|TIMETABLE|스케줄", re.I))]


def notice_feed(cfg, registry, store, limit=60):
    """공식 인스타·X 공지 글(사녹 집합 장소·공지·예약/발매 안내 등) → 최신순 [{url, at, account, kind, text, images}]."""
    posts = {}
    for u, items in {**(registry.get("ig_photos") or {}), **(registry.get("ig_posts") or {})}.items():
        if u in cfg["instagram"]:
            for m in items:
                posts.setdefault(m.get("permalink"), {**m, "account": "ig"})
    for items in (registry.get("x_photos") or {}).values():
        for m in items:
            posts.setdefault(m.get("permalink"), {**m, "account": "x"})
    for pid, m in (store.get("posts") or {}).items():
        acc = "x" if pid.startswith("x:") else ("ig" if pid.isdigit() else None)
        if acc and m.get("permalink"):
            posts.setdefault(m["permalink"], {**m, "account": acc})
    out = []
    for url, m in posts.items():
        text = (m.get("caption") or "").strip()
        if not url or not NOT_MEMBER_PHOTO.search(text):
            continue
        text = re.sub(r"\s*https://t\.co/\w+\s*$", "", text)  # X 사진 링크
        text = "\n".join(ln for ln in text.split("\n") if not re.fullmatch(r"(\s*#\S+)+\s*", ln)).strip()  # 해시태그만 있는 줄
        kind = next((k for k, rx in NOTICE_KIND if rx.search(text)), "notice")
        out.append({"url": url, "at": kst_datetime(m.get("timestamp")), "account": m["account"], "kind": kind,
                    "text": text[:600], "images": (m.get("images") or [])[:4], **notice_summary(kind, text)})
    out.sort(key=lambda x: x["at"], reverse=True)
    return out[:limit]


def store_post_title(caption):
    """입고 글 → 한 줄 요약 (해시태그·링크 뺀 첫 의미 있는 줄)."""
    for ln in (caption or "").splitlines():
        ln = re.sub(r"https?://\S+|#\S+", "", ln).strip(" -·|[]")
        if len(re.sub(r"\W", "", ln)) >= 4:
            return ln[:60]
    return ""


def store_posts(x, seen):
    """매장 입고 글 목록 (info.yml의 글 + 검색으로 찾은 글), 최신순."""
    out = list((seen or {}).get("posts") or [])
    if x.get("url") and not any(p["url"] == x["url"] for p in out):
        out.append({"date": x.get("date") or "", "url": x["url"], "text": ""})
    return sorted(out, key=lambda p: p["date"], reverse=True)[:12]


def notice_summary(kind, text):
    """공지 글 → 제목 한 줄 + 핵심 정보(인원 체크 시간·신청 시간·링크) + 나머지 설명."""
    lines = [ln.replace("\xa0", " ").strip() for ln in text.split("\n")]
    lines = [ln for ln in lines if ln and not re.fullmatch(r"\[[^\]]{1,4}\]", ln)]
    title, facts, rest = "", [], []

    def hm(s_):
        m = re.search(r"(AM|PM|오전|오후)?\s*(\d{1,2}):(\d{2})\s*(AM|PM)?", s_, re.I)
        if not m:
            return ""
        h = int(m.group(2)) % 12 if (m.group(1) or m.group(4)) else int(m.group(2))
        if (m.group(1) or m.group(4) or "").upper() in ("PM", "오후"):
            h += 12
        return f"{h:02d}:{m.group(3)}"

    for ln in lines:
        if not title and not re.search(r"https?://", ln):
            t_ = re.sub(r"^(\d{2})(\d{2})(\d{2})\b", lambda m: f"{int(m.group(2))}.{int(m.group(3))}", ln)
            t_ = re.sub(r"\s*A2O SOUL\s*", " ", t_)
            t_ = re.sub(r"\s*(사전녹화|생방송|녹화)에 참여하시는 분은.*$", r" \1 집합", t_)
            title = re.sub(r"\s+", " ", t_).strip()[:70]
            continue
        if re.fullmatch(r"(\s*#\S+)+", ln) or (re.search(r"인원\s*체크", ln) and not hm(ln)):
            continue
        slots = re.findall(r"(\d+)\s*번?\s*~\s*(\d+)?\s*번?\s*[-:]\s*((?:AM|PM|오전|오후)?\s*\d{1,2}:\d{2}(?:\s*(?:AM|PM))?)", ln, re.I)
        if slots:
            facts += [{"type": "slot", "range": f"{a}~{b}", "time": hm(t_)} for a, b, t_ in slots]
            continue
        if re.search(r"인원\s*체크", ln) and hm(ln):
            facts.append({"type": "check", "time": hm(ln)})
            continue
        if re.search(r"신청\s*기간", ln) and "~" in ln:
            a, b = ln.split("~", 1)
            d = re.search(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일", a)
            facts.append({"type": "apply", "date": f"{d.group(1)}.{d.group(2)}" if d else "", "from": hm(a), "to": hm(b)})
            continue
        u = re.search(r"https?://\S+", ln)
        if u:
            if not re.search(r"x\.com/|twitter\.com/|t\.co/", u.group(0)):
                host = re.sub(r"^www\.", "", u.group(0).split("/")[2])
                facts.append({"type": "link", "url": u.group(0), "label": "Mnet Plus" if "mnetplus" in host else host})
            continue
        rest.append(ln)
    return {"title": title, "facts": facts[:6], "desc": " ".join(rest)[:160]}


# 매체 글 중 논란·비판·가십 기사는 빼기 (콘텐츠만)
MEDIA_SKIP = re.compile(r"논란|비판|비난|백래시|사과문|해명|의혹|갑론을박|네티즌|누리꾼|backlash|controvers|criticis|slammed|apologi[sz]e|netizens|sparks?\s+debate|under fire|outrage", re.I)


def media_feed(cfg, state, limit=40):
    """매체·콘텐츠 계정의 A2O SOUL 글 → 최신순 [{url, at, handle, name, text, images, video}]."""
    names = {v["handle"].lower(): v["name"] for v in cfg["x_media"]}
    out = []
    for m in (state.get("posts") or {}).values():
        if m.get("author", "").lower() not in names or MEDIA_SKIP.search(m.get("caption") or ""):  # 목록에서 뺀 계정·논란 기사는 숨김
            continue
        text = re.sub(r"\s*https://(t\.co/\w+|x\.com/\S+/photo/\d)\s*$", "", (m.get("caption") or "").strip())
        imgs = (m.get("images") or [])[:4]
        if not imgs and (yt := re.search(r"(?:youtu\.be/|youtube\.com/(?:watch\?v=|shorts/))([\w-]{11})", text)):
            imgs = [f"https://i.ytimg.com/vi/{yt.group(1)}/hqdefault.jpg"]  # 사진 없는 글은 유튜브 링크 썸네일로
        out.append({"url": m["permalink"], "at": kst_datetime(m.get("timestamp")), "handle": m["author"],
                    "name": names[m["author"].lower()], "text": text[:400], "images": imgs,
                    "video": bool(m.get("video"))})
    out.sort(key=lambda x: x["at"] or "", reverse=True)
    return out[:limit]


def fan_extract(caption, posted, today):
    """팬 계정 글: 규칙으로 뽑되 확신을 낮춰 전부 '확인 필요'로."""
    return [{**i, "confidence": min(i["confidence"], 0.6), "title": f"[팬 계정] {i['title']}"} for i in rules.extract(caption, posted, today)]

A2O_MENTION = re.compile(r"A2O\s?SOUL|A2OSOUL|에이투오\s?소울|에이투오소울", re.I)


def official_extract(caption, posted, today):
    """음방·투표 앱 공식 계정 글: 본문에 A2O SOUL이 있고 투표 기간이 읽히면 링크가 없어도 바로 반영.
    (A2O SOUL이 후보인지 본문에 없는 일반 투표는 빼기)"""
    head = " ".join([ln for ln in (caption or "").splitlines() if ln.strip()][:2])
    if not A2O_MENTION.search(caption or "") or re.search(r"결과|RESULTS?\b|WINNERS?\b|발표합니다", head, re.I):
        return []  # A2O SOUL 없는 일반 투표, 첫 줄이 '결과 발표'인 글(이미 끝난 투표)은 빼기
    return [{**i, "confidence": max(i["confidence"], 0.9)} if i["kind"] == "vote" and i.get("end") else i
            for i in rules.extract(caption, posted, today) if i["kind"] in ("vote", "nominee")]

def nominees(today):
    """음방 1위 후보 (공식 글에서 자동, 최근 2주) — 이번 주 음방 표시·알림용"""
    out = {}
    for post in (load_json("announcements.json", {}).get("posts") or {}).values():
        for i in post.get("items", []):
            if i.get("kind") == "nominee" and i.get("date") and i.get("show") and i["date"] >= (date.fromisoformat(str(today)) - timedelta(days=14)).isoformat():
                out.setdefault((i["date"], i["show"]), {"date": i["date"], "show": i["show"], "url": post.get("permalink")})
    return sorted(out.values(), key=lambda x: x["date"])


PAST_DAYS = 120  # 지난 일정을 달력에 남기는 기간
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
SHOW_WEEKDAY = {"SHOW K-POP": 0, "더쇼": 1, "쇼챔피언": 2, "엠카운트다운": 3, "뮤직뱅크": 4, "음악중심": 5, "인기가요": 6}


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



def other_group_only(title):
    """'[최초공개] A2O LITE - NEON | WELCOME TO SOULITE From A2O SOUL A2O LITE' 처럼
    앞부분(출연자)에 A2O LITE만 있고 A2O SOUL은 없는 영상 (뒤의 행사 이름에만 SOUL이 들어간 경우)."""
    head = re.split(r"\s[|l]\s", title)[0]
    return bool(re.search(r"A2O\s*LITE|에이투오\s*라이트", head, re.I)) and not re.search(r"A2O\s*SOUL|에이투오\s*소울", head, re.I)


def other_trainee_only(cfg, title):
    """'A2O LTB DAVID, A2O LTG OA ...'처럼 유닛 뒤에 이름이 붙었는데 그 이름이 소울 멤버(별칭 포함)가 아닌 영상."""
    names = re.findall(r"\b(?:LTB|HTB)\s+([A-Z][A-Z\-]+)\b", title)
    if not names:
        return False
    known = set()
    for m in cfg["members"]:
        known |= {m["name"].upper()} | {str(a).upper() for a in m.get("aliases") or []}
    return not any(n in known for n in names)


def era_list(cfg):
    """활동 = info.yml 앨범의 활동곡(focus), 발매일 순."""
    out = []
    for a in cfg["info"]["albums"]:
        for f in a.get("focus") or []:
            if a["date"]:
                out.append((a["date"], f))
    return sorted(out)


def era_of(eras, v):
    """제목에 활동곡 이름이 있으면 그 활동, 없으면 올라온 날짜 기준 그때 활동."""
    title = v["title"].lower()
    for _, name in reversed(eras):
        if name.lower() in title:
            return name
    d = kst_date(v.get("published_at"))
    cur = ""
    for start, name in eras:
        if d >= start:
            cur = name
    return cur


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
    out = [{"date": d0.isoformat(), "title": "🎉 데뷔", "key": "anniv_debut", "n": 0}]
    out += [{"date": (d0 + timedelta(days=n - 1)).isoformat(), "title": f"🎉 데뷔 {n}일", "key": "anniv_days", "n": n}
            for n in range(100, 1001, 100)]
    out += [{"date": d0.replace(year=d0.year + y).isoformat(), "title": f"🎉 데뷔 {y}주년", "key": "anniv_years", "n": y}
            for y in range(1, 6)]
    return [{**a, "type": "기념일", "auto": True, "anniv": True} for a in sorted(out, key=lambda a: a["date"])]


def build_timeline(cfg, videos, episodes, subs=()):
    """기록: 데뷔·발매·첫 음방(자동) + 조회수·구독자 돌파(수집 기록 기준) + info.yml records(직접 입력)."""
    items = []
    if cfg["debut_date"]:
        items.append({"date": cfg["debut_date"], "kind": "debut", "title": "데뷔", "key": "tl_debut"})
    for a in cfg["info"]["albums"]:
        if a["date"]:
            items.append({"date": a["date"], "kind": "release", "title": f"{a['type']} '{a['title']}' 발매".strip(),
                          "key": "tl_release", "type": a["type"], "name": a["title"]})
    firsts = {}
    for ep in episodes:
        firsts[ep["show"]] = min(firsts.get(ep["show"], ep["date"]), ep["date"])
    for show, d in firsts.items():
        items.append({"date": d, "kind": "show", "title": f"첫 {show} 무대", "key": "tl_first_show", "show": show})
    ms = view_milestones()
    for v in videos:
        if v["category"] != "mv":
            continue
        pts = v["points"]
        for (_, a), (d, b) in zip(pts, pts[1:]):
            for m in ms:
                if a < m <= b and m >= 1_000_000:
                    items.append({"date": d, "kind": "views", "title": f"{song_of(v['title']) or 'MV'} MV {kr_num(m)}뷰 돌파",
                                  "url": f"https://youtu.be/{v['id']}", "key": "tl_views", "name": song_of(v["title"]) or "MV", "n": m})
    today = datetime.now(KST).date().isoformat()
    for a in anniversaries(cfg["debut_date"]):
        if a["date"] <= today:
            items.append({"date": a["date"], "kind": "anniv", "title": a["title"], "key": a["key"], "n": a["n"]})
    for pts in subs:
        for (_, a), (d, b) in zip(pts, pts[1:]):
            m = crossed(a, b, subscriber_milestones())
            if m:
                items.append({"date": d, "kind": "subs", "title": f"유튜브 구독자 {kr_num(m)} 돌파", "key": "tl_subs", "n": m})
    # 음방 1위: 공식 공지에서 자동 (같은 날·같은 음방은 하나)
    wins = set()
    for pid, post in (load_json("announcements.json", {}).get("posts") or {}).items():
        if pid.startswith(("xf:", "xv:", "xo:")):  # 팬 계정·판매처·음방 공식 글은 기록에 안 넣음
            continue
        for i in post.get("items", []):
            if i.get("kind") == "win" and i.get("date") and (i["date"], i.get("show")) not in wins:
                wins.add((i["date"], i.get("show")))
                items.append({"date": i["date"], "kind": "win", "title": i["title"], "key": "tl_win", "show": i.get("show"),
                              "url": post.get("permalink")})
    for w in cfg["info"]["wins"]:  # 직접 입력한 1위 — 공식 공지에서 이미 잡혔으면 그 항목에 사진·회차·해시태그 등을 합침
        extra = {k: w[k] for k in ("ep", "url", "image", "image_post", "tags", "og") if w.get(k)}
        same = next((x for x in items if x.get("kind") == "win" and x["date"] == w["date"] and x.get("show") == w["show"]), None)
        if same:
            same.update(extra)
            continue
        wins.add((w["date"], w["show"]))
        items.append({"date": w["date"], "kind": "win", "title": f"{w['show']} 1위", "key": "tl_win", "show": w["show"], **extra})
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


APPROVE_LINE = re.compile(r"^\s*[-*]\s*\[[xX]\].*<!--\s*key:(.+?)\s*-->")


def read_approvals(store):
    """'자동 수집 확인 필요' 이슈에서 체크(☑)한 항목 → store['approved']에 저장 (워크플로가 이슈 본문을 APPROVALS_FILE로 넘김)."""
    path = os.environ.get("APPROVALS_FILE")
    if not path or not os.path.exists(path):
        return False
    keys = [m.group(1) for ln in open(path, encoding="utf-8").read().splitlines() if (m := APPROVE_LINE.match(ln))]
    have = store.setdefault("approved", [])
    new = [k for k in keys if k not in have]
    have.extend(new)
    if new:
        print(f"[공지] 이슈에서 체크한 항목 {len(new)}개 반영")
    return bool(new)


def auto_items(today):
    """announcements.json → (자동 반영 일정, 공지 정보, 확인 필요 목록)."""
    store = load_json("announcements.json", {})
    if read_approvals(store):
        save_json("announcements.json", store)
    approved = set(store.get("approved") or [])
    events, notices, pending, votes, prerecs = [], [], [], [], []
    seen_ev, seen_pend, seen_vote = set(), set(), set()
    for pid, post in sorted(store.get("posts", {}).items(), key=lambda kv: kv[1].get("timestamp") or "", reverse=True):
        posted = kst_datetime(post.get("timestamp"))[:10]
        for i in post.get("items", []):
            akey = f"{pid}|{i.get('date') or ''}|{i['title']}"
            if akey in approved:  # 이슈에서 체크 → 확인된 항목으로
                i = {**i, "confidence": 1.0, "title": i["title"].replace("[팬 계정] ", "")}
            row = {**i, "post": post.get("permalink"), "posted": posted, "label": announce.KINDS.get(i["kind"], "기타"), "key": akey}
            future = (i.get("end_date") or i.get("date") or "9999") >= today
            # 팬 계정 투표 글: 마감 시각까지 읽히면 승인 없이 '팬 계정 제보' 표시로 바로 투표 칸에
            if (i["kind"] == "vote" and pid.startswith("xf:") and akey not in approved and i.get("end")
                    and i["end"] >= now_kst_str() and (i["end"], i["title"]) not in seen_vote):
                seen_vote.add((i["end"], i["title"]))
                title = i["title"].replace("[팬 계정] ", "")
                votes.append({"show": i.get("show") or "", "title": title if not i.get("show") else title.replace(i["show"], "").strip(),
                              "app": i.get("app") or "", "start": i.get("start") or i["end"], "end": i["end"],
                              "url": i.get("url") or post.get("permalink"), "source": post.get("permalink"), "auto": True, "fan": True})
                continue
            if i["confidence"] < announce.AUTO_CONFIDENCE:
                key = (i.get("date"), i["title"])
                # 날짜 없는 항목: 팬 계정 투표 독려 글은 확인할 게 없어서 빼고, 나머지도 올라온 지 2일 지나면 뺌
                if not i.get("date") and (pid.startswith("xf:") and i["kind"] == "vote"
                                          or posted < (date.fromisoformat(today) - timedelta(days=2)).isoformat()):
                    continue
                if future and key not in seen_pend and posted >= (date.fromisoformat(today) - timedelta(days=30)).isoformat():
                    seen_pend.add(key)
                    pending.append(row)
                continue
            if i["kind"] == "prerec":  # 사전녹화 신청 (신청 시간·링크)
                if i.get("end") and i["end"] >= now_kst_str() and i["confidence"] >= announce.AUTO_CONFIDENCE:
                    prerecs.append({"show": i.get("show") or "", "record": i.get("date"), "start": i["start"], "end": i["end"],
                                    "url": i.get("url"), "source": post.get("permalink")})
                continue
            if i["kind"] == "vote":  # 투표: 응원 탭 투표 카드·캘린더로 (기간·링크)
                if i.get("end") and i["end"] >= now_kst_str() and (i["end"], i["title"]) not in seen_vote:
                    seen_vote.add((i["end"], i["title"]))
                    votes.append({"show": i.get("show") or "", "title": i["title"] if not i.get("show") else i["title"].replace(i["show"], "").strip(),
                                  "app": i.get("app") or "", "start": i.get("start") or i["end"], "end": i["end"],
                                  "url": i.get("url") or post.get("permalink"), "source": post.get("permalink"), "auto": True})
                continue
            if i["kind"] == "nominee":  # 1위 후보는 이번 주 음방 표시·알림으로만 (nominees())
                continue
            past_from = (date.fromisoformat(today) - timedelta(days=PAST_DAYS)).isoformat()
            if i.get("date") and i["date"] >= past_from and (i["date"], i["title"]) not in seen_ev:
                seen_ev.add((i["date"], i["title"]))
                events.append({"date": i["date"], "time": i.get("time"), "type": row["label"], "title": i["title"],
                               "url": i.get("url") or post.get("permalink"), "auto": True,
                               **({"short": i["short"]} if i.get("short") else {})})
            if i["kind"] in ("ticket", "merch", "release", "concert", "fanmeeting", "event") and future:
                notices.append(row)
    prerecs.sort(key=lambda x: x["start"])
    notices.sort(key=lambda x: (x.get("date") or "9999", x.get("time") or "99:99"))
    return events, notices[:20], pending, votes, prerecs


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
            if vid not in keep_ids and reg.get("channel_id") not in channel_ids and not reg.get("discovered")]
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

    # 방송사 라디오·예능 출연 영상 찾기 (검색 100유닛이라 몇 시간에 한 번)
    #   제목에 그룹명이 있고, 채널 이름이 방송사·라디오 목록에 맞는 것만 (리액션·팬 채널 제외)
    disc = cfg.get("discover") or {}
    if disc.get("query"):
        last = registry.get("discover_at")
        every = timedelta(hours=float(disc.get("every_hours", 6)))
        if rescan or not last or now - datetime.fromisoformat(last) >= every:
            ch_re = re.compile(disc.get("channels") or r"MBC|KBS|SBS|JTBC|Mnet|tvN|EBS|ENA", re.I)
            title_re = re.compile(GROUP_PATTERN, re.I)
            after = (now - timedelta(days=int(disc.get("days", 14)))).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            try:
                found_s = youtube.search_videos(disc["query"], published_after=after)
                registry["discover_at"] = now.isoformat(timespec="minutes")
            except Exception as e:  # noqa: BLE001
                print(f"[YT] 검색 실패: {e}")
                found_s = []
            for up in found_s:
                if up["id"] in registry["videos"] or up["channel_id"] in channels:
                    continue
                if not title_re.search(up["title"]) or not ch_re.search(up["channel_title"]):
                    continue
                registry["videos"][up["id"]] = {"title": up["title"], "published_at": up["published_at"],
                                                "channel_id": up["channel_id"], "discovered": True}
                print(f"[YT] 방송사 영상 찾음: {up['channel_title']} — {up['title']}")

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
    if not use_ai and store.get("rules_version") != rules.RULES_VERSION:
        # 규칙이 바뀌면 최근 공지를 새 규칙으로 다시 읽기. 본문이 저장 안 된 옛 기록은 지우고 다시 받아옴
        posts = store.setdefault("posts", {})
        for pid, post in list(posts.items()):
            if post.get("caption"):
                ext = ((lambda c, p_, t_, v=post.get("vendor", ""): rules.fansign_items(c, p_, v)) if pid.startswith("xv:")
                       else fan_extract if pid.startswith("xf:") else official_extract if pid.startswith("xo:") else rules.extract)
                post["items"] = [i for i in ext(post["caption"], kst_datetime(post.get("timestamp")), today) if i["title"]]
            else:
                posts.pop(pid)
                if pid.startswith("x:"):
                    for st in (store.get("x") or {}).values():
                        st.pop("since_id", None)  # X는 최근 20개만 다시 (몇 센트)
                if pid.startswith("xv:"):
                    (store.get("x_vendors") or {}).pop("since_id", None)
                if pid.startswith("xf:"):
                    for st in (store.get("x_fans") or {}).values():
                        st.pop("since_id", None)
        store["rules_version"] = rules.RULES_VERSION
        print(f"[공지] 규칙 v{rules.RULES_VERSION}로 다시 처리")
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
                 "permalink": m.get("permalink"), "likes": m.get("like_count"), "comments": m.get("comments_count"),
                 "images": ig_images(m)}
                for m in media]
            announce.run(media, store, today, kst_datetime, extract, limit)
            # 사진 모음: 예전 게시물까지 (이미지 주소는 며칠 뒤 만료돼서 매번 새로 받음)
            try:
                allm = instagram.fetch_media_pages(username)
                registry.setdefault("ig_photos", {})[username] = [
                    {"id": m["id"], "caption": (m.get("caption") or "")[:400], "timestamp": m.get("timestamp"),
                     "permalink": m.get("permalink"), "images": ig_images(m)} for m in allm if ig_images(m)]
                print(f"[IG] 사진 게시물 {len(registry['ig_photos'][username])}개 (전체 {len(allm)}개 중)")
            except Exception as e:  # noqa: BLE001
                print(f"[IG] {username} 사진 모음 조회 실패: {e}")
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
                for xp in posts:  # 사진 모음용 이미지 주소
                    if xp.get("images") and xp["id"] in store["posts"]:
                        store["posts"][xp["id"]]["images"] = xp["images"][:4]
            # 사진 모음: 예전 글까지 한 번 훑어 두고(X는 읽은 글 수만큼 과금), 이후엔 새 글의 사진만 더함
            xp_all = registry.setdefault("x_photos", {})
            if username not in xp_all:
                try:
                    xp_all[username] = xposts.fetch_photo_posts(st["id"], username)
                    print(f"[X] @{username} 사진 글 {len(xp_all[username])}개 (예전 글까지)")
                except Exception as e:  # noqa: BLE001
                    print(f"[X] @{username} 사진 모음 조회 실패: {e}")
            if username in xp_all:
                have = {x["id"] for x in xp_all[username]}
                xp_all[username] = [{"id": xp["id"], "caption": (xp.get("caption") or "")[:400], "timestamp": xp.get("timestamp"),
                                     "permalink": xp.get("permalink"), "images": xp["images"][:4]}
                                    for xp in posts if xp.get("images") and xp["id"] not in have] + xp_all[username]
        # 판매처(Mnet Plus·Makestar·Withmuu 등) 팬사인회·영통 공지 — 검색으로 A2O SOUL 관련 글만 (읽은 글 수만큼 과금)
        vendors = cfg.get("x_vendors") or []
        if vendors:
            vst = store.setdefault("x_vendors", {})
            names = {v["handle"].lower(): v["name"] for v in vendors}
            base = ("(\"A2O SOUL\" OR A2OSOUL OR 에이투오소울 OR \"에이투오 소울\") "
                    "(팬사인회 OR 사인회 OR 영상통화 OR 영통 OR fansign OR \"video call\") ")
            # 검색어는 512자 제한 → 판매처를 몇 개씩 나눠서
            groups, cur = [], []
            for v in vendors:
                if cur and len(base) + len(" OR ".join("from:" + h for h in cur + [v["handle"]])) + 30 > 500:
                    groups.append(cur)
                    cur = []
                cur.append(v["handle"])
            if cur:
                groups.append(cur)
            posts = []
            for g in groups:
                query = base + f"({' OR '.join('from:' + h for h in g)}) -is:retweet -is:reply"
                try:
                    posts += xposts.search_posts(query, since_id=vst.get("since_id"))
                except Exception as e:  # noqa: BLE001
                    print(f"[공지] X 판매처 검색 실패: {e}")
            print(f"[공지] X 판매처 새 글 {len(posts)}개")
            if posts:
                vst["since_id"] = max(posts, key=lambda p: int(p["tweet_id"]))["tweet_id"]
                for post in posts:
                    vendor = names.get(post["author"].lower(), post["author"])
                    announce.run([post], store, today, kst_datetime,
                                 lambda c, p_, t_, v=vendor: rules.fansign_items(c, p_, v), limit)
                    if post["id"] in store["posts"]:
                        store["posts"][post["id"]]["vendor"] = vendor
        # 매체·콘텐츠 계정 — 목록 계정이 A2O SOUL을 언급한 글 (1시간마다, from: 검색이라 읽는 글 수가 적음)
        mst = store.setdefault("x_media", {})
        mposts = mst.setdefault("posts", {})
        mcands = mst.setdefault("candidates", {})
        mknown = {v["handle"].lower() for v in cfg["x_media"]}
        if cfg["x_media"] and (not mst.get("checked") or now - datetime.fromisoformat(mst["checked"]) >= timedelta(days=1)):
            try:  # 없는 아이디 확인 (하루 한 번)
                ok = xposts.users_exist([v["handle"] for v in cfg["x_media"]])
                mst["missing"] = sorted(v["handle"] for v in cfg["x_media"] if not ok.get(v["handle"].lower(), True))
                mst["checked"] = now.isoformat(timespec="minutes")
            except Exception as e:  # noqa: BLE001
                print(f"[매체] 아이디 확인 실패: {e}")
        if cfg["x_media"] and (not mst.get("at") or now - datetime.fromisoformat(mst["at"]) >= timedelta(hours=1)):
            base = "(\"A2O SOUL\" OR A2OSOUL OR 에이투오소울 OR \"에이투오 소울\") "
            live = [v["handle"] for v in cfg["x_media"] if v["handle"] not in (mst.get("missing") or [])]
            groups, cur = [], []
            for h in live:
                if cur and len(base) + len(" OR ".join("from:" + x for x in cur + [h])) + 30 > 500:
                    groups.append(cur)
                    cur = []
                cur.append(h)
            if cur:
                groups.append(cur)
            got, failed = [], False
            for g in groups:
                try:
                    got += xposts.search_posts(base + f"({' OR '.join('from:' + h for h in g)}) -is:retweet -is:reply",
                                               since_id=mst.get("since_id"), max_results=100, media=True)
                except Exception as e:  # noqa: BLE001
                    failed = True
                    print(f"[매체] 검색 실패: {e}")
            if not failed:
                mst["at"] = now.isoformat(timespec="minutes")
            if got:
                mst["since_id"] = max(got, key=lambda p_: int(p_["tweet_id"]))["tweet_id"]
            for p_ in got:
                if A2O_MENTION.search(p_["caption"]) and not MEDIA_SKIP.search(p_["caption"]):
                    mposts[p_["tweet_id"]] = {k: p_.get(k) for k in ("caption", "timestamp", "permalink", "author", "author_name", "images", "video")}
            cut = (now - timedelta(days=14)).isoformat()
            for k in [k for k, m in mposts.items() if (m.get("timestamp") or "") < cut]:
                mposts.pop(k)
            print(f"[매체] 새 글 {len(got)}개 · 보관 {len(mposts)}개")

        def media_cand(p_):
            """인증 기업 계정인데 목록에 없는 계정 → 새 매체 후보 (판매처·매장·투표 앱 제외)."""
            h = p_["author"].lower()
            if p_.get("verified_type") != "business" or h in mknown or h in mcands or h == "a2o_soul":
                return
            if h in {v["handle"].lower() for v in cfg.get("x_vendors") or []} | {u.lower() for u in cfg["x_vote_accounts"]} \
                    | {str(x.get("handle") or "").lower() for x in cfg["info"].get("offline_stores") or []}:
                return
            mcands[h] = {"handle": p_["author"], "name": p_.get("author_name") or p_["author"],
                         "date": (kst_datetime(p_["timestamp"]) or "")[:10], "url": p_["permalink"],
                         "text": re.sub(r"\s+", " ", p_["caption"])[:80]}
            if len(mcands) > 30:
                for k in sorted(mcands, key=lambda k: mcands[k]["date"])[:len(mcands) - 30]:
                    mcands.pop(k)

        # 오프라인 음반 매장 — 'A2O SOUL + 입고' 글 검색(6시간마다): 아는 매장은 입고 확인 날짜 갱신, 모르는 계정은 새 매장 후보로
        sst = store.setdefault("x_stores", {})
        if not sst.get("at") or now - datetime.fromisoformat(sst["at"]) >= timedelta(hours=6):
            query = ("(\"A2O SOUL\" OR A2OSOUL OR 에이투오소울 OR \"에이투오 소울\") "
                     "(입고 OR 재입고 OR 신보 OR \"NEW RELEASE\" OR 매장) -from:A2O_SOUL -is:retweet -is:reply")
            try:
                posts = xposts.search_posts(query, since_id=sst.get("since_id"), max_results=100, pages=1 if sst.get("since_id") else 3)
                sst["at"] = now.isoformat(timespec="minutes")
                if posts:
                    sst["since_id"] = max(posts, key=lambda p_: int(p_["tweet_id"]))["tweet_id"]
                known = {str(x.get("handle") or "").lower() for x in cfg["info"].get("offline_stores") or []} - {""}
                skip = {v["handle"].lower() for v in cfg.get("x_vendors") or []} | {u.lower() for u in cfg["x_fans"]}
                if sst.get("v") != 2:  # 판별 기준을 좁혀서 예전 후보는 비움
                    sst["candidates"], sst["v"] = {}, 2
                seen, cands = sst.setdefault("seen", {}), sst.setdefault("candidates", {})
                n_new = 0
                for p_ in posts:
                    media_cand(p_)
                    # '교복 입고 나와' 같은 팬 글이 섞이지 않게 매장 입고 공지 표현만 ('입고 공지·완료·안내·되었', 재입고, 신보 입고, NEW RELEASE)
                    if not re.search(r"(신보|음반|앨범|ALBUM)?\s*입고\s*(공지|완료|안내|소식|되었|됐|했)|재입고|신보\s*입고|NEW\s?RELEASE|IN\s?STOCK|RESTOCK",
                                     p_["caption"], re.I):
                        continue
                    h, day = p_["author"], (kst_datetime(p_["timestamp"]) or "")[:10]
                    if h.lower() in known:
                        cur = seen.setdefault(h.lower(), {"date": "", "url": ""})
                        if day >= cur.get("date", ""):
                            cur.update(date=day, url=p_["permalink"])
                        lst = cur.setdefault("posts", [])
                        if not any(x["url"] == p_["permalink"] for x in lst):  # 매장의 입고 글 전부 (최근 12개)
                            lst.append({"date": day, "url": p_["permalink"], "text": store_post_title(p_["caption"])})
                            lst.sort(key=lambda x: x["date"], reverse=True)
                            del lst[12:]
                    elif h.lower() not in skip and h.lower() not in cands:
                        cands[h.lower()] = {"handle": h, "name": p_.get("author_name") or h, "date": day, "url": p_["permalink"],
                                            "text": re.sub(r"\s+", " ", p_["caption"])[:80]}
                        n_new += 1
                if len(cands) > 40:  # 오래된 후보부터 정리
                    for k in sorted(cands, key=lambda k: cands[k]["date"])[:len(cands) - 40]:
                        cands.pop(k)
                print(f"[매장] 입고 글 검색 {len(posts)}개 · 새 매장 후보 {n_new}개")
            except Exception as e:  # noqa: BLE001
                print(f"[매장] 입고 글 검색 실패: {e}")
        # 음방·투표 앱 공식 계정 — 계정 목록 없이, A2O SOUL 투표·1위 후보 글 중 X 금색 인증(기관) 계정 글만 (3시간마다, 읽은 글 수만큼 과금)
        ost = store.setdefault("x_official_votes", {})
        if ost.get("v") != 2:  # 판별 방식이 바뀌어서 예전에 모은 공식 투표 글은 지우고 다시 검색
            for pid in [k for k in store.get("posts", {}) if k.startswith("xo:")]:
                store["posts"].pop(pid)
            ost.clear()
            ost["v"] = 2
        # 음방 당일 방송 1시간 반 전 ~ 방송 1시간 뒤엔 10분마다 (1위 후보·실시간 투표 글을 바로 잡으려고, since_id라 새 글만 읽음)
        air = {"더쇼": "18:00", "쇼챔피언": "18:00", "엠카운트다운": "18:00", "뮤직뱅크": "17:15", "음악중심": "15:15", "인기가요": "15:20"}
        on_air = any(rules.SHOW_WEEKDAY.get(sh) == now.weekday()
                     and -timedelta(minutes=90) <= now - datetime.strptime(f"{now:%Y-%m-%d} {tm}", "%Y-%m-%d %H:%M").replace(tzinfo=now.tzinfo) <= timedelta(hours=1)
                     for sh, tm in air.items())
        gap = timedelta(minutes=10) if on_air else timedelta(hours=3)
        if ost.get("deep") != 1 or not ost.get("at") or now - datetime.fromisoformat(ost["at"]) >= gap:
            query = ("(\"A2O SOUL\" OR A2OSOUL OR 에이투오소울 OR \"에이투오 소울\") "
                     "(투표 OR 사전투표 OR 1위후보 OR \"1위 후보\" OR vote OR voting OR nominee OR nominees) "
                     "-from:A2O_SOUL -is:retweet -is:reply")
            try:
                # 팬 글이 많아서 최신 50개만 보면 며칠 전 공식 글을 놓침 → 처음 한 번은 최근 7일을 5쪽(최대 500개)까지
                deep = ost.get("deep") != 1
                posts = xposts.search_posts(query, since_id=None if deep else ost.get("since_id"),
                                            max_results=100, pages=5 if deep else 2)
                ost["at"] = now.isoformat(timespec="minutes")
                ost["deep"] = 1
                vend = {v["handle"].lower() for v in cfg.get("x_vendors") or []} | {u.lower() for u in cfg["x_fans"]}
                known = {u.lower() for u in cfg["x_vote_accounts"]}  # 파란 인증이라 자동으로 못 가리는 투표 앱·음방 공식 계정
                official = [p_ for p_ in posts if p_["author"].lower() not in vend
                            and (p_.get("verified_type") in ("business", "government") or p_["author"].lower() in known)]
                # 점검용: 마지막 검색에서 몇 개를 읽었고, 인증 계정 중 누가 있었는지 (공개 계정 이름만)
                ost["last"] = {"read": len(posts), "official": sorted({p_["author"] for p_ in official}),
                               "verified": sorted({f"{p_['author']}:{p_.get('verified_type')}" for p_ in posts if p_.get("verified_type") not in (None, "none")})[:30]}
                if posts:
                    ost["since_id"] = max(posts, key=lambda p_: int(p_["tweet_id"]))["tweet_id"]
                for p_ in posts:
                    media_cand(p_)
                for p_ in official:
                    p_["id"] = "xo:" + p_["tweet_id"]
                    p_["caption"] = f"{p_['caption']}\n\n— {p_.get('author_name') or p_['author']}"  # 계정 이름(예: THE SHOW)으로도 음방·앱 찾기
                if official:
                    announce.run(official, store, today, kst_datetime, official_extract, limit)
                print(f"[공지] X 음방 공식 투표 글 {len(official)}개 (검색 {len(posts)}개 중)")
            except Exception as e:  # noqa: BLE001
                print(f"[공지] X 음방 공식 투표 검색 실패: {e}")
        # 팬 계정(정보 계정) — 일정·투표 후보만 뽑아 전부 '확인 필요' 이슈로 (사이트에 바로 반영 안 함, 새 글 피드에도 안 섞음)
        fstate = store.setdefault("x_fans", {})
        for username in cfg["x_fans"]:
            st = fstate.setdefault(username, {})
            try:
                st.setdefault("id", xposts.user_id(username))
                posts = xposts.fetch_posts(st["id"], username, since_id=st.get("since_id"))
            except Exception as e:  # noqa: BLE001
                print(f"[공지] X 팬 계정 @{username} 조회 실패: {e}")
                continue
            print(f"[공지] X 팬 계정 @{username} 새 글 {len(posts)}개")
            if posts:
                st["since_id"] = max(posts, key=lambda p: int(p["tweet_id"]))["tweet_id"]
                for xp in posts:
                    xp["id"] = "xf:" + xp["tweet_id"]
                announce.run(posts, store, today, kst_datetime, fan_extract, limit)
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
    lines = ["공식 인스타·X 공지(와 팬 계정)에서 자동으로 뽑았지만 확신이 낮아 사이트에 바로 넣지 않은 항목이에요.",
             "**맞는 항목은 체크(☑)만 하세요** — 다음 수집(1시간 안) 때 사이트에 자동으로 들어가요. 틀린 건 그냥 두면 돼요.",
             "날짜가 비었거나 틀렸으면 체크하지 말고 `schedule.yml`에 직접 적어 주세요.", ""]
    for p in pending:
        when = " ".join(x for x in [p.get("date") or "", p.get("time") or ""] if x) or "날짜 없음"
        lines.append(f"- [ ] **{p['label']}** {p['title']} · {when}{' · ' + p['place'] if p.get('place') else ''}"
                     f" · 확신 {p['confidence']:.0%} · [원문]({p.get('post')}) <!-- key:{p['key']} -->")
    path.write_text("\n".join(lines) + "\n", "utf-8")


def write_health(cfg, videos, members, today, official=(), store_cands=None, media_state=None):
    """수집 점검 → data/health.md (워크플로가 '수집 점검' 이슈로 올림). 문제가 없으면 파일 삭제."""
    secs = []
    known = {m["name"] for m in cfg["members"]}
    # 1) 멤버를 못 찾았거나 여러 명이 잡힌 개인 직캠
    odd = []
    for v in videos:
        if v["category"] != "fancam" or v["member"]:
            continue
        guess = re.search(r"A2O SOUL\s+([A-Z][A-Z\-]{1,15})\s+(?:FanCam|Fancam|직캠)|A2O SOUL\s+([가-힣]{1,4})\s+직캠", v["title"])
        name = guess and (guess.group(1) or guess.group(2))
        if (name and name.upper() not in known and name not in ("직캠",)) or len(v["members"]) > 1:
            odd.append(f"- [{v['title']}](https://youtu.be/{v['id']}) — 잡힌 멤버: {', '.join(v['members']) or '없음'}")
    if odd:
        secs.append(("멤버를 못 찾은 직캠", "`members.yml`의 `aliases`에 표기를 추가하거나 `targets.yml` `videos:`에서 직접 지정", odd))
    # 2) 공식 채널 업로드가 2주 넘게 없음
    stale = []
    for label, cid in official:
        last = max((kst_date(v["published_at"]) for v in videos if v.get("channel_id") == cid and v.get("published_at")), default="")
        if last and (date.fromisoformat(today) - date.fromisoformat(last)).days > 14:
            stale.append(f"- {label}: 마지막 영상 {last}")
    if stale:
        secs.append(("2주 넘게 새 영상이 없는 공식 채널", "채널 ID가 바뀌었거나 수집이 막혔는지 확인", stale))
    # 3) 사진·서명 없는 멤버
    no_photo = [m["name"] for m in members if not m.get("photo")]
    no_sign = [m["name"] for m in members if not m.get("signature")]
    if no_photo or no_sign:
        rows = ([f"- 사진 없음: {', '.join(no_photo)}"] if no_photo else []) + ([f"- 서명 없음: {', '.join(no_sign)}"] if no_sign else [])
        secs.append(("사진·서명이 없는 멤버", "`site/img/members/`에 `라벨_이름` 형식으로 올리기", rows))
    # 4) 번역이 빠진 문구
    tr = cfg.get("tr") or {}
    texts = [x.get("label", "") for x in cfg["group_links"]]
    for m in cfg["members"]:
        texts += [str(m.get("position") or "")] + [str(x) for k in ("nicknames", "career", "notes") for x in m.get(k) or []]
    texts += cfg["info"]["lore"] + [a["type"] for a in cfg["info"]["albums"]]
    texts += [x["label"] for x in cfg["info"]["shops"]] + [x["note"] for x in cfg["info"]["shops"]]
    texts += [x[k] for x in cfg["info"]["chain_stores"] if not x["langs"] for k in ("name", "note")]
    texts += [a["note"] for a in cfg["info"]["albums"]] + [v for a in cfg["info"]["albums"] for v in a["versions"]]
    texts += [cfg["stream_playlist"].get("title", ""), cfg["stream_playlist"].get("desc", "")] + cfg["stream_playlist"].get("tips", [])
    texts += [x["note"] for x in cfg["streaming"]] + [str(v.get(k) or "") for v in cfg["votes"] for k in ("show", "app", "title", "note")]
    for v in cfg["howto"]["voting"]:
        texts += [v.get(k, "") for k in ("when", "pre", "live", "note")]
    for g in cfg["howto"]["streaming"]:
        texts += [g["title"]] + g["steps"]
    for b in cfg["guide"]["beginner"]:
        texts += [b["title"]] + b["items"]
    texts += [c["note"] for c in cfg["guide"]["course"]]
    missing = sorted({x for x in texts if x and re.search(r"[가-힣]", x) and set(tr.get(x, {})) < {"en", "ja", "zh", "es", "id", "th", "pt"}})
    if missing:
        secs.append(("번역이 없는 문구", "`translations.yml`에 원문 그대로 추가 (en·ja·zh·es·id·th)", [f"- {x}" for x in missing]))
    # 오프라인 매장 후보: 'A2O SOUL 입고' 글을 올린, 목록에 없는 계정
    if store_cands:
        rows = [f"- @{c['handle']} {c['name']} · {c['date']} · [글]({c['url']}) — {c['text']}"
                for c in sorted(store_cands.values(), key=lambda c: c["date"], reverse=True)[:20]]
        secs.append(("새 오프라인 매장 후보", "매장 공식 계정이 맞으면 `info.yml` offline_stores에 추가 (리셀러·팬 계정은 무시)", rows))
    # 매체·콘텐츠: 없는 아이디, 새 후보
    ms = media_state or {}
    if ms.get("missing"):
        secs.append(("없는 매체 아이디", "`targets.yml` x_media에서 고치거나 빼기 (바뀐 아이디일 수 있어요)", [f"- @{h}" for h in ms["missing"]]))
    if ms.get("candidates"):
        rows = [f"- @{c['handle']} {c['name']} · {c['date']} · [글]({c['url']}) — {c['text']}"
                for c in sorted(ms["candidates"].values(), key=lambda c: c["date"], reverse=True)[:20]]
        secs.append(("새 매체·콘텐츠 계정 후보", "A2O SOUL 글을 올린 인증 기업 계정 — 매체가 맞으면 `targets.yml` x_media에 추가", rows))
    # 5) 투표 가이드가 오래됨
    checked = cfg["howto"].get("checked") or ""
    if checked and (date.fromisoformat(today) - date.fromisoformat(checked[:10])).days > 60:
        secs.append(("투표 가이드 점검", "`howto.yml` 음방 투표 앱이 맞는지 확인하고 `checked` 날짜 바꾸기", [f"- 마지막 확인 {checked}"]))

    path = DATA / "health.md"
    if not secs:
        path.unlink(missing_ok=True)
        return
    lines = ["사이트 데이터에서 손봐야 할 것들을 모아 둔 이슈예요. 수집할 때마다 갱신되고, 다 해결되면 자동으로 닫혀요.", ""]
    for title, how, rows in secs:
        lines += [f"### {title} ({len(rows)})", f"_{how}_", "", *rows[:30], *(["- …"] if len(rows) > 30 else []), ""]
    path.write_text("\n".join(lines), "utf-8")


def write_calendar(cfg, extra_events=()):
    """일정·생일·투표 마감·서포트를 iCal(.ics)로 → 휴대폰 캘린더 구독용."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//A2O SOUL Tracker//KO", "CALSCALE:GREGORIAN",
             "METHOD:PUBLISH", "X-WR-CALNAME:A2O SOUL", "X-WR-TIMEZONE:Asia/Seoul", "REFRESH-INTERVAL;VALUE=DURATION:PT6H",
             "BEGIN:VTIMEZONE", "TZID:Asia/Seoul", "BEGIN:STANDARD", "DTSTART:19700101T000000",
             "TZOFFSETFROM:+0900", "TZOFFSETTO:+0900", "TZNAME:KST", "END:STANDARD", "END:VTIMEZONE"]

    def event(uid, summary, start, end=None, all_day=False, rrule=None, url=None, desc=None, alarms=()):
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
        for mins in alarms:  # 마감 전 알림 (구독 캘린더에서 알림을 지원하는 앱만)
            lines.extend(["BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{_ics_escape(summary)}", f"TRIGGER:-PT{mins}M", "END:VALARM"])
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
              desc=f"앱: {v['app']}" if v.get("app") else None, alarms=(180, 30))
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
    for pid, post in (load_json("announcements.json", {}).get("posts") or {}).items():
        if not pid.startswith("x:") or not post.get("caption"):
            continue
        text = re.sub(r"\s*https://t\.co/\S+", "", post["caption"]).strip()
        ig_feed.append({"account": "x", "at": kst_datetime(post.get("timestamp")), "text": text[:300], "more": len(text) > 300,
                        "url": post.get("permalink"), "likes": None, "comments": None, "members": detect_members(cfg, text)})
    ig_feed.sort(key=lambda x: x["at"], reverse=True)
    # 같은 글을 인스타·X에 같이 올린 경우 하나만 (첫 문장이 같고 3시간 안)
    def first_line(t):
        for ln in t.splitlines():
            ln = re.sub(r"^\[[^\]]*\]\s*", "", ln).strip()
            if re.search(r"[가-힣A-Za-z]{2}", ln) and not ln.startswith("#"):
                return re.sub(r"\W+", "", ln.lower())[:40]
        return ""
    kept = []
    for x in ig_feed:
        k = first_line(x["text"])
        dup = k and any(first_line(y["text"]) == k and abs((datetime.fromisoformat(y["at"]) - datetime.fromisoformat(x["at"])).total_seconds()) < 3 * 3600
                        for y in kept)
        if not dup:
            kept.append(x)
    feed_all = ig_feed  # 화면은 인스타 | X 두 칸이라 칸마다 따로 (같은 글이 양쪽에 있어도 OK)
    ig_feed = kept      # 멤버 언급은 중복 없이

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
        if vid not in overrides and (other_group_only(reg["title"]) or other_trainee_only(cfg, reg["title"])):
            continue  # A2O LITE 단독 영상, 소울 멤버가 아닌 연습생 개인 영상
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
            "channel_id": reg.get("channel_id"),
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
            "series", "show", "era")
    eras = era_list(cfg)
    for v in videos:
        v["fanchant"] = bool(FANCHANT.search(v["title"]))
        v["era"] = "" if v["predebut"] else era_of(eras, v)
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
        sign_src = read_yml("members.yml").get("signature_sources") or {}
        members.append({
            "name": m["name"],
            "ko": m.get("ko", ""),
            "nationality": m.get("nationality", ""),
            "birth_year": m.get("birth_year"),
            "position": m.get("position") or "",
            "nicknames": m.get("nicknames") or [],
            "aliases": [str(a) for a in m.get("aliases") or [] if re.fullmatch(r"[A-Za-z][A-Za-z -]+", str(a))],
            "career": m.get("career") or [],
            "notes": m.get("notes") or [],
            "instagram_posts": [str(u) for u in (m.get("instagram_posts") or [])],
            "ig_mentions": [{k: x[k] for k in ("at", "text", "more", "url")} for x in ig_feed if m["name"] in x["members"]][:10],
            "photo": local_img(m.get("photo")) or auto["photo"],
            "color": m.get("color") if isinstance(m.get("color"), (int, float)) else "",
            "signature": local_img(m.get("signature")) or auto["signature"],
            # 서명 여러 장: 파일 이름 앞 라벨(서명·사인)별 출처·날짜는 members.yml signature_sources
            "signatures": [{"src": rel, **({k: str(v) for k, v in (sign_src.get(label) or {}).items() if k in ("label", "url") and v})}
                           # 최신순: signature_sources의 date가 늦은 것부터, 날짜 없는 것(처음 올린 서명)은 맨 뒤
                           for label, rel in sorted(auto["signs"], key=lambda x: str((sign_src.get(x[0]) or {}).get("date") or ""), reverse=True)],
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
    auto_events, notices, pending, auto_votes, prerecs = auto_items(today)
    have = {(v["end"], v.get("show", ""), v.get("title", "")) for v in cfg["votes"]}
    have_app = {(v["end"][:10], v.get("app", "")) for v in cfg["votes"] if v.get("app")}
    cfg["votes"] += [v for v in auto_votes if (v["end"], v["show"], v["title"]) not in have
                     and not (v["app"] and (v["end"][:10], v["app"]) in have_app)]
    seen = {(e["date"], e["title"]) for e in cfg["events"]}
    annivs = anniversaries(cfg["debut_date"])
    soon = (date.fromisoformat(today) + timedelta(days=120)).isoformat()
    # 지난 일정도 달력에 남김 (PAST_DAYS일 전까지) — 목록·'다가오는 일정'은 화면에서 오늘 이후만
    past_from = (date.fromisoformat(today) - timedelta(days=PAST_DAYS)).isoformat()
    all_events = sorted([e for e in cfg["events"] if e["date"] >= past_from]
                        + [e for e in auto_events + youtube_upcoming(registry, today) if (e["date"], e["title"]) not in seen]
                        + [a for a in annivs if past_from <= a["date"] <= soon],
                        key=lambda e: (e["date"], e.get("time") or ""))
    # 지난 음방 출연: 음방 영상이 올라온 회차 → 달력에 '○○ 출연' (공지로 이미 잡힌 날은 건너뜀)
    have = {(e["date"], e["title"]) for e in all_events}
    for ep in episodes:
        title = f"{ep['show']} 출연"
        if ep["date"] < today and ep["date"] >= past_from and (ep["date"], title) not in have:
            vid = next((v for v in ep["videos"] if v["category"] != "fancam"), ep["videos"][0])
            all_events.append({"date": ep["date"], "time": None, "type": "음방", "title": title,
                               "url": f"https://youtu.be/{vid['id']}", "auto": True, "past": True})
            have.add((ep["date"], title))
    all_events.sort(key=lambda e: (e["date"], e.get("time") or ""))
    write_pending(pending)
    recent = sorted((v for v in videos if v["category"] != "fancam"),
                    key=lambda v: v["published_at"] or "", reverse=True)[:12]
    today = datetime.now(KST).date().isoformat()

    stores_state = load_json("announcements.json", {}).get("x_stores") or {}
    media_state = load_json("announcements.json", {}).get("x_media") or {}
    dashboard = {
        "updated_at": registry.get("collected_at"),
        "debut_date": cfg["debut_date"],
        "kpis": kpis,
        "accounts": accounts,
        "ig_feed": [x for x in feed_all if x["account"] != "x"][:15] + [x for x in feed_all if x["account"] == "x"][:15],
        "photos": photo_feed(cfg, registry, load_json("announcements.json", {})),
        "notice_posts": notice_feed(cfg, registry, load_json("announcements.json", {})),
        "media_posts": media_feed(cfg, media_state),
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
        "notices": sorted(notices, key=lambda x: (x.get("date") or "9999", x.get("time") or "99:99")),  # 가까운 날짜부터
        "categories": CATEGORIES,
        "feedback_url": str(cfg.get("feedback_url") or ""),
        "push": {k: str(v) for k, v in (cfg.get("push") or {}).items() if k in ("api", "vapid_public") and v},
        "yt_channels": sorted(registry.get("channels") or {}),  # Cloudflare Worker가 YouTube 새 영상 즉시 알림(WebSub) 구독에 씀
        "votes": [v for v in cfg["votes"] if v["end"] >= now_kst_str()],
        "prerecs": prerecs,
        "nominees": nominees(today),
        "photocards": photocards(cfg),
        "streaming": cfg["streaming"],
        "stream_playlist": cfg["stream_playlist"],
        "charts": cfg["charts"],
        "chart_moves": cfg.get("chart_moves", [])[-30:],
        "supports": sorted((x for x in cfg["supports"] if x["end"] >= today), key=lambda x: x["start"]),
        "howto": cfg["howto"],
        "tr": cfg["tr"],
        "info": {**cfg["info"], "offline_stores": [  # 입고 글이 더 최근에 잡혔으면 날짜·글 링크 갱신 + 입고 글 목록
            {**x, **({"date": seen["date"], "url": seen["url"]} if (seen := (stores_state.get("seen") or {}).get(x["handle"].lower()) or {})
                      and seen.get("date", "") >= x["date"] else {}),
             "posts": store_posts(x, seen)}
            for x in cfg["info"].get("offline_stores") or []]},
        "guide": {"course": [{**c, **{k: by_id[c["id"]][k] for k in slim}}
                             for c in cfg["guide"]["course"] if c["id"] in by_id],
                  "tips": cfg["guide"]["tips"], "beginner": cfg["guide"]["beginner"]},
    }
    save_json("dashboard.json", dashboard)
    write_calendar(cfg, [e for e in all_events if e.get("auto") and not e.get("anniv") and not e.get("past")] + annivs)
    official = [(registry["channels"].get(channel_id(c), {}).get("title") or channel_id(c), channel_id(c))
                for c in cfg["channels"] if (c.get("kpi") or c.get("mv")) and channel_id(c)]
    write_health(cfg, videos, members, today, official, stores_state.get("candidates") or {}, media_state)
    print(f"dashboard.json 생성: 영상 {len(videos)}개 (MV {len(mvs)}, 직캠 {len(fancams)}), 일정 {len(dashboard['events'])}개")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true", help="수집 없이 dashboard.json만 생성")
    ap.add_argument("--rescan", action="store_true", help="채널 업로드를 처음부터 다시 훑기 (필터·멤버 표기 바꾼 뒤)")
    args = ap.parse_args()
    cfg = load_config()
    if not args.build:
        collect(cfg, rescan=args.rescan)
        api = (cfg.get("push") or {}).get("api")
        if api:  # 총공팀이 입력한 차트 순위 (chart.html → Worker)
            try:
                r = requests.get(f"{api.rstrip('/')}/charts", timeout=20)
                r.raise_for_status()
                save_json("chart_entries.json", [x for x in r.json() if isinstance(x, dict)])
            except Exception as e:  # noqa: BLE001
                print(f"[차트] 입력 순위 못 받음: {e}")
    build(cfg)
    if not args.build:  # 매시간 수집 때만 (배포용 --build에선 안 보냄)
        try:
            import webpush
            save_json("push_state.json", webpush.run(load_json("dashboard.json", {}), cfg, load_json("push_state.json", {})))
        except Exception as e:  # noqa: BLE001
            print(f"[푸시] 건너뜀: {type(e).__name__} {e}")


if __name__ == "__main__":
    main()
