import re, requests
from playwright.sync_api import sync_playwright
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}

r = requests.get("https://kong2017.kbs.co.kr/api/mobile/select_song_list?program_code=R2018-0187&rtype=json&request_date=20261122&page=1&page_size=50", headers=H, timeout=20)
print("== KBS API", r.status_code, r.text[:1500])

r = requests.get("https://www.cbs.co.kr/program/playlist/cbs_P000221?date=20261121", headers=H, timeout=20)
t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", r.text))
i = t.find("방송시간 곡명")
print("== CBS date", r.status_code, t[i - 40:i + 300])

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page()
    js = []
    pg.on("response", lambda r: js.append(r.url))
    try: pg.goto("https://program.imbc.com/radio/starnight/playlist", wait_until="load", timeout=45000)
    except Exception as e: print("goto", e)
    pg.wait_for_timeout(8000)
    print("== MBC urls")
    for u in js:
        if "imbc.com" in u and not u.endswith((".png", ".jpg", ".css", ".woff2", ".svg", ".gif")): print("  ", u[:200])
    html = pg.inner_html("body")
    i = html.find("선곡표</")
    print("== MBC html", re.sub(r"\s+", " ", html)[-6000:])
    b.close()

for u in set(re.findall(r'/radio/_nuxt/[^"\']+\.js', requests.get("https://program.imbc.com/radio/starnight/playlist", headers=H).text)):
    s = requests.get("https://program.imbc.com" + u, headers=H).text
    for m in set(re.findall(r".{0,120}[Pp]laylist.{0,160}", s)):
        print("JS", u[-30:], m[:300])
