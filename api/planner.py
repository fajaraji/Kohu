"""Kohu planner (P30): split a query into per-source subtasks, log under a run id.

Contract (PLAN.md section 3, PRD.md FR3/FR7, TASK_CHECKLIST.md T30):
  planner decomposes each question into subtasks per source type and
  decides which stores to hit. Every subtask is logged under a run id
  so the run log shows planning decisions (PLAN.md "run log" rule).

Source types come from corpus/manifest.json citation anchor kinds:
  anchor "page"       -> source_type "pdf"   (handbook, process-report,
                         licensed-report, scanned-note; cite p.N)
  anchor "slide"      -> source_type "deck"  (product-deck, sales-deck;
                         cite slide N)
  anchor "cell-range" -> source_type "sheet" (licensed-market,
                         performance; cite Sheet!A1:B2)

Store decision: all subtasks hit the single pgvector "chunks" store with
a source_id filter (the pre-filter P31 applies per role). The planner
names the store and the source list explicitly so the log shows the
decision instead of implying it.

Usage:
  python api/planner.py "What was Q3 growth for product X and what drives it?"
  python api/planner.py --demo      # fixed demo query, log + print subtasks
  python api/planner.py --verify    # demo query + read-back asserts, exit 1 on fail
"""

import argparse
import json
import os
import pathlib
import re
import sys
import uuid

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import migrate  # noqa: E402  (same-dir runner; once-per-process ensure)

REPO = HERE.parent
DEFAULT_CORPUS = REPO / "corpus"
DEFAULT_DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://postgres@localhost:5432/kohu")

DEMO_QUERY = "What was Viet Nam's GDP growth in 2023?"

# Fixed subtask order so logs read the same every run.
ANCHOR_ORDER = ("page", "slide", "cell-range")
SOURCE_TYPE = {"page": "pdf", "slide": "deck", "cell-range": "sheet"}

# Rationale templates: why each store matters for a growth/drivers query.
# Kept generic (no per-query branching) so the planner is deterministic
# and the fixed demo query always yields the same three subtasks.
RATIONALE = {
    "pdf": ("Search handbook, process-report, licensed-report and scanned "
            "note pages for growth drivers and background; cite p.N."),
    "deck": ("Search product and sales decks for stated growth figures and "
             "chart captions; cite slide N (conflict watch: sales slide 7)."),
    "sheet": ("Search licensed-market and performance row windows for the "
              "citable Q3 numbers; cite Sheet!A1:B2 ranges "
              "(conflict watch: Q3-Growth!E12)."),
}


def load_manifest(corpus_dir):
    with open(pathlib.Path(corpus_dir) / "manifest.json",
              encoding="utf-8") as f:
        return json.load(f)


def estimate_tokens(text):
    """Offline word-count token estimate for run_steps (P12/A07).

    Deterministic and dependency-free: whitespace-separated words.
    Local pipeline steps log these estimates; Spark-backed steps add
    the model API's real usage totals when the response carries them.
    """
    if not text:
        return 0
    return len(str(text).split())


def focus_terms(query):
    """Lowercased keyword signals quoted into each subtask's query_hint."""
    q = query.lower()
    terms = []
    for pat in (r"q[1-4]", r"growth", r"product\s*x", r"driv\w*",
                r"licensed", r"performance", r"conflict"):
        m = re.search(pat, q)
        if m:
            terms.append(re.sub(r"\s+", " ", m.group(0)).strip())
    return terms


def plan_query(query, manifest, run_id=None):
    """Split query into per-source-type subtasks. No I/O, no logging.

    Returns (run_id, subtasks) where each subtask is a dict with
    subtask_index, source_type, anchor, store, sources, query_hint,
    rationale. Raises ValueError on empty query.
    """
    if not query or not query.strip():
        raise ValueError("query must be a non-empty string")
    run_id = run_id or uuid.uuid4().hex
    by_anchor = {}
    for entry in manifest["entries"]:
        anchor = (entry.get("citation_anchors")
                  or entry.get("citationAnchors") or {}).get("type")
        if anchor in ANCHOR_ORDER:
            by_anchor.setdefault(anchor, []).append(entry["id"])
    terms = focus_terms(query)
    hint_suffix = (" [focus: %s]" % ", ".join(terms)) if terms else ""
    subtasks = []
    for i, anchor in enumerate(ANCHOR_ORDER):
        sources = sorted(by_anchor.get(anchor, []))
        if not sources:
            continue
        stype = SOURCE_TYPE[anchor]
        subtasks.append({
            "subtask_index": i,
            "source_type": stype,
            "anchor": anchor,
            "store": "chunks",
            "sources": sources,
            "query_hint": query.strip() + hint_suffix,
            "rationale": RATIONALE[stype],
        })
    return run_id, subtasks


