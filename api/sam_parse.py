"""SAM 3.1 output parsing and mark rendering.

SAM 3.1 returns one output_text line per frame:

  <Nf>id<|box;x1=..;y1=..;x2=..;y2=..;w=W;h=H[;c=..]|><|mask;x=0;y=0;data=H,W,~payload|>,id<|box..|><|mask..|>

Boxes are parsed here with a small regex (inclusive x2/y2 become
half-open right/bottom, as the protocol states). Mask payloads are base85
with a codec Meta ships in the `meta-sam-parser` package; when that
package is installed, masks are decoded with its `decode_mask_to_raster`.
Without it, the record keeps its box and `mask` is None, and callers fall
back to drawing the box.

Box prompts are built in the documented token format:
  <0f>1<|box;x1=..;y1=..;x2=..;y2=..;w=..;h=..|>
"""

import re

RECORD_RE = re.compile(
    r"(?P<id>\d+)<\|box;(?P<box>[^|]*)\|><\|mask;(?P<mask>[^|]*)\|>")
FRAME_RE = re.compile(r"^<(?P<frame>\d+)f>")

try:  # Meta's official parser (SAM License), optional dependency.
    import meta_sam_parser as _msp  # type: ignore
except Exception:  # pragma: no cover - depends on the environment
    _msp = None


def parser_available():
    return _msp is not None


def _fields(text):
    out = {}
    for part in text.split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def parse(output_text):
    """[{frame, object_id, box:{x1,y1,x2,y2}, w, h, confidence, mask}]."""
    records = []
    for line in (output_text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        m = FRAME_RE.match(line)
        frame = int(m.group("frame")) if m else 0
        body = line[m.end():] if m else line
        for rec in RECORD_RE.finditer(body):
            box = _fields(rec.group("box"))
            mask = _fields(rec.group("mask"))
            try:
                x1, y1 = int(box["x1"]), int(box["y1"])
                x2, y2 = int(box["x2"]) + 1, int(box["y2"]) + 1
                w, h = int(box["w"]), int(box["h"])
            except (KeyError, ValueError):
                continue
            conf = box.get("c")
            records.append({
                "frame": frame, "object_id": rec.group("id"),
                "box": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
                "w": w, "h": h,
                "confidence": float(conf) if conf else None,
                "mask_data": mask.get("data"),
                "mask": None})
    if _msp is not None:
        _decode_masks(records)
    return records


def _decode_masks(records):
    """Decode mask rasters with meta_sam_parser when present."""
    for r in records:
        data = r.get("mask_data")
        if not data:
            continue
        try:
            h, w, payload = data.split(",", 2)
            h, w = int(h), int(w)
            enc = "lossless" if payload.startswith("~") else "one_bit"
            # Payload keeps its marker; the package checks it.
            raster = _msp.decode_mask_to_raster(  # type: ignore[union-attr]
                _msp.SegmentationMask(encoding=enc, payload=payload,
                                      width=w, height=h))
            r["mask"] = {"h": h, "w": w,
                         "rows": [list(raster[i * w:(i + 1) * w])
                                  for i in range(h)]}
        except Exception:
            r["mask"] = None


def best(records):
    """Highest-confidence record, else the largest box, else None."""
    if not records:
        return None

    def area(r):
        b = r["box"]
        return (b["x2"] - b["x1"]) * (b["y2"] - b["y1"])
    return max(records, key=lambda r: ((r["confidence"] or 0), area(r)))


def box_prompt(x1, y1, x2, y2, w, h, object_id=1, frame=0):
    """Documented SAM box prompt text (inclusive corners, media pixels)."""
    clamp = lambda v, hi: max(0, min(int(v), hi - 1))  # noqa: E731
    return "<%df>%d<|box;x1=%d;y1=%d;x2=%d;y2=%d;w=%d;h=%d|>" % (
        frame, object_id, clamp(x1, w), clamp(y1, h), clamp(x2, w),
        clamp(y2, h), w, h)


def render_mark_png(record, out_path, color=(255, 196, 0)):
    """Transparent full-frame PNG with the mask (or box) filled.

    Returns "mask" when a decoded mask was drawn, "box" otherwise.
    """
    from PIL import Image, ImageDraw

    w, h = record["w"], record["h"]
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    b = record["box"]
    kind = "box"
    mask = record.get("mask")
    if mask and mask.get("rows"):
        mh, mw = mask["h"], mask["w"]
        small = Image.new("L", (mw, mh), 0)
        small.putdata([255 if v else 0 for row in mask["rows"] for v in row])
        bw, bh = max(1, b["x2"] - b["x1"]), max(1, b["y2"] - b["y1"])
        alpha = small.resize((bw, bh), Image.NEAREST).point(
            lambda v: 120 if v else 0)
        fill = Image.new("RGBA", (bw, bh), color + (0,))
        fill.putalpha(alpha)
        img.paste(fill, (b["x1"], b["y1"]), fill)
        kind = "mask"
    else:
        ImageDraw.Draw(img).rectangle(
            [b["x1"], b["y1"], b["x2"] - 1, b["y2"] - 1],
            fill=color + (90,))
    ImageDraw.Draw(img).rectangle(
        [b["x1"], b["y1"], b["x2"] - 1, b["y2"] - 1],
        outline=color + (255,), width=3)
    img.save(out_path)
    return kind


def mask_fraction(record):
    """Share of the box covered by the decoded mask, or None."""
    mask = record.get("mask")
    if not mask or not mask.get("rows"):
        return None
    cells = [v for row in mask["rows"] for v in row]
    return sum(1 for v in cells if v) / max(1, len(cells))
