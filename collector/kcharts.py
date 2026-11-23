"""국내 음원 차트 자동 기록 → data/kcharts.json

- 멜론 TOP100(실시간)·HOT100·일간, 지니 TOP200, 벅스 실시간 TOP100, FLO 차트: 1시간마다 우리 곡 순위 (곡 ID로 찾음)
- 지니 곡별 전체 청취자·재생 수, 멜론 좋아요 수: 하루 한 번 (누적 → 하루 증가량은 build에서)
- 써클차트 디지털·스트리밍 주간: 하루 한 번 확인, 발표된 주만 기록
곡 ID는 votes.yml stream_playlist.songs (melon·genie·bugs·flo)
※ 멜론·지니 등은 약관상 자동 수집을 막고 있음 — 운영자가 위험을 알고 켬 (2026-11-23). 1시간에 한 번만, 요청 수 최소로.
"""
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "data" / "kcharts.json"
KST = timezone(timedelta(hours=9))
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36", "Accept-Language": "ko-KR,ko;q=0.9"}
RELEASE = date(2026, 10, 1)
DISPLAY = {"superstar": "SUPERSTAR"}  # 다른 차트(써클·Spotify)와 같은 곡 이름으로


def songs():
    sp = (yaml.safe_load((ROOT / "votes.yml").read_text()) or {}).get("stream_playlist") or {}
    out = {}
    for k, v in (sp.get("songs") or {}).items():
        if isinstance(v, dict):
            out[DISPLAY.get(str(k).lower(), str(k))] = {p: str(v[p]) for p in ("melon", "genie", "bugs", "flo") if v.get(p)}
    return out


def load():
    return json.loads(PATH.read_text()) if PATH.exists() else {"ranks": {}, "counts": {}, "circle": {}}


def save(d):
    PATH.write_text(json.dumps(d, ensure_ascii=False, indent=1, sort_keys=True) + "\n")


def _get(url, **kw):
    r = requests.get(url, headers={**UA, **kw.pop("headers", {})}, timeout=20, **kw)
    r.raise_for_status()
    return r


def _rows(html, id_rx, rank_rx):
    """표 줄마다 (곡 ID, 순위)"""
    out = {}
    for row in re.split(r"<tr\b", html)[1:]:
        i, r = re.search(id_rx, row), re.search(rank_rx, row, re.S)
        if i and r:
            out.setdefault(i[1], int(r[1]))
    return out


def melon(url):
    return _rows(_get(url).text, r'data-song-no="(\d+)"', r'<span class="rank\s*">\s*(\d+)\s*</span>')


def genie():
    out = {}
    for pg in range(1, 5):
        out.update(_rows(_get(f"https://www.genie.co.kr/chart/top200?ditc=D&rtm=Y&pg={pg}").text,
                         r'songid="(\d+)"', r'<td class="number">\s*(\d+)'))
    return out


def bugs():
    h = _get("https://music.bugs.co.kr/chart/track/realtime/total").text
    return _rows(h, r'track(?:[Ii]d="|/)(\d+)', r'<div class="ranking">\s*<strong>\s*(\d+)')


def flo():
    j = _get("https://www.music-flo.com/api/display/v1/browser/chart/1/track/list?size=100").json()
    return {str(t["id"]): i + 1 for i, t in enumerate((j.get("data") or {}).get("trackList") or [])}


CHARTS = [  # (이름, 서비스 키, 함수)
    ("멜론 TOP100", "melon", lambda: melon("https://www.melon.com/chart/index.htm")),
    ("멜론 HOT100", "melon", lambda: melon("https://www.melon.com/chart/hot100/index.htm")),
    ("멜론 일간", "melon", lambda: melon("https://www.melon.com/chart/day/index.htm")),
    ("지니 TOP200", "genie", genie),
    ("벅스 실시간", "bugs", bugs),
    ("FLO 차트", "flo", flo),
]


def ranks(d, S):
    hour = datetime.now(KST).strftime("%Y-%m-%d %H")
    for name, svc, fn in CHARTS:
        try:
            got = fn()
        except Exception as e:  # noqa: BLE001
            print(f"[음원차트] {name} 실패: {type(e).__name__} {str(e)[:80]}")
            continue
        hits = []
        for song, ids in S.items():
            r = got.get(ids.get(svc, "-"))
            if r:
                d["ranks"].setdefault(name, {}).setdefault(song, {})[hour] = r
                hits.append(f"{song} {r}위")
        print(f"[음원차트] {name}: {len(got)}곡 중 " + (", ".join(hits) or "없음"))


def counts(d, S):
    today = datetime.now(KST).date().isoformat()
    c = d["counts"]
    for song, ids in S.items():
        if ids.get("genie"):
            try:
                h = _get(f"https://www.genie.co.kr/detail/songInfo?xgnm={ids['genie']}").text
                m = re.search(r"<p>([\d,]+)</p>\s*<span><img[^>]*전체 청취자수.*?<p>([\d,]+)</p>\s*<span><img[^>]*전체 재생수", h, re.S)
                if m:
                    c.setdefault("지니 청취자", {}).setdefault(song, {})[today] = int(m[1].replace(",", ""))
                    c.setdefault("지니 재생", {}).setdefault(song, {})[today] = int(m[2].replace(",", ""))
            except Exception as e:  # noqa: BLE001
                print(f"[음원차트] 지니 {song} 실패: {type(e).__name__}")
    ids = {v["melon"]: k for k, v in S.items() if v.get("melon")}
    if ids:
        try:
            j = _get("https://www.melon.com/commonlike/getSongLike.json", params={"contsIds": ",".join(ids)},
                     headers={"Referer": "https://www.melon.com/"}).json()
            for x in j.get("contsLike") or []:
                c.setdefault("멜론 좋아요", {}).setdefault(ids[str(x["CONTSID"])], {})[today] = int(x["SUMMCNT"])
        except Exception as e:  # noqa: BLE001
            print(f"[음원차트] 멜론 좋아요 실패: {type(e).__name__}")
    print(f"[음원차트] 누적 수 기록: " + ", ".join(f"{k} {len(v)}곡" for k, v in c.items()))


