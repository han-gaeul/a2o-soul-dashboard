"""공지 본문 → 일정 후보 (AI 없이 규칙으로).

음방 이름 + 날짜가 같은 줄에 있으면 확신 높음(자동 반영), 애매하면 확신 낮음('확인 필요' 이슈).
결과 형식은 announce.clean()과 같음.
"""
import re
from datetime import date, timedelta

RULES_VERSION = 4  # 규칙을 바꾸면 올리기 → 다음 수집 때 최근 공지를 다시 읽어 일정을 새로 뽑음

SHOWS = [
    ("더쇼", r"더\s?쇼(?!\s?챔)|THE\s?SHOW"),
    ("쇼챔피언", r"쇼\s?챔피언|쇼챔|SHOW\s?CHAMPION"),
    ("엠카운트다운", r"엠카운트다운|엠카|M\s?COUNTDOWN"),
    ("뮤직뱅크", r"뮤직\s?뱅크|뮤뱅|MUSIC\s?BANK"),
    ("음악중심", r"음악\s?중심|음중|MUSIC\s?CORE"),
    ("인기가요", r"인기가요|INKIGAYO"),
    ("SHOW K-POP", r"SHOW\s?K-?POP|쇼\s?케이팝"),
    ("케이팝업 차트쇼", r"케이팝업\s?차트\s?쇼|K-?POP\s?UP\s?CHART\s?SHOW"),
]
# 매주 방송 요일 (월=0) — 사전녹화 날짜에서 방송일 계산
SHOW_WEEKDAY = {"더쇼": 1, "쇼챔피언": 2, "엠카운트다운": 3, "뮤직뱅크": 4, "음악중심": 5, "인기가요": 6}
SHOW_RE = [(name, re.compile(p, re.I)) for name, p in SHOWS]

# 음방 외 공지 — 날짜가 있을 때만 '확인 필요'로
OTHER = [
    ("release", r"발매|RELEASE|컴백|COMEBACK"),
    ("fanmeeting", r"팬\s?미팅|FAN\s?MEETING|FANMEETING|팬콘|FANCON"),
    ("concert", r"콘서트|CONCERT|TOUR|투어"),
    ("ticket", r"티켓|예매|TICKET"),
    ("merch", r"굿즈|MERCH|\bMD\b|팝업|POP-?UP"),
    ("live", r"라이브|LIVE|생방송"),
    ("vote", r"투표|VOTE"),
    ("broadcast", r"출연|방송|ON\s?AIR"),
]
OTHER_RE = [(k, re.compile(p, re.I)) for k, p in OTHER]
RECAP = re.compile(r"감사|고마워|THANK|비하인드|BEHIND|직캠|FANCAM|무대\s?영상|STAGE\s?(VIDEO|CLIP)|다시\s?보기|REPLAY"
                   r"|\[📸\]|\[🔗\]|\d{6}\s*방송|youtu\.?be", re.I)
PRE_REC = re.compile(r"사전\s?녹화|사녹|PRE-?RECORD", re.I)
SOON = re.compile(r"잠시\s?후|곧|오늘|TODAY|TONIGHT", re.I)
APPLY = re.compile(r"신청|응모|링크|LINK", re.I)
DATE_CODE = re.compile(r"(?<!\d)(2[5-9])(0[1-9]|1[0-2])([0-3]\d)(?!\d)")  # 261115
TIME_BARE = re.compile(r"(?<!\d)(\d{1,2})\s*시(?:\s*(\d{1,2})\s*분)?")

