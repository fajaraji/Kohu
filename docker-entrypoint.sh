#!/usr/bin/env bash
# Migrate, optionally seed, then serve. DATABASE_URL must point at a
# Postgres 16 with pg_trgm available. A non-local host also needs
# KOHU_ALLOW_REMOTE_DB=1 (the safety guard in api/db.py).
set -euo pipefail

# The database may still be starting; retry for up to about 60 s.
for i in $(seq 1 30); do
  if python api/migrate.py up; then break; fi
  if [ "$i" = 30 ]; then echo "database not reachable, giving up" >&2; exit 1; fi
  echo "waiting for the database ($i)..." >&2
  sleep 2
done
if [ "${KOHU_SEED_ON_START:-0}" = "1" ]; then
  ./seed.sh
fi
exec uvicorn api.app:app --host 0.0.0.0 --port "${PORT:-8000}"
