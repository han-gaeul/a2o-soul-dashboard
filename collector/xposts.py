"""X(트위터) API v2 — 공식 계정 최근 게시물 읽기 (앱 전용 Bearer Token, 사용량 과금).

비용 줄이기: 사용자 ID는 한 번만 조회해 저장, 이후엔 since_id로 새 글만, 답글·리트윗 제외.
"""
import atexit
import os

import requests

API = "https://api.x.com/2"
# 이번 실행의 X 사용량 (추정용): 읽은 글 수(글당 $0.005)·사용자 조회(건당 $0.01)·402(크레딧 부족) 여부
USAGE = {"reads": 0, "users": 0, "err402": 0}


def enabled():
    return bool(os.environ.get("X_BEARER_TOKEN"))


def _get(path, params=None):
    r = requests.get(f"{API}{path}", params=params, timeout=30,
                     headers={"Authorization": f"Bearer {os.environ['X_BEARER_TOKEN']}"})
    if r.status_code == 402:
        USAGE["err402"] += 1
    r.raise_for_status()
    j = r.json()
    if path.startswith("/users/by/"):
        USAGE["users"] += 1
    else:
        d = j.get("data")
        USAGE["reads"] += len(d) if isinstance(d, list) else (1 if d else 0)
    return j


@atexit.register
def _report():
    """실행이 끝나면 사용량을 워커에 보냄 (초안 페이지에서만 보임). 크레딧이 처음 바닥나면 관리자 기기에 푸시."""
    if not (USAGE["reads"] or USAGE["users"] or USAGE["err402"]):
        return
    priv = os.environ.get("VAPID_PRIVATE_KEY")
    if not priv:
        return
    try:
        import webpush
        api = "https://push.a2osoul-tracker.com"
        r = requests.post(api + "/tweet/xstat", json=USAGE, timeout=15,
                          headers={"Authorization": f"Bearer {webpush._admin_token(priv)}"})
        r.raise_for_status()
        if r.json().get("alert"):  # 오늘 처음 402 → 관리자에게 알림
            webpush.alert_admin(api, priv, "⚠️ X 크레딧 부족", "수집·자동 글이 멈췄어요 — console.x.com에서 충전해 주세요")
        print(f"[X] 사용량 기록: 글 {USAGE['reads']} · 사용자 조회 {USAGE['users']}" + (f" · 402 {USAGE['err402']}" if USAGE["err402"] else ""))
    except Exception as e:  # noqa: BLE001
        print(f"[X] 사용량 기록 실패: {type(e).__name__} {e}")


def user_id(username):
    return _get(f"/users/by/username/{username}")["data"]["id"]


def fetch_posts(uid, username, since_id=None, first_limit=20, exclude="replies,retweets"):
    """[{id, caption, timestamp, permalink}] (최신순). 처음엔 최근 first_limit개만, 이후엔 since_id 이후 새 글 전부."""
    params = {"exclude": exclude, "tweet.fields": "created_at,note_tweet,entities,attachments",
              "expansions": "attachments.media_keys", "media.fields": "type,url,preview_image_url"}
    if since_id:
        params.update(since_id=since_id, max_results=100)
    else:
        params["max_results"] = max(5, min(100, first_limit))
    out = []
    res = _get(f"/users/{uid}/tweets", params)
    media = {m["media_key"]: m for m in (res.get("includes") or {}).get("media", [])}
    for t in res.get("data", []):
        text = (t.get("note_tweet") or {}).get("text") or t.get("text") or ""
        for u in (t.get("entities") or {}).get("urls", []):  # t.co → 실제 주소
            if u.get("url") and u.get("expanded_url"):
                text = text.replace(u["url"], u["expanded_url"])
        imgs = [media[k].get("url") or media[k].get("preview_image_url")
                for k in (t.get("attachments") or {}).get("media_keys", []) if k in media and media[k].get("type") == "photo"]
        out.append({"id": f"x:{t['id']}", "tweet_id": t["id"], "caption": text, "timestamp": t.get("created_at"),
                    "permalink": f"https://x.com/{username}/status/{t['id']}", "images": [u for u in imgs if u]})
    return out


