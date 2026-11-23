import sys, re, json
sys.path.insert(0, "collector")
import kcharts
h = kcharts._get("https://music.bugs.co.kr/chart/track/realtime/total").text
i = h.find("<tbody")
print("== BUGS", re.sub(r"\s+", " ", h[i:i + 1500]))
for name, svc, fn in kcharts.CHARTS:
    got = fn(); print("==", name, len(got), list(got.items())[:3])
kcharts.run()
d = kcharts.load()
d["counts_at"] = ""
kcharts.save(d)
kcharts.counts(d, kcharts.songs()); kcharts.circle(d, kcharts.songs()); kcharts.save(d)
print("== SUMMARY", json.dumps(kcharts.summary(), ensure_ascii=False))
print("== SERIES", json.dumps(kcharts.chart_series(), ensure_ascii=False)[:1500])
