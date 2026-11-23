import sys, re, json, requests
sys.path.insert(0, "collector")
import radio
H = radio.UA
pj = requests.get("https://pprogramapi.kbs.co.kr/api/v1/external/program?page=1&page_size=100&rtype=json&program_ch_code=25&end_yn=n&station_code=00", headers=H).json()
print("== prog keys", list(pj["data"][0].keys()))
codes = [p.get("program_code") or (re.search(r"open_program/([A-Z]\d{4}-\d{4})", json.dumps(p)) or [None, None])[1] for p in pj["data"]]
print("== codes", codes)
for page in (1, 2, 5):
    j = requests.get("https://kong2017.kbs.co.kr/api/mobile/select_song_list", headers=H,
                     params={"program_code": ",".join(c for c in codes if c), "rtype": "json", "request_date": "20261121", "page": page, "page_size": 40}).json()
    it = j.get("items") or []
    print("== page", page, len(it), [x.get("timestamp") for x in it[:3]], [x.get("timestamp") for x in it[-2:]], [x.get("program_code") for x in it[:3]])
