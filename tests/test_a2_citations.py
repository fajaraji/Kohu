"""A2: time pointers parse, format and resolve to video step chunks."""

import psycopg

import retrieval
import verifier


def test_format_and_parse_time():
    assert retrieval.format_time(42.5) == "t=42.5s"
    assert retrieval.format_time(7) == "t=7.0s"
    assert verifier._parse_pointer({"pointer": "t=42.5s"}) == \
        (None, None, None, 42.5)
    assert verifier._parse_pointer({"pointer": "p.3"}) == (3, None, None, None)
    assert verifier._parse_pointer({"pointer": "slide 4"})[2] == 4
    assert verifier._parse_pointer({"pointer": "Data!I11"})[1] == "Data!I11"
    assert verifier._parse_pointer({"pointer": "t=abc"}) is None


def test_citation_for_prefers_time():
    row = ("id", "vid", "text", None, None, None, 23.5)
    assert retrieval.citation_for(row) == {"source_id": "vid",
                                           "pointer": "t=23.5s"}
    assert retrieval.citation_for(("id", "r", "t", 3, None, None))[
        "pointer"] == "p.3"


def test_resolve_time_citation(seeded_db):
    with psycopg.connect(seeded_db) as conn:
        conn.execute("DELETE FROM chunks WHERE source_id = 'test-video'")
        conn.execute(
            "INSERT INTO chunks (source_id, license_class, chunk_index, text, "
            "t_start, text_origin) VALUES ('test-video', 'open-internal', 0, "
            "'Click Check stock', 23.5, 'video-step')")
        row = verifier.resolve_citation({"pointer": "t=23.5s"}, "test-video",
                                        conn)
        assert row is not None and row[2] == "Click Check stock"
        assert verifier.resolve_citation({"pointer": "t=99.0s"},
                                         "test-video", conn) is None
        conn.execute("DELETE FROM chunks WHERE source_id = 'test-video'")
