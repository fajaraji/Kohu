"""B2: Spark page reading for scanned and chart pages."""

import pathlib

import ingest
import vision

REPO = pathlib.Path(__file__).resolve().parent.parent


class FakeClient:
    enabled = True

    def __init__(self):
        self.bodies = []

    def responses(self, body, label=None):
        self.bodies.append(body)
        return {"output": [{"type": "message", "content": [
            {"type": "output_text", "text": "Viet Nam: 7.0"}]}]}


def test_only_scan_and_chart_pages_need_vision():
    flagged = []
    for sid, rel in (("scan", "handbook/handbook-training-scan.pdf"),
                     ("report", "licensed/asean-outlook-report.pdf"),
                     ("hb", "handbook/handbook-time-off.pdf")):
        for n, _t, needs, png in ingest.parse_pdf_pages(REPO / "corpus" / rel):
            if needs:
                assert png and png[:4] == b"\x89PNG"
                flagged.append((sid, n))
    assert flagged == [("scan", 1), ("report", 4)]


def test_reader_sends_one_page_image():
    fake = FakeClient()
    r = vision.PageReader(client=fake)
    assert r.read_page("asean-outlook-report", 4, b"\x89PNGxx") == \
        "Viet Nam: 7.0"
    content = fake.bodies[0]["input"][0]["content"]
    assert content[0]["image_url"].startswith("data:image/png;base64,")
    assert len(fake.bodies) == 1


def test_seed_db_falls_back_to_labeled_sidecar(seeded_db):
    import psycopg
    with psycopg.connect(seeded_db) as c:
        origin = c.execute(
            "SELECT text_origin FROM chunks WHERE source_id = "
            "'handbook-training-scan'").fetchone()[0]
    assert origin in ("sidecar-fallback", "spark-vision")
