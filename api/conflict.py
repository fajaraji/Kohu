"""Kohu conflict flagger (P32b): flag the seeded pair exactly once.

Contract (PLAN.md section 4, PRD.md FR6, TASK_CHECKLIST.md T34):
  the seeded sales-deck-vs-licensed-sheet Q3 disagreement flags exactly
  once and creates one Steward task. The agent never invents a resolution
  (status 'open', resolution 'none'). Repeat fires for the same pair are
  INSERT ... ON CONFLICT DO NOTHING on steward_tasks.conflict_id, so the
  table can never hold a second task for the pair.

Fire condition: the enforced (post-policy) result set contains BOTH the
side_a chunk (sales-deck slide 7) and a side_b chunk whose cell range
contains the seeded E12 cell, and both clear the relevance gate
(retrieval.MIN_RELEVANCE_SCORE) — score-0 filler can never flag, so only
cited-quality evidence fires. Detection is anchor-based, not figure-text
based, so reworded figures still match and nothing is auto-resolved.

Usage:
  python api/conflict.py --probe   # fires once, second run stays at one
"""

import argparse
import json
import os
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import migrate  # noqa: E402  (same-dir runner; once-per-process ensure)
import planner  # noqa: E402  (run creation for the probe)
import policy  # noqa: E402  (end-to-end probe input)
import retrieval  # noqa: E402

REPO = HERE.parent
DEFAULT_CORPUS = REPO / "corpus"
DEFAULT_DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://postgres@localhost:5432/kohu")


def _cell_in_range(cell_range, cell):
    """True when e.g. 'Q3-Growth!A2:F21' contains 'E12'."""
    m = re.fullmatch(r"(.+)!([A-Z]+)(\d+):([A-Z]+)(\d+)", cell_range or "")
    c = re.fullmatch(r"([A-Z]+)(\d+)", cell or "")
    if not m or not c:
        return False
    _, c1, r1, c2, r2 = m.groups()
    col, row = c.groups()
    return c1 <= col <= c2 and int(r1) <= int(row) <= int(r2)


def side_chunks(chunks, manifest):
    """(side_a_chunk|None, side_b_chunk|None), each found independently.

    Side B matches either its containing window (``Sheet!A2:F21``) or the
    pinpointed cell citation (``Sheet!E12``).
    """
    pair = manifest.get("conflict_pair", {})
    if not pair:
        return None, None
    a = pair.get("side_a", {})
    b = pair.get("side_b", {})
    a_src, a_slide = a.get("source_id"), (a.get("anchor") or {}).get("slide")
    b_src = b.get("source_id")
    b_cell = (b.get("anchor") or {}).get("range")
    b_sheet = (b.get("anchor") or {}).get("sheet")
    exact_b = "%s!%s" % (b_sheet, b_cell) if b_sheet and b_cell else None
    found_a = found_b = None
    for c in chunks:
        ptr = (c.get("citation") or {}).get("pointer", "")
        if (c.get("source_id") == a_src
                and ptr == "slide %d" % a_slide and found_a is None):
            found_a = c
        rng = ptr if "!" in ptr else None
        if (c.get("source_id") == b_src and rng and found_b is None
                and (ptr == exact_b
                     or (_cell_in_range(rng, b_cell)
                         and rng.startswith(b_sheet + "!")))):
            found_b = c
    return found_a, found_b


def sides_present(allowed, manifest):
    """(side_a_chunk, side_b_chunk) or (None, None) for the seeded pair."""
    found_a, found_b = side_chunks(allowed, manifest)
    if found_a is not None and found_b is not None:
        return found_a, found_b
    return None, None


def exact_pointer(chunk, manifest):
    """Pinpointed citation for a seeded side, else the chunk's pointer.

    Side B's containing window narrows to the anchored cell (e.g.
    ``Q3-Growth!A2:F21`` -> ``Q3-Growth!E12``); side A is already exact.
    """
    _, found_b = side_chunks([chunk], manifest)
    if found_b is not None:
        b = (manifest.get("conflict_pair", {}).get("side_b") or {})
        anchor = b.get("anchor") or {}
        if anchor.get("sheet") and anchor.get("range"):
            return "%s!%s" % (anchor["sheet"], anchor["range"])
    return (chunk.get("citation") or {}).get("pointer")


