"""사이트 구독자에게 웹 푸시 알림. 매시간 수집 뒤 dashboard.json을 보고 새로 생긴 것만 보냄.

VAPID_PRIVATE_KEY   VAPID 비밀키(base64url, `npx web-push generate-vapid-keys`의 Private Key) — GitHub Secrets
targets.yml push.api / push.vapid_public — 구독 저장 Worker 주소, 공개키

주제(topic): notice 새 공지·사녹 신청·차트 진입·급상승 / vote 투표 마감 3시간 전·음방 1위 후보 / show 음방·라이브 1시간 전 / video 새 MV·무대 영상·조회수 돌파 / birthday 멤버 생일 (그날 0시부터)
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
    "ko": {"views": "🎉 {name} MV {n}뷰 돌파!", "subs": "🎉 유튜브 구독자 {n} 돌파!", "birthday": "🎂 오늘은 {name} 생일", "birthday_body": "{name}의 생일을 함께 축하해요!", "chart_new": "📈 {service} 진입!", "chart_up": "🚀 {service} 급상승", "chart_new_body": "{song} {rank}위", "chart_up_body": "{song} {rank}위 (↑{n})", "nominee": "🏆 에투소 {show} 1위 후보!", "nominee_body": "{t} 생방송 투표로 1위 만들어요", "ev_show": "{show} 출연", "show_now": "🔴 지금 생방송 중", "notice": "📢 새 공지", "prerec": "🎙 사녹 신청 곧 시작", "vote": "🗳 투표 마감 임박", "vote_body": "{name} — {t} 마감",
           "show": "📺 곧 시작", "show_body": "{t} {name}", "video": "🎬 새 영상", "video_more": "{title} 외 {n}개"},
    "en": {"views": "🎉 {name} MV hit {n} views!", "subs": "🎉 {n} YouTube subscribers!", "birthday": "🎂 Happy birthday, {name}!", "birthday_body": "Today is {name}'s birthday — celebrate together!", "chart_new": "📈 Entered {service}!", "chart_up": "🚀 Rising on {service}", "chart_new_body": "{song} #{rank}", "chart_up_body": "{song} #{rank} (↑{n})", "nominee": "🏆 A2O SOUL is a #1 nominee on {show}!", "nominee_body": "Live vote at {t} KST — let's win", "ev_show": "On {show}", "show_now": "🔴 Live now", "notice": "📢 New notice", "prerec": "🎙 Pre-recording sign-up opens soon", "vote": "🗳 Vote closing soon", "vote_body": "{name} — ends {t} KST",
           "show": "📺 Starting soon", "show_body": "{t} KST {name}", "video": "🎬 New video", "video_more": "{title} +{n} more"},
    "ja": {"views": "🎉 {name} MV {n}回再生突破！", "subs": "🎉 YouTube登録者 {n} 突破！", "birthday": "🎂 今日は{name}の誕生日", "birthday_body": "{name}の誕生日を一緒にお祝いしよう！", "chart_new": "📈 {service} チャートイン！", "chart_up": "🚀 {service} 急上昇", "chart_new_body": "{song} {rank}位", "chart_up_body": "{song} {rank}位 (↑{n})", "nominee": "🏆 A2O SOUL {show} 1位候補！", "nominee_body": "{t} (KST) 生放送投票で1位に", "ev_show": "{show} 出演", "show_now": "🔴 生放送中", "notice": "📢 新しいお知らせ", "prerec": "🎙 事前収録の応募がまもなく開始", "vote": "🗳 投票締切間近", "vote_body": "{name} — {t} 締切 (KST)",
           "show": "📺 まもなく開始", "show_body": "{t} (KST) {name}", "video": "🎬 新しい動画", "video_more": "{title} ほか{n}件"},
    "zh": {"views": "🎉 {name} MV 播放量突破 {n}！", "subs": "🎉 YouTube 订阅突破 {n}！", "birthday": "🎂 今天是{name}的生日", "birthday_body": "一起为{name}庆祝生日吧！", "chart_new": "📈 进入 {service}！", "chart_up": "🚀 {service} 急升", "chart_new_body": "{song} 第{rank}名", "chart_up_body": "{song} 第{rank}名 (↑{n})", "nominee": "🏆 A2O SOUL 入围 {show} 一位候补！", "nominee_body": "{t} (KST) 直播投票，一起拿一位", "ev_show": "出演 {show}", "show_now": "🔴 正在直播", "notice": "📢 新公告", "prerec": "🎙 预录报名即将开始", "vote": "🗳 投票即将截止", "vote_body": "{name} — {t} 截止 (KST)",
           "show": "📺 即将开始", "show_body": "{t} (KST) {name}", "video": "🎬 新视频", "video_more": "{title} 等 {n} 个"},
    "es": {"views": "🎉 ¡{name} MV superó {n} vistas!", "subs": "🎉 ¡{n} suscriptores en YouTube!", "birthday": "🎂 ¡Feliz cumpleaños, {name}!", "birthday_body": "Hoy es el cumpleaños de {name}, ¡celebremos juntos!", "chart_new": "📈 ¡Entró en {service}!", "chart_up": "🚀 Subiendo en {service}", "chart_new_body": "{song} #{rank}", "chart_up_body": "{song} #{rank} (↑{n})", "nominee": "🏆 ¡A2O SOUL nominado al #1 en {show}!", "nominee_body": "Voto en vivo a las {t} KST — vamos por el #1", "ev_show": "En {show}", "show_now": "🔴 En vivo ahora", "notice": "📢 Nuevo aviso", "prerec": "🎙 La inscripción a la pregrabación abre pronto", "vote": "🗳 La votación cierra pronto", "vote_body": "{name} — cierra {t} KST",
           "show": "📺 Empieza pronto", "show_body": "{t} KST {name}", "video": "🎬 Nuevo video", "video_more": "{title} y {n} más"},
    "id": {"views": "🎉 MV {name} tembus {n} views!", "subs": "🎉 {n} subscriber YouTube!", "birthday": "🎂 Selamat ulang tahun, {name}!", "birthday_body": "Hari ini ulang tahun {name} — rayakan bersama!", "chart_new": "📈 Masuk {service}!", "chart_up": "🚀 Naik di {service}", "chart_new_body": "{song} #{rank}", "chart_up_body": "{song} #{rank} (↑{n})", "nominee": "🏆 A2O SOUL nominasi #1 di {show}!", "nominee_body": "Vote live {t} KST — ayo menang", "ev_show": "Tampil di {show}", "show_now": "🔴 Sedang live", "notice": "📢 Pengumuman baru", "prerec": "🎙 Pendaftaran pra-rekaman segera dibuka", "vote": "🗳 Voting segera ditutup", "vote_body": "{name} — tutup {t} KST",
           "show": "📺 Segera dimulai", "show_body": "{t} KST {name}", "video": "🎬 Video baru", "video_more": "{title} +{n} lainnya"},
    "th": {"views": "🎉 MV {name} ทะลุ {n} วิว!", "subs": "🎉 ผู้ติดตาม YouTube ทะลุ {n}!", "birthday": "🎂 สุขสันต์วันเกิด {name}!", "birthday_body": "วันนี้วันเกิดของ {name} มาฉลองด้วยกันนะ!", "chart_new": "📈 ติดชาร์ต {service}!", "chart_up": "🚀 พุ่งขึ้นใน {service}", "chart_new_body": "{song} อันดับ {rank}", "chart_up_body": "{song} อันดับ {rank} (↑{n})", "nominee": "🏆 A2O SOUL เข้าชิงอันดับ 1 {show}!", "nominee_body": "โหวตสด {t} KST — ไปคว้าอันดับ 1 กัน", "ev_show": "ออกรายการ {show}", "show_now": "🔴 กำลังออกอากาศสด", "notice": "📢 ประกาศใหม่", "prerec": "🎙 ใกล้เปิดสมัครพรีเรคคอร์ด", "vote": "🗳 โหวตใกล้ปิด", "vote_body": "{name} — ปิด {t} KST",
           "show": "📺 ใกล้เริ่มแล้ว", "show_body": "{t} KST {name}", "video": "🎬 วิดีโอใหม่", "video_more": "{title} และอีก {n} รายการ"},
    "pt": {"views": "🎉 MV {name} passou de {n} views!", "subs": "🎉 {n} inscritos no YouTube!", "birthday": "🎂 Feliz aniversário, {name}!", "birthday_body": "Hoje é aniversário de {name} — vamos comemorar juntos!", "chart_new": "📈 Entrou no {service}!", "chart_up": "🚀 Subindo no {service}", "chart_new_body": "{song} #{rank}", "chart_up_body": "{song} #{rank} (↑{n})", "nominee": "🏆 A2O SOUL indicado ao #1 no {show}!", "nominee_body": "Voto ao vivo às {t} KST — vamos vencer", "ev_show": "No {show}", "show_now": "🔴 Ao vivo agora", "notice": "📢 Novo aviso", "prerec": "🎙 Inscrição na pré-gravação abre em breve", "vote": "🗳 Votação fechando", "vote_body": "{name} — fecha {t} KST",
           "show": "📺 Começa em breve", "show_body": "{t} KST {name}", "video": "🎬 Novo vídeo", "video_more": "{title} +{n}"},
    "fil": {"birthday": "🎂 Happy birthday, {name}!", "birthday_body": "Birthday ngayon ni {name} — sabay tayong magdiwang!", "chart_new": "📈 Pumasok sa {service}!", "chart_up": "🚀 Umaakyat sa {service}", "chart_new_body": "{song} #{rank}", "chart_up_body": "{song} #{rank} (↑{n})", "nominee": "🏆 #1 nominee ang A2O SOUL sa {show}!", "nominee_body": "Live vote sa {t} KST — manalo tayo", "ev_show": "Sa {show}", "show_now": "🔴 Live ngayon", "notice": "📢 Bagong anunsyo", "prerec": "🎙 Malapit nang magbukas ang pre-recording sign-up", "vote": "🗳 Malapit nang magsara ang boto", "vote_body": "{name} — magsasara {t} KST", "show": "📺 Malapit nang magsimula", "show_body": "{t} KST {name}", "video": "🎬 Bagong video", "video_more": "{title} +{n} pa"},
    "vi": {"birthday": "🎂 Chúc mừng sinh nhật {name}!", "birthday_body": "Hôm nay là sinh nhật {name} — cùng chúc mừng nhé!", "chart_new": "📈 Lọt vào {service}!", "chart_up": "🚀 Tăng hạng trên {service}", "chart_new_body": "{song} hạng {rank}", "chart_up_body": "{song} hạng {rank} (↑{n})", "nominee": "🏆 A2O SOUL được đề cử hạng 1 {show}!", "nominee_body": "Bình chọn live lúc {t} KST — cùng giành chiến thắng", "ev_show": "Diễn tại {show}", "show_now": "🔴 Đang phát sóng", "notice": "📢 Thông báo mới", "prerec": "🎙 Sắp mở đăng ký ghi hình trước", "vote": "🗳 Bình chọn sắp đóng", "vote_body": "{name} — đóng lúc {t} KST", "show": "📺 Sắp bắt đầu", "show_body": "{t} KST {name}", "video": "🎬 Video mới", "video_more": "{title} và {n} video khác"},
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


def alert_admin(api, priv, title, body):
    """초안 알림(tweet)을 켠 관리자 기기에만 푸시."""
    from pywebpush import webpush
    subs = requests.get(api.rstrip("/") + "/subs", headers={"Authorization": f"Bearer {_admin_token(priv)}"}, timeout=20).json()
    for s in subs:
        if "tweet" in (s.get("topics") or []):
            try:
                webpush(subscription_info=s["sub"], data=json.dumps({"title": title, "body": body, "url": "https://a2osoul-tracker.com/tweet.html",
                        "tag": "x-credit"}, ensure_ascii=False), vapid_private_key=priv, vapid_claims={"sub": "https://a2osoul-tracker.com"}, ttl=6 * 3600, timeout=15)
            except Exception as e:  # noqa: BLE001
                print(f"[X] 관리자 알림 실패: {type(e).__name__}")


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
                        {"body": f"{v.get('show', '')} {v['start'][11:]}", "url": site + "#vote", "tr": {v.get('show', ''): tr.get(v.get('show', ''), {})}}))
    for v in dash.get("votes") or []:  # 투표 마감 3시간 전
        end, start = _kst(v["end"]), _kst(v.get("start") or v["end"])
        if start <= now and timedelta(0) < end - now <= timedelta(hours=3):
            name = " · ".join(x for x in [v.get("show"), v.get("title")] if x)
            out.append((f"vt|{v['end']}|{name}", "vote", "vote",
                        {"name": name, "t": v["end"][11:], "url": site + "#vote", "parts": [v.get("show"), v.get("title")], "tr": tr}))
    lives = (dash.get("info") or {}).get("show_live") or []
    # 일정에 시간이 없으면 기본 방송 시간 → 투표 가이드의 방송 시간 ('화 18:00 · SBS Life')으로 덮어씀
    air = {"더쇼": "18:00", "쇼챔피언": "18:00", "엠카운트다운": "18:00", "뮤직뱅크": "17:15", "음악중심": "15:15", "인기가요": "15:20"}
    for v in (dash.get("howto") or {}).get("voting") or []:
        m = re.search(r"(\d{1,2}):(\d{2})", v.get("when") or "")
        if m and v.get("show"):
            air[v["show"]] = f"{int(m.group(1)):02d}:{m.group(2)}"
    evs = dash.get("events") or []
    shows_on = {(e["date"], sh) for e in evs if e.get("type") == "음방" for sh in air if sh in (e.get("title") or "")}
    for e in evs:  # 음방·라이브 1시간 전 ~ 시작 30분 뒤 (생방송 보기 링크로)
        if e.get("type") not in ("음방", "라이브", "라디오") and not e.get("notify"):  # notify: true면 행사도 1시간 전 알림
            continue
        # 방송사 유튜브 라이브('[🔴라이브] 11/21 SATㅣ쇼! 음악중심ㅣ…')는 같은 날 '음악중심 출연' 일정이 있으면 건너뜀 (알림·초안 중복 + 긴 제목)
        if e.get("type") == "라이브" and any((e["date"], sh) in shows_on for sh in air if sh in (e.get("title") or "")):
            continue
        if e.get("credit"):  # 팬 계정이 주최하는 행사(단체 스밍·콜라보 등)는 푸시·트윗 둘 다 안 함
            continue
        tm = e.get("time") or next((t for sh, t in air.items() if sh in (e.get("title") or "")), None)
        if not (tm and re.fullmatch(r"\d{2}:\d{2}", tm)):
            continue
        st = _kst(f"{e['date']} {tm}")
        if -timedelta(minutes=30) <= st - now <= timedelta(hours=1, minutes=10):
            live = next((x for x in lives if x.get("show") and x["show"] in (e.get("title") or "")), None)
            out.append((f"ev|{e['date']}|{tm}|{e['title']}", "show", "show",
                        {"name": e["title"], "t": tm, "url": (live or {}).get("url") or site, "parts": [e["title"]], "tr": tr, "now": now >= st,
                         "credit": e.get("credit") or "", "no_draft": True}))  # 1시간 전은 푸시만
            # 트윗: 방송 5분 전 · 시작 정확히 10분 뒤 — 수집이 10분마다라 미리 보내고 워커가 그 시각(post_at)에 올림
            base = {"name": e["title"], "t": tm, "url": (live or {}).get("url") or site, "parts": [e["title"]], "tr": tr,
                    "credit": e.get("credit") or "", "draft_only": True}
            for tag, at, extra in (("pre5", st - timedelta(minutes=5), {"soon": True}), ("live", st + timedelta(minutes=10), {"now": True})):
                if -timedelta(minutes=20) <= now - at <= timedelta(minutes=20):  # 20분 전부터 예약 · 놓쳤으면 20분 안엔 바로
                    out.append((f"ev|{e['date']}|{tm}|{e['title']}|{tag}", "show", "show", {**base, **extra, "post_at": int(at.timestamp() * 1000)}))
    for c in dash.get("chart_moves") or []:  # 차트 첫 진입·10계단 이상 상승 (입력 후 3시간 안)
        if timedelta(0) <= now - _kst(c["at"]) <= timedelta(hours=3):
            out.append((f"ch|{c['song']}|{c['service']}|{c['at']}", "notice", "chart", {**c, "url": site + "#cheer", "tr": tr}))
    for x in dash.get("timeline") or []:  # MV 조회수·구독자 돌파 (돌파한 날·다음 날까지)
        if x.get("kind") in ("views", "subs") and x.get("n") and now.date() - _kst(x["date"] + " 00:00").date() <= timedelta(days=1):
            out.append((f"ms|{x['kind']}|{x.get('name', '')}|{x['n']}", "video", x["kind"],
                        {"name": x.get("name") or "", "n": x["n"], "url": x.get("url") or site}))
    # 음원 총공(총공팀 공지)·해외 팬 콜라보(스테이션헤드 등) — 시작 1시간 전쯤 + 진행 중에 트윗 초안만
    # (팬 주최라 푸시·자동 업로드 없음, tweet.html에서 확인 후 올림)
    jobs = [(e, "stream") for e in evs if e.get("type") == "총공"] + [(c, "collab") for c in dash.get("collabs") or []]
    for e, kind in jobs:
        if not re.fullmatch(r"\d{2}:\d{2}", e.get("time") or ""):
            continue
        st = _kst(f"{e['date']} {e['time']}")
        mm = re.search(r"\(~\s*(\d{1,2}):(\d{2})\)", e["title"])
        end = _kst(f"{e['date']} 00:00") + timedelta(hours=int(mm.group(1)), minutes=int(mm.group(2))) if mm else st + timedelta(hours=1)
        if end <= st:
            end += timedelta(days=1)
        base = {"name": re.sub(r"\s*\(~[^)]*\)", "", e["title"]).strip(), "t": e["time"], "end": f"{mm.group(1)}:{mm.group(2)}" if mm else "",
                "end_real": end.strftime("%H:%M"), "post": e.get("url") or "", "url": site + "#cheer", "with": e.get("with") or "",
                "draft_only": True}
        key = f"{'sg' if kind == 'stream' else 'cb'}|{e['date']}|{e['time']}|{e['title']}"
        if -timedelta(minutes=20) <= st - now <= timedelta(hours=1, minutes=10):  # 시작 전
            out.append((key, "show", kind, base))
        elif st + timedelta(minutes=30) <= now <= end - timedelta(minutes=30):  # 진행 중 (시작 30분 뒤 ~ 끝나기 30분 전)
            out.append((key + "|live", "show", kind, {**base, "now": True}))
    for n in dash.get("nominees") or []:  # 음방 1위 후보 — 방송 당일, 방송 끝나기 전까지
        tm = air.get(n["show"]) or ""
        end = _kst(f"{n['date']} {tm or '23:00'}") + timedelta(hours=1)
        if n["date"] == now.strftime("%Y-%m-%d") and now <= end:
            live = next((x for x in lives if x.get("show") and x["show"] in n["show"]), None)
            out.append((f"nm|{n['date']}|{n['show']}", "vote", "nominee",
                        {"show": n["show"], "t": tm or "", "url": (live or {}).get("url") or site + "#cheer", "tr": tr}))
    today = now.strftime("%m-%d")
    for m in dash.get("members") or []:  # 멤버 생일 당일 (KST 0시부터 하루 동안, 한 번만)
        if m.get("birthday") == today:
            out.append((f"bd|{now.year}|{m['name']}", "birthday", "birthday",
                        {"name": m["name"], "ko": m.get("ko") or m["name"], "url": site + "#member/" + m["name"]}))
    vids = [v for v in dash.get("videos") or [] if v.get("category") != "fancam" and v.get("published_at")
            and now - datetime.fromisoformat(v["published_at"].replace("Z", "+00:00")) < timedelta(hours=3)]
    for v in vids:  # 새 MV·무대 영상 (직캠은 많아서 뺌) — 같은 시간대 여러 개면 하나로 묶음
        out.append((f"vd|{v['id']}", "video", "video", {"title": v["title"][:90], "url": f"https://youtu.be/{v['id']}",
                                                         "members": _members_in(v, dash.get("members") or [])}))
    for x in dash.get("media_posts") or []:  # 매체·콘텐츠 계정 새 글 (3시간 안) — 트윗 초안만, 푸시는 안 보냄
        if x.get("at") and timedelta(0) <= now - _kst(x["at"]) < timedelta(hours=3):
            head = next((ln for ln in (x.get("text") or "").splitlines() if re.sub(r"#\S+|https?://\S+", "", ln).strip()), "")
            head = re.sub(r"\s*https?://\S+", "", head).strip()[:100]
            out.append((f"md|{x['url']}", "media", "media", {"name": x.get("name") or x.get("handle") or "", "title": head, "url": x["url"],
                                                            "members": _members_in({"title": x.get("text") or ""}, dash.get("members") or [])}))
    seen = set()
    for x in dash.get("photos") or []:  # 공식 계정 사진 글 ([📸]·컨셉 포토·생일 등, 공지 이미지는 사진 모음에서 이미 빠짐 · 3시간 안) — 확인 없이 바로 리트윗 (푸시는 안 보냄)
        u = x.get("url") or ""
        if x.get("account") != "x" or "/a2o_soul/status/" not in u.lower() or u in seen:
            continue
        seen.add(u)
        if x.get("at") and timedelta(0) <= now - _kst(x["at"]) < timedelta(hours=3):
            out.append((f"rt|{u}", "media", "media", {"name": "A2O SOUL", "title": (x.get("text") or "[📸]").strip()[:100], "url": u,
                                                     "members": [], "rt": True}))
    for x in dash.get("official_x") or []:  # @A2O_SOUL 글 전부 (링크·영상·공지 포함, 3시간 안) — 바로 리트윗 (사진 글과 같은 키라 중복 없음)
        if x.get("at") and timedelta(0) <= now - _kst(x["at"]) < timedelta(hours=3) and f"rt|{x['url']}" not in {o[0] for o in out}:
            out.append((f"rt|{x['url']}", "media", "media", {"name": "A2O SOUL", "title": "공식", "url": x["url"], "members": [], "rt": True}))
    for x in dash.get("vote_wins") or []:  # 투표 앱·방송사의 A2O SOUL 투표 글 전부 (6시간 안 — 투표 검색이 평소 3시간마다) — 바로 리트윗
        if x.get("at") and timedelta(0) <= now - _kst(x["at"]) < timedelta(hours=6):
            out.append((f"rt|{x['url']}", "media", "media", {"name": x.get("by") or "", "title": "투표", "url": x["url"], "members": [], "rt": True}))
    for x in dash.get("show_fancams") or []:  # 방송사 공식 직캠 글 (4시간 안 — 음방 사진 검색이 1~3시간마다) — 바로 리트윗
        if x.get("at") and timedelta(0) <= now - _kst(x["at"]) < timedelta(hours=4):
            out.append((f"rt|{x['url']}", "media", "media", {"name": x.get("by") or "", "title": "직캠", "url": x["url"], "members": [], "rt": True}))
    return out


def _members_in(v, members):
    """영상에 나온 멤버 [(영문, 한글)] — member 필드 + 제목 속 이름 (한 글자 한글 이름은 오탐이 많아 필드로만)."""
    title = v.get("title") or ""
    out = []
    for m in members:
        en, ko = m["name"], m.get("ko") or ""
        hit = v.get("member") == en or re.search(rf"(?<![A-Za-z]){re.escape(en)}(?![A-Za-z])", title) \
            or (len(ko) >= 2 and ko in title)
        if hit:
            out.append((en, ko))
    return out


def compose(kind, data, lang, group=None):
    m = MSG.get(lang) or MSG["en"]
    trs = lambda s: (((data.get("tr") or {}).get(s) or {}).get(lang) or ((data.get("tr") or {}).get(s) or {}).get("en") or s) if s and lang != "ko" else s  # noqa: E731
    if kind == "notice":
        return m["notice"], data["body"], data["url"]
    if kind == "prerec":
        return m["prerec"], data["body"], data["url"]
    if kind == "vote":
        name = " · ".join(trs(p) for p in data["parts"] if p) if lang != "ko" else data["name"]
        return m["vote"], m["vote_body"].format(name=name, t=data["t"]), data["url"]
    if kind == "show":
        name = data["name"]
        if lang != "ko":  # '더쇼 출연' → 'On THE SHOW' (방송 이름은 translations.yml)
            mm = re.fullmatch(r"(.+?)\s*출연", name)
            name = m["ev_show"].format(show=trs(mm.group(1))) if mm else trs(name)
        return (m["show_now"] if data.get("now") else m["show"]), m["show_body"].format(name=name, t=data["t"]), data["url"]
    if kind in ("views", "subs"):
        n = data["n"]
        num = (f"{n // 100000000}억" if n >= 100000000 and n % 100000000 == 0 else f"{n // 10000:,}만" if n >= 10000 else f"{n:,}") if lang == "ko" \
            else (f"{n / 1e8:g}億" if n >= 1e8 else f"{n / 1e4:g}万" if n >= 1e4 else str(n)) if lang in ("ja", "zh") \
            else (f"{n / 1e6:g}M" if n >= 1e6 else f"{n / 1e3:g}K" if n >= 1e3 else str(n))
        return m[kind].format(name=data["name"], n=num), "", data["url"]
    if kind == "chart":
        svc = trs(data["service"])
        if data["kind"] == "new":
            return m["chart_new"].format(service=svc), m["chart_new_body"].format(song=data["song"], rank=data["rank"]), data["url"]
        return m["chart_up"].format(service=svc), m["chart_up_body"].format(song=data["song"], rank=data["rank"], n=data["prev"] - data["rank"]), data["url"]
    if kind == "nominee":
        show = trs(data["show"])
        return m["nominee"].format(show=show), (m["nominee_body"].format(t=data["t"]) if data["t"] else ""), data["url"]
    if kind == "birthday":
        name = data["ko"] if lang == "ko" else data["name"]
        return m["birthday"].format(name=name), m["birthday_body"].format(name=name), data["url"]
    if kind == "video":
        body = data["title"] if not group or len(group) < 2 else m["video_more"].format(title=data["title"], n=len(group) - 1)
        return m["video"], body, data["url"]
    return "A2O SOUL", "", data.get("url")


# 트윗 초안 해시태그 — 공식 계정·유통사(STONE MUSIC)가 쓰는 표기에 맞춤
TAGS = "#A2OSOUL #A2O #에이투오소울 #에투소"
SONG_TAGS = {"Dancing in the Dark": "#Dancing_in_the_Dark", "SUPERSTAR": "#SUPERSTAR"}  # 글에 곡 이름이 있으면
ACTIVE_TAG = "#Dancing_in_the_Dark"  # 지금 활동곡 — 모든 초안에 항상 (활동이 바뀌면 고치기)
ERA_TAGS = "#SUPERSTAR #ZalphaPop"  # 지금 활동(앨범·레이블) — 280자 넘으면 빠짐
# 확실한 정보라 확인 없이 바로 올리는 종류 (일정·생일·조회수처럼 데이터에서 그대로 나오는 것)
AUTO_POST = {"show", "birthday", "views", "subs"}


def x_weight(s):
    """X 글자 수: 링크 23, 한글·한자·이모지 2, 나머지 1 (최대 280)."""
    n = 23 * len(re.findall(r"https?://\S+", s))
    for ch in re.sub(r"https?://\S+", "", s):
        c = ord(ch)
        n += 1 if (c <= 4351 or 8192 <= c <= 8205 or 8208 <= c <= 8223 or 8242 <= c <= 8247) else 2
    return n


def _josa(word, with_final, without_final):
    """한글 받침에 따라 조사 (과/와 등) — 한글이 아니면 받침 없는 쪽"""
    c = ord(word[-1]) if word else 0
    return with_final if 0xAC00 <= c <= 0xD7A3 and (c - 0xAC00) % 28 else without_final


def tweet_text(kind, data):
    """알림 내용 → X 글 초안: 한국어 + 영어 한 줄 + 링크 + 해시태그(그룹·곡·활동·멤버). 280자 넘으면 활동 태그 → 영어 줄 순서로 뺌."""
    en, links, quote = "", [], ""  # quote: 맨 끝에 붙이는 글 주소 → X가 인용으로 보여줌
    site_url = "https://a2osoul-tracker.com/"
    if kind == "media":  # 매체 글은 초안 페이지에서 리트윗 (본문은 미리보기용)
        title, body, url = f"📸 {data['name']} 새 콘텐츠", data["title"], data["url"]
    elif kind == "show" and (data.get("now") or data.get("soon")):  # 방송 5분 전 / 시작 뒤
        mm = re.fullmatch(r"(.+?)\s*출연", data["name"])
        show = mm.group(1) if mm else data["name"]
        show_en = (((data.get("tr") or {}).get(show) or {}).get("en")) or show
        if data.get("soon"):
            title, body = f"⏰ 곧 {show} 생방송!", f"{data['t']} 시작 — A2O SOUL 무대 함께 봐요 💜"
            en = f"⏰ {show_en} starts soon ({data['t']} KST)"
        else:
            title, body = f"🔴 지금 {show} 생방송 중!", "A2O SOUL 무대 같이 봐요 💜"
            en = f"🔴 {show_en} is LIVE now — watch A2O SOUL!"
        url = data["url"]
        site_cheer = "https://a2osoul-tracker.com/#cheer"
        links = [f"📺 생방송 {url}", f"💜 응원법·투표 {site_cheer}"]  # 방송 보기 + 사이트(응원법·투표) 링크 둘 다
    elif kind == "stream":  # 멜론 등 국내 음원 차트라 영어 줄 없음
        when = f"{data['t']}~{data['end']}" if data.get("end") else data["t"]
        if data.get("now"):
            until = f" (~{data['end']})" if data.get("end") else ""
            title, body, url = f"🔴 지금 {data['name']} 진행 중!{until}", "아직 늦지 않았어요, 같이 스밍해요 💜", data["url"]
        else:
            title, body, url = f"📢 오늘 {when} {data['name']}!", "시간 맞춰 같이 스밍해요 💜", data["url"]
        links = [f"🎧 플레이리스트 원클릭 담기 {url}"]
        quote = data.get("post") or ""  # 총공팀 공지는 인용으로
    elif kind == "collab":  # 해외 팬 콜라보 (스테이션헤드 등) — 해외 팬 대상이라 영어 줄 포함
        when = f"{data['t']}~{data['end']}" if data.get("end") else data["t"]
        w = data.get("with") or ""
        w_en = re.sub(r"\s*스테이션$", " station", w)
        ko_w = f"{w}{_josa(w, '과', '와')} " if w else ""
        en_w = f" with {w_en}" if w else ""
        what = data["name"].replace("스테이션헤드", "Stationhead").replace("콜라보", "collab").replace("합동 스밍", "streaming party")
        if data.get("now"):
            until = f" (~{data['end']})" if data.get("end") else ""
            title, body = f"🔴 지금 {ko_w}{data['name']} 진행 중!{until}", "아직 늦지 않았어요, 같이 들어요 💜"
            en = f"🔴 {what}{en_w} is ON now (until {data['end_real']} KST)!"
        else:
            title, body = f"📢 오늘 {when} {ko_w}{data['name']}!", "시간 맞춰 같이 들어요 💜"
            en = f"📢 {what}{en_w} — {when} KST, join us!"
        url = data["post"] or site_url
        links = [f"🎧 참여 {url}"]
    else:
        title, body, url = compose(kind, data, "ko")
        t2, b2, _ = compose(kind, data, "en")
        en = (t2 if b2 == body or not b2 else f"{t2} {b2}").strip() if kind not in ("show",) else ""  # 본문이 원문 그대로면 영어는 제목만
        if kind in ("views", "subs"):
            title = title.replace("🎉 ", "🎉 A2O SOUL ", 1) if "A2O SOUL" not in title else title
    if kind == "birthday":
        body = f"{data['ko']}의 생일을 함께 축하해요 💜 #Happy{data['name'].replace(' ', '')}Day"
    tags = TAGS
    text_all = f"{title} {body} {data.get('name', '')} {data.get('title', '')}"
    song = " ".join(t for k, t in SONG_TAGS.items() if k.lower() in text_all.lower() and t not in ERA_TAGS and t != ACTIVE_TAG)
    mems = data.get("members") or ([(data["name"], data.get("ko"))] if kind == "birthday" else [])
    for m_en, m_ko in mems:  # 멤버 개인 게시글이면 이름 해시태그 (한글·영어)
        tags += f" #{m_ko} #{re.sub(r'[^A-Za-z0-9]', '', m_en)}" if m_ko else f" #{re.sub(r'[^A-Za-z0-9]', '', m_en)}"

    def build(with_en, with_era):
        tag2 = " ".join(x for x in (ACTIVE_TAG, song, ERA_TAGS if with_era else "") if x)
        lines = [title] + ([body] if body else []) + ([en] if with_en and en else []) + [""] + (links or [f"👉 {url}" if url else ""]) + ["", tags, tag2] + ([quote] if quote else [])
        return re.sub(r"\n{3,}", "\n\n", "\n".join(x for x in lines if x is not None)).strip()

    for opt in ((True, True), (True, False), (False, False)):
        out = build(*opt)
        if x_weight(out) <= 280:
            return out
    return out


LIVE_IMG = {"더쇼": "theshow", "쇼챔피언": "showchampion", "엠카운트다운": "mcountdown", "뮤직뱅크": "musicbank", "음악중심": "musiccore", "인기가요": "inkigayo"}


def tweet_image(kind, data, site):
    """트윗에 붙일 사진 (사이트에 있는 것만): 음방 '곧 시작'·'생방송 중' 카드 — site/img/live/<방송>-soon|live.jpg"""
    if kind == "show" and (data.get("soon") or data.get("now")):
        slug = next((v for k, v in LIVE_IMG.items() if k in data.get("name", "")), None)
        if slug:
            return f"{site.rstrip('/')}/img/live/{slug}-{'live' if data.get('now') else 'soon'}.jpg"
    return None


def drafts(api, priv, new, site):
    """새 알림 후보 → 트윗 초안을 Worker에 저장. 저장된 개수를 돌려줌."""
    # 팬 계정이 주최하는 행사(credit 있음)는 초안 안 만듦 — 그쪽 공지를 리트윗하는 게 맞음
    items = [{"key": key, "kind": kind, "text": tweet_text(kind, data), "auto": kind in AUTO_POST, **({"rt": True} if data.get("rt") else {}), **({"post_at": data["post_at"]} if data.get("post_at") else {}),
              **({"image": tweet_image(kind, data, site)} if tweet_image(kind, data, site) else {})}
             for key, topic, kind, data in new
             if kind not in ("notice",) and not data.get("credit") and not data.get("no_draft")]  # 음원 총공(stream)은 초안만 — 공지 링크를 붙여서 만듦
    if not items:
        return 0
    try:
        r = requests.post(api.rstrip("/") + "/tweet/drafts", json={"drafts": items[:20]}, timeout=20,
                          headers={"Authorization": f"Bearer {_admin_token(priv)}"})
        r.raise_for_status()
        j = r.json()
        if j.get("posted"):
            print(f"[트윗] 바로 올림 {j['posted']}개")
        return j.get("added", 0)  # 확인이 필요한(아직 안 올린) 초안 수 — 관리자 알림용
    except Exception as e:  # noqa: BLE001
        print(f"[트윗] 초안 저장 실패: {type(e).__name__} {e}")
        return 0


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
    added = drafts(push["api"], priv, new, site)  # 확인 후 올릴 X 글 초안
    if added:
        print(f"[트윗] 초안 {added}개")
    videos = [c for c in new if c[2] == "video"]
    msgs = [c for c in new if c[2] not in ("video", "media") and not c[3].get("draft_only")] + ([videos[0]] if videos else [])  # media는 초안 전용
    dead, ok = [], 0
    for s in subs:
        if added and "tweet" in (s.get("topics") or []):  # 관리자: 올릴 트윗 초안이 생겼다고 알림
            try:
                webpush(subscription_info=s["sub"], data=json.dumps({"title": f"✍️ 올릴 트윗 초안 {added}개", "body": "눌러서 확인하고 올리기",
                        "url": site + "tweet.html", "tag": "tweet-drafts"}, ensure_ascii=False),
                        vapid_private_key=priv, vapid_claims={"sub": "https://a2osoul-tracker.com"}, ttl=6 * 3600, timeout=15)
            except Exception as e:  # noqa: BLE001
                print(f"[트윗] 관리자 알림 실패: {type(e).__name__}")
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
