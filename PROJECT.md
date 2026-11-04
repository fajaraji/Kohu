# Kohu (Knowledge Hub) — Project Record

> Note (kohu-v2): this is the plan written before version 2. Kohu entered the **Indie Developer** track. Version 2 replaced parts of this plan (public corpus instead of the fictional one, model-driven agent, video guides with Muse Voice Transcribe and SAM 3.1, Postgres full text search). Current scope and status are in [TICKETS.md](TICKETS.md) and [README.md](README.md).

Status: Draft
Date: 2026-10-31
Event: Meta Global AI Developer Hackathon (Remote, Oct 26 12:00 PM – Nov 4 9:00 PM ET, 2026)

## Vision

Kohu is one place where anyone in a company can find what the company knows and what it has paid for. Internal documents, purchased data and reports are ingested as they are, including scanned PDFs, slides, and spreadsheets. Local parsers extract structure today; Muse Spark adds optional chart-slide captions when configured. Employees can search or ask questions. Role-based access, including data license coverage, controls what each person's results and answers can draw from. Every answer cites the page, cell, or slide it came from.

Full vision also includes screen recordings turned into step-by-step guides with reasons preserved, SAM marks on the exact button or field for each step, and an agent that flags conflicts between recordings and documents for owner review.

## Hackathon Rules Check (from Cerebral Valley pages, fetched 2026-10-31)

What was verified from the main event page:

- Build with Meta's newest models: Muse Spark series, Muse Wonder, Muse Image, and SAM 3.1 through Meta Model API. Open-weights models and Muse Code coding agent are also in scope.
- Two tracks: Indie developer (individuals and students, judged on creativity, technical ambition, and whether it works) and Startup (teams and founders, judged on technical execution and whether it holds up in production).
- Two themes: Build for Your World (domain problem you know firsthand) and Push the Frontier (new capability for software, robotics, manufacturing, energy, materials, and beyond).
- Key dates (2026): applications from Oct 13, deadline Oct 25 (or earlier at 20,000 acceptances), hackathon Oct 26 to Nov 4 9:00 PM ET, judging Nov 4–8, finals Nov 9.
- Applications are reviewed on project idea clarity, feasibility, theme fit, and demonstrated technical skill.
- Eligibility exclusions apply (sanctioned countries/regions, Meta and Cerebral Valley staff and families, government-affiliated individuals). Official Rules were stated as to be published before the hackathon begins and must be accepted by selected participants.

What was not verified:

