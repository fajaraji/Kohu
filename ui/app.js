"use strict";

// Kohu demo UI. Login is a demo persona switch: POST /login returns a
// signed token, and every request sends it. The server reads the persona
// from the token only, so nothing here can widen access.

const PERSONAS = ["employee", "analyst", "manager", "steward"];
const LABELS = { employee: "Employee (new hire)", analyst: "Analyst", manager: "Manager", steward: "Steward" };
const SAMPLES = [
  "How do I process a customer refund?",
  "What was Viet Nam's GDP growth in 2023?",
  "How much can I spend per month without asking?",
  "Which country grew fastest in 2024?",
  "Who missed their Q3 target?",
  "How many days off can I take?",
];
const tokens = {};
let persona = null;
let config = { public_demo: false, uploads: true, step_editing: true };

function visitorId() {
  let v = null;
  try { v = localStorage.getItem("kohu_visitor"); } catch (e) { /* ignore */ }
  if (!/^[a-f0-9]{16}$/.test(v || "")) {
    v = Array.from(crypto.getRandomValues(new Uint8Array(8)), (b) => b.toString(16).padStart(2, "0")).join("");
    try { localStorage.setItem("kohu_visitor", v); } catch (e) { /* ignore */ }
  }
  return v;
}
let videoSteps = [];

// ------------------------------------------------------------- helpers

function el(tag, attrs, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") n.className = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) {
    if (kid === null || kid === undefined || kid === false) continue;
    n.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return n;
}

async function tokenFor(p) {
  if (tokens[p]) return tokens[p];
  const res = await fetch("/login", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ persona: p, user: "demo-" + p, visitor: visitorId() }) });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "login failed");
  tokens[p] = data.token;
  return data.token;
}

async function api(path, opts = {}, as = persona) {
  const t = await tokenFor(as);
  const headers = Object.assign({ Authorization: "Bearer " + t }, opts.headers || {});
  if (opts.json !== undefined) {
    headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(opts.json);
  }
  const res = await fetch(path, Object.assign({}, opts, { headers }));
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || ("HTTP " + res.status));
  return data;
}

function fileUrl(sourceId, suffix = "") {
  return "/files/" + encodeURIComponent(sourceId) + suffix + "?token=" + encodeURIComponent(tokens[persona]);
}

function shortTitle(title, sourceId) {
  if (!title) return sourceId;
  return title.replace(/^PostHog handbook: /, "Handbook: ").replace(/ \(.*\)$/, "");
}

function parsePointer(pointer) {
  let m = /^p\.(\d+)$/.exec(pointer);
  if (m) return { kind: "page", value: Number(m[1]), label: "page " + m[1] };
  m = /^slide (\d+)$/.exec(pointer);
  if (m) return { kind: "slide", value: Number(m[1]), label: "slide " + m[1] };
  m = /^t=(\d+(?:\.\d+)?)s$/.exec(pointer);
  if (m) return { kind: "time", value: Number(m[1]), label: fmtTime(Number(m[1])) };
  m = /^(.+)!([A-Z]+\d+(?::[A-Z]+\d+)?)$/.exec(pointer);
  if (m) return { kind: "cell", value: m[2], sheet: m[1], label: m[1] + "!" + m[2] };
  return { kind: "unknown", value: pointer, label: pointer };
}

function fmtTime(s) {
  const m = Math.floor(s / 60), r = (s - m * 60).toFixed(1).padStart(4, "0");
  return m + ":" + r;
}

function chip(c, onClick) {
  const loc = parsePointer(c.pointer);
  return el("button", { type: "button", class: "chip" + (c.license ? " lic" : "") + (c.stale ? " stale" : ""),
    title: (c.title || c.source_id) + ", " + loc.label + (c.stale ? " (superseded by a Steward decision)" : ""),
    onclick: () => onClick(c) },
    (loc.kind === "time" ? "▶ " : "") + shortTitle(c.title, c.source_id) + ", " + loc.label);
}

// ---------------------------------------------------------------- login

