// Record real product footage for the demo video from the running app.
// Usage: node video/capture.mjs <outdir> [segment ...]
// Needs the app at http://localhost:8000 (reset first: python video/reset_demo.py).
// Writes <outdir>/<segment>.webm and <outdir>/<segment>.events.json with
//   wait  : when the app was waiting on Muse Spark (the editor speeds only these up)
//   focus : the box of what matters on screen from a moment on (the editor zooms there)
//   clear : zoom back out
// Set KOHU_UPLOAD_CLIP to a recording the model has not processed before,
// otherwise the upload segment comes back from the model cache instantly.
import { createRequire } from "node:module";
import { execSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
let pw;
try { pw = require("playwright"); }
catch { pw = require(execSync("npm root -g").toString().trim() + "/playwright"); }
const { chromium } = pw;
const here = path.dirname(fileURLToPath(import.meta.url));
const [outDir, ...only] = process.argv.slice(2);
fs.mkdirSync(outDir, { recursive: true });
const BASE = "http://localhost:8000/";
const sleep = (s) => new Promise((r) => setTimeout(r, s * 1000));

async function segment(name, fn) {
  if (only.length && !only.includes(name)) return;
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 720 },
    recordVideo: { dir: outDir, size: { width: 1280, height: 720 } } });
  const page = await ctx.newPage();
  const t0 = Date.now();
  const events = [];
  const now = () => (Date.now() - t0) / 1000;
  const h = {
    page, events, now,
    wait: async (fnWait) => { const a = now(); await fnWait(); events.push({ type: "wait", start: a, end: now() }); },
    focus: async (locator, pad = 16) => {
      const b = await locator.boundingBox();
      if (!b) return;
      const x1 = Math.max(0, b.x - pad), y1 = Math.max(0, b.y - pad);
      const x2 = Math.min(1280, b.x + b.width + pad), y2 = Math.min(720, b.y + b.height + pad);
      events.push({ type: "focus", t: now(), rect: [x1, y1, x2, y2] });
    },
    clear: () => events.push({ type: "clear", t: now() }),
  };
  await page.goto(BASE);
  await sleep(1);
  await fn(h);
  await sleep(1);
  const v = page.video();
  await ctx.close();
  fs.renameSync(await v.path(), path.join(outDir, name + ".webm"));
  fs.writeFileSync(path.join(outDir, name + ".events.json"), JSON.stringify({ events, total: now() }, null, 1));
  await browser.close();
  console.log("captured", name, now().toFixed(1), "s");
}

async function ask(h, q) {
  const { page } = h;
  await page.click("#query");
  await page.fill("#query", "");
  await page.type("#query", q, { delay: 28 });
  await sleep(0.3);
  await page.keyboard.press("Enter");
  await sleep(1.2);
  await h.focus(page.locator("#ask-form"), 24);
  await h.wait(() => page.waitForFunction(() => /Answered in/.test(document.getElementById("status").textContent), null, { timeout: 180000 }));
  h.clear();
  await page.locator("#answer .answer").evaluate((e) => e.scrollIntoView({ behavior: "smooth", block: "start" }));
  await sleep(0.9);
  await h.focus(page.locator("#answer .answer-text"), 20);
  await sleep(3.2);
}

// Sign in as a demo account; from inside the app, go through "Switch".
async function persona(page, p) {
  if (await page.locator("#signin").isHidden()) { await page.click("#switch-account"); await sleep(0.6); }
  await page.click(`.account[data-persona=${p}]`);
  await sleep(0.8);
}
const note = (page, text) => page.locator("#answer .notes li", { hasText: text }).locator("a.src").first();

await segment("s2-process", async (h) => {
  const { page } = h;
  await persona(page, "employee");
  await ask(h, "How do I process a customer refund?");
  const pdf = note(page, "page");
  if (await pdf.count()) {
    await pdf.click(); await sleep(1.0);
    await h.focus(page.locator("#panel"), 0); await sleep(3.2);
    await page.click("#panel-close"); h.clear(); await sleep(0.4);
  }
  const vid = (await note(page, "0:23").count()) ? note(page, "0:23") : note(page, "in the recording");
  await vid.click(); await sleep(1.2);
  await h.focus(page.locator("#panel"), 0);
  await sleep(4);
  await page.evaluate(() => { const b = document.getElementById("panel-body"); b.scrollTo({ top: b.scrollHeight, behavior: "smooth" }); });
  await sleep(1.0);
  const marked = page.locator("#panel-body .marked").last();
  if (await marked.count()) await h.focus(marked, 8);
  await sleep(4.5);
});

await segment("s3-licensed", async (h) => {
  const { page, events } = h;
  await persona(page, "employee");
  await ask(h, "Using the chart in the ASEAN report, which country grew fastest in 2024?");
  const inset = page.locator("#answer .inset").first();
  if (await inset.count()) { await h.focus(inset, 14); await sleep(2.5); }
  const c = note(page, "page 4");
  const found = (await c.count()) > 0;
  events.push({ type: "note", found_page4: found });
  await (found ? c : page.locator("#answer .notes a.src").first()).click();
  await sleep(1.4);
  const marked = page.locator("#panel-body .marked").first();
  await h.focus((await marked.count()) ? marked : page.locator("#panel"), 6);
  await sleep(5);
});

