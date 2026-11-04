"""G1: public demo mode keeps each visitor's decisions private."""

import json

import psycopg
import pytest
from fastapi.testclient import TestClient

import app as kohu
import conflict
import demo
import meta_client
import retrieval

YES = {"is_conflict": True, "summary": "deck 6.5 vs report 5.0",
       "severity": "high", "evidence_a": "", "evidence_b": ""}


class Judge:
    enabled = True

    def responses(self, body, label=None, cache=True):
        return {"output": [{"type": "message", "content": [
            {"type": "output_text", "text": json.dumps(YES)}]}]}


@pytest.fixture()
def public(monkeypatch, seeded_db):
    monkeypatch.setenv("KOHU_PUBLIC_DEMO", "1")
    monkeypatch.setenv("KOHU_ASK_LIMIT_VISITOR", "3/600")
    demo.ask_limiter._hits.clear()
    with psycopg.connect(seeded_db) as c:
        c.execute("DELETE FROM conflicts")
        c.execute("DELETE FROM visitor_decisions")
    conflict.judge_pair(("regional-expansion-deck", "slide 4"),
                        ("asean-outlook-report", "p.3"), seeded_db,
                        client=Judge())
    with TestClient(kohu.app) as c:
        yield c
    with psycopg.connect(seeded_db) as c:
        c.execute("DELETE FROM conflicts")
        c.execute("DELETE FROM visitor_decisions")


def login(c, persona, visitor):
    r = c.post("/login", json={"persona": persona, "visitor": visitor})
    return {"Authorization": "Bearer " + r.json()["token"]}


def test_config_reports_public_mode(public):
    assert public.get("/config").json() == {
        "public_demo": True, "uploads": False, "step_editing": False}


def test_decision_is_private_to_one_visitor(public, seeded_db):
    a, b = "a" * 16, "b" * 16
    cid = public.get("/conflicts", headers=login(public, "steward", a)).json()[
        "conflicts"][0]["conflict_id"]
    r = public.post("/conflicts/%s/resolve" % cid,
                    headers=login(public, "steward", a),
                    json={"winner": "b", "note": "report is right"})
    assert r.json()["status"] == "resolved"
    mine = public.get("/conflicts", headers=login(public, "employee", a)).json()
    theirs = public.get("/conflicts", headers=login(public, "employee", b)).json()
    assert mine["conflicts"][0]["status"] == "resolved"
    assert theirs["conflicts"][0]["status"] == "open"
    with psycopg.connect(seeded_db) as c:
        assert c.execute("SELECT status FROM conflicts WHERE conflict_id = %s",
                         (cid,)).fetchone()[0] == "open"
    # Stale ranking follows the visitor too.
    with demo.visitor_scope(a):
        with psycopg.connect(seeded_db) as c:
            assert len(conflict.stale_keys(c)) == 1
    with demo.visitor_scope(b):
        with psycopg.connect(seeded_db) as c:
            assert conflict.stale_keys(c) == set()
    r = public.post("/demo/reset", headers=login(public, "employee", a))
    assert r.json()["cleared"] == 1
    again = public.get("/conflicts", headers=login(public, "employee", a)).json()
    assert again["conflicts"][0]["status"] == "open"


def test_uploads_and_edits_are_off(public):
    h = login(public, "manager", "c" * 16)
    r = public.post("/videos", headers=h,
                    files={"file": ("a.mp4", b"x", "video/mp4")})
    assert r.status_code == 403
    r = public.patch("/videos/refund-process-video/steps/1", headers=h,
                     json={"instruction": "changed"})
    assert r.status_code == 403
    steps = public.get("/videos/refund-process-video/steps", headers=h).json()
    assert steps["can_review"] is False


def test_ask_rate_limit_per_visitor(public):
    h = login(public, "employee", "d" * 16)
    codes = [public.post("/ask", headers=h, json={"query": "days off"})
             .status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]
    other = login(public, "employee", "e" * 16)
    assert public.post("/ask", headers=other,
                       json={"query": "days off"}).status_code == 200


def test_usage_logged_in_database(public, seeded_db, tmp_path):
    class T:
        def __call__(self, method, url, data, headers, timeout):
            return meta_client.HttpResult(200, json.dumps(
                {"status": "completed", "output": [], "usage": {
                    "input_tokens": 1000, "output_tokens": 10}}).encode())
    c = meta_client.MetaClient(key="k", transport=T(), cache_dir=tmp_path,
                               usage_log=tmp_path / "u.jsonl")
    with psycopg.connect(seeded_db) as conn:
        conn.execute("DELETE FROM meta_usage")
    c.responses({"input": "x"}, cache=False)
    assert c.spent() == pytest.approx((1000 * 1.25 + 10 * 4.25) / 1e6,
                                      abs=1e-6)
    (tmp_path / "u.jsonl").unlink()   # a restart loses the file log
    assert c.spent() > 0


def test_private_mode_unchanged(seeded_db, monkeypatch):
    monkeypatch.delenv("KOHU_PUBLIC_DEMO", raising=False)
    with demo.visitor_scope("a" * 16):
        assert demo.current_visitor() is None
    assert retrieval.search("days off", "employee", seeded_db)
