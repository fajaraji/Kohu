#!/usr/bin/env bash
# Migrate, optionally seed, then serve. DATABASE_URL must point at a
# Postgres 16 with pg_trgm available. A non-local host also needs
# KOHU_ALLOW_REMOTE_DB=1 (the safety guard in api/db.py).
set -euo pipefail
python api/migrate.py up
if [ "${KOHU_SEED_ON_START:-0}" = "1" ]; then
  ./seed.sh
fi
exec uvicorn api.app:app --host 0.0.0.0 --port "${PORT:-8000}"
