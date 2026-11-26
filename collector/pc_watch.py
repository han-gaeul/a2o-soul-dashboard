"""@soultemplates 새 포카 템플릿 → 멤버별 카드로 잘라 site/img/photocards/ 갱신 (photocards 워크플로가 PR로 올림).

    python3 collector/pc_watch.py            # 새 글만 (처음 실행은 기준점만 기록)
    python3 collector/pc_watch.py --backfill  # 최근 글 최대 100개 다시 훑기

템플릿 이름은 사진 속 검은 띠 글자(OCR)로 판별:
  'MOON [SUPERSTAR] PHOTOCARD TEMPLATE'            → SUPERSTAR_MOON (멤버 템플릿)
  'A2O SOUL [SUPERSTAR] CARABINER VER. PHOTOCARD'   → SUPERSTAR_CARABINER (단체)
  'A2O SOUL [DANCING IN THE DARK] BROADCAST ...'    → SUPERSTAR_BROADCAST-DITD
  'A2O SOUL [SUPERSTAR] OLIVE YOUNG LUCKY DRAW'     → SUPERSTAR_OLIVEYOUNG
A2O SOUL 템플릿이 아니면(다른 그룹) 건너뜀. 필요: X_BEARER_TOKEN, tesseract, pytesseract, scipy, Pillow

@soultemplates는 트윗 없이 구글 드라이브 폴더의 템플릿만 고치기도 해서(‘?’ 카드 공개 등) 드라이브 폴더도 매번 확인함.
드라이브에서 바뀐 템플릿은 **새 카드만** 추가 (이미 확인·수정한 카드는 덮어쓰지 않음). X 크레딧 안 씀.
"""
import hashlib
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
GROUP_Q = '(에이투오소울 OR 에투소 OR "A2O SOUL" OR A2OSOUL OR "에이투오 소울" OR エトゥソ OR #ตลาดนัดA2Osoul) '  # 일본어 줄임말·태국 장터 태그
TAIL_Q = ' has:images -is:retweet -is:reply -from:soultemplates'
SEARCHES = [
    # 포카 단어 (여러 언어)
    GROUP_Q + '(포카 OR 포토카드 OR 미공포 OR 앨포 OR 공방포카 OR 특전 OR 럭드 OR 럭키드로우 OR 미공개 OR 양도 OR 교환 '
              'OR photocard OR photocards OR pc OR pcs OR POB OR "lucky draw" OR WTT OR WTS OR trade '
              'OR トレカ OR フォトカード OR 特典 OR ラキドロ OR 小卡 OR 特典卡 OR 签售卡 OR โฟโต้การ์ด OR การ์ด OR "kartu foto")' + TAIL_Q,
    # 판매처·행사 이름 (특전 포카 사진이 이 이름과 같이 올라옴)
    GROUP_Q + '(위드뮤 OR 위뮤 OR Withmuu OR 메이크스타 OR 메스 OR Makestar OR 뮤직아트 OR 뮤아 OR Musicart OR 뮤직플랜트 OR 뮤플 OR 애플뮤직 OR 애뮤 '
              'OR 점프업 OR 점업 OR Jumpup OR 엠넷플러스 OR 엠플 OR 앰플 OR 올리브영 OR 올영 OR 사운드웨이브 OR 사웨 OR 케타포 OR Ktown4u '
              'OR 팬싸 OR 영통 OR 팬사인회 OR 공방 OR 럭키)' + TAIL_Q,
    # 그룹명 없는 글: 멤버 이름 + 포카 단어 (한 글자 이름 문·준은 오탐이 많아 영문만)
    '(서하 OR 소라 OR 테오 OR 가쿠 OR 한성 OR 루시엔 OR 시원 OR 알루어 OR 타이 OR 소노 OR 자이 OR 에이든 OR 제트 '
    'OR MOON OR SORA OR SEOHA OR TEO OR GAKU OR JUNE OR HANSUNG OR LUCIEN OR SEEONE OR ALURE OR TAI OR SONO OR ZAI OR AYDEN OR ZET) '
    '(포카 OR 미공포 OR 앨포 OR 특전포카 OR 럭드 OR photocard OR トレカ)' + TAIL_Q,
    # 그룹명·멤버명 둘 다 없는 글: 지금 A2O SOUL 특전을 하는 판매처 + 특전 포카 (다른 그룹 글도 섞일 수 있음)
    '(위드뮤 OR 위뮤 OR Withmuu OR 뮤직플랜트 OR 뮤플 OR 뮤직아트 OR 뮤아 OR Musicart OR 메이크스타 OR 메스 OR Makestar '
    'OR 점프업 OR 점업 OR Jumpup OR 애플뮤직 OR 애뮤 OR 엠넷플러스 OR 엠플 OR 앰플 OR 사운드웨이브 OR 사웨 OR 케타포 OR 올리브영 OR 올영) '
    '(특전 OR 미공포 OR 드볼 OR 럭드 OR 럭키드로우 OR 앨포 OR 팬싸 OR 영통) (포카 OR 포토카드 OR 미공포 OR pc)' + TAIL_Q,
]
DRIVE_FOLDER = "1_0U3zTDV2WDvJc3R8auhuenZF_oYTw1r"  # @soultemplates 공개 드라이브 (트윗에 링크된 폴더)
AUTO = []  # 일반 계정 사진에서 자동으로 자른 카드 [(파일, 글, 작성자)]
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
    if not m or "PHOTOCARD" not in t and "LUCKY" not in t and "POB" not in t:
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
    if "APPLE" in t and "LUCKY" in t:
        return "SUPERSTAR_LD-APPLEMUSIC", t
    if "POB" in t:  # 'A2O SOUL [SUPERSTAR] NEMOZ POB' → 판매처 특전 단체 템플릿
        store = next((k for k in sorted(pc_crop.STORES, key=len, reverse=True) if k in t[m.end():]), None)
        if store:
            return f"SUPERSTAR_POB-{store.replace(' ', '')}", t
    if "BROADCAST" in t:
        return ("SUPERSTAR_BROADCAST-DITD" if "DANCING" in m.group(1) else "SUPERSTAR_BROADCAST-SUPERSTAR"), t
    return None, t


