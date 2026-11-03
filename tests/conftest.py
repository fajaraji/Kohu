import os
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "api"))
FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "meta"

# Tests never reach a real database or the Meta API by accident.
os.environ.pop("CLOUDFLARE_API_TOKEN", None)
os.environ.pop("CLOUDFLARE_ACCOUNT_ID", None)
os.environ["DATABASE_URL"] = os.environ.get(
    "KOHU_TEST_DATABASE_URL", "postgresql://postgres@localhost:5432/kohu_test")
os.environ.setdefault("KOHU_SESSION_SECRET", "test-secret")
