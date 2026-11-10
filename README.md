# A2O SOUL Tracker

A2O SOUL 공식 유튜브 지표를 하루 2번 모아 보여주는 비공식 팬메이드 대시보드.
GitHub Actions가 수집하고 GitHub Pages로 배포합니다. 서버 없음.

## 처음 한 번 설정

1. **Settings → Secrets and variables → Actions → New repository secret**
   - `YOUTUBE_API_KEY` (필수)
   - `IG_USER_ID`, `IG_ACCESS_TOKEN` (선택 — 인스타 팔로워 수집용)
2. **Settings → Pages → Build and deployment → Source: GitHub Actions**
3. **Actions → Update dashboard → Run workflow** 로 첫 수집

이후로는 KST 0시·12시경 자동 수집 후 배포됩니다.

## 추적 대상 관리 — `targets.yml`

- 공식 채널 업로드는 자동 등록. 공용 채널(@A2OWORLD)은 `filter: soul`로 SOUL 관련 영상만
- 자동 분류: 60초 이하 → 콘텐츠(쇼츠), 제목에 MV/M/V/Music Video → MV, 티저·나머지 → 콘텐츠
- 분류가 틀렸거나 직캠을 추가하려면 `videos:`에 영상 ID로 적기

```yaml
videos:
  - id: XXXXXXXXXXX      # 쇼츠인데 MV로 잡힌 영상
    category: content
  - id: YYYYYYYYYYY      # 음방 직캠
    category: fancam
    member: MOON
  - id: ZZZZZZZZZZZ      # 빼고 싶은 영상
    active: false
```

GitHub 웹에서 이 파일을 편집해 커밋하면 1~2분 뒤 사이트에 반영됩니다(수집 없이 다시 빌드).
새로 추가한 직캠의 조회수는 다음 자동 수집 때부터 잡혀요. 바로 보고 싶으면 Run workflow.

## 로컬에서 돌려보기

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
YOUTUBE_API_KEY=키 python collector/collect.py
python -m http.server 8000
```

브라우저에서 `http://127.0.0.1:8000/site/` (파일을 직접 열면 데이터를 못 불러와요).
로컬 수집 결과(`data/`)는 커밋하지 말고 버리세요: `git checkout data`

## 구조

```
targets.yml              추적 대상·분류 설정
collector/collect.py     수집(--build: 집계만)
collector/youtube.py     YouTube Data API
collector/instagram.py   Instagram Business Discovery
data/                    registry.json, history.json, dashboard.json (Actions가 커밋)
site/                    정적 대시보드 (index.html, app.js, style.css)
.github/workflows/       수집·배포 워크플로
```
