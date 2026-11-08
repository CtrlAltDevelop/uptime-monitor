# Security Policy

## Supported versions

Security fixes are applied to the latest release and to `main`. Please update before reporting.

| Version | Supported |
| --- | --- |
| latest release / `main` | yes |
| older releases | no |

## Reporting a vulnerability

**Please do not open a public issue for security problems.**

Use GitHub's private reporting: open the repository's **Security** tab and choose **Report a vulnerability**
(a private security advisory). If that is not available, contact the maintainer privately through the contact
details on their GitHub profile.

Please include:

- what you found and where (file, endpoint or setting);
- steps to reproduce, or a proof of concept;
- the impact you expect, and the version or commit you tested.

This is a volunteer-maintained project, so responses are best effort. Reports are acknowledged as soon as
possible, fixed in order of severity, and credited in the changelog unless you prefer to stay anonymous.

## Scope

In scope: the public status page and `/api/status` (for example leaking targets, ports or error text), the admin
integration, the check implementations (for example command or argument injection through a target), the
Docker image and the default configuration.

Out of scope: problems that need a malicious **admin** (see below), vulnerabilities in Django, Unfold or other
dependencies themselves (report those upstream; we will bump the lock file), and denial of service by exhausting
your own server's resources.

## Security model

- **Admins are trusted.** Check targets are entered in the admin and probed from the server's network. An admin
  can therefore make the server connect to internal hosts (server-side request forgery by design). Give admin
  access only to people you trust, and restrict `/admin/` by network where you can.
- **The public surface is read-only and minimal.** `/` and `/api/status` return only name, category, check kind,
  status, last response time and uptime percentages. Targets, ports and error details stay in the admin.
  Services can also be hidden entirely with *Show on public page*.
- **Inputs are validated.** Hosts are checked against a strict pattern before ping or TCP checks, URLs must be
  `http://` or `https://`, and `ping` is executed with a fixed argument list (no shell).
- **Secrets come from the environment.** The app refuses to start without `SECRET_KEY` unless `DEBUG=1`.
  Nothing secret is committed; `.env` is git-ignored.

## Hardening checklist for operators

- [ ] Set a long random `SECRET_KEY` (`make env` generates one) and never run with `DEBUG=1` in production.
- [ ] Set `ALLOWED_HOSTS` and, behind an HTTPS proxy, `CSRF_TRUSTED_ORIGINS`.
- [ ] Serve the site over HTTPS only, and use a strong, unique admin password.
- [ ] Limit access to `/admin/` (VPN, IP allow-list or proxy authentication).
- [ ] Do not publish the worker or the SQLite database file; back up the data volume.
- [ ] Keep dependencies current: `uv lock --upgrade && make test`, then rebuild the image.
- [ ] Rotate `SECRET_KEY` and admin passwords if you suspect they leaked.
