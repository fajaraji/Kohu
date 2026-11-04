"""Build the licensed data files and the simulated internal files.

Public data: World Bank World Development Indicators for ten ASEAN
countries, 2019 to 2024 (corpus/public/worldbank-asean-2019-2024.csv,
CC BY 4.0). In the demo this data plays the role of purchased data:

  licensed/asean-outlook-report.pdf     company-wide license (simulated)
  licensed/asean-indicators-dataset.xlsx  seat-limited license (simulated)

The vendor name, license terms and seat counts are simulated and labeled
on every file. Numbers are World Bank values (report rounds to 1 decimal).

Simulated internal files (no public source exists for these):

  internal/regional-expansion-deck.pptx  slide deck; slide 4 deliberately
                                         states a 2023 Viet Nam growth
                                         figure that differs from the
                                         World Bank data, slide 6 states a
                                         spend limit that differs from the
                                         handbook
  internal/team-performance.xlsx         Manager-only performance sheet
                                         (role codes, no real people)
  internal/refund-process.pdf            written process for the demo
                                         back office app; deliberately
                                         says refunds above $200 need a
                                         supervisor code while the demo
                                         video says $500

Usage: python corpus/build_public_data.py
"""

import csv
import html
import io
import pathlib
import subprocess
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
CSV = HERE / "public" / "worldbank-asean-2019-2024.csv"
LIC = HERE / "licensed"
INT = HERE / "internal"
YEARS = ["2019", "2020", "2021", "2022", "2023", "2024"]
VENDOR = "Meridian Market Data (simulated vendor)"
SIM = "Simulated scenario for the Kohu demo"

INDICATORS = [
    ("NY.GDP.MKTP.KD.ZG", "GDP growth (annual %)"),
    ("NE.CON.PRVT.KD.ZG", "Household final consumption growth (annual %)"),
    ("NV.IND.MANF.ZS", "Manufacturing, value added (% of GDP)"),
    ("NY.GDP.MKTP.CD", "GDP (current US$)"),
]


def load():
    data, countries = {}, []
    with CSV.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["country"] not in countries:
                countries.append(r["country"])
            v = float(r["value"]) if r["value"] else None
            data[(r["country"], r["indicator_code"], r["year"])] = v
    return data, sorted(countries)


def fmt(v, code):
    if v is None:
        return "n/a"
    if code == "NY.GDP.MKTP.CD":
        return "%.1f" % (v / 1e9)
    return "%.1f" % v


# ------------------------------------------------------------- report

def chart_png(data, countries, year="2024"):
    """Bar chart image (no text layer once embedded in the PDF)."""
    from PIL import Image, ImageDraw, ImageFont

    vals = sorted(((data[(c, "NY.GDP.MKTP.KD.ZG", year)], c)
                   for c in countries), reverse=True)
    W, H = 1400, 820
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    f = ImageFont.truetype(font_path, 26)
    fb = ImageFont.truetype(font_path.replace("Sans", "Sans-Bold"), 32)
    d.text((40, 24), "Real GDP growth, %s (annual %%)" % year, fill="#111",
           font=fb)
    left, top, right, bottom = 120, 110, W - 40, H - 150
    lo, hi = -2.0, 8.0
    y0 = bottom - (0 - lo) / (hi - lo) * (bottom - top)
    for tick in range(-2, 9, 2):
        y = bottom - (tick - lo) / (hi - lo) * (bottom - top)
        d.line([(left, y), (right, y)], fill="#e5e5e5", width=2)
        d.text((40, y - 14), "%d" % tick, fill="#444", font=f)
    bw = (right - left) / len(vals)
    for i, (v, c) in enumerate(vals):
        x = left + i * bw + bw * 0.18
        y = bottom - (v - lo) / (hi - lo) * (bottom - top)
        d.rectangle([x, min(y, y0), x + bw * 0.64, max(y, y0)],
                    fill="#2f6db5" if v >= 0 else "#c0392b")
        d.text((x, min(y, y0) - 34), "%.1f" % v, fill="#111", font=f)
        label = {"Brunei Darussalam": "Brunei", "Philippines": "Philippines",
                 "Lao PDR": "Lao PDR"}.get(c, c)
        d.text((x - 6, bottom + 18), label, fill="#111",
               font=ImageFont.truetype(font_path, 21))
    d.line([(left, y0), (right, y0)], fill="#111", width=2)
    d.text((40, H - 60), "Source: World Bank WDI (CC BY 4.0).",
           fill="#555", font=f)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def table_html(data, countries, code, title, note=""):
    head = "".join("<th>%s</th>" % y for y in YEARS)
    rows = []
    for c in countries:
        cells = "".join("<td>%s</td>" % fmt(data[(c, code, y)], code)
                        for y in YEARS)
        rows.append("<tr><td>%s</td>%s</tr>" % (html.escape(c), cells))
    return ("<h2>%s</h2><table><tr><th>Country</th>%s</tr>%s</table>"
            "<p class='note'>%s</p>"
            % (html.escape(title), head, "".join(rows), note))


