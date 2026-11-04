"""Render every deck in the manifest to slide images for the citation panel.

Uses LibreOffice (headless) to convert the .pptx to PDF, then PyMuPDF to
render each page. Output: corpus/derived/<source_id>/slide-NN.png
(committed, so the app itself does not need LibreOffice).

  python corpus/build_slides.py
"""

import json
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent


def main():
    import pymupdf

    manifest = json.loads((HERE / "manifest.json").read_text())
    for e in manifest["entries"]:
        if e.get("kind") != "deck":
            continue
        out = HERE / "derived" / e["id"]
        out.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["soffice", "--headless", "--convert-to", "pdf",
                            "--outdir", tmp, str(HERE / e["filename"])],
                           check=True, capture_output=True, timeout=300)
            pdf = next(pathlib.Path(tmp).glob("*.pdf"))
            doc = pymupdf.open(str(pdf))
            for i, page in enumerate(doc, start=1):
                page.get_pixmap(dpi=110).save(str(out / ("slide-%02d.png" % i)))
            print("%s: %d slides" % (e["id"], doc.page_count))
    return 0


if __name__ == "__main__":
    sys.exit(main())
