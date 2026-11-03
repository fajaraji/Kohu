"""Kohu ask endpoint (P40): POST /ask over the five-agent pipeline.

Contract (PRD.md FR4/FR5, TASK_CHECKLIST.md T40-T42):
  POST /ask {persona, query} -> {run_id, persona, answer, claims,
  sources, stubs, conflict, dropped_count}. Each claim links to one
  chunk; unverified claims are dropped, never shown. Same query as
  different personas returns different source sets; denied sources
  never leak via text, snippet, or citation.

Pipeline (one run id, steps 0-4 in run_steps; retry round 2 at 5-7):
  planner.plan_and_log -> retrieval.retrieve (role pre-filter) ->
  policy.enforce (re-check + Steward stubs) -> one claim per relevant
  allowed source (top chunk scoring >= MIN_RELEVANCE_SCORE; score-0
  chunks never become claims; when both seeded conflict sides are
  relevant, their anchored chunks are cited and side B is pinpointed
  to its single cell) -> verifier.verify_claims (drops uncited) ->
  conflict.flag_conflict over verified cited chunks only (exactly-once
  Steward task). Empty verified sets return the no-answer message.

Answer synthesis is Spark-first (SparkSynthesizer drafts claims and
prose, env-gated on META_API_KEY/META_API_BASE/META_PARSE_MODEL like
SparkEnricher) with an extractive fallback: verifier drops unsupported
claims, a drop triggers re-retrieval with a revised query (max 2
rounds, each logged in run_steps), and Spark failure degrades to the
extractive path marked degraded in the trace. Empty results return a
safe message (T42).

Usage:
  uvicorn api.app:app --port 8000
"""

import json
import os
import pathlib
import sys
from contextlib import asynccontextmanager

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

import conflict  # noqa: E402
import meta_client  # noqa: E402
import migrate  # noqa: E402  (probe ensures task table exists)
import planner  # noqa: E402
import policy  # noqa: E402
import retrieval  # noqa: E402
import verifier  # noqa: E402

REPO = HERE.parent
DEFAULT_CORPUS = REPO / "corpus"
DEFAULT_DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://postgres@localhost:5432/kohu")

MAX_WORDS_PER_CLAIM = 40

# Explicit no-answer message (T42/A01): returned when no verified claim
# exists, e.g. a gibberish query whose chunks all score 0. Kept as a
# constant so the probe and the endpoint assert the exact same string.
NO_ANSWER_MESSAGE = ("No citable answer found for this query under the "
                     "%s role.")

@asynccontextmanager
async def _lifespan(app):
    """Run pending migrations once at startup (P12/A07).

    Request modules only call migrate.ensure_up_once (a per-process
    no-op after the first ensure), so serving requests performs no
    migration runs in the steady state.
    """
    migrate.ensure_up_once(database_url())
    yield


app = FastAPI(title="Kohu ask API (P40)", lifespan=_lifespan)


class AskRequest(BaseModel):
    persona: str = Field(description="one of employee, analyst, manager, steward")
    query: str = Field(description="non-empty question")


def database_url():
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


def excerpt(text, limit=MAX_WORDS_PER_CLAIM):
    words = text.split()
    return " ".join(words[:limit])


def synthesize(verified):
    """Extractive answer: numbered claim lines with [source pointer].

    Fallback path when Spark is off or fails; Spark prose (render_answer)
    is preferred when Spark is on. Signature kept stable.
    """
    lines = []
    for i, claim in enumerate(verified, start=1):
        cite = claim["citation"]
        lines.append("%d. %s [%s %s]" % (
            i, claim["text"], cite["source_id"], cite["pointer"]))
    return "\n".join(lines)


# Retry budget (A02/A03): at most 2 retrieval rounds per ask.
MAX_ROUNDS = 2
# run_steps indices for round 2 (round 1 keeps 0-4; CHECK allows only
# the five existing agent names, so round 2 reuses them at 5-7).
ROUND2_RETRIEVAL_STEP = 5
ROUND2_POLICY_STEP = 6
ROUND2_VERIFIER_STEP = 7


