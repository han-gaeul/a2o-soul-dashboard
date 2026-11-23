"""앨범 판매량 → data/sales.json
- 써클차트 주간 앨범 차트 (공식, 매주 목요일쯤 발표): 순위·판매량
- 한터 일간 (한터 사이트엔 숫자가 안 나와서 한터 기준 수치를 올리는 @koreansales_twt 글에서 DAY·TOTAL을 읽음)
"""
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

PATH = Path(__file__).resolve().parent.parent / "data" / "sales.json"
ALBUM = "SUPERSTAR"
ARTIST_RX = re.compile(r"A2O SOUL", re.I)
RELEASE = date(2026, 11, 9)
KST = timezone(timedelta(hours=9))


def load():
    return json.loads(PATH.read_text()) if PATH.exists() else {"album": ALBUM, "circle": {}, "hanteo": {}}


def save(d):
    PATH.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n")


def circle_week(year, week):
    r = requests.post("https://circlechart.kr/data/api/chart/album", timeout=20,
                      data={"nationGbn": "T", "termGbn": "week", "hitYear": str(year), "targetTime": str(week), "yearTime": "3", "curUrl": "x"},
                      headers={"User-Agent": "Mozilla/5.0", "Referer": "https://circlechart.kr/page_chart/album.circle"})
    r.raise_for_status()
    rows = (r.json().get("List") or {}).values()
    for x in rows:
        if isinstance(x, dict) and ARTIST_RX.search(x.get("ARTIST_NAME") or "") and ALBUM.lower() in (x.get("ALBUM_NAME") or "").lower():
            return {"rank": int(x.get("SERVICE_RANKING") or 0), "sales": int(x.get("Album_CNT") or 0)}
    return None


def update_circle(d):
    """발매 주부터 지난주까지, 아직 없는 주만 물어봄 (한 번 찾은 주는 다시 안 물어봄)"""
    today = datetime.now(KST).date()
    wk = RELEASE
    while wk <= today - timedelta(days=4):  # 써클 주간은 다음 주 목요일쯤 나옴
        y, w, _ = wk.isocalendar()
        key = f"{y}-{w:02d}"
        if key not in d["circle"]:
            try:
                got = circle_week(y, w)
            except Exception as e:  # noqa: BLE001
                print(f"[판매량] 써클 {key} 실패: {str(e)[:100]}")
                break
            if got is None and wk >= today - timedelta(days=10):
                break  # 아직 발표 전
            d["circle"][key] = got or {"rank": None, "sales": 0}
            print(f"[판매량] 써클 {key}: {got}")
        wk += timedelta(days=7)


HT_DAY = re.compile(r"DAY\s*(\d+)\s*:\s*([\d,]+)", re.I)
HT_TOTAL = re.compile(r"TOTAL\s*:\s*([\d,]+)", re.I)


def update_hanteo(d, xposts):
    """@koreansales_twt '[HT] A2O SOUL ... <SUPERSTAR> DAY n: … TOTAL: …' 글 (가장 최신 값으로)"""
    h = d["hanteo"]
    try:
        posts = xposts.search_posts('from:koreansales_twt "A2O SOUL" HT', since_id=h.get("since_id"), max_results=10)
    except Exception as e:  # noqa: BLE001
        print(f"[판매량] 한터 글 검색 실패: {str(e)[:100]}")
        return
    if posts:
        h["since_id"] = max(posts, key=lambda p: int(p["tweet_id"]))["tweet_id"]
    for p in sorted(posts, key=lambda p: p.get("timestamp") or ""):
        c = p.get("caption") or ""
        if "[HT]" not in c or ALBUM.lower() not in c.lower():
            continue
        days = {int(a): int(b.replace(",", "")) for a, b in HT_DAY.findall(c)}
        tot = HT_TOTAL.search(c)
        if days:
            h.setdefault("days", {}).update({str(k): v for k, v in days.items()})
        if tot:
            h["total"] = int(tot.group(1).replace(",", ""))
            h["post"] = p.get("permalink")
            h["at"] = p.get("timestamp")
    print(f"[판매량] 한터: 일차 {len(h.get('days') or {})}개 · 누적 {h.get('total')}")


def run(xposts=None):
    d = load()
    update_circle(d)
    if xposts is not None and xposts.enabled():
        update_hanteo(d, xposts)
    d["checked"] = datetime.now(KST).isoformat(timespec="minutes")
    save(d)


def summary():
    """사이트 차트 칸: 한터 초동·일차별, 써클 주간"""
    d = load()
    h = d.get("hanteo") or {}
    days = sorted(((int(k), v) for k, v in (h.get("days") or {}).items()))
    weeks = [{"week": k, **v} for k, v in sorted((d.get("circle") or {}).items()) if v and v.get("sales")]
    if not days and not weeks:
        return None
    first = sum(v for k, v in days if k <= 7) if len([k for k, _ in days if k <= 7]) == 7 else None
    return {"album": d.get("album") or ALBUM, "release": RELEASE.isoformat(),
            "hanteo": {"days": [{"day": k, "date": (RELEASE + timedelta(days=k - 1)).isoformat(), "n": v} for k, v in days],
                       "total": h.get("total"), "first_week": first, "post": h.get("post")},
            "circle": weeks}
