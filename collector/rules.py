"""공지 본문 → 일정 후보 (AI 없이 규칙으로).

음방 이름 + 날짜가 같은 줄에 있으면 확신 높음(자동 반영), 애매하면 확신 낮음('확인 필요' 이슈).
결과 형식은 announce.clean()과 같음.
"""
import re
from datetime import date, timedelta

SHOWS = [
    ("더쇼", r"더\s?쇼|THE\s?SHOW"),
    ("쇼챔피언", r"쇼\s?챔피언|쇼챔|SHOW\s?CHAMPION"),
    ("엠카운트다운", r"엠카운트다운|엠카|M\s?COUNTDOWN"),
    ("뮤직뱅크", r"뮤직\s?뱅크|뮤뱅|MUSIC\s?BANK"),
    ("음악중심", r"음악\s?중심|음중|MUSIC\s?CORE"),
    ("인기가요", r"인기가요|INKIGAYO"),
]
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
RECAP = re.compile(r"감사|고마워|THANK|비하인드|BEHIND|직캠|FANCAM|무대\s?영상|STAGE\s?(VIDEO|CLIP)|다시\s?보기|REPLAY", re.I)

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
    return None


def _item(kind, title, d, tm, conf, url=None):
    return {"kind": kind, "title": title, "date": d.isoformat() if d else None, "time": tm, "end_date": None,
            "place": None, "url": url, "confidence": conf}


def extract(caption, posted, today):
    """posted: 'YYYY-MM-DD HH:MM' (KST)."""
    caption = caption or ""
    try:
        pday = date.fromisoformat(posted[:10])
    except ValueError:
        return []
    recap = bool(RECAP.search(caption))
    lines = [ln for ln in caption.splitlines() if ln.strip()]
    all_dates = sorted(set(_dates(caption, pday)))
    rel_all = _rel(caption, pday)
    items, seen = [], set()

    for ln in lines:
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
        if recap and (d is None or d <= pday):  # "오늘 뮤직뱅크 감사합니다" 같은 회고 글
            continue
        if len(shows) > 1 and not ds:  # 한 줄에 여러 음방인데 날짜가 줄에 없으면 애매
            conf = min(conf, 0.6)
        if tm is None and len(lines) > 1 and len([ln2 for ln2 in lines if any(rx.search(ln2) for _, rx in SHOW_RE)]) == 1:
            tm = _time(caption)
        for name in shows:
            key = (name, d)
            if key not in seen:
                seen.add(key)
                items.append(_item("music_show", f"{name} 출연", d, tm, conf))

    if not items and not recap and all_dates:  # 음방 아닌 공지: 날짜 있는 것만 확인 필요로
        head = re.sub(r"\s+", " ", lines[0]).strip("[]【】 ") if lines else ""
        for kind, rx in OTHER_RE:
            if rx.search(caption):
                future = [d for d in all_dates if d.isoformat() >= today]
                if future:
                    items.append(_item(kind, head[:60] or kind, future[0], _time(caption), 0.6))
                break
    return items
