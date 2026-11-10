"""YouTube Data API v3 수집기.

channels.list / videos.list 모두 호출당 1유닛. search.list(100유닛)는 쓰지 않음.
"""
import requests
from django.conf import settings

API = "https://www.googleapis.com/youtube/v3"


def _chunks(items, size=50):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _get(endpoint, params):
    params = {**params, "key": settings.YOUTUBE_API_KEY}
    r = requests.get(f"{API}/{endpoint}", params=params, timeout=15)
    r.raise_for_status()
    return r.json().get("items", [])


def fetch_channels(channel_ids):
    """{channel_id: {"title", "subscribers", "views"}}"""
    out = {}
    for chunk in _chunks(list(channel_ids)):
        for item in _get("channels", {"part": "snippet,statistics", "id": ",".join(chunk)}):
            s = item.get("statistics", {})
            out[item["id"]] = {
                "title": item["snippet"]["title"],
                "subscribers": int(s["subscriberCount"]) if "subscriberCount" in s else None,
                "views": int(s.get("viewCount", 0)),
            }
    return out


def resolve_handle(handle):
    """@handle → 채널 ID(UC...). 없으면 None."""
    items = _get("channels", {"part": "id", "forHandle": handle.lstrip("@")})
    return items[0]["id"] if items else None


def fetch_uploads(channel_id, max_pages=10):
    """채널 업로드 목록 [{"id", "title", "published_at"}] — 페이지당 1유닛(50개)."""
    items = _get("channels", {"part": "contentDetails", "id": channel_id})
    if not items:
        return []
    playlist = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
    out, token = [], None
    for _ in range(max_pages):
        params = {"part": "snippet", "playlistId": playlist, "maxResults": 50, "key": settings.YOUTUBE_API_KEY}
        if token:
            params["pageToken"] = token
        r = requests.get(f"{API}/playlistItems", params=params, timeout=15)
        r.raise_for_status()
        body = r.json()
        for it in body.get("items", []):
            sn = it["snippet"]
            out.append({
                "id": sn["resourceId"]["videoId"],
                "title": sn["title"],
                "published_at": sn.get("publishedAt"),
            })
        token = body.get("nextPageToken")
        if not token:
            break
    return out


def guess_category(title):
    """제목으로 분류 추정: MV 본편 → mv, 나머지(티저·비하인드 등) → content."""
    t = title.upper()
    if "TEASER" in t or "티저" in title:
        return "content"
    if "M/V" in t or " MV" in t or "MUSIC VIDEO" in t:
        return "mv"
    return "content"


def fetch_videos(video_ids):
    """{video_id: {"title", "published_at", "views", "likes", "comments"}}"""
    out = {}
    for chunk in _chunks(list(video_ids)):
        for item in _get("videos", {"part": "snippet,statistics", "id": ",".join(chunk)}):
            s = item.get("statistics", {})
            out[item["id"]] = {
                "title": item["snippet"]["title"],
                "published_at": item["snippet"].get("publishedAt"),
                "views": int(s.get("viewCount", 0)),
                "likes": int(s["likeCount"]) if "likeCount" in s else None,
                "comments": int(s["commentCount"]) if "commentCount" in s else None,
            }
    return out
