import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db.models import OuterRef, Subquery
from django.test import TestCase

from .checks import run_check
from .models import Category, CheckResult, Service


class _Health(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        ok = self.path == "/health"
        self.send_response(200 if ok else 503)
        self.end_headers()
        if ok:
            self.wfile.write(b"all systems ok")

    def log_message(self, *args) -> None:
        pass


def _fake_tcp_server(reply: bytes, test: TestCase) -> int:
    """Accepts connections, sends `reply` immediately, drains the client's request, closes."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen()

    def serve() -> None:
        while True:
            try:
                conn, _ = srv.accept()
            except OSError:
                return
            with conn:
                conn.settimeout(1)
                conn.sendall(reply)
                try:
                    conn.recv(64)
                except OSError:
                    pass

    threading.Thread(target=serve, daemon=True).start()
    test.addCleanup(srv.close)
    return srv.getsockname()[1]


class MonitorTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.cat = Category.objects.create(name="Infra")

    def _svc(self, **kw) -> Service:
        defaults = {"name": "s", "category": self.cat, "timeout_seconds": 2}
        return Service.objects.create(**{**defaults, **kw})

    def test_http_and_tcp_up_and_down(self) -> None:
        server = HTTPServer(("127.0.0.1", 0), _Health)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        port = server.server_port
        base = f"http://127.0.0.1:{port}"

        ok = self._svc(check_type="http", target=f"{base}/health")
        bad = self._svc(check_type="http", target=f"{base}/nope")
        keyword_ok = self._svc(check_type="http_keyword", target=f"{base}/health", keyword="systems ok")
        keyword_bad = self._svc(check_type="http_keyword", target=f"{base}/health", keyword="missing")
        tcp_ok = self._svc(check_type="tcp", target="127.0.0.1", port=port)
        with socket.socket() as s:  # grab a free port that nothing listens on
            s.bind(("127.0.0.1", 0))
            closed = s.getsockname()[1]
        tcp_bad = self._svc(check_type="tcp", target="127.0.0.1", port=closed)

        self.assertTrue(run_check(ok).is_up)
        self.assertFalse(run_check(bad).is_up)
        self.assertTrue(run_check(keyword_ok).is_up)
        self.assertEqual(run_check(keyword_bad).detail, "keyword not found")
        self.assertTrue(run_check(tcp_ok).is_up)
        self.assertFalse(run_check(tcp_bad).is_up)

    def test_protocol_checks(self) -> None:
        cases = [
            ("ssh", b"SSH-2.0-test\r\n", b"garbage"),
            ("redis", b"+PONG\r\n", b"-ERR nope\r\n"),
            ("postgres", b"S", b"X"),
            ("mysql", b"\x4a\x00\x00\x00\x0a8.0.0", b"\x00\x00\x00\x00\xff"),
        ]
        for check_type, good, bad in cases:
            with self.subTest(check_type=check_type):
                up = self._svc(check_type=check_type, target="127.0.0.1", port=_fake_tcp_server(good, self))
                down = self._svc(check_type=check_type, target="127.0.0.1", port=_fake_tcp_server(bad, self))
                self.assertTrue(run_check(up).is_up)
                self.assertFalse(run_check(down).is_up)

    def test_dns_check(self) -> None:
        self.assertTrue(run_check(self._svc(check_type="dns", target="localhost")).is_up)
        self.assertFalse(run_check(self._svc(check_type="dns", target="no-such-host.invalid")).is_up)

    def test_validation_rules(self) -> None:
        with self.assertRaises(ValidationError):
            Service(name="x", category=self.cat, check_type="http_keyword", target="https://a.b").full_clean()
        with self.assertRaises(ValidationError):
            Service(name="x", category=self.cat, check_type="tcp", target="a.b").full_clean()
        with self.assertRaises(ValidationError):
            Service(name="x", category=self.cat, check_type="ping", target="-c 9 evil").full_clean()
        Service(name="x", category=self.cat, check_type="ssh", target="a.b").full_clean()  # default port is fine

    def test_runner_records_and_public_api_hides_sensitive_data(self) -> None:
        self._svc(name="Web", check_type="tcp", target="127.0.0.1", port=1)  # port 1: refused -> down
        hidden = self._svc(name="Hidden", check_type="tcp", target="10.9.9.9", port=1, is_public=False)

        call_command("run_checks", "--once")
        self.assertEqual(CheckResult.objects.count(), 2)
        self.assertTrue(CheckResult.objects.filter(service=hidden).exists())

        resp = self.client.get("/api/status")
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        data = resp.json()
        self.assertEqual(data["overall"], "degraded")
        self.assertEqual([s["name"] for s in data["categories"][0]["services"]], ["Web"])
        self.assertEqual(data["categories"][0]["services"][0]["status"], "down")
        for secret in ("127.0.0.1", "10.9.9.9", "Hidden", "detail", "target", "port"):
            self.assertNotIn(secret, body)

    def test_seed_demo_is_idempotent_and_has_50_services(self) -> None:
        call_command("seed_demo")
        call_command("seed_demo")
        self.assertEqual(Service.objects.count(), 50)
        for service in Service.objects.all():
            service.full_clean()

    def test_dashboard_renders(self) -> None:
        self.assertEqual(self.client.get("/").status_code, 200)

    def test_seed_realistic_builds_consistent_history(self) -> None:
        mine = self._svc(name="My own service", check_type="tcp", target="127.0.0.1", port=1)
        CheckResult.objects.create(service=mine, is_up=True, latency_ms=1)
        call_command("seed_realistic", "--days", "2")
        self.assertEqual(mine.results.count(), 1)  # user services keep their real results
        first = CheckResult.objects.count()
        call_command("seed_realistic", "--days", "2")  # replaces results instead of piling up
        self.assertEqual(CheckResult.objects.count(), first)
        self.assertEqual(mine.results.count(), 1)

        latest = CheckResult.objects.filter(service=OuterRef("pk")).order_by("-checked_at")
        down_now = set(
            Service.objects.exclude(pk=mine.pk)
            .annotate(up=Subquery(latest.values("is_up")[:1]))
            .filter(up=False)
            .values_list("name", flat=True)
        )
        self.assertEqual(
            down_now,
            {"Billing API (staging)", "Legacy FTP", "Certificate expired.badssl.com", "Certificate wrong.host.badssl.com"},
        )
        oldest = CheckResult.objects.order_by("checked_at").first()
        self.assertGreaterEqual((CheckResult.objects.order_by("-checked_at").first().checked_at - oldest.checked_at).days, 1)
