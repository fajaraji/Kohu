"""Kohu verifier (P32a): drop uncited claims, keep only grounded ones.

Contract (PLAN.md section 3, PRD.md FR4, TASK_CHECKLIST.md T33):
  every claim in an answer must link to one chunk. The verifier resolves
  each claim's citation against the chunks table and checks the cited
  chunk shares at least one content term with the claim. Claims with no
  citation, an unresolvable citation, or no supporting text are dropped —
  never shown. Verified claims keep their page/slide/cell citation.

Usage:
  python api/verifier.py --probe   # adversarial query drops cleanly
"""

import argparse
import json
import os
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import migrate  # noqa: E402  (same-dir runner; ensures run tables exist)
import planner  # noqa: E402  (run creation for the probe)
import policy  # noqa: E402  (end-to-end probe input)
import retrieval  # noqa: E402

REPO = HERE.parent
DEFAULT_CORPUS = REPO / "corpus"
DEFAULT_DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://postgres@localhost:5432/kohu")


TIME_RE = re.compile(r"t=(\d+(?:\.\d+)?)s")


def _parse_pointer(citation):
    """(page, cell_range, slide, t_start) from a citation dict, or None."""
    ptr = (citation or {}).get("pointer")
    if ptr is None:
        return None
    ptr = str(ptr).strip()
    m = re.fullmatch(r"p\.(\d+)", ptr)
    if m:
        return (int(m.group(1)), None, None, None)
    m = re.fullmatch(r"slide (\d+)", ptr)
    if m:
        return (None, None, int(m.group(1)), None)
    m = TIME_RE.fullmatch(ptr)
    if m:
        return (None, None, None, float(m.group(1)))
    if "!" not in ptr:
        return None
    return (None, ptr, None, None)


def _cell_in_range(cell_range, cell_pointer):
    """True when a window pointer contains a single-cell pointer.

    Both are ``Sheet!...`` pointers, e.g. window ``Q3-Growth!A2:F21``
    contains cell ``Q3-Growth!E12``.
    """
    win = re.fullmatch(r"(.+)!([A-Z]+)(\d+):([A-Z]+)(\d+)",
                       cell_range or "")
    cel = re.fullmatch(r"(.+)!([A-Z]+)(\d+)", cell_pointer or "")
    if not win or not cel or win.group(1) != cel.group(1):
        return False
    _, c1, r1, c2, r2 = win.groups()
    _, col, row = cel.groups()
    return c1 <= col <= c2 and int(r1) <= int(row) <= int(r2)


def resolve_citation(citation, source_id, conn):
    """Fetch the cited chunk row, or None when unresolvable.

    A single-cell pointer (``Sheet!E12``) resolves to the chunk whose
    window contains that cell; a window pointer must match exactly.
    """
    if not citation or not source_id:
        return None
    triple = _parse_pointer(citation)
    if triple is None:
        return None
    page, cell_range, slide, t_start = triple
    if t_start is not None:
        return conn.execute(
            "SELECT id, source_id, text, page, cell_range, slide, t_start "
            "FROM chunks WHERE source_id = %s AND abs(t_start - %s) < 0.05",
            (source_id, t_start)).fetchone()
    if page is not None:
        return conn.execute(
            "SELECT id, source_id, text, page, cell_range, slide "
            "FROM chunks WHERE source_id = %s AND page = %s",
            (source_id, page)).fetchone()
    if slide is not None:
        return conn.execute(
            "SELECT id, source_id, text, page, cell_range, slide "
            "FROM chunks WHERE source_id = %s AND slide = %s",
            (source_id, slide)).fetchone()
    row = conn.execute(
        "SELECT id, source_id, text, page, cell_range, slide "
        "FROM chunks WHERE source_id = %s AND cell_range = %s",
        (source_id, cell_range)).fetchone()
    if row is not None:
        return row
    if re.fullmatch(r".+![A-Z]+\d+", cell_range or ""):
        rows = conn.execute(
            "SELECT id, source_id, text, page, cell_range, slide "
            "FROM chunks WHERE source_id = %s AND cell_range IS NOT NULL",
            (source_id,)).fetchall()
        for candidate in rows:
            if _cell_in_range(candidate[4], cell_range):
                return candidate
    return None


