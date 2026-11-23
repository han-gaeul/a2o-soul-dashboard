import requests
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
j = requests.get("https://pprogramapi.kbs.co.kr/api/v1/external/program?page=1&page_size=100&rtype=json&program_ch_code=25&end_yn=n&station_code=00", headers=H).json()
print("== keys", type(j), list(j)[:10] if isinstance(j, dict) else len(j), str(j)[:300])
codes = "R2026-0019,R2026-0020,R2025-0082,R2024-0245,R2024-0203,R2024-0068,R2023-0192,R2020-0025,A2019-0002,R2007-0069,R2007-0074,R2014-0355,R2017-0175"
for c in [codes, ",".join(codes.split(",")[:5])]:
    r = requests.get("https://kong2017.kbs.co.kr/api/mobile/select_song_list", headers=H, params={"program_code": c, "rtype": "json", "request_date": "20261122", "page": 1, "page_size": 200})
    print("== n", len(c), r.status_code, len(r.json().get("items") or []), r.text[:200])
