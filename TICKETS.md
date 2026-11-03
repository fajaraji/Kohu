# Kohu v2 tickets

Branch `kohu-v2`. One commit per ticket, pushed after each. Order: foundation, then A and B (A2 before B3 and B5), then finish. Status is updated in this file as tickets land. Anything never run against the real Meta API is marked UNVERIFIED in `docs/run-report.md`.

Status key: `todo`, `done`, `done (UNVERIFIED: ...)`, `cut`.

## Foundation

| ID | Ticket | Done when | Status |
|---|---|---|---|
| T0 | Ticket list and safety guard | `TICKETS.md` exists; every DB entry point refuses a non-local `DATABASE_URL` unless `KOHU_ALLOW_REMOTE_DB=1` | done |
| U1 | API spike, results in `docs/spike.md` | Transcription, Files API video with timed steps, SAM on 5 app screenshots (phrase and box prompt), SAM on 3 PDF charts or tables, Python mask parser, each with a measured result or a recorded failure. Decisions for video timing and SAM on UI written down | done (live API, see docs/spike.md) |
| U2 | `api/meta_client.py` | Responses (sync and background with polling), Files, ASR, SAM calls; retry on 429 and 5xx; usage log with estimated spend; $30 stop; disk cache; recorded fixture replay for tests. `SparkEnricher` and `SparkSynthesizer` use it. Env `META_API_KEY`, `META_API_BASE`, `META_PARSE_MODEL` | done (verified live through U1 calls) |
| D1 | Public corpus | PostHog handbook pages (MIT notice kept, one scanned page), World Bank licensed report PDF and seat-limited XLSX, simulated performance sheet, simulated slide deck with a figure that differs from the World Bank data, demo app process PDF. `manifest.json`, `verify_*`, `seed.sh`, probes and `NOTICE.md` updated. `.gitignore` allows the corpus demo clip | done |
| L1 | License coverage | Licensed report visible to all personas, XLSX to Analyst and Steward only. `LICENSE_REGISTRY`, probes and manifest checks updated. Employee gets an answer from the report with a page citation and never sees the XLSX | done |

## Track A, video

| ID | Ticket | Done when | Status |
|---|---|---|---|
| A1 | Demo back office app, process PDF, demo clip | `corpus/demo-app/` small web app; process PDF with one planted difference from the video; 1 to 2 minute English clip recorded with Playwright and narrated with a synthetic voice labeled synthetic | todo |
| A2 | Migration `0004_video.sql` and time citations | `chunks.t_start`; tables `transcripts` and `guide_steps`; pointer form `t=42.5s` accepted by `retrieval.citation_for`, `verifier._parse_pointer`, `verifier.resolve_citation` and `parsePointer` in `ui/app.js`; `timestamp` anchor in manifest; uploads recorded in git-ignored `corpus/manifest.local.json` merged on read | done (migration landed with D1) |
| A3 | `api/video.py` pipeline | FFmpeg to WAV, ASR, transcript stored, video uploaded, Spark in background mode with step schema, polling, time validation, `reason` null unless spoken. `POST /videos`, `GET /videos/{id}/status`, `GET /videos/{id}/steps` | done (live) |
| A4 | SAM marking per step | Frame per step, phrase prompt then box prompt, mask as transparent PNG, `mark_status` one of `phrase`, `box`, `spark_box`, `failed`; SAM failure never fails the guide | done (live; masks drawn as SAM boxes here because meta-sam-parser could not be installed in this sandbox) |
| A5 | Review screen | Edit text, shift time, approve. Approved steps become chunks of instruction, reason and transcript excerpt with `t_start` | backend done; screen in C1 |
| A6 | Video citation panel | Citation plays `<video>` at the second and shows the frame and mask, through the B1 file route | todo |
| A7 | SAM on PDF charts and tables | Page render, SAM phrase mark, crop, Spark reads crop, citation shows the marked area. Mandatory if SAM fails on UI elements | todo |

## Track B, ask, conflicts, license

