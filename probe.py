import re, json, requests
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
for ch in ["21", "22", "24", "25"]:
    try:
        r = requests.get(f"https://pprogramapi.kbs.co.kr/api/v1/external/program?page=1&page_size=100&rtype=json&program_ch_code={ch}&end_yn=n&station_code=00", headers=H, timeout=20)
        j = r.json()
        items = j.get("data") or j.get("items") or j
        print("== KBS ch", ch, str(j)[:200] if not isinstance(items, list) else "")
        if isinstance(items, list):
            for it in items:
                print("  ", it.get("program_code"), it.get("program_title"), it.get("program_url") or it.get("homepage_url"))
    except Exception as e:
        print("ERR", ch, e)
r = requests.get("https://www.cbs.co.kr/radio/musicfm", headers=H, timeout=20)
print("== CBS", r.status_code, set(re.findall(r"(cbs_P\d+)[^<]{0,80}?[\"'>]\s*([^<]{2,30})<", r.text)))
for u in ["https://programs.sbs.co.kr/radio/cultwoshow/main", "https://programs.sbs.co.kr/radio/ycfm/main", "https://programs.sbs.co.kr/radio/king/main"]:
    r = requests.get(u, headers=H, timeout=20)
    print("== SBS", u, r.status_code, len(r.text), r.url)
    for a in re.findall(r'href="([^"]+)"[^>]*>([^<]*선곡[^<]*)<', r.text): print("  A", a)
    print("  API", set(re.findall(r"https?://[a-z.]*api[^\"' ]{0,120}", r.text)))
