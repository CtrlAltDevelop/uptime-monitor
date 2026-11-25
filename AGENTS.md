# AGENTS.md — uptime-monitor

Canonical instructions for any AI agent or human working in this repo.
`CLAUDE.md` is a pointer only; new rules go **here**.

A self-hosted uptime monitor: Django, Django Ninja, the Unfold admin. Services are defined in the admin, a background
worker records health-check results, and a public status page shows only "is it up, and for how long". Read `README.md` first.

## Commands (`make help` lists all)

- `make check` — Django system check plus a check that no migration is missing.
- `make test` — the test suite. CI runs both.
- `make run` / `make worker` — web server and health-check worker. `make demo-site` rebuilds the static demo in `docs/demo/`.

## Rules

- The public status page and public API never expose hosts, ports or error messages — only up/down and duration.
- A new check type needs a test and an entry in the README feature list.
- Schema changes ship as a migration; `make check` must pass.
- CI workflows are reusable ones from `CtrlAltDevelop/ci-workflows`; change checks there, not here.
