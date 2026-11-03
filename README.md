# Kohu — Company Knowledge Hub

Kohu is one place where anyone in a company can find what the company knows and what it has paid for. Internal documents, purchased data, and reports are ingested as they are, including scanned PDFs, slides, and spreadsheets. Local parsers extract structure today; Muse Spark adds optional chart-slide captions when `META_API_KEY`, `META_API_BASE`, and `META_PARSE_MODEL` are set (live DB shows zero `[Spark]` captions without a key). Employees search or ask questions. Role-based access, including data license coverage, controls what each person's results and answers can draw from. Every answer cites the page, cell, or slide it came from.

Built for the Meta Global AI Developer Hackathon (Remote, Oct 26 – Nov 4, 2026 ET), Startup track, theme Build for Your World.

- Representative: `alfianhid`
- Public repo: <https://github.com/alfianhid/Kohu>
- Status: built. Fresh clone plus `./seed.sh` reproduces the demo (61 chunks). See [PROJECT.md](PROJECT.md), [PLAN.md](PLAN.md), [PRD.md](PRD.md), [TASK_CHECKLIST.md](TASK_CHECKLIST.md), [HACKATHON.md](HACKATHON.md).

## Hackathon slice (what the demo proves)

Cited search and Q&A over a synthetic corpus of 6–8 files (PDFs, slides, spreadsheets, one scanned PDF), with role-based filtering and exact citations.

- Ingest of PDFs, slides, and spreadsheets as they are via local parsers; Muse Spark adds optional chart-slide captions on the Meta Model API when configured.
- Five agents per query: planner, per-source retrieval with role pre-filter, policy enforcer, citation verifier, conflict flagger.
- Four mocked personas: Employee, Licensed Analyst, Manager, Data Steward (Admin). Same query returns visibly different cited answers per role.
- Seeded conflict: sales deck vs. licensed sheet Q3 figure flags exactly once into the Steward queue.
- Three-minute Hyperframes video shows only hackathon-built work.

Deferred to follow-ons: recording-to-guide with SAM marks, full license-management backend, production hardening. See [PROJECT.md](PROJECT.md) D1.

## Repo layout

| Path | Contents |
|---|---|
| `api/` | FastAPI service, Postgres schema with full text and trigram search |
| `ui/` | Minimal web UI: four logins, ask box, comparison, citation panel (built) |
| `corpus/` | 8 synthetic demo files + `manifest.json`, all stamped `DEMO DATA — FICTIONAL` (built, 61 chunks) |
| `video/` | Hyperframes project source (HTML scenes, 180 s timeline) + rendered MP4 (source scaffold built; render excluded via `.gitignore`) |
| `seed.sh` | Fresh-clone seed: corpus, migrations, ingest, counts (built; prints 61 chunks) |

Which files are hackathon-built vs. reference-inspired is recorded in [HACKATHON.md](HACKATHON.md). No WeKnora or Logseq code is copied or vendored.

## Quickstart (built; verified via fresh clone + `./seed.sh`)

```sh
cp .env.example .env   # set META_API_KEY (never commit it)
./seed.sh              # build corpus, migrate, ingest, print counts
uvicorn api.main:app --reload
```

Fresh clone plus `./seed.sh` reproduces the demo (61 chunks). Answer synthesis is extractive today with a `synthesize()` seam for a future Muse Spark call; ingest Spark captions are env-gated and off without a key. No closed-model fallback in the judged path. Retrieval is Postgres full text search with pg_trgm similarity; there is no vector search.

## Roles (simulated, all data synthetic)

| Persona | Sees | Never sees |
|---|---|---|
| Employee | Handbook, process docs, general reports | Licensed data, manager-restricted |
| Licensed Analyst | Employee set + licensed sheet and licensed report | Manager-restricted |
| Manager | Employee set + performance summary | Licensed data |
| Steward | All + license metadata (vendor, coverage, expiry) and redacted stubs | Nothing hidden |

Denial is silent except Steward stubs. Denied sources never leak through snippets, citations, or reranking.

## Compliance

- New work only: demo highlights only features built during the hackathon.
- Rights clean: synthetic corpus only, no company files.
- SAM references use `SAM 3.1` in submission materials.
- One submission per team by the Representative via the CV platform by Nov 4 9:00 PM ET.
