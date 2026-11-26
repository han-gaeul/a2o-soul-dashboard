"""일반 계정이 올린 포카 사진(X 검색 후보) → 카드 찾아 자르기 → 사이트에 없는 카드만 추가.

    pc_watch.py 가 6시간마다 X 검색으로 모은 글을 넘겨줌 → process(posts, state) → 추가한 카드 목록

- 카드 찾기: 사진에서 포카 비율(가로:세로 ≈ 1:1.55) 네모를 찾아 원근 보정해서 똑바로 폄 (슬리브·탑로더 안 카드도)
- 멤버: 얼굴 인식(faces.py 기준 얼굴) — 얼굴이 하나이고 확실할 때만 (뒷면·여러 명·애매하면 건너뜀)
- 버전·판매처: 글 내용에서 (럭드·특전·팬싸영통 + 판매처 이름이 하나로 정해질 때만)
- 이미 있는 카드(같은 멤버, 사진 지문 비교)는 건너뜀
- 글에 '크롭·재업·무단 사용 금지' 같은 문구가 있으면 그 글은 안 씀 (같은 카드는 다른 사람 사진에서 찾음)
결과는 photocards 워크플로가 PR로 올림 → 확인하고 머지. 필요: opencv-python-headless, numpy, Pillow, 얼굴 모델(MODEL_DIR)
"""
import io
import json
import re
from pathlib import Path

import numpy as np
import requests
from PIL import Image

import faces
import pc_crop

LOG = Path(__file__).resolve().parent / "pc_auto.json"
W, H = 272, 420  # 저장 크기 (포카 55×85mm)

BAN = re.compile(r"do\s*n['o]?t\s*(?:crop|repost|edit|use|take|re-?upload)|don'?t\s*(?:crop|repost|edit|use|take)|no\s*(?:crop|repost|re-?upload)s?\b"
                 r"|without\s*permission|\bdnr\b|\bdnc\b|크롭\s*금지|자르기\s*금지|무단|퍼가지|퍼가기\s*금지|2차\s*가공|가공\s*금지|재업\s*금지|재업로드\s*금지"
                 r"|도용\s*금지|사용\s*금지|転載|無断|加工禁止|禁止转载|禁止二改|勿二改|勿转", re.I)
STORE_WORDS = [  # (정규식, 사이트 라벨) — 긴 이름 먼저
    (r"올리브\s?영|올영|olive\s?young|\boy\b", "Olive Young"), (r"뮤직\s?플랜트|뮤플|music\s?plant", "Music Plant"),
    (r"메이크스타|멬스|메스|makestar", "Makestar"), (r"위드뮤|위뮤|withmuu", "Withmuu"), (r"뮤직\s?아트|뮤아|musicart", "Musicart"),
    (r"애플\s?뮤직|애뮤|apple\s?music", "Apple Music"), (r"점프업|점업|jump\s?up", "Jumpup"), (r"엠넷|엠플|앰플|mnet", "Mnet"),
    (r"네모즈|nemoz", "Nemoz"), (r"사운드\s?웨이브|사웨|soundwave", "Soundwave"), (r"케타포|ktown4u", "Ktown4u"),
    (r"징동|jingdong|京东", "Jingdong"), (r"무신사|musinsa", "Musinsa"), (r"카카오\s?톡|kakao\s?talk", "KakaoTalk"),
]
KIND_WORDS = [  # (정규식, 사이트 버전) — 앞에 있는 게 우선
    (r"럭키\s?드로우|럭드|lucky\s?draw|ラキドロ|\bld\b", "럭키드로우"),
    (r"팬\s?사인|팬싸|영통|영상\s?통화|fan\s?sign|video\s?call|\bvc\b|\bfs\b", "팬사인·영통"),
    (r"특전|미공포|pob|pre-?order|特典", "예판 특전"),
]


def banned(caption):
    return bool(BAN.search(caption or ""))


def label_from(caption):
    """글 내용 → (버전, 판매처) — 판매처가 하나로 정해질 때만. 못 정하면 None"""
    c = caption or ""
    stores = {lab for pat, lab in STORE_WORDS if re.search(pat, c, re.I)}
    if len(stores) != 1:
        return None
    kind = next((v for pat, v in KIND_WORDS if re.search(pat, c, re.I)), None)
    if not kind:
        return None
    return kind, stores.pop()


