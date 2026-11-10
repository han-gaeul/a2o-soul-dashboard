"""YouTube Data API v3. search.list만 호출당 100유닛, 나머지는 1유닛."""
import html
import os
import re

import requests

API = "https://www.googleapis.com/youtube/v3"


def _key():
    return os.environ["YOUTUBE_API_KEY"]


def _get(endpoint, params):
    r = requests.get(f"{API}/{endpoint}", params={**params, "key": _key()}, timeout=20)
    r.raise_for_status()
    return r.json()


def _chunks(items, size=50):
    items = list(items)
    for i in range(0, len(items), size):
        yield items[i : i + size]


def fetch_channels(ids):
    """{id: {title, subscribers, views, uploads_playlist}}"""
    out = {}
    for chunk in _chunks(ids):
        body = _get("channels", {"part": "snippet,statistics,contentDetails", "id": ",".join(chunk)})
        for it in body.get("items", []):
            s = it.get("statistics", {})
            out[it["id"]] = {
                "title": it["snippet"]["title"],
                "subscribers": int(s["subscriberCount"]) if "subscriberCount" in s else None,
                "views": int(s.get("viewCount", 0)),
                "uploads_playlist": it["contentDetails"]["relatedPlaylists"]["uploads"],
            }
    return out


def resolve_handle(handle):
    """@handle → 채널 ID. 없으면 None."""
    items = _get("channels", {"part": "id", "forHandle": handle.lstrip("@")}).get("items", [])
    return items[0]["id"] if items else None


def fetch_uploads(playlist_id, since=None, max_pages=100):
    """[{id, title, published_at}] 최신순. since(ISO 날짜 문자열)보다 오래된 영상이 나오면 중단."""
    out, token = [], None
    for _ in range(max_pages):
        params = {"part": "snippet", "playlistId": playlist_id, "maxResults": 50}
        if token:
            params["pageToken"] = token
        body = _get("playlistItems", params)
        reached_old = False
        for it in body.get("items", []):
            sn = it["snippet"]
            published = sn.get("publishedAt") or ""
            if since and published and published[:10] < since:
                reached_old = True
                continue
            out.append({"id": sn["resourceId"]["videoId"], "title": sn["title"], "published_at": published or None})
        token = body.get("nextPageToken")
        if not token or reached_old:
            break
    return out


_DUR = re.compile(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")


def _seconds(iso):
    m = _DUR.fullmatch(iso or "")
    if not m:
        return None
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return ((d * 24 + h) * 60 + mi) * 60 + s


def fetch_videos(ids):
    """{id: {title, published_at, channel_id, channel_title, duration_s, views, likes, comments}}"""
    out = {}
    for chunk in _chunks(ids):
        body = _get("videos", {"part": "snippet,statistics,contentDetails", "id": ",".join(chunk)})
        for it in body.get("items", []):
            sn, s = it["snippet"], it.get("statistics", {})
            out[it["id"]] = {
                "title": sn["title"],
                "published_at": sn.get("publishedAt"),
                "channel_id": sn.get("channelId"),
                "channel_title": sn.get("channelTitle"),
                "duration_s": _seconds(it.get("contentDetails", {}).get("duration")),
                "views": int(s.get("viewCount", 0)),
                "likes": int(s["likeCount"]) if "likeCount" in s else None,
                "comments": int(s["commentCount"]) if "commentCount" in s else None,
            }
    return out


def search(query, published_after, max_pages=10):
    """search.list (호출당 100유닛). 최신순 [{id, title, published_at, channel_id, channel_title}]"""
    out, token = [], None
    for _ in range(max_pages):
        params = {"part": "snippet", "q": query, "type": "video", "order": "date",
                  "maxResults": 50, "publishedAfter": published_after}
        if token:
            params["pageToken"] = token
        body = _get("search", params)
        for it in body.get("items", []):
            sn = it["snippet"]
            out.append({
                "id": it["id"]["videoId"],
                "title": html.unescape(sn["title"]),
                "published_at": sn.get("publishedAt"),
                "channel_id": sn.get("channelId"),
                "channel_title": html.unescape(sn.get("channelTitle", "")),
            })
        token = body.get("nextPageToken")
        if not token:
            break
    return out
