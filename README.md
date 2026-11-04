# Kohu

Kohu is one place to search and ask about what a company knows and what it has paid for.

Know-how sits on a few laptops and in a few heads, and the rest is scattered across documents, slides, sheets and screen recordings. A new hire has nowhere obvious to learn how a process works. The company buys data under a license that covers everyone, yet only a few people know it exists. Our team has seen this problem firsthand. Atlassian's State of Teams 2025 survey of about 12,000 knowledge workers found that teams lose 25% of their time searching for answers.

In Kohu people search and ask in plain words. What each person can see follows their role and the license the company bought. Every answer points to its source, down to the page, the spreadsheet cell, the slide, or the second in a video. When two sources disagree, Kohu shows both and a data admin (a data steward, in data governance terms) decides which one is right, and the answer changes.

Built for the Meta Global AI Developer Hackathon, Indie Developer track, theme Build for Your World. All AI features use Meta models only.

- Team: `alfianhid` (Representative), `fajaraji`
- Repository: <https://github.com/fajaraji/Kohu> (fork of <https://github.com/alfianhid/Kohu>)
- Demo data: "Public documents and data with a simulated scenario". See [corpus/NOTICE.md](corpus/NOTICE.md).

## Try it in 60 seconds

Needs Python 3.12+, Postgres 16 (with `pg_trgm`), FFmpeg and Node only if you rebuild corpus files.

```sh
pip install -r api/requirements.txt
cp .env.example .env          # optional: set META_API_KEY for live asks
./seed.sh                     # migrate, ingest, load reviewed video steps, conflicts
uvicorn api.app:app --port 8000
```

Open <http://localhost:8000>. Or run everything with Docker: `docker compose up --build`.

Without a key the seed still works (cached Muse Spark, transcription and SAM results are committed in `corpus/spark-cache/`), and asks fall back to a labeled extractive answer.

Three things to try:

1. Sign in as **New hire** and ask "What was Viet Nam's GDP growth in 2023?". The answer cites a page of the licensed ASEAN report, which the company bought for everyone, and shows that the internal deck says something different.
2. Use **Switch** (bottom left) to sign in as **Data admin**, open Conflicts, pick the report as right. Switch back to New hire and ask again. The answer changes and the deck figure is marked superseded.
3. As **New hire**, ask "How do I process a customer refund?". Click a ▶ citation. The screen recording plays from that second, with the step's frame and the button marked by SAM 3.1. Then open **Compare roles** to see the same question answered for all four roles.

## How it works

```
             signed persona token (HMAC)                 every read filtered by role
 browser ──────────────────────────────▶ FastAPI ──▶ retrieval (Postgres full text + pg_trgm)
                                           │
                                           ├─ agent.py   Muse Spark picks tools, up to 4 steps:
                                           │             search_knowledge, read_section, read_cells
                                           ├─ answer.py  final Muse Spark call (no tools, JSON schema),
                                           │             server rejects markers not from this run and
                                           │             numbers not in the cited chunk
                                           ├─ conflict.py Muse Spark judges candidate pairs across sources;
                                           │             data admin decides; loser ranked lower
                                           ├─ video.py   MP4 → Voice Transcribe → Spark (video + transcript)
                                           │             → validated steps → SAM marks → review → chunks
                                           └─ licenses.py who used licensed data, per answer
```

- **Ingest** (`api/ingest.py`): PDF pages, slides, and spreadsheet row windows become chunks with a citation pointer (`p.3`, `slide 4`, `Data!I11`, `t=23.5s`). Pages with no text layer or with a chart are read by Muse Spark (`api/vision.py`); each chunk records where its text came from.
- **Access** (`api/policy.py`, `api/auth.py`): personas come only from a signed token. The licensed report is company-wide; the full dataset is seat-limited to Analyst and Data admin; the performance sheet is Manager and Data admin only. Each role sees a different set: Employee 14 of 16 sources, Analyst 15, Manager 15, Data admin 16. Files are served only through `GET /files/{source_id}` after the same check.
- **Ask** (`api/agent.py`, `api/answer.py`): a model-driven loop with three tools that filter sources before reading. Documents are passed as data, and the prompt forbids following instructions inside them. The final answer is checked on the server. If the model fails, the answer is extractive and labeled degraded. `GET /runs/{id}/steps` shows the trace, filtered to what the viewer may see.
- **Conflicts** (`api/conflict.py`): candidate pairs come from full text search across sources (at most 30 per source), Muse Spark judges each one for factual contradictions, a data admin resolves them, and the losing side is marked stale.
- **Video guides** (`api/video.py`, `api/marks.py`): a recording becomes reviewed, time-cited steps with spoken reasons. Answers read the approved text and never rewatch the video.
- **Document regions** (`api/regions.py`): SAM 3.1 marks charts and tables on report pages, and Muse Spark reads the marked crop.

## Meta models and how Kohu uses them

