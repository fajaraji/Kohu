"use strict";

// Kohu demo UI. Login is a demo persona switch: POST /login returns a
// signed token and every request sends it. The server reads the persona
// from the token only, so nothing here can widen access.

const PERSONAS = ["employee", "analyst", "manager", "steward"];
const LABELS = { employee: "Employee", analyst: "Analyst", manager: "Manager", steward: "Data admin" };
const LONG = { employee: "Employee (new hire)", analyst: "Analyst (dataset seat)", manager: "Manager", steward: "Data admin (decides conflicts)" };
const SAMPLES = [
  { q: "How do I process a customer refund?", icon: "play", hint: "process + video" },
  { q: "What was Viet Nam's GDP growth in 2023?", icon: "chart", hint: "licensed report" },
  { q: "Which country grew fastest in 2024?", icon: "chart", hint: "chart page" },
  { q: "How much can I spend per month without asking?", icon: "doc", hint: "handbook" },
  { q: "Who missed their Q3 target?", icon: "grid", hint: "manager only" },
];
const ICONS = {
  doc: "M5 2.5h6l4 4v11H5z M11 2.5v4h4",
  chart: "M4 16.5h12 M6 14V9 M10 14V5 M14 14v-3",
  grid: "M3.5 4.5h13v11h-13z M3.5 8.5h13 M3.5 12h13 M8 4.5v11",
  play: "M6 4.5v11l9-5.5z",
};
function icon(name) {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", "0 0 20 20"); svg.setAttribute("width", "14"); svg.setAttribute("height", "14");
  svg.setAttribute("aria-hidden", "true");
  const path = document.createElementNS(ns, "path");
  path.setAttribute("d", ICONS[name]); path.setAttribute("fill", "none"); path.setAttribute("stroke", "currentColor");
  path.setAttribute("stroke-width", "1.5"); path.setAttribute("stroke-linejoin", "round"); path.setAttribute("stroke-linecap", "round");
  svg.append(path);
  return svg;
}
const tokens = {};
let persona = null;
let config = { public_demo: false, uploads: true, step_editing: true };
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

function visitorId() {
  let v = null;
  try { v = localStorage.getItem("kohu_visitor"); } catch (e) { /* ignore */ }
  if (!/^[a-f0-9]{16}$/.test(v || "")) {
    v = Array.from(crypto.getRandomValues(new Uint8Array(8)), (b) => b.toString(16).padStart(2, "0")).join("");
    try { localStorage.setItem("kohu_visitor", v); } catch (e) { /* ignore */ }
  }
  return v;
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

function fileUrl(sourceId, suffix = "", as = persona) {
  return "/files/" + encodeURIComponent(sourceId) + suffix + "?token=" + encodeURIComponent(tokens[as]);
}

function shortTitle(title, sourceId) {
  if (!title) return sourceId;
  return title.replace(/^PostHog handbook: /, "Handbook, ").replace(/ \(.*\)$/, "");
}

function fmtTime(s) {
  const m = Math.floor(s / 60), r = Math.floor(s - m * 60);
  return m + ":" + String(r).padStart(2, "0");
}

function parsePointer(pointer) {
  let m = /^p\.(\d+)$/.exec(pointer);
  if (m) return { kind: "page", value: Number(m[1]), label: "page " + m[1] };
  m = /^slide (\d+)$/.exec(pointer);
  if (m) return { kind: "slide", value: Number(m[1]), label: "slide " + m[1] };
  m = /^t=(\d+(?:\.\d+)?)s$/.exec(pointer);
  if (m) return { kind: "time", value: Number(m[1]), label: "at " + fmtTime(Number(m[1])) + " in the recording" };
  m = /^(.+)!([A-Z]+)(\d+)(?::([A-Z]+)(\d+))?$/.exec(pointer);
  if (m) {
    let label;
    if (!m[4]) label = "cell " + m[2] + m[3];
    else if (m[3] === m[5]) label = "row " + m[3];
    else label = "rows " + m[3] + " to " + m[5];
    return { kind: "cell", value: pointer, sheet: m[1], label: label + ", sheet " + m[1] };
  }
  return { kind: "unknown", value: pointer, label: pointer };
}

function licenseTag(lic) {
  if (!lic) return null;
  return lic.seats ? "licensed, limited seats" : "licensed for everyone";
}

// ---------------------------------------------------------------- login

async function login(p) {
  persona = p;
  try { localStorage.setItem("kohu_persona", p); } catch (e) { /* ignore */ }
  document.querySelectorAll(".persona").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.persona === p)));
  await tokenFor(p);
  document.getElementById("answer").hidden = true;
  closePanel();
  refreshConflictCount();
  showTab(currentTab());
}

