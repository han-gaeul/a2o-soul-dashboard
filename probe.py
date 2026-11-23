import re, requests
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
for prog in ["starnight", "musicparty", "bfever", "worldmorning"]:
    h = requests.get(f"https://program.imbc.com/radio/{prog}/playlist", headers=H, timeout=20).text
    codes = re.findall(r'"touchCode":(\d+)', h)
    m = re.search(r'"(R[A-Z]{2,5}\d{3,4}) ?"', h)
    print("==", prog, m and m.group(1))
code = "RASFM210"
r = requests.get(f"https://miniweb.imbc.com/Music?page=1&progCode={code}", headers=H, timeout=20)
print("== list", r.status_code, len(r.text))
t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", r.text, flags=re.S)))
print("  TEXT", t[:1500])
links = re.findall(r'href="([^"]*)"', r.text) + re.findall(r"onclick=\"([^\"]*)\"", r.text)
for l in links[:60]: print("  L", l[:160])