class SparkSynthesizer:
    """Draft claims + prose answers through api/meta_client.MetaClient.

    Enabled when META_API_KEY is set. Any failure returns None so the
    caller degrades to the extractive path. Token totals come from the
    API usage object via MetaClient.
    """

    def __init__(self, force_off=False, client=None):
        self.client = client or meta_client.MetaClient()
        self.enabled = self.client.enabled and not force_off
        self.tokens_estimated = False

    @property
    def input_tokens(self):
        return self.client.input_tokens

    @property
    def output_tokens(self):
        return self.client.output_tokens

    @property
    def calls(self):
        return self.client.calls

    def _call(self, prompt):
        """Raw model text for a prompt, or None on any failure."""
        if not self.enabled:
            return None
        try:
            payload = self.client.responses({"input": prompt, "store": False},
                                            label="synthesize")
        except meta_client.MetaError:
            return None
        return meta_client.output_text(payload).strip() or None

    def draft_claims(self, query, chunks):
        """Draft one claim per chunk via Spark, or None on failure.

        Returns [{"text", "citation": {"source_id", "pointer"}}]. The
        model must cite only the given chunks; the verifier still drops
        anything unsupported, so a bad draft degrades to a retry, never
        to an uncited answer.
        """
        if not self.enabled or not chunks:
            return None
        context = []
        for c in chunks:
            context.append("[%s %s] %s" % (
                c["source_id"], c["citation"]["pointer"],
                excerpt(c["text"], 120)))
        prompt = (
            "You draft grounded claims for a cited Q&A system. Query: %s\n"
            "Evidence chunks (cite ONLY these source_id + pointer pairs):\n"
            "%s\n"
            "Return a JSON array only, one object per claim with "
            "text, source_id, and pointer keys (pointer must be one of "
            "the given exact pointers). No other text."
            % (query.strip(), "\n".join(context)))
        raw = self._call(prompt)
        if not raw:
            return None
        try:
            start, end = raw.find("["), raw.rfind("]")
            claims = json.loads(raw[start:end + 1] if start >= 0 and end > start
                                else raw)
        except Exception:
            return None
        if not isinstance(claims, list):
            return None
        out = []
        valid = {(c["source_id"], c["citation"]["pointer"]) for c in chunks}
        for item in claims:
            if not isinstance(item, dict):
                continue
            text = (item.get("text") or "").strip()
            sid, ptr = item.get("source_id"), item.get("pointer")
            if not text or (sid, ptr) not in valid:
                continue
            out.append({"text": excerpt(text),
                        "citation": {"source_id": sid, "pointer": ptr}})
        return out or None

    def render_answer(self, query, verified):
        """Prose answer with inline [source pointer] cites, or None."""
        if not self.enabled or not verified:
            return None
        lines = ["[%s %s] %s" % (c["citation"]["source_id"],
                                 c["citation"]["pointer"], c["text"])
                 for c in verified]
        prompt = (
            "Answer this query in one short prose paragraph using ONLY the "
            "verified claims below; keep each fact's [source pointer] cite "
            "inline. Query: %s\nClaims:\n%s"
            % (query.strip(), "\n".join(lines)))
        return self._call(prompt)


def _read_step(db, run_id, step_index):
    import psycopg

    with psycopg.connect(db) as conn:
        row = conn.execute(
            "SELECT detail FROM run_steps WHERE run_id = %s AND step_index = %s",
            (run_id, step_index)).fetchone()
    if row is None:
        return None
    detail = row[0]
    return json.loads(detail) if isinstance(detail, str) else detail


def _write_step(db, run_id, step_index, agent, detail):
    import psycopg

    with psycopg.connect(db) as conn:
        with conn.transaction():
            conn.execute(
                "INSERT INTO run_steps (run_id, step_index, agent, detail) "
                "VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (run_id, step_index) DO UPDATE "
                "SET detail = EXCLUDED.detail",
                (run_id, step_index, agent, json.dumps(detail)))