// ------------------------------------------------------------------ ask

function renderAnswer(r, target, as, compact = false) {
  // Number citations in order of first use, like notes in a paper.
  const byMarker = Object.fromEntries(r.citations.map((c) => [c.marker, c]));
  const order = [];
  for (const m of r.text.matchAll(/\[(S\d+)\]/g)) if (byMarker[m[1]] && !order.includes(m[1])) order.push(m[1]);
  const num = Object.fromEntries(order.map((m, i) => [m, i + 1]));
  const text = el("p", { class: "answer-text" });
  const parts = r.text.split(/(\[S\d+\])/);
  for (let i = 0; i < parts.length; i++) {
    let part = parts[i];
    const m = /^\[(S\d+)\]$/.exec(part);
    // A note number sits right after the word it supports.
    if (!m && i + 1 < parts.length && /^\[S\d+\]$/.test(parts[i + 1])) part = part.replace(/\s+$/, "");
    if (m && num[m[1]]) {
      const c = byMarker[m[1]];
      text.append(el("button", { type: "button", class: "note-ref" + (c.stale ? " stale" : ""),
        "aria-label": "Source " + num[m[1]] + ", " + shortTitle(c.title, c.source_id),
        onclick: () => openCitation(c, as) }, String(num[m[1]])));
    } else if (!m) text.append(part.replace(/\s+([.,;])/g, "$1"));
  }
  const notes = el("ol", { class: "notes", "aria-label": "Sources" }, order.map((m) => {
    const c = byMarker[m];
    const loc = parsePointer(c.pointer);
    return el("li", {}, el("span", { class: "n" }, num[m] + "."),
      el("span", {},
        el("a", { href: "#", class: "src", onclick: (e) => { e.preventDefault(); openCitation(c, as); } }, shortTitle(c.title, c.source_id)),
        ", ", el("span", { class: "where" }, loc.label),
        c.license ? el("span", { class: "tag" }, " · " + licenseTag(c.license)) : null,
        c.stale ? el("span", { class: "tag" }, " · superseded by a data admin decision") : null));
  }));
  const kids = [];
  if (r.degraded) kids.push(el("p", { class: "meta" }, "Muse Spark was not available, so this is the best matching passage, not a written answer."));
  kids.push(text);
  if (order.length) kids.push(notes);
  for (const l of compact ? [] : r.licensed || []) {
    kids.push(el("div", { class: "inset" },
      l.seats ? "This uses licensed data with a limited number of seats. Your role has one. "
              : "This uses data the company licensed for every employee. ",
      el("strong", {}, l.product), ". Vendor and terms are simulated."));
  }
  if (compact && (r.conflicts || []).length) {
    kids.push(el("p", { class: "meta" }, (r.conflicts.some((c) => c.status === "open")
      ? "Sources disagree on this. " : "A data admin decided a conflict on this. ") + "Ask on the Ask page to see both versions."));
  } else for (const c of r.conflicts || []) kids.push(conflictNotice(c, as));
  kids.push(traceBox(r.run_id, as));
  kids.push(el("p", { class: "meta" }, "Asked as " + LONG[r.persona] + (r.synthesis === "spark" ? ", answered by Muse Spark" : ", extractive answer")));
  target.replaceChildren(el("div", { class: "answer" }, kids));
  target.hidden = false;
}