def build_report(data, countries, chart_path):
    g = lambda c, y: fmt(data[(c, "NY.GDP.MKTP.KD.ZG", y)],  # noqa: E731
                         "NY.GDP.MKTP.KD.ZG")
    pages = []
    pages.append(
        "<div class='cover'><h1>ASEAN Economic Indicators Report "
        "2019 to 2024</h1><p class='lead'>Published by %s</p>"
        "<table class='lic'><tr><td>License</td><td>Company-wide license. "
        "Every employee may read and cite this report.</td></tr>"
        "<tr><td>Coverage</td><td>Ten ASEAN economies, 2019 to 2024</td></tr>"
        "<tr><td>Term</td><td>1 Jan 2026 to 31 Dec 2026</td></tr>"
        "<tr><td>Underlying data</td><td>World Bank, World Development "
        "Indicators, CC BY 4.0</td></tr></table>"
        "<p class='sim'>%s. The vendor, license and term are simulated. "
        "All figures are World Bank values, rounded to one decimal. The "
        "World Bank has not endorsed this report or Kohu.</p></div>"
        % (VENDOR, SIM))
    pages.append(
        "<h2>Key findings</h2>"
        "<p>Growth across the region recovered after the 2020 contraction. "
        "In 2023 the Philippines grew fastest at %s percent, followed by "
        "Indonesia at %s percent, Cambodia at %s percent and Viet Nam at "
        "%s percent.</p>"
        "<p>In 2024 Viet Nam led the region with real GDP growth of %s "
        "percent, ahead of Cambodia at %s percent and the Philippines at %s "
        "percent. Myanmar contracted by %s percent.</p>"
        "<p>Indonesia was the steadiest large economy, growing between %s "
        "and %s percent every year from 2022 to 2024.</p>"
        "<p>Household consumption and manufacturing tables follow. Figure 1 "
        "on page 4 charts 2024 growth for all ten economies.</p>"
        % (g("Philippines", "2023"), g("Indonesia", "2023"),
           g("Cambodia", "2023"), g("Viet Nam", "2023"),
           g("Viet Nam", "2024"), g("Cambodia", "2024"),
           g("Philippines", "2024"),
           fmt(-data[("Myanmar", "NY.GDP.MKTP.KD.ZG", "2024")],
               "NY.GDP.MKTP.KD.ZG"),
           g("Indonesia", "2024"), g("Indonesia", "2022")))
    pages.append(table_html(
        data, countries, "NY.GDP.MKTP.KD.ZG",
        "Table 1. Real GDP growth (annual %)",
        "Viet Nam real GDP growth was %s percent in 2023."
        % g("Viet Nam", "2023")))
    pages.append("<h2>Figure 1</h2><img class='chart' src='%s'>"
                 % chart_path.as_uri())
    pages.append(table_html(
        data, countries, "NE.CON.PRVT.KD.ZG",
        "Table 2. Household final consumption growth (annual %)",
        "n/a means the World Bank series has no value for that year."))
    pages.append(table_html(
        data, countries, "NV.IND.MANF.ZS",
        "Table 3. Manufacturing, value added (% of GDP)")
        + table_html(data, countries, "NY.GDP.MKTP.CD",
                     "Table 4. GDP (current US$, billions)"))
    pages.append(
        "<h2>Method and sources</h2><p>All series come from the World Bank "
        "World Development Indicators (indicator codes NY.GDP.MKTP.KD.ZG, "
        "NE.CON.PRVT.KD.ZG, NV.IND.MANF.ZS, NY.GDP.MKTP.CD), licensed CC BY "
        "4.0. Values are rounded to one decimal place. The full unrounded "
        "dataset is sold separately as a seat-limited spreadsheet.</p>"
        "<p class='sim'>%s. Meridian Market Data does not exist.</p>" % SIM)
    css = """
      body{font-family:Inter,'DejaVu Sans',sans-serif;font-size:11pt;
           color:#1d1d1f} .page{page-break-after:always}
      h1{font-size:24pt;margin-top:80pt} h2{font-size:15pt}
      table{border-collapse:collapse;margin:6pt 0}
      td,th{border:1px solid #bbb;padding:3pt 7pt;font-size:10pt}
      th{background:#eef2f7} .lic td:first-child{font-weight:600}
      .sim{font-size:9pt;color:#7a4b00;background:#fff4dd;padding:6pt}
      .note{font-size:9.5pt;color:#333} .chart{width:100%}
      .lead{font-size:13pt;color:#333}"""
    footer = ("<div style='font-size:7pt;width:100%;text-align:center;"
              "color:#666'>ASEAN Economic Indicators Report - " + VENDOR +
              " - company-wide license (simulated) - page "
              "<span class='pageNumber'></span></div>")
    return ("<!doctype html><html><head><meta charset='utf-8'>"
            "<meta name='pdf-footer' content=\"%s\"><style>%s</style>"
            "</head><body>%s</body></html>"
            % (html.escape(footer, quote=True), css,
               "".join("<div class='page'>%s</div>" % p for p in pages)))


