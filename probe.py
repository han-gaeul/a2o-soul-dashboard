import re, requests
from playwright.sync_api import sync_playwright
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
r = requests.get("https://static.apis.sbs.co.kr/program-api/1.0/menu/cultwoshow", headers=H, timeout=20)
print("== menu", r.status_code, r.text[:800])
r = requests.get("https://apis.sbs.co.kr/radio-api/playlist/V0000328482/20261122", headers=H, timeout=20)
print("== pl", r.status_code, r.text[:800])
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(); seen = []
    pg.on("response", lambda r: seen.append((r.url, r.headers.get("content-type", ""))))
    try: pg.goto("https://www.sbs.co.kr/schedule/index.html?type=ra&channel=Power", wait_until="load", timeout=45000)
    except Exception as e: print("goto", e)
    pg.wait_for_timeout(6000)
    for url, ct in seen:
        if "json" in ct or "api" in url: print("  XHR", url[:250])
    hs = sorted(set(a.get_attribute("href") or "" for a in pg.query_selector_all("a")))
    for h in hs:
        if "programs.sbs.co.kr/radio" in h: print("  A", h)
    b.close()