- The waiver page (https://cerebralvalley.ai/e/meta-ai-developer-hackathon/waiver) renders as a JavaScript shell and returned no readable text via direct fetch. BrowserOS neo tools were not available in this session, so the waiver contents, Official Rules, submission requirements, judging rubric, and IP terms are still unresolved. Action: user should paste the waiver/Rules text or open it in a connected browser before final submission planning.

## Settled Decisions

### D1: Hackathon demo slice — Option A (Decided 2026-10-31)

Decision: demo cited search and Q&A over a mixed corpus of PDFs, slides, and spreadsheets, with role-based filtering and exact citations.

Deferred to follow-ons: recording-to-guide with SAM marks, conflict-flag agent, and full license-coverage model. Only a thin mention in the demo narrative, no implementation in the hackathon slice unless time allows.

Reason: this slice is the core promise of Kohu and can be shown end to end with Muse Spark in hackathon time.

## Compliance Notes for Slice A

- Model usage: slice A must call Muse Spark through the Meta Model API for document understanding and Q&A. This satisfies the core build-with-Meta-models requirement.
- SAM naming: project brief says SAM 3; event page says SAM 3.1. Use SAM 3.1 references in submission materials. Slice A does not depend on SAM, so this is documentation-only for now.
- Theme fit: Build for Your World. The team has seen this problem firsthand (knowledge trapped on laptops and in heads, licensed data going unused, time lost searching). Cite the Atlassian 2025 State of Teams figure in the submission story.
- Citations and access control are differentiators: every answer must show page, cell, or timestamp provenance, and role-based filtering must be demonstrable (e.g., two roles see different sources for the same query).
- Open items before build: exact submission deliverables (repo, demo video, hosted URL), model API keys and rate limits (Baseten, Modal, Fireworks credits), data handling rules from the waiver/Official Rules.

### D2: Track — Indie Developer (Revised 2026-11-03)

Decision: enter the Indie Developer track.

History: on 2026-10-31 the plan was the Startup track as a two-person team. The team later settled on the Indie Developer track; this record was updated to match.

### D3: Demo corpus — synthetic near-enterprise set (Decided 2026-10-31)

Decision: use a synthetic corpus of 6 to 8 files created for the demo. No user-provided company files.

Planned set: two PDFs with tables and charts, two slide decks, two spreadsheets including one marked as licensed-only, and one scanned PDF to prove the OCR path. All names, figures, and license labels are fictional and marked as demo data. The licensed-only spreadsheet exists to demonstrate role-based filtering.

### D4: Roles and access model — enterprise simulation (Decided 2026-10-31)

Decision: simulate four enterprise roles for the demo. All data is synthetic and labeled as demo data.

Roles:

1. Employee (All Staff): company handbook, internal process docs, general reports. No licensed market data. No confidential finance or legal files.
2. Licensed Analyst: everything Employee sees, plus the licensed market dataset spreadsheet and licensed report pages. This is the role that proves the "what we paid for" promise.
3. Manager: everything Employee sees, plus team performance summaries and approval docs. No licensed data unless also granted analyst rights. Used to show separation between management and licensed-data access.
4. Data Steward (Admin): all sources plus license metadata (vendor, coverage, expiry, seat scope). Only role that sees license terms and can preview restricted hits as redacted stubs.

Access rules for slice A:

- Ingest tags every chunk with source id, license class (open-internal, licensed, confidential), and citation pointer (page, cell range, slide number).
- Query time filters by role before retrieval. No post-hoc redaction of full text except Steward stubs.
- Same query must return visibly different answers: Employee gets internal-only answer with internal citations; Analyst gets the same plus licensed cells; Steward sees license labels.
- Denied sources never leak through snippets, citations, or reranking. Denial is silent except Steward view.

Near-real mappings: Employee maps to Entra ID / Google Workspace all-staff group; Analyst maps to license security group tied to vendor seat list; Manager maps to manager hierarchy claim; Steward maps to data-owner group. Demo will mock these as four login personas.

### D5: Stack — agentic RAG that clears the rules (Decided 2026-10-31)

Source: Participant Guide screenshots provided by user (6 pages, read 2026-10-31). Key rules applied:

- Must incorporate Meta models through Meta Model API: Muse Spark series, Muse Wonder, Muse Image, Muse Voice Transcribe, and SAM 3.1, plus open-weights Muse Glimmer and Muse Spark Open, and Muse Code.
- Repositories must be public. Team size maximum four. Solo allowed. Two-person team is allowed.
- Demo must only highlight features, code, and functionality built during the hackathon. New work only. Startups building on existing code must clearly mark what is new.
- Banned: anything violating legal, ethical, or platform policies, or using code, data, or assets without rights. Sample Anti-Projects list explicitly names Basic RAG Applications, simple image analyzers, AI for Education chatbots, job screeners, nutrition coaches, personality analyzers, sports analyzers, medical advice, and political or war topics.
- Submission: one project per team via CV platform by Nov 4 9:00 PM EST, public repo, accessible video link, all builders listed. Submission needs a three-minute demo video showing what was built during the hackathon. Judging is pass/fail on theme fit and Meta-model use, then Impact 30 percent, Use of Meta AI Tooling 25 percent, Technical Depth and Execution 20 percent, Demo 25 percent.
- Bonus target: Best Agentic Use-Case, $5,000. Rewards the project that makes the strongest use of AI agents to complete meaningful tasks, make decisions, or coordinate multi-step workflows.

Stack decision for Kohu slice A plus agentic layer:

- API and agents: Python FastAPI service. Local parsers extract tables, charts, scanned PDFs, slides, and sheets today; Muse Spark on the Meta Model API adds optional chart-slide captions at ingest and is the planned path for answer synthesis (current synthesis is extractive with a `synthesize()` seam). No closed-model fallback in the judged path.
- Agentic design (this is what keeps Kohu out of the Basic RAG anti-pattern and aims at Best Agentic Use-Case):
  1. Planner agent decomposes each question into subtasks per source type.
  2. Retrieval agents run per source type with role filter applied before retrieval.
  3. Policy agent enforces license class and role, blocks leaks through snippets and citations.
  4. Verifier agent checks every claim against its cited chunk and rejects uncited claims.
  5. Conflict-flag agent marks the one demo case where two sources disagree and routes it to the Steward queue.
- Data: Postgres chunks table with full text and trigram search plus citation fields (source id, page, cell range, slide number, license class). Embeddings are NULL today so retrieval is lexical term counting, not vector search. Synthetic seed files only, all marked as demo data.
- App: minimal web UI with four persona logins, side-by-side same-query comparison, and citation panel. Demo video shows the same query as Employee versus Licensed Analyst versus Steward.
- Open-weights path: document one local run with Muse Spark Open served through an inference partner for the Best Build on Meta Open Weight Models story only if time allows. Judged path stays on Meta Model API.
- Public repo from day one. Three-minute video shows only hackathon-built agents, UI, and corpus.

### D6: Representative and public repo (Decided 2026-10-31)

Decision: team Representative is alfianhid. Public repo is https://github.com/alfianhid/Kohu. Repo must be public from day one. One submission per team by the Representative via the CV platform by Nov 4 9:00 PM ET, with accessible video link and all builders listed.

### D7: WeKnora as architecture reference only (Decided 2026-10-31)

Source: https://github.com/Tencent/WeKnora (MIT, 36k stars). Tagline: open-source LLM knowledge platform that turns raw documents into queryable RAG, autonomous reasoning agent, and self-maintaining wiki. Three modes share the same knowledge bases: Quick Q&A with hybrid search, multimodal parsing, and source citations; smart-reasoning agent with multi-step planning, skills, sandboxes, browser use, MCP tools, and memory; wiki with knowledge graph and rollback. Relevant patterns: 10-plus format parsing including PDF, Word, images, Excel, and XMind; chunk edit, diff, and rollback; multi-workspace RBAC with four roles plus per-resource ownership and audit log; scoped API keys; 29 model vendors; built-in MCP server; swappable LLMs, vector databases, and storage.

Decision for Kohu: take inspiration from the patterns, write original hackathon code. Do not fork or copy WeKnora code into the judged path. Reasons: hackathon rules require new work only, the demo must only highlight features built during the hackathon, and the judged path must use Meta models through the Meta Model API with Muse Spark. Kohu keeps its own differentiators: license-coverage-aware role filtering applied before retrieval, exact page, cell, and slide citations with a verifier agent, and a conflict-flag agent for recording-versus-document disagreements.

### D8: Logseq as second reference for knowledge UX (Decided 2026-10-31)

Source: https://github.com/logseq/logseq (privacy-first, open-source knowledge management, Markdown and Org-mode, journals, blocks, graph, PDF annotation, tasks, queries, plugin API, local-first).

Decision for Kohu: borrow UX ideas only, write original code. Take blocks with block-level citations, journal-style ingest log, linked references between docs and licensed cells, and query-first navigation. Do not copy Logseq code or bundle Logseq. Reasons: same new-work rule as WeKnora, plus Kohu must stay a small judged slice with Meta models. Logseq ideas that lift the Best Agentic Use-Case story: agent writes back a curated page per answer with kept citations, conflict blocks surface as task items for the Steward, and every agent step lands in an inspectable run log.

### D9: Demo video via Hyperframes desktop app (Decided 2026-10-31)

Source: https://github.com/heygen-com/hyperframes (Apache 2.0, write HTML, render deterministic MP4, CLI plus agent skills, 450 blocks, Node 22 plus FFmpeg). Desktop app already installed on the user's laptop.

Decision: author the three-minute judging video as a Hyperframes project (HTML plus seekable animations, charts, captions), preview locally, render to MP4. Content follows the recommended arc in PLAN.md. No build starts until the user approves PLAN.md.

## Unresolved Questions
- [x] PLAN.md review approval before any build (Approved 2026-10-31. Waiting for user's first build prompt).
- [ ] CV platform submission link, video hosting choice, and second builder identity.
- [ ] Meta Model API credit claim per builder ($150 each, claim by Nov 4 9:00 PM ET) and inference partner credits if needed.
