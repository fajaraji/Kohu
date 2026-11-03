#!/usr/bin/env bash
# Kohu seed (Phase 2): generate corpus, migrate, ingest, print counts.
# Safe with no keys (ingest falls back to local-only parse) and safe to
# re-run (corpus builds overwrite, migrate/ingest are idempotent).
# Never drops data; to reseed from scratch, drop the database first.
set -euo pipefail
cd "$(dirname "$0")"

# .env fills gaps only: an explicitly exported variable always wins
# (e.g. DATABASE_URL pointing at a test server).
if [ -f .env ]; then
  while IFS='=' read -r key value || [ -n "$key" ]; do
    value="${value%$'\r'}"
    case "$key" in \#*|'') continue;; esac
    if [ -z "${!key:-}" ]; then export "$key=$value"; fi
  done < .env
fi

PY="${PYTHON:-python}"

# Safety: refuse a non-local DATABASE_URL unless KOHU_ALLOW_REMOTE_DB=1.
"$PY" api/db.py

echo "Kohu seed plan (synthetic corpus, all DEMO DATA - FICTIONAL):"
echo " 1. handbook.pdf            open-internal       Employee handbook, tables"
echo " 2. process-report.pdf      open-internal       Process report, charts"
echo " 3. product-deck/           open-internal       Product slide deck, 10 slides"
echo " 4. sales-deck/             open-internal       Sales review deck, embedded chart"
echo " 5. licensed-market.xlsx    licensed-only       Market dataset, cells A1:F200"
echo " 6. licensed-report.pdf     licensed-only       Licensed report quoting dataset"
echo " 7. performance.xlsx        manager-restricted  Team performance summary"
echo " 8. scanned-note.pdf        open-internal       Scanned page, OCR path"
echo "Conflict pair: sales-deck Q3 figure vs licensed-market.xlsx Q3 figure (flags once)."
echo ""

if [ -n "${META_API_KEY:-}" ]; then
  echo "META_API_KEY: set (value hidden)."
else
  echo "META_API_KEY: not set. Ingest runs local-only; Spark captions need a key."
fi
echo ""

"$PY" - <<'EOF'
import sys
need = ["psycopg", "pypdf", "pptx", "openpyxl", "reportlab", "PIL"]
def _missing(m):
    try:
        __import__(m)
        return False
    except ImportError:
        return True
missing = [m for m in need if _missing(m)]
if missing:
    sys.exit("missing python modules: %s -- pip install -r api/requirements.txt"
             % " ".join(missing))
EOF

echo "== 1/3 corpus =="
"$PY" corpus/build_pdfs.py
"$PY" corpus/build_decks.py
"$PY" corpus/build_sheets.py
"$PY" corpus/build_scanned.py
"$PY" corpus/build_licensed_report.py

echo "== 2/3 migrate =="
"$PY" api/migrate.py up

echo "== 3/3 ingest =="
"$PY" api/ingest.py

echo "== counts =="
"$PY" - <<'EOF'
import json, os, psycopg
manifest = json.load(open("corpus/manifest.json", encoding="utf-8"))
expected = {e["id"]: e["expected_chunks"] for e in manifest["entries"]}
url = os.environ.get("DATABASE_URL", "postgresql://postgres@localhost:5432/kohu")
with psycopg.connect(url) as c:
    rows = dict(c.execute(
        "SELECT source_id, count(*) FROM chunks GROUP BY source_id").fetchall())
total, bad = 0, False
for sid, exp in expected.items():
    got = rows.get(sid, 0)
    total += got
    mark = "ok" if got == exp else "MISMATCH"
    bad = bad or got != exp
    print(f"{sid}: {got} (expected {exp}) {mark}")
print(f"total: {total} chunks")
raise SystemExit(1 if bad else 0)
EOF

echo "Seed check OK."