def anchored_text(chunk, manifest):
    """Header + anchored row for a side-B window chunk, or None.

    Sheet chunk text is the header line followed by one line per row in
    window order, so the anchored cell's row is directly addressable.
    The returned text supports the pinpointed cell citation instead of
    quoting the whole 20-row window.
    """
    _, found_b = side_chunks([chunk], manifest)
    if found_b is None:
        return None
    ptr = (chunk.get("citation") or {}).get("pointer", "")
    win = re.fullmatch(r"(.+)!([A-Z]+)(\d+):([A-Z]+)(\d+)", ptr or "")
    b = (manifest.get("conflict_pair", {}).get("side_b") or {})
    cell = (b.get("anchor") or {}).get("range") or ""
    cel = re.fullmatch(r"([A-Z]+)(\d+)", cell)
    if not win or not cel:
        return None
    start_row = int(win.group(3))
    idx = 1 + (int(cel.group(2)) - start_row)
    lines = (chunk.get("text") or "").splitlines()
    if idx < 1 or idx >= len(lines):
        return None
    return "\n".join([lines[0], lines[idx]])


def flag_conflict(allowed, run_id, database_url, corpus_dir=DEFAULT_CORPUS):
    """Flag the seeded pair when both sides are present; exactly once.

    Only relevance-gated chunks (score >= MIN_RELEVANCE_SCORE) count as
    evidence: score-0 filler is dropped here as defense in depth even
    though app.ask already gates before calling. Chunks without a score
    are treated as irrelevant. Returns {"fired": bool, "created": bool,
    "task": dict|None}. Logs agent='conflict' (ids only). Never writes
    a resolution.
    """
    import psycopg

    allowed = [c for c in allowed
               if retrieval.meets_relevance(c.get("score", 0))]
    manifest = retrieval.load_manifest(corpus_dir)
    pair = manifest.get("conflict_pair", {})
    conflict_id = pair.get("id", "conflict-01")
    side_a, side_b = sides_present(allowed, manifest)
    migrate.ensure_up_once(database_url)
    fired, created, task = False, False, None
    with psycopg.connect(database_url) as conn:
        with conn.transaction():
            if side_a is not None and side_b is not None:
                fired = True
                cur = conn.execute(
                    "INSERT INTO steward_tasks "
                    "(conflict_id, run_id, detail) VALUES (%s, %s, %s) "
                    "ON CONFLICT (conflict_id) DO NOTHING "
                    "RETURNING id, conflict_id, run_id, status, resolution, "
                    "created_at",
                    (conflict_id, run_id, json.dumps({
                        "side_a": {"source_id": side_a["source_id"],
                                   "pointer": side_a["citation"]["pointer"]},
                        "side_b": {"source_id": side_b["source_id"],
                                   "pointer": side_b["citation"]["pointer"]},
                        "policy": pair.get("policy", "flag-once")})))
                row = cur.fetchone()
                if row is not None:
                    created = True
                    task = {"id": str(row[0]), "conflict_id": row[1],
                            "run_id": row[2], "status": row[3],
                            "resolution": row[4],
                            "created_at": row[5].isoformat()}
                else:
                    row = conn.execute(
                        "SELECT id, conflict_id, run_id, status, resolution, "
                        "created_at FROM steward_tasks WHERE conflict_id=%s",
                        (conflict_id,)).fetchone()
                    task = {"id": str(row[0]), "conflict_id": row[1],
                            "run_id": row[2], "status": row[3],
                            "resolution": row[4],
                            "created_at": row[5].isoformat()}
            conn.execute(
                "INSERT INTO run_steps (run_id, step_index, agent, detail) "
                "VALUES (%s, %s, 'conflict', %s) "
                "ON CONFLICT (run_id, step_index) DO UPDATE "
                "SET detail = EXCLUDED.detail",
                (run_id, 4, json.dumps({
                    "conflict_id": conflict_id,
                    "fired": fired, "created": created,
                    "input_tokens": sum(
                        planner.estimate_tokens(c.get("text"))
                        for c in allowed),
                    "output_tokens": planner.estimate_tokens(json.dumps(
                        {"fired": fired, "created": created,
                         "conflict_id": conflict_id}))})))
    return {"fired": fired, "created": created, "task": task}


def list_tasks(database_url, corpus_dir=DEFAULT_CORPUS):
    """All Steward tasks with both seeded sides linked (no resolved text).

    Each task: {id, conflict_id, run_id, status, resolution, created_at,
    side_a: {source_id, pointer, claim}, side_b: {...}}. Pointers come
    from the stored firing run; claims come from the manifest pair.
    """
    import psycopg

    manifest = retrieval.load_manifest(corpus_dir)
    pair = manifest.get("conflict_pair", {})
    migrate.ensure_up_once(database_url)
    with psycopg.connect(database_url) as conn:
        rows = conn.execute(
            "SELECT id, conflict_id, run_id, detail, status, resolution, "
            "created_at FROM steward_tasks ORDER BY created_at").fetchall()
    tasks = []
    for tid, cid, run_id, detail, status, resolution, created in rows:
        d = json.loads(detail) if isinstance(detail, str) else (detail or {})
        tasks.append({
            "id": str(tid), "conflict_id": cid, "run_id": run_id,
            "status": status, "resolution": resolution,
            "created_at": created.isoformat() if created else None,
            "side_a": {**(d.get("side_a") or {}),
                       "claim": (pair.get("side_a") or {}).get("claim")},
            "side_b": {**(d.get("side_b") or {}),
                       "claim": (pair.get("side_b") or {}).get("claim")}})
    return tasks


