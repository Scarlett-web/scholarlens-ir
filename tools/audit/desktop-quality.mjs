/**
 * Read-only desktop quality pass for the local ScholarLens preview.
 *
 * The pass owns a temporary Playwright profile, blocks all non-loopback
 * network traffic and every non-read request, and writes a fresh report under
 * tools/audit/reports. It is intentionally not a production scanner or an
 * accessibility certification.
 */
import assert from "node:assert/strict";
import {mkdtempSync, mkdirSync, rmSync, writeFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {fileURLToPath} from "node:url";
import {randomBytes} from "node:crypto";
import {chromium} from "playwright";

const root = fileURLToPath(new URL("../../", import.meta.url));
const reportRoot = join(root, "tools/audit/reports");
const target = process.env.SCHOLARLENS_URL || "http://127.0.0.1:4174";
const targetUrl = new URL(target);
const selfTest = process.argv.includes("--self-test");
const normalizeHost = value => value.replace(/^\[|\]$/g, "");
const allowedHosts = new Set(["localhost", "127.0.0.1", "::1"]);

function validateTarget(raw) {
  const value = new URL(raw);
  assert.ok(["http:", "https:"].includes(value.protocol), "Target must use HTTP or HTTPS");
  assert.equal(value.username, "", "Target URL must not contain credentials");
  assert.equal(value.password, "", "Target URL must not contain credentials");
  assert.ok(allowedHosts.has(normalizeHost(value.hostname)), "desktop-quality only accepts an exact loopback host");
  return value;
}

validateTarget(target);

const stamp = new Date().toISOString().replace(/[:.]/g, "-");
const nonce = randomBytes(4).toString("hex");
const output = join(reportRoot, `desktop-quality-${stamp}-${nonce}`);

const routePlan = [
  {name: "home", path: "/"},
  {name: "search", path: "/search"},
  {name: "explore", path: "/explore"},
  {name: "library", path: "/library"},
  {name: "account", path: "/account"},
  {name: "assistant", path: "/assistant"},
  {name: "evaluation", path: "/evaluation"},
  {name: "upload", path: "/upload"},
  {name: "admin", path: "/admin"},
  {name: "not-found", path: "/__desktop_quality_not_found__"},
];
const widths = [1440, 1366];
const mobileWidth = 390;
// Keep dynamic paper-route probing bounded while covering the current unique
// paper links across all desktop routes and both desktop viewports.
const maxDynamicPaperProbes = 64;
const browsers = [
  {name: "chrome", channel: "chrome"},
  {name: "edge", channel: "msedge"},
];

const report = {
  passed: false,
  target,
  started_at: new Date().toISOString(),
  scope: "localhost-only, guest, read-only desktop UI quality pass; no production scan, account write, upload, approval, AI provider or load test",
  tools: {playwright: "project-local", browsers: {}} ,
  policy: {
    loopback_only: true,
    non_loopback_requests: "blocked_and_recorded",
    non_read_requests: "blocked_and_recorded",
    external_links: "recorded_only",
    temporary_profile: true,
  },
  checks: [],
  routes: [],
  browser_errors: [],
  external_requests: [],
  blocked_writes: [],
  external_links: [],
  screenshots: [],
  skipped: [],
};

function safeUrl(value) {
  try {
    const url = new URL(value);
    return `${url.protocol}//${url.host}${url.pathname}`;
  } catch {
    return String(value).slice(0, 240);
  }
}

function isLoopback(url) {
  const hostname = normalizeHost(url.hostname);
  return ["http:", "https:"].includes(url.protocol) &&
    allowedHosts.has(hostname);
}

function isAllowedRequest(url) {
  return isLoopback(url) && url.origin === targetUrl.origin;
}

function isReadMethod(method) {
  return ["GET", "HEAD", "OPTIONS"].includes(String(method).toUpperCase());
}

function accessibleName(parts) {
  return [parts.ariaLabel, parts.ariaLabelledBy, parts.labelText, parts.wrappedLabelText, parts.title, parts.text]
    .map(value => String(value || "").replace(/\s+/g, " ").trim())
    .find(Boolean) || "";
}

function routeKind(path) {
  if (routePlan.some(route => route.path === path)) return "fixed";
  if (/^\/paper\/[^/?#]+$/.test(path)) return "paper";
  return "unknown";
}

function dedupeProbePaths(paths) {
  return [...new Set(paths)];
}

function pushUnique(list, value) {
  if (!list.some(item => JSON.stringify(item) === JSON.stringify(value))) list.push(value);
}

function runSelfTest() {
  assert.doesNotThrow(() => validateTarget("http://127.0.0.1:4174"));
  assert.throws(() => validateTarget("https://127.example:4174"));
  assert.throws(() => validateTarget("http://127.0.0.2:4174"));
  assert.throws(() => validateTarget("https://example.com"));
  assert.equal(isAllowedRequest(new URL(targetUrl.href)), true);
  assert.equal(isAllowedRequest(new URL(`${targetUrl.protocol}//${targetUrl.hostname}:8000/`)), false);
  assert.equal(isAllowedRequest(new URL("http://localhost:4174/")), targetUrl.origin === "http://localhost:4174");
  assert.equal(isReadMethod("GET"), true);
  assert.equal(isReadMethod("POST"), false);
  assert.equal(accessibleName({placeholder: "Only placeholder"}), "");
  assert.equal(accessibleName({wrappedLabelText: "Wrapped field", placeholder: "hint"}), "Wrapped field");
  assert.equal(accessibleName({ariaLabelledBy: "Visible heading", placeholder: "hint"}), "Visible heading");
  assert.equal(routeKind("/search"), "fixed");
  assert.equal(routeKind("/paper/source-sha256:fixture"), "paper");
  assert.equal(routeKind("/unknown-spa-path"), "unknown");
  assert.deepEqual(dedupeProbePaths(["/search", "/search", "/paper/a"]), ["/search", "/paper/a"]);
  console.log("desktop-quality self-test passed: target, origin, read-only, accessible-name and SPA route guards");
}

if (selfTest) {
  runSelfTest();
  process.exit(0);
}

mkdirSync(output, {recursive: true});

async function inspectPage(page, browserName, viewport, route, probePage, linkProbeCache, probeBudget) {
  const errors = [];
  const failedRequests = [];
  const responses = [];
  const onConsole = message => {
    if (message.type() === "error") errors.push({type: "console:error", text: message.text().slice(0, 500)});
  };
  const onPageError = error => errors.push({type: "pageerror", text: String(error).slice(0, 500)});
  const onRequestFailed = request => {
    try {
      // Non-target requests are intentionally aborted by the policy route;
      // they belong in external_requests, not in the page's local failure list.
      if (!isAllowedRequest(new URL(request.url()))) return;
    } catch {}
    failedRequests.push({method: request.method(), url: safeUrl(request.url()), failure: request.failure()?.errorText || "unknown"});
  };
  const onResponse = response => {
    if (response.status() >= 500) responses.push({status: response.status(), url: safeUrl(response.url())});
  };
  page.on("console", onConsole);
  page.on("pageerror", onPageError);
  page.on("requestfailed", onRequestFailed);
  page.on("response", onResponse);

  const entry = {browser: browserName, viewport, route: route.path, name: route.name, status: "failed"};
  try {
    const response = await page.goto(new URL(route.path, targetUrl).href, {waitUntil: "domcontentloaded", timeout: 20000});
    await page.waitForSelector("#root", {timeout: 10000});
    // A root node only proves that React mounted. Wait for the page-level
    // heading as the finite, route-independent ready signal before measuring.
    await page.waitForSelector("main h1, h1", {state: "visible", timeout: 10000});
    await page.waitForFunction(() => Boolean(document.querySelector("main h1, h1")?.textContent?.trim()), undefined, {timeout: 10000});
    try {
      await page.waitForLoadState("networkidle", {timeout: 2500});
      entry.network_idle = {status: "observed"};
    } catch (error) {
      // Background polling can keep a page busy; record the timeout without
      // turning a usable page into a false route failure.
      entry.network_idle = {status: "timeout", error: String(error).slice(0, 240)};
    }
    await page.waitForTimeout(180);
    entry.http_status = response?.status() ?? null;
    entry.headers = response ? {
      "cache-control": response.headers()["cache-control"] || null,
      "content-security-policy": response.headers()["content-security-policy"] || null,
      "x-content-type-options": response.headers()["x-content-type-options"] || null,
      "x-frame-options": response.headers()["x-frame-options"] || null,
    } : {};
    entry.dom = await page.evaluate(() => {
      const visible = element => {
        const style = getComputedStyle(element);
        const rect = element.getBoundingClientRect();
        return style.visibility !== "hidden" && style.display !== "none" && rect.width > 0 && rect.height > 0;
      };
      const text = element => (element.textContent || "").replace(/\s+/g, " ").trim().slice(0, 180);
      const controls = [...document.querySelectorAll("button, input, select, textarea, [role='button']")].map(element => {
        const id = element.id;
        const label = id ? [...document.querySelectorAll("label")].find(item => item.htmlFor === id) : null;
        const wrappedLabel = element.closest("label");
        const ariaLabelledBy = element.getAttribute("aria-labelledby") ? element.getAttribute("aria-labelledby").split(/\s+/).map(value => document.getElementById(value)?.textContent || "").join(" ") : "";
        const name = [element.getAttribute("aria-label"), ariaLabelledBy, label?.textContent, wrappedLabel?.textContent, element.getAttribute("title"), text(element)]
          .map(value => String(value || "").replace(/\s+/g, " ").trim()).find(Boolean) || "";
        return {tag: element.tagName.toLowerCase(), type: element.getAttribute("type"), name: name.slice(0, 120), placeholder: element.getAttribute("placeholder"), visible: visible(element)};
      });
      const links = [...document.querySelectorAll("a")].map(element => ({
        href: element.getAttribute("href"),
        text: text(element),
        target: element.getAttribute("target"),
      }));
      const parsedLinks = links.map(link => {
        try {
          const url = new URL(link.href || "", location.href);
          return {...link, raw_href: link.href, href: url.href, protocol: url.protocol, origin: url.origin, path: url.pathname};
        } catch {
          return {...link, raw_href: link.href, protocol: "invalid", origin: "", path: ""};
        }
      });
      const viewport = {width: innerWidth, height: innerHeight, scrollWidth: document.documentElement.scrollWidth, scrollHeight: document.documentElement.scrollHeight};
      const offscreen = [...document.querySelectorAll("button, a[href], input, select, textarea")].filter(element => {
        if (!visible(element)) return false;
        const rect = element.getBoundingClientRect();
        return rect.left < -4 || rect.right > innerWidth + 4;
      }).length;
      return {
        title: document.title,
        main_count: document.querySelectorAll("main").length,
        h1_count: document.querySelectorAll("h1").length,
        body_text: text(document.body),
        controls,
        links: parsedLinks,
        viewport,
        overflow_x: document.documentElement.scrollWidth > innerWidth + 1,
        offscreen_controls: offscreen,
        reduced_motion: matchMedia("(prefers-reduced-motion: reduce)").matches,
        loading_nodes: document.querySelectorAll("[aria-busy='true'], [data-loading='true']").length,
        alert_nodes: document.querySelectorAll("[role='alert']").length,
      };
    });
    const dom = entry.dom;
    const unlabeled = dom.controls.filter(control => control.visible && !control.name);
    const invalidLinks = dom.links.filter(link => !link.raw_href || link.raw_href === "#" || link.protocol === "invalid" || link.protocol === "javascript:");
    const internalLinks = dom.links.filter(link => link.origin === targetUrl.origin && ["http:", "https:"].includes(link.protocol));
    const externalLinks = dom.links.filter(link => link.origin && link.origin !== targetUrl.origin && ["http:", "https:"].includes(link.protocol));
    for (const link of externalLinks) pushUnique(report.external_links, {browser: browserName, route: route.path, href: safeUrl(link.href)});
    const linkCandidates = dedupeProbePaths(internalLinks.map(link => `${link.path}${new URL(link.href).search}`)
      .filter(path => !path.startsWith("/api/") && !path.startsWith("/assets/") && !path.startsWith("/images/") && path !== "/robots.txt"));
    const unknownLinks = linkCandidates.filter(path => routeKind(path.split("?")[0]) === "unknown");
    const dynamicLinks = linkCandidates.filter(path => routeKind(path.split("?")[0]) === "paper");
    const linkStatus = [];
    for (const path of linkCandidates.filter(item => routeKind(item.split("?")[0]) === "fixed")) {
      linkStatus.push({path, status: 200, kind: "fixed-route", evidence: "route_plan"});
    }
    for (const path of dynamicLinks) {
      if (linkProbeCache.has(path)) {
        linkStatus.push(linkProbeCache.get(path));
        continue;
      }
      if (probeBudget.remaining <= 0) {
        const skipped = {path, status: null, kind: "paper", reason: "probe_budget_exhausted"};
        linkProbeCache.set(path, skipped);
        linkStatus.push(skipped);
        continue;
      }
      probeBudget.remaining -= 1;
      const probe = {path, status: null, kind: "paper", evidence: "rendered_route"};
      try {
        await probePage.goto(new URL(path, targetUrl).href, {waitUntil: "domcontentloaded", timeout: 12000});
        await probePage.waitForSelector("#root", {timeout: 8000});
        await probePage.waitForSelector("main h1, h1, .missing-page, .detail-page .error-state", {state: "visible", timeout: 8000});
        const state = await probePage.evaluate(() => ({
          missing: Boolean(document.querySelector(".missing-page")),
          detailError: Boolean(document.querySelector(".detail-page .error-state")),
          heading: Boolean(document.querySelector("main h1, h1")),
        }));
        probe.status = state.missing || state.detailError || !state.heading ? 404 : 200;
        if (probe.status !== 200) probe.reason = state.missing ? "rendered_not_found" : "rendered_detail_error";
      } catch (error) {
        probe.reason = String(error).slice(0, 240);
      }
      linkProbeCache.set(path, probe);
      linkStatus.push(probe);
    }
    for (const path of unknownLinks) linkStatus.push({path, status: null, kind: "unknown", reason: "unrecognized_spa_route"});
    const deadLinks = linkStatus.filter(item => item.status === null || item.status >= 400);
    entry.assertions = {
      title: Boolean(dom.title),
      main: dom.main_count === 1,
      heading: dom.h1_count >= 1,
      no_horizontal_overflow: !dom.overflow_x,
      no_offscreen_controls: dom.offscreen_controls === 0,
      controls_have_accessible_names: unlabeled.length === 0,
      links_parse: invalidLinks.length === 0,
      internal_links_reachable: deadLinks.length === 0,
      internal_links: internalLinks.length,
      external_links: externalLinks.length,
      reduced_motion_context: dom.reduced_motion,
    };
    entry.unlabeled_controls = unlabeled.slice(0, 20);
    entry.invalid_links = invalidLinks.slice(0, 20);
    entry.unrecognized_internal_links = unknownLinks.slice(0, 20);
    entry.internal_link_status = linkStatus;
    entry.failed_requests = failedRequests;
    entry.console_errors = errors;
    entry.server_errors = responses;
    entry.status = response && response.status() < 400 && entry.assertions.title && entry.assertions.main && entry.assertions.heading && entry.assertions.no_horizontal_overflow && entry.assertions.no_offscreen_controls && entry.assertions.controls_have_accessible_names && entry.assertions.links_parse && entry.assertions.internal_links_reachable ? "passed" : "failed";
    if (errors.length || failedRequests.length || responses.length) entry.status = "failed";
  } catch (error) {
    entry.error = String(error).slice(0, 800);
    entry.console_errors = errors;
    entry.failed_requests = failedRequests;
    entry.server_errors = responses;
  } finally {
    page.off("console", onConsole);
    page.off("pageerror", onPageError);
    page.off("requestfailed", onRequestFailed);
    page.off("response", onResponse);
  }
  report.routes.push(entry);
  return entry;
}

async function inspectBrowser(browserSpec) {
  const browserReport = {status: "not_available", channel: browserSpec.channel, viewports: {}, version: null};
  const profile = mkdtempSync(join(tmpdir(), `scholarlens-quality-${browserSpec.name}-`));
  let context, probePage;
  const linkProbeCache = new Map();
  const probeBudget = {remaining: maxDynamicPaperProbes};
  try {
    context = await chromium.launchPersistentContext(profile, {
      channel: browserSpec.channel,
      headless: true,
      viewport: {width: 1440, height: 1000},
      reducedMotion: "reduce",
      serviceWorkers: "block",
      args: ["--disable-background-networking", "--disable-component-update", "--disable-default-apps", "--disable-sync", "--no-first-run", "--no-default-browser-check"],
    });
    browserReport.status = "running";
    browserReport.version = context.browser()?.version() || null;
    await context.route("**/*", async route => {
      const request = route.request();
      const url = new URL(request.url());
      const method = request.method().toUpperCase();
      if (!isAllowedRequest(url)) {
        const item = {browser: browserSpec.name, method, url: safeUrl(request.url()), reason: "non_target_origin_blocked"};
        pushUnique(report.external_requests, item);
        await route.abort("blockedbyclient");
        return;
      }
      if (!isReadMethod(method)) {
        const item = {browser: browserSpec.name, method, url: safeUrl(request.url()), reason: "read_only_pass"};
        pushUnique(report.blocked_writes, item);
        await route.abort("blockedbyclient");
        return;
      }
      await route.continue();
    });
    probePage = await context.newPage();
    for (const width of widths) {
      browserReport.viewports[width] = {routes: []};
      const page = await context.newPage();
      await page.setViewportSize({width, height: 1000});
      for (const route of routePlan) {
        const result = await inspectPage(page, browserSpec.name, width, route, probePage, linkProbeCache, probeBudget);
        browserReport.viewports[width].routes.push({name: result.name, path: result.route, status: result.status});
        if (width === 1440 && ["home", "search", "not-found"].includes(route.name)) {
          const filename = `${browserSpec.name}-${width}-${route.name}.png`;
          await page.screenshot({path: join(output, filename), fullPage: false});
          report.screenshots.push(filename);
        }
      }
      await page.close();
    }
    // A narrow regression check covers the most layout-sensitive entry points.
    browserReport.viewports[mobileWidth] = {routes: []};
    const mobile = await context.newPage();
    await mobile.setViewportSize({width: mobileWidth, height: 844});
    for (const route of routePlan.filter(item => ["home", "search"].includes(item.name))) {
      const result = await inspectPage(mobile, browserSpec.name, mobileWidth, route, probePage, linkProbeCache, probeBudget);
      browserReport.viewports[mobileWidth].routes.push({name: result.name, path: result.route, status: result.status});
      if (route.name === "home") {
        const filename = `${browserSpec.name}-${mobileWidth}-${route.name}.png`;
        await mobile.screenshot({path: join(output, filename), fullPage: false});
        report.screenshots.push(filename);
      }
    }
    await mobile.close();
    await probePage.close();
    browserReport.profile_cleaned = true;
  } catch (error) {
    browserReport.error = String(error).slice(0, 800);
    if (browserReport.status === "running") browserReport.status = "failed";
  } finally {
    const recordCleanupError = (scope, error) => {
      browserReport.cleanup_error = browserReport.cleanup_error || [];
      browserReport.cleanup_error.push({scope, error: String(error).slice(0, 800)});
      browserReport.profile_cleaned = false;
      browserReport.status = "failed";
    };
    try {
      await context?.close();
    } catch (error) {
      recordCleanupError("context.close", error);
    }
    try {
      rmSync(profile, {recursive: true, force: true});
    } catch (error) {
      recordCleanupError("profile.remove", error);
    }
  }
  browserReport.paper_probe_budget = {
    limit: maxDynamicPaperProbes,
    used: maxDynamicPaperProbes - probeBudget.remaining,
    remaining: probeBudget.remaining,
    cache_entries: linkProbeCache.size,
  };
  if (browserReport.status === "running") browserReport.status = browserReport.profile_cleaned === false ? "failed" : "passed";
  report.tools.browsers[browserSpec.name] = browserReport;
  return browserReport;
}

try {
  for (const browserSpec of browsers) await inspectBrowser(browserSpec);
  const completed = Object.values(report.tools.browsers).filter(item => item.status === "passed");
  const routeFailures = report.routes.filter(item => item.status !== "passed");
  report.passed = completed.length === browsers.length && routeFailures.length === 0 && report.blocked_writes.length === 0;
  report.finished_at = new Date().toISOString();
  report.summary = {
    browsers_passed: completed.map(item => item.channel),
    browsers_not_available: Object.values(report.tools.browsers).filter(item => item.status === "not_available").map(item => item.channel),
    route_checks: report.routes.length,
    route_failures: routeFailures.length,
    external_requests_blocked: report.external_requests.length,
    non_read_requests_blocked: report.blocked_writes.length,
    scope_note: "External links were inventoried but never visited. This report does not replace ZAP, full accessibility certification, performance/load testing, Edge on a real user profile, or production validation.",
  };
  writeFileSync(join(output, "report.json"), JSON.stringify({...report, output}, null, 2), "utf8");
  console.log(JSON.stringify({passed: report.passed, summary: report.summary, output}));
  process.exitCode = report.passed ? 0 : 1;
} catch (error) {
  report.finished_at = new Date().toISOString();
  report.error = String(error).slice(0, 800);
  writeFileSync(join(output, "report.json"), JSON.stringify({...report, output}, null, 2), "utf8");
  console.error(JSON.stringify({passed: false, summary: report.summary || null, output}));
  process.exitCode = 1;
}
