# Kohu Task Checklist — v2 (Best Agentic Use-Case sprint)

> Note (kohu-v2): this is the plan written before version 2. Kohu entered the **Indie Developer** track. Version 2 replaced parts of this plan (public corpus instead of the fictional one, model-driven agent, video guides with Muse Voice Transcribe and SAM 3.1, Postgres full text search). Current scope and status are in [TICKETS.md](TICKETS.md) and [README.md](README.md).

Status: Audited rewrite, 2026-11-01. Check off only when the done bar is met, with evidence (command output, screenshot, or link).
Owners: A is backend/agents, B is frontend/video, Shared is either. Sprint: 2 builders, 1 week. Days refer to MULTI_PHASE_PROMPTS.md.
Excluded: Muse Spark Open. (Muse Voice Transcribe was excluded here; version 2 uses it.)
Audit baseline (live-verified 2026-11-01): corpus 61 chunks, persona matrix 5/7/6/8 sources, policy leakage probe PASS, conflict exactly-once PASS. Items already meeting their bar are checked with that evidence noted.

## Phase 0 — Gates and hygiene (Day 1, Shared)

- [x] G01 Meta console gate (P00): Spark endpoint/model/image format, Wonder model/endpoint, SAM 3.1 hosted availability/model/endpoint/schema/limits each recorded or marked UNVERIFIED. Done: written gate note exists; no invented endpoint or model id anywhere in code or docs. Evidence: [G01-meta-console-gate.md](G01-meta-console-gate.md) (2026-11-01, official dev.meta.ai docs + BrowserOS Neo authenticated console: Dashboard/Models/API keys/Usage/Segment playground read, Wonder 1,048,576 verified, SAM pixel cap = none published (50 MB + 16-object caps bind), live GET /v1/models = 9 ids; no UNVERIFIED flags remain; api/*.py env-gated only, *.md grep clean).
- [x] G02 Credits claimed by both builders ($150 each, before Nov 4 9:00 PM ET), spend limit set. Done: both confirm in chat. Evidence: both builders confirm claimed in chat (2026-11-02).
- [x] G03 Built code committed and pushed (P01): `api/`, `corpus/`, `ui/`, `seed.sh`, `video/` in the public repo. Done: fresh clone shows built code, not docs only. Evidence: pushed 765bb64 (built code) + 4726bd7 (doc fixes) + b3c9eab (HACKATHON note) to main; clean clone to %TEMP%\kohu-fresh contains api/corpus/ui/video/seed.sh, and `./seed.sh` exits 0 with per-source counts 12/9/10/8/10/6/5/1 = 61 chunks.
- [x] G04 Stale docs fixed (P01): README year/status, PROJECT judging dates, false "Spark parses all" and pgvector claims removed or made true. Done: grep finds no claim the code cannot back. Evidence: README 2026 ET + built status; PROJECT dates carry 2026; Spark = optional captions (extractive synthesis seam), pgvector column present with embeddings NULL / lexical retrieval; fresh-clone grep for false Spark-parse, pre-build/(planned, and vector/hybrid-search claims returns only honest negatives and the WeKnora-reference row.
- [x] G05 Public repo hygiene on paper: README, LICENSE, `.gitignore`, `HACKATHON.md` marking new work. Evidence: files present; public visibility still to confirm at S03.

## Phase 1 — Synthetic corpus (A) — audited complete

- [x] T10 8-file manifest with license classes, citation anchors, conflict pair. Evidence: `corpus/verify_manifest.py` PASS, 8 entries, `conflict-01`.
- [x] T11 2 PDFs with tables and charts. Evidence: `verify_pdfs.py` PASS; tables p.4/p.7, charts p.3/p.6.
- [x] T12 2 decks (10-slide product, sales with conflict figure on slide 7). Evidence: `verify_decks.py` PASS, slide numbers stable.
- [x] T13 2 sheets (licensed `Q3-Growth!A1:F200` with `E12=7.1`, performance summary). Evidence: `verify_sheets.py` PASS. Note (resolved 2026-11-01): wrong "D12" comments fixed to E12 in `build_sheets.py` and `build_decks.py`; `verify_sheets.py` PASS confirms E12==7.1.
- [x] T14 Scanned PDF ingest path. Evidence: chunk text lands from `scanned-note-ocr.txt` sidecar. Caveat: this is a sidecar fallback, not vision reading — true Spark vision read is task V03.
- [x] T15 Every file stamped `DEMO DATA — FICTIONAL`. Evidence: verify scripts confirm marker in all 8 files.

## Phase 2 — Data layer (A)

- [x] T20 Postgres schema applies clean (pgvector later removed in kohu-v2 B3). Evidence: migrations 0001–0003 applied in live probes.
- [ ] T21 Ingest honestly labelled: local parsers for structure, Spark only where it actually runs. Done: ingest log and docs state per-file-type what Spark touched; zero `[Spark]` captions in DB is explained (re-run or silent-failure root cause found), not ignored.
- [x] T22 License tags immutable at query time; retrieval pre-filter before search. Evidence: policy `--probe` PASS, smuggled chunks dropped, no leak.
- [x] T23 Fresh-clone seed reproducibility (P01). Done: clone to a clean directory, `./seed.sh`, counts = 61 chunks, no manual steps. Evidence: clean clone to %TEMP%\kohu-fresh, `./seed.sh` via Git Bash exits 0, per-source 12/9/10/8/10/6/5/1 = 61 chunks (2026-11-01; DB URL from environment since `.env` is git-ignored).

## Phase 3 — Agentic loop (A) — the Best Agentic core

- [x] A01 Relevance gate (P10): score-0 chunks never become claims; no-answer state reachable. Done: gibberish query returns 0 claims + no-answer message; Q3 query unaffected. Evidence: `MIN_RELEVANCE_SCORE=1` in `api/retrieval.py`, enforced in `api/app.py` (claims) with a self-filter in `conflict.flag_conflict`; `api/app.py --probe` PASS; live `/ask` gibberish = 200 + 0 claims + exact no-answer message + no conflict, Q3 = 5 claims + `conflict-01` fired with exactly 1 task row across repeat asks; policy/conflict/verifier/planner probes still PASS (2026-11-02).
- [x] A02 Spark synthesis in ask path (P11): Spark drafts claims at the `synthesize()` seam, env-gated, degraded mode labelled in trace. Done: live ask answer is Spark-synthesized prose, not numbered excerpts, when Spark is on. Evidence: `SparkSynthesizer` in `api/app.py` (env-gated on META_API_KEY/META_API_BASE/META_PARSE_MODEL, Responses-style, same pattern as `SparkEnricher`); live analyst ask with Spark on returns `synthesis=spark` prose paragraph with inline cites (8 claims, `degraded=False`); Spark failure degrades to extractive with `degraded=True` in run step 4 (2026-11-02).
- [x] A03 Verifier-retry loop (P11): dropped claim triggers re-retrieval, max 2 rounds, each logged. Done: forced-drop query shows dropped > 0, round 2 in `run_steps`, final claims all cited. Evidence: `KOHU_FORCE_UNSUPPORTED_CLAIM=1` analyst ask shows `dropped_count=1`, `rounds=2`, steps 0-4 + 5-7 (second `retrieval` round), final claims all resolve via `resolve_citation`; baseline (unforced) stays single-round steps 0-4; `api/app.py --probe` still PASS (2026-11-02).
- [ ] A04 Muse Wonder supervisor (P30, after A02): persona-aware planning, logged re-plans (max 2) on drops, empty evidence, or zero SAM regions. Done: forced-drop query logs one REPLAN event with revised subtasks; canned rationale removed or marked template.
- [x] A05 Conflict exactly-once (existing): seeded pair creates one Steward task. Evidence: live repeat asks, DB count = 1, `conflict-01` open.
- [x] A06 Conflict only on cited evidence (P10): flagging receives cited chunks only, and side B cites `E12`, not the containing window. Done: unrelated Analyst query fires no conflict; Q3 query cites `Q3-Growth!E12`. Evidence: `api/app.py --probe` PASS — gibberish + unrelated Analyst queries fire no conflict, Q3 Analyst cites side A `slide 7` + side B `Q3-Growth!E12` (claim text contains 7.1) and flags `conflict-01` exactly once; `conflict.py --probe` PASS (pinpoint + exactly-once), `verifier.py --probe` PASS (single-cell E12 resolves to its window and is preserved, E999 dropped); anchored chunks are pinned deterministically when both seeded sides are relevant, and `flag_conflict` receives only verified cited chunks (2026-11-02).
- [x] A07 Tokens + structured errors (P12): per-step token counts persisted; `/ask` returns 503 JSON on DB-down, never raw 500; migrations not re-run per request. Done: `api/verify_a07.py` PASS in one test pass (2026-11-03) — 422 JSON on bad persona/empty query, 503 JSON on unreachable DB, steps 0-4 carry int input/output_tokens, Spark-backed run logged real API usage (calls=2), two asks issued zero migration runs. Spark pinpoint follow-up (2026-11-03): Spark drafting now receives the pinned draft citations/anchored text and missing draft citations are supplemented, so side B cites `E12`, never the `A2:F21` window; `api/verify_spark_pin.py` PASS and `api/app.py --probe` PASS twice with Spark on.

## Phase 4 — SAM 3.1 visual citations (A+B, Day 4; gated on G01)

- [ ] V01 Page rendering + `0004_visual_regions.sql` (P20): PDF pages rendered 150–200 dpi, regions table added, chunk total stays 61. Done: migration applies; page PNGs exist for chart/table pages.
- [ ] V02 SAM segmentation + Spark crop-read (P21): prompts `bar chart / line chart / data table / figure`; crop +10% pad read by Spark; verifier requires region-caption support. Client uses only G01-verified endpoint/model/schema. Done: regions stored with `region_source='sam'` where SAM actually ran.
- [ ] V03 True vision read for scanned PDF: Spark reads the scanned page image; sidecar becomes fallback only. Done: scanned chunk text originates from a Spark image read, logged as such.
- [ ] V04 Honest fallbacks: zero SAM regions → `fallback-text` path, ingest never blocks; deck boxes from shape geometry labelled `pptx-shape`, never SAM; self-hosted SAM (if G01 says no hosted API) labelled checkpoint everywhere. Done: fallback runs produce labelled regions and no SAM claim in UI or docs.
- [ ] V05 Ground-truth test `corpus/verify_sam.py` + `sam_gt.json`: IoU ≥ 0.5 on ≥ 3/4 positives (process-report p.3/p.6, handbook p.4/p.7, sales slide 7), 0 false positives on negatives (scanned-note p.1, handbook p.1), crop captions contain ground-truth values (slide 7 = 9.4). Done: script prints PASS with SAM env set; prints UNVERIFIED and exits 0 when unset.

## Phase 5 — API and security (A)

- [ ] S01 Persona auth (P40): persona derived from server-checked demo token; self-asserted persona field rejected or ignored. Done: request with forged persona does not change source set.
- [ ] S02 Corpus gating (P40): no unauthenticated static mount of licensed files. Done: unauthenticated `licensed-market.xlsx` download returns 401/403; Employee 403 on licensed; Steward 200.
- [x] S03 Ask persona matrix (existing): same query, four payloads differ correctly, no leakage in text/snippet/citation. Evidence: live `/ask` matrix 5/7/6/8 sources, 2026-11-01. Re-verified after A01 (2026-11-02): cited-source matrix is now Employee 3 / Analyst 5 / Manager 4 / Steward 6 (score-0 filler no longer cited), four payloads differ correctly, Employee/Manager contain no licensed source, Steward shows 3 stubs, conflict fires for Analyst/Steward only — `api/app.py --probe` S03 checks PASS plus HTTP `/ask` check PASS. Still to re-verify after S01 (persona auth).
- [ ] S04 Steward resolve API (P41): POST confirm-A / confirm-B / dismiss records resolution in trace; repeat ask does not resurrect a resolved task. Done: API test passes for all three actions.

## Phase 6 — UI (B)

- [x] U01 Four logins and ask box (existing). Done bar was: login swaps persona token. Caveat: token is display-only today — becomes real under S01.
- [ ] U02 Agent trace timeline (P50): `GET /runs/{id}/steps` rendered as animated timeline, drops and re-plans highlighted. Done: one ask renders plan → retrieve → policy → verify → conflict in order.
- [ ] U03 Answer de-dupe + encoding (P51): no `???` bytes; one prose answer with inline citation chips; answer ≠ claim list. Done: grep clean, chips open correct citations.
- [ ] U04 SAM mask overlay (P22): region citations show page image + bbox overlay (`mask-overlay`); non-region citations show no overlay. Done: process-report p.3 claim highlights its chart box.
- [ ] U05 Four-persona comparison (P53): Manager and Steward columns added; sources/stubs/dropped diffed. Done: 4 columns on Q3 query, Steward stubs visible, Employee column licensed-free.
- [ ] U06 Steward queue actions (P41): Confirm A / Confirm B / Dismiss in UI, queue updates in place. Done: resolving `conflict-01` on screen closes the loop live.
- [x] U07 Citation panel page/cell/slide (existing): claim click lands on page iframe or locator card. Caveat: slide/cell show a text locator only until V01/V04 rendering lands.
- [ ] U08 States, tokens, mobile (P52): `:root` tokens, `:focus-visible`, disabled + spinner + single-submit guard, retry, 16px input, wrapped topbar/ask-row, persona badge instead of raw token. Done: real-browser check at 320/375/414/768 px — no overflow, visible focus, double-click sends one request. (CSS inference does not count.)

## Phase 7 — Retrieval depth (A, stretch)

- [x] R01 Embeddings decision (P54): resolved in kohu-v2 B3, pgvector removed, search is Postgres full text plus pg_trgm. No middle state. Done: 61/61 non-null + paraphrase win, or zero pgvector claims in docs/schema.

## Phase 8 — Video and submission (B + Shared)

- [ ] D01 Hyperframes project (P60): 180 s arc — problem, product, live agentic run with trace + SAM overlay, conflict + resolve, stack, close; includes one live terminal segment. Done: preview plays end to end ≤ 180 s.
- [ ] D02 Render (P61): captions on, music low, MP4 < 3:00, only hackathon-built work shown. Done: file plays, runtime checked.
- [ ] D03 Rehearsal: fixed query × 4 personas × 2 runs against PRD AC1–AC13, both logged here. Done: two clean passes recorded with date and builder initials.
- [ ] D04 Submission package (P70): public repo confirmed in a private window, accessible video link, all builders listed, Representative submits once via CV platform before Nov 4 9:00 PM EST. Done: confirmation recorded.
- [ ] D05 Freeze (P71): after D02, bug fixes only, each re-verified against AC1–AC13. Done: post-freeze git log shows fixes only.
