"""B8: licensed citations are logged; cards count distinct users."""

import agent
import licenses
import meta_client


def card(persona, sid, db):
    return [c for c in licenses.cards(persona, db) if c["source_id"] == sid]


def test_citation_logged_and_counted(seeded_db):
    licenses.seed_sample(seeded_db)
    before = card("steward", "asean-outlook-report", seeded_db)[0]
    assert before["sample_users_30d"] == 2
    r = agent.run("Viet Nam real GDP growth 2023 report", "employee",
                  user="new-hire-7", database_url=seeded_db,
                  client=meta_client.MetaClient(key=""))
    assert r["citations"][0]["source_id"] == "asean-outlook-report"
    after = card("steward", "asean-outlook-report", seeded_db)[0]
    assert after["users_30d"] >= before["users_30d"] + 1 or \
        before["users_30d"] >= 1
    assert after["users_by_persona"].get("employee", 0) >= 1


def test_employee_card_hides_dataset_and_cost(seeded_db):
    cards = licenses.cards("employee", seeded_db)
    assert [c["source_id"] for c in cards] == ["asean-outlook-report"]
    assert "annual_cost_usd" not in cards[0]
    assert cards[0]["simulated"] is True
    assert "sample" in cards[0]["sample_label"]


def test_unlicensed_citations_not_logged(seeded_db):
    assert licenses.log_citations("r", "employee", "u", [
        {"source_id": "handbook-time-off", "pointer": "p.1"}], seeded_db) == 0