# -------------------------------------------------------------- sheets

def build_dataset_xlsx(data, countries, path):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = "Data"
    ws.append(["Country", "Country code", "Indicator", "Indicator code"]
              + YEARS)
    codes = {}
    with CSV.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            codes[r["country"]] = r["country_code"]
    for code, name in INDICATORS:
        for c in countries:
            ws.append([c, codes[c], name, code]
                      + [data[(c, code, y)] for y in YEARS])
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="DDE6F0")
    ws.column_dimensions["A"].width = 20
    ws.column_dimensions["C"].width = 44
    lic = wb.create_sheet("License")
    for row in [
            ["ASEAN indicators dataset, full unrounded values"],
            ["Vendor", VENDOR],
            ["License", "Seat-limited: 5 named seats (Analyst and Steward "
                        "roles). Do not share outside licensed seats."],
            ["Term", "1 Jan 2026 to 31 Dec 2026"],
            ["Underlying data", "World Bank WDI, CC BY 4.0"],
            ["Note", SIM + ". Vendor and seats are simulated."]]:
        lic.append(row)
    wb.save(path)
    return ws.max_row


def build_performance_xlsx(path):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Q3"
    ws.append(["Team member", "Role", "Region", "Q3 target (USD k)",
               "Q3 actual (USD k)", "Attainment %", "Manager note"])
    rows = [
        ("Rep 01", "Account executive", "Viet Nam", 420, 465, None,
         "Closed two distributor renewals early"),
        ("Rep 02", "Account executive", "Indonesia", 510, 448, None,
         "Pipeline slipped to Q4 after a buyer change"),
        ("Rep 03", "Account executive", "Philippines", 380, 401, None,
         "On track"),
        ("Rep 04", "Account executive", "Thailand", 300, 233, None,
         "Needs coaching on discount approvals"),
        ("Rep 05", "Partner manager", "Malaysia", 260, 270, None,
         "On track"),
        ("Rep 06", "Partner manager", "Singapore", 350, 362, None,
         "Strong partner sourced pipeline"),
        ("Rep 07", "Account executive", "Cambodia", 150, 171, None,
         "First full quarter"),
        ("Rep 08", "Account executive", "Viet Nam", 400, 352, None,
         "Lost one tender on price"),
    ]
    for r in rows:
        r = list(r)
        r[5] = round(r[4] / r[3] * 100, 1)
        ws.append(r)
    ws.append([])
    ws.append([SIM + ". Role codes only; no real people."])
    wb.save(path)


# ---------------------------------------------------------------- deck

