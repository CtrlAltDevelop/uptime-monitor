"""A believable environment: demo services plus ~30 days of history with outages and flaky services.

Only the demo services (see seed_demo and EXTRA_SERVICES) are touched: their check results are replaced.
Services you created yourself, and their results, are left alone. Use `--days` to change the history length.
"""

import io
import random
from datetime import datetime, timedelta

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from monitor.management.commands.seed_demo import _rows
from monitor.models import Category, CheckResult, Service

STEP = timedelta(minutes=15)
BATCH = 5000
QUIET_HOURS = 1  # random incidents end at least this long before "now"
RNG_SEED = 42  # same data every run

# Services that really do fail when the worker checks them (name -> outage start, hours before now).
# Their history is consistent with what the worker will keep reporting.
FAILING = {
    "Billing API (staging)": 3,
    "Legacy FTP": 26,
    "Certificate expired.badssl.com": 24 * 8,
    "Certificate wrong.host.badssl.com": 24 * 12,
}
FAIL_DETAIL = {
    "Billing API (staging)": "ConnectionRefusedError: [Errno 111] Connection refused",
    "Legacy FTP": "TimeoutError: timed out",
    "Certificate expired.badssl.com": "SSLCertVerificationError: certificate has expired",
    "Certificate wrong.host.badssl.com": "SSLCertVerificationError: Hostname mismatch",
}
# (category, name, check_type, target, port, keyword)
EXTRA_SERVICES = [
    ("Internal", "Billing API (staging)", "tcp", "127.0.0.1", 9, ""),
    ("Internal", "Legacy FTP", "tcp", "192.0.2.1", 21, ""),
    ("Internal", "Marketing site (content)", "http_keyword", "https://example.com", None, "Example Domain"),
    ("TLS certificates", "Certificate expired.badssl.com", "ssl_cert", "expired.badssl.com", None, ""),
    ("TLS certificates", "Certificate wrong.host.badssl.com", "ssl_cert", "wrong.host.badssl.com", None, ""),
]
BASE_LATENCY_MS = {
    "ping": 120, "tcp": 130, "http": 900, "http_keyword": 700, "dns": 6,
    "ssl_cert": 380, "ssh": 450, "smtp": 600, "redis": 3, "postgres": 5, "mysql": 8,
}
DOWN_DETAIL = {
    "ping": "no ping reply",
    "dns": "gaierror: [Errno -2] Name or service not known",
    "http": "status 503",
    "http_keyword": "status 503",
}
# (share of services, expected incidents in the period, incident length range in minutes)
PROFILES = [(0.70, 0.4, (15, 60)), (0.20, 1.5, (15, 120)), (0.10, 5.0, (15, 30))]


def _pick_profile(rng: random.Random) -> tuple[float, tuple[int, int]]:
    roll, total = rng.random(), 0.0
    for share, incidents, length in PROFILES:
        total += share
        if roll < total:
            return incidents, length
    return PROFILES[-1][1], PROFILES[-1][2]


def _incident_windows(rng, start, end, expected, length_range) -> list[tuple[datetime, datetime]]:
    span_hours = (end - start).total_seconds() / 3600
    # Poisson-ish count: each hour has a small chance of starting an incident.
    chance = expected / span_hours
    windows, hour = [], 0
    while hour < span_hours:
        if rng.random() < chance:
            begin = start + timedelta(hours=hour, minutes=rng.randrange(60))
            windows.append((begin, begin + timedelta(minutes=rng.randint(*length_range))))
            hour += 2
        hour += 1
    return windows


def _history(rng, service, start, end) -> list[CheckResult]:
    forever = end + timedelta(days=1)
    if service.name in FAILING:
        windows = [(end - timedelta(hours=FAILING[service.name]), forever)]
    else:
        expected, length = _pick_profile(rng)
        windows = _incident_windows(rng, start, end - timedelta(hours=QUIET_HOURS), expected, length)

    base = BASE_LATENCY_MS[service.check_type] * rng.uniform(0.7, 1.4)
    detail = FAIL_DETAIL.get(service.name) or DOWN_DETAIL.get(service.check_type, "TimeoutError: timed out")
    rows, moment = [], start
    while moment <= end:
        down = any(a <= moment < b for a, b in windows)
        latency = None if down else round(base * rng.lognormvariate(0, 0.3), 1)
        rows.append(
            CheckResult(service=service, checked_at=moment, is_up=not down, latency_ms=latency, detail=detail if down else "")
        )
        moment += STEP
    return rows


class Command(BaseCommand):
    help = "Create the demo services and backfill realistic check history for them (replaces their results)."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--days", type=int, default=30, help="days of history to generate (default 30)")

    def handle(self, *args, days: int, **options) -> None:
        call_command("seed_demo", stdout=io.StringIO())
        self._add_extra_services()

        rng = random.Random(RNG_SEED)
        end = timezone.now().replace(second=0, microsecond=0)
        start = end - timedelta(days=days)

        demo_names = {row[1] for row in _rows()} | {extra[1] for extra in EXTRA_SERVICES}
        demo = Service.objects.filter(name__in=demo_names, is_active=True).order_by("id")
        CheckResult.objects.filter(service__in=demo).delete()
        total = 0
        for service in demo:
            rows = _history(rng, service, start, end)
            CheckResult.objects.bulk_create(rows, batch_size=BATCH)
            total += len(rows)
        self.stdout.write(f"{demo.count()} demo services, {total} results over {days} days.")

    @staticmethod
    def _add_extra_services() -> None:
        for order, (cat_name, name, check_type, target, port, keyword) in enumerate(EXTRA_SERVICES):
            category, _ = Category.objects.get_or_create(name=cat_name, defaults={"order": 10 + order})
            Service.objects.get_or_create(
                name=name,
                defaults={
                    "category": category, "check_type": check_type, "target": target, "port": port,
                    "keyword": keyword, "timeout_seconds": 3,
                },
            )
