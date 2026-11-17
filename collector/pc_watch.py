"""@soultemplates 새 포카 템플릿 → 멤버별 카드로 잘라 site/img/photocards/ 갱신 (photocards 워크플로가 PR로 올림).

    python3 collector/pc_watch.py            # 새 글만 (처음 실행은 기준점만 기록)
    python3 collector/pc_watch.py --backfill  # 최근 글 최대 100개 다시 훑기

템플릿 이름은 사진 속 검은 띠 글자(OCR)로 판별:
  'MOON [SUPERSTAR] PHOTOCARD TEMPLATE'            → SUPERSTAR_MOON (멤버 템플릿)
  'A2O SOUL [SUPERSTAR] CARABINER VER. PHOTOCARD'   → SUPERSTAR_CARABINER (단체)
  'A2O SOUL [DANCING IN THE DARK] BROADCAST ...'    → SUPERSTAR_BROADCAST-DITD
  'A2O SOUL [SUPERSTAR] OLIVE YOUNG LUCKY DRAW'     → SUPERSTAR_OLIVEYOUNG
A2O SOUL 템플릿이 아니면(다른 그룹) 건너뜀. 필요: X_BEARER_TOKEN, tesseract, pytesseract, scipy, Pillow
"""
import io
import json
import re
import sys
import tempfile
from pathlib import Path

import requests
from PIL import Image, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pc_crop  # noqa: E402
import xposts  # noqa: E402

ACCOUNT = "soultemplates"
STATE = Path(__file__).resolve().parent / "pc_state.json"
REPORT = Path(__file__).resolve().parent.parent / "pc_report.md"


def banner_text(img):
    """템플릿 위쪽 검은 띠의 흰 글자."""
    g = img.convert("L")
    w, _ = g.size
    band = g.crop((int(w * .15), int(w * .215), int(w * .85), int(w * .30)))
    band = ImageOps.invert(band).point(lambda x: 0 if x < 110 else 255)
    band = band.resize((band.width * 2, band.height * 2))
    return re.sub(r"\s+", " ", pc_crop.pytesseract.image_to_string(band, config="--psm 7")).strip().upper()


def template_name(img):
    t = banner_text(img)
    m = re.search(r"\[([^\]]+)\]", t)
    if not m or "PHOTOCARD" not in t and "LUCKY" not in t:
        return None, t
    album = re.sub(r"[^A-Z0-9]+", "", m.group(1).split()[0] if "DANCING" in m.group(1) else m.group(1)) or "ALBUM"
    head = t[:m.start()].strip()
    member = next((x for x in pc_crop.MEMBERS if re.fullmatch(re.escape(x).replace("\\-", "-?"), head.replace(" ", ""))), None)
    if member and "TEMPLATE" in t:
        return f"SUPERSTAR_{member}" if album == "SUPERSTAR" else f"{album}_{member}", t
    if not re.search(r"A[2Z]0|A2O", head):  # 다른 그룹 템플릿
        return None, t
    if "CARABINER" in t:
        return "SUPERSTAR_CARABINER", t
    if "OLIVE" in t:
        return "SUPERSTAR_OLIVEYOUNG", t
    if "BROADCAST" in t:
        return ("SUPERSTAR_BROADCAST-DITD" if "DANCING" in m.group(1) else "SUPERSTAR_BROADCAST-SUPERSTAR"), t
    return None, t


def main(backfill=False):
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    if not xposts.enabled():
        print("[포카] X 토큰 없음 — 건너뜀")
        return
    uid = state.get("uid") or xposts.user_id(ACCOUNT)
    state["uid"] = uid
    since = None if backfill else state.get("since_id")
    posts = xposts.fetch_posts(uid, ACCOUNT, since_id=since, first_limit=100 if backfill else 5,
                               exclude="retweets")  # 템플릿을 타래(자기 답글)로 올리기도 해서 답글 포함
    if posts:
        state["since_id"] = max(posts, key=lambda p: int(p["id"].split(":")[-1]))["id"].split(":")[-1]
    if not since and not backfill:
        STATE.write_text(json.dumps(state, indent=1))
        print(f"[포카] 처음 실행 — 기준점만 기록 ({len(posts)}개 글)")
        return
    found = []
    with tempfile.TemporaryDirectory() as tmp:
        for p in reversed(posts):  # 오래된 글부터 → 같은 템플릿이면 최신 것이 덮어씀
            for i, url in enumerate(p.get("images") or []):
                try:
                    img = Image.open(io.BytesIO(requests.get(url + "?name=orig", timeout=30).content)).convert("RGB")
                except Exception as e:  # noqa: BLE001
                    print(f"[포카] 사진 실패 {url}: {e}")
                    continue
                name, text = template_name(img)
                print(f"[포카] {p['permalink']} #{i + 1}: {text[:60]!r} → {name}")
                if name:
                    img.save(Path(tmp) / f"{name}.png")
                    found.append((name, p["permalink"]))
        if found:
            pc_crop.main(tmp)
    STATE.write_text(json.dumps(state, indent=1))
    if found:
        lines = ["@soultemplates 새 포카 템플릿을 멤버별로 잘랐어요. **Files changed**에서 잘린 카드와 라벨(파일 이름)을 확인하고 머지해 주세요.", "",
                 "| 템플릿 | 원본 글 |", "|---|---|"]
        lines += [f"| {n} | {u} |" for n, u in dict(found).items()]
        lines += ["", "출처 @soultemplates — 허락받음(원본 글 링크 표시 조건)"]
        REPORT.write_text("\n".join(lines) + "\n")
    print(f"[포카] 새 글 {len(posts)}개 · 템플릿 {len(found)}장")


if __name__ == "__main__":
    main(backfill="--backfill" in sys.argv)