def _build_draft_chunks(relevant, manifest):
    """Best-chunk-per-source + seeded-side pinning (extractive draft base)."""
    best = {}
    for c in relevant:
        prev = best.get(c["source_id"])
        if (prev is None or (c["score"], c["chunk_id"])
                > (prev["score"], prev["chunk_id"])):
            best[c["source_id"]] = c
    side_a, side_b = conflict.sides_present(relevant, manifest)
    pinned = set()
    if side_a is not None and side_b is not None:
        best[side_a["source_id"]] = side_a
        best[side_b["source_id"]] = side_b
        pinned = {side_a["chunk_id"], side_b["chunk_id"]}
    draft_chunks = sorted(best.values(), key=lambda c: c["source_id"])
    draft = []
    for c in draft_chunks:
        pointer = c["citation"]["pointer"]
        text = excerpt(c["text"])
        if c["chunk_id"] in pinned:
            pointer = conflict.exact_pointer(c, manifest) or pointer
            text = conflict.anchored_text(c, manifest) or text
        draft.append({"text": text,
                      "citation": {"source_id": c["source_id"],
                                   "pointer": pointer}})
    return draft_chunks, draft


def _maybe_inject_forced_claim(draft, draft_chunks):
    """Test hook: KOHU_FORCE_UNSUPPORTED_CLAIM=1 appends one droppable claim.

    The injected claim cites a real chunk (or an unresolvable pointer when
    the draft is empty) with text sharing no content term, so the verifier
    drops it as unsupported and the retry loop engages. Round 1 only.
    """
    if os.environ.get("KOHU_FORCE_UNSUPPORTED_CLAIM") != "1":
        return draft
    if draft_chunks:
        c = draft_chunks[0]
        draft = list(draft) + [{
            "text": "Moon cheese harvest reaches 99.9 percent on Mars "
                    "without exception",
            "citation": {"source_id": c["source_id"],
                         "pointer": c["citation"]["pointer"]}}]
    else:
        draft = list(draft) + [{
            "text": "Moon cheese harvest reaches 99.9 percent on Mars "
                    "without exception",
            "citation": {"source_id": "product-deck", "pointer": "slide 999"}}]
    return draft


def _revise_query(query, dropped):
    """Revised query for round 2: dropped-claim terms absent from the query."""
    have = set(retrieval.query_terms(query))
    fresh = set()
    for d in dropped:
        fresh |= set(retrieval.query_terms(d.get("text") or ""))
    fresh -= have
    extra = " ".join(sorted(fresh)[:6])
    return ("%s %s" % (query, extra)).strip() if extra else query + " detail"


def _backing_cited(draft_chunks, draft, verified):
    """Chunks backing verified claims (cited evidence for conflict).

    Matched by source_id (one chunk per source in draft_chunks), so both
    extractive drafts (positional) and Spark drafts (reordered) map to
    their backing chunk; the claim's own pointer is kept, pinpointed
    citations included.
    """
    by_source = {}
    for chunk in draft_chunks:
        by_source.setdefault(chunk["source_id"], chunk)
    cited = []
    for claim in verified:
        chunk = by_source.get(claim["citation"]["source_id"])
        if chunk is not None:
            cited.append({**chunk, "citation": dict(claim["citation"])})
    return cited


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/steward/queue")
def steward_queue(persona: str = ""):
    if persona != "steward":
        raise HTTPException(
            status_code=403,
            detail="steward queue is visible to the steward persona only")
    return {"persona": "steward",
            "tasks": conflict.list_tasks(
                database_url(), str(DEFAULT_CORPUS))}


