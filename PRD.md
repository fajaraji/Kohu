# Kohu PRD — Hackathon Slice v2 (Best Agentic Use-Case)

> Note (kohu-v2): this is the plan written before version 2. Kohu entered the **Indie Developer** track. Version 2 replaced parts of this plan (public corpus instead of the fictional one, model-driven agent, video guides with Muse Voice Transcribe and SAM 3.1, Postgres full text search). Current scope and status are in [TICKETS.md](TICKETS.md) and [README.md](README.md).

Status: Audited rewrite, 2026-11-01. Sources: full codebase + UI/UX audit, Details + Waiver PDFs (OCR, 11 pages), PROJECT.md D1–D9, PLAN.md.
Supersedes v1 where they conflict. Owners: A = backend/agents, B = frontend/video. Team: 2 builders, 1 week.
Excluded models: Muse Spark Open is out of scope. (Muse Voice Transcribe was excluded in this version of the PRD; version 2 uses it for video guides.)

## 1. Problem

Company knowledge sits on laptops and in heads. Licensed data bought for the whole company goes unused. Teams lose search time and cannot prove where an answer came from.
Kohu makes one searchable hub: ingest files as they are, filter by role and license before retrieval, answer with exact citations, and escalate source conflicts to a human Steward.

Winning claim for Best Agentic Use-Case ($5,000, Details p.6): agents complete meaningful tasks, make decisions, and coordinate multi-step workflows — visibly, in the live run trace. A fixed retrieval pipeline does not meet this bar.

## 2. Users and roles

Four mocked personas. Mappings are illustrative, not real IdP wiring. Persona must come from a server-checked token, never from a self-asserted request field (fixes audit B1).

| Persona | Sees | Never sees |
|---|---|---|
| Employee | Handbook, process docs, general reports | Licensed data, manager-restricted |
| Licensed Analyst | Employee set plus licensed sheet and licensed report | Manager-restricted |
| Manager | Employee set plus performance summary | Licensed data |
| Steward | All plus license metadata, redacted stubs, conflict queue | Nothing hidden |

## 3. Current state (audited, live-verified)

Working today: 8-file synthetic corpus, 61 chunks, role pre-filter in retrieval, policy re-check with Steward stubs, citation pointers (page / cell range / slide), exactly-once conflict task, persona matrix Employee 5 / Analyst 7 / Manager 6 / Steward 8 sources with no leakage in `/ask` payloads.

Not working today (do not claim in pitch or docs):
- No Meta model call in the ask path. `api/app.py` synthesis is extractive; claims are chunk excerpts.
- Muse Spark runs only as optional chart-slide captions at ingest; live DB shows zero `[Spark]` captions.
- Embeddings are NULL (61/61); retrieval is lexical term counting with no relevance threshold.
- No SAM code anywhere. Citations have no bounding box or visual region.
- Agent trace is stored (`run_steps`) but never exposed or shown in UI.
- `/corpus` static mount serves licensed files without auth; persona is self-asserted.
- No demo video. Built code is uncommitted; a fresh clone gets docs only.

## 4. Functional requirements

FR1 Ingest 8 synthetic files as they are: 2 PDFs with tables and charts, 2 decks, 2 sheets including 1 licensed-only, 1 scanned PDF, 1 manager-restricted sheet. Local parsers extract structure; Muse Spark on the Meta Model API reads charts, tables, and scanned content. Never claim Spark parses a file type it did not touch.

FR2 Chunk model: text plus source id, license class (open-internal, licensed, manager-restricted), citation pointer (page, cell range, slide number), and — for chart/table/figure chunks — a visual region (normalized bbox, optional mask, crop path, Spark crop caption, region source). License class set at ingest, immutable at query.

FR3 Agentic query loop (replaces fixed pipeline claim): Muse Wonder supervisor plans per query and per persona, dispatches per-source Spark workers, checks verifier results, and re-plans up to 2 times when claims drop or evidence is missing. Planner, retrieval, policy, verifier, and conflict steps emit trace events. Fixed-order execution without a model decision does not count as an agent.

FR4 Ask endpoint returns a synthesized prose answer plus claims. Each claim links to one chunk or visual region. Unverified claims are dropped, never shown. A dropped claim triggers the FR3 re-plan loop before the answer is final.

FR5 Relevance gate: chunks below a calibrated minimum score never become claims. An irrelevant or empty query returns an explicit no-answer state, not best-effort claims from every allowed source.

