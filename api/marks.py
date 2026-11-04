"""SAM marking for guide steps and document regions (A4, A7).

For each guide step a frame is cut from the video with FFmpeg, then:
  1. Muse Spark proposes a box for the target, given the step's
     instruction for context (JSON schema).
  2. SAM 3.1 with the step's target phrase (noun phrase prompt). Kept
     when the match is no bigger than MAX_SHARE of the frame and agrees
     with Spark's box (IoU >= AGREE_IOU). In the first live run, three of
     nine phrase or unguided marks landed on the wrong element, which
     is why the phrase result is checked against Spark's box.
  3. Otherwise SAM 3.1 refines Spark's box with a box prompt.
  4. If SAM returns nothing for that box, Spark's box itself is drawn.

mark_status records which path produced the mark:
  phrase     SAM matched the noun phrase
  box        SAM matched a box prompt (box proposed by Spark)
  spark_box  SAM found nothing; Spark's box is shown
  failed     no mark; the step still works without one

The mark is saved as a transparent PNG the size of the frame. It is the
decoded SAM mask when meta-sam-parser is installed, otherwise the SAM
box. A SAM or Spark failure never fails the guide.
"""

import base64
import json
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import meta_client  # noqa: E402
import sam_parse  # noqa: E402

MAX_SHARE = 0.25
AGREE_IOU = 0.5
FRAME_OFFSET_S = 0.8

BOX_SCHEMA = {
    "type": "object",
    "properties": {"x1": {"type": "integer"}, "y1": {"type": "integer"},
                   "x2": {"type": "integer"}, "y2": {"type": "integer"},
                   "found": {"type": "boolean"}},
    "required": ["x1", "y1", "x2", "y2", "found"],
    "additionalProperties": False}


def cut_frame(video, t, out_png):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "%.2f" % t,
                    "-i", str(video), "-frames:v", "1", str(out_png)],
                   check=True)
    from PIL import Image
    with Image.open(out_png) as im:
        return im.size


def iou(a, b):
    ix = max(0, min(a["x2"], b["x2"]) - max(a["x1"], b["x1"]))
    iy = max(0, min(a["y2"], b["y2"]) - max(a["y1"], b["y1"]))
    inter = ix * iy
    union = ((a["x2"] - a["x1"]) * (a["y2"] - a["y1"])
             + (b["x2"] - b["x1"]) * (b["y2"] - b["y1"]) - inter)
    return inter / union if union else 0.0


def spark_box(client, png, phrase, w, h, context=None):
    hint = (" The user is about to do this step: %s. Box the single control "
            "they act on (the button, field, menu item, row or dropdown "
            "itself), not its label or the whole panel." % context
            if context else "")
    body = {"input": [{"role": "user", "content": [
        {"type": "input_image", "image_url": "data:image/png;base64,"
         + base64.b64encode(png).decode()},
        {"type": "input_text", "text": (
            "The image is %d x %d pixels. Return the bounding box of the %s "
            "in pixel coordinates (x1,y1 top left, x2,y2 bottom right).%s "
            "Set found=false if it is not visible." % (w, h, phrase, hint))}]}],
        "text": {"format": {"type": "json_schema", "name": "box",
                            "schema": BOX_SCHEMA, "strict": True}},
        "store": False}
    out = meta_client.output_json(client.responses(body, label="spark-box"))
    if not out.get("found"):
        return None
    x1, x2 = sorted((max(0, out["x1"]), min(w - 1, out["x2"])))
    y1, y2 = sorted((max(0, out["y1"]), min(h - 1, out["y2"])))
    if x2 - x1 < 2 or y2 - y1 < 2:
        return None
    return {"x1": x1, "y1": y1, "x2": x2 + 1, "y2": y2 + 1}


def _share(box, w, h):
    return ((box["x2"] - box["x1"]) * (box["y2"] - box["y1"])) / float(w * h)


def mark_image(client, png, phrase, w, h, out_mask, context=None,
               allow_phrase=True):
    """Mark `phrase` in an image. Returns (status, box_info or None)."""
    detail = {}
    try:
        sb = spark_box(client, png, phrase or "main element", w, h, context)
        if allow_phrase and phrase:
            rec = sam_parse.best(sam_parse.parse(
                client.sam(png, phrase, label="mark-phrase")))
            if (rec and _share(rec["box"], w, h) <= MAX_SHARE
                    and (sb is None or iou(rec["box"], sb) >= AGREE_IOU)):
                drawn = sam_parse.render_mark_png(rec, out_mask)
                return "phrase", dict(rec["box"], w=w, h=h, drawn=drawn,
                                      confidence=rec["confidence"],
                                      spark_box=sb)
            detail["phrase_result"] = ("no match" if not rec else
                                       "disagrees with Spark box")
        if sb is None:
            return "failed", {"reason": "spark found no box", **detail}
        rec = sam_parse.best(sam_parse.parse(client.sam(
            png, sam_parse.box_prompt(sb["x1"], sb["y1"], sb["x2"] - 1,
                                      sb["y2"] - 1, w, h),
            label="mark-box")))
        if rec:
            drawn = sam_parse.render_mark_png(rec, out_mask)
            return "box", dict(rec["box"], w=w, h=h, drawn=drawn,
                               spark_box=sb, **detail)
        fake = {"box": sb, "w": w, "h": h, "mask": None}
        sam_parse.render_mark_png(fake, out_mask)
        return "spark_box", dict(sb, w=w, h=h, drawn="box", **detail)
    except (meta_client.MetaError, ValueError, KeyError) as e:
        return "failed", {"reason": "%s: %s" % (type(e).__name__,
                                                str(e)[:120]), **detail}


def mark_step(client, video, step, out_dir):
    """Frame + mark for one guide step dict (n, t_start, t_end, target_phrase).

    Returns a dict of columns to store: frame_path, mask_path, box,
    mark_status. Paths are file names inside out_dir.
    """
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    n = step["n"]
    t = min(step["t_start"] + FRAME_OFFSET_S,
            max(step["t_start"], step["t_end"] - 0.1))
    frame = out_dir / ("step-%02d-frame.png" % n)
    mask = out_dir / ("step-%02d-mask.png" % n)
    try:
        w, h = cut_frame(video, t, frame)
    except (subprocess.CalledProcessError, OSError):
        return {"frame_path": None, "mask_path": None, "box": None,
                "mark_status": "failed"}
    if not step.get("target_phrase"):
        return {"frame_path": frame.name, "mask_path": None,
                "box": json.dumps({"reason": "no target phrase"}),
                "mark_status": "failed"}
    status, info = mark_image(client, frame.read_bytes(),
                              step["target_phrase"], w, h, mask,
                              context=step.get("instruction"))
    return {"frame_path": frame.name,
            "mask_path": mask.name if status != "failed" else None,
            "box": json.dumps(dict(info or {}, frame_t=round(t, 2))),
            "mark_status": status}
