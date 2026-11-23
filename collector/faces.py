"""여러 멤버가 함께 나온 공식 사진 게시물에서 사진마다 누가 있는지 얼굴로 가리기 → data/photo_faces.json

- 글(캡션)에 적힌 멤버들 중에서만 고름 (후보가 적어서 잘 맞음)
- 기준 얼굴: site/img/members/ 의 멤버별 사진(포카·컨셉 사진 등, 파일 이름 끝 '_한글이름')
- 결과: {"게시물주소#사진번호": ["MOON", ...]} — 얼굴을 못 찾았거나 확신이 없으면 빈 목록
- 사진 모음에서 멤버를 고르면 이 결과에 있는 멤버만 그 사진에 나옴 (collect.py photo_feed)
OpenCV YuNet(얼굴 찾기)·SFace(얼굴 비교) 모델은 실행 때 받음 (MODEL_DIR)
"""
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

import numpy as np
import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "data" / "photo_faces.json"
MODEL_DIR = Path(os.environ.get("FACE_MODELS", "/tmp/fr"))
YUNET = "face_detection_yunet_2023mar.onnx"
SFACE = "face_recognition_sface_2021dec.onnx"
MATCH = 0.30   # 코사인 유사도 기준 (SFace 권장 0.363보다 조금 느슨 — 후보가 글에 적힌 멤버뿐이라)
LIMIT = 80     # 한 번에 처리할 사진 수
UA = {"User-Agent": "Mozilla/5.0"}


def key(p):
    return f"{p['url']}#{p.get('n', 0)}"


def load():
    return json.loads(PATH.read_text()) if PATH.exists() else {}


def todo(photos, cache):
    return [p for p in photos if len(p.get("members") or []) >= 2 and p.get("url") and key(p) not in cache]


def _models():
    import cv2
    det = cv2.FaceDetectorYN.create(str(MODEL_DIR / YUNET), "", (320, 320), 0.6, 0.3, 5000)
    rec = cv2.FaceRecognizerSF.create(str(MODEL_DIR / SFACE), "")
    return det, rec


def _faces(img, det, rec, min_size=32):
    import cv2
    h, w = img.shape[:2]
    s = min(1.0, 1600 / max(h, w))
    if s < 1:
        img = cv2.resize(img, (int(w * s), int(h * s)))
        h, w = img.shape[:2]
    det.setInputSize((w, h))
    _, faces = det.detect(img)
    out = []
    for f in faces if faces is not None else []:
        if min(f[2], f[3]) < min_size:
            continue
        al = rec.alignCrop(img, f)
        out.append((rec.feature(al).flatten(), f))
    return out


def _decode(data):
    import cv2
    arr = np.frombuffer(data, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:  # webp 등
        from PIL import Image
        import io
        img = cv2.cvtColor(np.array(Image.open(io.BytesIO(data)).convert("RGB")), cv2.COLOR_RGB2BGR)
    return img


def refs(det, rec):
    """멤버 이름 → 기준 얼굴 특징 목록"""
    mem = yaml.safe_load((ROOT / "members.yml").read_text())
    mem = mem.get("members", mem) if isinstance(mem, dict) else mem
    by = {unicodedata.normalize("NFC", m["ko"]): m["name"] for m in mem if m.get("ko")}
    by.update({m["name"].upper(): m["name"] for m in mem})
    out = {}
    # 멤버 사진(파일 끝 '_한글이름')·포카(파일 끝 '_MOON' 같은 영문 이름)
    for d in (ROOT / "site" / "img" / "members", ROOT / "site" / "img" / "photocards"):
        for f in sorted(d.iterdir()):
            m = re.search(r"_([^_]+)\.(webp|jpe?g|png)$", unicodedata.normalize("NFC", f.name))
            name = by.get(m[1]) or by.get(m[1].upper()) if m else None
            if not name:
                continue
            try:
                fs = _faces(_decode(f.read_bytes()), det, rec, min_size=24)
            except Exception:  # noqa: BLE001
                continue
            if len(fs) == 1:
                out.setdefault(name, []).append(fs[0][0])
    return out


def _sim(a, b):
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


def assign(feats, cands, R):
    """얼굴들 × 후보 멤버 → 높은 짝부터 한 명씩 (같은 멤버 두 번 X)"""
    pairs = sorted(((max(_sim(f, r) for r in R[m]), i, m) for i, f in enumerate(feats) for m in cands if R.get(m)), reverse=True)
    used_f, used_m, got = set(), set(), []
    for s, i, m in pairs:
        if s < MATCH or i in used_f or m in used_m:
            continue
        used_f.add(i); used_m.add(m); got.append((m, round(s, 3)))
    return got


def run(photos, verbose=False):
    cache = load()
    jobs = todo(photos, cache)[:LIMIT]
    if not jobs:
        print("[얼굴] 새로 볼 사진 없음")
        return cache
    det, rec = _models()
    R = refs(det, rec)
    print(f"[얼굴] 기준 얼굴: {', '.join(f'{k} {len(v)}' for k, v in sorted(R.items()))}")
    for p in jobs:
        try:
            r = requests.get(p["src"], headers=UA, timeout=30)
            r.raise_for_status()
            fs = _faces(_decode(r.content), det, rec)
        except Exception as e:  # noqa: BLE001 — 주소 만료 등은 다음에 다시
            print(f"[얼굴] 실패 {key(p)}: {type(e).__name__}")
            continue
        got = assign([f for f, _ in fs], p["members"], R)
        cache[key(p)] = [m for m, _ in got]
        if verbose:
            print(f"[얼굴] {key(p)} 얼굴 {len(fs)} · 후보 {p['members']} → {got}")
    PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=0, sort_keys=True) + "\n")
    print(f"[얼굴] {len(jobs)}장 확인 · 남은 사진 {len(todo(photos, cache))}")
    return cache


if __name__ == "__main__":
    dash = json.loads((ROOT / "data" / "dashboard.json").read_text())
    run(dash.get("photos") or [], verbose="-v" in sys.argv)
