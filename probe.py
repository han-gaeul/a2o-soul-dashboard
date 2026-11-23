import sys, re
sys.path.insert(0, "collector")
import radio
from datetime import date, timedelta
radio.ARTIST = re.compile(r"아이유|\bIU\b|김현식|BOYS LIKE GIRLS|AESPA|에스파|검정치마", re.I)
days = [date(2026, 11, 21), date(2026, 11, 22)]
for name, fn in (("KBS", lambda: radio.kbs(days)), ("CBS", lambda: radio.cbs(days))):
    got = fn(); print("==", name, len(got)); [print("  ", x) for x in got[:4]]
radio.ARTIST = re.compile(r"A2O\s?SOUL|에이투오\s?소울", re.I)
d = [date(2026, 11, 9) + timedelta(i) for i in range(15)]
for name, fn in (("KBS", lambda: radio.kbs(d)), ("CBS", lambda: radio.cbs(d))):
    got = fn(); print("== REAL", name, len(got)); [print("  ", x) for x in got[:10]]
