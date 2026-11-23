import re, requests
from bs4 import BeautifulSoup
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
for u in ["https://program.imbc.com/radio/starnight/playlist", "https://www.cbs.co.kr/program/playlist/cbs_P000221"]:
    r = requests.get(u, headers=H, timeout=20)
    print("==", u, r.status_code, len(r.text))
    s = BeautifulSoup(r.text, "html.parser")
    for x in s(["script", "style"]):
        if x.name == "script" and x.string and re.search(r"ajax|fetch|api|url", x.string, re.I):
            print("  SCRIPT", re.sub(r"\s+", " ", x.string)[:1500])
        x.decompose()
    txt = re.sub(r"\s+", " ", s.get_text(" "))
    i = txt.find("선곡")
    print("  TEXT", txt[max(0, i - 100):i + 2500])
    for a in s.find_all("a"):
        h = a.get("href") or ""
        if "playlist" in h: print("  A", a.get_text(" ", strip=True)[:30], "|", h[:150])
r = requests.get("https://program.kbs.co.kr/2radio/radio/nightyou/pc/index.html", headers=H, timeout=20)
print("== KBS", r.text[:6500])
