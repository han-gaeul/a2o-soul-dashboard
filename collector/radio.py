"""라디오 선곡표에서 A2O SOUL 곡이 나온 방송 찾기 → data/radio.json (3시간마다, 어제·오늘)

- KBS 해피FM·쿨FM: 채널 전체 프로그램 (선곡 API에 프로그램 코드를 한 번에)
- SBS 파워FM·러브FM: 채널 편성표의 프로그램마다 선곡 API
- MBC: 프로그램 선곡표 검색(가수 'A2O') — 방송 날짜까지 나옴 (MBC_PROGS에 있는 프로그램만)
- CBS 음악FM: 프로그램 선곡표 날짜별 페이지 (CBS_PROGS에 있는 프로그램만)
"""
import html
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

PATH = Path(__file__).resolve().parent.parent / "data" / "radio.json"
KST = timezone(timedelta(hours=9))
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
ARTIST = re.compile(r"A2O\s?SOUL|에이투오\s?소울", re.I)
RELEASE = date(2026, 10, 1)  # 처음 한 번 이 날 이후를 훑음 (KBS·SBS·CBS는 날짜별이라 최근 14일만)

KBS_CH = {"22": "KBS 해피FM", "25": "KBS 쿨FM"}
SBS_CH = {"Power": "SBS 파워FM", "Love": "SBS 러브FM"}
# MBC 선곡표 검색은 프로그램마다 (주소의 프로그램 이름 → 선곡표 코드는 실행 때 찾음)
MBC_PROGS = ["starnight", "musicparty", "bfever", "worldmorning", "fmdate", "musiccamp", "radiostar", "dreamradio", "goodmorningfm"]
CBS_PROGS = {"cbs_P000011": "김현주의 행복한 동행", "cbs_P000221": "허윤희의 꿈과 음악사이에"}


def load():
    return json.loads(PATH.read_text()) if PATH.exists() else {"plays": []}


def save(d):
    PATH.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n")


def _get(url, **kw):
    r = requests.get(url, headers=UA, timeout=20, **kw)
    r.raise_for_status()
    return r


def kbs(days):
    out = []
    for ch, station in KBS_CH.items():
        progs_j = _get(f"https://pprogramapi.kbs.co.kr/api/v1/external/program?page=1&page_size=100&rtype=json&program_ch_code={ch}&end_yn=n&station_code=00").json()
        progs = {}
        for p in (progs_j.get("data") or progs_j.get("items") or []):
            m = p.get("program_code") or (re.search(r"open_program/([A-Z]\d{4}-\d{4})", json.dumps(p)) or [None, None])[1]
            if m:
                progs[m] = p.get("program_title") or p.get("title") or ""
        want = {d.strftime("%Y%m%d") for d in days}
        # 여러 프로그램을 한 번에 물으면 40곡까지만 오고 쪽 넘김도 안 돼서 프로그램·날짜마다 (2시간 방송 ≈ 30곡)
        for code in progs:
            for d in days:
                j = _get("https://kong2017.kbs.co.kr/api/mobile/select_song_list",
                         params={"program_code": code, "rtype": "json", "request_date": d.strftime("%Y%m%d"), "page": 1, "page_size": 40}).json()
                for it in j.get("items") or []:
                    ts = it.get("timestamp") or ""
                    if ts[:8] in want and ARTIST.search(it.get("artist") or ""):
                        out.append({"date": f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}", "time": f"{ts[8:10]}:{ts[10:12]}",
                                    "station": station, "program": progs[code],
                                    "song": it.get("song_title") or "", "artist": it.get("artist") or ""})
    return out


def sbs(days):
    out = []
    for ch, station in SBS_CH.items():
        for d in days:
            try:
                sched = _get(f"https://static.cloud.sbs.co.kr/schedule/{d:%Y/%m/%d}/{ch}.json").json()
            except Exception:  # noqa: BLE001
                continue
            seen = set()
            for p in sched:
                pid = (p.get("programId") or "").split("_")[-1]
                if not pid.startswith("V") or pid in seen:
                    continue
                seen.add(pid)
                try:
                    pl = _get(f"https://apis.sbs.co.kr/radio-api/playlist/{pid}/{d:%Y%m%d}").json()
                except Exception:  # noqa: BLE001
                    continue
                for it in ((pl.get("data") or {}).get("playlist") or []):
                    who = f"{it.get('ARTIST_NAME') or ''} {it.get('DISPLAY_NAME') or ''}"
                    if ARTIST.search(who):
                        t = str(it.get("END_TIME") or "")
                        out.append({"date": d.isoformat(), "time": f"{t[8:10]}:{t[10:12]}" if len(t) >= 12 else "",
                                    "station": station, "program": (it.get("BROAD_NAME") or p.get("title") or "").strip(),
                                    "song": (it.get("ALBUM_TITLE") or "").split(";")[-1].strip() or it.get("SONG_TITLE") or "",
                                    "artist": it.get("ARTIST_NAME") or "", "url": f"https://programs.sbs.co.kr/radio/{p.get('programcode')}"})
    return out


