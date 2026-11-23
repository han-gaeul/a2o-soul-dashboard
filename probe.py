import re
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch()
    for u in ["https://program.imbc.com/radio/starnight/playlist", "https://program.kbs.co.kr/2radio/radio/nightyou/pc/index.html"]:
        pg = b.new_page()
        seen = []
        pg.on("response", lambda r: seen.append((r.status, r.url, r.headers.get("content-type", ""))))
        
        try: pg.goto(u, wait_until="load", timeout=45000)
        except Exception as e: print("goto", e)
        pg.wait_for_timeout(8000)
        print("==", u)
        for s, url, ct in seen:
            if "json" in ct or "api" in url:
                print("  XHR", s, url[:250])
        txt = re.sub(r"\s+", " ", pg.inner_text("body"))
        i = txt.find("선곡")
        print("  TEXT", txt[max(0, i - 50):i + 1500])
        for a in pg.query_selector_all("a"):
            t = (a.inner_text() or "").strip(); h = a.get_attribute("href") or ""
            if "선곡" in t: print("  A", t[:30], "|", h[:200])
    b.close()
