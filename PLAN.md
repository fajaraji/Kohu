# Kohu Build Plan — For Review Before Build

> Note (kohu-v2): this is the plan written before version 2. Kohu entered the **Indie Developer** track. Version 2 replaced parts of this plan (public corpus instead of the fictional one, model-driven agent, video guides with Muse Voice Transcribe and SAM 3.1, Postgres full text search). Current scope and status are in [TICKETS.md](TICKETS.md) and [README.md](README.md).

Status: Draft for review. No build starts until the user approves this file in chat.

## 1. Goal

Ship an Indie Developer track hackathon slice that proves one promise: anyone in a company can find what the company knows and what it has paid for, with role-based access and exact citations.

Demo proves: ingest of PDFs, slides, and spreadsheets as they are, including one scanned PDF and charts and tables, through local parsers with optional Muse Spark captions on the Meta Model API; five agents that plan, retrieve, enforce policy, verify citations, and flag conflicts; four persona logins with visibly different answers to the same query; three-minute Hyperframes video showing only hackathon-built work.

## 2. Non-goals for the hackathon slice

No screen-recording to guide, no SAM 3.1 button marking, no full license-management backend, no production hardening, no copied WeKnora or Logseq code. Recording and SAM stay in the narrative as follow-ons. Open-weights local run is stretch only.

## 3. Architecture

```
UI (4 personas) -> FastAPI -> Planner -> Retrieval x3 -> Policy -> Verifier -> Answer
                                              |-> Conflict flag -> Steward queue
Data: Postgres chunks table with full text (tsvector) and pg_trgm search, chunk = text + source id + license class + citation pointer
Models: Meta Model API, local parsers for parse with optional Muse Spark captions; extractive synthesis with a Spark seam. No closed fallback in judged path.
```

Agents and why each exists for Best Agentic Use-Case:

1. Planner breaks each question into subtasks by source type and decides which stores to hit.
2. Retrieval agents run per source type with the role filter applied before search, so denied sources never enter ranking.
3. Policy agent enforces license class and role, blocks leaks through snippets and citations, and shapes Steward redacted stubs.
4. Verifier rejects any claim without a supporting chunk and attaches page, cell, or slide numbers.
5. Conflict agent marks the one seeded disagreement and routes a task block to the Steward.

Run log: every agent step, tool call, token use, and citation decision is inspectable. This is the Logseq-inspired journal plus WeKnora-inspired tracing, built original.

## 4. Synthetic corpus (8 files, all fictional, all marked demo data)

1. Employee handbook PDF with tables (open-internal).
2. Process report PDF with charts (open-internal).
3. Product slide deck, 10 slides (open-internal).
4. Sales review deck with embedded chart (open-internal).
5. Licensed market dataset spreadsheet with cell ranges A1:F200 (licensed-only).
6. Licensed report pages PDF quoting that dataset (licensed-only).
7. Team performance summary spreadsheet (manager-restricted).
8. Scanned one-page PDF to prove OCR path (open-internal).

Seeded conflict: the sales deck states one Q3 figure, the licensed sheet states a different Q3 figure. Conflict agent must flag it once and never invent a resolution.

## 5. Roles and expected demo behavior

Same query asked four times: "What was Q3 growth for product X and what drives it?"

- Employee sees internal handbook plus process report answer with page citations, no licensed numbers.
- Licensed Analyst sees the same plus licensed cells with cell-range citations.
- Manager sees internal plus performance summary, no licensed numbers.
- Steward sees all plus license labels (vendor, coverage, expiry) and the conflict task block.

## 6. Work split for two builders

Builder A: FastAPI, agents, Postgres schema with full text search, ingest of 8 files, Muse Spark wiring.
Builder B: UI with four logins and side-by-side comparison, citation panel, Hyperframes video project, repo hygiene and submission page.

Shared: daily merge to main, public repo from day one, clear marking of hackathon-built files for the new-work rule.

## 7. Hyperframes three-minute video arc

User has the Hyperframes desktop app installed. Author as HTML scenes, preview, render to MP4. Do not screen-record the build environment as the judged artifact; the MP4 is the artifact.

- 0:00-0:20: problem. Knowledge on laptops and in heads, licensed data going unused, quarter of time lost searching.
- 0:20-0:50: what Kohu is. Ingest as they are, role filters, exact citations.
- 0:50-1:40: live agentic run. Same query as Employee versus Analyst versus Steward. Show planner, policy, verifier steps in run log. Show citations to page and cell.
- 1:40-2:20: conflict flag. Deck versus sheet disagree, Steward queue task appears.
- 2:20-2:50: stack. Optional Muse Spark captions via Meta Model API, FastAPI, Postgres full text search (no embeddings NULL, retrieval lexical), public repo. Name what was built during the hackathon.
- 2:50-3:00: close. Build for Your World, Indie Developer track, repo URL.

Requirements: Node 22 and FFmpeg for CLI render, or render from the desktop app. Keep captions on. Keep music low. Video must only highlight hackathon-built features and code.

## 8. Rule compliance checklist

- Meta models via Meta Model API with Muse Spark: yes, only judged path.
- SAM naming uses 3.1 in submission: yes.
- Public repo: https://github.com/alfianhid/Kohu, Representative alfianhid.
- Team size two inside maximum four: yes.
- New work only, demo shows only hackathon work: enforced by file marking.
- Rights clean: synthetic corpus only.
- Anti-project dodge: not a basic RAG demo; five coordinating agents plus policy and verifier carry the Best Agentic Use-Case claim.
- Submission: one entry by Representative, public repo link, accessible video link, all builders listed, due Nov 4 9:00 PM ET.

## 9. Risks

- Basic RAG label if agents look thin. Mitigation: run log must show planning, policy, and verification decisions, not just retrieval.
- Credits late. Mitigation: each builder claims the $150 Meta Model API credit immediately; set spend limit.
- Scope creep into recording and SAM. Mitigation: those stay as one closing slide, no code.
- Video overrun past three minutes. Mitigation: timed script above, Hyperframes timeline locked to 180 seconds.

## 10. Validation

- Same query returns different cited answers per role, with zero licensed leakage outside Analyst and Steward.
- Every claim in every answer opens to its page, cell, or slide.
- Conflict case flags exactly once and creates one Steward task.
- Fresh clone plus seed script reproduces the demo.
- Rubric covered: Impact 30, Meta use 25, Depth 20, Demo 25.

## 11. Review gate

Reply with approval or changes. No code, corpus files, or video project start until you say go.
