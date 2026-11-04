# Corpus notices

Kohu's demo corpus is "Public documents and data with a simulated scenario". This file lists every third-party item, its license, and what was changed, and every simulated item.

## Third-party material

| Path | Source | License | Changes |
|---|---|---|---|
| `handbook/handbook-*.pdf` (9 files) and `handbook/handbook-training-scan.pdf` | PostHog handbook, `contents/handbook/` in [PostHog/posthog.com](https://github.com/PostHog/posthog.com) at commit `f9d5711`. Page list in `handbook/pages.json` | The repository LICENSE grants MIT-style permission for content in the `/contents/` folder. The notice is copied in full to `handbook/LICENSE-posthog-contents.txt` and is printed on every page | Text is not edited. Markdown was rendered to PDF with pandoc and headless Chromium. MDX components show as their inner text, images are not embedded, front matter is dropped except the title. `people/training.md` was additionally rasterized into an image-only PDF to exercise the scanned page path, and `handbook-training-scan-sidecar.txt` holds that page's text taken from the source PDF at build time (a labeled fallback, not OCR) |
| `public/worldbank-asean-2019-2024.csv` | World Bank, World Development Indicators, via `api.worldbank.org`, retrieved 2026-11-04 | CC BY 4.0 | Four indicators for ten ASEAN countries, 2019 to 2024, flattened to one CSV |
| `licensed/asean-outlook-report.pdf`, `licensed/asean-indicators-dataset.xlsx` | Built from the World Bank CSV above by `build_public_data.py` | Data CC BY 4.0 | The report rounds values to one decimal and adds a chart; the dataset keeps full values |

PostHog does not endorse this project. The World Bank has not endorsed this project.

## Simulated scenario

In the demo the World Bank data plays the role of purchased data. The vendor "Meridian Market Data", the license terms, the company-wide coverage of the report, the 5-seat limit on the dataset and the license term are simulated and labeled as such on every file and in the app.

These files are simulated because no public source exists for them. Each one says so on its pages:

| Path | What it is | Planted difference |
|---|---|---|
| `internal/regional-expansion-deck.pptx` | Internal strategy deck | Slide 4 says Viet Nam grew 6.5% in 2023 and was the fastest in ASEAN; the World Bank value is 5.0% (Philippines 5.5% was fastest). Slide 6 says the monthly spending limit is $3,000; the handbook says $5,000 |
| `internal/team-performance.xlsx` | Manager-only performance sheet with role codes, no real people | none |
| `internal/refund-process.pdf` | Written refund process for the demo app | Says refunds above $200 need a supervisor code; the demo video says $500 |
| `demo-app/` | Back office web app "Harbor Supply" (not a real company), its 68 s demo clip `refund-process.mp4`, frames and ground truth | The clip's narration is a synthetic voice made with Kokoro TTS (Apache 2.0 model, voice `af_heart`) |
