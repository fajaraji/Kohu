// Print HTML files to PDF with headless Chromium (Playwright).
// Usage: node corpus/tools/html2pdf.mjs in1.html out1.pdf [in2.html out2.pdf ...]
import { createRequire } from "node:module";
import { execSync } from "node:child_process";
// Resolve Playwright locally, else from the global npm root.
const require = createRequire(import.meta.url);
let pw;
try { pw = require("playwright"); }
catch { pw = require(execSync("npm root -g").toString().trim() + "/playwright"); }
const { chromium } = pw;
import path from "node:path";

const args = process.argv.slice(2);
if (args.length === 0 || args.length % 2) {
  console.error("usage: html2pdf.mjs in.html out.pdf [...]");
  process.exit(2);
}
const browser = await chromium.launch();
const page = await browser.newPage();
for (let i = 0; i < args.length; i += 2) {
  await page.goto("file://" + path.resolve(args[i]), { waitUntil: "load" });
  await page.pdf({
    path: args[i + 1], format: "A4", printBackground: true,
    margin: { top: "18mm", bottom: "20mm", left: "16mm", right: "16mm" },
    displayHeaderFooter: true,
    headerTemplate: "<span></span>",
    footerTemplate: await page.evaluate(() =>
      document.querySelector("meta[name=pdf-footer]")?.content || "<span></span>"),
  });
  console.log("wrote " + args[i + 1]);
}
await browser.close();
