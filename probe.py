import re, requests
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
for u in ["https://circlechart.kr/page_chart/onoff.circle", "https://circlechart.kr/page_chart/onoff.circle?nationGbn=T&serviceGbn=S1020"]:
    h = requests.get(u, headers=H, timeout=20).text
    print("==", u, len(h))
    for m in set(re.findall(r".{0,120}S10\d0.{0,120}", h)):
        print("  ", re.sub(r"\s+", " ", m))
