"""B3: full text search, filtered by persona, calibrated threshold."""

import psycopg

import retrieval


def ids(hits):
    return [(h["source_id"], h["citation"]["pointer"]) for h in hits]


def test_schema_has_tsv_and_no_embedding(seeded_db):
    with psycopg.connect(seeded_db) as c:
        cols = {r[0] for r in c.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'chunks'").fetchall()}
    assert "tsv" in cols and "embedding" not in cols


def test_gibberish_and_offtopic_return_nothing(seeded_db):
    assert retrieval.search("zxqwv blorpt qwertyuiop", "steward") == []
    assert retrieval.search("What is the capital of France?", "steward") == []


def test_growth_query_finds_report_table(seeded_db):
    hits = retrieval.search("What was Viet Nam's GDP growth in 2023?",
                            "employee", limit=3)
    assert ("asean-outlook-report", "p.3") in ids(hits)


def test_employee_search_never_returns_denied_sources(seeded_db):
    for q in ("Viet Nam GDP growth dataset", "Q3 target attainment rep",
              "indicator code NY.GDP.MKTP.KD.ZG"):
        for h in retrieval.search(q, "employee", limit=20):
            assert h["source_id"] not in ("asean-indicators-dataset",
                                          "team-performance")


def test_kinds_filter(seeded_db):
    hits = retrieval.search("Viet Nam growth", "analyst", kinds=["sheet"])
    assert hits and {h["source_id"] for h in hits} == {
        "asean-indicators-dataset"}


def test_read_cells_exact_value_and_denial():
    out = retrieval.read_cells("asean-indicators-dataset", "Data!I11",
                               "analyst")
    assert out["pointer"] == "Data!I11"
    assert abs(out["cells"]["I11"] - 4.9787) < 0.001
    assert retrieval.read_cells("asean-indicators-dataset", "Data!I11",
                                "employee") is None
    assert retrieval.read_cells("no-such", "A1", "steward") is None


def test_read_section_denied_equals_unknown(seeded_db):
    with psycopg.connect(seeded_db) as c:
        cid = str(c.execute("SELECT id FROM chunks WHERE source_id = "
                            "'team-performance' LIMIT 1").fetchone()[0])
    assert retrieval.read_section(cid, "employee") == []
    assert retrieval.read_section(
        "00000000-0000-0000-0000-000000000000", "employee") == []
    assert retrieval.read_section(cid, "manager")[0]["source_id"] == \
        "team-performance"
