import re

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from tracker.collectors import instagram, youtube
from tracker.models import Snapshot, Target


class Command(BaseCommand):
    help = "활성화된 모든 Target의 지표를 수집해 Snapshot으로 저장"

    def handle(self, *args, **opts):
        now = timezone.now()
        rows = []
        targets = Target.objects.filter(active=True)

        # --- YouTube ---
        if settings.YOUTUBE_API_KEY:
            channels = {t.external_id: t for t in targets if t.kind == Target.Kind.YT_CHANNEL}
            for cid, data in youtube.fetch_channels(channels).items():
                t = channels[cid]
                if not t.title:
                    t.title = data["title"]
                    t.save(update_fields=["title"])
                if data["subscribers"] is not None:
                    rows.append(Snapshot(target=t, metric="subscribers", value=data["subscribers"], collected_at=now))
                rows.append(Snapshot(target=t, metric="views", value=data["views"], collected_at=now))

            # 공식 채널 업로드 자동 등록 (MV/티저/콘텐츠). 직캠은 음방 채널이라 track으로 수동 등록.
            known = set(Target.objects.filter(kind=Target.Kind.YT_VIDEO).values_list("external_id", flat=True))
            for cid, ch in channels.items():
                pattern = re.compile(ch.title_filter, re.I) if ch.title_filter else None
                for up in youtube.fetch_uploads(cid):
                    if up["id"] in known:
                        continue
                    if pattern and not pattern.search(up["title"]):
                        continue
                    cat = youtube.guess_category(up["title"])
                    Target.objects.create(
                        kind=Target.Kind.YT_VIDEO, external_id=up["id"], title=up["title"], category=cat,
                        published_at=parse_datetime(up["published_at"]) if up["published_at"] else None,
                    )
                    known.add(up["id"])
                    self.stdout.write(f"[YT] 새 영상 등록 [{cat}] {up['title']}")
            targets = Target.objects.filter(active=True)

            videos = {t.external_id: t for t in targets if t.kind == Target.Kind.YT_VIDEO}
            found = youtube.fetch_videos(videos)
            for vid, data in found.items():
                t = videos[vid]
                changed = []
                if not t.title:
                    t.title = data["title"]
                    changed.append("title")
                if not t.published_at and data["published_at"]:
                    t.published_at = parse_datetime(data["published_at"])
                    changed.append("published_at")
                if changed:
                    t.save(update_fields=changed)
                for metric in ("views", "likes", "comments"):
                    if data[metric] is not None:
                        rows.append(Snapshot(target=t, metric=metric, value=data[metric], collected_at=now))
            for vid in set(videos) - set(found):
                self.stderr.write(f"[YT] 영상을 찾을 수 없음(비공개/삭제?): {vid}")
        else:
            self.stderr.write("YOUTUBE_API_KEY 없음 — 유튜브 수집 건너뜀")

        # --- Instagram ---
        if settings.IG_USER_ID and settings.IG_ACCESS_TOKEN:
            for t in targets.filter(kind=Target.Kind.IG_ACCOUNT):
                try:
                    data = instagram.fetch_account(t.external_id)
                except Exception as e:  # noqa: BLE001
                    self.stderr.write(f"[IG] {t.external_id} 실패: {e}")
                    continue
                if not t.title:
                    t.title = data["name"]
                    t.save(update_fields=["title"])
                for metric in ("followers", "media_count"):
                    if data[metric] is not None:
                        rows.append(Snapshot(target=t, metric=metric, value=data[metric], collected_at=now))
        else:
            self.stderr.write("IG 토큰 없음 — 인스타 수집 건너뜀")

        Snapshot.objects.bulk_create(rows)
        self.stdout.write(self.style.SUCCESS(f"{len(rows)}개 스냅샷 저장 ({timezone.localtime(now):%Y-%m-%d %H:%M} KST)"))
