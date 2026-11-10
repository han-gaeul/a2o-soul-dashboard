# A2O SOUL Tracker

A2O SOUL 유튜브 지표·직캠·일정을 하루 2번 모아 보여주는 비공식 팬메이드 대시보드.
GitHub Actions가 수집하고 GitHub Pages로 배포합니다. 서버 없음.

**사이트**: https://han-gaeul.github.io/a2o-soul-dashboard/

## 기능

- **한눈에**: 구독자·MV·직캠 총 조회수, 다가오는 일정, 최신 영상, 구독자 추이
- **MV**: 순위와 다음 목표 돌파 예상(최근 7일 평균 증가량 기준), 누적·일일 증가량 차트
- **멤버·직캠**: 15명 멤버 카드(국적, 직캠 수·조회수, 대표 직캠), 멤버별 직캠 순위, 직캠 TOP 30
- **알림**: 새 영상(72시간 이내 업로드), MV·직캠 조회수 돌파, 구독자 10만 단위 돌파 → 디스코드/텔레그램

## 처음 한 번 설정

1. **Settings → Secrets and variables → Actions → New repository secret**
   - `YOUTUBE_API_KEY` (필수)
   - `DISCORD_WEBHOOK_URL` (선택) — 디스코드 채널 설정 → 연동 → 웹후크 → URL 복사
   - `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (선택) — @BotFather로 봇 생성, 채널에 봇을 관리자로 추가, chat id는 `@채널이름`
   - `IG_USER_ID`, `IG_ACCESS_TOKEN` (선택) — 인스타 팔로워 수집용
2. **Settings → Pages → Source: GitHub Actions**
3. **Actions → Update dashboard → Run workflow** 로 첫 수집

이후로는 KST 0시·12시경 자동 수집 후 배포됩니다.

## 관리하는 파일

GitHub 웹에서 편집해 커밋하면 1~2분 뒤 사이트에 반영돼요(수집 없이 다시 빌드).

### `schedule.yml` — 일정

```yaml
events:
  - date: 2026-11-13
    time: "17:00"
    type: 음방          # 음방 | 라이브 | 발매 | 행사 | 기타
    title: 뮤직뱅크 출연
    url: https://...    # 선택
```

지난 일정은 자동으로 숨겨져요.

### `targets.yml` — 추적 대상

- 공식 채널(@A2OSOUL) 업로드는 전부, 공용 채널(@A2OWORLD)은 `filter: soul`, 음방 채널은 `filter: group`으로 A2O SOUL 영상만 자동 등록
- 데뷔 전 영상도 포함. 처음엔 채널 업로드 전체를 훑고, 이후엔 새 업로드만 확인
- 멤버 이름은 영문(대소문자 무관)·한글 표기 모두 인식
- 필터나 `members.yml` 표기가 바뀌면 다음 수집 때 해당 채널을 자동으로 처음부터 다시 확인
- 소속사 채널(`filter: soul`)은 데뷔 전 연습생 유닛(LTB·HTB)과 SOULITE 영상도 포함
- 자동 분류: 제목에 직캠/FanCam/Focus → 직캠(제목에 멤버 이름이 하나면 그 멤버), 60초 이하 → 콘텐츠(쇼츠), MV/M/V/Music Video → MV, 티저·나머지 → 콘텐츠
- 분류가 틀렸거나 다른 채널 영상을 추가하려면 `videos:`에 영상 ID로

```yaml
videos:
  - id: XXXXXXXXXXX      # 분류 덮어쓰기
    category: content
  - id: YYYYYYYYYYY      # 멤버 지정
    category: fancam
    member: MOON
  - id: ZZZZZZZZZZZ      # 빼기
    active: false
```

### `members.yml` — 멤버

제목에서 멤버를 찾을 때 쓰는 표기. 한글 등 다른 표기는 `aliases`에 추가.

## 로컬에서 돌려보기

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
YOUTUBE_API_KEY=키 python collector/collect.py
python -m http.server 8000
```

브라우저에서 `http://127.0.0.1:8000/site/` (파일을 직접 열면 데이터를 못 불러와요).
로컬 수집 결과는 커밋하지 말고 되돌리세요: `git checkout data`

## 구조

```
targets.yml / schedule.yml / members.yml   설정
collector/collect.py     수집·알림·집계 (--build: 집계만)
collector/youtube.py     YouTube Data API
collector/notify.py      디스코드·텔레그램 알림
collector/instagram.py   Instagram Business Discovery
data/                    registry.json, history.json, dashboard.json (Actions가 커밋)
site/                    정적 대시보드
.github/workflows/       수집·배포 워크플로
```
