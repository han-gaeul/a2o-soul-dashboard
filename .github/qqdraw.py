import io
import urllib.request
from pathlib import Path

from PIL import Image

out = Path("site/img/drawings")
out.mkdir(parents=True, exist_ok=True)
for name, mid in {"moon": "HWrkDIZaQAAuVco", "sora": "HWrkDcwaAAALyxn", "seoha": "HWrkDvoa4AAr8Zt", "teo": "HWrkEB3aEAAxgdE"}.items():
    req = urllib.request.Request(f"https://pbs.twimg.com/media/{mid}?format=png&name=4096x4096", headers={"User-Agent": "Mozilla/5.0"})
    im = Image.open(io.BytesIO(urllib.request.urlopen(req, timeout=30).read())).convert("RGB")
    w, h = im.size
    px = im.load()
    xs, ys = [], []
    for y in range(h // 2):
        for x in range(w):
            r, g, b = px[x, y]
            if r > 225 and g > 225 and b > 225:
                xs.append(x)
                ys.append(y)
    p = 6
    box = (min(xs) + p, min(ys) + p, max(xs) - p, max(ys) - p)
    im.crop(box).save(out / f"qq_{name}.webp", quality=90)
    print(name, im.size, box)