FR6 Same query per persona returns visibly different answers. Denied sources never leak via answer text, snippet, citation, or SAM crop. Steward sees license labels and stubs.

FR7 Seeded conflict (sales deck slide 7 = 9.4% vs licensed sheet `Q3-Growth!E12` = 7.1%) flags exactly once, only when both sides are actually cited for the query, and creates one Steward task. Agent never invents a resolution. Steward can Confirm A, Confirm B, or Dismiss; the resolution is recorded in the trace.

FR8 Run trace per query: supervisor plan and re-plans, per-source subtasks, retrieval sets, policy decisions, verifier passes and drops, SAM regions used, token counts. Exposed via `GET /runs/{id}/steps` and inspectable as an animated timeline in UI.

FR9 SAM 3.1 visual citations: render PDF pages (and deck slides where a renderer exists) to images, segment chart/table/figure regions with SAM 3.1, crop each region, and read the crop with Muse Spark. SAM locates; Spark reads — SAM output alone is never presented as text evidence. Every region records its source honestly: `sam`, `pptx-shape`, or `fallback-text`.

FR10 UI: four persona logins, ask box, synthesized answer with inline citation chips, agent trace timeline, four-persona comparison, citation panel that opens to page / cell / slide / SAM region overlay, Steward queue with resolve actions.

FR11 Security baseline for the demo: corpus files are served only through persona-gated routes; no unauthenticated static mount of licensed files; structured JSON errors (no raw 500s); token usage persisted per run.

## 5. Meta API usage (judged path only, all via Meta Model API)

- Muse Spark: document and crop reading, chart/table captions, answer synthesis, per-source worker reasoning.
- Muse Wonder: supervisor planning and re-planning (FR3). One model, one job: coordination decisions.
- SAM 3.1: chart/table/figure segmentation for visual citations (FR9).
- Muse Image: stretch only, demo assets outside the judged path. Cut first under time pressure.
- No closed-model fallback in the judged path. If a Meta call fails, degrade to the local extractive path and label it in the trace; never silently present it as a model answer.

Gate: before building FR9/FR3 clients, verify in the Meta Model API console: SAM 3.1 hosted availability, exact model ids, endpoints, image-input format, bbox/mask response schema, and limits. The official SAM blog confirms checkpoints and Playground only. If hosted SAM is unavailable, self-host the SAM 3.1 checkpoint and label it as such everywhere. Never present a `pptx-shape` box or a self-hosted checkpoint as Meta Model API SAM.

## 6. Non-functional requirements

Public repo from day one; built code committed and pushed (fixes audit gap: fresh clone must reproduce the demo via `seed.sh` to 61 chunks). All demo data synthetic and stamped `DEMO DATA — FICTIONAL` (Waiver p.3: submission materials are not confidential and carry a broad license to organizers — never use real company data). Three-minute video shows only hackathon-built work, including one live (not pre-rendered) run segment.

## 7. Out of scope

Muse Spark Open, full license-management backend, production IdP, multi-tenant hosting. One closing video slide may name follow-ons; do not claim SAM marks until FR9 ships.

## 8. Acceptance criteria

AC1 Employee answer cites only internal pages. AC2 Analyst answer adds licensed cells. AC3 Manager answer adds performance summary, no licensed cells. AC4 Steward sees license labels, stubs, and conflict task. AC5 Zero leakage in any denied view — including direct file URLs (unauthenticated licensed download returns 401/403). AC6 Conflict flags exactly once and only on cited evidence. AC7 Every claim opens to its page, cell, slide, or SAM region. AC8 Gibberish query returns the no-answer state with zero claims. AC9 Verifier drop triggers a logged re-plan (max 2) before the final answer. AC10 Trace endpoint returns all steps in order and the UI timeline renders them. AC11 SAM ground-truth test: IoU ≥ 0.5 on at least 3 of 4 positive regions (process-report p.3, p.6; handbook p.4, p.7 or sales slide 7), zero false positives on negatives, each crop caption contains the ground-truth value. AC12 Fresh clone + `seed.sh` reproduces 61 chunks; docs match code. AC13 Rubric covered: Impact 30, Meta use 25, Depth 20, Demo 25; Best Agentic narrative shows plan → retrieve → verify → re-plan → escalate → human resolve in one live run.
