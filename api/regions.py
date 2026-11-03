"""SAM 3.1 on PDF charts and tables (A7).

For each chart or table page listed in the manifest (citation_anchors
"charts" and "tables"), the page is rendered, SAM 3.1 marks the region
with a noun phrase ("bar chart" or "table"), the region is cropped, and
Muse Spark reads the crop. The citation panel shows the page with the
SAM mark and the reading. All model results are cached.

  python api/regions.py        # mark every listed page (seed runs this)
"""

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import corpus  # noqa: E402
import db  # noqa: E402
import meta_client  # noqa: E402
import migrate  # noqa: E402
import sam_parse  # noqa: E402

DPI = 100
MAX_REGIONS = 2
READ_PROMPT = (
    "This image is a cropped %s from a report page. Transcribe it as plain "
    "text: for a chart give its title and one 'label: value' line per bar "
    "using only printed values; for a table give one line per row with "
    "cells separated by | . No commentary.")


def targets(corpus_dir=corpus.DEFAULT_CORPUS):
    out = []
    for e in corpus.load_manifest(corpus_dir)["entries"]:
        a = e.get("citation_anchors") or {}
        for kind, phrase in (("charts", "bar chart"), ("tables", "table")):
            for ptr in a.get(kind, []):
                out.append((e, int(ptr.split(".")[1]), phrase))
    return out


def mark_page(e, page, phrase, client, out_dir):
    import base64
    import io

    import pymupdf
    from PIL import Image

    doc = pymupdf.open(str(corpus.source_path(e, corpus.DEFAULT_CORPUS)))
    png = doc[page - 1].get_pixmap(dpi=DPI).tobytes("png")
    page_png = "page-%02d.png" % page
    (out_dir / page_png).write_bytes(png)
    recs = sam_parse.parse(client.sam(png, phrase, label="region %s p.%d"
                                      % (e["id"], page)))
    recs = sorted(recs, key=lambda r: (r["box"]["y1"], r["box"]["x1"]))
    rows = []
    for k, rec in enumerate(recs[:MAX_REGIONS], start=1):
        mask_png = "page-%02d-mask-%d.png" % (page, k)
        drawn = sam_parse.render_mark_png(rec, out_dir / mask_png)
        b = rec["box"]
        img = Image.open(io.BytesIO(png))
        # SAM's box hugs the plot; axis labels and titles sit just outside
        # it, so the crop Spark reads is padded.
        px, py = int((b["x2"] - b["x1"]) * 0.08), int((b["y2"] - b["y1"]) * 0.25)
        crop = img.crop((max(0, b["x1"] - px), max(0, b["y1"] - py),
                         min(img.width, b["x2"] + px),
                         min(img.height, b["y2"] + py)))
        buf = io.BytesIO()
        crop.save(buf, "PNG")
        body = {"input": [{"role": "user", "content": [
            {"type": "input_image", "image_url": "data:image/png;base64,"
             + base64.b64encode(buf.getvalue()).decode()},
            {"type": "input_text", "text": READ_PROMPT % phrase}]}],
            "store": False}
        reading = None
        try:
            reading = meta_client.output_text(client.responses(
                body, label="region read")).strip()
        except meta_client.MetaError as ex:
            reading = None
            print("warning: region read failed: %s" % ex)
        rows.append({"k": k, "box": dict(b, w=rec["w"], h=rec["h"],
                                         drawn=drawn),
                     "page_png": page_png, "mask_png": mask_png,
                     "reading": reading, "status": "phrase"})
    if not rows:
        rows.append({"k": 1, "box": None, "page_png": page_png,
                     "mask_png": None, "reading": None,
                     "status": "no match"})
    return rows


def run(database_url=None, corpus_dir=corpus.DEFAULT_CORPUS, client=None):
    import psycopg

    database_url = db.database_url(database_url)
    migrate.ensure_up_once(database_url)
    client = client or meta_client.MetaClient()
    done = []
    for e, page, phrase in targets(corpus_dir):
        out_dir = pathlib.Path(corpus_dir) / "derived" / e["id"]
        out_dir.mkdir(parents=True, exist_ok=True)
        try:
            rows = mark_page(e, page, phrase, client, out_dir)
        except meta_client.MetaError as ex:
            print("skip %s p.%d: %s" % (e["id"], page, ex))
            continue
        with psycopg.connect(database_url) as conn:
            conn.execute("DELETE FROM page_regions WHERE source_id = %s AND "
                         "page = %s", (e["id"], page))
            for r in rows:
                conn.execute(
                    "INSERT INTO page_regions (source_id, page, k, phrase, "
                    "box, page_png, mask_png, reading, status) VALUES (%s, "
                    "%s, %s, %s, %s, %s, %s, %s, %s)",
                    (e["id"], page, r["k"], phrase, json.dumps(r["box"]),
                     r["page_png"], r["mask_png"], r["reading"], r["status"]))
            conn.commit()
        done.append((e["id"], page, phrase, len([r for r in rows
                                                 if r["box"]])))
        print("%s p.%d %r: %d region(s)" % done[-1])
    return done


def regions(source_id, page, database_url=None):
    import psycopg
    with psycopg.connect(db.database_url(database_url)) as conn:
        rows = conn.execute(
            "SELECT k, phrase, box, page_png, mask_png, reading, status FROM "
            "page_regions WHERE source_id = %s AND page = %s ORDER BY k",
            (source_id, page)).fetchall()
    return [{"k": r[0], "phrase": r[1], "box": r[2], "page_png": r[3],
             "mask_png": r[4], "reading": r[5], "status": r[6],
             "reading_excerpt": (r[5] or "")[:400]} for r in rows
            if r[2]]


if __name__ == "__main__":
    run()
