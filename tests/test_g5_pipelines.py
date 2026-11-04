"""G5: model pipelines with fake clients (no network)."""

import json
import pathlib

import psycopg
import pytest

import marks
import meta_client
import regions
import video
from conftest import FIXTURES, REPO

W, H = 1280, 720
TARGET = {"x1": 251, "y1": 229, "x2": 367, "y2": 266}


def sam_line(b, w=W, h=H):
    return ("<0f>0<|box;x1=%d;y1=%d;x2=%d;y2=%d;w=%d;h=%d|>"
            "<|mask;x=0;y=0;data=2,2,~!!!!!|>"
            % (b["x1"], b["y1"], b["x2"] - 1, b["y2"] - 1, w, h))


def msg(text):
    return {"id": "r", "status": "completed", "output": [
        {"type": "message", "content": [{"type": "output_text",
                                         "text": text}]}]}


class FakeClient:
    """Plays the Meta API: ASR, Files, Spark (background and boxes), SAM."""

    enabled = True

    def __init__(self, phrase=None, box=TARGET, spark_box=TARGET,
                 fail_asr=False):
        self.phrase, self.box, self.spark = phrase, box, spark_box
        self.fail_asr = fail_asr
        self.calls = []

    def transcribe(self, wav, label=None, audio_seconds=None):
        self.calls.append("asr")
        if self.fail_asr:
            raise meta_client.MetaError("HTTP 500")
        return json.loads((FIXTURES / "live_asr.json").read_text())

    def upload_file(self, path, label=None):
        self.calls.append("upload")
        return {"id": "file-fake"}

    def responses_background(self, body, label=None, on_poll=None, **kw):
        self.calls.append("video")
        content = body["input"][0]["content"]
        assert content[0] == {"type": "input_video", "file_id": "file-fake"}
        assert "[6.0s-8.4s] First, open orders" in content[1]["text"]  # timed transcript
        assert body["text"]["format"]["type"] == "json_schema"
        if on_poll:
            on_poll("in_progress")
        return json.loads((FIXTURES / "live_video_steps.json").read_text())

    def responses(self, body, label=None, cache=True):
        self.calls.append("spark-box")
        if self.spark is None:
            return msg(json.dumps({"x1": 0, "y1": 0, "x2": 0, "y2": 0,
                                   "found": False}))
        return msg(json.dumps(dict(self.spark, found=True)))

    def sam(self, png, prompt, label=None, **kw):
        if prompt.startswith("<0f>"):
            self.calls.append("sam-box")
            return sam_line(self.box) if self.box else ""
        self.calls.append("sam-phrase")
        return sam_line(self.phrase) if self.phrase else ""


@pytest.fixture()
def tmp_corpus(tmp_path):
    """A corpus with only the demo video, so derived files stay in tmp."""
    (tmp_path / "demo-app").mkdir()
    (tmp_path / "demo-app" / "refund-process.mp4").symlink_to(
        REPO / "corpus" / "demo-app" / "refund-process.mp4")
    entry = next(e for e in json.loads(
        (REPO / "corpus" / "manifest.json").read_text())["entries"]
        if e["id"] == "refund-process-video")
    (tmp_path / "manifest.json").write_text(json.dumps(
        {"entries": [entry], "chunking": {"sheet_windows": {}}}))
    return tmp_path


def test_process_end_to_end_with_fake_client(tmp_corpus, seeded_db):
    fake = FakeClient()
    out = video.process("refund-process-video", seeded_db, tmp_corpus,
                        client=fake)
    try:
        assert fake.calls[:3] == ["asr", "upload", "video"]
        assert len(out["steps"]) == 9
        assert [s["n"] for s in out["steps"]] == list(range(1, 10))
        starts = [s["t_start"] for s in out["steps"]]
        assert starts == sorted(starts)
        st = video.status("refund-process-video", seeded_db)
        assert st["status"] == "ready for review"
        rows = video.steps("refund-process-video", seeded_db)
        assert all(r["mark_status"] == "box" for r in rows)
        assert not any(r["approved"] for r in rows)
        d = tmp_corpus / "derived" / "refund-process-video"
        assert (d / "step-01-frame.png").exists()
        assert (d / "step-01-mask.png").exists()
    finally:
        video.seed(seeded_db)  # restore the committed reviewed steps