def _order(pts):
    s, d = pts.sum(1), np.diff(pts, axis=1).ravel()
    return np.array([pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]], dtype="float32")


def find_cards(bgr):
    """사진 → 카드 네모들(원근 보정해서 W×H로 편 이미지, BGR)"""
    import cv2
    h0, w0 = bgr.shape[:2]
    s = min(1.0, 1600 / max(h0, w0))
    img = cv2.resize(bgr, (int(w0 * s), int(h0 * s))) if s < 1 else bgr
    h, w = img.shape[:2]
    gray = cv2.GaussianBlur(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    quads = []
    maps = [cv2.dilate(cv2.Canny(gray, lo, hi), np.ones((3, 3), np.uint8)) for lo, hi in ((10, 40), (30, 100), (60, 180))]
    maps.append(cv2.morphologyEx(cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 5),
                                 cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8)))
    for edges in maps:
        cnts, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        for c in cnts:
            area = cv2.contourArea(c)
            if area < 0.015 * w * h or area > 0.9 * w * h:
                continue
            peri = cv2.arcLength(c, True)
            ap = next((a for e in (0.02, 0.03, 0.05) for a in [cv2.approxPolyDP(c, e * peri, True)] if len(a) == 4), None)
            if ap is None or not cv2.isContourConvex(ap):
                continue
            q = _order(ap.reshape(4, 2).astype("float32"))
            a, b = np.linalg.norm(q[0] - q[1]), np.linalg.norm(q[1] - q[2])
            short, long_ = min(a, b), max(a, b)
            if short < 60 or not 1.38 <= long_ / short <= 1.72:
                continue
            quads.append((area, q))
    # 겹치는 네모(카드 테두리·슬리브)는 가장 작은 것(안쪽 카드)만
    quads.sort(key=lambda t: t[0])
    keep = []
    for area, q in quads:
        cx, cy = q.mean(0)
        if any(cv2.pointPolygonTest(k.reshape(-1, 1, 2), (float(cx), float(cy)), False) >= 0 for _, k in keep):
            continue
        keep.append((area, q))
    out = []
    for _, q in keep:
        a, b = np.linalg.norm(q[0] - q[1]), np.linalg.norm(q[1] - q[2])
        if a > b:  # 가로로 누운 카드 → 세로로
            q = np.roll(q, -1, axis=0)
        M = cv2.getPerspectiveTransform(q / s, np.array([[0, 0], [W, 0], [W, H], [0, H]], dtype="float32"))
        out.append(cv2.warpPerspective(bgr, M, (W, H)))
    return out


PRICE = re.compile(r"\d+\s?\.-|฿|บาท|\bphp\b|₱|\brm\s?\d|\bidr\b|\brp\s?\d|(?<![\d.])\d\s?[.,]\s?\d(?![\d.])|\d+\s?(?:만|천)\s?원?|\d{4,}\s?원|₩|\$\s?\d|\d\s?(?:usd|won|k)\b", re.I)


