from django.db import models

MEMBERS = [
    "MOON", "SORA", "SEOHA", "GAKU", "TEO", "JUNE", "LUCIEN", "HANSUNG",
    "TAI", "SEE-ONE", "SONO", "ALURE", "ZAI", "AYDEN", "ZET",
]
MEMBER_CHOICES = [("", "그룹/전체")] + [(m, m) for m in MEMBERS]

# 공용 채널(A2O WORLD 등)에서 A2O SOUL 영상 고르는 기본 필터.
# 그룹명은 대소문자 무시, 멤버 이름은 MOON/JUNE 같은 일반 단어와 안 겹치게 대문자 단어로만 매칭.
SOUL_FILTER = (
    r"A2O ?SOUL|A20 ?SOUL|에이투오 ?소울|"
    r"(?-i:\b(?:" + "|".join(m.replace("-", "-?") for m in MEMBERS) + r")\b)"
)
FILTER_PRESETS = {"soul": SOUL_FILTER}


class Target(models.Model):
    """추적 대상: 유튜브 채널, 유튜브 영상, 인스타 계정."""

    class Kind(models.TextChoices):
        YT_CHANNEL = "yt_channel", "유튜브 채널"
        YT_VIDEO = "yt_video", "유튜브 영상"
        IG_ACCOUNT = "ig_account", "인스타 계정"

    class Category(models.TextChoices):
        CHANNEL = "channel", "채널/계정"
        MV = "mv", "뮤직비디오"
        FANCAM = "fancam", "직캠"
        CONTENT = "content", "자체 콘텐츠"

    kind = models.CharField(max_length=20, choices=Kind.choices)
    external_id = models.CharField(
        "외부 ID", max_length=100, help_text="채널 ID(UC...), 영상 ID, 또는 인스타 username"
    )
    title = models.CharField("표시 이름", max_length=200, blank=True)
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.MV)
    member = models.CharField("멤버", max_length=20, choices=MEMBER_CHOICES, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    title_filter = models.CharField(
        "제목 필터(정규식)", max_length=200, blank=True,
        help_text="유튜브 채널용. 비우면 업로드 전부 등록, 넣으면 제목이 매칭되는 영상만 등록. "
                  "필터가 있는 채널(공용 채널)은 대시보드 구독자 KPI에서 빠짐",
    )
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("kind", "external_id")
        ordering = ["category", "published_at"]

    def __str__(self):
        return self.title or self.external_id


class Snapshot(models.Model):
    """수집 시점의 지표 값 하나."""

    class Metric(models.TextChoices):
        VIEWS = "views", "조회수"
        LIKES = "likes", "좋아요"
        COMMENTS = "comments", "댓글"
        SUBSCRIBERS = "subscribers", "구독자"
        FOLLOWERS = "followers", "팔로워"
        MEDIA_COUNT = "media_count", "게시물 수"

    target = models.ForeignKey(Target, on_delete=models.CASCADE, related_name="snapshots")
    metric = models.CharField(max_length=20, choices=Metric.choices)
    value = models.BigIntegerField()
    collected_at = models.DateTimeField(db_index=True)

    class Meta:
        indexes = [models.Index(fields=["target", "metric", "collected_at"])]
        ordering = ["collected_at"]

    def __str__(self):
        return f"{self.target} {self.metric}={self.value}"
