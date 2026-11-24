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
    bright = lambda c: min(c) > 160 and max(c) - min(c) < 30  # 흰·회색 종이 (파란 배경 제외)

    def longest(flags, gap):
        """True가 가장 길게 이어진 구간 (gap 이하 끊김은 이어진 걸로)"""
        best, s0, last = (0, 0), None, None
        for i, ok in enumerate(flags + [False] * (gap + 1)):
            if ok:
                if s0 is None or i - last > gap:
                    s0 = i
                last = i
                if last - s0 > best[1] - best[0]:
                    best = (s0, last + 1)
        return best

    H = int(h * 0.6)
    y0, y1 = longest([sum(1 for x in range(0, w, 2) if bright(px[x, y])) > w / 12 for y in range(H)], h // 25)
    x0, x1 = longest([sum(1 for y in range(y0, y1, 2) if bright(px[x, y])) > (y1 - y0) / 12 for x in range(w)], w // 25)
    xs = [x0, x1 - 1]
    p = 6
    box = (min(xs) + p, y0 + p, max(xs) - p, y1 - p)
    im.crop(box).save(out / f"qq_{name}.webp", quality=90)
    print(name, im.size, box)
