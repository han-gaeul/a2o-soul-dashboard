from collections import defaultdict
from datetime import timedelta

from django.conf import settings
from django.shortcuts import render
from django.utils import timezone

from .models import Snapshot, Target


def _daily_series(target, metric):
    """날짜별 마지막 값 [(date_str, value), ...]"""
    by_day = {}
    for collected_at, value in (
        Snapshot.objects.filter(target=target, metric=metric)
        .order_by("collected_at")
        .values_list("collected_at", "value")
    ):
        by_day[timezone.localtime(collected_at).date().isoformat()] = value
    return sorted(by_day.items())


def _latest_and_delta(target, metric):
    """(최신값, 24시간 전 대비 증가량)"""
    qs = Snapshot.objects.filter(target=target, metric=metric).order_by("-collected_at")
    latest = qs.first()
    if not latest:
        return None, None
    prev = qs.filter(collected_at__lte=latest.collected_at - timedelta(hours=23)).first()
    return latest.value, (latest.value - prev.value if prev else None)


def dashboard(request):
    targets = Target.objects.filter(active=True)
    today = timezone.localdate()

    # 채널/계정 KPI + 추이
    kpis, account_series = [], []
    # 제목 필터가 걸린 공용 채널(A2O WORLD 등)은 그룹 지표가 아니라서 제외
    for t in targets.filter(category=Target.Category.CHANNEL, title_filter=""):
        metric = "subscribers" if t.kind == Target.Kind.YT_CHANNEL else "followers"
        value, delta = _latest_and_delta(t, metric)
        label = f"{'유튜브 구독자' if metric == 'subscribers' else '인스타 팔로워'}"
        kpis.append({"label": label, "sub": t.title or t.external_id, "value": value, "delta": delta})
        account_series.append({"name": f"{label} · {t}", "points": _daily_series(t, metric)})

    # MV 조회수
    mv_series, mv_total, mv_total_delta = [], 0, 0
    for t in targets.filter(category=Target.Category.MV):
        value, delta = _latest_and_delta(t, "views")
        mv_total += value or 0
        mv_total_delta += delta or 0
        mv_series.append({"name": str(t), "points": _daily_series(t, "views"), "value": value, "delta": delta})
    kpis.append({"label": "MV 총 조회수", "sub": f"{len(mv_series)}편", "value": mv_total, "delta": mv_total_delta or None})

    # 멤버별 직캠 조회수 합계
    fancam = defaultdict(lambda: {"views": 0, "delta": 0, "count": 0})
    for t in targets.filter(category=Target.Category.FANCAM).exclude(member=""):
        value, delta = _latest_and_delta(t, "views")
        fancam[t.member]["views"] += value or 0
        fancam[t.member]["delta"] += delta or 0
        fancam[t.member]["count"] += 1
    fancam_rank = sorted(
        ({"member": m, **v} for m, v in fancam.items()), key=lambda r: r["views"], reverse=True
    )

    last = Snapshot.objects.order_by("-collected_at").values_list("collected_at", flat=True).first()

    return render(request, "tracker/dashboard.html", {
        "d_day": (today - settings.DEBUT_DATE).days + 1,
        "debut_date": settings.DEBUT_DATE,
        "kpis": kpis,
        "mv_list": sorted(mv_series, key=lambda r: r["value"] or 0, reverse=True),
        "fancam_rank": fancam_rank,
        "last_collected": last,
        "chart_data": {
            "accounts": account_series,
            "mvs": [{"name": s["name"], "points": s["points"]} for s in mv_series],
            "fancam": [{"member": r["member"], "views": r["views"]} for r in fancam_rank],
        },
    })
