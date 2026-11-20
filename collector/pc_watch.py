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
# 템플릿 계정 말고도 X 검색으로 새 포카 글 후보를 모아 이슈로 알려 줌 (자동으로 올리진 않음 — 확인·허락 후 직접 추가)
SEARCH = ('(에이투오소울 OR 에투소 OR "A2O SOUL" OR A2OSOUL) '
          '(포카 OR 포토카드 OR 미공포 OR 특전 OR 럭드 OR 럭키드로우 '          # 한국어
          'OR photocard OR photocards OR pc OR pcs OR POB OR "lucky draw" '     # 영어 (+스페인어·포르투갈어·인니 등도 대부분 영어 표기)
          'OR トレカ OR フォトカード OR 特典 OR ラキドロ '                       # 일본어
          'OR 小卡 OR 特典卡 OR 签售卡 '                                        # 중국어
          'OR โฟโต้การ์ด OR การ์ด OR "kartu foto") '                           # 태국어·인니어
          'has:images -is:retweet -is:reply -from:soultemplates')
CAND = Path(__file__).resolve().parent.parent / "pc_candidates.md"
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


def search_candidates(state):
    """X 검색 → 새 포카 글 후보 마크다운 (없으면 None). 처음엔 최근 20개만, 이후엔 since_id 이후 새 글만."""
    since = state.get("search_since")
    try:
        posts = xposts.search_posts(SEARCH, since_id=since, max_results=20 if not since else 50, media=True)
    except Exception as e:  # noqa: BLE001
        print(f"[포카 검색] 실패: {type(e).__name__} {e}")
        return None
    if posts:
        state["search_since"] = max(posts, key=lambda p: int(p["tweet_id"]))["tweet_id"]
    posts = [p for p in posts if p.get("images")]
    print(f"[포카 검색] 후보 {len(posts)}개")
    if not posts:
        return None
    out = [f"### 🔎 X에서 찾은 포카 글 {len(posts)}개", "", "새 버전이면 원본 글 확인 → 필요하면 작성자에게 허락받고 `site/img/photocards/`에 추가해 주세요.", ""]
    for p in posts:
        cap = re.sub(r"\s+", " ", re.sub(r"https?://\S+", "", p["caption"])).strip()[:120]
        out.append(f"- **@{p['author']}** · {p['timestamp'][:10]} — {cap} ([원본]({p['permalink']}))")
        out.append("  " + " ".join(f'<img src="{u}?name=small" width="120">' for u in p["images"][:4]))
    return "\n".join(out) + "\n"


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
    if not backfill:
        cand = search_candidates(state)
        if cand:
            CAND.write_text(cand)
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
