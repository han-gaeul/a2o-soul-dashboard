import re, json, requests
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}


def clean(h):
    return re.sub(r"\s+", " ", re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", h, flags=re.S))


for prog in ["starnight", "musicparty", "bfever", "worldmorning"]:
    h = requests.get(f"https://program.imbc.com/radio/{prog}/playlist", headers=H, timeout=20).text
    m = re.search(r'id="__NUXT_DATA__">(.*?)</script>', h, re.S)
    arr = json.loads(m.group(1))
    code = next((arr[o["touchCode"]] for o in arr if isinstance(o, dict) and "touchCode" in o), None)
    print("==", prog, repr(code))
for word in ["아이유", "A2O SOUL"]:
    r = requests.post("https://miniweb.imbc.com/Music/Search", data={"progCode": "RASFM210", "searchType": "2", "searchWord": word}, headers=H, timeout=20)
    h = clean(r.text)
    i = h.find("<tbody")
    print("== search", word, r.status_code, r.url, h[i:i + 1500])
r = requests.get("https://miniweb.imbc.com/Music/View?seqID=7252&progCode=RASFM210&page=1", headers=H, timeout=20)
h = clean(r.text)
i = h.find("<tbody")
print("== view", h[i:i + 1500])