function versionBlock(side, cls, as) {
  const c = { source_id: side.source_id, pointer: side.pointer, title: side.title, license: side.license, excerpt: side.text, quote: side.quote };
  return el("div", { class: "version " + (cls || "") },
    el("q", {}, side.quote || side.text.slice(0, 160)),
    el("div", { class: "who" }, el("button", { type: "button", class: "link-button", onclick: () => openCitation(c, as) },
      shortTitle(side.title, side.source_id) + ", " + parsePointer(side.pointer).label)));
}

function conflictNotice(c, as) {
  if (c.status === "resolved") {
    const win = c["side_" + c.winner];
    return el("div", { class: "inset decided" },
      el("strong", {}, "A data admin decided that " + shortTitle(win.title, win.source_id) + " is right."),
      c.note ? el("div", {}, c.note) : null,
      el("div", { class: "versions" }, versionBlock(c.side_a, c.winner === "a" ? "winner" : "loser", as),
        versionBlock(c.side_b, c.winner === "b" ? "winner" : "loser", as)));
  }
  return el("div", { class: "warning", role: "note" },
    el("span", { class: "icon", "aria-hidden": "true" }, "!"),
    el("div", {}, el("strong", {}, "Two sources disagree, and no one has decided which is right."),
      el("div", {}, c.summary),
      el("div", { class: "versions" }, versionBlock(c.side_a, "", as), versionBlock(c.side_b, "", as))));
}

function progressLine(s) {
  const d = s.detail;
  if (s.kind === "model") return "Muse Spark, step " + d.step + ": " + (d.tool_calls.length ? d.tool_calls.map((t) => t.name.replace("_", " ")).join(", ") : "has enough to answer");
  if (s.kind === "tool") return d.tool.replace("_", " ") + (d.args.terms ? " “" + d.args.terms + "”" : "") + ", " + d.results.length + " result" + (d.results.length === 1 ? "" : "s");
  if (s.kind === "answer") return "Writing the answer and checking every citation";
  if (s.kind === "fallback") return "Model unavailable, using the best matching passage";
  return "Done";
}

function traceBox(runId, as) {
  const box = el("details", { class: "trace" }, el("summary", {}, "How Kohu found this"));
  box.addEventListener("toggle", async () => {
    if (!box.open || box.dataset.loaded) return;
    box.dataset.loaded = "1";
    try {
      const data = await api("/runs/" + runId + "/steps", {}, as);
      box.append(el("ol", {}, data.steps.map((s) => {
        const d = s.detail;
        if (s.kind === "tool") {
          return el("li", {}, el("code", {}, d.tool), " ", d.args.terms ? "“" + d.args.terms + "”" : "",
            " → ", d.results.length ? d.results.map((x) => shortTitle(x.title, x.source_id) + " " + x.pointer).join("; ") : "nothing");
        }
        if (s.kind === "model") return el("li", {}, "Muse Spark step " + d.step + (d.seconds ? " (" + d.seconds + " s)" : "") + ": " +
          (d.tool_calls.length ? d.tool_calls.map((t) => t.name).join(", ") : "stops searching"));
        if (s.kind === "answer") return el("li", {}, "Final answer call without tools" + (d.seconds ? " (" + d.seconds + " s)" : "") +
          ". The server kept " + d.kept_citations.length + " citation(s)" +
          (d.dropped.length ? " and removed " + d.dropped.length + " (" + [...new Set(d.dropped.map((x) => x.reason))].join(", ") + ")" : "") + ".");
        if (s.kind === "fallback") return el("li", {}, "Model unavailable (" + d.reason + "), extractive fallback.");
        return el("li", {}, "Total " + d.usage.input_tokens.toLocaleString() + " input and " + d.usage.output_tokens.toLocaleString() + " output tokens.");
      })));
    } catch (e) { box.append(el("p", { class: "meta" }, "Could not load the steps: " + e.message)); }
  });
  return box;
}

