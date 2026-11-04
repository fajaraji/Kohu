"""U1 spike: run each Meta API capability Kohu depends on, record results.

  python api/spike.py            # writes docs/spike-results.json and
                                 # tests/fixtures/meta/live_*.json samples

Checks: ASR on the demo clip audio, video understanding through the
Files API in background mode with timed steps, SAM 3.1 on five app
screenshots (noun phrase and box prompt, plus a Spark-proposed box), SAM
on three PDF chart and table pages, and the SAM mask parser. Every check
records its own result or its own error; nothing is filled in by hand.
"""

import json
import pathlib
import subprocess
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))

import meta_client as mc  # noqa: E402
import sam_parse  # noqa: E402

APP = REPO / "corpus" / "demo-app"
CLIP = APP / "refund-process.mp4"
REPORT = REPO / "corpus" / "licensed" / "asean-outlook-report.pdf"
FIX = REPO / "tests" / "fixtures" / "meta"

STEP_SCHEMA = {
    "type": "object",
    "properties": {"steps": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "t_start": {"type": "number"},
            "t_end": {"type": "number"},
            "instruction": {"type": "string"},
            "reason": {"type": ["string", "null"]},
            "target_phrase": {"type": ["string", "null"]}},
        "required": ["t_start", "t_end", "instruction", "reason",
                     "target_phrase"],
        "additionalProperties": False}}},
    "required": ["steps"], "additionalProperties": False}

BOX_SCHEMA = {
    "type": "object",
    "properties": {"x1": {"type": "integer"}, "y1": {"type": "integer"},
                   "x2": {"type": "integer"}, "y2": {"type": "integer"},
                   "found": {"type": "boolean"}},
    "required": ["x1", "y1", "x2", "y2", "found"],
    "additionalProperties": False}


def iou(a, b):
    ix = max(0, min(a["x2"], b["x2"]) - max(a["x1"], b["x1"]))
    iy = max(0, min(a["y2"], b["y2"]) - max(a["y1"], b["y1"]))
    inter = ix * iy
    ua = ((a["x2"] - a["x1"]) * (a["y2"] - a["y1"])
          + (b["x2"] - b["x1"]) * (b["y2"] - b["y1"]) - inter)
    return round(inter / ua, 3) if ua else 0.0


def save_fixture(name, payload):
    FIX.mkdir(parents=True, exist_ok=True)
    (FIX / ("live_" + name + ".json")).write_text(
        json.dumps(payload, indent=1)[:200000])


def wav_from(video, out):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video),
                    "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
                    str(out)], check=True)


def spike_asr(client, truth, tmp):
    wav = tmp / "clip.wav"
    wav_from(CLIP, wav)
    t = time.time()
    payload = client.transcribe(wav, label="spike-asr")
    save_fixture("asr", payload)
    return {"seconds": round(time.time() - t, 1),
            "top_keys": sorted(payload.keys()) if isinstance(payload, dict)
            else str(type(payload)),
            "sample": json.dumps(payload)[:1500]}


