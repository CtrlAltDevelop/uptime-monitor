# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Docker support: `Dockerfile` and `compose.yaml` that run the web server and the check worker as two containers
  sharing one data volume, with a health check and a non-root user.
- `Makefile` with shortcuts for development (`make run`, `make worker`, `make test`, ...) and Docker
  (`make up`, `make down`, `make logs`, ...).
- `SECURITY.md` with the vulnerability reporting process and a hardening checklist.
- `.env.example` and `make env`, which creates `.env` with a generated `SECRET_KEY`.
- WhiteNoise, so static files (the admin theme) are served without a separate web server.

### Changed
- Dependencies are managed with [uv](https://docs.astral.sh/uv/): `pyproject.toml` and `uv.lock` replace
  `requirements.txt`.

## [0.1.0] - 2026-11-08

### Added
- Services and categories managed in the Django admin.
- 11 check types: ping, TCP, HTTP, HTTP keyword, DNS, SSL certificate expiry, SSH, SMTP, Redis, PostgreSQL and
  MySQL/MariaDB.
- Background worker (`manage.py run_checks`) with per-service interval and timeout, parallel checks and automatic
  pruning of old results (`RESULT_RETENTION_DAYS`).
- Public status page at `/`: glass-style grid that scales to the screen (TV friendly), problems first, 30-day
  history bars, auto refresh and full-screen on double-click.
- Public JSON API at `/api/status` that never exposes targets, ports or error details, cached for 15 seconds.
- Unfold admin with a custom glass theme, a dashboard with live counters and recent failures, and status badges.
- `manage.py seed_demo`, which creates 50 demo services that monitor well-known public hosts.
- Test suite covering every protocol check, validation rules, the worker cycle, the seed command and the public API.
- MIT license.
