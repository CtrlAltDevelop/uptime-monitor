from django.core.management.base import BaseCommand

from monitor.models import Category, Service

# (category, name, check_type, target, port)
WEBSITES = [
    ("Google", "google.com"), ("GitHub", "github.com"), ("Cloudflare", "cloudflare.com"),
    ("Wikipedia", "wikipedia.org"), ("Microsoft", "microsoft.com"), ("Apple", "apple.com"),
    ("Netflix", "netflix.com"), ("Reddit", "reddit.com"), ("Stack Overflow", "stackoverflow.com"),
    ("Python", "python.org"), ("Django Project", "djangoproject.com"), ("npm", "npmjs.com"),
    ("Docker", "docker.com"), ("Mozilla", "mozilla.org"), ("BBC", "bbc.com"),
    ("The Guardian", "theguardian.com"), ("NY Times", "nytimes.com"), ("Anthropic", "anthropic.com"),
    ("YouTube", "youtube.com"), ("Spotify", "spotify.com"), ("Twitch", "twitch.tv"),
    ("Hacker News", "news.ycombinator.com"), ("Let's Encrypt", "letsencrypt.org"),
    ("Linux Kernel", "kernel.org"), ("Ubuntu", "ubuntu.com"),
]
DNS_SERVERS = [
    ("Google DNS 8.8.8.8", "8.8.8.8"), ("Google DNS 8.8.4.4", "8.8.4.4"), ("Cloudflare DNS 1.1.1.1", "1.1.1.1"),
    ("Cloudflare DNS 1.0.0.1", "1.0.0.1"), ("Quad9 DNS", "9.9.9.9"), ("OpenDNS", "208.67.222.222"),
]
DNS_LOOKUPS = ["google.com", "github.com", "cloudflare.com", "wikipedia.org"]
# These sites answer scripted HTTP requests with 403, so only their HTTPS port is probed.
BOT_BLOCKED = {"npmjs.com", "stackoverflow.com", "nytimes.com"}
PING_HOSTS = ["8.8.8.8", "1.1.1.1", "9.9.9.9", "github.com", "cloudflare.com"]


def _rows() -> list[tuple[str, str, str, str, int | None]]:
    rows = [
        ("Websites", name, "tcp", host, 443) if host in BOT_BLOCKED else ("Websites", name, "http", f"https://{host}", None)
        for name, host in WEBSITES
    ]
    rows += [("DNS servers", name, "tcp", ip, 53) for name, ip in DNS_SERVERS]
    rows += [("DNS servers", f"Resolve {h}", "dns", h, None) for h in DNS_LOOKUPS]
    rows += [("Network", f"Ping {h}", "ping", h, None) for h in PING_HOSTS]
    rows += [("Network", f"HTTPS port {h}", "tcp", h, 443) for h in ("github.com", "google.com")]
    rows += [("Git & Mail", "GitHub SSH", "ssh", "github.com", None), ("Git & Mail", "GitLab SSH", "ssh", "gitlab.com", None)]
    rows += [("Git & Mail", "Gmail SMTP", "smtp", "smtp.gmail.com", 587), ("Git & Mail", "Gmail SMTP (SSL)", "smtp", "smtp.gmail.com", 465)]
    rows += [("TLS certificates", f"Certificate {h}", "ssl_cert", h, None) for h in ("github.com", "cloudflare.com", "python.org", "wikipedia.org")]
    return rows


class Command(BaseCommand):
    help = "Create ~50 demo services that monitor well-known public hosts (idempotent)."

    def handle(self, *args, **options) -> None:
        categories: dict[str, Category] = {}
        created = 0
        for order, (cat, name, check_type, target, port) in enumerate(_rows()):
            if cat not in categories:
                categories[cat], _ = Category.objects.get_or_create(name=cat, defaults={"order": len(categories)})
            _, was_created = Service.objects.get_or_create(
                name=name,
                defaults={"category": categories[cat], "check_type": check_type, "target": target, "port": port},
            )
            created += was_created
        self.stdout.write(f"{created} services created, {Service.objects.count()} total.")