async function ask(q) {
  const status = document.getElementById("status");
  const btn = document.querySelector("#ask-form button");
  q = (q || "").trim();
  if (!q) return;
  document.getElementById("query").value = q;
  document.getElementById("samples").hidden = true;
  btn.disabled = true;
  document.getElementById("answer").hidden = true;
  status.textContent = "Searching the sources your role can see…";
  const t0 = performance.now();
  const runId = Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) => b.toString(16).padStart(2, "0")).join("");
  const live = el("ol", { class: "live" });
  status.after(live);
  let polling = true;
  (async () => {
    await new Promise((r) => setTimeout(r, 1500));
    while (polling) {
      try {
        const data = await api("/runs/" + runId + "/steps");
        if (polling) live.replaceChildren(...data.steps.filter((s) => s.kind !== "result").map((s) => el("li", {}, progressLine(s))));
      } catch (e) { /* run not started yet */ }
      await new Promise((r) => setTimeout(r, 1200));
    }
  })();
  try {
    const r = await api("/ask", { method: "POST", json: { query: q, run_id: runId } });
    renderAnswer(r, document.getElementById("answer"), persona);
    status.textContent = "Answered in " + ((performance.now() - t0) / 1000).toFixed(1) + " s.";
    refreshConflictCount();
  } catch (e) {
    status.textContent = e.message;
  } finally { polling = false; live.remove(); btn.disabled = false; }
}

// ------------------------------------------------------------- compare

async function compare(q) {
  const wrap = document.getElementById("compare");
  const btn = document.querySelector("#compare-form button");
  btn.disabled = true;
  wrap.replaceChildren(...PERSONAS.map((p) => el("div", { id: "cmp-" + p },
    el("h2", {}, LONG[p]), el("p", { class: "meta" }, "Asking…"))));
  await Promise.all(PERSONAS.map(async (p) => {
    const box = document.getElementById("cmp-" + p);
    try {
      await tokenFor(p);
      const r = await api("/ask", { method: "POST", json: { query: q } }, p);
      const body = el("div");
      renderAnswer(r, body, p, true);
      box.replaceChildren(el("h2", {}, LONG[p]), body);
    } catch (e) { box.replaceChildren(el("h2", {}, LONG[p]), el("p", {}, e.message)); }
  }));
  btn.disabled = false;
}

// -------------------------------------------------------------- citation

function closePanel() {
  document.getElementById("panel").hidden = true;
  document.getElementById("panel-body").replaceChildren();
}

