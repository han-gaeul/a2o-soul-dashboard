import io
import urllib.request
from pathlib import Path

from PIL import Image

out = Path("site/img/drawings")
out.mkdir(parents=True, exist_ok=True)
IDS = {"gaku": "HWrmMpYa4AA682D", "june": "HWrmM7ka0AAHq9I", "hansung": "HWrmNNEbkAATK7F", "seeone": "HWrmVFkbAAAuAwW",
       "alure": "HWrmVZhbcAEjynV", "tai": "HWrmVsBboAA-Q4n", "sono": "HWrmWARbMAAgtso", "zai": "HWrmittbwAEXoPd",
       "ayden": "HWrmjAPbcAAuOn7", "zet": "HWrmjR1aoAAvJJN", "lucien": "HWrrBg8bEAAQNWO"}
for name, mid in IDS.items():
    req = urllib.request.Request(f"https://pbs.twimg.com/media/{mid}?format=png&name=4096x4096", headers={"User-Agent": "Mozilla/5.0"})
    im = Image.open(io.BytesIO(urllib.request.urlopen(req, timeout=30).read())).convert("RGB")
    w, h = im.size
    px = im.load()
    # 흰 그림 칸: 행마다 밝은 픽셀이 폭의 절반 넘는 줄 중 가장 긴 연속 구간
    rows = [sum(1 for x in range(0, w, 2) if min(px[x, y]) > 215) > w / 4 for y in range(int(h * 0.6))]
    best, cur, start = (0, 0), 0, 0
    for y, ok in enumerate(rows + [False]):
        if ok:
            if cur == 0:
                start = y
            cur += 1
        else:
            if cur > best[1] - best[0]:
                best = (start, start + cur)
            cur = 0
    y0, y1 = best
    xs = [x for x in range(w) if min(px[x, (y0 + y1) // 2]) > 215]
    p = 6
    box = (min(xs) + p, y0 + p, max(xs) - p, y1 - p)
    im.crop(box).save(out / f"qq_{name}.webp", quality=90)
    print(name, im.size, box)
