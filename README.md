# A2O SOUL Tracker

A2O SOUL 유튜브·인스타 공식 지표를 매일 수집해 추이를 보여주는 팬 대시보드.

## 로컬 실행

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # 키 채우기
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver  # http://127.0.0.1:8000
```

## 추적 대상 등록

```bash
# 공식 유튜브 채널 — 등록해두면 collect 때 업로드 영상(MV·티저·콘텐츠)을 자동 등록
python manage.py track channel UCAdLPETtxpZeRVqsq_QTneA   # @A2OSOUL
# 소속사 공용 채널 — 그룹명이나 멤버 이름(대문자)이 제목에 있는 영상만 등록 (구독자 KPI에서는 제외)
python manage.py track channel UCn-SYb1TUz-1itK_uz4imUA --filter soul   # @A2OWORLD
# @핸들/URL도 가능 (API 키 필요)
python manage.py track channel https://www.youtube.com/@A2OSOUL

# 공식 인스타
python manage.py track ig a2o.soul

# MV (URL 그대로 넣어도 됨)
python manage.py track video https://youtu.be/XXXXXXXXXXX --category mv

# 멤버 직캠
python manage.py track video https://youtu.be/YYYYYYYYYYY --category fancam --member MOON
```

공식 채널 영상은 제목으로 분류를 추정해요(`MV`/`M/V` → mv, 티저 등 → content). 틀리면 `/admin`에서 바꾸면 되고, 직캠은 음방 채널 영상이라 `track`으로 직접 등록합니다. 영상 제목·업로드일은 첫 수집 때 자동으로 채워집니다. `/admin`에서도 추가·수정 가능.

## 수집

```bash
python manage.py collect
```

같은 날 여러 번 돌려도 그래프는 날짜별 마지막 값만 씁니다.

## API 준비

- **YouTube**: Google Cloud에서 YouTube Data API v3 활성화 → API 키 발급. 일일 기본 쿼터 10,000유닛, 이 앱은 영상 50개당 1유닛이라 넉넉함.
- **Instagram**: Meta 개발자 앱(개인용) + 본인 IG 비즈니스/크리에이터 계정 연결 → `IG_USER_ID`, 장기 액세스 토큰. Business Discovery로 @a2o.soul 팔로워 조회.

## Railway 배포

1. 레포 연결 → Postgres 플러그인 추가 (`DATABASE_URL` 자동 주입)
2. 환경변수: `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=0`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`, API 키들
3. 수집용 Cron 서비스를 같은 레포로 하나 더 만들고 Start Command `python manage.py collect`, 스케줄 예: `0 3,15 * * *` (UTC 기준 = KST 0시·12시)

## 구조

```
config/                 Django 설정
tracker/
  models.py             Target(추적 대상), Snapshot(시점별 지표)
  collectors/           youtube.py, instagram.py
  management/commands/  collect.py(수집), track.py(대상 등록)
  views.py              대시보드 집계
  templates/tracker/    dashboard.html (Chart.js)
```
