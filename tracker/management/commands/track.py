import re

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from tracker.collectors import youtube
from tracker.models import FILTER_PRESETS, MEMBERS, Target

YT_ID = re.compile(r"(?:v=|youtu\.be/|shorts/)([\w-]{11})")
YT_HANDLE = re.compile(r"@([\w.-]+)")


class Command(BaseCommand):
    help = "추적 대상 추가. 예) track video https://youtu.be/xxxx --category fancam --member MOON"

    def add_arguments(self, parser):
        parser.add_argument("kind", choices=["video", "channel", "ig"])
        parser.add_argument("ids", nargs="+", help="영상 URL/ID, 채널 ID(UC...), 인스타 username")
        parser.add_argument("--category", default=None, choices=["mv", "fancam", "content"])
        parser.add_argument("--member", default="", help="멤버 이름 (직캠용)")
        parser.add_argument("--filter", default=None, dest="title_filter",
                            help="채널 업로드 중 제목이 이 정규식에 맞는 것만 등록 (공용 채널용). "
                                 "'soul' = 그룹명 + 멤버 이름 프리셋")

    def handle(self, kind, ids, category, member, title_filter, **opts):
        if title_filter:
            title_filter = FILTER_PRESETS.get(title_filter.lower(), title_filter)
            try:
                re.compile(title_filter)
            except re.error as e:
                raise CommandError(f"정규식 오류: {e}")
        member = member.upper()
        if member and member not in MEMBERS:
            raise CommandError(f"알 수 없는 멤버: {member} (가능: {', '.join(MEMBERS)})")

        kind_map = {"video": Target.Kind.YT_VIDEO, "channel": Target.Kind.YT_CHANNEL, "ig": Target.Kind.IG_ACCOUNT}
        for raw in ids:
            ext = raw
            if kind == "video":
                m = YT_ID.search(raw)
                ext = m.group(1) if m else raw
            elif kind == "ig":
                ext = raw.lstrip("@")
            elif kind == "channel" and not raw.startswith("UC"):
                handle = YT_HANDLE.search(raw)
                if not handle:
                    raise CommandError(f"채널 ID(UC...) 또는 @핸들/URL이 필요해요: {raw}")
                if not settings.YOUTUBE_API_KEY:
                    raise CommandError("@핸들 변환에는 YOUTUBE_API_KEY가 필요해요")
                ext = youtube.resolve_handle(handle.group(1))
                if not ext:
                    raise CommandError(f"채널을 찾을 수 없음: {raw}")
            cat = "channel" if kind in ("channel", "ig") else (category or "mv")
            defaults = {"category": cat, "member": member}
            if title_filter is not None:
                defaults["title_filter"] = title_filter
            t, created = Target.objects.update_or_create(
                kind=kind_map[kind], external_id=ext, defaults=defaults
            )
            extra = f" filter={t.title_filter}" if t.title_filter else ""
            self.stdout.write(("추가: " if created else "갱신: ") + f"{t.get_kind_display()} {ext} [{cat}] {member}{extra}")
