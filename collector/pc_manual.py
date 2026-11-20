"""손으로 고른 포카 사진(X 글) → 카드 부분만 잘라 site/img/photocards/ 에 저장.

    python3 collector/pc_manual.py   # collector/pc_manual.json 의 항목 중 아직 파일이 없는 것만

pc_manual.json 항목: {"file": "버전_라벨_멤버.webp", "img": "https://pbs.twimg.com/media/<id>.jpg",
                      "crop": [x0, y0, x1, y1] (사진 크기 대비 비율 0~1), "post": 원본 글, "credit": "@작성자"}
작성자에게 허락받은 사진만 넣기. 컨테이너에선 pbs.twimg.com이 막혀 있어서 GitHub Actions에서 실행됨.
"""
import io
import json
import unicodedata
from pathlib import Path

import requests
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "site" / "img" / "photocards"
LIST = Path(__file__).resolve().parent / "pc_manual.json"


def main():
    have = {unicodedata.normalize("NFC", f.name) for f in OUT.iterdir()}
    for it in json.loads(LIST.read_text()):
        name = unicodedata.normalize("NFC", it["file"])
        if name in have and not it.get("replace"):
            continue
        raw = requests.get(it["img"] + "?name=orig", timeout=30).content
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        w, h = img.size
        x0, y0, x1, y1 = it["crop"]
        card = img.crop((round(x0 * w), round(y0 * h), round(x1 * w), round(y1 * h)))
        card = card.resize((272, round(272 * card.height / card.width)), Image.LANCZOS)
        card.save(OUT / name, "WEBP", quality=90, method=6)
        print("저장:", name, card.size, it.get("credit", ""))


if __name__ == "__main__":
    main()