async function openCitation(c, as = persona) {
  const loc = parsePointer(c.pointer);
  document.getElementById("panel-title").textContent = c.title || c.source_id;
  document.getElementById("panel-pointer").textContent = loc.label +
    (c.license ? " · " + licenseTag(c.license) : "") + (c.stale ? " · superseded by a data admin decision" : "");
  const body = document.getElementById("panel-body");
  body.replaceChildren(el("p", { class: "meta" }, "Loading…"));
  document.getElementById("panel").hidden = false;
  try {
    if (loc.kind === "page") {
      const kids = [];
      try {
        const mk = await api("/regions/" + encodeURIComponent(c.source_id) + "/" + loc.value, {}, as);
        for (const r of mk.regions || []) {
          kids.push(el("div", { class: "marked" },
            el("img", { src: fileUrl(c.source_id, "/assets/" + r.page_png, as), alt: "Page " + loc.value }),
            r.mask_png ? el("img", { class: "mask", src: fileUrl(c.source_id, "/assets/" + r.mask_png, as), alt: "" }) : null));
          kids.push(el("p", { class: "caption" }, "Area marked by SAM 3.1 from the phrase “" + r.phrase + "”. Muse Spark read the marked area."));
        }
      } catch (e) { /* no marked regions */ }
      const hl = c.quote ? "&hl=" + encodeURIComponent(c.quote) : "";
      if (!kids.length) kids.push(el("img", { class: "page-img", src: fileUrl(c.source_id, "/page/" + loc.value + ".png", as) + hl, alt: "Page " + loc.value }));
      kids.push(el("p", { class: "caption" }, el("a", { href: fileUrl(c.source_id, "", as) + "#page=" + loc.value, target: "_blank", rel: "noopener" }, "Open the PDF at page " + loc.value)));
      body.replaceChildren(...kids);
    } else if (loc.kind === "time") {
      const v = el("video", { controls: true, preload: "auto", src: fileUrl(c.source_id, "", as) });
      v.addEventListener("loadedmetadata", () => { v.currentTime = loc.value; v.play().catch(() => {}); }, { once: true });
      const kids = [v];
      try {
        const data = await api("/videos/" + encodeURIComponent(c.source_id) + "/steps", {}, as);
        const step = data.steps.find((s) => Math.abs(s.t_start - loc.value) < 0.06);
        if (step) {
          kids.push(el("h3", { class: "h2" }, "Step " + step.n + ", " + fmtTime(step.t_start) + ". " + step.instruction));
          if (step.reason) kids.push(el("p", { class: "excerpt" }, "Why, as said in the recording: " + step.reason));
          if (step.frame_path) {
            kids.push(el("div", { class: "marked" },
              el("img", { src: fileUrl(c.source_id, "/assets/" + step.frame_path, as), alt: "Frame of step " + step.n }),
              step.mask_path ? el("img", { class: "mask", src: fileUrl(c.source_id, "/assets/" + step.mask_path, as), alt: "" }) : null));
            kids.push(el("p", { class: "caption" }, markLabel(step)));
          }
        }
      } catch (e) { /* steps optional */ }
      body.replaceChildren(...kids);
    } else if (loc.kind === "cell") {
      const g = await api("/cells/" + encodeURIComponent(c.source_id) + "?range=" + encodeURIComponent(c.pointer), {}, as);
      const [r1, r2] = g.highlight.rows, [c1, c2] = g.highlight.cols;
      const table = el("table", { class: "grid" },
        el("tr", {}, el("th", {}, ""), g.letters.map((L) => el("th", {}, L))),
        el("tr", {}, el("th", {}, "1"), g.header.map((h) => el("th", {}, h))),
        g.rows.map((row) => el("tr", { class: row.row >= r1 && row.row <= r2 ? "hit-row" : "" },
          el("th", {}, String(row.row)),
          row.cells.map((v, i) => el("td", { class: !g.window && row.row >= r1 && row.row <= r2 && i + 1 >= c1 && i + 1 <= c2 ? "hit" : "" }, v)))));
      body.replaceChildren(el("div", { class: "grid-wrap" }, table),
        el("p", { class: "caption" }, "Exact values from the spreadsheet." + (c.license && c.license.seats ? " Only roles with a seat can open this file." : "")),
        el("a", { href: fileUrl(c.source_id, "", as), target: "_blank", rel: "noopener" }, "Download the spreadsheet"));
      const hit = body.querySelector("td.hit") || body.querySelector("tr.hit-row td:nth-child(9)");
      if (hit) hit.scrollIntoView({ block: "nearest", inline: "center" });
    } else if (loc.kind === "slide") {
      const img = el("img", { class: "slide-img", src: fileUrl(c.source_id, "/slide/" + loc.value + ".png", as), alt: "Slide " + loc.value });
      img.addEventListener("error", () => img.replaceWith(el("div", { class: "excerpt" }, c.excerpt || "")), { once: true });
      body.replaceChildren(img, el("p", { class: "caption" }, el("a", { href: fileUrl(c.source_id, "", as), target: "_blank", rel: "noopener" }, "Download the deck")));
    } else {
      body.replaceChildren(el("div", { class: "excerpt" }, c.excerpt || ""));
    }
  } catch (e) {
    body.replaceChildren(el("p", {}, "Could not open this source. " + e.message));
  }
}

function markLabel(step) {
  const how = { phrase: "SAM 3.1 found it from the phrase", box: "SAM 3.1 refined a box proposed by Muse Spark",
    spark_box: "box proposed by Muse Spark (SAM found nothing)", failed: "not marked" }[step.mark_status] || step.mark_status;
  const drawn = step.box && step.box.drawn === "mask" ? "the SAM mask" : "the SAM box";
  return step.mark_status === "failed" ? "No mark for this step." : "Marked “" + (step.target_phrase || "") + "”. " + how + ", drawn as " + drawn + ".";
}

