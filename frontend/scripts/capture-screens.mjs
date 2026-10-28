/**
 * Viewport-accurate screenshots through the Chrome DevTools Protocol.
 * Windows-only. Run while `npm run preview -- --port 4173` is active.
 *
 *   node scripts/capture-screens.mjs --out ../../output/shots --prefix after
 *
 * Why not `chrome --headless --screenshot --window-size`? That path rasterises a
 * window, so the captured viewport drifts from the requested CSS width and the
 * right edge looks clipped. Emulation.setDeviceMetricsOverride pins the exact
 * CSS viewport, which is what responsive review needs.
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
const outDir = path.resolve(process.cwd(), argValue("--out", "screens"));
const prefix = argValue("--prefix", "screen");
const only = argValue("--only", "");
const glass = argValue("--glass", "");

const TARGETS = [
  { name: "home", url: "/", width: 1440, height: 900 },
  { name: "home-mobile", url: "/", width: 390, height: 844, mobile: true },
  { name: "search", url: "/search", width: 1440, height: 900 },
  { name: "search-mobile", url: "/search", width: 390, height: 844, mobile: true },
  { name: "library", url: "/library", width: 1440, height: 900 },
  { name: "explore", url: "/explore", width: 1440, height: 900 },
  { name: "paper", url: "/paper/demo-003", width: 1440, height: 1000 },
  { name: "account-mobile", url: "/account", width: 390, height: 844, mobile: true },
];

const queue = TARGETS.filter((target) => !only || target.name.includes(only));

if (!fs.existsSync(chrome)) throw new Error("Chrome not found: " + chrome);
fs.mkdirSync(outDir, { recursive: true });

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const profile = fs.mkdtempSync(path.join(os.tmpdir(), "scholarlens-shots-"));

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
    if (data.method && events.has(data.method)) for (const handler of events.get(data.method)) handler(data.params);
  });
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++serial;
    const timer = setTimeout(() => { pending.delete(id); reject(new Error("CDP timeout: " + method)); }, 25000);
    pending.set(id, { resolve, reject, timer });
    ws.send(JSON.stringify({ id, method, params }));
  });
  const once = (method, timeout = 25000) => new Promise((resolve, reject) => {
    const handler = (params) => { clearTimeout(timer); events.get(method).delete(handler); resolve(params); };
    const timer = setTimeout(() => { events.get(method)?.delete(handler); reject(new Error("Event timeout: " + method)); }, timeout);
    if (!events.has(method)) events.set(method, new Set());
    events.get(method).add(handler);
  });
  return { send, once };
}

const results = [];
try {
  const port = await waitPort();
  const version = await (await fetch(`http://127.0.0.1:${port}/json/version`)).json();
  const browser = makeClient(await connect(version.webSocketDebuggerUrl));
  const { targetId } = await browser.send("Target.createTarget", { url: "about:blank" });
  const page = makeClient(await connect(`ws://127.0.0.1:${port}/devtools/page/${targetId}`));

  await page.send("Page.enable");
  await page.send("Runtime.enable");

  if (glass) {
    // Persist a surface preset before the app boots so the shell renders with it.
    await page.send("Page.addScriptToEvaluateOnNewDocument", {
      source: `try{localStorage.setItem("scholarlens-v1:glass",JSON.stringify(${JSON.stringify(glass)}))}catch(e){}`,
    });
  }

  for (const target of queue) {
    await page.send("Emulation.setDeviceMetricsOverride", {
      width: target.width,
      height: target.height,
      deviceScaleFactor: 1,
      mobile: Boolean(target.mobile),
    });
    const loaded = page.once("Page.loadEventFired").catch(() => null);
    await page.send("Page.navigate", { url: origin + target.url });
    await loaded;
    await delay(2200);

    const { data } = await page.send("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
    const file = path.join(outDir, `${prefix}-${target.name}.png`);
    fs.writeFileSync(file, Buffer.from(data, "base64"));

    const { result } = await page.send("Runtime.evaluate", {
      expression: `JSON.stringify({scrollWidth:document.documentElement.scrollWidth,clientWidth:document.documentElement.clientWidth,title:document.title})`,
      returnByValue: true,
    });
    const meta = JSON.parse(result.value);
    results.push({ name: target.name, file, width: target.width, height: target.height, ...meta });
    console.log(`${target.name.padEnd(16)} ${target.width}x${target.height}  scroll=${meta.scrollWidth}/${meta.clientWidth}  ${path.basename(file)}`);
  }
} finally {
  try { child.kill(); } catch {}
  await delay(200);
  try { fs.rmSync(profile, { recursive: true, force: true }); } catch {}
}

const overflowing = results.filter((item) => item.scrollWidth > item.clientWidth);
console.log(`\nCaptured ${results.length} screens into ${outDir}`);
if (overflowing.length) {
  console.log("HORIZONTAL OVERFLOW: " + overflowing.map((item) => `${item.name} +${item.scrollWidth - item.clientWidth}px`).join(", "));
  process.exitCode = 2;
}
