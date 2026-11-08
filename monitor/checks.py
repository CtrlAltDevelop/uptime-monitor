"""Health checks. Pure functions: no DB access, safe to run in worker threads.

Each check returns "" when healthy, or a short reason string when not (exceptions also mean down).
"""

import smtplib
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from functools import lru_cache
from typing import NamedTuple

import certifi

from .models import DEFAULT_PORTS, HOST_RE, URL_TYPES, Service

MAX_BODY_BYTES = 1_000_000
POSTGRES_SSL_REQUEST = b"\x00\x00\x00\x08\x04\xd2\x16\x2f"  # answered with a single "S" or "N"
SECONDS_PER_DAY = 86400


class Outcome(NamedTuple):
    is_up: bool
    latency_ms: float | None
    detail: str


@lru_cache(maxsize=1)
def _tls_context() -> ssl.SSLContext:
    # certifi: a bundled CA store, so HTTPS checks also work where the OS store is missing (e.g. python.org macOS builds)
    return ssl.create_default_context(cafile=certifi.where())


def _port(service: Service) -> int:
    return service.port or DEFAULT_PORTS[service.check_type]


def _check_host(service: Service) -> None:
    if not HOST_RE.match(service.target):
        raise ValueError("invalid host")


def _exchange(service: Service, send: bytes = b"", size: int = 128) -> bytes:
    """Open a TCP connection, optionally send bytes, and return the first reply chunk."""
    _check_host(service)
    with socket.create_connection((service.target, _port(service)), timeout=service.timeout_seconds) as sock:
        if send:
            sock.sendall(send)
        return sock.recv(size)


def _ping(service: Service) -> str:
    _check_host(service)
    # macOS -W is milliseconds, Linux -W is seconds.
    wait = service.timeout_seconds * (1000 if sys.platform == "darwin" else 1)
    proc = subprocess.run(  # noqa: S603 - args are a fixed list, host validated above
        ["ping", "-c", "1", "-W", str(wait), service.target],
        capture_output=True,
        timeout=service.timeout_seconds + 2,
    )
    return "" if proc.returncode == 0 else "no ping reply"


def _tcp(service: Service) -> str:
    _check_host(service)
    with socket.create_connection((service.target, service.port), timeout=service.timeout_seconds):
        return ""


def _fetch(service: Service) -> tuple[int, str]:
    if not service.target.startswith(("http://", "https://")):
        raise ValueError("invalid url")
    req = urllib.request.Request(service.target, headers={"User-Agent": "uptime-monitor/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=service.timeout_seconds, context=_tls_context()) as resp:  # noqa: S310
            body = resp.read(MAX_BODY_BYTES) if service.check_type == "http_keyword" else b""
            return resp.status, body.decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, ""


def _http(service: Service) -> str:
    status, _ = _fetch(service)
    return "" if status == service.expected_status else f"status {status}"


def _http_keyword(service: Service) -> str:
    status, body = _fetch(service)
    if status != service.expected_status:
        return f"status {status}"
    return "" if service.keyword in body else "keyword not found"


def _dns(service: Service) -> str:
    _check_host(service)
    socket.getaddrinfo(service.target, None)  # raises socket.gaierror on failure
    return ""


def _ssl_cert(service: Service) -> str:
    _check_host(service)
    ctx = _tls_context()  # verifies chain + hostname
    with socket.create_connection((service.target, _port(service)), timeout=service.timeout_seconds) as raw:
        with ctx.wrap_socket(raw, server_hostname=service.target) as tls:
            expires = ssl.cert_time_to_seconds(tls.getpeercert()["notAfter"])
    days_left = (expires - time.time()) / SECONDS_PER_DAY
    return "" if days_left >= service.warn_days else f"certificate expires in {days_left:.0f} days"


def _ssh(service: Service) -> str:
    return "" if _exchange(service).startswith(b"SSH-") else "no SSH banner"


def _smtp(service: Service) -> str:
    _check_host(service)
    port = _port(service)
    client = smtplib.SMTP_SSL if port == 465 else smtplib.SMTP
    with client(service.target, port, timeout=service.timeout_seconds) as smtp:
        code, _ = smtp.noop()
    return "" if code == 250 else f"SMTP code {code}"


def _redis(service: Service) -> str:
    reply = _exchange(service, b"PING\r\n")
    # -NOAUTH means the server is alive but requires a password.
    return "" if reply.startswith((b"+PONG", b"-NOAUTH")) else "unexpected reply"


def _postgres(service: Service) -> str:
    return "" if _exchange(service, POSTGRES_SSL_REQUEST, 1) in (b"S", b"N") else "not a PostgreSQL server"


def _mysql(service: Service) -> str:
    greeting = _exchange(service)
    return "" if len(greeting) > 4 and greeting[4] == 10 else "not a MySQL server"  # protocol version 10


_CHECKS = {
    Service.CheckType.PING: _ping,
    Service.CheckType.TCP: _tcp,
    Service.CheckType.HTTP: _http,
    Service.CheckType.HTTP_KEYWORD: _http_keyword,
    Service.CheckType.DNS: _dns,
    Service.CheckType.SSL_CERT: _ssl_cert,
    Service.CheckType.SSH: _ssh,
    Service.CheckType.SMTP: _smtp,
    Service.CheckType.REDIS: _redis,
    Service.CheckType.POSTGRES: _postgres,
    Service.CheckType.MYSQL: _mysql,
}
assert set(_CHECKS) == set(Service.CheckType), "every check type needs an implementation"
assert set(URL_TYPES) <= {t.value for t in Service.CheckType}


def run_check(service: Service) -> Outcome:
    started = time.monotonic()
    try:
        detail = _CHECKS[service.check_type](service)
    except Exception as exc:  # any failure of the target means "down"; recorded in detail
        detail = f"{type(exc).__name__}: {exc}"[:255]
    latency = round((time.monotonic() - started) * 1000, 1)
    return Outcome(is_up=not detail, latency_ms=None if detail else latency, detail=detail)
