"""공식 인스타 공지 → AI(Claude)로 일정·티켓·굿즈 정보 추출.

- 새 게시물만 처리 (data/announcements.json에 처리 기록)
- 확신도 높은 항목은 사이트에 자동 반영, 낮은 항목은 '확인 필요'로 따로 모아 GitHub 이슈로 알림
ANTHROPIC_API_KEY 필요, ANTHROPIC_MODEL로 모델 변경 가능
"""
import json
import os
import re

import requests

API = "https://api.anthropic.com/v1/messages"
KINDS = {
    "music_show": "음방", "broadcast": "방송", "live": "라이브", "release": "발매", "concert": "공연",
    "fanmeeting": "팬미팅", "ticket": "티켓", "merch": "굿즈", "vote": "투표", "event": "행사", "other": "기타",
}
AUTO_CONFIDENCE = 0.8  # 이 이상이면 자동 반영

PROMPT = """너는 K-pop 그룹 A2O SOUL 팬 사이트의 정보 정리 도우미야.
아래는 공식 인스타그램 게시물 본문이야. 게시 시각: {posted} (KST). 오늘: {today} (KST).

본문에서 팬이 챙겨야 할 구체적인 일정·정보만 뽑아서 JSON 배열로만 답해. 설명 문장은 쓰지 마.
각 항목 형식:
{{"kind": "{kinds}", "title": "한국어로 짧게 (예: 뮤직뱅크 출연, 1st 미니앨범 예약 판매)",
  "date": "YYYY-MM-DD 또는 null", "time": "HH:MM(KST) 또는 null", "end_date": "YYYY-MM-DD 또는 null",
  "place": "장소/방송사/판매처 또는 null", "url": "본문에 있는 링크 또는 null", "confidence": 0~1}}

규칙:
- 본문에 실제로 적힌 내용만. 추측해서 날짜를 만들지 마. '내일', '이번 주 금요일' 같은 표현은 게시 시각 기준으로 계산하고 confidence를 낮춰.
- 날짜가 없는 판매처·티켓 안내도 kind에 맞춰 넣되 date는 null.
- 지난 일정 회고, 단순 사진·인사, 응원 메시지는 빈 배열 [].
- 다른 그룹(A2O LITE 등)만 해당하는 내용은 제외.

본문:
\"\"\"{caption}\"\"\""""


def enabled():
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _extract(caption, posted, today):
    body = {
        "model": os.environ.get("ANTHROPIC_MODEL", "claude-haiku-5-5"),
        "max_tokens": 1200,
        "messages": [{"role": "user", "content": PROMPT.format(
            posted=posted, today=today, kinds="|".join(KINDS), caption=caption[:4000])}],
    }
    r = requests.post(API, json=body, timeout=60, headers={
        "x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01", "content-type": "application/json"})
    r.raise_for_status()
    text = "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text")
    m = re.search(r"\[.*\]", text, re.S)
    items = json.loads(m.group(0)) if m else []
    return [clean(i) for i in items if isinstance(i, dict)]


def clean(i):
    def d(v):
        v = str(v or "")
        return v if re.fullmatch(r"\d{4}-\d{2}-\d{2}", v) else None

    def tm(v):
        v = str(v or "")
        return v if re.fullmatch(r"\d{2}:\d{2}", v) else None

    url = str(i.get("url") or "")
    try:
        conf = max(0.0, min(1.0, float(i.get("confidence", 0))))
    except (TypeError, ValueError):
        conf = 0.0
    return {
        "kind": i.get("kind") if i.get("kind") in KINDS else "other",
        "title": str(i.get("title") or "").strip()[:80],
        "date": d(i.get("date")), "time": tm(i.get("time")), "end_date": d(i.get("end_date")),
        "place": (str(i.get("place")).strip()[:80] if i.get("place") else None),
        "url": url if url.startswith("https://") else None,
        "confidence": round(conf, 2),
    }


def run(media, store, today, kst_of, extract=None, limit=15):
    """media: [{id, caption, timestamp, permalink}], store: data/announcements.json 내용(갱신됨).
    extract: 본문 → 항목 함수 (기본 AI). 새로 처리한 개수 반환."""
    extract = extract or _extract
    processed = store.setdefault("posts", {})
    new = [m for m in media if m.get("id") not in processed and (m.get("caption") or "").strip()]
    for m in new[:limit]:  # AI는 한 번에 최대 15개 (첫 실행 비용 제한)
        posted = kst_of(m.get("timestamp"))
        try:
            items = extract(m["caption"], posted, today)
        except Exception as e:  # noqa: BLE001
            print(f"[공지] {m['id']} 추출 실패: {type(e).__name__} {e}")
            continue
        processed[m["id"]] = {"timestamp": m.get("timestamp"), "permalink": m.get("permalink"),
                              "excerpt": (m.get("caption") or "")[:140], "caption": (m.get("caption") or "")[:1500],
                              "items": [i for i in items if i["title"]]}
        print(f"[공지] {m['id']} {posted} 항목 {len(items)}개: " + ", ".join(i["title"] for i in items))
    for m in media:  # 캡션 없는 게시물도 처리한 걸로 기록해 매번 다시 보지 않게
        processed.setdefault(m["id"], {"timestamp": m.get("timestamp"), "permalink": m.get("permalink"), "excerpt": "", "items": []})
    return len(new[:limit])