async function login(p) {
  persona = p;
  try { localStorage.setItem("kohu_persona", p); } catch (e) { /* ignore */ }
  document.querySelectorAll(".persona").forEach((b) => b.classList.toggle("active", b.dataset.persona === p));
  await tokenFor(p);
  document.getElementById("answer").hidden = true;
  closePanel();
  refreshConflictCount();
  const tab = document.querySelector(".tabs .active").dataset.tab;
  showTab(tab);
}

// ------------------------------------------------------------------ ask

function renderText(text, citations, onChip) {
  const byMarker = Object.fromEntries(citations.map((c) => [c.marker, c]));
  const out = el("p", { class: "answer-text" });
  for (const part of text.split(/(\[S\d+\])/)) {
    const m = /^\[(S\d+)\]$/.exec(part);
    if (m && byMarker[m[1]]) out.append(chip(byMarker[m[1]], onChip));
    else if (!m) out.append(part);
  }
  return out;
}

function sideCard(side, cls) {
  const c = { source_id: side.source_id, pointer: side.pointer, title: side.title, license: side.license, excerpt: side.text, quote: side.quote };
  return el("div", { class: "side " + (cls || "") },
    el("div", { class: "src" }, shortTitle(side.title, side.source_id)),
    chip(c, openCitation),
    side.quote ? el("q", {}, side.quote) : null);
}

function conflictBox(c) {
  if (c.status === "resolved") {
    const win = c["side_" + c.winner];
    return el("div", { class: "conflict-box resolved" },
      el("h4", {}, "Steward decided: " + shortTitle(win.title, win.source_id) + " is right"),
      el("div", {}, c.note || ""),
      el("div", { class: "sides" }, sideCard(c.side_a, c.winner === "a" ? "winner" : "loser"),
        sideCard(c.side_b, c.winner === "b" ? "winner" : "loser")));
  }
  return el("div", { class: "conflict-box" },
    el("h4", {}, "⚠ Two sources disagree. A Steward has not decided yet."),
    el("div", {}, c.summary),
    el("div", { class: "sides" }, sideCard(c.side_a), sideCard(c.side_b)));
}

function traceBox(runId, as) {
  const box = el("details", { class: "trace" }, el("summary", {}, "Show how Kohu found this"));
  box.addEventListener("toggle", async () => {
    if (!box.open || box.dataset.loaded) return;
    box.dataset.loaded = "1";
    try {
      const data = await api("/runs/" + runId + "/steps", {}, as);
      const ol = el("ol");
      for (const s of data.steps) {
        const d = s.detail;
        if (s.kind === "model") {
          ol.append(el("li", {}, "Muse Spark step " + d.step + (d.seconds ? " (" + d.seconds + " s)" : "") + ": ",
            d.tool_calls.length ? d.tool_calls.map((t) => t.name).join(", ") : "done searching"));
        } else if (s.kind === "tool") {
          const args = d.args.terms ? "“" + d.args.terms + "”" : JSON.stringify(d.args);
          ol.append(el("li", {}, el("code", {}, d.tool), " ", args, " → ",
            d.results.length ? d.results.map((r) => r.marker + " " + shortTitle(r.title, r.source_id) + " " + r.pointer).join("; ") : "nothing"));
        } else if (s.kind === "answer") {
          ol.append(el("li", {}, "Final answer call, no tools" + (d.seconds ? " (" + d.seconds + " s)" : "") + ". Server check kept " + d.kept_citations.length +
            " citation(s)" + (d.dropped.length ? ", dropped " + d.dropped.length + " (" + [...new Set(d.dropped.map((x) => x.reason))].join(", ") + ")" : "")));
        } else if (s.kind === "fallback") {
          ol.append(el("li", {}, "Model unavailable (" + d.reason + "), extractive fallback"));
        } else if (s.kind === "result") {
          ol.append(el("li", {}, "Result: " + d.answer_type + ", " + d.usage.input_tokens + " input and " + d.usage.output_tokens + " output tokens"));
        }
      }
      box.append(ol);
    } catch (e) { box.append(el("p", { class: "hint" }, "Trace failed: " + e.message)); }
  });
  return box;
}