DATE_FULL = re.compile(r"(?<!\d)(20\d\d)\s*[./-]\s*(\d{1,2})\s*[./-]\s*(\d{1,2})(?!\d)")
DATE_KO = re.compile(r"(?<!\d)(\d{1,2})\s*월\s*(\d{1,2})\s*일")
DATE_MD = re.compile(r"(?<![\d.:/])(\d{1,2})\s*[./]\s*(\d{1,2})(?![\d:]|\.\d)")
REL = [(re.compile(r"오늘|TODAY|TONIGHT", re.I), 0), (re.compile(r"내일|TOMORROW", re.I), 1)]
TIME_HM = re.compile(r"(오전|오후|AM|PM)?\s*(?<!\d)(\d{1,2}):(\d{2})\s*(AM|PM)?", re.I)
TIME_KO = re.compile(r"(오전|오후)\s*(\d{1,2})\s*시(?:\s*(\d{1,2})\s*분)?")
TIME_EN = re.compile(r"(?<![\d:])(\d{1,2})\s*(AM|PM)\b", re.I)


def _mk(y, m, d):
    try:
        return date(int(y), int(m), int(d))
    except ValueError:
        return None


def _dates(text, posted):
    """줄 안의 날짜들. 연도 없는 날짜는 게시일 기준으로 (한 달 넘게 과거면 다음 해)."""
    out = []
    for m in DATE_FULL.finditer(text):
        out.append(_mk(*m.groups()))
    rest = DATE_FULL.sub(" ", text)
    for m in DATE_CODE.finditer(rest):
        out.append(_mk(2000 + int(m.group(1)), m.group(2), m.group(3)))
    rest = DATE_CODE.sub(" ", rest)
    for rx in (DATE_KO, DATE_MD):
        for m in rx.finditer(rest):
            d = _mk(posted.year, *m.groups())
            if d and d < posted - timedelta(days=30):
                d = _mk(posted.year + 1, *m.groups())
            out.append(d)
        rest = rx.sub(" ", rest)
    return [d for d in out if d]


def _rel(text, posted):
    for rx, add in REL:
        if rx.search(text):
            return posted + timedelta(days=add)
    return None


def _time(text):
    m = TIME_KO.search(text)
    if m:
        h = int(m.group(2)) % 12 + (12 if m.group(1) == "오후" else 0)
        return f"{h:02d}:{int(m.group(3) or 0):02d}"
    m = TIME_HM.search(text)
    if m:
        h, mi = int(m.group(2)), int(m.group(3))
        ampm = (m.group(1) or m.group(4) or "").upper()
        if ampm in ("오후", "PM") and h < 12:
            h += 12
        if ampm in ("오전", "AM") and h == 12:
            h = 0
        if h < 24 and mi < 60:
            return f"{h:02d}:{mi:02d}"
    m = TIME_EN.search(text)
    if m:
        h = int(m.group(1)) % 12 + (12 if m.group(2).upper() == "PM" else 0)
        return f"{h:02d}:00"
    m = TIME_BARE.search(text)
    if m:
        h = int(m.group(1))
        if 1 <= h <= 8:  # 음방은 오후 — '5시 10분' → 17:10
            h += 12
        if h < 24:
            return f"{h:02d}:{int(m.group(2) or 0):02d}"
    return None


def _item(kind, title, d, tm, conf, url=None):
    return {"kind": kind, "title": title, "date": d.isoformat() if d else None, "time": tm, "end_date": None,
            "place": None, "url": url, "confidence": conf}



# ---------- 투표 공지 ----------
VOTE = re.compile(r"투표|VOTE|VOTING", re.I)
VOTE_APPS = [
    ("빅크(BIGC)", r"빅크|BIGC"), ("아이돌챔프(IDOLCHAMP)", r"아이돌\s?챔프|IDOL\s?CHAMP|최애돌"),
    ("엠넷플러스(Mnet Plus)", r"엠넷\s?플러스|MNET\s?PLUS|mnetplus"), ("팬캐스트(FANCAST)", r"팬캐스트|FANCAST"),
    ("뮤니버스(MUNIVERSE)", r"뮤니버스|MUNIVERSE"), ("뮤빗(MUBEAT)", r"뮤빗|MUBEAT"), ("링크(LiNC)", r"\bLiNC\b|링크\s?앱"),
    ("하이어(HIGHER)", r"하이어|HIGHER"), ("유픽(U+PICK)", r"유픽|U\+?\s?PICK"), ("스타플래닛(STARPLANET)", r"스타플래닛|STAR\s?PLANET"),
    ("팬앤스타(FAN N STAR)", r"팬앤스타|FAN\s?N\s?STAR"), ("아이돌플러스(IDOLPLUS)", r"아이돌\s?플러스|IDOL\s?PLUS"),
]
VOTE_APPS_RE = [(n, re.compile(p, re.I)) for n, p in VOTE_APPS]
URL = re.compile(r"https?://[^\s)\]]+")
SKIP_URL = re.compile(r"//(x\.com|twitter\.com|t\.co|www\.instagram\.com|instagram\.com|youtu\.be|www\.youtube\.com|youtube\.com|vm\.tiktok\.com|www\.tiktok\.com)/", re.I)