@app.post("/ask")
def ask(req: AskRequest):
    """Ask entry point with structured JSON errors (P12/A07).

    422 for bad input (unknown persona, empty query — FastAPI also
    returns 422 for malformed bodies before this runs), 503 with a JSON
    body when Postgres is unreachable (never a raw 500/HTML page), and
    a JSON 500 for anything else unexpected. Bodies stay {"detail":
    str} so the UI's data.detail error path keeps working.
    """
    import psycopg

    persona, query = req.persona, (req.query or "").strip()
    if persona not in retrieval.PERSONAS:
        raise HTTPException(
            status_code=422,
            detail="unknown persona %r (want one of %s)"
            % (persona, ", ".join(retrieval.PERSONAS)))
    if not query:
        raise HTTPException(
            status_code=422, detail="query must be a non-empty string")
    try:
        return run_ask(persona, query, database_url(), str(DEFAULT_CORPUS))
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=422,
                            detail="invalid request: %s" % e)
    except psycopg.OperationalError:
        raise HTTPException(
            status_code=503,
            detail="database unavailable; try again shortly")
    except Exception:
        raise HTTPException(status_code=500,
                            detail="internal error; try again shortly")


def _draft_with_spark_or_extractive(spark, query, draft_chunks, draft):
    """Spark drafts claims; None/empty from Spark falls back to extractive.

    Spark sees the extractive draft's evidence, not the raw chunks:
    pinned sources keep their pinpointed citation and anchored text
    (e.g. conflict side B cites Q3-Growth!E12, never its containing
    A2:F21 window), so the model's valid citation set is exactly the
    draft's. A window-only draft is therefore invalid and falls back.

    Returns (claims, spark_drafted_bool, spark_failed_bool).
    """
    if spark is not None and spark.enabled and draft_chunks:
        spark_chunks = [
            {**chunk,
             "text": (item["text"]
                      if item["citation"]["pointer"]
                      != chunk["citation"]["pointer"]
                      else chunk["text"]),
             "citation": dict(item["citation"])}
            for chunk, item in zip(draft_chunks, draft)
        ] or draft_chunks
        try:
            spark_claims = spark.draft_claims(query, spark_chunks)
        except Exception:
            spark_claims = None
        if spark_claims:
            # Spark may omit a drafted source entirely. Fill only the
            # missing citations from the extractive draft so coverage
            # (including both seeded conflict sides) stays deterministic;
            # Spark's own claim wins wherever it cited the same pointer.
            present = {(c["citation"]["source_id"],
                        c["citation"]["pointer"]) for c in spark_claims}
            merged = list(spark_claims) + [
                item for item in draft
                if (item["citation"]["source_id"],
                    item["citation"]["pointer"]) not in present]
            return merged, True, False
        return draft, False, True
    return draft, False, False


