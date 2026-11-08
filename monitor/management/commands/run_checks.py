import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from monitor.checks import run_check
from monitor.models import CheckResult, Service

logger = logging.getLogger(__name__)

TICK_SECONDS = 5
PRUNE_EVERY_SECONDS = 3600
MAX_WORKERS = 20


class Command(BaseCommand):
    help = "Background worker: runs each active service's health check on its own interval."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--once", action="store_true", help="check every active service once and exit")

    def handle(self, *args, **options) -> None:
        last_run: dict[int, float] = {}
        last_prune = 0.0
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            while True:
                now = time.monotonic()
                try:
                    self._tick(pool, last_run, now, force=options["once"])
                    if now - last_prune >= PRUNE_EVERY_SECONDS:
                        self._prune()
                        last_prune = now
                except Exception:
                    logger.exception("check cycle failed")
                if options["once"]:
                    return
                time.sleep(TICK_SECONDS)

    @staticmethod
    def _tick(pool: ThreadPoolExecutor, last_run: dict[int, float], now: float, force: bool) -> None:
        due = [
            s
            for s in Service.objects.filter(is_active=True)
            if force or now - last_run.get(s.id, float("-inf")) >= s.interval_seconds
        ]
        for service in due:
            last_run[service.id] = now
        outcomes = pool.map(run_check, due)  # workers never touch the DB
        CheckResult.objects.bulk_create(
            CheckResult(service=s, is_up=o.is_up, latency_ms=o.latency_ms, detail=o.detail)
            for s, o in zip(due, outcomes)
        )

    @staticmethod
    def _prune() -> None:
        cutoff = timezone.now() - timedelta(days=settings.RESULT_RETENTION_DAYS)
        CheckResult.objects.filter(checked_at__lt=cutoff).delete()
