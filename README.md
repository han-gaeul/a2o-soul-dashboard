# A2O SOUL Tracker

A2O SOUL 유튜브 지표·직캠·일정을 하루 2번 모아 보여주는 비공식 팬메이드 대시보드.
GitHub Actions가 수집하고 GitHub Pages로 배포합니다. 서버 없음.

**사이트**: https://han-gaeul.github.io/a2o-soul-dashboard/

## 기능

- **한눈에**: 구독자·MV·직캠 총 조회수, 다가오는 일정, 최신 영상, 구독자 추이
- **MV**: 순위와 다음 목표 돌파 예상(최근 7일 평균 증가량 기준), 누적·일일 증가량 차트
- **멤버·직캠**: 15명 멤버 카드(국적, 직캠 수·조회수, 대표 직캠), 멤버별 직캠 순위, 직캠 TOP 30
- **공식 인스타**: 새 글 피드(본문·링크, 이미지 없음), 멤버 이름이 나온 게시물은 멤버 창에, 최근 게시물 평균 좋아요·댓글 추이
- **알림**: 새 영상(72시간 이내 업로드), MV·직캠 조회수 돌파, 구독자 10만 단위 돌파 → 디스코드/텔레그램

## 앱으로 쓰기 (PWA)

사이트를 홈 화면에 설치하면 주소창 없이 앱처럼 열리고, 오프라인에서도 마지막 데이터를 볼 수 있어요.

- **안드로이드(크롬)**: 사이트 오른쪽 위 **앱 설치** 버튼 또는 메뉴 → 앱 설치
- **아이폰(Safari)**: **앱 설치** 버튼 → 안내대로 공유 → 홈 화면에 추가

`site/manifest.webmanifest`(앱 이름·아이콘·색), `site/sw.js`(캐시), `site/icons/`

## 처음 한 번 설정

1. **Settings → Secrets and variables → Actions → New repository secret**
   - `YOUTUBE_API_KEY` (필수)
   - `DISCORD_WEBHOOK_URL` (선택) — 디스코드 채널 설정 → 연동 → 웹후크 → URL 복사
   - `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (선택) — @BotFather로 봇 생성, 채널에 봇을 관리자로 추가, chat id는 `@채널이름`
   - `IG_USER_ID`, `IG_ACCESS_TOKEN` (선택) — 인스타 팔로워 수집용
2. **Settings → Pages → Source: GitHub Actions**
3. **Actions → Update dashboard → Run workflow** 로 첫 수집

이후로는 KST 0시·12시경 자동 수집 후 배포됩니다.

## 자동 수집

- **공식 유튜브**: 영상·조회수, 예정된 라이브·프리미어 시작 시각 → 다가오는 일정
- **공식 인스타(@a2o.soul)·공식 X**: 새 게시물 본문에서 음방·발매·팬미팅·티켓·굿즈 일정을 뽑아 정리
  - 기본은 규칙 방식: 음방 이름 + 날짜가 같은 줄에 있으면 자동 반영, 애매하면 확인 필요로
  - `ANTHROPIC_API_KEY`가 있으면 AI(Claude)가 읽어서 정리 (확신도 80% 이상 자동 반영)
  - 자동 반영 → 사이트·캘린더 '다가오는 일정'(응원 탭 '공식 공지'), 그 밖 → GitHub 이슈 **'자동 수집 확인 필요'**. 맞으면 `schedule.yml`에 옮겨 적기
- 필요한 시크릿: 인스타 `IG_USER_ID`, `IG_ACCESS_TOKEN`(만료 없는 페이지 토큰) / X `X_BEARER_TOKEN` + `targets.yml`의 `x:`에 핸들 / AI `ANTHROPIC_API_KEY`(선택)
- X는 읽은 게시물 수만큼 과금돼요. 처음엔 최근 20개, 이후엔 새 글만 읽어요(답글·리트윗 제외)
- 투표 일정·음원 차트는 공식 계정에 안 올라오거나 자동 수집이 막혀 있어서 직접 입력

## 관리하는 파일

| 파일 | 내용 |
|---|---|
| `schedule.yml` | 일정 (음방·라이브·발매 등) |
| `votes.yml` | 음방 투표(시작·마감), 스밍 리스트 |
| `charts.yml` | 음원 차트 순위 기록 (멜론·지니는 자동 수집 불가라 직접 입력) |
| `support.yml` | 생일 카페·서포트 |
| `guide.yml` | 입덕 가이드 입문 코스, 멤버 구분 팁 |
| `howto.yml` | 스밍·투표 방법 (음방별 투표 앱, 스밍 요령) |
| `info.yml` | 세계관, 앨범(수록곡·버전·링크), 티켓·굿즈 공식 판매처 |
| `members.yml` | 멤버 프로필·생일·사진 |
| `targets.yml` | 수집 채널, 시리즈 분류, 의견 보내기 링크(`feedback_url`) |

일정·생일·투표 마감·서포트는 `data/calendar.ics`로도 만들어져서 응원 탭의 **캘린더 구독**으로 휴대폰 캘린더에 넣을 수 있어요.
화면 문구는 `site/i18n.js`에서 한국어·영어·일본어·중국어·스페인어·인도네시아어로 번역돼요 (데이터 내용은 원문).

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
collector/xposts.py      X API v2 (공식 계정 게시물)
collector/rules.py       공지 본문 → 일정 후보 (규칙)
collector/announce.py    공지 본문 → 일정 후보 (AI, 선택)
data/                    registry.json, history.json, dashboard.json (Actions가 커밋)
site/                    정적 대시보드
.github/workflows/       수집·배포 워크플로
```