def verify_claims(claims, run_id, database_url):
    """Split claims into verified/dropped; log agent='verifier' (no text).

    Claim shape: {"text": str, "citation": {"source_id", "pointer"} |
    {"chunk_id"}}. Drop reasons: 'no-citation', 'unresolvable-citation',
    'unsupported' (no shared content term with the cited chunk).
    Returns {"verified": [...], "dropped": [...]}.
    """
    import psycopg

    verified, dropped = [], []
    with psycopg.connect(database_url) as conn:
        for claim in claims:
            text = (claim.get("text") or "").strip()
            cite = claim.get("citation") or {}
            row = None
            if cite.get("chunk_id"):
                row = conn.execute(
                    "SELECT id, source_id, text, page, cell_range, slide "
                    "FROM chunks WHERE id = %s",
                    (cite["chunk_id"],)).fetchone()
                reason = "unresolvable-citation"
            elif cite.get("source_id") and cite.get("pointer"):
                row = resolve_citation(cite, cite["source_id"], conn)
                reason = "unresolvable-citation"
            else:
                reason = "no-citation"
            if row is not None:
                terms = set(retrieval.query_terms(text))
                chunk_terms = set(retrieval.query_terms(row[2]))
                if terms & chunk_terms:
                    # Keep a pinpointed single-cell pointer when it
                    # resolved into this chunk's window; otherwise use
                    # the chunk's canonical citation.
                    canonical = retrieval.citation_for(row)["pointer"]
                    pointer = canonical
                    if _cell_in_range(canonical, cite.get("pointer")):
                        pointer = cite["pointer"]
                    verified.append({
                        "text": text,
                        "citation": {"source_id": row[1],
                                     "pointer": pointer}})
                    continue
                reason = "unsupported"
            dropped.append({"text": text,
                            "citation": cite if cite else None,
                            "reason": reason})
        with conn.transaction():
            conn.execute(
                "INSERT INTO run_steps (run_id, step_index, agent, detail) "
                "VALUES (%s, %s, 'verifier', %s) "
                "ON CONFLICT (run_id, step_index) DO UPDATE "
                "SET detail = EXCLUDED.detail",
                (run_id, 3, json.dumps({
                    "verified_count": len(verified),
                    "dropped_count": len(dropped),
                    "drop_reasons": sorted(
                        {d["reason"] for d in dropped}),
                    "input_tokens": sum(
                        planner.estimate_tokens(c.get("text"))
                        for c in claims),
                    "output_tokens": sum(
                        planner.estimate_tokens(v["text"])
                        for v in verified)})) )
    return {"verified": verified, "dropped": dropped}


def _check(name, cond, detail=""):
    cond = bool(cond)
    print(("PASS " if cond else "FAIL ") + name
          + ((" — " + detail) if detail and not cond else ""))
    return cond


def cmd_probe(database_url, corpus_dir):
    """Adversarial probe: grounded claims survive, the rest drop cleanly."""
    migrate.cmd_up(database_url)
    run_id, _ = planner.plan_and_log(
        planner.DEMO_QUERY, database_url, corpus_dir)
    cands = retrieval.retrieve(
        planner.DEMO_QUERY, "analyst", run_id, database_url, corpus_dir)
    out = policy.enforce(cands, "analyst", run_id, database_url, corpus_dir)
    assert out["allowed"], "probe needs enforced chunks; ingest first"
    good = out["allowed"][0]
    good_claim = {
        "text": " ".join(good["text"].split()[:24]),
        "citation": {"source_id": good["source_id"],
                     "pointer": good["citation"]["pointer"]}}
    claims = [
        good_claim,
        {"text": "Q3 growth for product X was 99.9 percent, sources say.",
         "citation": None},
        {"text": "Licensed analysts confirm the 7.1 percent Q3 figure.",
         "citation": {"source_id": "licensed-market",
                      "pointer": "Q3-Growth!Z999:Z999"}},
        {"text": "Employee morale improves every quarter without exception.",
         "citation": {"source_id": good["source_id"],
                      "pointer": good["citation"]["pointer"]}},
    ]
    res = verify_claims(claims, run_id, database_url, )
    exact = verify_claims([
        {"text": "Product X | All regions | 4.1 | 6.2 | 7.1 | 8.0",
         "citation": {"source_id": "licensed-market",
                      "pointer": "Q3-Growth!E12"}},
        {"text": "Product X | All regions | 4.1 | 6.2 | 7.1 | 8.0",
         "citation": {"source_id": "licensed-market",
                      "pointer": "Q3-Growth!E999"}}], run_id, database_url)
    ok = True
    ok &= _check("single-cell E12 citation resolves and is preserved",
                 len(exact["verified"]) == 1
                 and exact["verified"][0]["citation"] == {
                     "source_id": "licensed-market",
                     "pointer": "Q3-Growth!E12"}
                 and len(exact["dropped"]) == 1
                 and exact["dropped"][0]["reason"]
                 == "unresolvable-citation",
                 "exact=%s" % exact)
    ok &= _check("grounded claim verified with citation",
                 len(res["verified"]) == 1
                 and res["verified"][0]["text"] == good_claim["text"],
                 "verified=%d" % len(res["verified"]))
    reasons = sorted(d["reason"] for d in res["dropped"])
    ok &= _check("three adversarial claims dropped cleanly",
                 len(res["dropped"]) == 3, "dropped=%d" % len(res["dropped"]))
    ok &= _check("drop reasons cover all failure modes",
                 reasons == ["no-citation", "unresolvable-citation",
                             "unsupported"],
                 "reasons=%s" % reasons)
    blob = json.dumps(res["verified"])
    ok &= _check("dropped text absent from verified output",
                 "99.9" not in blob and "morale" not in blob, blob[:200])
    print("VERIFIER PROBE: " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description="Kohu verifier (P32a)")
    parser.add_argument("--probe", action="store_true",
                        help="adversarial query drops cleanly")
    parser.add_argument("--database-url", default=os.environ.get(
        "DATABASE_URL", DEFAULT_DATABASE_URL))
    parser.add_argument("--corpus", default=str(DEFAULT_CORPUS))
    args = parser.parse_args(argv)
    if not args.probe:
        parser.error("need --probe")
    return cmd_probe(args.database_url, args.corpus)


if __name__ == "__main__":
    raise SystemExit(main())
