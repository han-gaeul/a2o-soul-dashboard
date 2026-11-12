"""Instagram Graph API — Business Discovery (본인 IG 비즈니스 계정 토큰으로 공개 계정 조회)."""
import os

import requests


def enabled():
    return bool(os.environ.get("IG_USER_ID") and os.environ.get("IG_ACCESS_TOKEN"))


def fetch_account(username):
    ver = os.environ.get("GRAPH_API_VERSION", "v21.0")
    url = f"https://graph.facebook.com/{ver}/{os.environ['IG_USER_ID']}"
    fields = f"business_discovery.username({username}){{followers_count,media_count,name}}"
    r = requests.get(url, params={"fields": fields, "access_token": os.environ["IG_ACCESS_TOKEN"]}, timeout=20)
    r.raise_for_status()
    bd = r.json()["business_discovery"]
    return {"name": bd.get("name") or username, "followers": bd.get("followers_count"), "media_count": bd.get("media_count")}


def fetch_media(username, limit=25):
    """공개 계정의 최근 게시물 [{id, caption, timestamp, permalink, media_type}] (최신순)."""
    ver = os.environ.get("GRAPH_API_VERSION", "v21.0")
    url = f"https://graph.facebook.com/{ver}/{os.environ['IG_USER_ID']}"
    fields = (f"business_discovery.username({username})"
              f"{{media.limit({int(limit)}){{id,caption,timestamp,permalink,media_type}}}}")
    r = requests.get(url, params={"fields": fields, "access_token": os.environ["IG_ACCESS_TOKEN"]}, timeout=30)
    r.raise_for_status()
    return r.json()["business_discovery"].get("media", {}).get("data", [])
