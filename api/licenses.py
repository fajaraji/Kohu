"""License usage (B8): who actually used the data the company paid for.

Every answer that cites a licensed source writes one row per cited
source to source_access_log (persona and user from the signed token).
GET /licenses returns a card per licensed source the persona may see:
vendor, coverage, seats, term, and distinct users in the last 30 days.
The seeded baseline (sample = true) is labeled sample data in the app;
real rows come only from answers asked in Kohu.
"""

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import corpus  # noqa: E402
import db  # noqa: E402
import policy  # noqa: E402

# Sample baseline: distinct users who opened each file in the 30 days
# before Kohu, as a simulated starting point. Labeled sample in the app.
SAMPLE_BASELINE = {"asean-outlook-report": 2, "asean-indicators-dataset": 1}


def log_citations(run_id, persona, user, citations, database_url=None):
    import psycopg

    rows = []
    seen = set()
    for c in citations or []:
        sid = c["source_id"]
        if policy.is_licensed(sid) and sid not in seen:
            seen.add(sid)
            rows.append((sid, persona, user or "demo-" + persona, run_id,
                         c.get("pointer")))
    if not rows:
        return 0
    with psycopg.connect(db.database_url(database_url)) as conn:
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO source_access_log (source_id, persona, user_id, "
                "run_id, pointer) VALUES (%s, %s, %s, %s, %s)", rows)
        conn.commit()
    return len(rows)


def seed_sample(database_url=None):
    """Insert the labeled sample baseline once (idempotent)."""
    import psycopg

    with psycopg.connect(db.database_url(database_url)) as conn:
        conn.execute("DELETE FROM source_access_log WHERE sample")
        for sid, n in SAMPLE_BASELINE.items():
            for i in range(n):
                conn.execute(
                    "INSERT INTO source_access_log (source_id, persona, "
                    "user_id, sample, at) VALUES (%s, 'analyst', %s, true, "
                    "now() - make_interval(days => %s))",
                    (sid, "sample-analyst-%d" % (i + 1), 3 + 7 * i))
        conn.commit()


def cards(persona, database_url=None, corpus_dir=corpus.DEFAULT_CORPUS):
    import psycopg

    visible = set(policy.visible_sources(persona, corpus_dir))
    titles = corpus.titles(corpus_dir)
    out = []
    with psycopg.connect(db.database_url(database_url)) as conn:
        for sid, info in policy.LICENSE_REGISTRY.items():
            if sid not in visible:
                continue
            real, sample, cites = conn.execute(
                "SELECT count(DISTINCT user_id) FILTER (WHERE NOT sample), "
                "count(DISTINCT user_id) FILTER (WHERE sample), "
                "count(*) FILTER (WHERE NOT sample) FROM source_access_log "
                "WHERE source_id = %s AND at > now() - interval '30 days'",
                (sid,)).fetchone()
            by_persona = dict(conn.execute(
                "SELECT persona, count(DISTINCT user_id) FROM "
                "source_access_log WHERE source_id = %s AND NOT sample AND "
                "at > now() - interval '30 days' GROUP BY persona",
                (sid,)).fetchall())
            card = dict(info, source_id=sid, title=titles.get(sid),
                        users_30d=real, sample_users_30d=sample,
                        citations_30d=cites, users_by_persona=by_persona,
                        sample_label="sample data (seeded baseline)")
            if persona != policy.STEWARD:
                card.pop("annual_cost_usd", None)
                card.pop("users_by_persona", None)
            out.append(card)
    return out
