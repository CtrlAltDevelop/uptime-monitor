# Uptime Monitor

A small, self-hosted uptime monitor built with **Django**, **Django Ninja** and the **Unfold** admin.
Define services in the admin, choose how each one is health-checked, and a background worker records the
results. A public, TV-friendly status page shows only what matters: **is it up, and for how long**. No hosts,
ports or error messages are ever exposed.

![Public status page](docs/screenshots/public-dashboard.png)

## Features

- **11 check types:** ping, TCP port, HTTP status, HTTP keyword, DNS, SSL certificate expiry, SSH, SMTP, Redis,
  PostgreSQL and MySQL/MariaDB.
- **Categories:** group services however you like; the order is configurable.
- **Background worker:** every service runs on its own interval and timeout, checks run in parallel, and old
  results are pruned automatically.
- **Public status page (`/`):** a glass-style grid that scales to the screen, so all services fit on a TV without
  scrolling. Problems sort first, each tile has a 30-day history bar, and it refreshes itself every 30 seconds.
  Double-click for full screen.
- **Public JSON API (`/api/status`):** the same data the page uses, cached for 15 seconds.
- **Modern admin (`/admin/`):** Unfold theme with a custom glass skin, a dashboard with live counters and recent
  failures, status badges, search and filters.
- **Safe by default:** the public side never returns targets, ports or error details.
  Per-service `show on public page` switch.

## Screenshots

| Admin dashboard | Services |
| --- | --- |
| ![Admin dashboard](docs/screenshots/admin-dashboard.png) | ![Services list](docs/screenshots/admin-services.png) |

| Add a service | Login |
| --- | --- |
| ![Service form](docs/screenshots/admin-service-form.png) | ![Login](docs/screenshots/admin-login.png) |

## Check types

| Type | Target | Healthy when |
| --- | --- | --- |
| `ping` | host or IP | the system `ping` gets a reply |
| `tcp` | host or IP + **port** | a TCP connection opens |
| `http` | full URL | the response status equals the expected code (default `200`, redirects followed) |
| `http_keyword` | full URL + **keyword** | expected status **and** the first 1 MB of the body contains the keyword |
| `dns` | hostname | the name resolves |
| `ssl_cert` | host (default port 443) | the certificate chain is valid and expires in more than `warn_days` (default 14) |
| `ssh` | host (default port 22) | the server answers with an `SSH-` banner |
| `smtp` | host (default port 25; 465 uses SSL) | the server greets and answers `NOOP` |
| `redis` | host (default port 6379) | `PING` returns `+PONG` (or `-NOAUTH`, meaning it is alive but needs a password) |
| `postgres` | host (default port 5432) | answers the protocol's SSL handshake request |
| `mysql` | host (default port 3306) | sends a MySQL protocol-10 greeting |

