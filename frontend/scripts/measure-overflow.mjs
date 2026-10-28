/**
 * Layout overflow diagnostic without external test libraries.
 * Windows-only. Run while `npm run preview -- --port 4173` is active.
 *
 *   node scripts/measure-overflow.mjs            # 390x844 default
 *   WIDTH=1440 HEIGHT=900 node scripts/measure-overflow.mjs
 *   SCHOLARLENS_URL=http://127.0.0.1:4173/search WIDTH=390 node scripts/measure-overflow.mjs
 *
 * Reports document scroll width versus viewport width and every element whose
 * box escapes the viewport horizontally. Read-only: it never edits the page.
 */
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawn } from "node:child_process";

const chrome = process.env.CHROME_PATH || "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const origin = process.env.SCHOLARLENS_URL || "http://127.0.0.1:4173/";
const width = Number(process.env.WIDTH || 390);
const height = Number(process.env.HEIGHT || 844);

if (!fs.existsSync(chrome)) throw new Error("Chrome not found: " + chrome);

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const profile = fs.mkdtempSync(path.join(os.tmpdir(), "scholarlens-measure-"));

const child = spawn(chrome, [
  "--headless=new",
  "--disable-gpu",
  "--hide-scrollbars",
  "--no-first-run",
  "--disable-extensions",
  "--disable-background-networking",
  "--remote-debugging-port=0",
  "--user-data-dir=" + profile,
  "about:blank",
], { stdio: "ignore" });

async function waitPort(timeout = 20000) {
  const file = path.join(profile, "DevToolsActivePort");
  const start = Date.now();
  while (Date.now() - start < timeout) {
    if (fs.existsSync(file)) {
      const lines = fs.readFileSync(file, "utf8").trim().split(/\r?\n/);
      if (lines.length >= 2) return Number(lines[0]);
    }
    await delay(120);
  }
  throw new Error("Chrome did not create a debugging port");
}

function connect(url) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(url);
    const timer = setTimeout(() => reject(new Error("WebSocket connect timeout")), 10000);
    ws.addEventListener("open", () => { clearTimeout(timer); resolve(ws); }, { once: true });
    ws.addEventListener("error", () => { clearTimeout(timer); reject(new Error("WebSocket connect error")); }, { once: true });
  });
}

function makeClient(ws) {
  let serial = 0;
  const pending = new Map();
  const events = new Map();
  ws.addEventListener("message", (event) => {
    const data = JSON.parse(String(event.data));
    if (data.id && pending.has(data.id)) {
      const { resolve, reject, timer } = pending.get(data.id);
      clearTimeout(timer);
      pending.delete(data.id);
      if (data.error) reject(new Error(data.error.message || "CDP error"));
      else resolve(data.result);
      return;
    }
    if (data.method && events.has(data.method)) {
      for (const handler of events.get(data.method)) handler(data.params);
    }
  });
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++serial;
    const timer = setTimeout(() => { pending.delete(id); reject(new Error("CDP timeout: " + method)); }, 20000);
    pending.set(id, { resolve, reject, timer });
    ws.send(JSON.stringify({ id, method, params }));
  });
  const once = (method, timeout = 20000) => new Promise((resolve, reject) => {
    const handler = (params) => { clearTimeout(timer); events.get(method).delete(handler); resolve(params); };
    const timer = setTimeout(() => { events.get(method)?.delete(handler); reject(new Error("Event timeout: " + method)); }, timeout);
    if (!events.has(method)) events.set(method, new Set());
    events.get(method).add(handler);
  });
  const on = (method, handler) => {
    if (!events.has(method)) events.set(method, new Set());
    events.get(method).add(handler);
  };
  return { send, once, on };
}

const EXPRESSION = `(() => {
  const vw = document.documentElement.clientWidth;
  const rows = [];
  for (const el of document.querySelectorAll("body *")) {
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) continue;
    if (r.right > vw + 0.5 || r.left < -0.5) {
      const style = getComputedStyle(el);
      if (style.position === "fixed" && style.pointerEvents === "none") continue;
      rows.push({
        tag: el.tagName.toLowerCase(),
        cls: String(el.className && el.className.baseVal !== undefined ? el.className.baseVal : el.className || "").slice(0, 90),
        id: el.id || "",
        left: Math.round(r.left * 10) / 10,
        right: Math.round(r.right * 10) / 10,
        width: Math.round(r.width * 10) / 10,
        overflowX: Math.round((r.right - vw) * 10) / 10
      });
    }
  }
  rows.sort((a, b) => b.overflowX - a.overflowX);
  return JSON.stringify({
    url: location.href,
    viewport: { clientWidth: vw, innerWidth: window.innerWidth, clientHeight: document.documentElement.clientHeight },
    scrollWidth: document.documentElement.scrollWidth,
    bodyScrollWidth: document.body.scrollWidth,
    horizontalOverflow: document.documentElement.scrollWidth - vw,
    offenders: rows.slice(0, 30),
    offenderCount: rows.length
  });
})()`;

let port;
try {
  port = await waitPort();
  const version = await (await fetch(`http://127.0.0.1:${port}/json/version`)).json();
  const browser = makeClient(await connect(version.webSocketDebuggerUrl));
  const { targetId } = await browser.send("Target.createTarget", { url: "about:blank" });
  const page = makeClient(await connect(`ws://127.0.0.1:${port}/devtools/page/${targetId}`));

  await page.send("Page.enable");
  await page.send("Runtime.enable");
  await page.send("Emulation.setDeviceMetricsOverride", {
    width, height, deviceScaleFactor: 1, mobile: width < 700
  });
  const loaded = page.once("Page.loadEventFired").catch(() => null);
  await page.send("Page.navigate", { url: origin });
  await loaded;
  await delay(1800);

  const { result, exceptionDetails } = await page.send("Runtime.evaluate", {
    expression: EXPRESSION, returnByValue: true, awaitPromise: true
  });
  if (exceptionDetails) throw new Error(exceptionDetails.text || "evaluation failed");

  const report = JSON.parse(result.value);
  console.log(JSON.stringify(report, null, 2));
  console.log(
    `\nSUMMARY ${width}x${height} · scrollWidth ${report.scrollWidth} · viewport ${report.viewport.clientWidth} · overflow ${report.horizontalOverflow}px · offenders ${report.offenderCount}`
  );
  process.exitCode = report.horizontalOverflow > 0 ? 2 : 0;
} finally {
  try { child.kill(); } catch {}
  await delay(200);
  try { fs.rmSync(profile, { recursive: true, force: true }); } catch {}
}
