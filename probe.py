import re, requests
from playwright.sync_api import sync_playwright
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
for ch in ["Power", "Love"]:
    r = requests.get(f"https://static.cloud.sbs.co.kr/schedule/2026/11/23/{ch}.json", headers=H, timeout=20)
    print("== SBS", ch, r.status_code, r.text[:1200])
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page()
    try: pg.goto("https://www.cbs.co.kr/schedule/radio", wait_until="load", timeout=45000)
    except Exception as e: print("goto", e)
    pg.wait_for_timeout(6000)
    seen = set()
    for a in pg.query_selector_all("a"):
        h = a.get_attribute("href") or ""; t = re.sub(r"\s+", " ", a.inner_text() or "").strip()
        m = re.search(r"cbs_P\d+", h)
        if m and m.group(0) not in seen:
            seen.add(m.group(0)); print("  CBS", m.group(0), t[:40])
    print("  CBSTEXT", re.sub(r"\s+", " ", pg.inner_text("body"))[:1500])
    b.close()
