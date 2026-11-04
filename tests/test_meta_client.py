"""MetaClient tests against fake transports and doc-shaped fixtures."""

import json

import pytest

import meta_client as mc
from conftest import FIXTURES


class FakeTransport:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def __call__(self, method, url, data, headers, timeout):
        self.calls.append({"method": method, "url": url, "data": data,
                           "headers": headers})
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        status, body = reply[0], reply[1]
        hdrs = reply[2] if len(reply) > 2 else {}
        if not isinstance(body, (bytes, str)):
            body = json.dumps(body)
        if isinstance(body, str):
            body = body.encode()
        return mc.HttpResult(status, body, hdrs)


def fixture(name):
    return json.loads((FIXTURES / name).read_text())


def make(tmp_path, replies, **kw):
    t = FakeTransport(replies)
    c = mc.MetaClient(key="test-key", transport=t,
                      cache_dir=tmp_path / "cache",
                      usage_log=tmp_path / "usage.jsonl",
                      sleep=lambda s: None, **kw)
    return c, t


def test_responses_parses_text_and_logs_usage(tmp_path):
    c, t = make(tmp_path, [(200, fixture("responses_text.json"))])
    payload = c.responses({"input": "hi"}, label="t")
    assert mc.output_text(payload) == "Fixture answer."
    assert t.calls[0]["url"] == "https://api.meta.ai/v1/responses"
    assert t.calls[0]["headers"]["Authorization"] == "Bearer test-key"
    sent = json.loads(t.calls[0]["data"])
    assert sent["model"] == "muse-spark-1.3"
    line = json.loads((tmp_path / "usage.jsonl").read_text().splitlines()[0])
    assert line["input_tokens"] == 120 and line["output_tokens"] == 8
    assert "test-key" not in (tmp_path / "usage.jsonl").read_text()
    assert line["usd"] == pytest.approx((120 * 1.25 + 8 * 4.25) / 1e6,
                                        abs=1e-6)


def test_cache_prevents_second_call(tmp_path):
    c, t = make(tmp_path, [(200, fixture("responses_text.json"))])
    c.responses({"input": "same"})
    c.responses({"input": "same"})
    assert len(t.calls) == 1 and c.cache_hits == 1


def test_read_only_disk_falls_back_to_tmp(tmp_path, monkeypatch):
    """On a read-only deploy (Vercel) the cache moves to /tmp and the file
    usage log is skipped; the call itself still succeeds once."""
    blocker = tmp_path / "file"
    blocker.write_text("x")                      # mkdir under a file fails
    monkeypatch.setattr(mc, "TMP_CACHE", tmp_path / "tmp-cache")
    t = FakeTransport([(200, fixture("responses_text.json"))])
    c = mc.MetaClient(key="test-key", transport=t,
                      cache_dir=blocker / "cache",
                      usage_log=blocker / "usage.jsonl",
                      sleep=lambda s: None)
    c.responses({"input": "ro"})
    c.responses({"input": "ro"})
    assert len(t.calls) == 1 and c.cache_hits == 1
    assert list((tmp_path / "tmp-cache").glob("*.json"))


def test_retry_on_429_and_5xx(tmp_path):
    c, t = make(tmp_path, [(429, {"error": "slow"}, {"Retry-After": "0"}),
                           (503, {"error": "busy"}),
                           (200, fixture("responses_text.json"))])
    payload = c.responses({"input": "retry"})
    assert mc.output_text(payload) == "Fixture answer."
    assert len(t.calls) == 3


def test_gives_up_after_max_attempts(tmp_path):
    c, t = make(tmp_path, [(500, {})] * mc.MAX_ATTEMPTS)
    with pytest.raises(mc.MetaError):
        c.responses({"input": "x"}, cache=False)
    assert len(t.calls) == mc.MAX_ATTEMPTS


def test_4xx_not_retried(tmp_path):
    c, t = make(tmp_path, [(400, {"error": {"message": "bad schema"}})])
    with pytest.raises(mc.MetaError, match="bad schema"):
        c.responses({"input": "x"}, cache=False)
    assert len(t.calls) == 1


def test_proxy_denial_is_unavailable_without_retry_storm(tmp_path):
    c, t = make(tmp_path, [OSError("Tunnel connection failed: 403")])
    with pytest.raises(mc.MetaUnavailable):
        c.responses({"input": "x"}, cache=False)
    with pytest.raises(mc.MetaUnavailable):
        c.responses({"input": "y"}, cache=False)  # cooling down, no call
    assert len(t.calls) == 1