function renderAnswer(r, target, as) {
  target.replaceChildren();
  const card = el("div", { class: "card" });
  const badges = el("div", {},
    r.answer_type === "conflict" ? el("span", { class: "badge warn" }, "sources disagree") : null,
    r.degraded ? el("span", { class: "badge grey", title: "Muse Spark was not available; this is the best matching passage" }, "degraded: extractive answer") : null,
    r.answer_type === "not_found" ? el("span", { class: "badge grey" }, "no cited answer") : null);
  card.append(badges, renderText(r.text, r.citations, openCitation));
  if (r.licensed && r.licensed.length) {
    for (const l of r.licensed) {
      card.append(el("div", { class: "licensed-note" },
        "🔒 This answer uses licensed data your company paid for: ", el("b", {}, l.product), ". ",
        l.coverage + ". Vendor " + l.vendor + ". (License terms are simulated.)"));
    }
  }
  for (const c of r.conflicts || []) card.append(conflictBox(c));
  card.append(traceBox(r.run_id, as));
  card.append(el("div", { class: "meta" }, "Asked as " + LABELS[r.persona] + " · " +
    (r.synthesis === "spark" ? "Muse Spark" : "extractive") + " · run " + r.run_id.slice(0, 8)));
  target.append(card);
  target.hidden = false;
}

async function ask(q) {
  const status = document.getElementById("status");
  const btn = document.querySelector("#ask-form button");
  q = (q || "").trim();
  if (!q) return;
  document.getElementById("query").value = q;
  btn.disabled = true;
  status.textContent = "Muse Spark is searching the sources your role can see…";
  const t0 = performance.now();
  const runId = Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) => b.toString(16).padStart(2, "0")).join("");
  const live = el("ol", { class: "live" });
  status.after(live);
  let polling = true;
  const poll = async () => {
    await new Promise((r) => setTimeout(r, 1500));
    while (polling) {
      try {
        const data = await api("/runs/" + runId + "/steps");
        if (polling) live.replaceChildren(...data.steps.map((s) => el("li", {}, progressLine(s))));
      } catch (e) { /* run not started yet */ }
      await new Promise((r) => setTimeout(r, 1200));
    }
  };
  poll();
  try {
    const r = await api("/ask", { method: "POST", json: { query: q, run_id: runId } });
    renderAnswer(r, document.getElementById("answer"), persona);
    status.textContent = "Answered in " + ((performance.now() - t0) / 1000).toFixed(1) + " s.";
    refreshConflictCount();
  } catch (e) {
    status.textContent = "Ask failed: " + e.message;
  } finally { polling = false; live.remove(); btn.disabled = false; }
}

function progressLine(s) {
  const d = s.detail;
  if (s.kind === "model") return "Muse Spark step " + d.step + ": " + (d.tool_calls.length ? d.tool_calls.map((t) => t.name.replace("_", " ")).join(", ") : "has enough evidence");
  if (s.kind === "tool") return "\u2192 " + d.tool.replace("_", " ") + (d.args.terms ? " \u201C" + d.args.terms + "\u201D" : "") + ": " + d.results.length + " result(s)";
  if (s.kind === "answer") return "Writing the answer and checking every citation";
  if (s.kind === "fallback") return "Model unavailable, using the best matching passage";
  return "Done";
}

// ------------------------------------------------------------- compare

async function compare(q) {
  const wrap = document.getElementById("compare");
  wrap.replaceChildren(...PERSONAS.map((p) => el("div", { class: "card", id: "cmp-" + p },
    el("h3", {}, LABELS[p]), el("p", { class: "hint" }, "Asking…"))));
  await Promise.all(PERSONAS.map(async (p) => {
    const box = document.getElementById("cmp-" + p);
    try {
      const r = await api("/ask", { method: "POST", json: { query: q } }, p);
      const body = el("div");
      renderAnswer(r, body, p);
      const srcs = [...new Set(r.citations.map((c) => shortTitle(c.title, c.source_id)))];
      box.replaceChildren(el("h3", {}, LABELS[p]), body,
        el("div", { class: "meta" }, "Cited: " + (srcs.join(", ") || "none")));
    } catch (e) { box.replaceChildren(el("h3", {}, LABELS[p]), el("p", {}, "Failed: " + e.message)); }
  }));
}

// -------------------------------------------------------------- citation

function closePanel() {
  const panel = document.getElementById("panel");
  panel.hidden = true;
  document.getElementById("panel-body").replaceChildren();
}

