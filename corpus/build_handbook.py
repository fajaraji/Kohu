"""Render selected PostHog handbook pages to PDF (public company documents).

Source: github.com/PostHog/posthog.com, folder contents/handbook. The
repository LICENSE grants MIT-style permission for the /contents folder
(notice copied to corpus/handbook/LICENSE-posthog-contents.txt). Page text
is not edited: Markdown is rendered as is with pandoc and printed with
headless Chromium. MDX components render as their inner text, images are
not embedded, and front matter is dropped except the title. One page is
also rasterized into an image-only "scanned" PDF to exercise the scan
path. PostHog does not endorse Kohu.

The built PDFs are committed, so seeding needs no network. Rebuild with:
  python corpus/build_handbook.py --posthog /path/to/posthog.com
"""

import argparse
import html
import json
import pathlib
import re
import subprocess
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "handbook"

# (source id, path under contents/handbook)
PAGES = [
    ("handbook-spending-money", "people/spending-money.md"),
    ("handbook-time-off", "people/time-off.md"),
    ("handbook-benefits", "people/benefits.md"),
    ("handbook-feedback", "people/feedback.md"),
    ("handbook-offboarding", "people/offboarding.md"),
    ("handbook-side-gigs", "people/side-gigs.md"),
    ("handbook-meetings", "getting-started/meetings.md"),
    ("handbook-communication", "company/communication.md"),
    ("handbook-goal-setting", "company/goal-setting.md"),
    ("handbook-training", "people/training.md"),
]
SCANNED = "handbook-training"

CSS = """
body { font-family: Inter, 'DejaVu Sans', sans-serif; font-size: 10.5pt;
       line-height: 1.45; color: #1d1d1f; }
h1 { font-size: 20pt; margin: 0 0 4pt; }
h2 { font-size: 14pt; margin-top: 16pt; }
h3 { font-size: 12pt; }
.src { font-size: 8.5pt; color: #555; border-bottom: 1px solid #ccc;
       padding-bottom: 6pt; margin-bottom: 10pt; }
table { border-collapse: collapse; } td, th { border: 1px solid #bbb;
       padding: 3pt 5pt; font-size: 9.5pt; }
code { font-size: 9pt; } a { color: #1d1d1f; }
img { display: none; }
"""


def split_front_matter(text):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        return {}, text
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip("'\"")
    return meta, text[m.end():]


def render_html(md_body, title, rel_path, commit):
    body = subprocess.run(
        ["pandoc", "-f", "gfm+raw_html", "-t", "html5"], input=md_body,
        capture_output=True, text=True, check=True).stdout
    source = ("PostHog handbook, contents/handbook/%s at commit %s. "
              "Copyright (c) 2020-2025 PostHog Inc., MIT-style license for "
              "/contents (see LICENSE-posthog-contents.txt). Text unchanged; "
              "rendered to PDF for the Kohu demo. PostHog does not endorse "
              "Kohu." % (rel_path, commit[:7]))
    footer = ("<div style='font-size:7pt;width:100%;text-align:center;"
              "color:#666'>PostHog handbook (MIT-style license) - "
              + html.escape(title) + " - page <span class='pageNumber'></span>"
              " of <span class='totalPages'></span></div>")
    return ("<!doctype html><html><head><meta charset='utf-8'>"
            "<meta name='pdf-footer' content=\"%s\">"
            "<title>%s</title><style>%s</style></head><body>"
            "<h1>%s</h1><div class='src'>%s</div>%s</body></html>"
            % (html.escape(footer, quote=True), html.escape(title), CSS,
               html.escape(title), html.escape(source), body))


def rasterize(pdf_path, out_pdf, sidecar_txt, dpi=110):
    """Image-only copy of a PDF plus a build-time text sidecar.

    The sidecar holds the page text taken from the source PDF at build
    time. It is a labeled fallback used only when Spark cannot read the
    page images; it is not OCR output.
    """
    import pymupdf as fitz

    src = fitz.open(str(pdf_path))
    dst = fitz.open()
    pages_text = []
    for page in src:
        pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
        img_page = dst.new_page(width=page.rect.width,
                                height=page.rect.height)
        img_page.insert_image(img_page.rect, stream=pix.tobytes("png"))
        pages_text.append(page.get_text().strip())
    dst.save(str(out_pdf), deflate=True)
    sidecar_txt.write_text(
        "\f".join(pages_text), encoding="utf-8")
    return len(pages_text)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--posthog", required=True,
                    help="path to a checkout of PostHog/posthog.com")
    args = ap.parse_args(argv)
    root = pathlib.Path(args.posthog)
    commit = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                            capture_output=True, text=True,
                            check=True).stdout.strip()
    lic = (root / "LICENSE").read_text(encoding="utf-8")
    assert "For content in the /contents/ folder" in lic, "license changed?"
    OUT.mkdir(exist_ok=True)
    (OUT / "LICENSE-posthog-contents.txt").write_text(
        lic[lic.index("# For content in the /contents/ folder"):],
        encoding="utf-8")
    pairs, meta_out = [], []
    with tempfile.TemporaryDirectory() as tmp:
        for sid, rel in PAGES:
            text = (root / "contents" / "handbook" / rel).read_text(
                encoding="utf-8")
            meta, body = split_front_matter(text)
            title = meta.get("title") or sid
            page_html = pathlib.Path(tmp) / (sid + ".html")
            page_html.write_text(render_html(body, title, rel, commit),
                                 encoding="utf-8")
            pairs += [str(page_html), str(OUT / (sid + ".pdf"))]
            meta_out.append({"id": sid, "title": title,
                             "source_path": "contents/handbook/" + rel,
                             "commit": commit})
        subprocess.run(["node", str(HERE / "tools" / "html2pdf.mjs")]
                       + pairs, check=True)
    n = rasterize(OUT / (SCANNED + ".pdf"), OUT / (SCANNED + "-scan.pdf"),
                  OUT / (SCANNED + "-scan-sidecar.txt"))
    (OUT / (SCANNED + ".pdf")).unlink()  # only the scanned copy is kept
    (OUT / "pages.json").write_text(json.dumps(meta_out, indent=1),
                                    encoding="utf-8")
    print("scanned copy: %d pages" % n)


if __name__ == "__main__":
    main()
