// Record real product footage for the demo video from the running app.
// Usage: node video/capture.mjs <outdir> [segment ...]
// Needs the app at http://localhost:8000 (reset first: python video/reset_demo.py).
// Writes <outdir>/<segment>.webm and <outdir>/<segment>.events.json with
// the times (seconds from the start of that recording) when the app was
// waiting on Muse Spark, so the editor can speed only those parts up.
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
  const wait = async (fnWait) => {
    const a = now();
    await fnWait();
    events.push({ type: "wait", start: a, end: now() });
  };
  await page.goto(BASE);
  await sleep(1);
  await fn(page, wait, now, events);
  await sleep(1);
  const v = page.video();
  await ctx.close();
  fs.renameSync(await v.path(), path.join(outDir, name + ".webm"));
  fs.writeFileSync(path.join(outDir, name + ".events.json"), JSON.stringify({ events, total: now() }, null, 1));
  await browser.close();
  console.log("captured", name, now().toFixed(1), "s");
}

async function ask(page, wait, q) {
  await page.fill("#query", "");
  await page.type("#query", q, { delay: 25 });
  await page.click("[data-testid=ask-submit]");
  await wait(() => page.waitForFunction(() => /Answered in/.test(document.getElementById("status").textContent), null, { timeout: 180000 }));
}

async function persona(page, p) { await page.click(`[data-persona=${p}]`); await sleep(0.8); }

await segment("s2-process", async (page, wait) => {
  await persona(page, "employee");
  await ask(page, wait, "How do I process a customer refund?");
  await sleep(4);
  const pdf = page.locator("#answer .notes li", { hasText: "page" }).locator("a.src").first();
  if (await pdf.count()) { await pdf.click(); await sleep(4); await page.click("#panel-close"); }
  const vid = page.locator("#answer .notes li", { hasText: "0:23" }).locator("a.src").first();
  const anyVid = (await vid.count()) ? vid : page.locator("#answer .notes li", { hasText: "in the recording" }).locator("a.src").first();
  await anyVid.click();
  await sleep(6);
  await page.evaluate(() => { const b = document.getElementById("panel-body"); b.scrollTo({ top: b.scrollHeight, behavior: "smooth" }); });
  await sleep(6);
});

await segment("s3-licensed", async (page, wait, now, events) => {
  await persona(page, "employee");
  await ask(page, wait, "Using the chart in the ASEAN report, which country grew fastest in 2024?");
  await sleep(4);
  const c = page.locator("#answer .notes li", { hasText: "page 4" }).locator("a.src").first();
  const found = (await c.count()) > 0;
  events.push({ type: "note", found_page4: found });
  const chip = found ? c : page.locator("#answer .notes a.src").first();
  await chip.click();
  await sleep(7);
});

await segment("s4-seats", async (page, wait) => {
  await persona(page, "analyst");
  await page.click("nav [data-tab=compare]");
  await page.fill("#compare-query", "");
  await page.type("#compare-query", "What is the exact 2023 GDP growth value for Viet Nam in the licensed dataset?", { delay: 15 });
  await page.click("#compare-form button");
  await wait(() => page.waitForFunction(() => document.querySelectorAll("#compare .answer").length === 4, null, { timeout: 240000 }));
  await sleep(5);
  const single = page.locator("#cmp-analyst .notes li", { hasText: "cell" }).locator("a.src").first();
  const cell = (await single.count()) ? single : page.locator("#cmp-analyst .notes a.src").first();
  if (await cell.count()) { await cell.click(); await sleep(6); }
});

await segment("s5-conflict", async (page, wait) => {
  await persona(page, "employee");
  await ask(page, wait, "What was Viet Nam's GDP growth in 2023?");
  await sleep(6);
  await persona(page, "steward");
  await page.click("nav [data-tab=steward]");
  await page.waitForSelector("#conflicts .conflict");
  await sleep(2);
  for (let i = 0; i < 2; i++) {
    const done = await page.evaluate(() => {
      for (const card of document.querySelectorAll("#conflicts .conflict")) {
        const t = card.textContent;
        if (!/Open/.test(card.querySelector(".state").textContent)) continue;
        if (!(t.includes("6.5") && t.includes("ASEAN"))) continue;
        const sides = card.querySelectorAll(".version .who");
        const reportLeft = sides[0].textContent.includes("ASEAN");
        card.querySelector("input").value = "The licensed report uses World Bank data and is the source of record. The deck used an old estimate.";
        const btns = [...card.querySelectorAll("button")].filter((b) => /is right/.test(b.textContent));
        btns[reportLeft ? 0 : 1].click();
        return true;
      }
      return false;
    });
    await sleep(2.5);
    if (!done) break;
  }
  await persona(page, "employee");
  await page.click("nav [data-tab=ask]");
  await ask(page, wait, "What was Viet Nam's GDP growth in 2023?");
  await sleep(7);
});

await segment("s6-upload", async (page, wait) => {
  await persona(page, "manager");
  await page.click("nav [data-tab=videos]");
  await sleep(2);
  await page.setInputFiles("#upload-file", process.env.KOHU_UPLOAD_CLIP || path.join(here, "assets", "stock-check.mp4"));
  await page.fill("#upload-title", "How to check stock for a returned item");
  await page.click("#upload-form button");
  await wait(() => page.waitForFunction(() => /ready for review|failed/.test(document.getElementById("video-status").textContent), null, { timeout: 600000 }));
  await page.waitForSelector(".step");
  await sleep(4);
  await page.evaluate(() => document.querySelector(".step:nth-child(4)")?.scrollIntoView({ behavior: "smooth" }));
  await sleep(4);
  const approve = page.locator(".step .button", { hasText: "Approve" });
  const n = await approve.count();
  for (let i = 0; i < Math.min(n, 2); i++) { await approve.nth(0).click(); await sleep(1.5); }
  await sleep(3);
});

await segment("s7-licenses", async (page) => {
  await persona(page, "steward");
  await page.click("nav [data-tab=licenses]");
  await sleep(8);
});
