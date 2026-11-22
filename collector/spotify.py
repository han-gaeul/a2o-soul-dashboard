"""Spotify 아티스트 페이지의 '인기' 곡 누적 재생 수 → data/spotify.json (하루 한 번, GitHub Actions에서)

Spotify 공개 API엔 재생 수가 없어서, 로그인 없이 보이는 웹 플레이어 아티스트 페이지를 브라우저로 열어 읽음.
하루 재생 수 = 오늘 누적 − 어제 누적 (build에서 계산)
"""
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ARTIST = "1sqWFSwBcJ6eunJRrCsmYb"  # A2O SOUL
PATH = Path(__file__).resolve().parent.parent / "data" / "spotify.json"


def read_counts():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(locale="ko-KR")
        pg.goto(f"https://open.spotify.com/artist/{ARTIST}", wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_selector('[data-testid="tracklist-row"]', timeout=45000)
        pg.wait_for_timeout(2500)
        rows = pg.eval_on_selector_all('[data-testid="tracklist-row"]', "rs => rs.map(r => r.innerText)")
        b.close()
    out = {}
    for r in rows:
        parts = [x.strip() for x in r.split("\n") if x.strip()]
        nums = [x for x in parts if re.fullmatch(r"\d{1,3}(,\d{3})+|\d{4,}", x)]
        if len(parts) >= 2 and nums:
            out[parts[1]] = int(nums[0].replace(",", ""))
    return out


def main():
    data = json.loads(PATH.read_text()) if PATH.exists() else {"artist": ARTIST, "days": {}}
    counts = read_counts()
    if not counts:
        sys.exit("[Spotify] 재생 수를 못 읽었어요 (페이지 구조 바뀜?)")
    day = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d")
    data["days"][day] = counts
    data["days"] = dict(sorted(data["days"].items())[-120:])
    PATH.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n")
    print(f"[Spotify] {day}: " + " · ".join(f"{k} {v:,}" for k, v in counts.items()))


if __name__ == "__main__":
    main()