def test_budget_stop(tmp_path):
    c, t = make(tmp_path, [], spend_limit=0.001)
    (tmp_path / "usage.jsonl").write_text(json.dumps({"usd": 0.002}) + "\n")
    with pytest.raises(mc.BudgetExceeded):
        c.responses({"input": "x"}, cache=False)
    assert t.calls == []


def test_no_key_is_unavailable(tmp_path):
    c = mc.MetaClient(key="", cache_dir=tmp_path, usage_log=tmp_path / "u")
    assert not c.enabled
    with pytest.raises(mc.MetaUnavailable):
        c.responses({"input": "x"}, cache=False)


def test_background_polls_until_completed(tmp_path):
    done = fixture("responses_text.json")
    c, t = make(tmp_path, [(200, {"id": "resp_bg", "status": "queued"}),
                           (200, {"id": "resp_bg", "status": "in_progress"}),
                           (200, done)])
    seen = []
    payload = c.responses_background({"input": "long"}, on_poll=seen.append)
    assert mc.output_text(payload) == "Fixture answer."
    assert json.loads(t.calls[0]["data"])["background"] is True
    assert t.calls[1]["method"] == "GET"
    assert t.calls[1]["url"].endswith("/responses/resp_bg")
    assert seen == ["in_progress", "completed"]


def test_background_failure_raises(tmp_path):
    c, t = make(tmp_path, [(200, {"id": "r", "status": "queued"}),
                           (200, {"id": "r", "status": "failed"})])
    with pytest.raises(mc.MetaError):
        c.responses_background({"input": "x"}, cache=False)


def test_function_calls_parsed(tmp_path):
    calls = mc.function_calls(fixture("responses_function_call.json"))
    assert calls == [{"call_id": "call_1", "name": "search_knowledge",
                      "arguments": {"terms": "expense receipts"}}]


def test_output_json_tolerates_fences():
    payload = {"output": [{"type": "message", "content": [
        {"type": "output_text", "text": "```json\n{\"a\": 1}\n```"}]}]}
    assert mc.output_json(payload) == {"a": 1}


def test_upload_and_transcribe_multipart(tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"\x00" * 64)
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"\x00" * (44 + 32000 * 10))
    c, t = make(tmp_path, [(200, fixture("files_upload.json")),
                           (200, fixture("asr_turns.json"))])
    up = c.upload_file(video)
    assert up["id"] == "file-fixture123"
    assert b'name="purpose"' in t.calls[0]["data"]
    assert b"user_data" in t.calls[0]["data"]
    tr = c.transcribe(wav)
    body = t.calls[1]["data"]
    assert t.calls[1]["url"].endswith("/asr/transcribe")
    assert b'"audioEncoding": "WAV"' in body and b'name="audio"' in body
    assert tr["turns"][0]["startMs"] == 1200
    lines = [json.loads(x) for x in
             (tmp_path / "usage.jsonl").read_text().splitlines()]
    asr = [x for x in lines if x["kind"] == "asr"][0]
    assert asr["audio_seconds"] == pytest.approx(10.0)
    assert asr["usd"] == pytest.approx(10 / 3600 * 0.18, abs=1e-6)


def test_sam_request_shape_and_cost(tmp_path):
    text = (FIXTURES / "sam_two_records.txt").read_text().strip()
    payload = {"id": "r", "status": "completed", "output": [
        {"type": "message", "content": [{"type": "output_text",
                                         "text": text}]}]}
    c, t = make(tmp_path, [(200, payload), (200, {"status": "completed",
                                                  "output": []})])
    out = c.sam(b"PNGDATA", "button")
    sent = json.loads(t.calls[0]["data"])
    assert sent["model"] == "sam-3.1"
    content = sent["input"][0]["content"]
    assert content[0] == {"type": "input_text", "text": "button"}
    assert content[1]["image_url"].startswith("data:image/png;base64,")
    assert out.startswith("<0f>0<|box;")
    assert c.sam(b"OTHER", "nothing here") == ""  # empty = no match
    lines = [json.loads(x) for x in
             (tmp_path / "usage.jsonl").read_text().splitlines()]
    assert sum(x["usd"] for x in lines) == pytest.approx(2 * 0.0025)


def test_base_accepts_full_responses_url(tmp_path):
    c = mc.MetaClient(key="k", base="https://api.meta.ai/v1/responses",
                      cache_dir=tmp_path, usage_log=tmp_path / "u")
    assert c.base == "https://api.meta.ai/v1"