def fetch_photo_posts(uid, username, pages=5):
    """사진 모음용: 예전 글까지 넘겨 보며 사진이 있는 글만 [{id, caption, timestamp, permalink, images}] (최대 pages×100개 읽음)."""
    params = {"exclude": "replies,retweets", "max_results": 100, "tweet.fields": "created_at,note_tweet,attachments",
              "expansions": "attachments.media_keys", "media.fields": "type,url"}
    out, token = [], None
    for _ in range(pages):
        if token:
            params["pagination_token"] = token
        res = _get(f"/users/{uid}/tweets", params)
        media = {m["media_key"]: m for m in (res.get("includes") or {}).get("media", [])}
        for t in res.get("data", []):
            imgs = [media[k]["url"] for k in (t.get("attachments") or {}).get("media_keys", [])
                    if k in media and media[k].get("type") == "photo" and media[k].get("url")]
            if imgs:
                text = (t.get("note_tweet") or {}).get("text") or t.get("text") or ""
                out.append({"id": f"x:{t['id']}", "caption": text[:400], "timestamp": t.get("created_at"),
                            "permalink": f"https://x.com/{username}/status/{t['id']}", "images": imgs[:4]})
        token = (res.get("meta") or {}).get("next_token")
        if not token:
            break
    return out


def users_exist(usernames):
    """핸들 목록 → {소문자 핸들: True/False} (없거나 정지된 계정은 False). 100개씩 한 번에."""
    out = {}
    names = [u for u in usernames if u]
    for i in range(0, len(names), 100):
        chunk = names[i:i + 100]
        res = _get("/users/by", {"usernames": ",".join(chunk)})
        found = {u["username"].lower() for u in res.get("data", [])}
        out.update({u.lower(): u.lower() in found for u in chunk})
    return out


def search_posts(query, since_id=None, max_results=50, pages=1, media=False):
    """최근 7일 검색 → [{id, tweet_id, caption, timestamp, permalink, author}] (최신순). since_id로 새 글만.
    pages: 결과가 많으면 다음 쪽까지 (쪽마다 max_results개 읽음 → 과금). media: 사진·영상 썸네일도 (images)."""
    params = {"query": query, "max_results": max(10, min(100, max_results)),
              "tweet.fields": "created_at,note_tweet,entities,author_id", "expansions": "author_id", "user.fields": "username,verified_type,name"}
    if media:
        params.update({"tweet.fields": params["tweet.fields"] + ",attachments",
                       "expansions": "author_id,attachments.media_keys", "media.fields": "type,url,preview_image_url"})
    if since_id:
        params["since_id"] = since_id
    out = []
    for _ in range(max(1, pages)):
        res = _get("/tweets/search/recent", params)
        out += _search_page(res)
        token = (res.get("meta") or {}).get("next_token")
        if not token:
            break
        params["next_token"] = token
    return out


def _search_page(res):
    people = {u["id"]: u for u in (res.get("includes") or {}).get("users", [])}
    media = {m["media_key"]: m for m in (res.get("includes") or {}).get("media", [])}
    users = {k: u["username"] for k, u in people.items()}
    out = []
    for t in res.get("data", []):
        text = (t.get("note_tweet") or {}).get("text") or t.get("text") or ""
        for u in (t.get("entities") or {}).get("urls", []):
            if u.get("url") and u.get("expanded_url"):
                text = text.replace(u["url"], u["expanded_url"])
        name = users.get(t.get("author_id"), "i")
        out.append({"id": f"xv:{t['id']}", "tweet_id": t["id"], "caption": text, "timestamp": t.get("created_at"),
                    "permalink": f"https://x.com/{name}/status/{t['id']}", "author": name,
                    "verified_type": (people.get(t.get("author_id")) or {}).get("verified_type"),
                    "author_name": (people.get(t.get("author_id")) or {}).get("name"),
                    "images": [u for u in (media[k].get("url") or media[k].get("preview_image_url")
                                           for k in (t.get("attachments") or {}).get("media_keys", []) if k in media) if u][:4],
                    "video": any(media[k].get("type") in ("video", "animated_gif")
                                 for k in (t.get("attachments") or {}).get("media_keys", []) if k in media)})
    return out
