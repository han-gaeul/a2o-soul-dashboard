import re, json, requests
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36", "Accept-Language": "ko-KR,ko;q=0.9"}
def show(name, r, pat=None, n=600):
    print("==", name, r.status_code, len(r.text), r.url[:120])
    if pat:
        i = r.text.find(pat); print("  ", re.sub(r"\s+", " ", r.text[max(0, i - 300):i + n]) if i >= 0 else "  (no pat)")
# Melon
for u in ["https://www.melon.com/chart/index.htm", "https://www.melon.com/chart/hot100/index.htm", "https://www.melon.com/chart/day/index.htm"]:
    r = requests.get(u, headers=H, timeout=20); show(u, r, 'data-song-no', 900)
    print("  A2O?", len(re.findall("A2O SOUL", r.text)), "603382330" in r.text, "603877088" in r.text)
r = requests.get("https://www.melon.com/commonlike/getSongLike.json?contsIds=603382330,603877088", headers={**H, "Referer": "https://www.melon.com/"}, timeout=20); show("melon like", r, "{", 400)
# Genie
r = requests.get("https://www.genie.co.kr/chart/top200?ditc=D&rtm=Y&pg=1", headers=H, timeout=20); show("genie top200", r, 'songid=', 900)
r = requests.get("https://www.genie.co.kr/detail/songInfo?xgnm=117256250", headers=H, timeout=20); show("genie song", r, "청취자", 600)
# Bugs
r = requests.get("https://music.bugs.co.kr/chart/track/realtime/total", headers=H, timeout=20); show("bugs", r, 'trackid=', 900)
print("  A2O?", "A2O SOUL" in r.text)
# FLO
r = requests.get("https://www.music-flo.com/api/display/v1/browser/chart/1/track/list?size=100", headers=H, timeout=20); show("flo", r, '"trackList"', 600)
# Circle digital
for path, data in [("onoff", {"nationGbn": "T", "serviceGbn": "ALL", "termGbn": "week", "hitYear": "2026", "targetTime": "46", "yearTime": "3", "curUrl": "x"}),
                   ("onoff", {"nationGbn": "T", "serviceGbn": "S1020", "termGbn": "week", "hitYear": "2026", "targetTime": "46", "yearTime": "3", "curUrl": "x"}),
                   ("global", {"termGbn": "week", "hitYear": "2026", "targetTime": "46", "yearTime": "3", "curUrl": "x"})]:
    r = requests.post(f"https://circlechart.kr/data/api/chart/{path}", data=data, timeout=20, headers={**H, "Referer": "https://circlechart.kr/page_chart/onoff.circle"})
    show(f"circle {path} {data.get('serviceGbn')}", r, "{", 500)
    print("  A2O?", "A2O SOUL" in r.text)
