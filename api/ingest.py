"""Kohu ingest: parse corpus files into cited chunks.

Chunking (matches corpus/manifest.json "chunking"):
  PDF    one chunk per page (pointer p.N)
  deck   one chunk per slide (pointer slide N)
  sheet  row windows of the data sheet (pointer Sheet!A2:J11). Each row
         line starts with its row number and the header line names the
         column letters, so a single cell (Data!I11) can be cited.
  video  chunks come from approved guide steps (api/video.py), not here.

PDF pages that have no text layer, or whose text is a caption over a
large image (a chart), are read by Muse Spark when a page reader is
available (api/vision.py, cached in corpus/spark-cache). Without it a
scanned page falls back to its build-time text sidecar, and the chunk
records that origin. Every chunk stores where its text came from in
chunks.text_origin: text-layer, spark-vision, sidecar-fallback.

Re-runs are idempotent: a source's chunks are replaced in one transaction.

Usage:
  python api/ingest.py [--database-url URL] [--corpus DIR] [--no-spark]
"""

import argparse
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import corpus as corpus_mod  # noqa: E402
import db  # noqa: E402
import migrate  # noqa: E402

DEFAULT_CORPUS = corpus_mod.DEFAULT_CORPUS
VISION_MIN_CHARS = 200        # below this, a page has no useful text layer
VISION_IMAGE_SHARE = 0.25     # an image covering this much is a chart page


# ---------------------------------------------------------------- parsers

def parse_pdf_pages(path):
    """[(page_no, text, needs_vision, png_bytes|None)] with PyMuPDF."""
    import pymupdf

    doc = pymupdf.open(str(path))
    out = []
    for i, page in enumerate(doc, start=1):
        text = page.get_text().strip()
        area = page.rect.width * page.rect.height
        img_area = 0.0
        for info in page.get_image_info():
            x0, y0, x1, y1 = info["bbox"]
            img_area += max(0, x1 - x0) * max(0, y1 - y0)
        needs = (len(text) < VISION_MIN_CHARS
                 or img_area / area >= VISION_IMAGE_SHARE)
        png = page.get_pixmap(dpi=110).tobytes("png") if needs else None
        out.append((i, text, needs, png))
    return out


def slide_text(slide):
    parts = []
    for shape in slide.shapes:
        if shape.has_text_frame:
            t = shape.text_frame.text.strip()
            if t:
                parts.append(t)
        elif getattr(shape, "has_table", False) and shape.has_table:
            for row in shape.table.rows:
                cells = [c.text.strip() for c in row.cells]
                if any(cells):
                    parts.append(" | ".join(cells))
    return "\n".join(parts).strip()


def parse_deck(path):
    from pptx import Presentation
    prs = Presentation(str(path))
    return [(i, slide_text(s)) for i, s in enumerate(prs.slides, start=1)]


def col_letter(n):
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def fmt_cell(v):
    if v is None:
        return ""
    if isinstance(v, float):
        if abs(v) >= 1e6:
            return "%d" % round(v)
        return ("%.4f" % v).rstrip("0").rstrip(".")
    return str(v)


def parse_sheet_windows(path, sheet_name, rows_per_chunk, last_col, last_row):
    """[(cell_range, text)] windows over data rows 2..last_row."""
    from openpyxl import load_workbook
    wb = load_workbook(str(path), read_only=True, data_only=True)
    ws = wb[sheet_name]
    header = next(ws.iter_rows(min_row=1, max_row=1, values_only=True))
    head = "Sheet %s columns: %s" % (sheet_name, " | ".join(
        "%s=%s" % (col_letter(i + 1), h) for i, h in enumerate(header)
        if h is not None))
    chunks = []
    row = 2
    while row <= last_row:
        end = min(row + rows_per_chunk - 1, last_row)
        lines = [head]
        for r_no, r in enumerate(ws.iter_rows(min_row=row, max_row=end,
                                              values_only=True), start=row):
            if any(v is not None and str(v).strip() for v in r):
                lines.append("row %d: %s" % (r_no, " | ".join(
                    fmt_cell(v) for v in r)))
        chunks.append(("%s!A%d:%s%d" % (sheet_name, row, last_col, end),
                       "\n".join(lines)))
        row = end + 1
    wb.close()
    return chunks


def parse_range(cell_range):
    m = re.fullmatch(r"([A-Z]+)1:([A-Z]+)(\d+)", cell_range)
    if not m:
        raise ValueError("unsupported sheet range: %r" % cell_range)
    return m.group(2), int(m.group(3))


