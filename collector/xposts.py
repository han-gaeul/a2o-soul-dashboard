"""X(트위터) API v2 — 공식 계정 최근 게시물 읽기 (앱 전용 Bearer Token, 사용량 과금).

비용 줄이기: 사용자 ID는 한 번만 조회해 저장, 이후엔 since_id로 새 글만, 답글·리트윗 제외.
"""
import os

import requests

API = "https://api.x.com/2"


def enabled():
    return bool(os.environ.get("X_BEARER_TOKEN"))


def _get(path, params=None):
    r = requests.get(f"{API}{path}", params=params, timeout=30,
                     headers={"Authorization": f"Bearer {os.environ['X_BEARER_TOKEN']}"})
    r.raise_for_status()
    return r.json()


def user_id(username):
    return _get(f"/users/by/username/{username}")["data"]["id"]


def fetch_posts(uid, username, since_id=None, first_limit=20):
    """[{id, caption, timestamp, permalink}] (최신순). 처음엔 최근 first_limit개만, 이후엔 since_id 이후 새 글 전부."""
    params = {"exclude": "replies,retweets", "tweet.fields": "created_at,note_tweet,entities"}
    if since_id:
        params.update(since_id=since_id, max_results=100)
    else:
        params["max_results"] = max(5, min(100, first_limit))
    out = []
    for t in _get(f"/users/{uid}/tweets", params).get("data", []):
        text = (t.get("note_tweet") or {}).get("text") or t.get("text") or ""
        for u in (t.get("entities") or {}).get("urls", []):  # t.co → 실제 주소
            if u.get("url") and u.get("expanded_url"):
                text = text.replace(u["url"], u["expanded_url"])
        out.append({"id": f"x:{t['id']}", "tweet_id": t["id"], "caption": text, "timestamp": t.get("created_at"),
                    "permalink": f"https://x.com/{username}/status/{t['id']}"})
    return out


def search_posts(query, since_id=None, max_results=50):
    """최근 7일 검색 → [{id, tweet_id, caption, timestamp, permalink, author}] (최신순). since_id로 새 글만."""
    params = {"query": query, "max_results": max(10, min(100, max_results)),
              "tweet.fields": "created_at,note_tweet,entities,author_id", "expansions": "author_id", "user.fields": "username"}
    if since_id:
        params["since_id"] = since_id
    res = _get("/tweets/search/recent", params)
    users = {u["id"]: u["username"] for u in (res.get("includes") or {}).get("users", [])}
    out = []
    for t in res.get("data", []):
        text = (t.get("note_tweet") or {}).get("text") or t.get("text") or ""
        for u in (t.get("entities") or {}).get("urls", []):
            if u.get("url") and u.get("expanded_url"):
                text = text.replace(u["url"], u["expanded_url"])
        name = users.get(t.get("author_id"), "i")
        out.append({"id": f"xv:{t['id']}", "tweet_id": t["id"], "caption": text, "timestamp": t.get("created_at"),
                    "permalink": f"https://x.com/{name}/status/{t['id']}", "author": name})
    return out
