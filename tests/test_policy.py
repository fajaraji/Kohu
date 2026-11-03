"""L1: license coverage and role access."""

import policy

EVERYONE = set(policy.PERSONAS)


def test_report_is_company_wide():
    for p in policy.PERSONAS:
        assert policy.can_see(p, "asean-outlook-report")
    assert "Company-wide" in policy.license_info(
        "asean-outlook-report")["coverage"]


def test_dataset_is_seat_limited():
    assert {p for p in policy.PERSONAS
            if policy.can_see(p, "asean-indicators-dataset")} == \
        {"analyst", "steward"}


def test_performance_is_manager_and_steward():
    assert {p for p in policy.PERSONAS
            if policy.can_see(p, "team-performance")} == {"manager", "steward"}


def test_steward_sees_everything():
    import corpus
    assert set(policy.visible_sources("steward")) == {
        e["id"] for e in corpus.load_manifest()["entries"]}


def test_license_labels_are_simulated():
    for sid in policy.LICENSE_REGISTRY:
        assert policy.license_info(sid)["simulated"] is True


def test_enforce_drops_smuggled_rows():
    rows = [{"source_id": "asean-indicators-dataset", "text": "SECRET"},
            {"source_id": "asean-outlook-report", "text": "ok"}]
    out = policy.enforce(rows, "employee")
    assert [r["source_id"] for r in out["allowed"]] == ["asean-outlook-report"]
    assert out["allowed"][0]["license"]["seats"] is None


def test_unknown_persona_rejected():
    import pytest
    with pytest.raises(ValueError):
        policy.visible_sources("intern")