def ok_card(card):
    """흐린 카드(템플릿의 '?'·모자이크), 얼굴만 크게 잘린 것 빼기"""
    import cv2
    return cv2.Laplacian(cv2.cvtColor(card, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var() >= 80


def who(card, det, rec, R):
    """카드 한 장 → 멤버 (얼굴 하나, 카드 안에서 알맞은 크기, 1등 0.6 이상이고 2등과 0.08 넘게 차이 날 때만)"""
    fs = faces._faces(card, det, rec, min_size=24)
    if len(fs) != 1:
        return None, 0
    f, box = fs[0]
    if not 0.25 <= box[2] / card.shape[1] <= 0.8:  # 얼굴이 너무 작거나(여러 장·배경) 너무 큼(얼굴만 잘림)
        return None, 0
    sc = sorted(((max(faces._sim(f, r) for r in R[m]), m) for m in R if R[m]), reverse=True)
    if not sc or sc[0][0] < 0.6 or (len(sc) > 1 and sc[0][0] - sc[1][0] < 0.08):
        return None, sc[0][0] if sc else 0
    return sc[0][1], sc[0][0]


_ORB = None


def _feat(pil):
    """ORB 특징점 — 사진 찍은 카드 vs 템플릿 카드처럼 색감·각도가 달라도 같은 카드면 많이 맞음"""
    import cv2
    global _ORB
    _ORB = _ORB or cv2.ORB_create(1500)
    g = cv2.equalizeHist(cv2.cvtColor(np.array(pil.convert("RGB").resize((W, H))), cv2.COLOR_RGB2GRAY))
    return _ORB.detectAndCompute(g, None)


def _inliers(a, b):
    import cv2
    (ka, da), (kb, db) = a, b
    if da is None or db is None:
        return 0
    good = [m[0] for m in cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(da, db, k=2) if len(m) == 2 and m[0].distance < 0.75 * m[1].distance]
    if len(good) < 8:
        return len(good)
    _, mask = cv2.findHomography(np.float32([ka[g.queryIdx].pt for g in good]), np.float32([kb[g.trainIdx].pt for g in good]), cv2.RANSAC, 8)
    return int(mask.sum()) if mask is not None else 0


def _dupe(pil, fp, have):
    """같은 멤버의 이미 있는 카드와 같은 카드인지 — 사진 지문이 아주 가깝거나, 가까운 후보 몇 장 중 특징점이 50개 넘게 맞으면 같은 카드
    (같은 카드 100~170개 / 다른 카드 25개 이하로 확인함)"""
    if any(int((fp != f2).sum()) < pc_crop.SAME for f2, _ in have):
        return True
    fe = _feat(pil)
    near = sorted(have, key=lambda h: int((fp != h[0]).sum()))[:5]
    return any(_inliers(fe, h[1]) >= 50 for h in near)


def process(posts, state):
    """글 목록 → 새 카드 저장. [(파일 이름, 글 주소, 작성자)]"""
    import cv2
    done = set(state.setdefault("auto_seen", []))
    todo = [p for p in posts if p.get("images") and p["tweet_id"] not in done]
    if not todo:
        return []
    det, rec = faces._models()
    R = faces.refs(det, rec)
    by_member = {}
    for f in pc_crop.OUT.glob("*.webp"):
        m = f.stem.split("_")[-1]
        try:
            im = Image.open(f)
            by_member.setdefault(m, []).append((pc_crop.dhash(im), _feat(im)))
        except Exception:  # noqa: BLE001
            pass
    log = json.loads(LOG.read_text()) if LOG.exists() else []
    added = []
    for p in todo:
        done.add(p["tweet_id"])
        cap = p.get("caption") or ""
        if banned(cap):
            print(f"[포카 자동] 금지 문구 — 건너뜀 {p['permalink']}")
            continue
        if PRICE.search(cap):  # 가격이 적힌 양도 글은 사진에도 가격을 써 둔 경우가 많아서
            print(f"[포카 자동] 가격 적힌 글 — 건너뜀 {p['permalink']}")
            continue
        lab = label_from(cap)
        for url in p["images"][:4]:
            try:
                raw = requests.get(url + "?name=orig", timeout=30).content
                bgr = faces._decode(raw)
            except Exception as e:  # noqa: BLE001
                print(f"[포카 자동] 사진 실패 {url}: {type(e).__name__}")
                continue
            for card in find_cards(bgr):
                if not ok_card(card):
                    continue
                member, score = who(card, det, rec, R)
                if not member:
                    continue
                pil = Image.fromarray(cv2.cvtColor(card, cv2.COLOR_BGR2RGB))
                fp = pc_crop.dhash(pil)
                have = by_member.setdefault(member, [])
                if _dupe(pil, fp, have):
                    continue  # 이미 있는 카드
                if not lab:
                    print(f"[포카 자동] 새 카드 같지만 판매처·종류를 못 정함 ({member}) {p['permalink']}")
                    continue
                version, store = lab
                name = f"{version}_{store}_{member}.webp"
                n = 2
                while (pc_crop.OUT / name).exists():  # 같은 판매처의 다른 카드(다른 회차) → 2, 3…
                    name = f"{version}_{store} {n}_{member}.webp"
                    n += 1
                pil.save(pc_crop.OUT / name, "WEBP", quality=90, method=6)
                have.append((fp, _feat(pil)))
                added.append((name, p["permalink"], p.get("author", "")))
                log.append({"file": name, "post": p["permalink"], "img": url, "credit": "@" + p.get("author", ""), "face": round(score, 3)})
                print(f"[포카 자동] 추가 {name} ← {p['permalink']} (얼굴 {score:.2f})")
    state["auto_seen"] = sorted(done, key=int)[-3000:]
    if added:
        LOG.write_text(json.dumps(log, ensure_ascii=False, indent=1) + "\n")
    return added