def _check(name, cond, detail=""):
    cond = bool(cond)
    print(("PASS " if cond else "FAIL ") + name
          + ((" — " + detail) if detail and not cond else ""))
    return cond


def _analyst_allowed(database_url, corpus_dir):
    run_id, _ = planner.plan_and_log(
        planner.DEMO_QUERY, database_url, corpus_dir)
    cands = retrieval.retrieve(
        planner.DEMO_QUERY, "analyst", run_id, database_url, corpus_dir)
    out = policy.enforce(cands, "analyst", run_id, database_url, corpus_dir)
    return run_id, out["allowed"]


def cmd_probe(database_url, corpus_dir):
    """Seeded pair fires once; rerun creates no second task; no resolution."""
    migrate.cmd_up(database_url)
    ok = True
    run1, allowed1 = _analyst_allowed(database_url, corpus_dir)
    r1 = flag_conflict(allowed1, run1, database_url, corpus_dir)
    ok &= _check("analyst result fires on the seeded pair",
                 r1["fired"] and r1["task"] is not None,
                 "fired=%s" % r1["fired"])
    manifest = retrieval.load_manifest(corpus_dir)
    side_a, side_b = sides_present(allowed1, manifest)
    exact_b = {**side_b, "citation": {
        "source_id": side_b["source_id"],
        "pointer": exact_pointer(side_b, manifest)}}
    exact_a, exact_found_b = sides_present([side_a, exact_b], manifest)
    ok &= _check("side B pinpoints to Q3-Growth!E12, not the window",
                 exact_pointer(side_b, manifest) == "Q3-Growth!E12"
                 and "7.1" in (anchored_text(side_b, manifest) or "")
                 and exact_a is not None and exact_found_b is not None,
                 "pointer=%s text=%s"
                 % (exact_pointer(side_b, manifest),
                    anchored_text(side_b, manifest)))
    run2, allowed2 = _analyst_allowed(database_url, corpus_dir)
    r2 = flag_conflict(allowed2, run2, database_url, corpus_dir)
    ok &= _check("second fire creates no new task (exactly once)",
                 r2["fired"] and not r2["created"]
                 and r2["task"]["id"] == r1["task"]["id"],
                 "created=%s" % r2["created"])
    t = r2["task"]
    ok &= _check("task links both sides with no resolution",
                 t["status"] == "open" and t["resolution"] == "none"
                 and t["conflict_id"] == "conflict-01",
                 "%s" % t)
    import psycopg
    with psycopg.connect(database_url) as conn:
        n = conn.execute(
            "SELECT count(*) FROM steward_tasks "
            "WHERE conflict_id = 'conflict-01'").fetchone()[0]
    ok &= _check("exactly one task row for the pair", n == 1, "n=%s" % n)
    # Negative: employee result lacks the licensed side, so no fire.
    run3, _ = planner.plan_and_log(
        planner.DEMO_QUERY, database_url, corpus_dir)
    cands = retrieval.retrieve(
        planner.DEMO_QUERY, "employee", run3, database_url, corpus_dir)
    out = policy.enforce(cands, "employee", run3, database_url, corpus_dir)
    r3 = flag_conflict(out["allowed"], run3, database_url, corpus_dir)
    ok &= _check("employee result (no licensed side) does not fire",
                 not r3["fired"] and r3["task"] is None,
                 "fired=%s" % r3["fired"])
    print("CONFLICT PROBE: " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description="Kohu conflict (P32b)")
    parser.add_argument("--probe", action="store_true",
                        help="fires once, second run stays at one")
    parser.add_argument("--database-url", default=os.environ.get(
        "DATABASE_URL", DEFAULT_DATABASE_URL))
    parser.add_argument("--corpus", default=str(DEFAULT_CORPUS))
    args = parser.parse_args(argv)
    if not args.probe:
        parser.error("need --probe")
    return cmd_probe(args.database_url, args.corpus)


if __name__ == "__main__":
    raise SystemExit(main())