Every check has a per-service **interval** (minimum 10 s) and **timeout**. HTTPS verification uses the bundled
[`certifi`](https://pypi.org/project/certifi/) CA store, so it works the same on every OS.

## Quick start

### With Docker (recommended)

Requires Docker with the Compose plugin.

```bash
make up               # creates .env with a generated SECRET_KEY, builds the image, starts web + worker
make docker-superuser # create your admin login
make docker-seed      # optional: 50 services that monitor well-known public hosts
```

Open <http://localhost:8000/> (status page) and <http://localhost:8000/admin/> (admin).
`compose.yaml` runs two containers, `web` (gunicorn) and `worker` (the health checks), which share one data volume,
so your database survives `make down` and image rebuilds. Change the published port with `PORT` in `.env`.
Run `make help` to list every shortcut.

### Locally with uv

Requires [uv](https://docs.astral.sh/uv/) (it installs Python for you) and Python 3.10+.

```bash
git clone <your-fork-url> uptime-monitor && cd uptime-monitor
make install      # uv sync
make migrate
make superuser
make seed         # optional demo data
make run          # terminal 1: status page at /, admin at /admin/
make worker       # terminal 2: the background worker
```

The `make` targets set `DEBUG=1` for you. Without make, use
`DEBUG=1 uv run python manage.py <command>`.

> **The worker is a separate process.** The web server only reads results; nothing is checked unless the worker is
> running. `make check-once` checks every active service once and exits, which is handy for cron jobs and debugging.

### Adding your first service

1. In the admin, create a **Category** (for example "Production").
2. Create a **Service**, pick a **check type**, enter the **target** (a hostname, or a URL for HTTP checks) and save.
   Fields that don't apply to the chosen type are ignored.
3. Within one interval it appears on the status page.

## Configuration

All settings are environment variables.

| Variable | Default | Purpose |
| --- | --- | --- |
| `SECRET_KEY` | none, **required** unless `DEBUG=1` | Django secret key |
| `DEBUG` | off | set to `1` for local development only |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | comma-separated host names |
| `CSRF_TRUSTED_ORIGINS` | none | comma-separated origins, e.g. `https://status.example.com` (needed behind HTTPS proxies) |
| `DB_PATH` | `./db.sqlite3` | SQLite database file |
| `TIME_ZONE` | `Asia/Tehran` | used for the daily history buckets and the admin |
| `RESULT_RETENTION_DAYS` | `90` | raw check results older than this are deleted |

## Public API

`GET /api/status` (no authentication, cached for 15 s):

```json
{
  "overall": "up",
  "updated_at": "2026-11-08T13:28:38Z",
  "categories": [
    {
      "name": "Websites",
      "services": [
        {
          "name": "GitHub",
          "kind": "HTTP",
          "status": "up",
          "latency_ms": 670.2,
          "uptime_30d": 99.8,
          "last_checked": "2026-11-08T13:28:30Z",
          "days": [{ "date": "2026-11-08", "uptime": 100.0 }]
        }
      ]
    }
  ]
}
```

`overall` is `up`, `degraded` (at least one service is down) or `unknown` (no results yet). `status` is
`up`, `down` or `unknown`. The response never includes targets, ports, hostnames or error text.

## Deploying

The simplest route is the included Compose file: put it on a server, run `make up`, and put a reverse proxy with
HTTPS in front of port 8000. Set these in `.env` first:

```bash
ALLOWED_HOSTS=status.example.com
CSRF_TRUSTED_ORIGINS=https://status.example.com
```

Static files (the admin theme) are served by WhiteNoise, so no extra web server is needed for them.

Without Docker, run **two processes** against the same database:

```bash
export SECRET_KEY='<long random string>' ALLOWED_HOSTS=status.example.com \
       CSRF_TRUSTED_ORIGINS=https://status.example.com DB_PATH=/var/lib/uptime/db.sqlite3

uv sync --no-dev
uv run python manage.py migrate
uv run python manage.py collectstatic --noinput

uv run gunicorn config.wsgi --bind 127.0.0.1:8000    # web
uv run python manage.py run_checks                   # worker (keep it alive with systemd or supervisor)
```

Example systemd unit for the worker:

```ini
[Service]
WorkingDirectory=/srv/uptime-monitor
EnvironmentFile=/etc/uptime-monitor.env
ExecStart=/srv/uptime-monitor/.venv/bin/python manage.py run_checks
Restart=always
```

Back up the SQLite file (the `uptime-data` volume with Docker), or point `DATABASES` at PostgreSQL in
`config/settings.py` for heavier use. The `ping` check needs the `ping` command and permission to send ICMP;
the Docker image installs it.

## Security notes

- **Admins decide what the server probes.** Check targets are entered in the admin, and checks run from the
  server's network, so a malicious admin could point a check at internal addresses. Only give admin access to
  people you trust.
- Hostnames are validated before ping/TCP checks, and the `ping` command is invoked with a fixed argument list.
- The public page and API intentionally omit everything except name, category, check kind, status, response time
  and uptime percentages. Use the `show on public page` switch to keep a service private.
- `SECRET_KEY` is mandatory outside `DEBUG`, and the app refuses to start without it.
- See [SECURITY.md](SECURITY.md) for how to report a vulnerability and a hardening checklist for operators.

## Development

```bash
make test     # run the suite
make check    # Django system check + "no missing migrations"
```

The suite covers each protocol check against local fake servers, validation rules, the worker's cycle, the demo
seed and the public API, including a test that sensitive values never leak.

```
config/                  Django project (settings, urls, wsgi)
compose.yaml, Dockerfile web + worker containers
Makefile                 development and Docker shortcuts (run `make help`)
monitor/
  models.py              Category, Service, CheckResult
  checks.py              one function per check type + run_check()
  api.py                 public /api/status (Django Ninja)
  admin.py               Unfold admin classes and status badges
  dashboard.py           context for the admin home page
  management/commands/   run_checks (worker), seed_demo
  templates/monitor/     public status page
  static/monitor/        admin glass theme
templates/admin/         admin home page template
docs/screenshots/        images used in this README
```

To add a check type: add a value to `Service.CheckType`, write a function in `monitor/checks.py` that returns
`""` when healthy or a short reason when not, register it in `_CHECKS`, and add a label in `monitor/api.py`.
An import-time assertion fails if a type has no implementation.

## License

[MIT](LICENSE) © 2026 Mohammad Zarif. See [CHANGELOG.md](CHANGELOG.md) for release notes.
