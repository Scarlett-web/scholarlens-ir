/**
 * Evaluate an arbitrary expression on a live preview page through the CDP.
 * Windows-only. Run while `npm run preview -- --port 4173` is active.
 *
 *   node scripts/probe-dom.mjs --url / --width 1440 --expr "document.title"
 *   node scripts/probe-dom.mjs --url / --selector ".sidebar-signature-mark" --styles background,color
 *
 * Read-only: it never mutates the page or the filesystem.
 */
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawn } from "node:child_process";

const chrome = process.env.CHROME_PATH || "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const origin = process.env.SCHOLARLENS_URL || "http://127.0.0.1:4173";

const argv = process.argv.slice(2);
const argValue = (flag, fallback) => {
  const index = argv.indexOf(flag);
  return index >= 0 && argv[index + 1] ? argv[index + 1] : fallback;
};
const url = origin + argValue("--url", "/");
const width = Number(argValue("--width", "1440"));
const height = Number(argValue("--height", "900"));
const selector = argValue("--selector", "");
const styleList = argValue("--styles", "").split(",").map((item) => item.trim()).filter(Boolean);
const expr = argValue("--expr", "");

const buildExpression = () => {
  if (expr) return expr;
  if (!selector) throw new Error("Provide --expr or --selector");
  const styleProbe = styleList.map((name) => `${JSON.stringify(name)}:getComputedStyle(el).getPropertyValue(${JSON.stringify(name)})`).join(",");
  return `(() => {
    const el = document.querySelector(${JSON.stringify(selector)});
    if (!el) return JSON.stringify({ error: "selector not found", selector: ${JSON.stringify(selector)} });
    const r = el.getBoundingClientRect();
    return JSON.stringify({
      selector: ${JSON.stringify(selector)},
      rect: { left: r.left, top: r.top, right: r.right, bottom: r.bottom, width: r.width, height: r.height },
      styles: { ${styleProbe} },
      text: (el.textContent || "").trim().slice(0, 120)
    });
  })()`;
};

if (!fs.existsSync(chrome)) throw new Error("Chrome not found: " + chrome);
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const profile = fs.mkdtempSync(path.join(os.tmpdir(), "scholarlens-probe-"));

const child = spawn(chrome, [
  "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
  "--disable-extensions", "--disable-background-networking",
  "--remote-debugging-port=0", "--user-data-dir=" + profile, "about:blank",
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

function connect(target) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(target);
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
    if (data.method && events.has(data.method)) for (const handler of events.get(data.method)) handler(data.params);
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
  return { send, once };
}

try {
  const port = await waitPort();
  const version = await (await fetch(`http://127.0.0.1:${port}/json/version`)).json();
  const browser = makeClient(await connect(version.webSocketDebuggerUrl));
  const { targetId } = await browser.send("Target.createTarget", { url: "about:blank" });
  const page = makeClient(await connect(`ws://127.0.0.1:${port}/devtools/page/${targetId}`));

  await page.send("Page.enable");
  await page.send("Runtime.enable");
  await page.send("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 1, mobile: width < 700 });
  const loaded = page.once("Page.loadEventFired").catch(() => null);
  await page.send("Page.navigate", { url });
  await loaded;
  await delay(1600);

  const { result, exceptionDetails } = await page.send("Runtime.evaluate", {
    expression: buildExpression(), returnByValue: true, awaitPromise: true,
  });
  if (exceptionDetails) throw new Error(exceptionDetails.text || JSON.stringify(exceptionDetails));
  const value = result.value;
  try { console.log(JSON.stringify(JSON.parse(value), null, 2)); }
  catch { console.log(typeof value === "string" ? value : JSON.stringify(value, null, 2)); }
} finally {
  try { child.kill(); } catch {}
  await delay(200);
  try { fs.rmSync(profile, { recursive: true, force: true }); } catch {}
}
