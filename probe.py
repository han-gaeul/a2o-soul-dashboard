import re, requests
from playwright.sync_api import sync_playwright
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
for u in ["https://www.cbs.co.kr/program/playlist/cbs_P000011", "https://www.cbs.co.kr/schedule/radio"]:
    r = requests.get(u, headers=H, timeout=20)
    print("== CBS", u, r.status_code)
    for code, name in sorted(set(re.findall(r"(cbs_P\d+)[^>]*>\s*(?:<[^>]+>\s*)*([^<]{2,40})<", r.text))):
        print("  ", code, name.strip())
with sync_playwright() as p:
    b = p.chromium.launch()
    for u in ["https://programs.sbs.co.kr/radio/cultwoshow/main"]:
        pg = b.new_page(); seen = []
        pg.on("response", lambda r: seen.append((r.url, r.headers.get("content-type", ""))))
        try: pg.goto(u, wait_until="load", timeout=45000)
        except Exception as e: print("goto", e)
        pg.wait_for_timeout(6000)
        print("== SBS", u)
        for a in pg.query_selector_all("a"):
            t = (a.inner_text() or "").strip(); h = a.get_attribute("href") or ""
            if "선곡" in t or "music" in h.lower(): print("  A", t[:30], "|", h[:200])
        links = [a.get_attribute("href") for a in pg.query_selector_all("a") if "선곡" in (a.inner_text() or "")]
        if links:
            seen.clear()
            l = links[0]
            try: pg.goto(l if l.startswith("http") else "https://programs.sbs.co.kr" + l, wait_until="load", timeout=45000)
            except Exception as e: print("goto2", e)
            pg.wait_for_timeout(6000)
            print("  URL", pg.url)
            for url, ct in seen:
                if "json" in ct or "api" in url: print("  XHR", url[:250])
            print("  TEXT", re.sub(r"\s+", " ", pg.inner_text("body"))[:1500])
    b.close()
