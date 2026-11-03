"""B1: signed tokens, persona from token, guarded file route."""

import pytest
from fastapi.testclient import TestClient

import app as kohu
import auth


@pytest.fixture(scope="module")
def client(seeded_db):
    with TestClient(kohu.app) as c:
        yield c


def login(client, persona):
    r = client.post("/login", json={"persona": persona})
    assert r.status_code == 200
    return r.json()["token"]


def test_token_roundtrip_and_tamper():
    t = auth.issue("employee")
    assert auth.verify(t)["persona"] == "employee"
    payload, sig = t.rsplit(".", 1)
    forged = auth.issue("steward").rsplit(".", 1)[0] + "." + sig
    with pytest.raises(auth.AuthError):
        auth.verify(forged)
    with pytest.raises(auth.AuthError):
        auth.verify(auth.issue("employee", now=1))  # expired


def test_unknown_persona_login_422(client):
    assert client.post("/login", json={"persona": "admin"}).status_code == 422


def test_employee_403_on_dataset_xlsx(client):
    t = login(client, "employee")
    r = client.get("/files/asean-indicators-dataset", params={"token": t})
    assert r.status_code == 403


def test_employee_can_open_company_wide_report(client):
    t = login(client, "employee")
    r = client.get("/files/asean-outlook-report",
                   headers={"Authorization": "Bearer " + t})
    assert r.status_code == 200 and r.content[:4] == b"%PDF"


def test_analyst_can_open_dataset(client):
    t = login(client, "analyst")
    r = client.get("/files/asean-indicators-dataset", params={"token": t})
    assert r.status_code == 200 and r.content[:2] == b"PK"


def test_no_token_401_and_no_corpus_mount(client):
    assert client.get("/files/asean-outlook-report").status_code == 401
    r = client.get("/corpus/licensed/asean-indicators-dataset.xlsx")
    assert r.status_code == 404


def test_ask_ignores_persona_in_body(client):
    t = login(client, "employee")
    r = client.post("/ask", json={"query": "Viet Nam GDP growth dataset row",
                                  "persona": "steward"},
                    headers={"Authorization": "Bearer " + t})
    assert r.status_code == 200
    assert r.json()["persona"] == "employee"
    assert "asean-indicators-dataset" not in r.text


def test_steward_queue_needs_steward_token(client):
    t = login(client, "employee")
    r = client.get("/steward/queue", headers={"Authorization": "Bearer " + t})
    assert r.status_code == 403


def test_sources_list_filtered(client):
    t = login(client, "employee")
    ids = {s["source_id"] for s in client.get(
        "/sources", headers={"Authorization": "Bearer " + t}).json()["sources"]}
    assert "asean-outlook-report" in ids
    assert "asean-indicators-dataset" not in ids
    assert "team-performance" not in ids


def test_ask_run_id_validation(client):
    t = {"Authorization": "Bearer " + login(client, "employee")}
    r = client.post("/ask", json={"query": "days off", "run_id": "nothex"},
                    headers=t)
    assert r.status_code == 422
    rid = "ab" * 16
    r = client.post("/ask", json={"query": "days off", "run_id": rid},
                    headers=t)
    assert r.status_code == 200 and r.json()["run_id"] == rid
    steps = client.get("/runs/%s/steps" % rid, headers=t).json()["steps"]
    assert steps[-1]["kind"] == "result"
    r = client.post("/ask", json={"query": "days off", "run_id": rid},
                    headers=t)
    assert r.status_code == 409
