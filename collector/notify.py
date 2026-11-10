"""새 영상·조회수 돌파 알림. 시크릿이 있는 채널로만 보냄.

DISCORD_WEBHOOK_URL               디스코드 채널 웹훅
TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID  텔레그램 봇 / 채널(@이름 또는 숫자 ID)
SITE_URL                          메시지 끝에 붙일 사이트 주소 (선택)
"""
import os

import requests


def enabled():
    return bool(os.environ.get("DISCORD_WEBHOOK_URL")
                or (os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID")))


def _chunks(lines, limit):
    buf = ""
    for line in lines:
        if buf and len(buf) + len(line) + 1 > limit:
            yield buf
            buf = ""
        buf += line + "\n"
    if buf:
        yield buf


def send(lines):
    if not lines or not enabled():
        return
    site = os.environ.get("SITE_URL")
    if site:
        lines = [*lines, site]

    hook = os.environ.get("DISCORD_WEBHOOK_URL")
    if hook:
        for text in _chunks(lines, 1900):
            try:
                requests.post(hook, json={"content": text, "flags": 4}, timeout=15).raise_for_status()  # 4 = 링크 미리보기 끔
            except Exception as e:  # noqa: BLE001
                print(f"[알림] 디스코드 실패: {e}")

    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if token and chat:
        for text in _chunks(lines, 3800):
            try:
                requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                              json={"chat_id": chat, "text": text, "disable_web_page_preview": True},
                              timeout=15).raise_for_status()
            except Exception as e:  # noqa: BLE001
                print(f"[알림] 텔레그램 실패: {type(e).__name__}")  # URL에 토큰이 있어서 메시지는 안 찍음