async function openCitation(c) {
  const loc = parsePointer(c.pointer);
  document.getElementById("panel-title").textContent = c.title || c.source_id;
  document.getElementById("panel-pointer").textContent = loc.label + (c.stale ? " · superseded by a Steward decision" : "") +
    (c.license ? " · licensed data (" + c.license.coverage.split(":")[0].toLowerCase() + ")" : "");
  const body = document.getElementById("panel-body");
  body.replaceChildren(el("p", { class: "hint" }, "Loading…"));
  document.getElementById("panel").hidden = false;
  try {
    if (loc.kind === "page") {
      const kids = [];
      try {
        const mk = await api("/regions/" + encodeURIComponent(c.source_id) + "/" + loc.value);
        if (mk.regions && mk.regions.length) {
          for (const r of mk.regions) {
            kids.push(el("div", { class: "marked" },
              el("img", { src: fileUrl(c.source_id, "/assets/" + r.page_png), alt: "page " + loc.value }),
              r.mask_png ? el("img", { class: "mask", src: fileUrl(c.source_id, "/assets/" + r.mask_png), alt: "" }) : null));
            kids.push(el("p", { class: "hint" }, "Marked by SAM 3.1 (prompt “" + r.phrase + "”). Muse Spark read the marked area: ", el("span", {}, r.reading_excerpt || "")));
          }
        }
      } catch (e) { /* no marked regions for this page */ }
      const hl = c.quote ? "&hl=" + encodeURIComponent(c.quote) : "";
      kids.push(el("img", { class: "page-img", src: fileUrl(c.source_id, "/page/" + loc.value + ".png") + hl, alt: "page " + loc.value }));
      kids.push(el("p", { class: "hint" }, el("a", { href: fileUrl(c.source_id) + "#page=" + loc.value, target: "_blank" }, "Open the PDF at page " + loc.value)));
      body.replaceChildren(...kids);
    } else if (loc.kind === "time") {
      const v = el("video", { controls: true, preload: "auto", src: fileUrl(c.source_id) });
      v.addEventListener("loadedmetadata", () => { v.currentTime = loc.value; v.play().catch(() => {}); }, { once: true });
      const kids = [v];
      try {
        const data = await api("/videos/" + encodeURIComponent(c.source_id) + "/steps");
        const step = data.steps.find((s) => Math.abs(s.t_start - loc.value) < 0.06);
        if (step) {
          kids.push(el("h4", {}, "Step " + step.n + " at " + fmtTime(step.t_start) + ": " + step.instruction));
          if (step.reason) kids.push(el("p", { class: "why" }, "Why (spoken in the video): " + step.reason));
          if (step.frame_path) {
            kids.push(el("div", { class: "marked" },
              el("img", { src: fileUrl(c.source_id, "/assets/" + step.frame_path), alt: "frame" }),
              step.mask_path ? el("img", { class: "mask", src: fileUrl(c.source_id, "/assets/" + step.mask_path), alt: "" }) : null));
            kids.push(el("p", { class: "hint" }, markLabel(step)));
          }
        }
      } catch (e) { /* steps optional */ }
      body.replaceChildren(...kids);
    } else if (loc.kind === "cell") {
      const g = await api("/cells/" + encodeURIComponent(c.source_id) + "?range=" + encodeURIComponent(c.pointer));
      const [r1, r2] = g.highlight.rows, [c1, c2] = g.highlight.cols;
      const table = el("table", { class: "grid" },
        el("tr", {}, el("th", {}, ""), g.letters.map((L) => el("th", {}, L))),
        el("tr", {}, el("th", {}, "1"), g.header.map((h) => el("th", {}, h))),
        g.rows.map((row) => el("tr", { class: row.row >= r1 && row.row <= r2 ? "hit-row" : "" },
          el("th", {}, String(row.row)),
          row.cells.map((v, i) => el("td", { class: !g.window && row.row >= r1 && row.row <= r2 && i + 1 >= c1 && i + 1 <= c2 ? "hit" : "" }, v)))));
      body.replaceChildren(table, el("p", { class: "hint" }, "Exact values from the spreadsheet. " +
        (c.license ? "Seat-limited licensed data: only roles with a seat can open it." : "")),
        el("a", { href: fileUrl(c.source_id), target: "_blank" }, "Open the file"));
      const hit = body.querySelector("td.hit");
      if (hit) hit.scrollIntoView({ block: "nearest", inline: "center" });
    } else if (loc.kind === "slide") {
      body.replaceChildren(el("div", { class: "slide" }, c.excerpt || ""),
        el("p", { class: "hint" }, "Text of slide " + loc.value + " as extracted from the deck."),
        el("a", { href: fileUrl(c.source_id), target: "_blank" }, "Download the deck"));
    } else {
      body.replaceChildren(el("div", { class: "excerpt" }, c.excerpt || ""));
    }
  } catch (e) {
    body.replaceChildren(el("p", {}, "Could not open this source: " + e.message));
  }
}

