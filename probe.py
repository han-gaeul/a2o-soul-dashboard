import re, requests
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
for prog in ["starnight", "musicparty", "bfever", "worldmorning"]:
    h = requests.get(f"https://program.imbc.com/radio/{prog}/playlist", headers=H, timeout=20).text
    i = h.find("touchCode")
    print("==", prog, len(h), re.findall(r'"(R[A-Z0-9]{5,9}) *"', h)[:3])
r = requests.get("https://miniweb.imbc.com/Music?page=1&progCode=RASFM210", headers=H, timeout=20)
h = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", r.text, flags=re.S)
i = h.find("2026-11-22")
print("== rows", re.sub(r"\s+", " ", h[i - 600:i + 600]))
i = h.find("분류별")
print("== form", re.sub(r"\s+", " ", h[i - 300:i + 1500]))
print("== scripts", [re.sub(r"\s+", " ", s)[:800] for s in re.findall(r"<script[^>]*>(.*?)</script>", r.text, re.S) if "Search" in s or "search" in s or "location" in s])
