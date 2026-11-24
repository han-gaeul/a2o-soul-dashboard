"""Spotify 나라별 일간 차트(Top 200) 기록 → data/spotify_country.json (6시간마다)

Spotify는 나라별 총 재생 수를 공개하지 않음 → 나라별 일간 Top 200에 든 날만 그 나라 순위·재생 수가 나옴.
kworb.net(Spotify 공식 차트를 모아 두는 사이트)의 아티스트·곡 페이지에서 읽음.
"""
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "data" / "spotify_country.json"
ARTIST = "1sqWFSwBcJ6eunJRrCsmYb"  # A2O SOUL (collector/spotify.py와 같음)
KST = timezone(timedelta(hours=9))
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
CELL = re.compile(r'<span class="p">(\d+)</span>.*?<span class="s">([\d,]+)</span>', re.S)


def load():
    return json.loads(PATH.read_text()) if PATH.exists() else {"songs": {}}


def save(d):
    PATH.write_text(json.dumps(d, ensure_ascii=False, indent=1, sort_keys=True) + "\n")


def _get(url):
    r = requests.get(url, headers=UA, timeout=25)
    r.raise_for_status()
    return r.text


def run():
    d = load()
    html = _get(f"https://kworb.net/spotify/artist/{ARTIST}.html")
    tracks = re.findall(r'href="\.\./track/([A-Za-z0-9]+)\.html">([^<]+)</a>', html)
    for tid, title in tracks:
        try:
            th = _get(f"https://kworb.net/spotify/track/{tid}.html")
        except Exception as e:  # noqa: BLE001
            print(f"[Spotify 나라별] {title} 실패: {type(e).__name__}")
            continue
        tables = re.findall(r"<table>(.*?)</table>", th, re.S)
        daily = tables[-1] if tables else ""  # 마지막 표 = 일간 (앞은 주간)
        countries = re.findall(r"<th>([A-Z]{2})</th>", daily)
        days = {}
        for date, cells in re.findall(r"<tr><td>(\d{4}/\d{2}/\d{2})</td>(.*?)</tr>", daily, re.S):
            tds = re.findall(r"<td>(.*?)</td>", cells, re.S)
            for cc, td in zip(countries, tds):
                m = CELL.search(td)
                if m:
                    days.setdefault(cc, {})[date.replace("/", "-")] = [int(m[1]), int(m[2].replace(",", ""))]
        if days:
            song = d["songs"].setdefault(title.strip(), {"id": tid, "countries": {}})
            for cc, v in days.items():
                song["countries"].setdefault(cc, {}).update(v)
        print(f"[Spotify 나라별] {title}: " + (", ".join(f"{cc} {len(v)}일" for cc, v in days.items()) or "차트 기록 없음"))
    d["checked"] = datetime.now(KST).isoformat(timespec="minutes")
    save(d)


def summary():
    """곡마다 나라별: 최근 차트인 날 순위·재생, 최고 순위"""
    d = load()
    out = []
    for song, v in (d.get("songs") or {}).items():
        rows = []
        for cc, days in (v.get("countries") or {}).items():
            if not days:
                continue
            last = max(days)
            best = min(days.items(), key=lambda kv: kv[1][0])
            rows.append({"cc": cc, "last": last, "pos": days[last][0], "streams": days[last][1],
                         "peak": best[1][0], "peak_date": best[0], "days": len(days)})
        if rows:
            out.append({"song": song, "countries": sorted(rows, key=lambda r: r["peak"])})
    return {"checked": d.get("checked"), "songs": out} if out else None


if __name__ == "__main__":
    run()
    print(json.dumps(summary(), ensure_ascii=False, indent=1))
