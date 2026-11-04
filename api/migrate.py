"""Kohu migration runner: applies api/migrations/*.sql in filename order.

Usage:
  python api/migrate.py            # apply pending migrations (up)
  python api/migrate.py up         # same as above
  python api/migrate.py down       # roll back the latest applied migration
  python api/migrate.py down --steps 2

Connection: DATABASE_URL env var, or --database-url.
Default: postgresql://postgres@localhost:5432/kohu

Conventions:
  - Up files:   NNNN_name.sql        (applied in sorted order)
  - Down files: NNNN_name.down.sql   (rollback for that version)
  - Applied versions are recorded in schema_migrations inside the same
    transaction as the migration, so a failed run never marks a version
    done and a retry is safe (SQL files are also IF NOT EXISTS).
"""

import argparse
import os
import pathlib
import sys
import threading

try:
    import psycopg
except ImportError:
    print("error: psycopg is not installed (pip install -r api/requirements.txt)",
          file=sys.stderr)
    sys.exit(2)

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import db as _db  # noqa: E402  (local-only DATABASE_URL guard)

MIGRATIONS_DIR = pathlib.Path(__file__).resolve().parent / "migrations"
DEFAULT_DATABASE_URL = "postgresql://postgres@localhost:5432/kohu"


def up_files():
    return sorted(
        p for p in MIGRATIONS_DIR.glob("*.sql")
        if not p.name.endswith(".down.sql")
    )


def down_file_for(version: str) -> pathlib.Path:
    return MIGRATIONS_DIR / f"{version}.down.sql"


def ensure_database(database_url: str) -> None:
    """Create the target database if it is missing (never drops anything).

    Connects to the maintenance database on the same server, so a fresh
    clone can seed without a manual createdb step. Refuses unsafe names.
    """
    import re
    from urllib.parse import urlparse, urlunparse

    parts = urlparse(database_url)
    dbname = parts.path.lstrip("/") or "postgres"
    if dbname == "postgres":
        return
    if not re.fullmatch(r"[A-Za-z0-9_-]+", dbname):
        print(f"error: refusing to create database {dbname!r}", file=sys.stderr)
        sys.exit(1)
    maint = urlunparse(parts._replace(path="/postgres"))
    with psycopg.connect(maint, autocommit=True) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (dbname,),
        ).fetchone()
        if not exists:
            conn.execute(f'CREATE DATABASE "{dbname}"')
            print(f"created database {dbname}")


def ensure_tracking(conn) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "  version TEXT PRIMARY KEY,"
        "  applied_at TIMESTAMPTZ NOT NULL DEFAULT now()"
        ")"
    )


def applied_versions(conn) -> list:
    ensure_tracking(conn)
    rows = conn.execute(
        "SELECT version FROM schema_migrations ORDER BY version"
    ).fetchall()
    return [r[0] for r in rows]


def cmd_up(database_url: str) -> int:
    _db.check_url(database_url)
    ensure_database(database_url)
    with psycopg.connect(database_url) as conn:
        done = set(applied_versions(conn))
        pending = [p for p in up_files() if p.stem not in done]
        if not pending:
            print("migrate up: nothing pending.")
            return 0
        for path in pending:
            version = path.stem
            sql = path.read_text(encoding="utf-8")
            with conn.transaction():
                conn.execute(sql)
                conn.execute(
                    "INSERT INTO schema_migrations (version) VALUES (%s)",
                    (version,),
                )
            print(f"migrate up: applied {version}")
        return 0


# Once-per-process guard for request paths (P12/A07): the ask pipeline
# used to call cmd_up from every module on every request (planner,
# retrieval, policy, conflict — 5+ migration runs per ask). Request code
# calls ensure_up_once instead: the migration runs at most once per
# database URL per process (server startup covers the steady state, so
# requests perform no migration runs at all). Failures propagate and are
# never cached, so a DB-down request still surfaces as unavailable.
_ensured_urls = set()
_ensured_lock = threading.Lock()


def ensure_up_once(database_url: str) -> int:
    with _ensured_lock:
        if database_url in _ensured_urls:
            return 0
    rc = cmd_up(database_url)
    with _ensured_lock:
        _ensured_urls.add(database_url)
    return rc


def cmd_down(database_url: str, steps: int) -> int:
    _db.check_url(database_url)
    with psycopg.connect(database_url) as conn:
        done = applied_versions(conn)
        if not done:
            print("migrate down: nothing applied.")
            return 0
        targets = done[-steps:] if steps < len(done) else done
        for version in reversed(targets):
            down_path = down_file_for(version)
            if not down_path.exists():
                print(f"error: no down file for {version} "
                      f"(expected {down_path.name})", file=sys.stderr)
                return 1
            sql = down_path.read_text(encoding="utf-8")
            with conn.transaction():
                conn.execute(sql)
                conn.execute(
                    "DELETE FROM schema_migrations WHERE version = %s",
                    (version,),
                )
            print(f"migrate down: rolled back {version}")
        return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Kohu migration runner")
    parser.add_argument("direction", nargs="?", default="up",
                        choices=["up", "down"])
    parser.add_argument("--steps", type=int, default=1,
                        help="migrations to roll back (down only)")
    parser.add_argument("--database-url", default=os.environ.get(
        "DATABASE_URL", DEFAULT_DATABASE_URL))
    args = parser.parse_args(argv)

    if not MIGRATIONS_DIR.is_dir():
        print(f"error: migrations dir not found: {MIGRATIONS_DIR}",
              file=sys.stderr)
        return 1
    try:
        if args.direction == "up":
            return cmd_up(args.database_url)
        return cmd_down(args.database_url, args.steps)
    except psycopg.OperationalError as e:
        print(f"error: cannot connect to Postgres: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
