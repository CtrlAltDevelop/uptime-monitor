"""Public, read-only status API. Exposes name, category, check kind, up/down, uptime % and last response time:
never targets, ports or error details."""

from collections import defaultdict
from datetime import date, datetime, timedelta

from django.core.cache import cache
from django.db.models import Count, OuterRef, Q, Subquery
from django.db.models.functions import TruncDate
from django.utils import timezone
from ninja import NinjaAPI, Schema

from .models import Category, CheckResult, Service

HISTORY_DAYS = 30
CACHE_SECONDS = 15
KIND_LABELS = {
    "ping": "PING", "tcp": "TCP", "http": "HTTP", "http_keyword": "HTTP+TEXT", "dns": "DNS",
    "ssl_cert": "SSL", "ssh": "SSH", "smtp": "SMTP", "redis": "REDIS", "postgres": "POSTGRES", "mysql": "MYSQL",
}

api = NinjaAPI(title="Uptime status", docs_url=None, openapi_url=None)


class DayOut(Schema):
    date: date
    uptime: float | None  # percent, None = no data


class ServiceOut(Schema):
    name: str
    kind: str  # short check label, e.g. HTTP, DNS, SSL
    status: str  # up | down | unknown
    latency_ms: float | None
    uptime_30d: float | None
    last_checked: datetime | None
    days: list[DayOut]


class CategoryOut(Schema):
    name: str
    services: list[ServiceOut]


class StatusOut(Schema):
    overall: str  # up | degraded | unknown
    updated_at: datetime
    categories: list[CategoryOut]


def _pct(up: int, total: int) -> float | None:
    return round(up * 100 / total, 2) if total else None


def _build_status() -> dict:
    today = timezone.localdate()
    first_day = today - timedelta(days=HISTORY_DAYS - 1)
    since = timezone.make_aware(datetime.combine(first_day, datetime.min.time()))

    latest = CheckResult.objects.filter(service=OuterRef("pk")).order_by("-checked_at")
    services = (
        Service.objects.filter(is_active=True, is_public=True)
        .annotate(
            last_up=Subquery(latest.values("is_up")[:1]),
            last_at=Subquery(latest.values("checked_at")[:1]),
            last_ms=Subquery(latest.values("latency_ms")[:1]),
        )
        .select_related("category")
    )

    daily: dict[int, dict[date, tuple[int, int]]] = defaultdict(dict)
    rows = (
        CheckResult.objects.filter(service__in=services, checked_at__gte=since)
        .annotate(day=TruncDate("checked_at"))
        .values("service_id", "day")
        .annotate(total=Count("id"), up=Count("id", filter=Q(is_up=True)))
    )
    for row in rows:
        daily[row["service_id"]][row["day"]] = (row["up"], row["total"])

    by_category: dict[int, list[dict]] = defaultdict(list)
    statuses: list[str] = []
    for s in services:
        days = [first_day + timedelta(days=i) for i in range(HISTORY_DAYS)]
        per_day = daily[s.id]
        up_sum = sum(per_day.get(d, (0, 0))[0] for d in days)
        total_sum = sum(per_day.get(d, (0, 0))[1] for d in days)
        status = "unknown" if s.last_up is None else ("up" if s.last_up else "down")
        statuses.append(status)
        by_category[s.category_id].append(
            {
                "name": s.name,
                "kind": KIND_LABELS[s.check_type],
                "status": status,
                "latency_ms": s.last_ms,
                "uptime_30d": _pct(up_sum, total_sum),
                "last_checked": s.last_at,
                "days": [{"date": d, "uptime": _pct(*per_day.get(d, (0, 0)))} for d in days],
            }
        )

    categories = [
        {"name": c.name, "services": by_category[c.id]}
        for c in Category.objects.all()
        if by_category[c.id]
    ]
    if "down" in statuses:
        overall = "degraded"
    else:
        overall = "up" if "up" in statuses else "unknown"
    return {"overall": overall, "updated_at": timezone.now(), "categories": categories}


@api.get("/status", response=StatusOut, summary="Public service status")
def status(request) -> dict:
    return cache.get_or_set("public_status", _build_status, CACHE_SECONDS)