| Model | Where | What it does |
|---|---|---|
| Muse Spark 1.3 (`muse-spark-1.3`) | `agent.py` | Chooses tool calls (Responses API function calling with `previous_response_id`) |
| | `answer.py` | Writes the final answer with structured output (`text.format` JSON schema) |
| | `vision.py` | Reads scanned pages and chart pages from images |
| | `video.py` | Turns a screen recording (Files API `input_video`) plus its timed transcript into steps, in background mode with polling |
| | `marks.py` | Proposes a box for the on-screen control of each step |
| | `conflict.py` | Judges whether two passages contradict each other (JSON schema) |
| | `regions.py` | Reads a chart or table cropped by SAM |
| Muse Voice Transcribe 1.0 | `video.py` | Transcribes the narration with turn start and end times |
| SAM 3.1 (`sam-3.1`) | `marks.py` | Marks the control in each step's frame (box prompt refining Spark's box; noun phrase when it agrees) |
| | `regions.py` | Finds charts and tables on report pages (noun phrases) |

All calls go through `api/meta_client.py`: retries on 429 and 5xx, a usage log with estimated spend, a spend stop (default $30), and a disk cache so a reseed never calls a model again. The whole build, including the spike, five question runs and the demo video footage, logged about $6.00 of Meta API usage.

## Eval

Full results with every number and every failure: [docs/eval-result.md](docs/eval-result.md). Spike notes from the first live API runs: [docs/spike.md](docs/spike.md).

- 20 frozen questions across four roles: 19, 19 and 20 passed in three runs on 2026-11-04. The only unstable question (q01) sometimes describes the stock check without the words its check looks for. An earlier first run scored 18 because two checks were wrong; they were amended with the reason recorded.
- Leak test: 0 failures in 74 checks of every role against every tool and route.
- Conflicts: 2 of 3 planted conflicts caught, 0 of 3 control pairs flagged. One extra flag inside PostHog's own handbook (two pages describe open source sponsorship money differently).
- Video steps on the refund clip (used for tuning): 9 of 9 steps, start time error median 0.22 s, 9 of 9 SAM marks on the right control.
- Held-out recording made after tuning: 4 of 5 steps found and marked on the right control; one step was merged with another and marked on the wrong button, and one extra step was added.
- Chart page read by Muse Spark: 10 of 10 values correct.

## Limitations

- The eval corpus is small and the conflict detection rules, mark rule and crop padding were tuned on it. Only the second recording is held out, and it scored lower (4 of 5 steps).
- Asks take about 20 to 40 seconds because each one makes three to five model calls.
- SAM masks are decoded with Meta's `meta-sam-parser`. Our parsing matches Meta's parser on every box and mask pixel of the 49 SAM records we have, but mask quality is checked by eye only. Without the package installed, marks fall back to SAM boxes.
- The planted spend-limit conflict was missed; the judge read the deck's limit as scoped to one team.
- Sign-in is a choice of four demo accounts with signed tokens, not a real identity provider. License terms, vendor, seats and costs are simulated.
- The Docker image was built and run end to end in the build environment, except for `meta-sam-parser`, which was left out there.
- On Vercel the per-visitor and per-IP rate limits live in each instance's memory, so they are looser than in a single container. The Meta spend stop is counted in the database and holds.
- Uploading new recordings is turned off on the public demo, so the public site shows the recordings that ship with the demo data.

## Data and licenses

Company documents are ten pages of PostHog's public handbook (MIT-style license for `/contents`, text unchanged, notice kept in `corpus/handbook/LICENSE-posthog-contents.txt`). PostHog does not endorse Kohu. Purchased data is simulated with World Bank World Development Indicators (CC BY 4.0). The deck, performance sheet, refund process, back office app and its narrated clip (synthetic Kokoro TTS voice) are simulated and labeled. Details in [corpus/NOTICE.md](corpus/NOTICE.md). Our code is MIT ([LICENSE](LICENSE)).

## Deploy

Kohu deploys to Vercel's free plan through Vercel's Git integration (`index.py`, `vercel.json`), with Postgres on Neon. A GitHub Actions job seeds the database from the committed corpus and model cache without a Meta key. A Cloudflare Containers setup is included as a paid alternative. Steps for both are in [docs/deploy.md](docs/deploy.md).

The container image (`Dockerfile`) also runs anywhere else. Set `DATABASE_URL`, `KOHU_ALLOW_REMOTE_DB=1`, `KOHU_SESSION_SECRET` and `META_API_KEY`, and for a public URL also `KOHU_PUBLIC_DEMO=1`. In that mode every visitor's data admin decisions stay private to their own browser, uploads are off, questions are rate limited, and Meta usage is logged in the database so the spend stop survives restarts.

## Repo layout

| Path | Contents |
|---|---|
| `api/` | FastAPI app and modules listed above, migrations `0001` to `0010` |
| `ui/` | Single page UI (no framework) |
| `corpus/` | Public and simulated corpus, build scripts, manifest, model cache, demo app and clip |
| `eval/` | Frozen questions and conflict pairs, eval runner, raw results |
| `tests/` | Pytest suite (fixtures and live response samples, no network) |
| `docs/` | Spike notes, eval results, deploy guide, design notes, run report (Indonesian), submission draft |
| `index.py`, `vercel.json`, `requirements.txt` | Vercel entry point and config |
| `.github/workflows/` | Tests on every push; seeds the demo database; optional Cloudflare deploy |
| `cloudflare/`, `wrangler.jsonc`, `Dockerfile` | Paid alternative: Cloudflare Containers (the same image runs anywhere) |
| `video/` | Demo video (`kohu-demo.mp4`), script, captions, and the scripts that capture the app and build the video |
| `TICKETS.md` | The v2 work plan and status |

Which work was done when is recorded in [HACKATHON.md](HACKATHON.md).
