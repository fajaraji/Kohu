# Kohu Multi-Phase Prompts — Copy-Paste Build Order v2

> Note (kohu-v2): this is the plan written before version 2. Kohu entered the **Indie Developer** track. Version 2 replaced parts of this plan (public corpus instead of the fictional one, model-driven agent, video guides with Muse Voice Transcribe and SAM 3.1, Postgres full text search). Current scope and status are in [TICKETS.md](TICKETS.md) and [README.md](README.md).

Also check/cross [TASK_CHECKLIST.md](TASK_CHECKLIST.md) after the task is done. 
Status: Audited rewrite, 2026-11-01. Run in order. Each prompt is one small-medium task. Stop after each verify step and report the result before the next prompt.
Owners: A = backend/agents, B = frontend/video. Target: Best Agentic Use-Case, Indie Developer track. Rubric: Impact 30, Meta Tooling 25, Technical Depth 20, Demo 25.
Excluded: Muse Spark Open. (Muse Voice Transcribe was excluded in this plan; version 2 uses it for video guides.)
Already built and live-verified (do not rebuild): 8-file corpus (61 chunks), role pre-filter, policy stubs, exactly-once conflict, four-persona UI shell. Prompts below close the audited gaps only.

## Phase 0 — Gates and hygiene (Day 1, Shared)

P00 Meta console gate (no code): "Verify in the Meta Model API console and report, without inventing any value: (1) Muse Spark endpoint, model id, and multimodal image-input format; (2) Muse Wonder model id and endpoint; (3) SAM 3.1 hosted availability — model id, endpoint, auth, image encoding, bbox/mask response schema, size and rate limits. The official SAM blog confirms checkpoints and Playground only, so hosted availability is unproven until you see it. Verify: a written gate note with each value or an explicit UNVERIFIED flag. If hosted SAM is absent, record the fallback: self-host the SAM 3.1 checkpoint and label it as checkpoint, never as Meta Model API."

P01 Commit and docs truth (B): "Commit and push api/, corpus/, ui/, seed.sh, video/ so a fresh clone contains the built code, then fix stale judge-visible docs: README year and pre-build status, PROJECT judging dates, and every claim that Muse Spark parses all files or that pgvector search works (embeddings are NULL today). Verify: fresh clone + ./seed.sh reaches 61 chunks, and grep finds no doc claim the code cannot back."

P02 Credits (Shared, human) — [x] DONE 2026-11-02: "Both builders claim the $150 Meta Model API credit individually before Nov 4 9:00 PM ET and set a spend limit. Verify: both confirm claimed in chat. No code."

## Phase 1 — Make the ask path agentic (Days 1–2, A)

P10 Relevance gate: "In api/retrieval.py and api/app.py, add a calibrated minimum relevance score so score-0 chunks never become claims, make the no-answer branch reachable, and pass only cited chunks to conflict flagging in api/conflict.py. Verify: gibberish query returns zero claims, the explicit no-answer message, and no conflict; the fixed Q3 query still flags conflict-01 exactly once."

P11 Spark synthesis + verifier-retry loop: "Wire Muse Spark into the synthesize() seam in api/app.py (pattern: SparkEnricher in api/ingest.py, env-gated on META_API_KEY/META_API_BASE/META_PARSE_MODEL): Spark drafts claims from retrieved chunks, the verifier drops unsupported claims, and a drop triggers re-retrieval with a revised query, max 2 rounds, each round logged in run_steps. On Spark failure, degrade to the current extractive path and mark the run degraded in the trace. Verify: a query with a forced unsupported claim shows dropped > 0, a second retrieval round in run_steps, and a final answer whose claims all resolve to chunks."

P12 Structured errors + tokens: "Add try/except around POST /ask returning structured JSON errors (503 on DB-down, 422 on bad input), persist per-step token counts in run_steps, and stop re-running migrations on every request module call. Verify: DB stopped returns 503 JSON not a raw 500; a Spark-backed run shows non-null token counts."

## Phase 2 — SAM 3.1 visual citations (Day 4, A+B; gated on P00)

P20 Render + regions schema: "Add pymupdf and Pillow to api/requirements.txt, render PDF pages at 150–200 dpi to corpus/pages/{source}/p{N}.png during ingest, and add migration 0004_visual_regions.sql (chunk_id, page, slide, prompt, bbox JSONB normalized 0–1, mask_rle, score, crop_path, spark_caption, region_source). Keep chunk counts at 61. Decks: if LibreOffice is unavailable, derive boxes from python-pptx shape geometry and label region_source='pptx-shape' — never label it SAM. Verify: migration applies, rendered pages exist for process-report and handbook, chunk total still 61."

P21 SAM segment + Spark crop-read: "For each chart/table-bearing page, call SAM 3.1 with text prompts 'bar chart', 'line chart', 'data table', 'figure' (client built only from P00-verified endpoint/model/schema; env-gated SAM_API_BASE/SAM_MODEL, unset means skip cleanly). Crop each returned box with 10% padding, read the crop with Muse Spark, store caption on the region and append it to the chunk. Extend the verifier: a claim citing a region chunk also requires the region caption to support it. Zero SAM regions on a chart page must fall back to today's text path with region_source='fallback-text' and never block ingest. Verify: corpus/verify_sam.py against hand-labelled corpus/sam_gt.json — IoU >= 0.5 on at least 3 of 4 positives (process-report p.3, p.6; handbook p.4, p.7; sales slide 7 chart), zero false positives on scanned-note p.1 and handbook p.1, and each positive crop caption contains its ground-truth value (slide 7 = 9.4)."

