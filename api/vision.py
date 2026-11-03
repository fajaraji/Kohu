"""Muse Spark page reading for scanned pages and chart pages (B2).

Ingest calls PageReader.read_page() for a PDF page with no useful text
layer or with a large image (a chart). The page image goes to Spark one
page per request; the result is cached in corpus/spark-cache/ by
MetaClient, so a reseed never calls the model again for the same page.
The chunk records text_origin = "spark-vision".
"""

import base64
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import meta_client  # noqa: E402

PROMPT = (
    "This is one page of a company document. Transcribe it as plain text "
    "for a search index. Copy every heading and sentence exactly. For a "
    "chart, give its title, then one line per bar or point as "
    "'label: value' using only values printed on the chart, then the "
    "source line. For a table, one line per row with cells separated by "
    " | . Do not add commentary, do not guess values that are not printed.")


class PageReader:
    def __init__(self, client=None):
        self.client = client or meta_client.MetaClient()
        # Cached readings work without a key; only new pages need one.
        self.enabled = True
        self.has_key = self.client.enabled
        self.calls = 0

    def read_page(self, source_id, page_no, png_bytes, text_layer=""):
        """Spark transcription of a page image, or None when unavailable."""
        if not self.enabled or not png_bytes:
            return None
        body = {"input": [{"role": "user", "content": [
            {"type": "input_image", "image_url": "data:image/png;base64,"
             + base64.b64encode(png_bytes).decode()},
            {"type": "input_text", "text": PROMPT}]}], "store": False}
        try:
            payload = self.client.responses(
                body, label="page-read %s p.%d" % (source_id, page_no))
        except meta_client.MetaError as e:
            print("warning: Spark page read failed for %s p.%d (%s)"
                  % (source_id, page_no, e))
            return None
        self.calls += 1
        text = meta_client.output_text(payload).strip()
        return text or None
