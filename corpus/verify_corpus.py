"""Check the committed corpus: files, licenses, planted differences, access.

Exit 0 iff every check passes. Run by seed.sh before ingest.
"""

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ok = True


def check(name, cond):
    global ok
    ok &= bool(cond)
    print(("PASS " if cond else "FAIL ") + name)


def main():
    import pymupdf
    from openpyxl import load_workbook
    from pptx import Presentation

    m = json.loads((HERE / "manifest.json").read_text())
    ids = [e["id"] for e in m["entries"]]
    check("manifest ids unique", len(ids) == len(set(ids)))
    check("manifest label states the scenario",
          m["label"] == "Public documents and data with a simulated scenario")
    for e in m["entries"]:
        check("%s file exists" % e["id"], (HERE / e["filename"]).exists())
        check("%s has a notice" % e["id"], e.get("notice"))
    lic = (HERE / "handbook" / "LICENSE-posthog-contents.txt").read_text()
    check("PostHog /contents license notice kept",
          "Permission is hereby granted" in lic and "PostHog Inc." in lic)
    notice = (HERE / "NOTICE.md").read_text()
    check("NOTICE says PostHog does not endorse",
          "PostHog does not endorse" in notice)
    scan = pymupdf.open(str(HERE / "handbook" / "handbook-training-scan.pdf"))
    check("scanned handbook page has no text layer",
          all(not p.get_text().strip() for p in scan))
    rep = pymupdf.open(str(HERE / "licensed" / "asean-outlook-report.pdf"))
    check("report p.3 states Viet Nam 2023 growth 5.0",
          "Viet Nam real GDP growth was 5.0 percent in 2023"
          in rep[2].get_text().replace("\n", " "))
    check("report chart page p.4 has no figures in its text layer",
          "7.0" not in rep[3].get_text())
    deck = Presentation(str(HERE / "internal" / "regional-expansion-deck.pptx"))
    texts = ["\n".join(s.text_frame.text for s in sl.shapes
                       if s.has_text_frame) for sl in deck.slides]
    check("deck slide 4 states the planted 6.5% figure", "6.5%" in texts[3])
    check("deck slide 6 states the planted $3,000 limit", "$3,000" in texts[5])
    wb = load_workbook(str(HERE / "licensed" / "asean-indicators-dataset.xlsx"),
                       read_only=True)
    ws = wb["Data"]
    row11 = [c.value for c in next(ws.iter_rows(min_row=11, max_row=11))]
    check("dataset Data!A11 is Viet Nam GDP growth, I11 is 2023 = 4.98",
          row11[0] == "Viet Nam" and row11[3] == "NY.GDP.MKTP.KD.ZG"
          and abs(row11[8] - 4.9787) < 0.001)
    proc = pymupdf.open(str(HERE / "internal" / "refund-process.pdf"))
    check("process PDF states the planted $200 threshold",
          "Refunds above $200 need a supervisor code" in proc[0].get_text()
          .replace("\n", " "))
    by_id = {e["id"]: e for e in m["entries"]}
    everyone = {"employee", "analyst", "manager", "steward"}
    check("licensed report is company-wide",
          set(by_id["asean-outlook-report"]["visible_to"]) == everyone)
    check("licensed dataset is Analyst and Steward only",
          set(by_id["asean-indicators-dataset"]["visible_to"])
          == {"analyst", "steward"})
    check("performance sheet is Manager and Steward only",
          set(by_id["team-performance"]["visible_to"]) == {"manager", "steward"})
    print("CORPUS VERIFY: " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