def build_deck(path):
    from pptx import Presentation
    from pptx.util import Inches, Pt

    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    slides = [
        ("Regional expansion review", [
            "Internal planning deck, Q3 2026",
            "Prepared by the strategy team for the leadership offsite"]),
        ("Why Southeast Asia", [
            "Ten economies, one regional trade bloc",
            "Growth rebounded after the 2020 contraction",
            "We already sell in six of the ten markets"]),
        ("Markets we cover today", [
            "Viet Nam, Indonesia, Philippines, Thailand, Malaysia, Singapore",
            "Cambodia added in Q3 2026 as a pilot market"]),
        ("Where growth is fastest", [
            "Viet Nam grew 6.5% in 2023, the fastest economy in ASEAN",
            "This is why Viet Nam is our first expansion market for 2027",
            "Indonesia stays our largest market by revenue"]),
        ("Indonesia", [
            "Indonesia grew about 5% a year from 2022 to 2024",
            "Steady demand from household consumption"]),
        ("Travel and spending for the expansion team", [
            "Book flights through the travel desk",
            "Each team member has a spending limit of $3,000 per month",
            "Ask your team lead before any purchase above the limit"]),
        ("Next steps", [
            "Confirm market sizing with the licensed ASEAN data",
            "Decide the first expansion market at the December offsite"]),
    ]
    blank = prs.slide_layouts[6]
    for title, bullets in slides:
        s = prs.slides.add_slide(blank)
        tb = s.shapes.add_textbox(Inches(0.7), Inches(0.5), Inches(12),
                                  Inches(1.2))
        tb.text_frame.text = title
        tb.text_frame.paragraphs[0].runs[0].font.size = Pt(36)
        tb.text_frame.paragraphs[0].runs[0].font.bold = True
        body = s.shapes.add_textbox(Inches(0.9), Inches(1.9), Inches(11.5),
                                    Inches(4.5)).text_frame
        body.word_wrap = True
        for i, b in enumerate(bullets):
            p = body.paragraphs[0] if i == 0 else body.add_paragraph()
            p.text = "- " + b
            p.runs[0].font.size = Pt(24)
        foot = s.shapes.add_textbox(Inches(0.7), Inches(6.8), Inches(12),
                                    Inches(0.4)).text_frame
        foot.text = SIM + " (internal deck, not a real company document)"
        foot.paragraphs[0].runs[0].font.size = Pt(11)
    prs.save(path)
    return len(slides)


# ------------------------------------------------------- process PDF

PROCESS_STEPS = [
    ("Open Orders", "Open Orders from the left menu of the back office."),
    ("Find the order", "Type the order number in the search box and press "
     "Search."),
    ("Check the status", "Open the order. Only refund orders whose status "
     "is Delivered."),
    ("Check stock", "Click Check stock. The returned item must be back in "
     "stock before any refund is paid."),
    ("Choose a reason", "Choose a refund reason: Damaged on arrival, Wrong "
     "item sent, or Customer changed mind."),
    ("Issue the refund", "Click Issue refund. Type the order number again in "
     "the confirmation dialog."),
    ("Supervisor approval", "Refunds above $200 need a supervisor code. Ask "
     "a supervisor to type their code in the confirmation dialog."),
    ("Confirm", "Click Confirm refund and wait for the green confirmation "
     "message."),
]


def build_process_pdf(out):
    rows = "".join("<tr><td>%d</td><td><b>%s</b><br>%s</td></tr>"
                   % (i + 1, html.escape(t), html.escape(d))
                   for i, (t, d) in enumerate(PROCESS_STEPS))
    page = (
        "<!doctype html><html><head><meta charset='utf-8'><style>"
        "body{font-family:Inter,'DejaVu Sans',sans-serif;font-size:11pt}"
        "table{border-collapse:collapse;width:100%%}td{border:1px solid #bbb;"
        "padding:6pt;vertical-align:top}.sim{font-size:9pt;color:#7a4b00;"
        "background:#fff4dd;padding:6pt}</style></head><body>"
        "<h1>Customer refund process</h1>"
        "<p>Harbor Supply back office, operations team. Version 3, "
        "March 2026.</p><p>Use this process for every customer refund. "
        "A refund cannot be reversed once it is confirmed.</p>"
        "<table>%s</table>"
        "<h2>Out of stock items</h2><p>If Check stock shows Out of stock, "
        "do not refund. Ask the warehouse team to receive the returned item "
        "first.</p><p class='sim'>%s. Harbor Supply is not a real company; "
        "this document belongs to the simulated back office app in "
        "corpus/demo-app.</p></body></html>" % (rows, SIM))
    with tempfile.TemporaryDirectory() as tmp:
        f = pathlib.Path(tmp) / "process.html"
        f.write_text(page, encoding="utf-8")
        subprocess.run(["node", str(HERE / "tools" / "html2pdf.mjs"),
                        str(f), str(out)], check=True)


def main():
    data, countries = load()
    LIC.mkdir(exist_ok=True)
    INT.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        chart = pathlib.Path(tmp) / "figure1.png"
        chart.write_bytes(chart_png(data, countries))
        page = pathlib.Path(tmp) / "report.html"
        page.write_text(build_report(data, countries, chart),
                        encoding="utf-8")
        subprocess.run(["node", str(HERE / "tools" / "html2pdf.mjs"),
                        str(page), str(LIC / "asean-outlook-report.pdf")],
                       check=True)
    n = build_dataset_xlsx(data, countries,
                           LIC / "asean-indicators-dataset.xlsx")
    print("dataset rows incl. header:", n)
    build_performance_xlsx(INT / "team-performance.xlsx")
    print("deck slides:", build_deck(INT / "regional-expansion-deck.pptx"))
    build_process_pdf(INT / "refund-process.pdf")


if __name__ == "__main__":
    main()
