# HACKATHON.md, new work record

Hackathon rule: the demo must only highlight features, code, and functionality built during the hackathon (Oct 26 to Nov 4, 2026 ET). Everything in this repository was created during that window. `git log` is the evidence: every commit is dated inside the window, and nothing was imported from an earlier codebase.

## Timeline

| Dates (commit time) | Who | What |
|---|---|---|
| 2026-10-31 | Alfian (`alfianhid`) | Plan, PRD, task checklist, research notes (`PLAN.md`, `PRD.md`, `PROJECT.md`, `TASK_CHECKLIST.md`, `MULTI_PHASE_PROMPTS.md`, `G01-meta-console-gate.md`) |
| 2026-11-02 to 2026-11-03 | Alfian | First MVP: FastAPI service, five-step pipeline, lexical search, synthetic fictional corpus, four-persona UI, seeded conflict, Spark synthesis with retry |
| 2026-11-04 (WIB) | Fajar (`fajaraji`) | World Bank ASEAN indicators CSV added as public corpus data |
| 2026-11-03 19:27 UTC onward | Fajar with Claude Code, on branch `kohu-v2` | Version 2, ticket by ticket (see `TICKETS.md` and the commit messages): everything listed below |

Writing code with Claude Code (an AI coding assistant) was allowed. Inside the app, every AI feature uses Meta models only.

## Built in version 2 (branch `kohu-v2`)

| Ticket | Paths | What |
|---|---|---|
| T0 | `api/db.py`, `seed.sh` | Refuse non-local databases unless opted in |
| U2 | `api/meta_client.py`, `api/sam_parse.py`, `tests/` | Meta API client (Responses, background polling, Files, ASR, SAM), retry, usage log, spend stop, cache; SAM output parser |
| U1 | `api/spike.py`, `docs/spike.md`, `docs/spike-results.json` | Live API spike and decisions |
| A1 | `corpus/demo-app/` | Simulated back office app, Playwright recording, Kokoro TTS narration (synthetic, labeled), ground truth |
| D1 | `corpus/build_handbook.py`, `corpus/build_public_data.py`, `corpus/handbook/`, `corpus/licensed/`, `corpus/internal/`, `corpus/manifest.json`, `corpus/NOTICE.md`, `corpus/verify_corpus.py`, `api/ingest.py`, `api/corpus.py` | Public corpus replacing the fictional one: PostHog handbook pages, World Bank based licensed report and dataset, simulated deck, performance sheet and refund process |
| L1 | `api/policy.py` | Company-wide licensed report, seat-limited dataset |
| B1 | `api/auth.py`, `api/app.py` | Signed persona tokens, guarded file route, no static corpus mount |
| A2 | `api/migrations/0004_video.sql`, `api/retrieval.py`, `api/verifier.py`, `ui/app.js` | Video second citations |
| B2 | `api/vision.py` | Muse Spark reads scanned and chart pages |
| B3 | `api/migrations/0005_search.sql`, `api/retrieval.py` | Postgres full text and trigram search; pgvector removed |
| B4, B5 | `api/agent.py`, `api/answer.py`, `api/migrations/0006_agent_runs.sql` | Model-driven tool loop and server-checked final answer; old planner and verifier logic removed |
| A3, A4, A5 | `api/video.py`, `api/marks.py` | Video to reviewed guide steps with SAM marks |
| B6, B7 | `api/conflict.py`, `api/migrations/0007_conflicts.sql`, `eval/conflicts.json` | Spark-judged conflicts, Steward decisions, stale ranking |
| B8 | `api/licenses.py`, `api/migrations/0008_license_usage.sql` | License usage log and cards |
| A7 | `api/regions.py`, `api/migrations/0009_page_regions.sql` | SAM on PDF charts and tables |
| C1, A6 | `ui/` | New UI |
| C2 | `Dockerfile`, `docker-compose.yml`, `docker-entrypoint.sh`, `.env.example` | Deploy files |
| C3 | `eval/`, `docs/eval-result.md` | Frozen questions, eval runner, results as measured |
| C4 | `README.md`, this file, doc fixes | Docs |
| C5 | `video/` | Demo video package |
| R1 | `docs/run-report.md` | Run report |

## Third-party material

| Source | How it is used | License |
|---|---|---|
| PostHog handbook (`PostHog/posthog.com`, `contents/handbook`) | Ten pages rendered to PDF as company documents, text unchanged | MIT-style license for `/contents`, notice kept. PostHog does not endorse Kohu |
| World Bank World Development Indicators | ASEAN data behind the simulated licensed report and dataset | CC BY 4.0 |
| Kokoro TTS (`kokoro-onnx`, Kokoro v1.0 model) | Build-time narration voice for the demo clip only, not part of the app | Apache 2.0 |
| `meta-sam-parser` (Meta) | Optional runtime dependency that decodes SAM masks | SAM License |
| Playwright, pandoc, FFmpeg, PyMuPDF and the Python packages in `api/requirements.txt` | Build and runtime tools | Their own licenses |

Reference-inspired, no copied code: WeKnora (architecture ideas), Logseq (UX ideas), Hyperframes (video tool, renderer only). No source from these projects is in this repository.