// --------------------------------------------------------------- videos

async function loadVideos() {
  const sel = document.getElementById("video-select");
  const data = await api("/videos");
  const keep = sel.value;
  sel.replaceChildren(...data.videos.map((v) => el("option", { value: v.source_id }, v.title)));
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
  document.getElementById("video-status").textContent = st ? "Status: " + st.status : "Not processed yet";
  const data = await api("/videos/" + sourceId + "/steps");
  videoSteps = data.steps;
  document.getElementById("video-note").textContent = data.can_review
    ? "Muse Voice Transcribe writes down the narration, Muse Spark turns the recording into timed steps, and SAM 3.1 marks what each step uses. Review the steps here. Approved steps become searchable and citable by the second."
    : "Muse Voice Transcribe wrote down the narration, Muse Spark turned the recording into timed steps, and SAM 3.1 marked what each step uses. A reviewer approved them. Select a time to jump there.";
  document.getElementById("steps").replaceChildren(...videoSteps.map((s) => stepItem(sourceId, s, data.can_review)));
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
    el("img", { src: fileUrl(sourceId, "/assets/" + s.frame_path), alt: "Frame of step " + s.n }),
    s.mask_path ? el("img", { class: "mask", src: fileUrl(sourceId, "/assets/" + s.mask_path), alt: "" }) : null) : el("div");
  const text = el("div", {},
    el("div", {}, el("a", { href: "#", class: "time", onclick: (e) => { e.preventDefault(); seek(s.t_start); } }, fmtTime(s.t_start)),
      el("span", { class: "meta" }, "  Step " + s.n + (s.approved ? "" : ", waiting for review"))),
    el("div", { class: "instr" }, s.instruction),
    s.reason ? el("div", { class: "why" }, "Why: " + s.reason) : el("div", { class: "meta" }, "No reason was said."),
    el("div", { class: "meta" }, markLabel(s)));
  li.append(el("div", { class: "row" }, thumb, text));
  if (canReview && config.step_editing) {
    const instr = el("input", { value: s.instruction, "aria-label": "Instruction for step " + s.n });
    const why = el("input", { value: s.reason || "", placeholder: "Reason, only if it was said", "aria-label": "Reason for step " + s.n });
    const save = async (extra) => {
      await api("/videos/" + sourceId + "/steps/" + s.n, { method: "PATCH", json: Object.assign({
        instruction: instr.value, reason: why.value || null, clear_reason: !why.value }, extra || {}) });
      loadSteps(sourceId);
    };
    li.append(el("div", { class: "edit" }, instr, why, el("div", { class: "btns" },
      el("button", { type: "button", class: "button secondary small", onclick: () => save({ shift_s: -0.5 }) }, "Earlier 0.5 s"),
      el("button", { type: "button", class: "button secondary small", onclick: () => save({ shift_s: 0.5 }) }, "Later 0.5 s"),
      el("button", { type: "button", class: "button secondary small", onclick: () => save() }, "Save text"),
      s.approved ? null : el("button", { type: "button", class: "button small", onclick: async () => {
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
  document.getElementById("steward-hint").textContent = (data.can_decide
    ? "Muse Spark compared related passages across sources and flagged these as factual contradictions. Decide which side is right. The other side is then ranked lower and marked as superseded in answers."
    : "Passages that contradict each other, in sources your role can see. Only the data admin can decide which is right.") +
    (data.decisions_are_private ? " In this public demo your decisions only change what you see in this browser." : "");
  document.getElementById("reset-row").hidden = !data.decisions_are_private;
  const wrap = document.getElementById("conflicts");
  if (!data.conflicts.length) { wrap.replaceChildren(el("p", {}, "No conflicts between sources you can see.")); return; }
  wrap.replaceChildren(...data.conflicts.map((c) => {
    const note = el("input", { placeholder: "Note shown with the decision", "aria-label": "Note" });
    const decide = async (payload) => {
      await api("/conflicts/" + c.conflict_id + "/resolve", { method: "POST", json: Object.assign({ note: note.value }, payload) });
      loadConflicts(); refreshConflictCount();
    };
    const state = c.status === "open" ? el("span", { class: "state open" }, "Open")
      : c.status === "resolved" ? el("span", { class: "state ok" }, "Decided") : el("span", { class: "state muted" }, "Not a conflict");
    const item = el("div", { class: "conflict" },
      el("div", {}, state, el("span", { class: "meta" }, c.severity + " severity")),
      el("p", { class: "summary" }, c.summary),
      el("div", { class: "versions" },
        versionBlock(c.side_a, c.winner === "a" ? "winner" : c.winner ? "loser" : ""),
        versionBlock(c.side_b, c.winner === "b" ? "winner" : c.winner ? "loser" : "")));
    if (data.can_decide && c.status === "open") {
      item.append(el("div", { class: "decide" }, note,
        el("button", { type: "button", class: "button small", onclick: () => decide({ winner: "a" }) }, "Left is right"),
        el("button", { type: "button", class: "button small", onclick: () => decide({ winner: "b" }) }, "Right is right"),
        el("button", { type: "button", class: "button secondary small", onclick: () => decide({ dismiss: true }) }, "Not a conflict")));
    } else if (c.status !== "open") {
      item.append(el("p", { class: "meta" }, "Decided by " + (c.resolved_by || "unknown") + (c.note ? ". " + c.note : "")),
        data.can_decide ? el("button", { type: "button", class: "link-button", onclick: async () => {
          await api("/conflicts/" + c.conflict_id + "/reopen", { method: "POST" }); loadConflicts(); refreshConflictCount();
        } }, "Reopen") : null);
    }
    return item;
  }));
}

// ------------------------------------------------------------- licenses

async function loadLicenses() {
  const data = await api("/licenses");
  const wrap = document.getElementById("licenses");
  if (!data.cards.length) { wrap.replaceChildren(el("p", {}, "Your role does not cover any licensed source.")); return; }
  wrap.replaceChildren(...data.cards.map((c) => el("section", { class: "licence" },
    el("h2", { class: "h2" }, c.product),
    el("p", {}, el("span", { class: "figure" }, String(c.users_30d)), el("br"),
      el("span", { class: "meta" }, (c.users_30d === 1 ? "person" : "people") + " used it through Kohu in the last 30 days. Before Kohu, " +
        c.sample_users_30d + " opened the file. That baseline is sample data.")),
    el("dl", { class: "summary-list" },
      el("dt", {}, "Vendor"), el("dd", {}, c.vendor),
      el("dt", {}, "Who may use it"), el("dd", {}, c.coverage),
      el("dt", {}, "Seats"), el("dd", {}, c.seats ? String(c.seats) : "No limit, company-wide"),
      el("dt", {}, "Term"), el("dd", {}, c.term),
      c.annual_cost_usd ? [el("dt", {}, "Annual cost"), el("dd", {}, "$" + c.annual_cost_usd.toLocaleString() + " (simulated)")] : null,
      c.users_by_persona ? [el("dt", {}, "Users by role"), el("dd", {}, Object.entries(c.users_by_persona).map(([k, v]) => k + " " + v).join(", ") || "none yet")] : null))));
}

async function loadSources() {
  const data = await api("/sources");
  document.getElementById("sources").replaceChildren(...data.sources.map((s) => el("tr", {},
    el("td", {}, el("a", { href: fileUrl(s.source_id), target: "_blank", rel: "noopener" }, s.title)),
    el("td", {}, s.kind), el("td", {}, s.origin),
    el("td", {}, s.license ? s.license.coverage : "Internal"))));
}

// ----------------------------------------------------------------- tabs

function currentTab() {
  const t = (location.hash || "#ask").slice(1);
  return ["ask", "compare", "videos", "steward", "licenses", "sources"].includes(t) ? t : "ask";
}

async function showTab(name) {
  document.querySelectorAll(".navlinks a").forEach((a) => {
    if (a.dataset.tab === name) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  });
  document.querySelectorAll(".tab").forEach((t) => { t.hidden = t.id !== "tab-" + name; });
  try {
    if (name === "videos") await loadVideos();
    if (name === "steward") await loadConflicts();
    if (name === "licenses") await loadLicenses();
    if (name === "sources") await loadSources();
  } catch (e) {
    document.getElementById("tab-" + name).prepend(el("p", { class: "status" }, "Could not load this page. " + e.message));
  }
}

window.addEventListener("hashchange", () => { if (persona) showTab(currentTab()); });
document.querySelectorAll("[data-tab]").forEach((a) => a.addEventListener("click", (e) => {
  e.preventDefault();
  if (location.hash !== "#" + a.dataset.tab) location.hash = a.dataset.tab; else showTab(a.dataset.tab);
}));
document.querySelectorAll(".persona").forEach((b) => b.addEventListener("click", () => login(b.dataset.persona)));
document.getElementById("ask-form").addEventListener("submit", (e) => { e.preventDefault(); ask(document.getElementById("query").value); });
document.getElementById("compare-form").addEventListener("submit", (e) => { e.preventDefault(); compare(document.getElementById("compare-query").value); });
document.getElementById("panel-close").addEventListener("click", closePanel);
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closePanel(); });
document.getElementById("video-select").addEventListener("change", (e) => loadSteps(e.target.value));
document.getElementById("guide-video").addEventListener("timeupdate", (e) => {
  const t = e.target.currentTime;
  let cur = null;
  for (const s of videoSteps) if (s.t_start <= t + 0.05) cur = s.n;
  document.querySelectorAll(".step").forEach((li) => li.classList.toggle("current", Number(li.dataset.n) === cur));
});
document.getElementById("reset-demo").addEventListener("click", async () => {
  await api("/demo/reset", { method: "POST" });
  loadConflicts(); refreshConflictCount();
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
  if (!res.ok) { document.getElementById("video-status").textContent = data.detail || "Upload failed"; return; }
  await loadVideos();
  document.getElementById("video-select").value = data.source_id;
  loadSteps(data.source_id);
});
let selected = -1;
function renderSamples() {
  const list = document.getElementById("samples");
  list.replaceChildren(...SAMPLES.map((x, i) => el("li", { role: "option", "aria-selected": String(i === selected),
    onclick: () => ask(x.q), onmouseenter: () => { selected = i; markSelected(); } },
    el("span", { class: "ic" }, icon(x.icon)), el("span", { class: "q" }, x.q), el("span", { class: "hint" }, x.hint))));
}
function markSelected() {
  document.querySelectorAll("#samples li").forEach((li, i) => li.setAttribute("aria-selected", String(i === selected)));
}
renderSamples();
const queryInput = document.getElementById("query");
queryInput.addEventListener("keydown", (e) => {
  const list = document.getElementById("samples");
  if (list.hidden || !["ArrowDown", "ArrowUp"].includes(e.key)) return;
  e.preventDefault();
  selected = (selected + (e.key === "ArrowDown" ? 1 : -1) + SAMPLES.length) % SAMPLES.length;
  queryInput.value = SAMPLES[selected].q;
  markSelected();
});
queryInput.addEventListener("focus", () => { document.getElementById("samples").hidden = false; });
document.addEventListener("keydown", (e) => {
  if (e.key === "/" && document.activeElement.tagName !== "INPUT" && currentTab() === "ask") { e.preventDefault(); queryInput.focus(); }
});

(async () => {
  try { config = await (await fetch("/config")).json(); } catch (e) { /* defaults */ }
  let start = "employee";
  try { start = localStorage.getItem("kohu_persona") || start; } catch (e) { /* ignore */ }
  login(PERSONAS.includes(start) ? start : "employee");
})();
