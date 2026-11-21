"""공지 이미지 글자 읽기 (판매처 팬사인회 공지처럼 날짜·응모 기간이 이미지에만 있을 때).

tesseract(한국어)로 읽음. GitHub Actions에 없으면 필요할 때만 설치 (평소 수집 시간은 그대로).
"""
import io
import os
import shutil
import subprocess
import tempfile

import requests
from PIL import Image

_ready = None


def ready():
    """tesseract + 한국어 데이터가 있으면 True (Actions에선 처음 필요할 때 설치)."""
    global _ready
    if _ready is not None:
        return _ready
    def ok():
        if not shutil.which("tesseract"):
            return False
        langs = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True).stdout
        return "kor" in langs.split()
    if not ok() and os.environ.get("GITHUB_ACTIONS"):
        print("[OCR] tesseract 설치 중…")
        subprocess.run("sudo apt-get update -qq && sudo apt-get install -y -qq tesseract-ocr tesseract-ocr-kor > /dev/null",
                       shell=True, check=False)
    _ready = ok()
    if not _ready:
        print("[OCR] tesseract(한국어) 없음 — 이미지 글자 읽기 건너뜀")
    return _ready


def read_images(urls, limit=4):
    """이미지 주소들 → 읽은 글자 (줄 단위). 작은 이미지는 2배로 키워서 읽음 (날짜 숫자 오인식 줄이기)."""
    if not urls or not ready():
        return ""
    out = []
    for u in urls[:limit]:
        try:
            src = u if "?" in u else u + "?name=large"
            img = Image.open(io.BytesIO(requests.get(src, timeout=30).content)).convert("L")
            if img.width < 2000:
                img = img.resize((img.width * 2, img.height * 2), Image.LANCZOS)
            with tempfile.NamedTemporaryFile(suffix=".png") as f:
                img.save(f.name)
                txt = subprocess.run(["tesseract", f.name, "-", "-l", "kor+eng", "--psm", "6"],
                                     capture_output=True, text=True, timeout=120).stdout
            out += [ln.strip() for ln in txt.splitlines() if ln.strip()]
        except Exception as e:  # noqa: BLE001
            print(f"[OCR] {u} 실패: {type(e).__name__} {e}")
    return "\n".join(out)
