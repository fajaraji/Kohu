#!/usr/bin/env bash
# Kohu seed: migrate, ingest the committed corpus, print chunk counts.
# The corpus files are committed, so no network is needed. Model results
# (Spark page reading, video steps, conflict judgments) are read from
# corpus/spark-cache/ and never re-requested; without a cache entry and
# without META_API_KEY, ingest falls back to labeled non-model text.
# Safe to re-run. Refuses a non-local DATABASE_URL unless
# KOHU_ALLOW_REMOTE_DB=1.
set -euo pipefail
cd "$(dirname "$0")"

# .env fills gaps only: an explicitly exported variable always wins.
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

echo "Kohu corpus: public documents and data with a simulated scenario."
echo "  PostHog handbook pages (MIT-style license), one as a scanned copy"
echo "  ASEAN report (World Bank data, company-wide license, simulated)"
echo "  ASEAN dataset (World Bank data, seat-limited license, simulated)"
echo "  Expansion deck, team performance, refund process, demo video (simulated)"
if [ -n "${META_API_KEY:-}" ]; then
  echo "META_API_KEY: set (value hidden)."
else
  echo "META_API_KEY: not set. Cached model results are used; nothing new is requested."
fi

"$PY" - <<'PYEOF'
import sys
need = ["psycopg", "pymupdf", "pptx", "openpyxl", "PIL", "fastapi"]
missing = []
for m in need:
    try:
        __import__(m)
    except ImportError:
        missing.append(m)
if missing:
    sys.exit("missing python modules: %s -- pip install -r api/requirements.txt"
             % " ".join(missing))
PYEOF

echo "== 1/4 verify corpus files =="
"$PY" corpus/verify_corpus.py

echo "== 2/4 migrate =="
"$PY" api/migrate.py up

echo "== 3/4 ingest =="
"$PY" api/ingest.py

echo "== 4/4 counts =="
"$PY" - <<'PYEOF'
import json, os, sys
sys.path.insert(0, "api")
import db, psycopg
manifest = json.load(open("corpus/manifest.json", encoding="utf-8"))
expected = {e["id"]: e.get("expected_chunks") for e in manifest["entries"]}
with psycopg.connect(db.database_url()) as c:
    rows = dict(c.execute(
        "SELECT source_id, count(*) FROM chunks GROUP BY source_id").fetchall())
bad = False
for sid, exp in expected.items():
    got = rows.get(sid, 0)
    ok = exp is None or got == exp
    bad = bad or not ok
    print(f"{sid}: {got}" + ("" if exp is None else f" (expected {exp})")
          + ("" if ok else " MISMATCH"))
print(f"total: {sum(rows.values())} chunks")
raise SystemExit(1 if bad else 0)
PYEOF

echo "Seed check OK."