# ---------------------------------------------------------------- ingest

def _page_rows(entry, path, reader, log):
    rows = []
    anchors = entry["citation_anchors"]
    sidecar_pages = None
    if anchors.get("sidecar"):
        sc = path.parent.parent / anchors["sidecar"]
        if sc.exists():
            sidecar_pages = sc.read_text(encoding="utf-8").split("\f")
    for page_no, text, needs, png in parse_pdf_pages(path):
        origin = "text-layer"
        if needs and reader is not None:
            read = reader.read_page(entry["id"], page_no, png, text)
            if read:
                text = (text + "\n" if text else "") + read
                origin = "spark-vision"
        if not text.strip() and sidecar_pages:
            text = sidecar_pages[page_no - 1].strip()
            origin = "sidecar-fallback"
        if not text.strip():
            raise RuntimeError("%s p.%d has no text, no Spark reading and "
                               "no sidecar" % (entry["id"], page_no))
        log.append((entry["id"], "p.%d" % page_no, origin))
        rows.append((page_no - 1, text, page_no, None, None, origin))
    return rows


def ingest(corpus_dir, database_url, no_spark=False, only=None):
    corpus_dir = pathlib.Path(corpus_dir)
    manifest = corpus_mod.load_manifest(corpus_dir)
    windows = manifest["chunking"]["sheet_windows"]
    reader = None
    if not no_spark:
        try:
            import vision
            reader = vision.PageReader()
            if not reader.enabled:
                reader = None
        except ImportError:
            reader = None
    print("Spark page reading: %s" % ("on" if reader else "off"))
    migrate.cmd_up(database_url)

    import psycopg
    counts, origins = {}, []
    with psycopg.connect(database_url) as conn:
        for entry in manifest["entries"]:
            sid = entry["id"]
            if only and sid not in only:
                continue
            anchor = entry["citation_anchors"]["type"]
            if anchor == "timestamp":
                continue  # video chunks come from approved guide steps
            path = corpus_mod.source_path(entry, corpus_dir)
            rows = []  # (chunk_index, text, page, cell_range, slide, origin)
            if anchor == "page":
                rows = _page_rows(entry, path, reader, origins)
            elif anchor == "slide":
                rows = [(n - 1, text, None, None, n, "text-layer")
                        for n, text in parse_deck(path) if text]
            elif anchor == "cell-range":
                cfg = windows[sid]
                last_col, last_row = parse_range(
                    entry["citation_anchors"]["range"])
                rows = [(i, text, None, rng, None, "text-layer")
                        for i, (rng, text) in enumerate(parse_sheet_windows(
                            path, cfg["sheet"], cfg["rows_per_chunk"],
                            last_col, last_row))]
            else:
                raise ValueError("unknown anchor type %r" % anchor)
            with conn.transaction():
                conn.execute("DELETE FROM chunks WHERE source_id = %s",
                             (sid,))
                with conn.cursor() as cur:
                    cur.executemany(
                        "INSERT INTO chunks (source_id, license_class, "
                        "chunk_index, text, page, cell_range, slide, "
                        "text_origin) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                        [(sid, entry["license_class"], idx, text, page, cr,
                          slide, origin)
                         for idx, text, page, cr, slide, origin in rows])
            counts[sid] = len(rows)
            exp = entry.get("expected_chunks")
            flag = "" if exp is None or exp == len(rows) else \
                "  MISMATCH (manifest expects %d)" % exp
            print("%s: %d chunks%s" % (sid, len(rows), flag))
    for sid, ptr, origin in origins:
        if origin != "text-layer":
            print("  text origin %s %s: %s" % (sid, ptr, origin))
    print("total: %d chunks from %d sources"
          % (sum(counts.values()), len(counts)))
    return counts


def main(argv=None):
    parser = argparse.ArgumentParser(description="Kohu corpus ingest")
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--corpus", default=str(DEFAULT_CORPUS))
    parser.add_argument("--no-spark", action="store_true",
                        help="never call Spark; use text layers and sidecars")
    parser.add_argument("--only", nargs="*", help="source ids to re-ingest")
    args = parser.parse_args(argv)
    ingest(pathlib.Path(args.corpus), db.database_url(args.database_url),
           args.no_spark, args.only)
    return 0


if __name__ == "__main__":
    sys.exit(main())