def drive_templates(state, tmp):
    """공개 드라이브 폴더 목록 → 바뀐(또는 처음 보는) 템플릿만 내려받아 tmp/<템플릿이름>.png 로. [(이름, 링크)]"""
    try:
        html = requests.get(f"https://drive.google.com/embeddedfolderview?id={DRIVE_FOLDER}", timeout=30).text
    except Exception as e:  # noqa: BLE001
        print(f"[드라이브] 목록 실패: {e}")
        return []
    entries = re.findall(r'id="entry-([\w-]+)".*?<img src="([^"]+)".*?flip-entry-title">([^<]+)<.*?flip-entry-last-modified"?[^>]*>(?:<div>)?([^<]*)', html, re.S)
    if not entries:  # 목록 모양이 바뀌었을 때 — id·제목만이라도
        entries = [(i, "", t, "") for i, t in re.findall(r'id="entry-([\w-]+)".*?flip-entry-title">([^<]+)<', html, re.S)]
    seen = state.setdefault("drive", {})
    out = []
    import html as _h
    for fid, thumb, title, date in entries:
        title = _h.unescape(title)
        if not re.search(r"\.(png|jpe?g|webp)$", title, re.I):
            continue
        old = seen.get(fid, {})
        mark = f"{thumb.split('=')[0]}|{date.strip()}"
        if old.get("mark") == mark and thumb:
            continue  # 목록상 그대로
        try:
            raw = requests.get(f"https://drive.usercontent.google.com/download?id={fid}&export=download&confirm=t", timeout=60).content
            img = Image.open(io.BytesIO(raw)).convert("RGB")
        except Exception as e:  # noqa: BLE001
            print(f"[드라이브] {title} 받기 실패: {e}")
            continue
        sha = hashlib.sha1(raw).hexdigest()
        seen[fid] = {"title": title, "mark": mark, "sha": sha}
        if old.get("sha") == sha:
            continue  # 내용 그대로
        name, text = template_name(img)
        print(f"[드라이브] {title}: {text[:60]!r} → {name}")
        if name:
            img.save(Path(tmp) / f"{name}.png")
            out.append((name, f"https://drive.google.com/file/d/{fid}/view"))
    return out


