"""사이트 구독자에게 웹 푸시 알림. 매시간 수집 뒤 dashboard.json을 보고 새로 생긴 것만 보냄.

VAPID_PRIVATE_KEY   VAPID 비밀키(base64url, `npx web-push generate-vapid-keys`의 Private Key) — GitHub Secrets
targets.yml push.api / push.vapid_public — 구독 저장 Worker 주소, 공개키

주제(topic): notice 새 공지·사녹 신청 / vote 투표 마감 3시간 전 / show 음방·라이브 1시간 전 / video 새 MV·무대 영상
처음 실행할 땐 지금 있는 것들을 '보낸 것'으로만 기록하고 보내지 않음 (구독 첫날 알림 폭탄 방지)
"""
import base64
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone

import requests

KST = timezone(timedelta(hours=9))

MSG = {
    "ko": {"notice": "📢 새 공지", "prerec": "🎙 사녹 신청 곧 시작", "vote": "🗳 투표 마감 임박", "vote_body": "{name} — {t} 마감",
           "show": "📺 곧 시작", "show_body": "{t} {name}", "video": "🎬 새 영상", "video_more": "{title} 외 {n}개"},
    "en": {"notice": "📢 New notice", "prerec": "🎙 Pre-recording sign-up opens soon", "vote": "🗳 Vote closing soon", "vote_body": "{name} — ends {t} KST",
           "show": "📺 Starting soon", "show_body": "{t} KST {name}", "video": "🎬 New video", "video_more": "{title} +{n} more"},
    "ja": {"notice": "📢 新しいお知らせ", "prerec": "🎙 事前収録の応募がまもなく開始", "vote": "🗳 投票締切間近", "vote_body": "{name} — {t} 締切 (KST)",
           "show": "📺 まもなく開始", "show_body": "{t} (KST) {name}", "video": "🎬 新しい動画", "video_more": "{title} ほか{n}件"},
    "zh": {"notice": "📢 新公告", "prerec": "🎙 预录报名即将开始", "vote": "🗳 投票即将截止", "vote_body": "{name} — {t} 截止 (KST)",
           "show": "📺 即将开始", "show_body": "{t} (KST) {name}", "video": "🎬 新视频", "video_more": "{title} 等 {n} 个"},
    "es": {"notice": "📢 Nuevo aviso", "prerec": "🎙 La inscripción a la pregrabación abre pronto", "vote": "🗳 La votación cierra pronto", "vote_body": "{name} — cierra {t} KST",
           "show": "📺 Empieza pronto", "show_body": "{t} KST {name}", "video": "🎬 Nuevo video", "video_more": "{title} y {n} más"},
    "id": {"notice": "📢 Pengumuman baru", "prerec": "🎙 Pendaftaran pra-rekaman segera dibuka", "vote": "🗳 Voting segera ditutup", "vote_body": "{name} — tutup {t} KST",
           "show": "📺 Segera dimulai", "show_body": "{t} KST {name}", "video": "🎬 Video baru", "video_more": "{title} +{n} lainnya"},
    "th": {"notice": "📢 ประกาศใหม่", "prerec": "🎙 ใกล้เปิดสมัครพรีเรคคอร์ด", "vote": "🗳 โหวตใกล้ปิด", "vote_body": "{name} — ปิด {t} KST",
           "show": "📺 ใกล้เริ่มแล้ว", "show_body": "{t} KST {name}", "video": "🎬 วิดีโอใหม่", "video_more": "{title} และอีก {n} รายการ"},
    "pt": {"notice": "📢 Novo aviso", "prerec": "🎙 Inscrição na pré-gravação abre em breve", "vote": "🗳 Votação fechando", "vote_body": "{name} — fecha {t} KST",
           "show": "📺 Começa em breve", "show_body": "{t} KST {name}", "video": "🎬 Novo vídeo", "video_more": "{title} +{n}"},
}


