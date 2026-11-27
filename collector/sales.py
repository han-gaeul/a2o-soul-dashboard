"""앨범 판매량 → data/sales.json
- 써클차트 주간 앨범 차트 (공식, 매주 목요일쯤 발표): 순위·판매량 (유통사 출고량 - 반품)
- 써클차트 주간 리테일 앨범 차트 (소매점 실제 판매량, Top 50): 순위·판매량
- 한터 초동 일차별 (@koreansales_twt 글의 DAY·TOTAL)
- 한터 차트 일간·주간 판매량 (hanteochart.com 공식 차트 API, 100위 안에 있을 때) — 초동 이후 판매량
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
    """써클 주간 앨범 차트 — 버전(예: SUPERSTAR, SUPERSTAR (Nemo))이 따로 오르면 합침.
    차트가 아직 안 나왔으면 None, 나왔는데 100위 안에 없으면 out=True"""
    r = requests.post("https://circlechart.kr/data/api/chart/album", timeout=20,
                      data={"nationGbn": "T", "termGbn": "week", "hitYear": str(year), "targetTime": str(week), "yearTime": "3", "curUrl": "x"},
                      headers={"User-Agent": "Mozilla/5.0", "Referer": "https://circlechart.kr/page_chart/album.circle"})
    r.raise_for_status()
    rows = [x for x in (r.json().get("List") or {}).values() if isinstance(x, dict)]
    if not rows:
        return None
    hit = [x for x in rows if ARTIST_RX.search(x.get("ARTIST_NAME") or "") and ALBUM.lower() in (x.get("ALBUM_NAME") or "").lower()]
    if not hit:  # 100위 밖 — 써클은 100위 밖 판매량을 공개 안 함, 100위 판매량(=이보다 적게 팔림)만 남김
        cut = min(int(x.get("Album_CNT") or 0) for x in rows)
        return {"rank": None, "sales": 0, "out": True, "cut": cut, "v": 3}
    vers = [{"name": x.get("ALBUM_NAME"), "rank": int(x.get("SERVICE_RANKING") or 0), "sales": int(x.get("Album_CNT") or 0)} for x in hit]
    return {"rank": min(v["rank"] for v in vers), "sales": sum(v["sales"] for v in vers), "versions": vers, "v": 3}


def update_circle(d):
    """발매 주부터 지난주까지, 아직 없는(또는 예전 방식으로 저장된) 주만 물어봄"""
    today = datetime.now(KST).date()
    wk = RELEASE
    while wk <= today - timedelta(days=4):  # 써클 주간은 다음 주 목요일쯤 나옴
        y, w, _ = wk.isocalendar()
        key = f"{y}-{w:02d}"
        if (d["circle"].get(key) or {}).get("v") != 3:
            try:
                got = circle_week(y, w)
            except Exception as e:  # noqa: BLE001
                print(f"[판매량] 써클 {key} 실패: {str(e)[:100]}")
                break
            if got is None:
                break  # 아직 발표 전
            d["circle"][key] = got
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


HT_TARGET = "912566026"  # 한터 SUPERSTAR 음반 번호 (차트 페이지 targetIdx)
HT_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}


def update_hanteo_chart(d):
    """한터 공식 일간·주간 음반 차트에서 SUPERSTAR 판매량 (집계 날짜는 차트 페이지의 '집계 기준')"""
    hc = d.setdefault("hanteo_chart", {"daily": {}, "weekly": {}})
    for term in ("daily", "weekly"):
        try:
            html = requests.get(f"https://www.hanteochart.com/ko/charts/album/{term}", headers=HT_UA, timeout=20).text
            ds = re.findall(r"(\d{4})\.(\d{2})\.(\d{2})", html[html.find("집계 기준"):][:120])
            j = requests.get(f"https://www.hanteochart.com/api/chart-sales?type=album&term={term}&genre=basic", headers=HT_UA, timeout=20).json()
        except Exception as e:  # noqa: BLE001
            print(f"[판매량] 한터 {term} 실패: {type(e).__name__}")
            continue
        if not ds:
            print(f"[판매량] 한터 {term}: 집계 날짜 못 읽음")
            continue
        x = next((r for r in j.get("sales") or [] if str(r.get("targetIdx")) == HT_TARGET), None)
        key = "-".join(ds[0])
        if x:
            row = {"rank": int(x["rank"]), "sales": int(x["salesVolume"])}
            if term == "weekly" and len(ds) > 1:
                row["end"] = "-".join(ds[1])
            hc[term][key] = row
        print(f"[판매량] 한터 {term} {key}: {x and x['salesVolume']}장 {x and x['rank']}위" if x else f"[판매량] 한터 {term} {key}: 100위 밖")


HT_RANK = re.compile(r'"rank":(\d+),"rankDiff":-?\d+,"targetIdx":"' + HT_TARGET + '"')


def _ht_rank(path):
    """한터 공식 차트 지난 발행본 페이지 → SUPERSTAR 순위 (판매량은 최신 발행본만 공개라 순위만). 100위 밖 = 0"""
    r = requests.get(f"https://www.hanteochart.com/ko/charts/album/{path}", headers=HT_UA, timeout=20)
    r.raise_for_status()
    m = HT_RANK.search(r.text.replace('\\"', '"'))
    return int(m.group(1)) if m else 0


def update_hanteo_ranks(d):
    """발매일부터 어제까지 일간 순위, 발매 주부터 지난주까지 주간 순위 — 없는 것만 한 번씩"""
    rk = d.setdefault("hanteo_chart", {}).setdefault("ranks", {"daily": {}, "weekly": {}})
    today = datetime.now(KST).date()
    day = RELEASE
    while day < today:
        k = day.isoformat()
        if k not in rk["daily"]:
            try:
                rk["daily"][k] = _ht_rank(f"daily/{k}")
                print(f"[판매량] 한터 일간 {k}: {rk['daily'][k] or '100위 밖'}")
            except Exception as e:  # noqa: BLE001
                print(f"[판매량] 한터 일간 {k} 실패: {type(e).__name__}")
                break
        day += timedelta(days=1)
    wk = RELEASE - timedelta(days=RELEASE.weekday())
    while wk + timedelta(days=6) < today:
        y, w, _ = wk.isocalendar()
        k = f"{y}-W{w:02d}"
        if k not in rk["weekly"]:
            try:
                rk["weekly"][k] = _ht_rank(f"weekly/{k}")
                print(f"[판매량] 한터 주간 {k}: {rk['weekly'][k] or '100위 밖'}")
            except Exception as e:  # noqa: BLE001
                print(f"[판매량] 한터 주간 {k} 실패: {type(e).__name__}")
                break
        wk += timedelta(days=7)


def circle_retail_week(sunday):
    """써클 리테일 앨범 차트 (일~토, 주 시작 일요일 날짜로 조회). 아직 안 나왔으면 None, 50위 밖이면 out=True"""
    r = requests.post("https://circlechart.kr/data/api/chart/retail_list", timeout=20,
                      data={"termGbn": "week", "yyyymmdd": sunday.strftime("%Y%m%d")},
                      headers={"User-Agent": "Mozilla/5.0", "Referer": "https://circlechart.kr/page_chart/retail.circle"})
    r.raise_for_status()
    rows = [x for x in (r.json().get("List") or {}).values() if isinstance(x, dict)]
    if not rows:
        return None
    hit = [x for x in rows if ARTIST_RX.search(x.get("Artist") or "") and ALBUM.lower() in (x.get("Album") or "").lower()]
    if not hit:
        return {"rank": None, "sales": 0, "out": True, "cut": min(int(x.get("rowSum") or 0) for x in rows)}
    vers = [{"name": x.get("Album"), "rank": int(x.get("RankOrder") or 0), "sales": int(x.get("rowSum") or 0)} for x in hit]
    return {"rank": min(v["rank"] for v in vers), "sales": sum(v["sales"] for v in vers), "versions": vers}


def update_retail(d):
    """발매 주(일요일 시작)부터, 끝난 주 중 아직 없는 주만"""
    today = datetime.now(KST).date()
    sun = RELEASE - timedelta(days=(RELEASE.weekday() + 1) % 7)
    rt = d.setdefault("retail", {})
    while sun + timedelta(days=6) < today:
        key = sun.isoformat()
        if key not in rt:
            try:
                got = circle_retail_week(sun)
            except Exception as e:  # noqa: BLE001
                print(f"[판매량] 써클 리테일 {key} 실패: {str(e)[:100]}")
                break
            if got is None:
                break  # 아직 발표 전
            rt[key] = got
            print(f"[판매량] 써클 리테일 {key}: {got}")
        sun += timedelta(days=7)


def run(xposts=None):
    d = load()
    update_circle(d)
    update_retail(d)
    update_hanteo_chart(d)
    update_hanteo_ranks(d)
    if xposts is not None and xposts.enabled():
        update_hanteo(d, xposts)
    d["checked"] = datetime.now(KST).isoformat(timespec="minutes")
    save(d)


def summary():
    """사이트 차트 칸: 한터 초동·일차별, 써클 주간"""
    d = load()
    h = d.get("hanteo") or {}
    days = sorted(((int(k), v) for k, v in (h.get("days") or {}).items()))
    weeks = [{"week": k, **v} for k, v in sorted((d.get("circle") or {}).items()) if v and (v.get("sales") or v.get("out"))]
    hc = d.get("hanteo_chart") or {}
    first_end = (RELEASE + timedelta(days=6)).isoformat()
    ht_days = [{"date": k, **v} for k, v in sorted((hc.get("daily") or {}).items()) if k > first_end]  # 초동 이후 일간
    ht_weeks = [{"start": k, **v} for k, v in sorted((hc.get("weekly") or {}).items())]
    if not days and not weeks and not ht_weeks:
        return None
    first = sum(v for k, v in days if k <= 7) if len([k for k, _ in days if k <= 7]) == 7 else None
    rk = hc.get("ranks") or {}
    y, w, _ = RELEASE.isocalendar()
    wk1 = f"{y}-W{w:02d}"

    def day_row(k, v):
        iso = (RELEASE + timedelta(days=k - 1)).isoformat()
        return {"day": k, "date": iso, "n": v, "rank": (rk.get("daily") or {}).get(iso) or None}
    return {"album": d.get("album") or ALBUM, "release": RELEASE.isoformat(),
            "hanteo": {"days": [day_row(k, v) for k, v in days],
                       "total": h.get("total"), "first_week": first, "post": h.get("post"),
                       "week_rank": (rk.get("weekly") or {}).get(wk1) or None,
                       "week_url": f"https://www.hanteochart.com/ko/charts/album/weekly/{wk1}"},
            "circle": weeks, "retail": [{"start": k, **v} for k, v in sorted((d.get("retail") or {}).items())],
            "hanteo_daily": ht_days, "hanteo_weekly": ht_weeks}
