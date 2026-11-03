"use strict";

// Mocked persona login (PRD section 2): no real IdP. Login swaps the
// persona token; the token's persona is what POST /ask sends.
const PERSONAS = ["employee", "analyst", "manager", "steward"];
const API_BASE = location.protocol.startsWith("http")
  ? "" : "http://localhost:8000";

function tokenFor(persona) {
  return "kohu-demo-token-" + persona;
}

function currentPersona() {
  const p = localStorage.getItem("kohu_persona");
  return PERSONAS.includes(p) ? p : null;
}

function login(persona) {
  localStorage.setItem("kohu_persona", persona);
  localStorage.setItem("kohu_token", tokenFor(persona));
  renderSession();
}

function renderSession() {
  const persona = currentPersona();
  document.getElementById("token").textContent = persona
    ? localStorage.getItem("kohu_token") : "not logged in";
  document.getElementById("current-persona").textContent = persona || "none";
  document.querySelectorAll(".login").forEach((b) => {
    const active = b.dataset.persona === persona;
    b.classList.toggle("active", active);
    b.setAttribute("aria-pressed", active ? "true" : "false");
  });
  loadQueue();
}

async function loadQueue() {
  const wrap = document.getElementById("steward-queue");
  if (currentPersona() !== "steward") {
    wrap.hidden = true;
    document.getElementById("queue-tasks").replaceChildren();
    return;
  }
  try {
    const res = await fetch(
      API_BASE + "/steward/queue?persona=steward", {
        headers: { "Authorization": "Bearer " + tokenFor("steward") } });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || ("HTTP " + res.status));
    renderQueue(data.tasks || []);
  } catch (e) {
    wrap.hidden = false;
    document.getElementById("queue-empty").hidden = false;
    document.getElementById("queue-empty").textContent =
      "Queue failed to load: " + e.message;
  }
}

function sideButton(side) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "claim queue-side";
  btn.dataset.source = side.source_id;
  btn.dataset.pointer = side.pointer;
  btn.textContent = side.claim + " [" + side.source_id + " " +
    side.pointer + "]";
  btn.addEventListener("click", () => openCitation({
    text: side.claim,
    citation: { source_id: side.source_id, pointer: side.pointer } }));
  return btn;
}

function renderQueue(tasks) {
  const wrap = document.getElementById("steward-queue");
  wrap.hidden = false;
  document.getElementById("queue-empty").hidden = tasks.length > 0;
  document.getElementById("queue-tasks").replaceChildren(...tasks.map((t) => {
    const li = document.createElement("li");
    li.className = "queue-task";
    li.dataset.conflictId = t.conflict_id;
    const head = document.createElement("strong");
    head.textContent = t.conflict_id + " — " + t.status +
      ", resolution: " + t.resolution;
    li.append(head);
    const a = document.createElement("div");
    a.append("Side A: ", sideButton(t.side_a));
    const b = document.createElement("div");
    b.append("Side B: ", sideButton(t.side_b));
    li.append(a, b);
    return li;
  }));
}

const SOURCE_FILES = {
  "handbook": "handbook.pdf",
  "process-report": "process-report.pdf",
  "product-deck": "product-deck.pptx",
  "sales-deck": "sales-deck.pptx",
  "licensed-market": "licensed-market.xlsx",
  "licensed-report": "licensed-report.pdf",
  "performance": "performance.xlsx",
  "scanned-note": "scanned-note.pdf",
};

function parsePointer(pointer) {
  let m = /^p\.(\d+)$/.exec(pointer);
  if (m) return { kind: "page", value: m[1], label: "page " + m[1] };
  m = /^slide (\d+)$/.exec(pointer);
  if (m) return { kind: "slide", value: m[1], label: "slide " + m[1] };
  m = /^t=(\d+(?:\.\d+)?)s$/.exec(pointer);
  if (m) return { kind: "time", value: Number(m[1]), label: m[1] + " s" };
  m = /^(.+)!([A-Z]+\d+(?::[A-Z]+\d+)?)$/.exec(pointer);
  if (m) return { kind: "cell", value: m[2], sheet: m[1], label: m[1] + "!" + m[2] };
  return { kind: "unknown", value: pointer, label: pointer };
}

function openCitation(claim) {
  const { source_id, pointer } = claim.citation;
  const loc = parsePointer(pointer);
  const file = SOURCE_FILES[source_id];
  const panel = document.getElementById("citation-panel");
  panel.hidden = false;
  panel.dataset.kind = loc.kind;
  panel.dataset.source = source_id;
  panel.dataset.location = loc.label;
  document.getElementById("cite-source").textContent = source_id;
  const locEl = document.getElementById("cite-location");
  locEl.textContent = loc.label;
  locEl.dataset.kind = loc.kind;
  locEl.dataset.value = loc.value;
  document.getElementById("cite-claim").textContent = claim.text;
  const fileUrl = API_BASE + "/corpus/" + file;
  document.getElementById("cite-open").href = fileUrl;
  const viewer = document.getElementById("cite-viewer");
  viewer.replaceChildren();
  if (loc.kind === "page") {
    const frame = document.createElement("iframe");
    frame.className = "cite-frame";
    frame.title = source_id + " " + loc.label;
    frame.src = fileUrl + "#page=" + loc.value;
    frame.dataset.page = loc.value;
    viewer.append(frame);
  } else {
    const card = document.createElement("div");
    card.className = "cite-locator";
    card.id = "cite-target";
    card.textContent = loc.kind === "slide"
      ? source_id + " — slide " + loc.value + " of " + file
      : source_id + " — cells " + loc.label + " in " + file;
    viewer.append(card);
  }
  history.replaceState(null, "", "#cite-" + loc.kind + "-" +
    loc.value.replace(":", "-"));
  panel.scrollIntoView({ block: "start" });
}