function markLabel(step) {
  const how = { phrase: "SAM 3.1 matched the phrase", box: "SAM 3.1, refining a box proposed by Muse Spark",
    spark_box: "box proposed by Muse Spark (SAM found no mask)", failed: "no mark" }[step.mark_status] || step.mark_status;
  const drawn = step.box && step.box.drawn === "mask" ? "mask" : "box";
  return "Marked: “" + (step.target_phrase || "") + "”, " + how + " (drawn as " + drawn + ").";
}

// --------------------------------------------------------------- videos

async function loadVideos() {
  const sel = document.getElementById("video-select");
  const data = await api("/videos");
  const keep = sel.value;
  sel.replaceChildren(...data.videos.map((v) => el("option", { value: v.source_id }, v.title + " (" + v.status + ")")));
  if (keep && data.videos.some((v) => v.source_id === keep)) sel.value = keep;
  document.getElementById("upload-form").hidden = !config.uploads || !["manager", "steward"].includes(persona);
  if (sel.value) await loadSteps(sel.value);
}

async function loadSteps(sourceId) {
  const video = document.getElementById("guide-video");
  if (video.dataset.src !== sourceId + persona) {
    video.src = fileUrl(sourceId);
    video.dataset.src = sourceId + persona;
  }
  let st = null;
  try { st = await api("/videos/" + sourceId + "/status"); } catch (e) { /* not processed */ }
  document.getElementById("video-status").textContent = st ? st.status : "not processed";
  const data = await api("/videos/" + sourceId + "/steps");
  videoSteps = data.steps;
  document.getElementById("video-note").textContent = data.can_review
    ? "You can review: edit text, shift a step's time, approve. Approved steps become searchable chunks cited by second."
    : "Steps were made by Muse Spark from the video and its transcript, then approved by a reviewer. Click a time to jump.";
  const ol = document.getElementById("steps");
  ol.replaceChildren(...videoSteps.map((s) => stepItem(sourceId, s, data.can_review)));
  if (st && !["ready for review", "reviewed (seeded)", "failed"].includes(st.status)) {
    setTimeout(() => { if (document.getElementById("video-select").value === sourceId) loadSteps(sourceId); }, 3000);
  }
}

function seek(t) {
  const v = document.getElementById("guide-video");
  v.currentTime = t;
  v.play().catch(() => {});
}

function stepItem(sourceId, s, canReview) {
  const li = el("li", { class: "step", "data-n": s.n });
  const thumb = s.frame_path ? el("div", { class: "thumb", onclick: () => seek(s.t_start) },
    el("img", { src: fileUrl(sourceId, "/assets/" + s.frame_path), alt: "frame" }),
    s.mask_path ? el("img", { class: "mask", src: fileUrl(sourceId, "/assets/" + s.mask_path), alt: "" }) : null) : null;
  const text = el("div", {},
    el("div", {}, el("span", { class: "time", onclick: () => seek(s.t_start) }, fmtTime(s.t_start)), " · Step " + s.n + " ",
      s.approved ? el("span", { class: "badge ok" }, "approved") : el("span", { class: "badge warn" }, "needs review")),
    el("div", {}, el("b", {}, s.instruction)),
    s.reason ? el("div", { class: "why" }, "Why: " + s.reason) : el("div", { class: "why" }, "No reason spoken."),
    el("div", { class: "hint" }, markLabel(s)));
  li.append(el("div", { class: "row" }, thumb, text));
  if (canReview) {
    const instr = el("input", { value: s.instruction, "aria-label": "Instruction" });
    const why = el("input", { value: s.reason || "", placeholder: "Reason (only if spoken)", "aria-label": "Reason" });
    const save = async (extra) => {
      await api("/videos/" + sourceId + "/steps/" + s.n, { method: "PATCH", json: Object.assign({
        instruction: instr.value, reason: why.value || null, clear_reason: !why.value }, extra || {}) });
      loadSteps(sourceId);
    };
    li.append(el("div", { class: "edit" }, instr, why, el("div", { class: "btns" },
      el("button", { type: "button", class: "btn small ghost", onclick: () => save({ shift_s: -0.5 }) }, "− 0.5 s"),
      el("button", { type: "button", class: "btn small ghost", onclick: () => save({ shift_s: 0.5 }) }, "+ 0.5 s"),
      el("button", { type: "button", class: "btn small ghost", onclick: () => save() }, "Save text"),
      el("button", { type: "button", class: "btn small", onclick: async () => {
        await api("/videos/" + sourceId + "/approve", { method: "POST", json: { steps: [s.n] } });
        loadSteps(sourceId);
      } }, "Approve"))));
  }
  return li;
}

