"""Reset the demo database to the start state for recording the video.

Reopens every conflict and removes uploaded videos (manifest.local.json
entries, their rows and derived files). Local database only.
"""

import json
import pathlib
import shutil
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "api"))
import corpus  # noqa: E402
import db  # noqa: E402

import psycopg  # noqa: E402

local = REPO / "corpus" / corpus.LOCAL_NAME
ids = []
if local.exists():
    ids = [e["id"] for e in json.loads(local.read_text())["entries"]]
    local.unlink()
with psycopg.connect(db.database_url()) as c:
    c.execute("UPDATE conflicts SET status = 'open', winner = NULL, note = "
              "NULL, resolved_by = NULL, resolved_at = NULL")
    for sid in ids:
        for t in ("chunks", "guide_steps", "transcripts", "video_jobs"):
            c.execute("DELETE FROM %s WHERE source_id = %%s" % t, (sid,))
        c.execute("DELETE FROM conflicts WHERE a_source = %s OR b_source = %s",
                  (sid, sid))
    c.commit()
for sid in ids:
    shutil.rmtree(REPO / "corpus" / "derived" / sid, ignore_errors=True)
    f = REPO / "corpus" / "uploads" / (sid + ".mp4")
    if f.exists():
        f.unlink()
print("reset: conflicts reopened, removed uploads", ids)
