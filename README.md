# Kohu

Kohu is one place to search and ask about what a company knows and what it has paid for.

Know-how sits on a few laptops and in a few heads, and the rest is scattered across documents, slides, sheets and screen recordings. A new hire has nowhere obvious to learn how a process works. The company buys data under a license that covers everyone, yet only a few people know it exists. Our team has seen this problem firsthand. Atlassian's State of Teams 2025 survey of about 12,000 knowledge workers found that teams lose 25% of their time searching for answers.

In Kohu people search and ask in plain words. What each person can see follows their role and the license the company bought. Every answer points to its source, down to the page, the spreadsheet cell, the slide, or the second in a video. When two sources disagree, Kohu shows both and a data steward decides which one is right, and the answer changes.

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

1. As **Employee**, ask "What was Viet Nam's GDP growth in 2023?". The answer cites a page of the licensed ASEAN report, which the company bought for everyone, and shows that the internal deck says something different.
2. Switch to **Steward**, open Conflicts, pick the report as right. Ask again as Employee. The answer changes and the deck figure is marked superseded.
3. As **Employee**, ask "How do I process a customer refund?". Click a ▶ citation. The screen recording plays from that second, with the step's frame and the button marked by SAM 3.1. Then open **Compare roles** to see the same question answered for all four roles.

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
                                           │             Steward decides; loser ranked lower
                                           ├─ video.py   MP4 → Voice Transcribe → Spark (video + transcript)
                                           │             → validated steps → SAM marks → review → chunks
                                           └─ licenses.py who used licensed data, per answer
```

- **Ingest** (`api/ingest.py`): PDF pages, slides, and spreadsheet row windows become chunks with a citation pointer (`p.3`, `slide 4`, `Data!I11`, `t=23.5s`). Pages with no text layer or with a chart are read by Muse Spark (`api/vision.py`); each chunk records where its text came from.
- **Access** (`api/policy.py`, `api/auth.py`): personas come only from a signed token. The licensed report is company-wide; the full dataset is seat-limited to Analyst and Steward; the performance sheet is Manager and Steward only. Files are served only through `GET /files/{source_id}` after the same check.
- **Ask** (`api/agent.py`, `api/answer.py`): a model-driven loop with three tools that filter sources before reading. Documents are passed as data, and the prompt forbids following instructions inside them. The final answer is checked on the server. If the model fails, the answer is extractive and labeled degraded. `GET /runs/{id}/steps` shows the trace, filtered to what the viewer may see.
- **Conflicts** (`api/conflict.py`): candidate pairs come from full text search across sources (at most 30 per source), Muse Spark judges each one for factual contradictions, a Steward resolves them, and the losing side is marked stale.
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

All calls go through `api/meta_client.py`: retries on 429 and 5xx, a usage log with estimated spend, a spend stop (default $30), and a disk cache so a reseed never calls a model again. The whole build, including the spike, two eval runs and the demo video footage, logged about $4.04 of Meta API usage.

## Eval

Full results with every number and every failure: [docs/eval-result.md](docs/eval-result.md). Spike notes from the first live API runs: [docs/spike.md](docs/spike.md).

- 20 frozen questions across four roles: 19 of 20 passed in the final run (18 of 20 in the first run, where two checks were wrong and were then amended with the reason recorded).
- Leak test: 0 failures in 74 checks of every role against every tool and route.
- Conflicts: 2 of 3 planted conflicts caught, 0 of 3 control pairs flagged. One extra flag inside PostHog's own handbook (two pages describe open source sponsorship money differently).
- Video steps on the demo clip: 9 of 9 steps found, start time error median 0.22 s. SAM marks: 9 of 9 overlap the true control (IoU at least 0.5, median 0.93).
- Chart page read by Muse Spark: 10 of 10 values correct.

## Limitations

- The eval corpus is small and the conflict detection rules, mark rule and crop padding were tuned on it. These are not held-out results.
- Asks take about 20 to 40 seconds because each one makes three to five model calls.
- SAM marks are drawn as boxes in our runs. Meta's `meta-sam-parser` (listed in requirements) decodes masks, but it could not be installed in the build environment, so mask drawing is untested.
- The planted spend-limit conflict was missed; the judge read the deck's limit as scoped to one team.
- Login is a demo persona switch with signed tokens, not a real identity provider. License terms, vendor, seats and costs are simulated.
- The Docker image was written but not built in the build environment (base image registry rate limit, Debian mirrors blocked). It has not been deployed by us.
- Slides are shown as extracted text, not rendered slide images.

## Data and licenses

Company documents are ten pages of PostHog's public handbook (MIT-style license for `/contents`, text unchanged, notice kept in `corpus/handbook/LICENSE-posthog-contents.txt`). PostHog does not endorse Kohu. Purchased data is simulated with World Bank World Development Indicators (CC BY 4.0). The deck, performance sheet, refund process, back office app and its narrated clip (synthetic Kokoro TTS voice) are simulated and labeled. Details in [corpus/NOTICE.md](corpus/NOTICE.md). Our code is MIT ([LICENSE](LICENSE)).

## Deploy

The app is one container plus Postgres 16 with `pg_trgm`.

1. Build the image from `Dockerfile` (Python 3.12 slim with FFmpeg).
2. Set `DATABASE_URL`, `KOHU_ALLOW_REMOTE_DB=1` (the guard in `api/db.py` refuses non-local databases otherwise), a long random `KOHU_SESSION_SECRET`, and `META_API_KEY`.
3. Start once with `KOHU_SEED_ON_START=1` to load the corpus, then without it.
4. The container listens on `PORT` (default 8000) and serves the UI at `/`.

Uploaded videos are written to `corpus/uploads/` inside the container, so mount a volume there if uploads must survive restarts.

## Repo layout

| Path | Contents |
|---|---|
| `api/` | FastAPI app and modules listed above, migrations `0001` to `0009` |
| `ui/` | Single page UI (no framework) |
| `corpus/` | Public and simulated corpus, build scripts, manifest, model cache, demo app and clip |
| `eval/` | Frozen questions and conflict pairs, eval runner, raw results |
| `tests/` | Pytest suite (fixtures and live response samples, no network) |
| `docs/` | Spike notes, eval results, run report (Indonesian), submission draft |
| `video/` | Demo video package (script, captions, footage list) |
| `TICKETS.md` | The v2 work plan and status |

Which work was done when is recorded in [HACKATHON.md](HACKATHON.md).