def _when(text, pday, base=None):
    """'2026년 11월 14일 (토) 12:00' / '11/14 12:00' / '16일 23:59' → (date, 'HH:MM' or None)."""
    ds = _dates(text, pday)
    d = ds[0] if ds else None
    if d is None and base:
        m = re.search(r"(?<!\d)(\d{1,2})\s*일", text)
        if m:
            d = _mk(base.year, base.month, m.group(1))
        elif _time(text):
            d = base
    return d, _time(text)


def vote_items(caption, pday):
    """투표 안내 → [{kind: vote, title, show, app, start, end, url, confidence}]"""
    if not VOTE.search(caption) or PRE_REC.search(caption):
        return []
    lines = [ln.strip() for ln in caption.splitlines() if ln.strip()]
    urls = [u for u in URL.findall(caption) if not SKIP_URL.search(u)]
    url = next((u for ln in lines if re.search(r"투표|vote|링크|link", ln, re.I) for u in URL.findall(ln) if u in urls), urls[0] if urls else None)
    show = next((n for n, rx in SHOW_RE if rx.search(caption)), "")
    app = next((n for n, rx in VOTE_APPS_RE if rx.search(caption)), "")
    kind = "사전투표" if re.search(r"사전\s?투표|PRE-?VOT", caption, re.I) else \
        "생방송 투표" if re.search(r"실시간|생방송|LIVE\s?VOT", caption, re.I) else "투표"
    start = end = None
    for ln in lines:
        if "~" in ln and (_dates(ln, pday) or _time(ln)):
            left, right = ln.split("~", 1)
            sd, st = _when(left, pday)
            ed, et = _when(right, pday, base=sd)
            if sd or ed:
                start = (sd or pday, st or "00:00")
                end = (ed or sd, et or "23:59")
                break
    if not end:
        for ln in lines:
            if re.search(r"마감|까지|END|DEADLINE", ln, re.I) and _dates(ln, pday):
                ed, et = _when(ln, pday)
                end, start = (ed, et or "23:59"), (pday, "00:00")
                break
    title = " ".join(x for x in [show, kind] if x) if show else \
        next((re.sub(r"^\[[^\]]*\]\s*", "", ln) for ln in lines if re.search(r"[가-힣A-Za-z]{2}", re.sub(r"^\[[^\]]*\]", "", ln))), kind)[:60]
    conf = 0.9 if end and url else 0.6
    fmt = lambda x: f"{x[0].isoformat()} {x[1]}" if x and x[0] else None
    return [{"kind": "vote", "title": title, "show": show, "app": app, "date": end[0].isoformat() if end else None,
             "time": end[1] if end else None, "end_date": None, "place": None, "url": url,
             "start": fmt(start), "end": fmt(end), "confidence": conf}]


def _next_weekday(d, wd):
    return d + timedelta(days=(wd - d.weekday()) % 7)


