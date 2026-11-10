"""Instagram Graph API — Business Discovery.

본인 IG 비즈니스/크리에이터 계정(IG_USER_ID)의 토큰으로
다른 공개 비즈니스/크리에이터 계정의 팔로워 수 등을 조회.
"""
import requests
from django.conf import settings


def fetch_account(username):
    """{"followers", "media_count"}"""
    url = f"https://graph.facebook.com/{settings.GRAPH_API_VERSION}/{settings.IG_USER_ID}"
    fields = f"business_discovery.username({username}){{followers_count,media_count,name}}"
    r = requests.get(
        url,
        params={"fields": fields, "access_token": settings.IG_ACCESS_TOKEN},
        timeout=15,
    )
    r.raise_for_status()
    bd = r.json()["business_discovery"]
    return {
        "name": bd.get("name") or username,
        "followers": bd.get("followers_count"),
        "media_count": bd.get("media_count"),
    }
