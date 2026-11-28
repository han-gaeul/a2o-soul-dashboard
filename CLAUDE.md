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
- 음방 트윗은 생방송 시작 시각에 '지금 생방송 중' 하나만 (5분 전 '곧 시작' 없음). 방송사·매체가 그 시간대에 생방송 글을 올리면 그걸 리트윗하고 우리 글은 취소.
- X 비용: 글 읽기 $0.005, 글 올리기 $0.015, 링크 있는 글 $0.20 — 링크 없어도 되는 글(생일·차트)은 링크 빼기, 공식 글 리트윗으로 대신할 수 있으면 대신.
- 예약 트윗(음방 3시간 전부터, 새 영상·직캠 묶음)은 트윗 페이지 ⏰ 예약됨에 뜸 → 취소 안 하면 그 시각에 올라감. 조회수·구독자·생일·차트는 예약 없이 바로. 공식 글이 나와 리트윗으로 대신하면 수집기가 예약 자동 취소(워커 cancel).
- 자동 업로드: MV 조회수(100만 단위)·구독자 돌파, 생일, 음방 등 데이터로 확실한 것, 음원 차트 매일 9시 요약·새 차트 첫 진입(국내 차트라 한국어만).
- 초안 → 안 보면 자동: 음원 총공은 시작 시각에 '지금 진행 중' 하나만(총공팀 공지 인용, 늦게 알면 10분 뒤). 해외 팬 콜라보(스테이션헤드 등, 한국어+영어)는 시작 전(10분 전)·진행 중(20분 뒤).
- 공식 계정·매체·방송사 계정(targets.yml x_media) + 목록에 없어도 인증 기업·기관 계정(투표 앱·판매처 제외)의 A2O SOUL X 글은 확인 없이 바로 리트윗(3시간 안 글). 음방 검색은 사진·영상(풀캠·직캠) 글 모두.
- 새 영상(MV·무대·콘텐츠): 올라오고 30분 뒤로 예약, 그사이 같은 영상의 공식·매체 X 글이 나오면 예약 취소하고 그 글 리트윗.
- 팬 주최 일정(credit)은 푸시 없음. 리트윗은 '올렸어요' 알림 제외.
- 트윗은 X 가중치 280자 이내(`webpush.x_weight`).
- 사이트 업데이트 공지 초안을 쓸 때는 항상 공지 이미지(1200×675, 바뀐 화면 캡처 포함)도 같이 만들어 보내기.
- 생일·MV 조회수 돌파 트윗엔 이미지(site/img/tw/, `node tools/make_tw_cards.js`로 미리 만듦). 항상 최신 컨셉 포토(멤버 프로필 사진) — 프로필 사진 바꾸면 다시 만들기(health.md에 뜸).
- 같은 채널·같은 무대의 멤버별 직캠·페이스캠이 2개 이상이면 한 글로 묶음(`#멤버: 링크`, 5명씩). 방송사 공식 계정(kpop_sbs 등 targets.yml x_media)이 같은 영상 링크로 묶음 글을 올리면 그걸 자동 리트윗, 마지막 영상 30분 뒤까지 안 올리면 우리 글 업로드. 직캠 1개짜리도 새 영상처럼 30분 예약(그사이 묶음이 되거나 공식 글 나오면 취소).

## 멤버 정보 (members.yml)
- 본명은 멤버가 공식적으로 밝힌 것만(QQ뮤직·쿠거우뮤직 카드·공개 프로필). TMI는 notes에 "QQ뮤직 TMI: …", "쿠거우뮤직: 좋아하는 동물 · 불리고 싶은 별명". 학교·가족·거주지·신체정보·출처 없는 소문 금지.
- 준(JUNE) 포지션은 공식 확인 전까지 비워 둠(빈칸이면 카드에 아무것도 안 나옴).
- 포카(`site/img/photocards/버전_라벨_멤버.webp`): 중복은 판매처 이름이 아니라 **사진으로** 판단(`pc_crop.dhash`, 해밍 120 미만 = 같은 카드). 같은 판매처라도 다른 카드일 수 있음. 손으로 넣거나 지울 때도 사진 비교 먼저.
- 사인: `사인_이름.png`(THE KPOP) + `서명_이름.svg`. 필기체 'Lin' = 준, 사선 사인 = 시원.