def extract(caption, posted, today):
    """posted: 'YYYY-MM-DD HH:MM' (KST)."""
    caption = caption or ""
    try:
        pday = date.fromisoformat(posted[:10])
    except ValueError:
        return []
    lines = [ln for ln in caption.splitlines() if ln.strip()]
    shows_all = [name for name, rx in SHOW_RE if rx.search(caption)]

    # 0) 투표 안내 (기간·투표 링크)
    votes = vote_items(caption, pday)
    if votes:
        return votes

    # 1) 사전녹화 안내: '261115 SBS 인기가요 사전녹화 참여' → 녹화일 기준 그 주 방송일에 출연
    #    (신청 기간·인원 체크 시간은 방송 시각이 아니라서 무시)
    if PRE_REC.search(caption) and shows_all:
        head = next((ln for ln in lines if PRE_REC.search(ln) or DATE_CODE.search(ln)), "")
        ds = [m for m in DATE_CODE.finditer(caption)]
        rec = _mk(2000 + int(ds[0].group(1)), ds[0].group(2), ds[0].group(3)) if ds else None
        if not rec:
            return []
        items = []
        for name in shows_all[:1]:
            if name in SHOW_WEEKDAY:
                items.append(_item("music_show", f"{name} 출연", _next_weekday(rec, SHOW_WEEKDAY[name]), None, 0.85))
            else:
                items.append(_item("music_show", f"{name} 출연", rec, None, 0.8))
            # 사녹 신청: '신청 기간 : 2026년 11월 13일 (금) PM 9:10 ~ PM 9:20' + 신청 링크
            for ln in lines:
                if re.search(r"신청|응모|APPLY", ln, re.I) and "~" in ln:
                    left, right = ln.split("~", 1)
                    sd, st = _when(left, pday)
                    ed, et = _when(right, pday, base=sd)
                    if sd and st:
                        url = next((u for x in lines if re.search(r"신청|링크|LINK", x, re.I) for u in URL.findall(x)
                                    if not SKIP_URL.search(u)), None)
                        items.append({"kind": "prerec", "title": f"{name} 사전녹화 신청", "show": name, "date": rec.isoformat(),
                                      "time": None, "end_date": None, "place": None, "url": url,
                                      "start": f"{sd.isoformat()} {st}", "end": f"{(ed or sd).isoformat()} {et or st}",
                                      "confidence": 0.9 if url else 0.6})
                    break
        return items if head or items else []

    # 2) 방송 직전·당일 안내: '잠시 후, 5시 10분 뮤직뱅크에 출연합니다'
    if shows_all and SOON.search(caption) and not RECAP.search(caption):
        return [_item("music_show", f"{shows_all[0]} 출연", pday, _time(caption), 0.9)]

    recap = bool(RECAP.search(caption))
    all_dates = sorted(set(_dates(caption, pday)))
    rel_all = _rel(caption, pday)
    items, seen = [], set()

    for ln in lines:
        if APPLY.search(ln) and not any(rx.search(ln) for _, rx in SHOW_RE):
            continue
        shows = [name for name, rx in SHOW_RE if rx.search(ln)]
        if not shows:
            continue
        ds, tm = _dates(ln, pday), _time(ln)
        if ds:
            d, conf = ds[0], 0.9
        elif _rel(ln, pday):
            d, conf = _rel(ln, pday), 0.85
        elif len(all_dates) == 1:
            d, conf = all_dates[0], 0.8
        elif rel_all and not all_dates:
            d, conf = rel_all, 0.8
        else:
            d, conf = None, 0.5
        if recap and (d is None or d <= pday):  # 지난 무대 링크·사진·감사 인사
            continue
        if d is not None and d < pday:
            continue
        if len(shows) > 1 and not ds:
            conf = min(conf, 0.6)
        for name in shows:
            key = (name, d)
            if key not in seen:
                seen.add(key)
                items.append(_item("music_show", f"{name} 출연", d, tm, conf))

    if not items and not recap and all_dates:  # 음방 아닌 공지: 날짜 있는 것만 확인 필요로
        text_lines = [re.sub(r"^\[[^\]]*\]\s*", "", ln).strip() for ln in lines]
        head = next((x for x in text_lines if re.search(r"[가-힣A-Za-z]{2}", x)), "")
        for kind, rx in OTHER_RE:
            if rx.search(caption):
                future = [d for d in all_dates if d.isoformat() >= today]
                if future:
                    items.append(_item(kind, head[:60] or kind, future[0], _time(caption), 0.6))
                break
    return items