def _text(h):
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h))).strip()


def mbc():
    out = []
    for alias in MBC_PROGS:
        try:
            h = _get(f"https://program.imbc.com/radio/{alias}/playlist").text
            m = re.search(r'id="__NUXT_DATA__"[^>]*>(.*?)</script>', h, re.S)
            arr = json.loads(m.group(1))
            meta = next(o for o in arr if isinstance(o, dict) and "touchCode" in o)
            code = str(arr[meta["touchCode"]]).strip()
            title = str(arr[meta["programTitle"]]) if "programTitle" in meta else alias
        except Exception:  # noqa: BLE001 — 없는 프로그램 주소 등
            continue
        for word in ("A2O", "에이투오"):
            r = requests.post("https://miniweb.imbc.com/Music/Search", headers=UA, timeout=20,
                              data={"progCode": code, "searchType": "2", "searchWord": word})
            for row in re.findall(r"<tr>(.*?)</tr>", r.text, re.S):
                cells = [_text(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
                dm = re.search(r"(\d{4})년 (\d{1,2})월 (\d{1,2})일", cells[0] if cells else "")
                if len(cells) >= 3 and dm and ARTIST.search(cells[2]):
                    sid = re.search(r"seqID=(\d+)", row)
                    out.append({"date": f"{dm[1]}-{int(dm[2]):02d}-{int(dm[3]):02d}", "time": "", "station": "MBC FM4U",
                                "program": title, "song": cells[1], "artist": cells[2],
                                "url": f"https://miniweb.imbc.com/Music/View?seqID={sid[1]}&progCode={code}" if sid else ""})
    return out


def cbs(days):
    out = []
    for code, prog in CBS_PROGS.items():
        for d in days:
            try:
                h = _get(f"https://www.cbs.co.kr/program/playlist/{code}", params={"date": d.strftime("%Y%m%d")}).text
            except Exception:  # noqa: BLE001
                continue
            # 고른 날짜의 목록만 (페이지에 여러 날짜가 슬라이드로 들어 있음)
            for li in re.split(r"<li\b", h):
                if not re.search(rf'data-playdate=["\']{d.isoformat()}["\']', li, re.I):
                    continue
                name = re.search(r'class="name"[^>]*>(.*?)</div>', li, re.S)
                title = re.search(r'class="title"[^>]*>(.*?)</div>', li, re.S)
                tm = re.search(r'class="time"[^>]*>\s*(\d{2}:\d{2})', li)
                if name and ARTIST.search(_text(name[1])):
                    out.append({"date": d.isoformat(), "time": tm[1] if tm else "", "station": "CBS 음악FM", "program": prog,
                                "song": _text(title[1]) if title else "", "artist": _text(name[1]),
                                "url": f"https://www.cbs.co.kr/program/playlist/{code}?date={d:%Y%m%d}"})
    return out


def run():
    d = load()
    today = datetime.now(KST).date()
    back = 14 if not d.get("checked") else 1
    days = [today - timedelta(days=i) for i in range(back, -1, -1)]
    found, errs = [], []
    for name, fn in (("KBS", lambda: kbs(days)), ("SBS", lambda: sbs(days)), ("MBC", mbc), ("CBS", lambda: cbs(days))):
        try:
            got = fn()
            found += got
            print(f"[라디오] {name}: A2O SOUL {len(got)}곡")
        except Exception as e:  # noqa: BLE001
            errs.append(name)
            print(f"[라디오] {name} 실패: {type(e).__name__} {str(e)[:120]}")
    have = {(p["date"], p["station"], p["program"], p["song"].lower()) for p in d["plays"]}
    for p in found:
        k = (p["date"], p["station"], p["program"], p["song"].lower())
        if k not in have and p["date"] >= RELEASE.isoformat():
            have.add(k)
            d["plays"].append(p)
    d["plays"].sort(key=lambda p: (p["date"], p.get("time") or ""), reverse=True)
    d["checked"] = datetime.now(KST).isoformat(timespec="minutes")
    save(d)


def summary(days=30):
    d = load()
    since = (datetime.now(KST).date() - timedelta(days=days)).isoformat()
    return [p for p in d.get("plays", []) if p["date"] >= since][:20]


if __name__ == "__main__":
    run()
    print(json.dumps(load(), ensure_ascii=False, indent=1)[:3000])