// -------------------------------------------------------------- steward

async function refreshConflictCount() {
  const badge = document.getElementById("conflict-count");
  try {
    const data = await api("/conflicts?status=open");
    badge.textContent = data.conflicts.length;
    badge.hidden = data.conflicts.length === 0;
  } catch (e) { badge.hidden = true; }
}

async function loadConflicts() {
  const data = await api("/conflicts");
  document.getElementById("steward-hint").textContent = data.can_decide
    ? "Muse Spark compared passages across sources and flagged these as factual contradictions. Decide which side is right; the losing side is ranked lower and answers change."
    : "Conflicts between sources you can see. Only the Steward (data admin) can decide which side is right.";
  const wrap = document.getElementById("conflicts");
  if (!data.conflicts.length) { wrap.replaceChildren(el("p", {}, "No conflicts between sources you can see.")); return; }
  wrap.replaceChildren(...data.conflicts.map((c) => {
    const note = el("input", { placeholder: "Note for the decision (shown in answers)", style: "flex:1;padding:7px;border:1px solid #dde3ea;border-radius:6px" });
    const decide = async (payload) => {
      await api("/conflicts/" + c.conflict_id + "/resolve", { method: "POST", json: Object.assign({ note: note.value }, payload) });
      loadConflicts(); refreshConflictCount();
    };
    const head = el("div", {},
      el("span", { class: "badge " + (c.status === "open" ? "warn" : c.status === "resolved" ? "ok" : "grey") }, c.status),
      el("span", { class: "badge " + (c.severity === "high" ? "bad" : "grey") }, c.severity + " severity"),
      el("b", {}, c.summary));
    const card = el("div", { class: "card" }, head,
      el("div", { class: "sides" },
        sideCard(c.side_a, c.winner === "a" ? "winner" : c.winner ? "loser" : ""),
        sideCard(c.side_b, c.winner === "b" ? "winner" : c.winner ? "loser" : "")));
    if (data.can_decide && c.status === "open") {
      card.append(el("div", { style: "display:flex;gap:6px;margin-top:10px;flex-wrap:wrap" }, note,
        el("button", { type: "button", class: "btn small", onclick: () => decide({ winner: "a" }) }, "Left is right"),
        el("button", { type: "button", class: "btn small", onclick: () => decide({ winner: "b" }) }, "Right is right"),
        el("button", { type: "button", class: "btn small ghost", onclick: () => decide({ dismiss: true }) }, "Not a conflict")));
    } else if (c.status !== "open") {
      card.append(el("p", { class: "hint" }, "Decided by " + (c.resolved_by || "?") + (c.note ? ": " + c.note : "")),
        data.can_decide ? el("button", { type: "button", class: "btn small ghost", onclick: async () => {
          await api("/conflicts/" + c.conflict_id + "/reopen", { method: "POST" }); loadConflicts(); refreshConflictCount();
        } }, "Reopen") : null);
    }
    return card;
  }));
}

// ------------------------------------------------------------- licenses

