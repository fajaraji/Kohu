"""A3-A5: video steps validation, marks, review and approval."""

import json

import pytest
from fastapi.testclient import TestClient

import app as kohu
import marks
import meta_client
import video
from conftest import FIXTURES

TURNS = [{"start": 6.0, "end": 8.4, "text": "First, open orders."},
         {"start": 14.1, "end": 22.9, "text": "We only refund delivered "
          "orders because a shipped order can still be stopped."}]


def test_parse_live_asr_shape():
    turns = video.parse_turns(json.loads(
        (FIXTURES / "live_asr.json").read_text()))
    assert turns[1]["start"] == 5.98 and "left menu" in turns[1]["text"]


def test_validate_steps_rules():
    raw = [
        {"t_start": 6.3, "t_end": 8, "instruction": "Open Orders",
         "reason": "because the manager said so", "target_phrase": "Orders"},
        {"t_start": 14.4, "t_end": 22, "instruction": "Open the order",
         "reason": "a shipped order can still be stopped",
         "target_phrase": "order row"},
        {"t_start": 12.0, "t_end": 13, "instruction": "Out of order",
         "reason": None, "target_phrase": None},
        {"t_start": 99.0, "t_end": 100, "instruction": "After the end",
         "reason": None, "target_phrase": None}]
    steps, notes = video.validate_steps(raw, 60.0, TURNS)
    assert [s["n"] for s in steps] == [1, 2]
    assert steps[0]["t_start"] == 6.0          # snapped to the turn
    assert steps[0]["reason"] is None          # never spoken
    assert steps[1]["reason"].startswith("a shipped order")
    assert any("outside the video" in n for n in notes)
    assert any("out of order" in n for n in notes)


class FailingClient:
    enabled = True

    def sam(self, *a, **k):
        raise meta_client.MetaError("HTTP 500")

    def responses(self, *a, **k):
        raise meta_client.MetaError("HTTP 500")


def test_sam_failure_never_fails_the_guide(tmp_path):
    vid = kohu.CORPUS_DIR / "demo-app" / "refund-process.mp4"
    out = marks.mark_step(FailingClient(), vid, {
        "n": 1, "t_start": 6.0, "t_end": 8.0, "instruction": "Open Orders",
        "target_phrase": "Orders"}, tmp_path)
    assert out["mark_status"] == "failed" and out["frame_path"]
    assert (tmp_path / out["frame_path"]).exists()


@pytest.fixture(scope="module")
def client(seeded_db):
    video.seed(seeded_db)
    with TestClient(kohu.app) as c:
        yield c


def tok(client, persona):
    return {"Authorization": "Bearer " + client.post(
        "/login", json={"persona": persona}).json()["token"]}


def test_seeded_steps_are_cited_by_time(client, seeded_db):
    import psycopg
    with psycopg.connect(seeded_db) as c:
        rows = c.execute("SELECT t_start, text_origin FROM chunks WHERE "
                         "source_id = 'refund-process-video'").fetchall()
    assert len(rows) == 9 and all(r[1] == "video-step" for r in rows)


def test_employee_cannot_upload_or_edit(client):
    h = tok(client, "employee")
    r = client.post("/videos", headers=h,
                    files={"file": ("a.mp4", b"x", "video/mp4")})
    assert r.status_code == 403
    r = client.patch("/videos/refund-process-video/steps/1", headers=h,
                     json={"instruction": "x"})
    assert r.status_code == 403


def test_steps_endpoint_and_assets(client):
    h = tok(client, "employee")
    r = client.get("/videos/refund-process-video/steps", headers=h)
    assert r.status_code == 200 and len(r.json()["steps"]) == 9
    step = r.json()["steps"][3]
    assert step["mark_status"] in ("phrase", "box", "spark_box")
    a = client.get("/files/refund-process-video/assets/" + step["mask_path"],
                   headers=h)
    assert a.status_code == 200 and a.content[:4] == b"\x89PNG"
    v = client.get("/files/refund-process-video", headers={
        **h, "Range": "bytes=0-99"})
    assert v.status_code == 206


def test_review_edit_unapproves_then_approve_rebuilds(client, seeded_db):
    h = tok(client, "manager")
    r = client.patch("/videos/refund-process-video/steps/2", headers=h,
                     json={"instruction": "Search for the order number.",
                           "shift_s": 0.5})
    assert r.status_code == 200
    emp = client.get("/videos/refund-process-video/steps",
                     headers=tok(client, "employee")).json()["steps"]
    assert 2 not in [s["n"] for s in emp]       # unapproved are hidden
    r = client.post("/videos/refund-process-video/approve", headers=h,
                    json={"steps": [2]})
    assert r.json()["approved"] == 9
    video.seed(seeded_db)                       # restore committed review