def _norm(x):
    return re.sub(r"[`'’‘\s]", "", x).lower()


def circle(d, S):
    """써클 디지털(ALL)·스트리밍(S1020) 주간 — 발매 주부터 지난주까지 아직 없는 주만"""
    names = {s.lower() for s in S}
    today = datetime.now(KST).date()
    wk = RELEASE
    while wk + timedelta(days=7) <= today:
        y, w, _ = wk.isocalendar()
        key = f"{y}-{w:02d}"
        for label, svc in (("써클 디지털", "ALL"), ("써클 스트리밍", "S1040")):
            if key in d["circle"].get(label, {}):
                continue
            try:
                r = requests.post("https://circlechart.kr/data/api/chart/onoff", timeout=20,
                                  headers={**UA, "Referer": "https://circlechart.kr/page_chart/onoff.circle"},
                                  data={"nationGbn": "T", "serviceGbn": svc, "termGbn": "week", "hitYear": str(y), "targetTime": str(w), "yearTime": "3", "curUrl": "x"})
                rows = [x for x in ((r.json().get("List") or {}).values()) if isinstance(x, dict)]
            except Exception as e:  # noqa: BLE001
                print(f"[음원차트] 써클 {label} {key} 실패: {type(e).__name__}")
                continue
            if not rows:
                continue  # 아직 발표 전
            got = {}
            for x in rows:
                if re.search(r"A2O\s?SOUL|에이투오", x.get("ARTIST_NAME") or "", re.I):
                    t = (x.get("SONG_NAME") or x.get("TITLE") or "").strip()
                    nt = _norm(t)
                    song = next((s for s in S if _norm(s) == nt or _norm(s) in nt), t)
                    got[song] = int(x.get("SERVICE_RANKING") or 0)
            d["circle"].setdefault(label, {})[key] = got
            print(f"[음원차트] {label} {key}: {got or '순위 밖'}")
        wk += timedelta(days=7)


def run():
    d = load()
    S = songs()
    ranks(d, S)
    now = datetime.now(KST)
    if d.get("counts_at", "")[:10] != now.date().isoformat() and now.hour >= 1:
        counts(d, S)
        circle(d, S)
        d["counts_at"] = now.isoformat(timespec="minutes")
    d["checked"] = now.isoformat(timespec="minutes")
    save(d)


def chart_series():
    """그래프용 → [{song, service, type, ranks:[(날짜, 순위)]}] 날짜마다 그날 마지막 순위 + 누적 수의 하루 증가량(streams)"""
    d = load()
    out = []
    for name, by in (d.get("ranks") or {}).items():
        svc, typ = name.split(" ", 1)
        for song, hours in by.items():
            day = {}
            for h in sorted(hours):
                day[h[:10]] = hours[h]
            out.append({"song": song, "service": svc, "type": typ, "ranks": sorted(day.items())})
    for label, weeks in (d.get("circle") or {}).items():
        by = {}
        for wk, got in weeks.items():
            y, w = map(int, wk.split("-"))
            end = date.fromisocalendar(y, w, 6).isoformat()  # 주의 토요일
            for song, r in got.items():
                by.setdefault(song, {})[end] = r
        for song, days in by.items():
            out.append({"song": song, "service": label.split(" ")[0], "type": label.split(" ", 1)[1] + " 주간", "ranks": sorted(days.items())})
    for label, by in (d.get("counts") or {}).items():
        if label != "지니 재생":
            continue
        for song, days in by.items():
            ds = sorted(days)
            st = [(b, days[b] - days[a]) for a, b in zip(ds, ds[1:])
                  if (date.fromisoformat(b) - date.fromisoformat(a)).days == 1 and days[b] >= days[a]]
            if st:
                out.append({"song": song, "service": "지니 일간 재생", "type": "", "ranks": [], "streams": st})
    return out


def summary():
    """차트 칸 표: 지금 순위(마지막 확인 시각) + 지니·멜론 누적"""
    d = load()
    last = {}
    for name, by in (d.get("ranks") or {}).items():
        for song, hours in by.items():
            h = max(hours)
            last.setdefault(name, {})[song] = {"rank": hours[h], "at": h}
    now = (d.get("checked") or "")[:13].replace("T", " ")
    live = {n: {s: v["rank"] for s, v in by.items() if v["at"] == now} for n, by in last.items()}
    live = {n: v for n, v in live.items() if v}
    cnt = {}
    for label, by in (d.get("counts") or {}).items():
        for song, days in by.items():
            ds = sorted(days)
            cnt.setdefault(song, {})[label] = {"total": days[ds[-1]], "daily": days[ds[-1]] - days[ds[-2]] if len(ds) > 1 else None}
    return {"checked": d.get("checked"), "live": live, "counts": cnt} if (live or cnt) else None


if __name__ == "__main__":
    run()
    print(json.dumps(summary(), ensure_ascii=False, indent=1))
