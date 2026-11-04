"""Video to guide steps (A3), review and approval (A5).

Pipeline for one video (MP4, at most 10 minutes):
  1. FFmpeg extracts 16 kHz mono WAV.
  2. Muse Voice Transcribe returns turns {startMs, endMs, transcript};
     stored in `transcripts`.
  3. The MP4 is uploaded with the Files API (purpose=user_data).
  4. Muse Spark 1.3 gets the video, the timed transcript and a JSON
     schema, in background mode, and the job polls until it finishes.
  5. Steps are validated: times inside the video, ascending, t_end after
     t_start, each start snapped to the nearest transcript turn start
     within 1.5 s (spike decision), and `reason` kept only when its words
     were actually spoken (else null).
  6. SAM marks each step's frame (api/marks.py).
  7. A person reviews: edits text, shifts time, approves. Approved steps
     become chunks (instruction, reason, transcript excerpt, t_start), so
     answers read the approved text and never rewatch the video.

CLI:
  python api/video.py process <source_id>   run 1-6 (model results cached)
  python api/video.py seed                  load committed reviewed steps
"""

import json
import pathlib
import re
import subprocess
import sys
import tempfile
import threading
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import corpus  # noqa: E402
import db  # noqa: E402
import marks  # noqa: E402
import meta_client  # noqa: E402
import migrate  # noqa: E402

MAX_SECONDS = 600
SNAP_S = 1.5
DERIVED = "derived"

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

PROMPT = (
    "This screen recording shows how to do a task in a business app. "
    "Split it into the steps a new employee must perform, in order. For "
    "each step give t_start and t_end in seconds from the start of the "
    "video, a short imperative instruction, and target_phrase: a 1 to 4 "
    "word noun phrase naming the on-screen element the step acts on "
    "(null if none). Set reason to the narrator's own explanation of WHY "
    "the step is done, only if the narrator says it out loud; otherwise "
    "reason must be null. Never invent a reason. Skip intro and outro "
    "talk that has no action.\nTimed transcript:\n")


# ------------------------------------------------------------- helpers

def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def to_wav(video, wav):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video),
                    "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
                    str(wav)], check=True)


def parse_turns(payload):
    """[{start, end, text}] in seconds from a transcribe response."""
    turns = []
    for t in (payload or {}).get("turns") or []:
        text = (t.get("transcript") or t.get("text") or "").strip()
        if not text:
            continue
        turns.append({"start": round((t.get("startMs") or 0) / 1000.0, 2),
                      "end": round((t.get("endMs") or 0) / 1000.0, 2),
                      "text": text})
    return turns


def transcript_text(turns):
    return "\n".join("[%.1fs-%.1fs] %s" % (t["start"], t["end"], t["text"])
                     for t in turns)


def _words(s):
    return [w for w in re.findall(r"[a-z0-9$]+", (s or "").lower())
            if len(w) > 2]


def reason_spoken(reason, turns, t_start, t_end):
    """True when most of the reason's words were said near the step."""
    words = _words(reason)
    if not words:
        return False
    near = " ".join(t["text"] for t in turns
                    if t["end"] >= t_start - 2 and t["start"] <= t_end + 2)
    said = set(_words(near))
    return sum(w in said for w in words) / len(words) >= 0.6


def validate_steps(raw_steps, dur, turns):
    """Clean model steps; returns (steps, notes)."""
    notes = []
    starts = [t["start"] for t in turns]
    out = []
    for s in raw_steps:
        try:
            a, b = float(s["t_start"]), float(s["t_end"])
        except (KeyError, TypeError, ValueError):
            notes.append("dropped step without numeric times")
            continue
        if not (0 <= a < dur):
            notes.append("dropped step at %.1fs outside the video" % a)
            continue
        near = min(starts, key=lambda x: abs(x - a)) if starts else None
        if near is not None and abs(near - a) <= SNAP_S and abs(near - a) > 0:
            notes.append("step at %.1fs snapped to turn %.1fs" % (a, near))
            a = near
        b = min(max(b, a + 0.5), dur)
        if out and a <= out[-1]["t_start"]:
            notes.append("dropped step at %.1fs out of order" % a)
            continue
        reason = (s.get("reason") or "").strip() or None
        if reason and not reason_spoken(reason, turns, a, b):
            notes.append("reason removed at %.1fs (not spoken)" % a)
            reason = None
        instr = (s.get("instruction") or "").strip()
        if not instr:
            continue
        out.append({"t_start": round(a, 2), "t_end": round(b, 2),
                    "instruction": instr[:300], "reason": reason,
                    "target_phrase": (s.get("target_phrase") or None)})
    for i in range(len(out) - 1):
        if out[i]["t_end"] > out[i + 1]["t_start"]:
            out[i]["t_end"] = out[i + 1]["t_start"]
    for i, s in enumerate(out, start=1):
        s["n"] = i
    return out, notes


