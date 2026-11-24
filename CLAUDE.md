# CLAUDE.md — A2O SOUL Tracker (a2osoul-tracker.com)

A2O SOUL 팬 정보 사이트. 운영자 1명(가을)이 Claude와 함께 만든다. 이 파일은 새 대화가 바로 이어서 일할 수 있게 쓰는 작업 규칙.

## 대화 규칙
- 답은 항상 한국어 존댓말, 짧고 바로 행동. 영어는 남에게 보낼 초안 안에서만.
- 디자인(화면 모양)을 바꾸기 전엔 미리보기 스크린샷 먼저 보여 주기.
- 요청하지 않은 내용은 마음대로 고치지 않기. 애매하면 물어보기.
- 공식 출처(소속사·방송사·공식 계정) 우선, 팬 계정 정보는 출처 표기. 지어내지 않기(모르면 비워 두기).
- 소속사 비판에 동조하지 않기. 초안에서 @A2O_SOUL 태그 금지.
- 비밀번호 입력·결제·토큰 붙여넣기는 운영자가 직접.
- 문구를 새로 넣으면 translations.yml 번역(en·ja·zh·es·id·th·pt)까지 같이 넣기.

## 구조
- `collector/collect.py` — 수집·빌드 본체. `data/dashboard.json`을 만들고 사이트(`site/`)가 읽음.
  - 개별 수집기: youtube, xposts(X API, 비용 주의), instagram, radio(KBS·SBS·MBC·CBS 선곡표), kcharts(멜론·지니·벅스·FLO·써클), spotify, faces(공식 사진 얼굴 인식), sales, photocards 등.
  - `webpush.py` — 푸시 알림 + 트윗 초안/자동 업로드 후보(candidates → tweet_text).
- 설정 YAML: `members.yml`(멤버), `schedule.yml`, `votes.yml`, `info.yml`, `howto.yml`, `support.yml`, `targets.yml`(영상 분류 지정), `charts.yml`, `translations.yml`.
- `site/` — GitHub Pages 정적 사이트(app.js, i18n.js 9개 언어, style.css, tweet.html = 운영자용 트윗 초안 페이지, privacy.html).
- `push-worker/worker.js` — Cloudflare Worker `a2o-push` (push.a2osoul-tracker.com): 웹푸시 구독, 트윗 올리기/예약, 기기 수 집계(D1), 매분 cron → 10분마다 update.yml 실행. **운영자가 worker.js를 Cloudflare에 직접 붙여넣어 배포** — 바꾸면 파일을 보내고 배포 요청.
- `.github/workflows/update.yml` — 수집 실행(워커가 10분마다 dispatch, 예비 cron 매시 7분). 봇 커밋이 계속 쌓이는 게 정상.

## 작업 흐름
- main에서 브랜치 → 커밋(작성자 han-gaeul, 기존 커밋과 같은 이름·메일) → `gh api`로 PR 생성 → 바로 merge.
  - 연달아 고칠 땐 PR 하나에 모으기.
  - 머지 직후 수동 dispatch 하지 않기(10분 안에 자동 반영).
  - 봇 커밋(github-actions) 때문에 'Unverified' 경고가 떠도 이력 고쳐 쓰지 않기.
- 빌드 확인: `python3 collector/collect.py --build` 후 `git checkout -q data && rm -f data/health.md`.
- 미리보기: `site/` + `data/dashboard.json`을 임시 폴더에 복사 → `python3 -m http.server` → Playwright 스크린샷.
- 이 컨테이너에서 막힌 사이트(트위터 이미지, 국내 음원 사이트 등)는 임시 브랜치에 push 트리거 워크플로를 올려 Actions에서 받기 → 끝나면 워크플로 파일 지우고 머지.
- 한글 파일 이름은 NFC/NFD가 섞여 있음 — 비교할 땐 `unicodedata.normalize('NFC', ...)`.

## 트윗·알림 규칙 (@A2OSOUL_Tracker)
- 바로 자동 업로드: MV 조회수(100만 단위)·구독자 돌파, 생일, 음방 등 데이터로 확실한 것, 음원 차트 매일 9시 요약·새 차트 첫 진입(국내 차트라 한국어만).
- 초안 → 안 보면 자동(시작 전: 시작 10분 전 / 진행 중: 20분 뒤): 음원 총공(총공팀 공지, 공지 링크는 맨 끝에 붙여 인용), 해외 팬 콜라보(스테이션헤드 등, 한국어+영어).
- 팬 주최 일정(credit)은 푸시 없음. 리트윗은 '올렸어요' 알림 제외.
- 트윗은 X 가중치 280자 이내(`webpush.x_weight`).

## 멤버 정보 (members.yml)
- 본명은 멤버가 공식적으로 밝힌 것만(QQ뮤직 카드·공개 프로필). 학교·가족·거주지·신체정보·출처 없는 소문 금지.
- 준(JUNE) 포지션은 공식 확인 전까지 비워 둠(빈칸이면 카드에 아무것도 안 나옴).
- 사인: `사인_이름.png`(THE KPOP) + `서명_이름.svg`. 필기체 'Lin' = 준, 사선 사인 = 시원.