def run_ask(persona, query, db, corpus_dir, _spark=None):
    """Full ask pipeline without HTTP handling (endpoint + probe share it).

    A02/A03: Spark drafts claims at this seam when env-gated on; the
    verifier drops unsupported claims; a drop triggers re-retrieval with
    a revised query (max MAX_ROUNDS rounds, each logged in run_steps).
    Spark failure degrades to the extractive path and marks the run
    degraded in the trace.
    """
    run_id, _ = planner.plan_and_log(query, db, corpus_dir)
    manifest = retrieval.load_manifest(corpus_dir)
    spark = _spark if _spark is not None else SparkSynthesizer()
    degraded = False
    spark_drafted_any = False
    spark_failed_any = False

    # ---- round 1 (steps 0-3 as before) ----
    cands = retrieval.retrieve(query, persona, run_id, db, corpus_dir)
    out = policy.enforce(cands, persona, run_id, db, corpus_dir)
    # Relevance gate (A01): score-0 chunks share no content term with the
    # query, so they can never become claims. Filtering here (not in
    # retrieve/policy) keeps the probes' full-visible-set asserts intact.
    relevant = [c for c in out["allowed"]
                if retrieval.meets_relevance(c.get("score", 0))]
    draft_chunks, draft = _build_draft_chunks(relevant, manifest)
    draft, spark_drafted, spark_failed = _draft_with_spark_or_extractive(
        spark, query, draft_chunks, draft)
    spark_drafted_any |= spark_drafted
    spark_failed_any |= spark_failed
    draft = _maybe_inject_forced_claim(draft, draft_chunks)
    res = verifier.verify_claims(draft, run_id, db)
    verified = list(res["verified"])
    dropped = list(res["dropped"])
    cited = _backing_cited(draft_chunks, draft, verified)
    stubs = list(out["stubs"])
    rounds = 1
    revised_query = None

    # ---- round 2 on drops (steps 5-7; round 1 rows restored after) ----
    if dropped and MAX_ROUNDS >= 2:
        revised_query = _revise_query(query, dropped)
        r1_retrieval = _read_step(db, run_id, 1)
        r1_policy = _read_step(db, run_id, 2)
        r1_verifier = _read_step(db, run_id, 3)
        cands2 = retrieval.retrieve(revised_query, persona, run_id, db,
                                    corpus_dir)
        out2 = policy.enforce(cands2, persona, run_id, db, corpus_dir)
        r2_retrieval = _read_step(db, run_id, 1)
        r2_policy = _read_step(db, run_id, 2)
        relevant2 = [c for c in out2["allowed"]
                     if retrieval.meets_relevance(c.get("score", 0))]
        draft_chunks2, draft2 = _build_draft_chunks(relevant2, manifest)
        draft2, spark_drafted2, spark_failed2 = \
            _draft_with_spark_or_extractive(
                spark, revised_query, draft_chunks2, draft2)
        spark_drafted_any |= spark_drafted2
        spark_failed_any |= spark_failed2
        res2 = verifier.verify_claims(draft2, run_id, db)
        r2_verifier = _read_step(db, run_id, 3)
        # Archive round 2 under 5-7; restore round 1 under 1-3.
        if r2_retrieval is not None:
            _write_step(db, run_id, ROUND2_RETRIEVAL_STEP, "retrieval",
                        {**r2_retrieval, "round": 2,
                         "revised_query": revised_query})
        if r2_policy is not None:
            _write_step(db, run_id, ROUND2_POLICY_STEP, "policy",
                        {**r2_policy, "round": 2})
        if r2_verifier is not None:
            _write_step(db, run_id, ROUND2_VERIFIER_STEP, "verifier",
                        {**r2_verifier, "round": 2})
        if r1_retrieval is not None:
            _write_step(db, run_id, 1, "retrieval",
                        {**r1_retrieval, "round": 1})
        if r1_policy is not None:
            _write_step(db, run_id, 2, "policy", {**r1_policy, "round": 1})
        if r1_verifier is not None:
            _write_step(db, run_id, 3, "verifier",
                        {**r1_verifier, "round": 1})
        seen = {(c["citation"]["source_id"], c["citation"]["pointer"])
                for c in verified}
        for c in res2["verified"]:
            key = (c["citation"]["source_id"], c["citation"]["pointer"])
            if key not in seen:
                seen.add(key)
                verified.append(c)
        dropped = dropped + list(res2["dropped"])
        cited = cited + [c for c in
                         _backing_cited(draft_chunks2, draft2,
                                        res2["verified"])
                         if c not in cited]
        stubs = stubs + [s for s in out2["stubs"] if s not in stubs]
        rounds = 2

    degraded = spark_failed_any
    # Conflict receives only chunks backing verified claims (cited
    # chunks), pinpointed citations included — never the wider relevant
    # pool. A dropped claim therefore cannot flag.
    flag = conflict.flag_conflict(cited, run_id, db, corpus_dir)
    synthesis = "extractive"
    answer = None
    if verified and spark_drafted_any and spark.enabled:
        try:
            prose = spark.render_answer(query, verified)
        except Exception:
            prose = None
        if prose:
            synthesis = "spark"
            answer = prose
        else:
            degraded = True
    if answer is None:
        answer = (synthesize(verified) if verified
                  else NO_ANSWER_MESSAGE % persona)
    # Mark degraded/synthesis/rounds/tokens in the trace (step 4 keeps
    # fired plus the conflict input/output estimates). Spark totals are
    # real API usage when the response carried it, else prompt/completion
    # word-count estimates; zero when Spark never produced text.
    conflict_detail = _read_step(db, run_id, 4) or {}
    _write_step(db, run_id, 4, "conflict",
                {**conflict_detail, "degraded": degraded,
                 "synthesis": synthesis, "rounds": rounds,
                 "spark_used": spark_drafted_any,
                 "revised_query": revised_query,
                 "spark_input_tokens": getattr(spark, "input_tokens", 0),
                 "spark_output_tokens": getattr(spark, "output_tokens", 0),
                 "spark_calls": getattr(spark, "calls", 0),
                 "spark_tokens_estimated": getattr(
                     spark, "tokens_estimated", False)})
    return {
        "run_id": run_id,
        "persona": persona,
        "answer": answer,
        "claims": verified,
        "sources": sorted({c["citation"]["source_id"] for c in verified}),
        "stubs": stubs,
        "conflict": {"fired": flag["fired"],
                     "conflict_id": (flag["task"]["conflict_id"]
                                     if flag["task"] else None)},
        "dropped_count": len(dropped),
        "degraded": degraded,
        "synthesis": synthesis,
        "rounds": rounds,
    }


