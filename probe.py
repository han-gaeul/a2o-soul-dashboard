import sys, re, json
sys.path.insert(0, "collector")
import radio
from datetime import date, timedelta
radio.ARTIST = re.compile(r"아이유|\bIU\b|김현식|BOYS LIKE GIRLS|AESPA|에스파|A2O", re.I)
days = [date(2026, 11, 21), date(2026, 11, 22)]
for name, fn in (("KBS", lambda: radio.kbs(days)), ("SBS", lambda: radio.sbs(days)), ("CBS", lambda: radio.cbs(days))):
    try:
        got = fn(); print("==", name, len(got)); [print("  ", x) for x in got[:4]]
    except Exception as e:
        import traceback; traceback.print_exc()
radio.MBC_PROGS = radio.MBC_PROGS
got = radio.mbc(); print("== MBC", len(got), sorted(set(x["program"] for x in got))); [print("  ", x) for x in got[:4]]
radio.ARTIST = re.compile(r"A2O\s?SOUL|에이투오", re.I)
print("== REAL")
for name, fn in (("KBS", lambda: radio.kbs([date(2026,11,9)+timedelta(i) for i in range(15)])), ("SBS", lambda: radio.sbs([date(2026,11,9)+timedelta(i) for i in range(15)])), ("MBC", radio.mbc), ("CBS", lambda: radio.cbs([date(2026,11,9)+timedelta(i) for i in range(15)]))):
    got = fn(); print("==", name, len(got)); [print("  ", x) for x in got[:10]]
