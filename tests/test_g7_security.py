"""G7: security fixes from the review."""

import uuid

import pytest
from fastapi.testclient import TestClient

import app as kohu
import demo


@pytest.fixture(scope="module")
def client(seeded_db):
    with TestClient(kohu.app) as c:
        yield c


def hdr(c, persona, visitor=None):
    body = {"persona": persona}
    if visitor:
        body["visitor"] = visitor
    return {"Authorization": "Bearer " + c.post("/login", json=body)
            .json()["token"]}


def test_security_headers_on_every_response(client):
    for path in ("/", "/health", "/files/asean-outlook-report?token=x"):
        r = client.get(path)
        assert r.headers["referrer-policy"] == "no-referrer"
        assert r.headers["x-content-type-options"] == "nosniff"
        assert "frame-ancestors 'none'" in r.headers["content-security-policy"]


def test_trace_only_for_the_asker(client):
    rid = uuid.uuid4().hex
    analyst = hdr(client, "analyst")
    r = client.post("/ask", headers=analyst,
                    json={"query": "days off", "run_id": rid})
    assert r.status_code == 200
    assert client.get("/runs/%s/steps" % rid, headers=analyst).status_code \
        == 200
    other = client.get("/runs/%s/steps" % rid, headers=hdr(client, "employee"))
    assert other.status_code == 404
    assert "days off" not in other.text


def test_cloudflare_ip_header_needs_opt_in(monkeypatch):
    class Req:
        headers = {"cf-connecting-ip": "1.2.3.4"}

        class client:
            host = "10.0.0.9"
    monkeypatch.delenv("KOHU_BEHIND_CLOUDFLARE", raising=False)
    assert kohu.client_ip(Req) == "10.0.0.9"
    monkeypatch.setenv("KOHU_BEHIND_CLOUDFLARE", "1")
    assert kohu.client_ip(Req) == "1.2.3.4"


def test_public_mode_refuses_weak_secret(monkeypatch, seeded_db):
    monkeypatch.setenv("KOHU_PUBLIC_DEMO", "1")
    monkeypatch.setenv("KOHU_SESSION_SECRET", "short")
    with pytest.raises(RuntimeError):
        with TestClient(kohu.app):
            pass


def test_upload_rejects_non_video(client):
    before = set(kohu.CORPUS_DIR.glob("uploads/*.mp4"))
    r = client.post("/videos", headers=hdr(client, "manager"),
                    files={"file": ("x.mp4", b"not a video at all",
                                    "video/mp4")})
    assert r.status_code == 422
    assert set(kohu.CORPUS_DIR.glob("uploads/*.mp4")) == before


def test_cells_window_is_capped(client):
    r = client.get("/cells/asean-indicators-dataset",
                   params={"range": "Data!A2:J9999"},
                   headers=hdr(client, "analyst"))
    assert r.status_code == 200 and len(r.json()["rows"]) <= 61


def test_visitor_ids_are_unguessable():
    import auth
    assert len(auth.new_visitor()) == 16
    assert demo.public() is False


def test_slide_images_served_with_access_check(client):
    r = client.get("/files/regional-expansion-deck/slide/4.png",
                   headers=hdr(client, "employee"))
    assert r.status_code == 200 and r.content[:4] == b"\x89PNG"
    assert client.get("/files/regional-expansion-deck/slide/99.png",
                      headers=hdr(client, "employee")).status_code == 404
    assert client.get("/files/team-performance/slide/1.png",
                      headers=hdr(client, "employee")).status_code == 403
