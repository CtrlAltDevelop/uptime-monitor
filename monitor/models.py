import re

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

# hostname / IPv4 / IPv6; must not start with "-" (would be read as a ping option)
HOST_RE = re.compile(r"^(?!-)[A-Za-z0-9:.\-]+$")

URL_TYPES = ("http", "http_keyword")
# Protocol default ports, used when the port field is left empty.
DEFAULT_PORTS = {"ssl_cert": 443, "ssh": 22, "smtp": 25, "redis": 6379, "postgres": 5432, "mysql": 3306}


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    order = models.PositiveIntegerField("display order", default=0)

    class Meta:
        ordering = ("order", "name")
        verbose_name = "category"
        verbose_name_plural = "categories"

    def __str__(self) -> str:
        return self.name


class Service(models.Model):
    class CheckType(models.TextChoices):
        PING = "ping", "Ping (ICMP)"
        TCP = "tcp", "TCP port"
        HTTP = "http", "HTTP / Health route"
        HTTP_KEYWORD = "http_keyword", "HTTP keyword"
        DNS = "dns", "DNS resolve"
        SSL_CERT = "ssl_cert", "SSL certificate"
        SSH = "ssh", "SSH"
        SMTP = "smtp", "SMTP"
        REDIS = "redis", "Redis"
        POSTGRES = "postgres", "PostgreSQL"
        MYSQL = "mysql", "MySQL / MariaDB"

    name = models.CharField(max_length=100)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="services")
    check_type = models.CharField(max_length=20, choices=CheckType.choices)
    target = models.CharField(
        max_length=255,
        help_text="http / http_keyword: full URL, e.g. https://example.com/health. Every other type: host or IP.",
    )
    port = models.PositiveIntegerField(
        null=True, blank=True, help_text="Required for TCP; optional elsewhere (protocol default is used)"
    )
    expected_status = models.PositiveSmallIntegerField(
        "expected status code", default=200, help_text="HTTP checks only"
    )
    keyword = models.CharField(max_length=200, blank=True, help_text="HTTP keyword checks: text the page must contain")
    warn_days = models.PositiveIntegerField(
        "certificate warning (days)", default=14, help_text="SSL checks: report down when expiry is closer than this"
    )
    interval_seconds = models.PositiveIntegerField(
        "check interval (seconds)", default=60, validators=[MinValueValidator(10)]
    )
    timeout_seconds = models.PositiveIntegerField(
        "timeout (seconds)", default=5, validators=[MinValueValidator(1)]
    )
    is_active = models.BooleanField("active", default=True)
    is_public = models.BooleanField("show on public page", default=True)

    class Meta:
        ordering = ("category__order", "name")
        verbose_name = "service"
        verbose_name_plural = "services"

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        if self.check_type in URL_TYPES:
            if not self.target.startswith(("http://", "https://")):
                raise ValidationError({"target": "URL must start with http:// or https://"})
            if self.check_type == self.CheckType.HTTP_KEYWORD and not self.keyword:
                raise ValidationError({"keyword": "A keyword is required for HTTP keyword checks."})
            return
        if not HOST_RE.match(self.target):
            raise ValidationError({"target": "Enter a valid hostname or IP address."})
        if self.check_type == self.CheckType.TCP and not (self.port and 1 <= self.port <= 65535):
            raise ValidationError({"port": "A valid port is required for TCP checks."})


class CheckResult(models.Model):
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name="results")
    checked_at = models.DateTimeField(default=timezone.now)
    is_up = models.BooleanField()
    latency_ms = models.FloatField(null=True, blank=True)
    # Error text may contain internal details: admin-only, never exposed by the API.
    detail = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("-checked_at",)
        indexes = [models.Index(fields=["service", "-checked_at"]), models.Index(fields=["checked_at"])]
        verbose_name = "check result"
        verbose_name_plural = "check results"

    def __str__(self) -> str:
        return f"{self.service} {'UP' if self.is_up else 'DOWN'} @ {self.checked_at:%Y-%m-%d %H:%M:%S}"