def test_process_failure_sets_status_and_raises(tmp_corpus, seeded_db):
    with pytest.raises(meta_client.MetaError):
        video.process("refund-process-video", seeded_db, tmp_corpus,
                      client=FakeClient(fail_asr=True))
    st = video.status("refund-process-video", seeded_db)
    assert st["status"] == "failed" and "HTTP 500" in st["detail"]["error"]
    video.seed(seeded_db)


def frame():
    return (REPO / "corpus" / "demo-app" / "frames" / "step-04.png").read_bytes()


@pytest.mark.parametrize("phrase,box,spark,want", [
    (TARGET, TARGET, TARGET, "phrase"),                 # phrase agrees
    ({"x1": 420, "y1": 202, "x2": 860, "y2": 518},       # phrase too large
     TARGET, TARGET, "box"),
    ({"x1": 900, "y1": 600, "x2": 950, "y2": 640},       # phrase elsewhere
     TARGET, TARGET, "box"),
    (None, None, TARGET, "spark_box"),                   # SAM finds nothing
    (None, None, None, "failed"),                        # Spark finds nothing
])
def test_mark_image_paths(tmp_path, phrase, box, spark, want):
    status, info = marks.mark_image(
        FakeClient(phrase=phrase, box=box, spark_box=spark), frame(),
        "Check stock button", W, H, tmp_path / "m.png",
        context="Click Check stock")
    assert status == want
    if want != "failed":
        assert (tmp_path / "m.png").exists()
        assert marks.iou(info, TARGET) > 0.9


def test_mark_image_model_error_is_failed_not_raised(tmp_path):
    class Broken(FakeClient):
        def responses(self, *a, **k):
            raise meta_client.MetaError("HTTP 503")
    status, info = marks.mark_image(Broken(), frame(), "x", W, H,
                                    tmp_path / "m.png")
    assert status == "failed" and "HTTP 503" in info["reason"]


def test_regions_mark_page_reads_crop(tmp_path):
    entry = {"id": "asean-outlook-report",
             "filename": "licensed/asean-outlook-report.pdf"}

    class C(FakeClient):
        def sam(self, png, prompt, label=None, **kw):
            assert prompt == "bar chart"
            return sam_line({"x1": 134, "y1": 206, "x2": 736, "y2": 431},
                            828, 1171)

        def responses(self, body, label=None, cache=True):
            assert body["input"][0]["content"][0]["image_url"].startswith(
                "data:image/png")
            return msg("Viet Nam: 7.0")
    rows = regions.mark_page(entry, 4, "bar chart", C(), tmp_path)
    assert rows[0]["reading"] == "Viet Nam: 7.0"
    assert rows[0]["box"]["x1"] == 134
    assert (tmp_path / rows[0]["mask_png"]).exists()


def test_regions_no_match_is_recorded(tmp_path):
    class C(FakeClient):
        def sam(self, *a, **k):
            return ""
    rows = regions.mark_page({"id": "asean-outlook-report",
                              "filename": "licensed/asean-outlook-report.pdf"},
                             3, "table", C(), tmp_path)
    assert rows == [{"k": 1, "box": None, "page_png": "page-03.png",
                     "mask_png": None, "reading": None,
                     "status": "no match"}]


def test_seeded_steps_match_committed_review(seeded_db):
    video.seed(seeded_db)
    data = json.loads((REPO / "corpus" / "demo-app" /
                       "refund-process.steps.json").read_text())
    with psycopg.connect(seeded_db) as c:
        n = c.execute("SELECT count(*) FROM guide_steps WHERE source_id = "
                      "'refund-process-video' AND approved").fetchone()[0]
    assert n == len(data["steps"]) == 9
    assert pathlib.Path(REPO / "corpus" / "derived" / "refund-process-video"
                        / data["steps"][0]["mask_path"]).exists()