def _b64u(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _admin_token(priv_b64):
    """Worker 관리용 ES256 토큰 (VAPID 비밀키로 서명 — Worker는 공개키로 확인)."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
    d = base64.urlsafe_b64decode(priv_b64 + "=" * (-len(priv_b64) % 4))
    key = ec.derive_private_key(int.from_bytes(d, "big"), ec.SECP256R1())
    head = _b64u(json.dumps({"alg": "ES256", "typ": "JWT"}).encode())
    body = _b64u(json.dumps({"aud": "push-admin", "exp": int(time.time()) + 300}).encode())
    r, s = decode_dss_signature(key.sign(f"{head}.{body}".encode(), ec.ECDSA(hashes.SHA256())))
    return f"{head}.{body}.{_b64u(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}"


def _kst(s):
    return datetime.fromisoformat(s).replace(tzinfo=KST)


def _first_line(text):
    lines = [re.sub(r"^\[[^\]]*\]\s*", "", ln).strip() for ln in (text or "").splitlines()]
    return next((ln for ln in lines if ln), "")[:120]


def candidates(dash, site, now):
    """지금 보낼 만한 알림 후보 [(key, topic, kind, data)]."""
    tr = dash.get("tr") or {}
    out = []
    for x in dash.get("notice_posts") or []:  # 새 공지 (최근 6시간 안)
        if x.get("at") and now - _kst(x["at"]) < timedelta(hours=6):
            out.append((f"np|{x['url']}", "notice", "notice", {"body": _first_line(x["text"]), "url": site + "#notice", "tr": {}}))
    for v in dash.get("prerecs") or []:  # 사녹 신청 시작 1시간 전 ~ 시작
        st = _kst(v["start"])
        if timedelta(0) <= st - now <= timedelta(hours=1, minutes=10):
            out.append((f"pr|{v['start']}|{v.get('show')}", "notice", "prerec",
                        {"body": f"{v.get('show', '')} {v['start'][11:]}", "url": site + "#cheer", "tr": {v.get('show', ''): tr.get(v.get('show', ''), {})}}))
    for v in dash.get("votes") or []:  # 투표 마감 3시간 전
        end, start = _kst(v["end"]), _kst(v.get("start") or v["end"])
        if start <= now and timedelta(0) < end - now <= timedelta(hours=3):
            name = " · ".join(x for x in [v.get("show"), v.get("title")] if x)
            out.append((f"vt|{v['end']}|{name}", "vote", "vote",
                        {"name": name, "t": v["end"][11:], "url": site + "#cheer", "parts": [v.get("show"), v.get("title")], "tr": tr}))
    for e in dash.get("events") or []:  # 음방·라이브 1시간 전
        if e.get("type") in ("음방", "라이브") and e.get("time") and re.fullmatch(r"\d{2}:\d{2}", e["time"]):
            st = _kst(f"{e['date']} {e['time']}")
            if timedelta(0) <= st - now <= timedelta(hours=1, minutes=10):
                out.append((f"ev|{e['date']}|{e['time']}|{e['title']}", "show", "show",
                            {"name": e["title"], "t": e["time"], "url": site, "parts": [e["title"]], "tr": tr}))
    vids = [v for v in dash.get("videos") or [] if v.get("category") != "fancam" and v.get("published_at")
            and now - datetime.fromisoformat(v["published_at"].replace("Z", "+00:00")) < timedelta(hours=3)]
    for v in vids:  # 새 MV·무대 영상 (직캠은 많아서 뺌) — 같은 시간대 여러 개면 하나로 묶음
        out.append((f"vd|{v['id']}", "video", "video", {"title": v["title"][:90], "url": f"https://youtu.be/{v['id']}"}))
    return out


def compose(kind, data, lang, group=None):
    m = MSG.get(lang) or MSG["en"]
    trs = lambda s: ((data.get("tr") or {}).get(s) or {}).get(lang) or s if s else s  # noqa: E731
    if kind == "notice":
        return m["notice"], data["body"], data["url"]
    if kind == "prerec":
        return m["prerec"], data["body"], data["url"]
    if kind == "vote":
        name = " · ".join(trs(p) for p in data["parts"] if p) if lang != "ko" else data["name"]
        return m["vote"], m["vote_body"].format(name=name, t=data["t"]), data["url"]
    if kind == "show":
        name = trs(data["name"]) if lang != "ko" else data["name"]
        return m["show"], m["show_body"].format(name=name, t=data["t"]), data["url"]
    if kind == "video":
        body = data["title"] if not group or len(group) < 2 else m["video_more"].format(title=data["title"], n=len(group) - 1)
        return m["video"], body, data["url"]
    return "A2O SOUL", "", data.get("url")


def run(dash, cfg, state, site="https://a2osoul-tracker.com/"):
    """state: {'sent': [...]} — 바뀐 state를 돌려줌."""
    push = cfg.get("push") or {}
    priv = os.environ.get("VAPID_PRIVATE_KEY")
    now = datetime.now(KST)
    cands = candidates(dash, site, now)
    sent = set(state.get("sent") or [])
    first = "sent" not in state
    new = [c for c in cands if c[0] not in sent]
    state["sent"] = (list(sent) + [c[0] for c in new])[-800:]
    if first:
        print(f"[푸시] 처음 실행 — 지금 있는 {len(new)}개는 보낸 것으로만 기록")
        return state
    if not new:
        return state
    if not (priv and push.get("api") and push.get("vapid_public")):
        print(f"[푸시] 설정 없음 — 새 알림 {len(new)}개 건너뜀")
        return state
    try:
        from pywebpush import WebPushException, webpush
        subs = requests.get(push["api"].rstrip("/") + "/subs", headers={"Authorization": f"Bearer {_admin_token(priv)}"}, timeout=20)
        subs.raise_for_status()
        subs = subs.json()
    except Exception as e:  # noqa: BLE001
        print(f"[푸시] 구독 목록 실패: {type(e).__name__} {e}")
        return state
    videos = [c for c in new if c[2] == "video"]
    msgs = [c for c in new if c[2] != "video"] + ([videos[0]] if videos else [])
    dead, ok = [], 0
    for s in subs:
        for key, topic, kind, data in msgs[:5]:  # 한 번에 최대 5개
            if topic not in (s.get("topics") or []):
                continue
            title, body, url = compose(kind, data, s.get("lang") or "en", videos if kind == "video" else None)
            try:
                webpush(subscription_info=s["sub"], data=json.dumps({"title": title, "body": body, "url": url, "tag": key[:60]}, ensure_ascii=False),
                        vapid_private_key=priv, vapid_claims={"sub": "https://a2osoul-tracker.com"}, ttl=3 * 3600, timeout=15)
                ok += 1
            except WebPushException as e:
                if e.response is not None and e.response.status_code in (404, 410):
                    dead.append(s["id"])
                    break
                print(f"[푸시] 실패 {e.response.status_code if e.response is not None else ''}")
            except Exception as e:  # noqa: BLE001
                print(f"[푸시] 실패: {type(e).__name__}")
    if dead:
        try:
            requests.post(push["api"].rstrip("/") + "/prune", json={"ids": dead}, timeout=20,
                          headers={"Authorization": f"Bearer {_admin_token(priv)}"})
        except Exception:  # noqa: BLE001
            pass
    print(f"[푸시] 알림 {len(msgs)}종 · 구독 {len(subs)}명 · 보냄 {ok} · 만료 정리 {len(dead)}")
    return state