async function loadLicenses() {
  const data = await api("/licenses");
  const wrap = document.getElementById("licenses");
  if (!data.cards.length) { wrap.replaceChildren(el("p", {}, "No licensed sources for your role.")); return; }
  wrap.replaceChildren(...data.cards.map((c) => el("div", { class: "card lic-card" },
    el("span", { class: "badge lic" }, "licensed, simulated terms"),
    el("h3", {}, c.product),
    el("dl", {},
      el("dt", {}, "Vendor"), el("dd", {}, c.vendor),
      el("dt", {}, "Coverage"), el("dd", {}, c.coverage),
      el("dt", {}, "Seats"), el("dd", {}, c.seats ? String(c.seats) : "unlimited (company-wide)"),
      el("dt", {}, "Term"), el("dd", {}, c.term),
      c.annual_cost_usd ? [el("dt", {}, "Annual cost"), el("dd", {}, "$" + c.annual_cost_usd.toLocaleString() + " (simulated)")] : null),
    el("div", {}, el("span", { class: "big" }, String(c.users_30d)), " people used it through Kohu in the last 30 days"),
    el("div", { class: "hint" }, "Before Kohu: " + c.sample_users_30d + " people opened the file (" + c.sample_label + ")."),
    c.users_by_persona ? el("div", { class: "hint" }, "By role: " + (Object.entries(c.users_by_persona).map(([k, v]) => k + " " + v).join(", ") || "none yet")) : null)));
}

async function loadSources() {
  const data = await api("/sources");
  document.getElementById("sources").replaceChildren(...data.sources.map((s) => el("tr", {},
    el("td", {}, el("a", { href: fileUrl(s.source_id), target: "_blank" }, s.title)),
    el("td", {}, s.kind), el("td", {}, s.origin),
    el("td", {}, s.license ? s.license.coverage : "internal"))));
}

// ----------------------------------------------------------------- tabs

async function showTab(name) {
  document.querySelectorAll(".tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  document.querySelectorAll(".tab").forEach((t) => { t.hidden = t.id !== "tab-" + name; });
  try {
    if (name === "videos") await loadVideos();
    if (name === "steward") await loadConflicts();
    if (name === "licenses") await loadLicenses();
    if (name === "sources") await loadSources();
  } catch (e) {
    document.getElementById("tab-" + name).prepend(el("p", { class: "status" }, "Failed to load: " + e.message));
  }
}

document.querySelectorAll(".persona").forEach((b) => b.addEventListener("click", () => login(b.dataset.persona)));
document.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));
document.getElementById("ask-form").addEventListener("submit", (e) => { e.preventDefault(); ask(document.getElementById("query").value); });
document.getElementById("compare-form").addEventListener("submit", (e) => { e.preventDefault(); compare(document.getElementById("compare-query").value); });
document.getElementById("panel-close").addEventListener("click", closePanel);
document.getElementById("video-select").addEventListener("change", (e) => loadSteps(e.target.value));
document.getElementById("guide-video").addEventListener("timeupdate", (e) => {
  const t = e.target.currentTime;
  let cur = null;
  for (const s of videoSteps) if (s.t_start <= t + 0.05) cur = s.n;
  document.querySelectorAll(".step").forEach((li) => li.classList.toggle("current", Number(li.dataset.n) === cur));
});
document.getElementById("upload-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = document.getElementById("upload-file").files[0];
  if (!f) return;
  const fd = new FormData();
  fd.append("file", f);
  fd.append("title", document.getElementById("upload-title").value || f.name);
  const t = await tokenFor(persona);
  const res = await fetch("/videos", { method: "POST", headers: { Authorization: "Bearer " + t }, body: fd });
  const data = await res.json();
  if (!res.ok) { alert(data.detail || "upload failed"); return; }
  await loadVideos();
  document.getElementById("video-select").value = data.source_id;
  loadSteps(data.source_id);
});
document.getElementById("samples").replaceChildren(...SAMPLES.map((q) =>
  el("button", { type: "button", onclick: () => ask(q) }, q)));

fetch("/config").then((r) => r.json()).then((c) => { config = c; }).catch(() => {});
let start = "employee";
try { start = localStorage.getItem("kohu_persona") || start; } catch (e) { /* ignore */ }
login(PERSONAS.includes(start) ? start : "employee");
