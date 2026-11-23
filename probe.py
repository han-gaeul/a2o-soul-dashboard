import sys, re
sys.path.insert(0, "collector")
import radio
from datetime import date, timedelta
radio.ARTIST = re.compile(r"아이유|\bIU\b|AESPA|에스파|검정치마", re.I)
got = radio.kbs([date(2026, 11, 21)]); print("== KBS test", len(got), sorted(set((x["date"], x["program"]) for x in got))[:10])
radio.ARTIST = re.compile(r"A2O\s?SOUL|에이투오\s?소울", re.I)
got = radio.kbs([date(2026, 11, 9) + timedelta(i) for i in range(15)]); print("== REAL KBS", len(got)); [print("  ", x) for x in got[:10]]