def excerpt(turns, a, b):
    return " ".join(t["text"] for t in turns
                    if t["end"] > a - 0.2 and t["start"] < b + 0.2)


# ---------------------------------------------------------------- jobs

def set_status(conn, source_id, status, **detail):
    conn.execute(
        "INSERT INTO video_jobs (source_id, status, detail, updated_at) "
        "VALUES (%s, %s, %s, now()) ON CONFLICT (source_id) DO UPDATE SET "
        "status = EXCLUDED.status, detail = video_jobs.detail || "
        "EXCLUDED.detail, updated_at = now()",
        (source_id, status, json.dumps(detail)))
    conn.commit()


def process(source_id, database_url=None, corpus_dir=corpus.DEFAULT_CORPUS,
            client=None, with_marks=True):
    """Run the model pipeline for one video and store steps (unapproved)."""
    import psycopg

    database_url = db.database_url(database_url)
    migrate.ensure_up_once(database_url)
    client = client or meta_client.MetaClient()
    e = corpus.entry(source_id, corpus_dir)
    if e is None or e.get("kind") != "video":
        raise ValueError("no video source %r" % source_id)
    video = corpus.source_path(e, corpus_dir)
    timing = {}
    with psycopg.connect(database_url) as conn:
        try:
            dur = duration(video)
            if dur > MAX_SECONDS:
                raise ValueError("video is longer than 10 minutes")
            set_status(conn, source_id, "transcribing", duration=dur)
            t0 = time.time()
            with tempfile.TemporaryDirectory() as tmp:
                wav = pathlib.Path(tmp) / "audio.wav"
                to_wav(video, wav)
                asr = client.transcribe(wav, label="asr " + source_id,
                                        audio_seconds=dur)
            turns = parse_turns(asr)
            timing["transcribe_s"] = round(time.time() - t0, 1)
            text = " ".join(t["text"] for t in turns)
            conn.execute(
                "INSERT INTO transcripts (source_id, turns, text) VALUES "
                "(%s, %s, %s) ON CONFLICT (source_id) DO UPDATE SET turns = "
                "EXCLUDED.turns, text = EXCLUDED.text, created_at = now()",
                (source_id, json.dumps(turns), text))
            set_status(conn, source_id, "uploading", turns=len(turns))
            t0 = time.time()
            up = client.upload_file(video, label="video " + source_id)
            timing["upload_s"] = round(time.time() - t0, 1)
            set_status(conn, source_id, "reading video")
            body = {"input": [{"role": "user", "content": [
                {"type": "input_video", "file_id": up["id"]},
                {"type": "input_text",
                 "text": PROMPT + transcript_text(turns)}]}],
                "text": {"format": {"type": "json_schema",
                                    "name": "guide_steps",
                                    "schema": STEP_SCHEMA, "strict": True}}}
            t0 = time.time()
            payload = client.responses_background(
                body, label="video steps " + source_id,
                on_poll=lambda st: set_status(conn, source_id,
                                              "reading video", model=st))
            timing["spark_s"] = round(time.time() - t0, 1)
            raw = meta_client.output_json(payload).get("steps") or []
            steps, notes = validate_steps(raw, dur, turns)
            if not steps:
                raise ValueError("model returned no usable steps")
            out_dir = pathlib.Path(corpus_dir) / DERIVED / source_id
            with conn.transaction():
                conn.execute("DELETE FROM guide_steps WHERE source_id = %s",
                             (source_id,))
                for s in steps:
                    conn.execute(
                        "INSERT INTO guide_steps (source_id, n, t_start, "
                        "t_end, instruction, reason, target_phrase, origin) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, 'spark')",
                        (source_id, s["n"], s["t_start"], s["t_end"],
                         s["instruction"], s["reason"], s["target_phrase"]))
            if with_marks:
                set_status(conn, source_id, "marking", steps=len(steps))
                t0 = time.time()
                for s in steps:
                    m = marks.mark_step(client, video, s, out_dir)
                    conn.execute(
                        "UPDATE guide_steps SET frame_path = %s, mask_path = "
                        "%s, box = %s, mark_status = %s WHERE source_id = %s "
                        "AND n = %s", (m["frame_path"], m["mask_path"],
                                       m["box"], m["mark_status"], source_id,
                                       s["n"]))
                    conn.commit()
                timing["marks_s"] = round(time.time() - t0, 1)
            set_status(conn, source_id, "ready for review",
                       steps=len(steps), notes=notes, timing=timing)
            return {"steps": steps, "notes": notes, "timing": timing}
        except Exception as ex:
            conn.rollback()
            set_status(conn, source_id, "failed",
                       error="%s: %s" % (type(ex).__name__, str(ex)[:300]))
            raise


