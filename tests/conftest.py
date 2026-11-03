import os
import pathlib
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "api"))
FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "meta"

# Tests never reach a foreign database or the Meta API by accident.
for var in ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID", "APP_PASSWORD",
            "META_API_KEY"):
    os.environ.pop(var, None)
TEST_DB = os.environ.get("KOHU_TEST_DATABASE_URL",
                         "postgresql://postgres@localhost:5432/kohu_test")
os.environ["DATABASE_URL"] = TEST_DB
os.environ.setdefault("KOHU_SESSION_SECRET", "test-secret")
os.environ["KOHU_SPARK_CACHE"] = str(REPO / "corpus" / "spark-cache")


@pytest.fixture(scope="session")
def seeded_db():
    """kohu_test database migrated and ingested without model calls."""
    import db
    import ingest
    url = db.database_url(TEST_DB)
    ingest.ingest(REPO / "corpus", url, no_spark=True)
    return url