function claimItem(claim) {
  const li = document.createElement("li");
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "claim";
  btn.dataset.source = claim.citation.source_id;
  btn.dataset.pointer = claim.citation.pointer;
  btn.textContent = claim.text + " [" + claim.citation.source_id + " " +
    claim.citation.pointer + "]";
  btn.addEventListener("click", () => openCitation(claim));
  li.append(btn);
  return li;
}

async function fetchAsk(persona, query) {
  const res = await fetch(API_BASE + "/ask", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": "Bearer " + tokenFor(persona),
    },
    body: JSON.stringify({ persona, query }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || ("HTTP " + res.status));
  return data;
}

async function ask(event) {
  event.preventDefault();
  const persona = currentPersona();
  const query = document.getElementById("query").value.trim();
  const status = document.getElementById("status");
  const error = document.getElementById("error");
  error.textContent = "";
  if (!persona) { error.textContent = "Log in as a persona first."; return; }
  if (!query) { error.textContent = "Enter a question."; return; }
  status.textContent = "Asking as " + persona + " ...";
  try {
    renderResult(await fetchAsk(persona, query));
    status.textContent = "";
  } catch (e) {
    status.textContent = "";
    error.textContent = "Ask failed: " + e.message;
  }
}

function renderCompareColumn(persona, data, otherSources) {
  const col = document.getElementById("col-" + persona);
  const src = col.querySelector(".col-sources");
  src.replaceChildren(...(data.sources || []).map((s) => {
    const span = document.createElement("span");
    span.textContent = s;
    span.className = "src" + (otherSources.has(s) ? "" : " src-added");
    return span;
  }));
  col.querySelector(".col-answer").textContent = data.answer;
  col.querySelector(".col-claims").replaceChildren(
    ...(data.claims || []).map(claimItem));
}

async function compare() {
  const query = document.getElementById("query").value.trim();
  const error = document.getElementById("error");
  const diff = document.getElementById("compare-diff");
  error.textContent = "";
  if (!query) { error.textContent = "Enter a question."; return; }
  diff.textContent = "Comparing ...";
  try {
    const [emp, ana] = await Promise.all(
      ["employee", "analyst"].map((p) => fetchAsk(p, query)));
    renderCompareColumn("employee", emp, new Set(ana.sources));
    renderCompareColumn("analyst", ana, new Set(emp.sources));
    document.getElementById("compare").hidden = false;
    const added = ana.sources.filter((s) => !emp.sources.includes(s));
    const removed = emp.sources.filter((s) => !ana.sources.includes(s));
    diff.textContent = "Analyst adds: " + (added.join(", ") || "nothing") +
      ". Employee-only: " + (removed.join(", ") || "nothing") + ".";
  } catch (e) {
    diff.textContent = "";
    error.textContent = "Compare failed: " + e.message;
  }
}

function renderResult(data) {
  document.getElementById("result").hidden = false;
  document.getElementById("run-id").textContent = data.run_id;
  document.getElementById("result-persona").textContent = data.persona;
  document.getElementById("sources").textContent =
    (data.sources || []).join(", ") || "none";
  document.getElementById("dropped").textContent = data.dropped_count;
  document.getElementById("answer").textContent = data.answer;
  document.getElementById("claims").replaceChildren(
    ...(data.claims || []).map(claimItem));
  const stubsWrap = document.getElementById("stubs-wrap");
  const stubs = data.stubs || [];
  stubsWrap.hidden = stubs.length === 0;
  document.getElementById("stubs").replaceChildren(...stubs.map((s) => {
    const li = document.createElement("li");
    const lic = s.license || {};
    li.textContent = s.source_id + " (" + s.license_class + ") — " +
      [lic.vendor, lic.coverage, lic.expiry].filter(Boolean).join(" · ");
    return li;
  }));
  document.getElementById("conflict").textContent = data.conflict && data.conflict.fired
    ? "Conflict flagged for Steward: " + data.conflict.conflict_id : "";
  if (data.persona === "steward") loadQueue();
}

document.querySelectorAll(".login").forEach((b) =>
  b.addEventListener("click", () => login(b.dataset.persona)));
document.getElementById("ask-form").addEventListener("submit", ask);
document.getElementById("compare-btn").addEventListener("click", compare);
if (!currentPersona()) login("employee");
renderSession();
