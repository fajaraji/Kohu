// Record the demo clip of corpus/demo-app with Playwright.
// Usage: node record.mjs <durations.json> <outdir>
// durations.json: [seconds of narration per step]. Writes outdir/raw.webm,
// outdir/truth.json (step start times, action times, target boxes) and
// outdir/step-NN.png (frame just before each action, for SAM checks).
import { createRequire } from "node:module";
import { execSync } from "node:child_process";
// Resolve Playwright locally, else from the global npm root.
const require = createRequire(import.meta.url);
let pw;
try { pw = require("playwright"); }
catch { pw = require(execSync("npm root -g").toString().trim() + "/playwright"); }
const { chromium } = pw;
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const [durFile, outDir] = process.argv.slice(2);
const script = JSON.parse(fs.readFileSync(path.join(here, "script.json"), "utf8"));
const durations = JSON.parse(fs.readFileSync(durFile, "utf8"));
fs.mkdirSync(outDir, { recursive: true });
const W = 1280, H = 720, GAP = 0.8, LEAD = 0.5;

const browser = await chromium.launch();
const context = await browser.newContext({
  viewport: { width: W, height: H },
  recordVideo: { dir: outDir, size: { width: W, height: H } },
});
const page = await context.newPage();
const t0 = Date.now();
const now = () => (Date.now() - t0) / 1000;
const sleep = (s) => new Promise((r) => setTimeout(r, Math.max(0, s * 1000)));
await page.goto("file://" + path.join(here, "index.html"));
await sleep(1.0);

const truth = [];
for (let i = 0; i < script.steps.length; i++) {
  const step = script.steps[i];
  const start = now();
  const rec = { n: i, start, say: step.say, target: step.target || null,
                reason: step.reason || null, action: step.action };
  await sleep(LEAD);
  if (step.action) {
    const el = page.locator(step.selector).first();
    const box = await el.boundingBox();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2, { steps: 8 });
    await sleep(0.3);
    rec.box = { x1: Math.round(box.x), y1: Math.round(box.y),
                x2: Math.round(box.x + box.width), y2: Math.round(box.y + box.height), w: W, h: H };
    rec.frame = `step-${String(i).padStart(2, "0")}.png`;
    await page.screenshot({ path: path.join(outDir, rec.frame) });
    rec.action_at = now();
    if (step.action === "click") await el.click();
    else if (step.action === "fill") await el.pressSequentially(step.value, { delay: 90 });
    else if (step.action === "select") await el.selectOption(step.value);
    else if (step.action === "search") {
      await el.click();
      await el.pressSequentially(step.value, { delay: 90 });
      await page.locator("#search-btn").click();
    }
  }
  const spent = now() - start;
  await sleep(durations[i] + GAP - spent);
  rec.end = now();
  truth.push(rec);
}
await sleep(1.0);
const video = page.video();
await context.close();
fs.renameSync(await video.path(), path.join(outDir, "raw.webm"));
fs.writeFileSync(path.join(outDir, "truth.json"), JSON.stringify({ width: W, height: H, steps: truth, total: now() }, null, 1));
await browser.close();
console.log("recorded", truth.length, "steps,", now().toFixed(1), "s");
