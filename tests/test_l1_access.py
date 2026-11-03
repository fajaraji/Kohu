"""L1 done-condition: Employee answers from the licensed report, never the XLSX."""

import json

import app

Q = "What was Viet Nam's GDP growth in 2023?"


def ask(persona, db, q=Q):
    return app.run_ask(persona, q, db, str(app.DEFAULT_CORPUS),
                       _spark=app.SparkSynthesizer(force_off=True))


def test_employee_cites_report_page_never_dataset(seeded_db):
    res = ask("employee", seeded_db)
    cites = [c["citation"] for c in res["claims"]]
    assert any(c["source_id"] == "asean-outlook-report"
               and c["pointer"].startswith("p.") for c in cites)
    assert "asean-indicators-dataset" not in json.dumps(res)


def test_analyst_may_cite_dataset_cells(seeded_db):
    res = ask("analyst", seeded_db, "Viet Nam GDP growth dataset row")
    assert "asean-indicators-dataset" in res["sources"]
