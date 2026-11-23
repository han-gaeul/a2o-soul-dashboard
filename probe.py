import re, requests
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
for codes, ps in [("R2018-0187", 50), ("R2018-0187", 200), ("R2026-0019,R2026-0020", 50), ("R2026-0019", 50)]:
    r = requests.get("https://kong2017.kbs.co.kr/api/mobile/select_song_list", headers=H, timeout=20,
                     params={"program_code": codes, "rtype": "json", "request_date": "20261122", "page": 1, "page_size": ps})
    print("== KBS", codes, ps, r.status_code, r.text[:300])
h = requests.get("https://www.cbs.co.kr/program/playlist/cbs_P000221", params={"date": "20261122"}, headers=H, timeout=20).text
i = h.find("언제나 그대 내곁에")
print("== CBS", h[i - 1500:i + 400])