await segment("s4-seats", async (h) => {
  const { page } = h;
  await persona(page, "analyst");
  await page.click("nav [data-tab=compare]");
  await page.fill("#compare-query", "");
  await page.type("#compare-query", "What is the exact 2023 GDP growth value for Viet Nam in the licensed dataset?", { delay: 12 });
  await page.click("#compare-form button");
  await sleep(0.8);
  await h.wait(() => page.waitForFunction(() => document.querySelectorAll("#compare .answer").length === 4, null, { timeout: 240000 }));
  await page.locator("#compare").evaluate((e) => e.scrollIntoView({ behavior: "smooth", block: "start" }));
  await sleep(1.0);
  await h.focus(page.locator("#compare"), 8);
  await sleep(3.5);
  await h.focus(page.locator("#cmp-analyst"), 10);
  await sleep(2.0);
  const single = page.locator("#cmp-analyst .notes li", { hasText: "cell" }).locator("a.src").first();
  const cell = (await single.count()) ? single : page.locator("#cmp-analyst .notes a.src").first();
  if (await cell.count()) {
    await cell.click(); await sleep(1.2);
    await h.focus(page.locator("#panel-body .grid-wrap"), 10);
    await sleep(4.5);
  }
});

await segment("s5-conflict", async (h) => {
  const { page } = h;
  await persona(page, "employee");
  await ask(h, "What was Viet Nam's GDP growth in 2023?");
  const warn = page.locator("#answer .warning").first();
  if (await warn.count()) {
    await warn.evaluate((e) => e.scrollIntoView({ behavior: "smooth", block: "center" })); await sleep(0.8);
    await h.focus(warn, 12); await sleep(3.5);
  }
  h.clear();
  await persona(page, "steward");
  await page.click("nav [data-tab=steward]");
  await page.waitForSelector("#conflicts .conflict");
  await sleep(1.2);
  const target = page.locator("#conflicts .conflict", { hasText: "real GDP growth as 5.0" }).first();
  const card = (await target.count()) ? target : page.locator("#conflicts .conflict", { hasText: "6.5" }).first();
  await card.evaluate((e) => e.scrollIntoView({ behavior: "smooth", block: "center" })); await sleep(0.8);
  await h.focus(card, 10);
  await sleep(1.0);
  await card.locator("input").type("The licensed report uses World Bank data and is the source of record.", { delay: 14 });
  const reportLeft = (await card.locator(".version .who").first().textContent()).includes("ASEAN");
  await card.locator("button", { hasText: reportLeft ? "Left is right" : "Right is right" }).click();
  await sleep(2.0);
  // The other deck-versus-report conflict, decided the same way.
  const other = page.locator("#conflicts .conflict", { hasText: "fastest in 2023" }).first();
  if (await other.count() && (await other.locator("button", { hasText: "is right" }).count())) {
    const left = (await other.locator(".version .who").first().textContent()).includes("ASEAN");
    await other.locator("button", { hasText: left ? "Left is right" : "Right is right" }).click();
    await sleep(1.0);
  }
  h.clear();
  await persona(page, "employee");
  await page.click("nav [data-tab=ask]");
  await sleep(0.6);
  await ask(h, "What was Viet Nam's GDP growth in 2023?");
  const decided = page.locator("#answer .inset.decided").first();
  if (await decided.count()) { await h.focus(decided, 12); await sleep(3.5); }
});

await segment("s6-upload", async (h) => {
  const { page } = h;
  await persona(page, "manager");
  await page.click("nav [data-tab=videos]");
  await sleep(1.5);
  await h.focus(page.locator("#upload-form"), 12);
  await page.setInputFiles("#upload-file", process.env.KOHU_UPLOAD_CLIP || path.join(here, "assets", "stock-check.mp4"));
  await page.fill("#upload-title", "How to check stock for a returned item");
  await page.click("#upload-form button");
  await sleep(1.0);
  h.clear();
  await h.wait(() => page.waitForFunction(() => /ready for review|failed/.test(document.getElementById("video-status").textContent), null, { timeout: 600000 }));
  await page.waitForSelector(".step");
  await sleep(1.0);
  await h.focus(page.locator("#steps"), 6);
  await sleep(3.0);
  const withReason = page.locator(".step", { hasText: "Why:" }).first();
  if (await withReason.count()) {
    await withReason.evaluate((e) => e.scrollIntoView({ behavior: "smooth", block: "center" })); await sleep(0.8);
    await h.focus(withReason, 8); await sleep(3.0);
    const approve = withReason.locator(".button", { hasText: "Approve" });
    if (await approve.count()) { await approve.click(); await sleep(1.5); }
  }
});

await segment("s7-licenses", async (h) => {
  const { page } = h;
  await persona(page, "steward");
  await page.click("nav [data-tab=licenses]");
  await sleep(1.2);
  await h.focus(page.locator(".licence").first(), 10);
  await sleep(5);
});
