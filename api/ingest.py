"""Kohu ingest (P21): parse the 8 corpus files, write chunks with pointers.

Chunking rule (matches corpus/manifest.json "chunking"):
  PDF   -> one chunk per page (pointer: page)
  deck  -> one chunk per slide (pointer: slide)
  sheet -> row windows of the data sheet (pointer: cell_range "Sheet!A2:F21")
  OCR   -> a PDF page with no text layer falls back to {stem}-ocr.txt

Each chunk carries source_id + license_class from the manifest. Re-runs are
idempotent: chunks for a source are deleted before its fresh chunks insert.

Muse Spark path: when META_API_KEY, META_API_BASE, and META_PARSE_MODEL are
all set, chart-bearing slide chunks get a model-generated caption appended.
META_API_BASE must be the full HTTPS completions endpoint URL (it is
deployment-specific, so there is no default); the API is Responses-style,
{"model", "input"}. Without all three, ingest runs
fully local and logs that Spark enrichment is off; chunk counts are identical
either way. Embeddings are left NULL (column is nullable by design) until the
embedding pass lands.

Usage:
  python api/ingest.py [--database-url URL] [--corpus DIR] [--no-spark]
"""

import argparse
import json
import os
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import meta_client  # noqa: E402
import migrate  # noqa: E402  (same-dir runner; ensures schema before write)

REPO = HERE.parent
DEFAULT_CORPUS = REPO / "corpus"
DEFAULT_DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://postgres@localhost:5432/kohu")