def plan_and_log(query, database_url, corpus_dir=DEFAULT_CORPUS,
                 run_id=None):
    """Plan the query and persist the run + subtasks + planner step.

    One transaction: runs row, planner_subtasks rows, one run_steps row
    with agent='planner'. Returns (run_id, subtasks).
    """
    import psycopg

    manifest = load_manifest(corpus_dir)
    run_id, subtasks = plan_query(query, manifest, run_id=run_id)
    migrate.ensure_up_once(database_url)
    with psycopg.connect(database_url) as conn:
        with conn.transaction():
            conn.execute(
                "INSERT INTO runs (run_id, query) VALUES (%s, %s) "
                "ON CONFLICT (run_id) DO UPDATE SET query = EXCLUDED.query",
                (run_id, query.strip()))
            conn.execute("DELETE FROM planner_subtasks WHERE run_id = %s",
                         (run_id,))
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO planner_subtasks "
                    "(run_id, subtask_index, source_type, anchor, store, "
                    " sources, query_hint, rationale) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                    [(run_id, s["subtask_index"], s["source_type"],
                      s["anchor"], s["store"], s["sources"],
                      s["query_hint"], s["rationale"]) for s in subtasks])
            conn.execute(
                "INSERT INTO run_steps (run_id, step_index, agent, detail) "
                "VALUES (%s, %s, 'planner', %s) "
                "ON CONFLICT (run_id, step_index) DO UPDATE "
                "SET detail = EXCLUDED.detail",
                (run_id, 0, json.dumps({
                    "query": query.strip(),
                    "subtasks": [
                        {"source_type": s["source_type"],
                         "anchor": s["anchor"],
                         "store": s["store"],
                         "sources": s["sources"]} for s in subtasks],
                    "input_tokens": estimate_tokens(query),
                    "output_tokens": estimate_tokens(json.dumps(
                        [{"query_hint": s["query_hint"],
                          "rationale": s["rationale"]}
                         for s in subtasks])),
                })))
    return run_id, subtasks


def read_subtasks(run_id, database_url):
    """Read back logged subtasks for a run id in index order."""
    import psycopg
    with psycopg.connect(database_url) as conn:
        rows = conn.execute(
            "SELECT subtask_index, source_type, anchor, store, sources, "
            "query_hint, rationale FROM planner_subtasks "
            "WHERE run_id = %s ORDER BY subtask_index",
            (run_id,)).fetchall()
    return [{"subtask_index": r[0], "source_type": r[1], "anchor": r[2],
             "store": r[3], "sources": list(r[4]),
             "query_hint": r[5], "rationale": r[6]} for r in rows]


def print_plan(run_id, query, subtasks):
    print("run_id: %s" % run_id)
    print("query: %s" % query.strip())
    for s in subtasks:
        print("subtask %d: [%s/%s] store=%s sources=%s" % (
            s["subtask_index"], s["source_type"], s["anchor"],
            s["store"], ",".join(s["sources"])))
        print("  hint: %s" % s["query_hint"])
        print("  why: %s" % s["rationale"])


def cmd_verify(database_url, corpus_dir):
    """Fixed demo query: log, read back, assert 3 subtasks cover 8 sources."""
    manifest = load_manifest(corpus_dir)
    expected_sources = sorted(e["id"] for e in manifest["entries"])
    run_id, subtasks = plan_and_log(DEMO_QUERY, database_url, corpus_dir)
    logged = read_subtasks(run_id, database_url)
    print_plan(run_id, DEMO_QUERY, logged)
    got_sources = sorted({s for t in logged for s in t["sources"]})
    anchors = [t["anchor"] for t in logged]
    ok = (len(logged) == 3
          and anchors == ["page", "slide", "cell-range"]
          and got_sources == expected_sources
          and all(t["store"] == "chunks" for t in logged))
    print("ASSERT 3 subtasks (page/slide/cell-range) covering 8 sources: %s"
          % ("PASS" if ok else
             "FAIL (anchors=%r sources=%r)" % (anchors, got_sources)))
    return 0 if ok else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description="Kohu planner (P30)")
    parser.add_argument("query", nargs="?", default=None)
    parser.add_argument("--demo", action="store_true",
                        help="plan + log the fixed demo query and print it")
    parser.add_argument("--verify", action="store_true",
                        help="demo query + read-back asserts (exit 1 on fail)")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--database-url", default=os.environ.get(
        "DATABASE_URL", DEFAULT_DATABASE_URL))
    parser.add_argument("--corpus", default=str(DEFAULT_CORPUS))
    args = parser.parse_args(argv)

    if args.verify:
        return cmd_verify(args.database_url, args.corpus)
    if args.demo:
        run_id, subtasks = plan_and_log(DEMO_QUERY, args.database_url,
                                        args.corpus, run_id=args.run_id)
        print_plan(run_id, DEMO_QUERY, read_subtasks(run_id,
                                                     args.database_url))
        return 0
    if not args.query:
        parser.error("need a query positional arg, --demo, or --verify")
    run_id, _ = plan_and_log(args.query, args.database_url, args.corpus,
                             run_id=args.run_id)
    print_plan(run_id, args.query, read_subtasks(run_id, args.database_url))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