CORPUS_DIR = REPO / "corpus"
if CORPUS_DIR.is_dir():
    app.mount("/corpus", StaticFiles(directory=str(CORPUS_DIR)),
              name="corpus")

UI_DIR = REPO / "ui"
if UI_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(UI_DIR), html=True),
              name="ui")


# Probe queries: gibberish (no shared content term with any chunk),
# an unrelated analyst query (relevant claims, no conflict sides),
# and the fixed Q3 demo query (must flag conflict-01 exactly once).
GIBBERISH_QUERY = "zxqwv blorpt qwertyuiop"
UNRELATED_QUERY = "What is the travel reimbursement policy?"


def _check(name, cond, detail=""):
    cond = bool(cond)
    print(("PASS " if cond else "FAIL ") + name
          + ((" — " + detail) if detail and not cond else ""))
    return cond


def _conflict_01_count(database_url):
    import psycopg

    with psycopg.connect(database_url) as conn:
        return conn.execute(
            "SELECT count(*) FROM steward_tasks "
            "WHERE conflict_id = 'conflict-01'").fetchone()[0]


def cmd_probe(database_url, corpus_dir):
    """Relevance gate + no-answer + cited-only conflict (A01/A06).

    Gibberish returns zero claims, the explicit no-answer message, and
    no conflict; an unrelated analyst query returns claims but fires no
    conflict; the fixed Q3 query flags conflict-01 exactly once.
    Exit 0 iff all pass.
    """
    migrate.cmd_up(database_url)
    ok = True

    before = _conflict_01_count(database_url)
    gib = run_ask("analyst", GIBBERISH_QUERY, database_url, corpus_dir)
    ok &= _check("gibberish returns zero claims",
                 gib["claims"] == [], "claims=%d" % len(gib["claims"]))
    ok &= _check("gibberish returns the explicit no-answer message",
                 gib["answer"] == NO_ANSWER_MESSAGE % "analyst",
                 "answer=%.60s" % gib["answer"])
    ok &= _check("gibberish cites no sources", gib["sources"] == [],
                 "sources=%s" % gib["sources"])
    ok &= _check("gibberish fires no conflict",
                 gib["conflict"] == {"fired": False, "conflict_id": None},
                 "conflict=%s" % gib["conflict"])
    ok &= _check("gibberish creates no Steward task",
                 _conflict_01_count(database_url) == before,
                 "count moved")

    unrelated = run_ask("analyst", UNRELATED_QUERY,
                        database_url, corpus_dir)
    ok &= _check("unrelated analyst query fires no conflict",
                 unrelated["conflict"]["fired"] is False,
                 "conflict=%s" % unrelated["conflict"])
    ok &= _check("unrelated analyst query still answers from cited chunks",
                 len(unrelated["claims"]) > 0,
                 "claims=%d" % len(unrelated["claims"]))

    first = run_ask("analyst", planner.DEMO_QUERY,
                    database_url, corpus_dir)
    second = run_ask("analyst", planner.DEMO_QUERY,
                     database_url, corpus_dir)
    ok &= _check("fixed Q3 query flags conflict-01",
                 first["conflict"] == {"fired": True,
                                       "conflict_id": "conflict-01"},
                 "conflict=%s" % first["conflict"])
    ok &= _check("Q3 query still returns cited claims",
                 len(first["claims"]) > 0,
                 "claims=%d" % len(first["claims"]))
    licensed = [c for c in first["claims"]
                if c["citation"]["source_id"] == "licensed-market"]
    sales = [c for c in first["claims"]
             if c["citation"]["source_id"] == "sales-deck"]
    ok &= _check("Q3 side B cites Q3-Growth!E12, not the containing window",
                 len(licensed) == 1
                 and licensed[0]["citation"]["pointer"]
                 == "Q3-Growth!E12"
                 and "7.1" in licensed[0]["text"],
                 "licensed=%s" % licensed)
    ok &= _check("Q3 side A cites sales slide 7",
                 len(sales) == 1
                 and sales[0]["citation"]["pointer"] == "slide 7",
                 "sales=%s" % sales)
    ok &= _check("repeat Q3 ask creates no second task",
                 second["conflict"] == {"fired": True,
                                        "conflict_id": "conflict-01"}
                 and _conflict_01_count(database_url) == 1,
                 "count=%d conflict=%s"
                 % (_conflict_01_count(database_url),
                    second["conflict"]))

    # S03 re-verify (after A01): cited-source matrix per persona.
    expected_sources = {
        "employee": ["product-deck", "sales-deck", "scanned-note"],
        "analyst": ["licensed-market", "licensed-report", "product-deck",
                    "sales-deck", "scanned-note"],
        "manager": ["performance", "product-deck", "sales-deck",
                    "scanned-note"],
        "steward": ["licensed-market", "licensed-report", "performance",
                    "product-deck", "sales-deck", "scanned-note"],
    }
    for persona, want in expected_sources.items():
        got = run_ask(persona, planner.DEMO_QUERY,
                      database_url, corpus_dir)
        want_conflict = persona in ("analyst", "steward")
        leaked = (persona in ("employee", "manager")
                  and bool({"licensed-market", "licensed-report"}
                           & set(got["sources"])))
        ok &= _check(
            "S03 %s: %d cited sources, conflict=%s, no leakage"
            % (persona, len(want), want_conflict),
            got["sources"] == want
            and got["conflict"]["fired"] is want_conflict
            and (want_conflict
                 or got["conflict"]["conflict_id"] is None)
            and not leaked
            and (persona != "steward" or len(got["stubs"]) == 3),
            "sources=%s conflict=%s stubs=%s"
            % (got["sources"], got["conflict"],
               [s["source_id"] for s in got["stubs"]]))
    print("ASK PROBE: " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(description="Kohu ask API (P40)")
    parser.add_argument("--probe", action="store_true",
                        help="relevance gate + no-answer + conflict checks")
    parser.add_argument("--database-url", default=os.environ.get(
        "DATABASE_URL", DEFAULT_DATABASE_URL))
    parser.add_argument("--corpus", default=str(DEFAULT_CORPUS))
    args = parser.parse_args(argv)
    if not args.probe:
        parser.error("need --probe")
    return cmd_probe(args.database_url, args.corpus)


if __name__ == "__main__":
    raise SystemExit(main())