def remark(source_id, database_url=None, corpus_dir=corpus.DEFAULT_CORPUS,
           client=None):
    """Re-run SAM marking for stored steps (keeps text and approval)."""
    import psycopg

    client = client or meta_client.MetaClient()
    e = corpus.entry(source_id, corpus_dir)
    video = corpus.source_path(e, corpus_dir)
    out_dir = pathlib.Path(corpus_dir) / DERIVED / source_id
    done = []
    with psycopg.connect(db.database_url(database_url)) as conn:
        for s in steps(source_id, database_url):
            m = marks.mark_step(client, video, s, out_dir)
            conn.execute(
                "UPDATE guide_steps SET frame_path = %s, mask_path = %s, "
                "box = %s, mark_status = %s WHERE source_id = %s AND n = %s",
                (m["frame_path"], m["mask_path"], m["box"], m["mark_status"],
                 source_id, s["n"]))
            conn.commit()
            done.append((s["n"], m["mark_status"]))
    return done


def process_async(source_id, database_url=None,
                  corpus_dir=corpus.DEFAULT_CORPUS):
    def _run():
        try:
            process(source_id, database_url, corpus_dir)
        except Exception as ex:  # noqa: BLE001 (status row holds the error)
            print("video %s failed: %s" % (source_id, ex), file=sys.stderr)
    th = threading.Thread(target=_run, daemon=True)
    th.start()
    return th


def status(source_id, database_url=None):
    import psycopg
    with psycopg.connect(db.database_url(database_url)) as conn:
        row = conn.execute("SELECT status, detail, updated_at FROM video_jobs "
                           "WHERE source_id = %s", (source_id,)).fetchone()
    if row is None:
        return None
    return {"source_id": source_id, "status": row[0], "detail": row[1],
            "updated_at": row[2].isoformat()}


STEP_COLS = ("n, t_start, t_end, instruction, reason, target_phrase, box, "
             "mask_path, frame_path, mark_status, approved, origin")


def steps(source_id, database_url=None):
    import psycopg
    with psycopg.connect(db.database_url(database_url)) as conn:
        rows = conn.execute("SELECT %s FROM guide_steps WHERE source_id = %%s "
                            "ORDER BY n" % STEP_COLS, (source_id,)).fetchall()
        tr = conn.execute("SELECT turns FROM transcripts WHERE source_id = %s",
                          (source_id,)).fetchone()
    names = [c.strip() for c in STEP_COLS.split(",")]
    out = []
    turns = tr[0] if tr else []
    for r in rows:
        d = dict(zip(names, r))
        if isinstance(d["box"], str):
            d["box"] = json.loads(d["box"])
        d["transcript"] = excerpt(turns, d["t_start"], d["t_end"])
        out.append(d)
    return out


# -------------------------------------------------------------- review

def edit_step(source_id, n, instruction=None, reason=None, shift_s=None,
              clear_reason=False, database_url=None):
    """Reviewer edit. Editing an approved step un-approves it."""
    import psycopg
    with psycopg.connect(db.database_url(database_url)) as conn:
        row = conn.execute("SELECT t_start, t_end FROM guide_steps WHERE "
                           "source_id = %s AND n = %s",
                           (source_id, n)).fetchone()
        if row is None:
            return None
        a, b = row
        if shift_s:
            shift = max(-10.0, min(10.0, float(shift_s)))
            a, b = max(0.0, a + shift), max(0.0, b + shift)
        conn.execute(
            "UPDATE guide_steps SET t_start = %s, t_end = %s, "
            "instruction = COALESCE(%s, instruction), reason = CASE WHEN %s "
            "THEN NULL ELSE COALESCE(%s, reason) END, approved = false, "
            "origin = CASE WHEN origin LIKE '%%edited%%' THEN origin ELSE "
            "origin || '+edited' END WHERE source_id = %s AND n = %s",
            (round(a, 2), round(b, 2), instruction, clear_reason, reason,
             source_id, n))
        conn.commit()
    return True


def step_chunk_text(s, title):
    parts = ["%s, step %d: %s" % (title, s["n"], s["instruction"])]
    if s["reason"]:
        parts.append("Why: %s" % s["reason"])
    if s.get("transcript"):
        parts.append("Narration: %s" % s["transcript"])
    return "\n".join(parts)


