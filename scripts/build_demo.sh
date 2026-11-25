#!/usr/bin/env bash
# Rebuild the static live demo (docs/demo/) used by the GitHub Pages site.
# Seeds a throwaway database, snapshots /api/status, and copies the real public
# status template with its fetch pointed at that snapshot. Your local DB is untouched.
set -euo pipefail
cd "$(dirname "$0")/.."

export DEBUG=1 DB_PATH="$(mktemp -d)/demo.sqlite3"
manage="uv run python manage.py"

$manage migrate -v0
$manage seed_realistic >/dev/null

mkdir -p docs/demo
$manage shell -c "
from django.test import Client
import sys
sys.stdout.write(Client().get('/api/status', HTTP_HOST='localhost').content.decode())
" 2>/dev/null | grep '^{' > docs/demo/status.json

uv run python - <<'PY'
from pathlib import Path

src = Path("monitor/templates/monitor/index.html").read_text()

def swap(text, old, new):
    assert old in text, f"template changed, update build_demo.sh: {old!r}"
    return text.replace(old, new, 1)

# Timestamps in the snapshot are old; shift them so the page looks live.
rebase = """function rebase(d) {
  const off = Date.now() - new Date(d.updated_at);
  const shift = iso => iso && new Date(new Date(iso).getTime() + off).toISOString();
  d.updated_at = shift(d.updated_at);
  d.categories.forEach(c => c.services.forEach(s => { s.last_checked = shift(s.last_checked); }));
  return d;
}
async function load() {"""

out = swap(src, 'async function load() {', rebase)
out = swap(out, 'fetch("/api/status")', 'fetch("status.json")')
out = swap(out, "render(await r.json())", "render(rebase(await r.json()))")
out = swap(out, "<title>Service status</title>", "<title>Live demo · Uptime Monitor</title>")
out = swap(out, "· double-click for full screen</div>",
    '· double-click for full screen · <a href="../" style="color:inherit">demo snapshot, back to project</a></div>')
Path("docs/demo/index.html").write_text(out)
PY

echo "docs/demo rebuilt"
