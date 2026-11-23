import re, requests
from bs4 import BeautifulSoup
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
urls = ["https://program.imbc.com/radio/starnight", "https://program.imbc.com/radio/musicparty", "https://program.imbc.com/radio/bfever",
        "https://program.imbc.com/radio/worldmorning", "https://program.kbs.co.kr/2radio/radio/nightyou/pc/index.html",
        "https://www.cbs.co.kr/program/home/cbs_P000011", "https://www.cbs.co.kr/program/home/cbs_P000221",
        "https://www.cbs.co.kr/board/list/cbs_P000011_request"]
for u in urls:
    try:
        r = requests.get(u, headers=H, timeout=20)
        print("==", u, r.status_code, len(r.text), r.url)
        s = BeautifulSoup(r.text, "html.parser")
        for a in s.find_all("a"):
            t = a.get_text(" ", strip=True); h = a.get("href") or ""
            if re.search("선곡|music|song|playlist", t + h, re.I):
                print("  A", t[:40], "|", h[:200])
        for m in list(set(re.findall(r"[\"']((?:https?:)?//[^\"']*api[^\"']*)[\"']", r.text)))[:15]:
            print("  API", m[:200])
    except Exception as e:
        print("ERR", u, e)