def approve(source_id, ns=None, database_url=None,
            corpus_dir=corpus.DEFAULT_CORPUS, detect_conflicts=True):
    """Approve steps (all when ns is None) and rebuild the video's chunks."""
    import psycopg

    database_url = db.database_url(database_url)
    e = corpus.entry(source_id, corpus_dir)
    with psycopg.connect(database_url) as conn:
        if ns is None:
            conn.execute("UPDATE guide_steps SET approved = true WHERE "
                         "source_id = %s", (source_id,))
        else:
            conn.execute("UPDATE guide_steps SET approved = true WHERE "
                         "source_id = %s AND n = ANY(%s)",
                         (source_id, list(ns)))
        conn.commit()
    approved = [s for s in steps(source_id, database_url) if s["approved"]]
    with psycopg.connect(database_url) as conn:
        with conn.transaction():
            conn.execute("DELETE FROM chunks WHERE source_id = %s",
                         (source_id,))
            for i, s in enumerate(approved):
                conn.execute(
                    "INSERT INTO chunks (source_id, license_class, "
                    "chunk_index, text, t_start, text_origin) VALUES "
                    "(%s, %s, %s, %s, %s, 'video-step')",
                    (source_id, e["license_class"], i,
                     step_chunk_text(s, e.get("title", source_id)),
                     s["t_start"]))
    found = None
    if detect_conflicts:
        import conflict
        try:
            found = conflict.detect([source_id], database_url, corpus_dir)
        except Exception as ex:  # noqa: BLE001
            found = {"error": str(ex)[:200]}
    return {"approved": len(approved), "conflicts": found}


# ---------------------------------------------------------------- seed

def export_reviewed(source_id, path, database_url=None):
    data = steps(source_id, database_url)
    for d in data:
        d.pop("transcript", None)
    import psycopg
    with psycopg.connect(db.database_url(database_url)) as conn:
        tr = conn.execute("SELECT turns, text FROM transcripts WHERE "
                          "source_id = %s", (source_id,)).fetchone()
    pathlib.Path(path).write_text(json.dumps(
        {"source_id": source_id, "turns": tr[0], "text": tr[1],
         "steps": data}, indent=1))


def seed(database_url=None, corpus_dir=corpus.DEFAULT_CORPUS):
    """Load reviewed steps committed next to each video (no model calls)."""
    import psycopg

    database_url = db.database_url(database_url)
    migrate.ensure_up_once(database_url)
    loaded = {}
    for e in corpus.load_manifest(corpus_dir)["entries"]:
        if e.get("kind") != "video":
            continue
        f = corpus.source_path(e, corpus_dir).with_suffix(".steps.json")
        if not f.exists():
            continue
        data = json.loads(f.read_text())
        with psycopg.connect(database_url) as conn:
            with conn.transaction():
                conn.execute(
                    "INSERT INTO transcripts (source_id, turns, text) VALUES "
                    "(%s, %s, %s) ON CONFLICT (source_id) DO UPDATE SET "
                    "turns = EXCLUDED.turns, text = EXCLUDED.text",
                    (e["id"], json.dumps(data["turns"]), data["text"]))
                conn.execute("DELETE FROM guide_steps WHERE source_id = %s",
                             (e["id"],))
                for s in data["steps"]:
                    conn.execute(
                        "INSERT INTO guide_steps (source_id, n, t_start, "
                        "t_end, instruction, reason, target_phrase, box, "
                        "mask_path, frame_path, mark_status, approved, "
                        "origin) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, "
                        "%s, %s, %s, %s)",
                        (e["id"], s["n"], s["t_start"], s["t_end"],
                         s["instruction"], s["reason"], s["target_phrase"],
                         json.dumps(s["box"]) if s["box"] else None,
                         s["mask_path"], s["frame_path"], s["mark_status"],
                         s["approved"], s["origin"]))
                conn.execute(
                    "INSERT INTO video_jobs (source_id, status, detail) "
                    "VALUES (%s, 'reviewed (seeded)', '{}') ON CONFLICT "
                    "(source_id) DO UPDATE SET status = EXCLUDED.status",
                    (e["id"],))
        loaded[e["id"]] = approve(e["id"], None, database_url, corpus_dir,
                                  detect_conflicts=False)["approved"]
        print("%s: %d approved steps loaded" % (e["id"], loaded[e["id"]]))
    return loaded


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Kohu video guides")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("process")
    p.add_argument("source_id")
    p.add_argument("--no-marks", action="store_true")
    sub.add_parser("seed")
    p = sub.add_parser("export")
    p.add_argument("source_id")
    p = sub.add_parser("remark")
    p.add_argument("source_id")
    p = sub.add_parser("approve")
    p.add_argument("source_id")
    args = ap.parse_args(argv)
    if args.cmd == "process":
        out = process(args.source_id, with_marks=not args.no_marks)
        print(json.dumps({"notes": out["notes"], "timing": out["timing"],
                          "steps": len(out["steps"])}, indent=1))
    elif args.cmd == "seed":
        seed()
    elif args.cmd == "remark":
        print(remark(args.source_id))
    elif args.cmd == "approve":
        print(approve(args.source_id))
    elif args.cmd == "export":
        e = corpus.entry(args.source_id)
        export_reviewed(args.source_id, corpus.source_path(e).with_suffix(
            ".steps.json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
