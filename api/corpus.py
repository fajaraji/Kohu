"""Corpus manifest access shared by ingest, policy, retrieval and the API.

corpus/manifest.json is the tracked source of truth. Videos uploaded at
run time are recorded in corpus/manifest.local.json (git-ignored) and
merged on read, so an upload never edits a tracked file.
"""

import json
import pathlib
import threading

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
DEFAULT_CORPUS = REPO / "corpus"
LOCAL_NAME = "manifest.local.json"
_lock = threading.Lock()


def load_manifest(corpus_dir=DEFAULT_CORPUS):
    corpus_dir = pathlib.Path(corpus_dir)
    with open(corpus_dir / "manifest.json", encoding="utf-8") as f:
        manifest = json.load(f)
    local = corpus_dir / LOCAL_NAME
    if local.exists():
        extra = json.loads(local.read_text(encoding="utf-8"))
        known = {e["id"] for e in manifest["entries"]}
        manifest["entries"] = manifest["entries"] + [
            e for e in extra.get("entries", []) if e["id"] not in known]
    return manifest


def entry(source_id, corpus_dir=DEFAULT_CORPUS):
    for e in load_manifest(corpus_dir)["entries"]:
        if e["id"] == source_id:
            return e
    return None


def add_local_entry(new_entry, corpus_dir=DEFAULT_CORPUS):
    """Record an uploaded source in manifest.local.json (idempotent)."""
    local = pathlib.Path(corpus_dir) / LOCAL_NAME
    with _lock:
        data = (json.loads(local.read_text(encoding="utf-8"))
                if local.exists() else {"entries": []})
        data["entries"] = [e for e in data["entries"]
                           if e["id"] != new_entry["id"]] + [new_entry]
        local.write_text(json.dumps(data, indent=1), encoding="utf-8")


def source_path(e, corpus_dir=DEFAULT_CORPUS):
    return pathlib.Path(corpus_dir) / e["filename"]


def titles(corpus_dir=DEFAULT_CORPUS):
    return {e["id"]: e.get("title", e["id"])
            for e in load_manifest(corpus_dir)["entries"]}