def load_manifest(corpus_dir):
    with open(corpus_dir / "manifest.json", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------- parsers

def parse_pdf_pages(path):
    """[(page_no, text)] with pypdf; empty-string text means image-only."""
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    out = []
    for i, page in enumerate(reader.pages, start=1):
        out.append((i, (page.extract_text() or "").strip()))
    return out


def slide_text(slide):
    parts = []
    for shape in slide.shapes:
        if shape.has_text_frame:
            t = shape.text_frame.text.strip()
            if t:
                parts.append(t)
        elif shape.has_table:
            for row in shape.table.rows:
                cells = [c.text.strip() for c in row.cells]
                if any(cells):
                    parts.append(" | ".join(cells))
        elif shape.has_chart:
            chart = shape.chart
            for series in chart.series:
                try:
                    vals = ", ".join(
                        str(v) for v in series.values if v is not None)
                except Exception:
                    vals = "?"
                parts.append("Chart series %s: %s" % (series.name, vals))
    return "\n".join(parts).strip()


def parse_deck(path):
    """[(slide_no, text, has_chart)] in deck order."""
    from pptx import Presentation
    prs = Presentation(str(path))
    out = []
    for i, slide in enumerate(prs.slides, start=1):
        has_chart = any(s.has_chart for s in slide.shapes
                        if hasattr(s, "has_chart"))
        out.append((i, slide_text(slide), has_chart))
    return out


def parse_range(cell_range):
    m = re.fullmatch(r"([A-Z]+)1:([A-Z]+)(\d+)", cell_range)
    if not m:
        raise ValueError("unsupported sheet range: %r" % cell_range)
    _, last_col, last_row = m.groups()
    return last_col, int(last_row)


def parse_sheet_windows(path, sheet_name, rows_per_chunk, last_col, last_row):
    """[(cell_range, text)] windows over data rows 2..last_row."""
    from openpyxl import load_workbook
    wb = load_workbook(str(path), read_only=True, data_only=True)
    ws = wb[sheet_name]
    header = next(ws.iter_rows(min_row=1, max_row=1, values_only=True))
    header = [(h if h is not None else "") for h in header]
    chunks = []
    row = 2
    while row <= last_row:
        end = min(row + rows_per_chunk - 1, last_row)
        lines = [" | ".join(str(h) for h in header)]
        for r in ws.iter_rows(min_row=row, max_row=end, values_only=True):
            vals = [(v if v is not None else "") for v in r]
            if any(str(v).strip() for v in vals):
                lines.append(" | ".join(str(v) for v in vals))
        chunks.append(("%s!A%d:%s%d" % (sheet_name, row, last_col, end),
                       "\n".join(lines)))
        row = end + 1
    wb.close()
    return chunks


# ---------------------------------------------------------------- Spark

class SparkEnricher:
    """Model captions for chart chunks via api/meta_client.MetaClient.

    Enabled when META_API_KEY is set (base URL and model have defaults).
    Any failure degrades to local-only text with a warning. Results are
    cached by MetaClient, so a reseed never calls the model again.
    """

    def __init__(self, force_off=False, client=None):
        self.client = client or meta_client.MetaClient()
        self.enabled = self.client.enabled and not force_off
        if self.enabled:
            print("Spark enrichment: on (model %s)" % self.client.model)
        else:
            print("Spark enrichment: off (META_API_KEY not set); "
                  "local parse only.")

    def caption(self, pointer_label, text):
        """One-sentence model caption for a chart/table chunk, or None."""
        if not self.enabled:
            return None
        prompt = ("Describe in one sentence the single citable fact a Q&A "
                  "system should quote from this %s. Text:\n%s"
                  % (pointer_label, text[:2000]))
        try:
            payload = self.client.responses(
                {"input": prompt, "store": False}, label="caption")
            return meta_client.output_text(payload).strip() or None
        except meta_client.MetaError as e:
            print("warning: Spark caption failed (%s); continuing local-only."
                  % e)
            return None


# ---------------------------------------------------------------- ingest

def ingest(corpus_dir, database_url, no_spark=False):
    manifest = load_manifest(corpus_dir)
    windows = manifest["chunking"]["sheet_windows"]
    spark = SparkEnricher(force_off=no_spark)

    migrate.cmd_up(database_url)

    import psycopg
    counts = {}
    with psycopg.connect(database_url) as conn:
        with conn.transaction():
            for entry in manifest["entries"]:
                sid = entry["id"]
                lic = entry["license_class"]
                path = corpus_dir / entry["filename"]
                anchor = entry["citation_anchors"]["type"]
                rows = []  # (chunk_index, text, page, cell_range, slide)

                if anchor == "page":
                    for page_no, text in parse_pdf_pages(path):
                        if not text:
                            sidecar = path.with_name(path.stem + "-ocr.txt")
                            if sidecar.exists():
                                text = sidecar.read_text(
                                    encoding="utf-8").strip()
                                print("  %s p.%d: no text layer, "
                                      "used OCR sidecar" % (sid, page_no))
                            else:
                                raise RuntimeError(
                                    "%s p.%d has no text and no OCR sidecar"
                                    % (sid, page_no))
                        rows.append((page_no - 1, text, page_no, None, None))
                elif anchor == "slide":
                    for slide_no, text, has_chart in parse_deck(path):
                        if has_chart:
                            note = spark.caption("slide %d" % slide_no, text)
                            if note:
                                text += "\n[Spark] %s" % note
                        rows.append((slide_no - 1, text, None, None, slide_no))
                elif anchor == "cell-range":
                    cfg = windows[sid]
                    last_col, last_row = parse_range(
                        entry["citation_anchors"]["range"])
                    assert cfg["sheet"] == entry["citation_anchors"]["sheet"]
                    for i, (rng, text) in enumerate(parse_sheet_windows(
                            path, cfg["sheet"], cfg["rows_per_chunk"],
                            last_col, last_row)):
                        rows.append((i, text, None, rng, None))
                else:
                    raise ValueError("unknown anchor type %r" % anchor)

                conn.execute("DELETE FROM chunks WHERE source_id = %s", (sid,))
                with conn.cursor() as cur:
                    cur.executemany(
                        "INSERT INTO chunks (source_id, license_class, "
                        "chunk_index, text, page, cell_range, slide) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                        [(sid, lic, idx, text, page, cr, slide)
                         for idx, text, page, cr, slide in rows])
                counts[sid] = len(rows)
                exp = entry.get("expected_chunks")
                flag = "" if exp is None or exp == len(rows) else \
                    "  MISMATCH (manifest expects %d)" % exp
                print("%s: %d chunks%s" % (sid, len(rows), flag))

    total = sum(counts.values())
    print("total: %d chunks from %d files" % (total, len(counts)))
    return counts


def main(argv=None):
    parser = argparse.ArgumentParser(description="Kohu corpus ingest (P21)")
    parser.add_argument("--database-url", default=DEFAULT_DATABASE_URL)
    parser.add_argument("--corpus", default=str(DEFAULT_CORPUS))
    parser.add_argument("--no-spark", action="store_true",
                        help="force local-only parse even if Spark is set up")
    args = parser.parse_args(argv)
    ingest(pathlib.Path(args.corpus), args.database_url, args.no_spark)
    return 0


if __name__ == "__main__":
    sys.exit(main())
