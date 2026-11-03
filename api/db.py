"""Database URL resolution with a local-only safety guard.

Kohu's seed, ingest and migrations delete and rewrite rows. A stray
DATABASE_URL inherited from another project's shell could point those
statements at a database that is not Kohu's. Every entry point therefore
resolves its URL here, and a host other than localhost is refused unless
the operator opts in with KOHU_ALLOW_REMOTE_DB=1 (a deployment that owns
its database sets this on purpose).
"""

import os
import sys
from urllib.parse import urlparse

DEFAULT_DATABASE_URL = "postgresql://postgres@localhost:5432/kohu"
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", ""}


class UnsafeDatabaseURL(RuntimeError):
    pass


def check_url(url):
    """Return url when it is local or remote use is opted in; else raise."""
    host = urlparse(url).hostname or ""
    if host in LOCAL_HOSTS:
        return url
    if os.environ.get("KOHU_ALLOW_REMOTE_DB") == "1":
        return url
    raise UnsafeDatabaseURL(
        "refusing non-local DATABASE_URL host %r; set KOHU_ALLOW_REMOTE_DB=1 "
        "only if this database belongs to Kohu" % host)


def database_url(explicit=None):
    return check_url(explicit or os.environ.get("DATABASE_URL")
                     or DEFAULT_DATABASE_URL)


if __name__ == "__main__":
    # `python api/db.py` prints only the host, never credentials.
    try:
        print("database host:", urlparse(database_url()).hostname)
    except UnsafeDatabaseURL as e:
        print("error:", e, file=sys.stderr)
        sys.exit(1)