| ID | Ticket | Done when | Status |
|---|---|---|---|
| B1 | File route and signed persona token | `/corpus` static mount removed; `GET /files/{source_id}?token=` checks persona; `POST /login {persona}` returns HMAC token from `KOHU_SESSION_SECRET`; `/ask` and Steward routes read persona from the token. Employee gets 403 on the XLSX | done |
| B2 | Spark page reading | Pages with no text layer and chart pages read by Spark one page at a time, cached in `corpus/spark-cache/`, text origin logged. OCR sidecar kept only as a labeled fallback | done (live: scanned page and chart page read by Spark, cached) |
| B3 | Full text search | Migration adds `tsv`, GIN index, `pg_trgm`; drops embedding column and every pgvector claim. Retrieval uses `ts_rank` and `similarity` filtered by `source_id = ANY(visible)`. Threshold recalibrated | done |
| B4 | `api/agent.py` | Model driven loop, max 4 steps, tools `search_knowledge`, `read_section`, `read_cells`. Persona only from token, tools filter before reading, document text wrapped as data. `GET /runs/{id}/steps` shows only sources the persona may see. Template planner removed. Model failure falls back to extractive path labeled `degraded` | done (live) |
| B5 | Checked final answer | Final call without tools, schema `{answer_type, text, citations[{marker, source_id, pointer}]}`. Server rejects markers not returned by tools in this run and sentences whose numbers are not in the cited chunk. Not found answers never hint at restricted sources | done (live) |
| B6 | Conflict detection | `api/conflict.py` finds candidates across sources after ingest or video approval (max 30 pairs per source), Spark judges with schema, factual contradictions only, `conflict_id` is a hash of the chunk pair. `eval/conflicts.json` with 3 conflicts and 3 controls. Fixed manifest pair removed | todo |
| B7 | Steward decision | `POST /conflicts/{id}/resolve {winner or dismiss, note}`, Steward only. Losing source marked `stale` and ranked lower. Open conflicts show both versions with a warning, only to users who may see both sources | todo |
| B8 | License usage | `source_access_log` written when a licensed source is cited. `GET /licenses` and a card with vendor, coverage, distinct users in 30 days. Seeded baseline labeled sample data | todo |

## Finish

| ID | Ticket | Done when | Status |
|---|---|---|---|
| C1 | Demo UI | No `???` characters, citation chips, step trace, Steward decision buttons, four persona comparison | todo |
| C2 | Deploy readiness | `Dockerfile` with FFmpeg; README deploy section. No deploy, no Cloudflare credential used | todo |
| C3 | Eval | 20 frozen questions in `eval/questions.json`; leak test for all personas and tools; conflict catches and false alarms; step time error; mask percentage; `docs/eval-result.md` as measured | todo |
| C4 | Repo docs | Startup to Indie, Voice Transcribe exclusion removed, run command fixed, `.env.example`, false video scaffold claim removed, `HACKATHON.md` lists new work. README sections: problem, try it in 60 seconds, architecture, Meta models, eval, limitations | todo |
| C5 | Demo video package | `video/` script, captions, real product footage where possible, Hyperframes only for opening and transitions. Rendered if tools allow. Not submitted | todo |
| R1 | Run report | `docs/run-report.md` in Indonesian: verified, UNVERIFIED, failures, spend, how to run, next steps | todo |

## Cut order if time runs short

A7 unless mandatory, then B3, then the text edit part of A5, then live video upload in production, then SAM masks become boxes, then B4 becomes one round of model decisions. Never cut: SAM use, cited Q&A, role and license access, conflict through to the changed answer, one citable video, honest eval.

## Standing decisions

- The Meta API host was denied at the start of the run (proxy 403). The user then attached the key as a network secret, and from U1 on every model path is run against the live API. Paths that were never run live are marked UNVERIFIED in the report.
- No model output is ever invented. When the model is unreachable, a feature either uses a labeled non model fallback (for example `extractive`, `rule-fallback`, `authored-script`) or reports that it did not run.