def spike_video(client, truth, transcript_text):
    t0 = time.time()
    up = client.upload_file(CLIP, label="spike-video")
    t_upload = time.time() - t0
    save_fixture("files_upload", up)
    prompt = (
        "This screen recording shows how to do a task in a back office app. "
        "Split it into the steps a new employee must perform. For each step "
        "give t_start and t_end in seconds from the start of the video, a "
        "short imperative instruction, the reason ONLY if the narrator says "
        "why out loud (else null), and target_phrase: a 1 to 4 word noun "
        "phrase naming the on-screen element the step acts on (else null).\n"
        "Transcript for reference:\n" + transcript_text)
    body = {"input": [{"role": "user", "content": [
        {"type": "input_video", "file_id": up.get("id")},
        {"type": "input_text", "text": prompt}]}],
        "text": {"format": {"type": "json_schema", "name": "guide_steps",
                            "schema": STEP_SCHEMA, "strict": True}}}
    polls = []
    t1 = time.time()
    payload = client.responses_background(
        body, label="spike-video-steps", poll_interval=3,
        on_poll=lambda s: polls.append((round(time.time() - t1, 1), s)))
    save_fixture("video_steps", payload)
    steps = mc.output_json(payload)["steps"]
    truth_starts = [s["start"] for s in truth["steps"] if s.get("action")]
    errs = []
    for s in steps:
        nearest = min(truth_starts, key=lambda x: abs(x - s["t_start"]))
        errs.append(round(abs(nearest - s["t_start"]), 2))
    return {"upload_seconds": round(t_upload, 1),
            "processing_seconds": round(time.time() - t1, 1),
            "polls": polls, "usage": payload.get("usage"),
            "n_steps": len(steps), "steps": steps,
            "abs_error_to_nearest_truth_start_s": errs,
            "median_error_s": sorted(errs)[len(errs) // 2] if errs else None}


def spike_sam_ui(client, truth):
    out = []
    picks = [s for s in truth["steps"] if s.get("frame")]
    picks = [picks[i] for i in (0, 1, 3, 4, 6)]
    for s in picks:
        png = (APP / "frames" / s["frame"]).read_bytes()
        tb = s["box"]
        rec = {"frame": s["frame"], "target": s["target"], "truth_box": tb}
        try:
            text = client.sam(png, s["target"], label="spike-sam-phrase")
            r = sam_parse.parse(text)
            b = sam_parse.best(r)
            rec["phrase"] = {"records": len(r),
                             "iou": iou(b["box"], tb) if b else 0.0,
                             "box": b["box"] if b else None,
                             "raw": text[:300]}
        except mc.MetaError as e:
            rec["phrase"] = {"error": str(e)}
        try:
            text = client.sam(png, sam_parse.box_prompt(
                tb["x1"], tb["y1"], tb["x2"] - 1, tb["y2"] - 1, tb["w"],
                tb["h"]), label="spike-sam-box")
            r = sam_parse.parse(text)
            b = sam_parse.best(r)
            rec["box_prompt"] = {"records": len(r),
                                 "iou": iou(b["box"], tb) if b else 0.0,
                                 "raw": text[:300]}
        except mc.MetaError as e:
            rec["box_prompt"] = {"error": str(e)}
        try:
            rec["spark_box"] = spark_box_then_sam(client, png, s["target"],
                                                  tb)
        except Exception as e:  # noqa: BLE001
            rec["spark_box"] = {"error": str(e)}
        out.append(rec)
    return out


def spark_box(client, png, phrase, w, h, label="spark-box"):
    import base64
    body = {"input": [{"role": "user", "content": [
        {"type": "input_image", "image_url": "data:image/png;base64,"
         + base64.b64encode(png).decode()},
        {"type": "input_text", "text": (
            "The image is %d x %d pixels. Return the bounding box of the %s "
            "in pixel coordinates (x1,y1 top left, x2,y2 bottom right). "
            "Set found=false if it is not visible." % (w, h, phrase))}]}],
        "text": {"format": {"type": "json_schema", "name": "box",
                            "schema": BOX_SCHEMA, "strict": True}}}
    return mc.output_json(client.responses(body, label=label))


def spark_box_then_sam(client, png, phrase, tb):
    sb = spark_box(client, png, phrase, tb["w"], tb["h"])
    res = {"spark": sb, "spark_iou": iou(sb, tb) if sb.get("found") else 0.0}
    if sb.get("found"):
        text = client.sam(png, sam_parse.box_prompt(
            sb["x1"], sb["y1"], sb["x2"], sb["y2"], tb["w"], tb["h"]),
            label="spike-sam-sparkbox")
        b = sam_parse.best(sam_parse.parse(text))
        res["sam_iou"] = iou(b["box"], tb) if b else 0.0
    return res


def spike_sam_pdf(client):
    import pymupdf as fitz
    doc = fitz.open(str(REPORT))
    out = []
    for page_no, phrase in ((4, "bar chart"), (3, "table"), (6, "table")):
        pix = doc[page_no - 1].get_pixmap(dpi=100)
        png = pix.tobytes("png")
        try:
            text = client.sam(png, phrase, label="spike-sam-pdf")
            r = sam_parse.parse(text)
            b = sam_parse.best(r)
            out.append({"page": page_no, "phrase": phrase,
                        "records": len(r), "box": b["box"] if b else None,
                        "page_size": [pix.width, pix.height],
                        "raw": text[:300]})
        except mc.MetaError as e:
            out.append({"page": page_no, "phrase": phrase, "error": str(e)})
    return out


def main():
    client = mc.MetaClient()
    truth = json.loads((APP / "clip-truth.json").read_text())
    results = {"run_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "spend_before_usd": round(client.spent(), 4)}
    ok, models = mc.ping()
    results["models"] = models
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        for name, fn in (
                ("asr", lambda: spike_asr(client, truth, tmp)),
                ("sam_ui", lambda: spike_sam_ui(client, truth)),
                ("sam_pdf", lambda: spike_sam_pdf(client))):
            try:
                results[name] = fn()
            except Exception as e:  # noqa: BLE001
                results[name] = {"error": "%s: %s" % (type(e).__name__, e)}
            print(name, "done")
        asr = json.loads((FIX / "live_asr.json").read_text())
        transcript = "\n".join(
            "[%.1fs-%.1fs] %s" % (t["startMs"] / 1000, t["endMs"] / 1000,
                                  t["transcript"])
            for t in asr.get("turns") or [])
        try:
            results["video"] = spike_video(client, truth, transcript)
        except Exception as e:  # noqa: BLE001
            results["video"] = {"error": "%s: %s" % (type(e).__name__, e)}
        print("video done")
    results["mask_parser"] = {
        "meta_sam_parser_installed": sam_parse.parser_available()}
    results["spend_after_usd"] = round(client.spent(), 4)
    (REPO / "docs").mkdir(exist_ok=True)
    (REPO / "docs" / "spike-results.json").write_text(
        json.dumps(results, indent=1))
    print(json.dumps({k: (v if k in ("spend_before_usd", "spend_after_usd")
                          else "...") for k, v in results.items()}))


if __name__ == "__main__":
    main()
