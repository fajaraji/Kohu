# HACKATHON.md — New Work Record

Hackathon rule: the demo must only highlight features, code, and functionality built during the hackathon. This file lists exactly which paths are hackathon-built and which outside sources inspired the design. No outside code is copied into this repo.

## Hackathon-built (original code, docs, and data by this team)

| Path | What it is |
|---|---|
| `README.md` | Project overview, slice, roles, layout (this hackathon) |
| `LICENSE` | MIT terms for our code (this hackathon) |
| `.gitignore` | Python / Node / Postgres data / Hyperframes render ignores (this hackathon) |
| `HACKATHON.md` | This record (this hackathon) |
| `PROJECT.md` | Decisions D1–D9, compliance notes (this hackathon) |
| `PLAN.md` | Build plan and video arc (this hackathon) |
| `PRD.md` | Slice requirements FR1–FR8, acceptance AC1–AC7 (this hackathon) |
| `TASK_CHECKLIST.md` | Phased tasks T01–T72 (this hackathon) |
| `MULTI_PHASE_PROMPTS.md` | Copy-paste build order P00–P71 (this hackathon) |
| `api/` | FastAPI service, five agents, Postgres schema with full text and trigram search, ingest, POST /ask (built P20-P40) |
| `ui/` | Four-login web UI, comparison, citation panel, Steward queue (built shell) |
| `corpus/` | 8 synthetic demo files + `manifest.json`, all fictional (built, 61 chunks) |
| `video/` source | Hyperframes HTML scenes, 180-second timeline (scaffold built; render output excluded via `.gitignore`) |
| `seed.sh` | Fresh-clone seed script (built; prints 61 chunks) |

## Reference-inspired (ideas only, zero copied code)

| Source | What we took | What we did not take |
|---|---|---|
| WeKnora (<https://github.com/Tencent/WeKnora>, MIT) | Architecture patterns: multimodal parse (local-only today; Spark captions optional), per-resource RBAC, run tracing, wiki-style chunk diff — not hybrid retrieval (retrieval is lexical, embeddings NULL) | No fork, no vendored files, no copied modules. Judged path uses Meta Model API with Muse Spark, not WeKnora's model wiring. |
| Logseq (<https://github.com/logseq/logseq>) | UX ideas: block-level citations, journal-style ingest/run log, linked references, conflict blocks as tasks | No copied code, no bundled build. UI is original. |
| Hyperframes (<https://github.com/heygen-com/hyperframes>, Apache 2.0) | Tool use: author video as HTML scenes, render deterministic MP4 via CLI or desktop app | Renderer only. No Hyperframes source copied into this repo. Rendered `*.mp4` files are git-ignored. |

Verification: `git log` history and per-file authorship show the above paths as team-written during the hackathon window. A reviewer can confirm no third-party code by checking that no `api/`, `ui/`, `corpus/`, or `video/` source file matches WeKnora, Logseq, or Hyperframes sources.
