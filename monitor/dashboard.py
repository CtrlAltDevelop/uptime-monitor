"""Context for the admin home page (Unfold DASHBOARD_CALLBACK)."""

from datetime import timedelta

from django.db.models import Count, OuterRef, Q, Subquery
from django.http import HttpRequest
from django.utils import timezone

from .models import CheckResult, Service

RECENT_FAILURES = 8


def dashboard_callback(request: HttpRequest, context: dict) -> dict:
    latest = CheckResult.objects.filter(service=OuterRef("pk")).order_by("-checked_at")
    active = Service.objects.filter(is_active=True).annotate(last_up=Subquery(latest.values("is_up")[:1]))

    down = list(active.filter(last_up=False).select_related("category"))
    up_count = active.filter(last_up=True).count()
    total = active.count()

    day = CheckResult.objects.filter(checked_at__gte=timezone.now() - timedelta(hours=24)).aggregate(
        total=Count("id"), up=Count("id", filter=Q(is_up=True))
    )
    uptime_24h = round(day["up"] * 100 / day["total"], 2) if day["total"] else None

    context.update(
        {
            "stats": {
                "total": total,
                "up": up_count,
                "down": len(down),
                "unknown": total - up_count - len(down),
                "uptime_24h": uptime_24h,
            },
            "down_services": down,
            "recent_failures": CheckResult.objects.filter(is_up=False).select_related("service")[:RECENT_FAILURES],
        }
    )
    return context
