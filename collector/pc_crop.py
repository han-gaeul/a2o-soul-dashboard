"""포카 리스트 템플릿(@soultemplates) → 카드 한 장씩 잘라 site/img/photocards/버전_라벨_멤버.webp 로 저장.

    python3 collector/pc_crop.py 템플릿폴더

- 멤버 템플릿(파일 이름에 멤버 이름): 카드 아래 글자(OCR)로 라벨, 줄 위치로 버전(앨범/예판 특전/팬사인·영통/방송/럭키드로우)
- 단체 템플릿(CARABINER·BROADCAST·OLIVE YOUNG): 카드 아래 멤버 이름 순서(알파벳)로 매칭
- 아직 공개 안 된 '?' 카드는 건너뜀. 같은 카드가 겹치면 먼저 나온 것만.
필요: tesseract, pytesseract, scipy, Pillow
"""
import re
import sys
import unicodedata
from pathlib import Path

import numpy as np
import pytesseract
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "site" / "img" / "photocards"
MEMBERS = ["ALURE", "AYDEN", "GAKU", "HANSUNG", "JUNE", "LUCIEN", "MOON",
           "SEE-ONE", "SEOHA", "SONO", "SORA", "TAI", "TEO", "ZAI", "ZET"]  # 단체 템플릿 순서
STORES = {"APPLEMUSIC": "Apple Music", "APPLE MUSIC": "Apple Music", "MUSIC PLANT": "Music Plant", "MAKESTAR": "Makestar",
          "WITHMUU": "Withmuu", "JUMPUP": "Jumpup", "NEMOZ": "Nemoz", "JINGDONG": "Jingdong", "MUSINA": "Musina",
          "MNET": "Mnet", "MUSICART": "Musicart", "OLIVE YOUNG": "Olive Young"}
KINDS = {"PHOTOBOOK": "Photobook", "PB": "Photobook", "CARABINER": "Carabiner", "FANSIGN": "Fansign",
         "VIDEOCALL": "Videocall", "VC": "Videocall", "FS": "Fansign"}
GROUP = {"CARABINER": ("앨범", "CARABINER Ver."), "BROADCAST-SUPERSTAR": ("방송", "SUPERSTAR"),
         "BROADCAST-DITD": ("방송", "Dancing in the Dark"), "OLIVEYOUNG": ("럭키드로우", "Olive Young")}


def cards(img):
    a = np.asarray(img).astype(int)
    mask = np.abs(a - a[620, 10]).sum(2) > 30
    lab, _ = ndimage.label(mask)
    out = []
    for sl in ndimage.find_objects(lab):
        y, x = sl[0].start, sl[1].start
        h, w = sl[0].stop - y, sl[1].stop - x
        if 100 < w < 260 and 1.3 < h / w < 1.7:
            hidden = a[y + 10:y + h - 10, x + 10:x + w - 10].mean() < 60  # 검은 '?' 카드
            out.append((y, x, w, h, hidden))
    rows = sorted({c[0] // 40 for c in out})
    return sorted(out, key=lambda c: (c[0] // 40, c[1])), rows


def ocr(img, box):
    x0, y0, x1, y1 = box
    t = pytesseract.image_to_string(img.crop(box).resize(((x1 - x0) * 2, (y1 - y0) * 2)), config="--psm 6")
    return re.sub(r"\s+", " ", t).strip().upper()


def album_label(t):
    for v in ("CONSTELLATION", "CARABINER", "SOUL"):
        if v in t:
            return f"{v} Ver."
    return None


def store_label(t):
    t = t.replace("|", "").strip()
    store = next((v for k, v in sorted(STORES.items(), key=lambda kv: -len(kv[0])) if k in t.replace(" ", "") or k in t), None)
    if not store:
        return None
    m = re.search(r"-\s*([AB])\b", t)
    kinds = [v for k, v in KINDS.items() if re.search(rf"\b{k}\b", t)]
    kinds = list(dict.fromkeys(kinds))
    return " ".join([store] + ([m.group(1)] if m else [])) + (f" ({'·'.join(kinds)})" if kinds else "")


def save(img, c, version, label, member, seen):
    key = (version, label, member)
    if key in seen:
        return
    seen.add(key)
    y, x, w, h, _ = c
    name = f"{version}_{label}_{member}.webp".replace("/", "·")
    img.crop((x + 1, y + 1, x + w - 1, y + h - 1)).save(OUT / name, "WEBP", quality=92, method=6)
    print(" ", name)


def main(src):
    OUT.mkdir(parents=True, exist_ok=True)
    seen = set()
    files = sorted(Path(src).iterdir(), key=lambda f: f.name)
    # 단체 템플릿 먼저 (멤버 템플릿에서 '?'인 카드도 채워져 있음)
    for f in files:
        stem = unicodedata.normalize("NFC", f.stem).upper()
        g = next((k for k in GROUP if k in stem.replace("_", "-").replace(" ", "-")
                  or k.replace("-", "") in stem.replace("_", "").replace("-", "")), None)
        if not g:
            continue
        img = Image.open(f).convert("RGB")
        cs, _ = cards(img)
        print(f.name, len(cs))
        for c, member in zip(cs, MEMBERS):
            if not c[4]:
                save(img, c, *GROUP[g], member, seen)
    for f in files:
        stem = unicodedata.normalize("NFC", f.stem).upper()
        member = next((m for m in MEMBERS if stem.endswith(m) or stem.endswith(m.replace("-", ""))), None)
        if not member:
            continue
        img = Image.open(f).convert("RGB")
        cs, rows = cards(img)
        print(f.name, len(cs))
        for c in cs:
            if c[4]:
                continue
            y, x, w, h, _ = c
            t = ocr(img, (x - 25, y + h + 2, x + w + 25, y + h + 52))
            row = rows.index(y // 40)
            if row == 0:
                version, label = "앨범", album_label(t)
            elif "SUPERSTAR" in t:
                version, label = "방송", "SUPERSTAR"
            elif "DANCING" in t:
                version, label = "방송", "Dancing in the Dark"
            elif "OLIVE" in t or (row == len(rows) - 1 and "APPLE" in t):
                version, label = "럭키드로우", store_label(t)
            elif re.search(r"FANSIGN|VIDEOCALL|VC/FS", t):
                version, label = "팬사인·영통", store_label(t)
            else:
                version, label = "예판 특전", store_label(t)
            if not label:
                print("  ?? 라벨 못 읽음:", f.name, (x, y), t)
                continue
            save(img, c, version, label, member, seen)


if __name__ == "__main__":
    main(sys.argv[1])