def search_candidates(state):
    """X 검색(여러 묶음) → 새 포카 글 후보 마크다운 목록(댓글 하나씩, 없으면 None).
    처음 한 번은 최근 7일을 깊게(묶음마다 최대 300개), 이후엔 since_id 이후 새 글을 묶음마다 최대 200개."""
    # X 비용 아끼기: 템플릿 확인은 3시간마다, 이 검색은 6시간마다만
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    if state.get("search_at") and now - datetime.fromisoformat(state["search_at"]) < timedelta(hours=5, minutes=50):
        print("[포카 검색] 6시간 안 지나서 건너뜀")
        return None
    state["search_at"] = now.isoformat(timespec="minutes")
    deep = state.get("search_v") != 4  # 4: 일반 계정 사진 자동 자르기 시작 — 7일치 한 번 다시 (묶음마다 최대 200개)
    if deep:
        state.pop("search_since", None)
    found = {}
    for i, q in enumerate(SEARCHES):
        key = f"search_since_{i}"
        since = None if deep else state.get(key)
        try:
            got = xposts.search_posts(q, since_id=since, max_results=100, pages=2 if deep else 1, media=True)  # 평소엔 묶음마다 최대 100개
        except Exception as e:  # noqa: BLE001
            print(f"[포카 검색 {i}] 실패: {type(e).__name__} {e}")
            continue
        if got:
            state[key] = max(got, key=lambda p: int(p["tweet_id"]))["tweet_id"]
        for p in got:
            found.setdefault(p["tweet_id"], p)
    state["search_v"] = 4
    posts = sorted(found.values(), key=lambda p: int(p["tweet_id"]), reverse=True)
    posts = [p for p in posts if p.get("images")]
    print(f"[포카 검색] 후보 {len(posts)}개")
    if not posts:
        return None
    try:  # 일반 계정 사진에서 카드 찾아 자르기 (얼굴로 멤버, 글로 판매처) — 사이트에 없는 카드만
        import pc_auto
        AUTO.extend(pc_auto.process(posts, state))
    except ImportError as e:
        print(f"[포카 자동] 건너뜀 (모듈 없음: {e})")
    except Exception as e:  # noqa: BLE001
        print(f"[포카 자동] 실패: {type(e).__name__} {e}")
    # 이슈 댓글 하나에 다 안 들어가서(65,536자) 100개씩 나눠 여러 댓글로 — 전부 보이게
    per = 100
    parts = []
    for i in range(0, len(posts), per):
        chunk = posts[i:i + per]
        head = (f"### 🔎 X에서 찾은 포카 글 {len(posts)}개" + (f" ({i // per + 1}/{-(-len(posts) // per)})" if len(posts) > per else ""))
        out = [head, ""] + (["새 버전이면 원본 글 확인 → 필요하면 작성자에게 허락받고 `site/img/photocards/`에 추가해 주세요.", ""] if i == 0 else [])
        for p in chunk:
            cap = re.sub(r"\s+", " ", re.sub(r"https?://\S+", "", p["caption"])).strip()[:100]
            out.append(f"- **@{p['author']}** · {p['timestamp'][:10]} — {cap} ([원본]({p['permalink']}))")
            out.append("  " + " ".join(f'<img src="{u}?name=small" width="110">' for u in p["images"][:4]))
        parts.append("\n".join(out) + "\n")
    return parts


def main(backfill=False):
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    drive_found = []
    with tempfile.TemporaryDirectory() as tmp:
        drive_found = drive_templates(state, tmp)
        if drive_found:
            pc_crop.ONLY_NEW = True  # 드라이브 쪽은 새 카드만
            pc_crop.main(tmp)
            pc_crop.ONLY_NEW = False
    if not xposts.enabled():
        print("[포카] X 토큰 없음 — X 확인은 건너뜀")
        STATE.write_text(json.dumps(state, indent=1))
        report(drive_found)
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
        for i, part in enumerate(search_candidates(state) or []):
            (CAND if i == 0 else CAND.with_name(f"pc_candidates_{i + 1:02d}.md")).write_text(part)
    STATE.write_text(json.dumps(state, indent=1))
    report(found + drive_found)
    print(f"[포카] 새 글 {len(posts)}개 · 템플릿 {len(found)}장 · 드라이브 {len(drive_found)}장 · 일반 사진 {len(AUTO)}장")


def report(found):
    if not found and not AUTO:
        return
    lines = []
    if AUTO:
        lines += ["### 일반 계정 사진에서 자른 카드", "멤버는 얼굴 인식, 판매처·종류는 글 내용으로 붙였어요. 잘못 잘렸거나 라벨이 틀리면 그 파일만 지우고 머지해 주세요.", "",
                  "| 파일 | 원본 글 |", "|---|---|"] + [f"| {f} | [@{a}]({u}) |" for f, u, a in AUTO] + [""]
    if not found:
        REPORT.write_text("\n".join(lines) + "\n")
        return
    lines += ["@soultemplates 새 포카 템플릿을 멤버별로 잘랐어요. **Files changed**에서 잘린 카드와 라벨(파일 이름)을 확인하고 머지해 주세요.",
             "드라이브에서 바뀐 템플릿은 사이트에 없던 카드만 추가했어요.", "",
             "| 템플릿 | 원본 |", "|---|---|"]
    lines += [f"| {n} | {u} |" for n, u in dict(found).items()]
    lines += ["", "출처 @soultemplates — 허락받음(원본 글 링크 표시 조건)"]
    REPORT.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main(backfill="--backfill" in sys.argv)
