"""Vercel entry point: the whole Kohu app (API and UI) as one function.

Vercel sets VERCEL=1. On Vercel, Kohu runs as the public demo: remote
Postgres allowed, client IP from Vercel's x-real-ip, Meta usage counted
in the database, and a spend stop of 10 USD unless set otherwise. Only
DATABASE_URL, KOHU_SESSION_SECRET and META_API_KEY need to be set in the
Vercel project. Locally, run `uvicorn api.app:app` as before.
"""

import os

if os.environ.get("VERCEL") == "1":
    for key, value in {
        "KOHU_PUBLIC_DEMO": "1",
        "KOHU_ALLOW_REMOTE_DB": "1",
        "KOHU_BEHIND_VERCEL": "1",
        "KOHU_USAGE_IN_DB": "1",
        "META_SPEND_LIMIT_USD": "10",
        "META_USAGE_LOG": "/tmp/meta-usage.jsonl",
    }.items():
        os.environ.setdefault(key, value)

from api.app import app  # noqa: E402,F401