P22 Mask overlay UI (B): "In ui/app.js citation panel, replace the PDF iframe with the rendered page image plus an absolutely positioned bbox overlay (data-testid='mask-overlay') for region citations; clicking a claim highlights its region. Slide and cell citations keep the locator card until deck rendering lands. Verify: clicking the process-report p.3 claim shows the chart box over the page image; a non-region citation shows no overlay."

## Phase 3 — Wonder supervisor (Day 5, A; after P11)

P30 Supervisor re-planner: "Add a Muse Wonder supervisor at the planner seam in api/planner.py (model id and endpoint only as verified in P00): it receives the query, persona, and verifier outcome, and issues a logged re-plan (max 2) when dropped_count > 0, when retrieval returns no cited evidence, or when SAM finds zero regions on a chart-bearing page. Plans become persona-aware; remove canned rationale text or mark it as template. Verify: a forced-drop query logs exactly one REPLAN event in run_steps and the trace shows the revised subtasks; re-plan count never exceeds 2."

## Phase 4 — Security and steward loop (Day 3, A+B)

P40 Persona auth + corpus gating: "Remove or gate the unauthenticated /corpus static mount in api/app.py; derive persona from a server-checked demo token (Authorization header the server actually validates), return 401/403 for unauthenticated or under-privileged file access, and update ui/app.js to stop displaying the raw token. Verify: unauthenticated download of licensed-market.xlsx returns 401/403, Employee token gets 403 on licensed files, Steward gets 200; the four-persona ask matrix still returns 5/7/6/8 sources with no leakage."

P41 Steward resolve loop: "Add POST resolve/dismiss for conflict tasks in api/app.py + api/conflict.py and Confirm A / Confirm B / Dismiss actions in the ui/app.js Steward queue, recording the resolution as a trace step. Verify: resolving conflict-01 in the UI sets status resolved, the queue updates without reload of other panels, and a repeat ask does not resurrect it."

## Phase 5 — Trace and UI completion (Days 2–5, B)

P50 Trace API + timeline: "Add GET /runs/{id}/steps in api/app.py returning ordered run_steps (plan, re-plans, retrieval counts, policy decisions, verifier drops, SAM regions, tokens), and render an animated step timeline under the Ask panel in ui/index.html, ui/app.js, ui/styles.css with dropped claims highlighted. Verify: after one ask, the timeline renders all steps in order and a dropped claim from P11 is visibly marked."

P51 Answer de-dupe + encoding: "Fix the literal '???' mojibake in ui/index.html, replace the duplicated <pre> answer + claim list with one synthesized prose answer carrying inline citation chips that open the citation panel. Verify: no '???' bytes remain (grep), answer text differs from the claim list, every chip opens the correct page/cell/slide/region."

P52 States, tokens, mobile: "Add a :root design-token block (color, space, radius, font) in ui/styles.css, :focus-visible rings, hover/active/disabled states with spinner and single-submit guard on ask/compare, retry on errors, 16px input text, wrapping topbar and ask-row, and a persona badge instead of the raw token. Verify in a real browser at 320/375/414/768 px: no horizontal overflow, visible keyboard focus, double-click sends one request."

P53 Four-persona compare: "Extend the comparison view beyond Employee vs Analyst to Manager and Steward, diffing sources, stubs, and dropped counts per persona. Verify: four columns render for the fixed Q3 query, Steward column shows stubs, Employee column contains no licensed source ids or values."

P54 Embeddings decision (A): "Either populate chunk embeddings and add hybrid vector + lexical retrieval in api/retrieval.py, or remove the pgvector claim from docs and schema comments. No middle state. Verify: embeddings non-null 61/61 and a paraphrase query retrieves the licensed chunk the lexical path misses — or grep shows no pgvector claim left."

## Phase 6 — Video (Day 7, B)

P60 Hyperframes scenes: "Scaffold video/ as a Hyperframes project on the PLAN.md 180-second arc: problem, product, live agentic run (Employee vs Analyst vs Steward with trace timeline and SAM overlay), conflict + Steward resolve, stack, close. Include one genuinely live terminal run segment so judges can tell the system is not canned playback. Captions on, music low. Verify: preview plays end to end at <= 180 s and every on-screen claim maps to a shipped feature."

P61 Render + rehearsal: "Render the MP4 under 3:00, then run the fixed demo query as all four personas twice against PRD AC1–AC13 and log both passes in TASK_CHECKLIST.md. Verify: runtime passes, two clean rehearsal logs, T60–T62 checked."

## Phase 7 — Submission (Day 7, Shared)

P70 Package: "Confirm public repo visibility, accessible video link, all builders listed, one submission by the Representative (alfianhid) via the CV platform before Nov 4 9:00 PM EST. Verify: links open in a private window; submission checklist in TASK_CHECKLIST.md Phase 8 fully checked."

P71 Freeze rule: "After P61, no feature changes — bug fixes only, each re-verified against AC1–AC13. Verify: git log after freeze shows fixes only."
