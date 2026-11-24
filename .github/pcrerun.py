"""임시: @soultemplates 261124 멤버 템플릿 15장 다시 자르기 (새 카드만, 이름이 더 자세하면 바꿈)"""
import sys
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, "collector")
import pc_crop  # noqa: E402

IDS = {"ALURE": "HX2L_GhWUAAKpIF", "AYDEN": "HX2MAAkWcAIqcf6", "GAKU": "HX2MA-sX0AAp3I1", "HANSUNG": "HX2MCgVWAAARkKd",
       "JUNE": "HX2MFr1XgAAns32", "LUCIEN": "HX2MGMgWYAAKn77", "MOON": "HX2MGx3WEAAMhUJ", "SEE-ONE": "HX2MHOWXAAAvoqU",
       "SEOHA": "HX2MHqrW4AAECGF", "SONO": "HX2MIEbWgAE4TCK", "SORA": "HX2MIgYWoAEz-9X", "TAI": "HX2MI9sXYAA38cj",
       "TEO": "HX2MJatXsAAKB5I", "ZAI": "HX2MJ4iXcAApGt2", "ZET": "HX2MKYlXIAArGws"}
with tempfile.TemporaryDirectory() as tmp:
    for m, mid in IDS.items():
        req = urllib.request.Request(f"https://pbs.twimg.com/media/{mid}?format=png&name=4096x4096", headers={"User-Agent": "Mozilla/5.0"})
        Path(tmp, f"SUPERSTAR_{m}.png").write_bytes(urllib.request.urlopen(req, timeout=60).read())
    pc_crop.ONLY_NEW = True
    pc_crop.main(tmp)
