"""배포 직전: 음방 1위 후 7일 동안 링크 미리보기(og:image·제목·설명)를 1위 축하용으로 바꿈.
사용: python collector/og_win.py _site   (data/dashboard.json의 기록 중 og가 있는 1위)"""
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))
SITE = "https://a2osoul-tracker.com/"


def main(out):
    dash = json.loads(Path("data/dashboard.json").read_text(encoding="utf-8"))
    today = datetime.now(KST).date()
    wins = sorted((x for x in dash.get("timeline") or [] if x.get("kind") == "win" and x.get("og")), key=lambda x: x["date"])
    if not wins:
        return
    w = wins[-1]
    if (today - datetime.fromisoformat(w["date"]).date()).days > 7 or not (Path(out) / w["og"]).exists():
        return
    first = len([x for x in dash["timeline"] if x.get("kind") == "win"]) == 1
    title = f"🏆 A2O SOUL {'데뷔 첫 음방 1위!' if first else w['show'] + ' 1위!'}"
    desc = f"{w['show']}{' ' + w['ep'] + '회' if w.get('ep') else ''} · {w['date'].replace('-', '.')} — 투표·음방 일정 한눈에"
    img = SITE + w["og"]
    p = Path(out) / "index.html"
    html = p.read_text(encoding="utf-8")
    subs = {r'(<meta property="og:title" content=")[^"]*(">)': title, r'(<meta property="og:description" content=")[^"]*(">)': desc,
            r'(<meta property="og:image" content=")[^"]*(">)': img}
    for rx, val in subs.items():
        html = re.sub(rx, lambda m: m.group(1) + val.replace("&", "&amp;").replace('"', "&quot;") + m.group(2), html)
    if 'name="twitter:image"' not in html:
        html = html.replace('<meta name="twitter:card" content="summary_large_image">',
                            f'<meta name="twitter:card" content="summary_large_image">\n<meta name="twitter:image" content="{img}">')
    p.write_text(html, encoding="utf-8")
    print(f"[og] 1위 미리보기 적용: {title}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "_site")
