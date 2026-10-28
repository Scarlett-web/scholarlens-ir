/**
 * Read-only Playwright acceptance for the paper relations and motion surfaces.
 *
 * The main flow uses the real local API exposed by the supplied preview. The
 * only synthetic response is an explicitly recorded, browser-local 500 for
 * the first relation-candidate request; the retry is forwarded to the real
 * API. No service writes, credentials, AI providers, or external origins are
 * contacted.
 */
import assert from "node:assert/strict";
import {mkdirSync, writeFileSync} from "node:fs";
import {fileURLToPath} from "node:url";
import {join} from "node:path";
import {randomBytes} from "node:crypto";
import {chromium} from "playwright";

const root = fileURLToPath(new URL("../../", import.meta.url));
const origin = process.env.SCHOLARLENS_URL || "http://127.0.0.1:4175";
const targetUrl = new URL(origin);
const allowedHosts = new Set(["localhost", "127.0.0.1", "::1"]);
const output = join(root, "tools/audit/reports", `relation-motion-${new Date().toISOString().replace(/[:.]/g, "-")}-${randomBytes(4).toString("hex")}`);
mkdirSync(output, {recursive: true});

function normalizedHost(value) {
  return value.replace(/^\[|\]$/g, "");
}

function assertTarget(value) {
  assert.ok(["http:", "https:"].includes(value.protocol), "Target must use HTTP or HTTPS");
  assert.equal(value.username, "", "Target URL must not contain credentials");
  assert.equal(value.password, "", "Target URL must not contain credentials");
  assert.ok(allowedHosts.has(normalizedHost(value.hostname)), "Only an exact loopback target is allowed");
}

assertTarget(targetUrl);

const report = {
  passed: false,
  target: origin,
  started_at: new Date().toISOString(),
  scope: "same-origin loopback, real paper API read path, browser-local relation 500 fixture, no service writes or AI configuration",
  data_boundary: {
    real: ["GET /api/discover", "GET /api/search", "GET /api/papers/{paper_id}", "GET /api/discover/random"],
    browser_fixture: [
      "one GET /api/discover response fulfilled as HTTP 500, then retry forwarded to the real API",
      "one GET /api/discover/random response held and released after exit-focus",
      "one GET /api/discover response fulfilled as HTTP 500 during an SPA focus switch",
    ],
    synthetic_corpus: "none",
  },
  checks: [],
  real_data: {},
  fixture_data: {responses: [], delayed_random: []},
  contexts: [],
  screenshots: [],
  blocked_requests: [],
  write_requests: [],
  external_requests: [],
  page_errors: [],
  console_errors: [],
  expected_console_errors: [],
  server_errors: [],
  cleanup_errors: [],
};

function safeUrl(value) {
  try {
    const url = new URL(value);
    return `${url.protocol}//${url.host}${url.pathname}${url.search}`.slice(0, 320);
  } catch {
    return String(value).slice(0, 320);
  }
}

function isTarget(url) {
  return ["http:", "https:"].includes(url.protocol) &&
    allowedHosts.has(normalizedHost(url.hostname)) && url.origin === targetUrl.origin;
}

function isReadMethod(method) {
  return ["GET", "HEAD"].includes(String(method).toUpperCase());
}

function pushBounded(list, value, limit = 120) {
  if (list.length < limit) list.push(value);
}

function deferred() {
  let release;
  const promise = new Promise(resolve => { release = resolve; });
  return {promise, release};
}

async function waitForState(predicate, label, timeout = 20000) {
  const started = Date.now();
  while (Date.now() - started < timeout) {
    if (predicate()) return;
    await new Promise(resolve => setTimeout(resolve, 50));
  }
  throw new Error("Timed out waiting for " + label);
}

function check(name, details = {}) {
  report.checks.push({name, status: "passed", ...details});
}

function expectNetworkFailure(state, path, status, reason) {
  const url = new URL(path, targetUrl.origin);
  assert.ok(isTarget(url), "Expected network failures must stay on the target origin");
  state.expectedNetworkErrors.set(url.href, {status, reason});
}

function pageReady(page) {
  return page.locator("#root").waitFor({state: "attached", timeout: 20000});
}

async function waitForRoute(page, path, selector = "#main h1, #main h2, #main .detail-header, #main .empty-state") {
  const response = await page.goto(targetUrl.origin + path, {waitUntil: "domcontentloaded", timeout: 20000});
  await pageReady(page);
  await page.locator(selector).first().waitFor({state: "visible", timeout: 20000});
  await page.waitForTimeout(120);
  return response;
}

async function waitForPaper(page) {
  await page.locator(".detail-header").waitFor({state: "visible", timeout: 20000});
  await page.locator(".detail-relations").waitFor({state: "attached", timeout: 20000});
  await page.locator(".detail-relations-map").waitFor({state: "visible", timeout: 20000});
}

async function ensureTargetPage(page) {
  let currentOrigin = "";
  try { currentOrigin = new URL(page.url()).origin; } catch { /* about:blank has no target origin */ }
  if (currentOrigin === targetUrl.origin) return;
  await page.goto(targetUrl.origin + "/", {waitUntil: "domcontentloaded", timeout: 20000});
  await pageReady(page);
}

async function readJson(page, path) {
  await ensureTargetPage(page);
  const requestUrl = new URL(path, targetUrl.origin);
  assert.ok(isTarget(requestUrl), "readJson only accepts the exact target origin");
  const result = await page.evaluate(async requestPath => {
    const response = await fetch(requestPath, {method: "GET", headers: {Accept: "application/json"}});
    return {status: response.status, body: await response.text()};
  }, requestUrl.href);
  assert.ok(result.status >= 200 && result.status < 300, `Expected ${path} to return 2xx, got ${result.status}`);
  try {
    return JSON.parse(result.body);
  } catch {
    throw new Error(`Invalid JSON from ${path}`);
  }
}

function responsePapers(payload) {
  const rows = Array.isArray(payload?.recommendations) ? payload.recommendations :
    Array.isArray(payload?.results) ? payload.results : [];
  return rows.map(row => row?._source || row?.paper || row).filter(row => row && typeof row.paper_id === "string");
}

function titleTokens(papers) {
  const values = papers.flatMap(paper => [paper.title, ...(paper.keywords || []), ...(paper.authors || [])]);
  return [...new Set(values.flatMap(value => String(value || "").split(/[^\p{L}\p{N}]+/u)
    .map(item => item.trim()).filter(item => item.length >= 3 || /[^\x00-\x7F]/u.test(item) && item.length >= 2)))];
}

async function chooseRealTarget(page, discovery) {
  const recommendations = responsePapers(discovery);
  assert.ok(recommendations.length > 0, "Real /api/discover returned no recommendations");
  const discoveryIds = new Set(recommendations.map(paper => paper.paper_id));
  const minimumYear = recommendations.map(paper => Number(paper.year)).filter(Number.isFinite).sort((a, b) => a - b)[0] ?? null;
  const attempts = [];
  const queries = [...new Set(["data", "research", "study", "method", ...titleTokens(recommendations)])].slice(0, 24);
  for (const query of queries) {
    const params = new URLSearchParams({q: query, field: "all", mode: "keyword", page: "1", page_size: "100", sort: "year_asc"});
    let payload;
    try {
      payload = await readJson(page, "/api/search?" + params);
    } catch (error) {
      attempts.push({query, status: "error", error: String(error).slice(0, 180)});
      continue;
    }
    const results = responsePapers(payload);
    attempts.push({query, status: "ok", count: results.length});
    const outsideBatch = results.filter(paper => !discoveryIds.has(paper.paper_id));
    const older = minimumYear === null ? outsideBatch : outsideBatch.filter(paper => Number.isFinite(Number(paper.year)) && Number(paper.year) <= minimumYear);
    const target = (older[0] || outsideBatch[0]);
    if (target) {
      return {
        id: target.paper_id,
        year: Number.isFinite(Number(target.year)) ? Number(target.year) : null,
        title: String(target.title || "").slice(0, 240),
        query,
        selection_mode: older.includes(target) ? "real-search-older-than-discovery-window" : "real-search-outside-discovery-window",
        discovery_count: recommendations.length,
        discovery_ids: [...discoveryIds],
        minimum_discovery_year: minimumYear,
        search_attempts: attempts,
      };
    }
  }
  throw new Error("Could not select a real paper outside the /api/discover window; 21-to-20 focus retention was not safely testable");
}

function attachPageTelemetry(page, state, contextName) {
  page.on("request", request => {
    let url;
    try { url = new URL(request.url()); } catch { return; }
    const item = {context: contextName, method: request.method(), url: safeUrl(request.url())};
    if (!isTarget(url)) {
      pushBounded(report.external_requests, {...item, reason: "non_target_origin"});
      return;
    }
    if (!isReadMethod(request.method())) {
      pushBounded(report.write_requests, {...item, reason: "read_only_guard"});
      return;
    }
    pushBounded(state.requests, item);
  });
  page.on("response", response => {
    const item = {context: contextName, method: response.request().method(), status: response.status(), url: safeUrl(response.url())};
    const expected = state.expectedNetworkErrors.get(response.url());
    if (response.status() >= 500 && (!expected || expected.status !== response.status())) {
      pushBounded(report.server_errors, item);
    }
  });
  page.on("requestfailed", request => {
    const url = new URL(request.url());
    if (isTarget(url)) pushBounded(state.failed_requests, {method: request.method(), url: safeUrl(request.url()), failure: request.failure()?.errorText || "unknown"});
  });
  page.on("pageerror", error => {
    const item = {context: contextName, error: String(error).slice(0, 500)};
    pushBounded(state.page_errors, item); pushBounded(report.page_errors, item);
  });
  page.on("console", message => {
    if (message.type() === "error") {
      const text = message.text().slice(0, 500);
      const location = message.location()?.url || "";
      const status = Number(text.match(/\b(404|500)\b/)?.[1] || 0);
      const expectedEntry = [...state.expectedNetworkErrors.entries()].find(([url, expected]) =>
        expected.status === status && location === url);
      const item = {context: contextName, text, location: safeUrl(location), expected: Boolean(expectedEntry), reason: expectedEntry?.[1].reason || null};
      if (expectedEntry) {
        pushBounded(state.expected_console_errors, item);
        pushBounded(report.expected_console_errors, item);
      } else {
        pushBounded(state.console_errors, item); pushBounded(report.console_errors, item);
      }
    }
  });
}

async function createContext(browser, name, {reducedMotion = false, failNextDiscovery = false, delayNextRandom = false} = {}) {
  const context = await browser.newContext({
    viewport: {width: 1440, height: 900},
    reducedMotion: reducedMotion ? "reduce" : "no-preference",
    serviceWorkers: "block",
  });
  const state = {
    name,
    requests: [],
    failed_requests: [],
    page_errors: [],
    console_errors: [],
    expected_console_errors: [],
    expectedNetworkErrors: new Map(),
    fixtureResponseUrls: new Set(),
    randomGate: null,
    releaseDelayedRandom: () => state.randomGate?.release(),
    fixture: {
      fail_next_discovery: failNextDiscovery,
      delay_next_random: delayNextRandom,
      responses: [],
      delayed_random: [],
    },
  };
  // Prevent guest history/preferences from persisting outside this isolated browser context.
  await context.addInitScript(() => {
    const nativeSetItem = Storage.prototype.setItem;
    Storage.prototype.setItem = function(key, value) {
      if (this === window.localStorage && key.startsWith("scholarlens-v1:")) return;
      nativeSetItem.call(this, key, value);
    };
  });
  await context.route("**/*", async route => {
    const request = route.request();
    let url;
    try { url = new URL(request.url()); } catch { await route.abort("blockedbyclient"); return; }
    if (!isTarget(url)) {
      pushBounded(report.blocked_requests, {context: name, method: request.method(), url: safeUrl(request.url()), reason: "non_target_origin"});
      await route.abort("blockedbyclient");
      return;
    }
    if (!isReadMethod(request.method())) {
      pushBounded(report.write_requests, {context: name, method: request.method(), url: safeUrl(request.url()), reason: "read_only_pass"});
      await route.abort("blockedbyclient");
      return;
    }
    if (state.fixture.fail_next_discovery && url.pathname === "/api/discover") {
      state.fixture.fail_next_discovery = false;
      state.fixtureResponseUrls.add(request.url());
      state.expectedNetworkErrors.set(request.url(), {status: 500, reason: "browser-route-fixture"});
      const item = {context: name, method: request.method(), url: safeUrl(request.url()), status: 500, source: "browser-route-fixture"};
      state.fixture.responses.push(item); report.fixture_data.responses.push(item);
      await route.fulfill({status: 500, contentType: "application/json", body: JSON.stringify({error: {message: "browser-local relation candidate fixture failure"}})});
      return;
    }
    if (state.fixture.delay_next_random && url.pathname === "/api/discover/random") {
      state.fixture.delay_next_random = false;
      const gate = deferred();
      state.randomGate = gate;
      const item = {context: name, method: request.method(), url: safeUrl(request.url()), status: "held", source: "browser-route-fixture"};
      state.fixture.delayed_random.push(item);
      report.fixture_data.delayed_random.push(item);
      await gate.promise;
      item.status = "released";
      state.randomGate = null;
      await route.continue();
      return;
    }
    await route.continue();
  });
  const page = await context.newPage();
  attachPageTelemetry(page, state, name);
  return {context, page, state};
}

async function selectedNode(page, id) {
  return page.locator(".constellation-node").evaluateAll((nodes, paperId) => {
    const node = nodes.find(item => item.getAttribute("data-paper-id") === paperId);
    return node ? {found: true, pressed: node.getAttribute("aria-pressed") === "true"} : {found: false, pressed: false};
  }, id);
}

async function assertSettledRoute(page, label) {
  const rootElement = page.locator("#main > *").first();
  const initialStyle = await rootElement.evaluate(element => {
    const style = getComputedStyle(element);
    return {animationName: style.animationName, animationDuration: style.animationDuration};
  });
  const duration = initialStyle.animationDuration;
  const durationMs = Number.parseFloat(duration) * 1000;
  assert.ok(Number.isFinite(durationMs) && Math.abs(durationMs - 420) < 20, `${label}: expected 420ms route animation, got ${duration}`);
  assert.equal(initialStyle.animationName, "route-enter", `${label}: expected route-enter animation, got ${initialStyle.animationName}`);
  await page.waitForTimeout(500);
  const settled = await rootElement.evaluate(element => {
    const style = getComputedStyle(element), rect = element.getBoundingClientRect();
    return {animationName: style.animationName, transform: style.transform, x: rect.x, y: rect.y};
  });
  assert.ok(settled.transform === "none" || /^matrix\(1, 0, 0, 1, 0, 0\)$/.test(settled.transform), `${label}: route transform did not settle: ${settled.transform}`);
  return {duration, ...settled};
}

function contextSnapshot(state) {
  return {
    name: state.name,
    requests: state.requests,
    failed_requests: state.failed_requests,
    expected_network_errors: [...state.expectedNetworkErrors.entries()].map(([url, expected]) => ({url: safeUrl(url), ...expected})),
    expected_console_errors: state.expected_console_errors,
    fixture: state.fixture,
  };
}

async function runRealFlow(browser, target) {
  const session = await createContext(browser, "real-motion", {reducedMotion: false});
  const {context, page, state} = session;
  try {
    const discovery = await readJson(page, "/api/discover?limit=20");
    const recommendations = responsePapers(discovery);
    const chosen = target;
    report.real_data.discovery = {endpoint: "/api/discover?limit=20", count: recommendations.length, ids: recommendations.map(item => item.paper_id)};
    report.real_data.target = chosen;
    assert.ok(chosen.id && !report.real_data.discovery.ids.includes(chosen.id), "The real focus target must be outside the initial 20-paper discovery window");

    const paperPath = "/paper/" + encodeURIComponent(chosen.id);
    await waitForRoute(page, paperPath);
    await waitForPaper(page);
    assert.ok((await page.locator("#paper-fulltext").textContent() || "").length > 20, "Real paper正文 should remain readable");
    await page.screenshot({path: join(output, "real-detail-relations.png")});
    report.screenshots.push("real-detail-relations.png");
    check("real detail relations panel", {paper_id: chosen.id, relation_candidate_get: true});

    await Promise.all([
      page.waitForURL(url => new URL(url).pathname === "/explore" && new URL(url).searchParams.get("focus") === chosen.id, {timeout: 20000}),
      page.getByRole("link", {name: /在关系图中查看候选/}).click(),
    ]);
    await page.locator(".constellation-node").first().waitFor({state: "visible", timeout: 20000});
    const focused = await selectedNode(page, chosen.id);
    assert.deepEqual(focused, {found: true, pressed: true}, "The focused real paper must remain selected in the relation graph");
    const initialNodeCount = await page.locator(".constellation-node").count();
    assert.equal(initialNodeCount, 20, "The graph should apply its 20-node display limit");
    await page.screenshot({path: join(output, "real-focused-map.png")});
    report.screenshots.push("real-focused-map.png");
    check("focus URL and 21-to-20 retention", {focus_id: chosen.id, input_candidates: 21, displayed_nodes: initialNodeCount, target_retained: true});

    await page.getByRole("button", {name: "换一批", exact: true}).click();
    await page.locator(".constellation-node").first().waitFor({state: "visible", timeout: 20000});
    assert.deepEqual(await selectedNode(page, chosen.id), {found: true, pressed: true}, "换一批 must keep the focused node selected");
    check("shuffle preserves focus", {focus_id: chosen.id});

    state.fixture.delay_next_random = true;
    await page.getByRole("button", {name: "换一批", exact: true}).click();
    await waitForState(() => state.fixture.delayed_random.some(item => item.status === "held"), "delayed discover/random response");
    await page.getByRole("button", {name: "退出聚焦", exact: true}).click();
    await page.waitForURL(url => new URL(url).pathname === "/explore" && !new URL(url).searchParams.has("focus"), {timeout: 20000});
    assert.equal(new URL(page.url()).search, "", "Exit focus must remain URL-synchronized while random discovery is held");
    state.releaseDelayedRandom();
    await page.waitForFunction(focusId => {
      const hasFocusNode = [...document.querySelectorAll("[data-paper-id]")].some(node => node.getAttribute("data-paper-id") === focusId);
      const candidateCount = document.querySelectorAll(".paper-card, .constellation-node").length;
      return !hasFocusNode && !document.querySelector(".explore-focus-note") && candidateCount > 0;
    }, chosen.id, {timeout: 20000});
    await page.waitForTimeout(450);
    assert.equal(new URL(page.url()).search, "", "A late random response must not restore the focus query");
    assert.equal(await page.locator(".explore-focus-note").count(), 0, "A late random response must not restore the focus prompt");
    assert.equal(await page.locator("[data-paper-id]").evaluateAll((nodes, focusId) =>
      nodes.filter(node => node.getAttribute("data-paper-id") === focusId).length, chosen.id), 0,
    "A late random response must not restore the focused node");
    check("late random response cannot revive focus after exit", {
      focus_id: chosen.id,
      random_response: "held_then_released",
      focus_url_after_exit: new URL(page.url()).search,
      focus_prompt_after_release: false,
      focus_node_after_release: false,
    });

    assert.equal(new URL(page.url()).search, "", "退出聚焦 must remove the focus query");
    await page.goBack();
    await page.waitForURL(url => new URL(url).pathname === "/paper/" + encodeURIComponent(chosen.id), {timeout: 20000});
    await page.locator(".detail-header").waitFor({state: "visible", timeout: 20000});
    await page.goForward();
    await page.waitForURL(url => new URL(url).pathname === "/explore" && !new URL(url).searchParams.has("focus"), {timeout: 20000});
    check("exit URL sync and browser back/forward", {after_exit: "/explore", back_to_detail: true, forward_to_plain_explore: true});

    const missingFocusPath = "/api/papers/" + encodeURIComponent("source-sha256:not-in-delivery");
    expectNetworkFailure(state, missingFocusPath, 404, "unknown-focus-paper");
    await waitForRoute(page, "/explore?focus=" + encodeURIComponent("source-sha256:not-in-delivery"));
    await page.locator(".explore-focus-note[role=alert]").waitFor({state: "visible", timeout: 20000});
    assert.ok(await page.locator(".paper-card, .constellation-node").count() > 0, "An unknown focus must restore ordinary exploration candidates");
    await page.getByRole("button", {name: "退出聚焦", exact: true}).click();
    await page.waitForURL(url => new URL(url).pathname === "/explore" && !new URL(url).searchParams.has("focus"), {timeout: 20000});
    check("unknown focus recovers ordinary exploration");

    await waitForRoute(page, paperPath);
    await waitForPaper(page);
    await page.getByRole("button", {name: "专注阅读", exact: true}).click();
    await page.locator('.detail-page[data-reading-focus="true"]').waitFor({state: "attached", timeout: 10000});
    const relationsHidden = await page.locator(".detail-relations").evaluate(element => {
      const style = getComputedStyle(element), rect = element.getBoundingClientRect();
      return {display: style.display, height: rect.height, visibility: style.visibility};
    });
    assert.equal(relationsHidden.display, "none", "专注阅读 must hide the relation panel");
    assert.equal(relationsHidden.height, 0, "Hidden relation panel must not occupy reading space");
    await page.screenshot({path: join(output, "real-focused-reader.png")});
    report.screenshots.push("real-focused-reader.png");
    check("focused reading hides relations", {relations_hidden: relationsHidden});

    await waitForRoute(page, "/");
    await page.locator('.app-sidebar a[href="/explore"]').click();
    await page.waitForURL(url => new URL(url).pathname === "/explore", {timeout: 20000});
    const transition = await assertSettledRoute(page, "normal transition");
    check("normal route transition settles after 420ms", transition);

    await waitForRoute(page, "/");
    await page.getByRole("button", {name: "暂停网站动效", exact: true}).click();
    await page.locator('.workspace-shell[data-motion="paused"]').waitFor({state: "attached", timeout: 10000});
    await page.locator('.app-sidebar a[href="/explore"]').click();
    await page.waitForURL(url => new URL(url).pathname === "/explore", {timeout: 20000});
    const pausedRoot = page.locator("#main > *").first();
    const pausedBefore = await pausedRoot.evaluate(element => {
      const style = getComputedStyle(element), rect = element.getBoundingClientRect();
      return {animationName: style.animationName, transform: style.transform, x: rect.x, y: rect.y};
    });
    await page.waitForTimeout(500);
    const pausedAfter = await pausedRoot.evaluate(element => {
      const style = getComputedStyle(element), rect = element.getBoundingClientRect();
      return {animationName: style.animationName, transform: style.transform, x: rect.x, y: rect.y};
    });
    assert.equal(pausedBefore.animationName, "none", "Paused website must disable route animation");
    assert.equal(pausedAfter.animationName, "none");
    assert.ok(pausedBefore.transform === "none" || /^matrix\(1, 0, 0, 1, 0, 0\)$/.test(pausedBefore.transform));
    assert.ok(Math.abs(pausedBefore.x - pausedAfter.x) < 0.5 && Math.abs(pausedBefore.y - pausedAfter.y) < 0.5, "Paused route must not move");
    await page.screenshot({path: join(output, "motion-paused.png")});
    report.screenshots.push("motion-paused.png");
    check("website pause disables animation and movement", {before: pausedBefore, after: pausedAfter});
  } finally {
    state.releaseDelayedRandom();
    report.contexts.push(contextSnapshot(state));
    try { await context.close(); } catch (error) { report.cleanup_errors.push({context: state.name, error: String(error).slice(0, 500)}); }
  }
}

async function runRelationFailure(browser, target) {
  const session = await createContext(browser, "relation-failure-fixture", {failNextDiscovery: true});
  const {context, page, state} = session;
  try {
    await waitForRoute(page, "/paper/" + encodeURIComponent(target.id));
    await page.locator(".detail-header").waitFor({state: "visible", timeout: 20000});
    await page.locator(".detail-relations-state[role=alert]").waitFor({state: "visible", timeout: 20000});
    assert.ok((await page.locator("#paper-fulltext").textContent() || "").length > 20, "Candidate failure must not remove real正文");
    await page.locator(".detail-relations-state[role=alert]").getByRole("button", {name: /重试/}).click();
    await page.locator(".detail-relations-state[role=alert]").waitFor({state: "detached", timeout: 20000});
    assert.equal(state.fixture.responses.length, 1, "Exactly one browser-local relation 500 is expected");
    assert.ok(state.requests.some(item => item.url.includes("/api/discover")), "Retry must forward a real GET /api/discover");
    await page.screenshot({path: join(output, "relation-candidate-retry.png")});
    report.screenshots.push("relation-candidate-retry.png");
    check("relation candidate 500 then retry", {fixture_status: 500, retry_forwarded: true, body_preserved: true});
  } finally {
    state.releaseDelayedRandom();
    report.contexts.push(contextSnapshot(state));
    try { await context.close(); } catch (error) { report.cleanup_errors.push({context: state.name, error: String(error).slice(0, 500)}); }
  }
}

async function runExploreRetryRecovery(browser) {
  const session = await createContext(browser, "explore-retry-fixture", {failNextDiscovery: true});
  const {context, page, state} = session;
  try {
    await waitForRoute(page, "/explore");
    await page.locator(".empty-state.error-state").waitFor({state: "visible", timeout: 20000});
    const retry = page.getByRole("button", {name: /重新读取|重试/}).first();
    await retry.waitFor({state: "visible", timeout: 10000});
    await retry.click();
    await page.locator(".paper-card, .constellation-node").first().waitFor({state: "visible", timeout: 20000});
    assert.equal(await page.locator(".empty-state.error-state").count(), 0, "Explore retry must clear the initial discovery error state");
    assert.ok(await page.locator(".paper-card, .constellation-node").count() > 0, "Explore retry must restore real discovery candidates");
    assert.equal(state.fixture.responses.filter(item => item.status === 500).length, 1, "Explore initial discovery must fail exactly once in the browser fixture");
    assert.ok(state.requests.filter(item => item.url.includes("/api/discover")).length >= 2, "Explore retry must forward a second real GET /api/discover");
    await page.screenshot({path: join(output, "explore-retry-recovery.png")});
    report.screenshots.push("explore-retry-recovery.png");
    check("Explore initial discovery failure then retry recovery", {
      fixture_status: 500,
      retry_forwarded: true,
      error_state_cleared: true,
      candidates_restored: true,
    });
  } finally {
    state.releaseDelayedRandom();
    report.contexts.push(contextSnapshot(state));
    try { await context.close(); } catch (error) { report.cleanup_errors.push({context: state.name, error: String(error).slice(0, 500)}); }
  }
}

async function runFocusSwitchFailure(browser, target) {
  const session = await createContext(browser, "focus-switch-failure", {reducedMotion: false});
  const {context, page, state} = session;
  try {
    const targetPath = "/explore?focus=" + encodeURIComponent(target.id);
    await waitForRoute(page, targetPath);
    await page.locator(".explore-focus-note[role=status]").waitFor({state: "visible", timeout: 20000});
    const oldPrompt = await page.locator(".explore-focus-note").textContent();
    assert.ok(oldPrompt?.includes(target.title.slice(0, 24)), "The first focus prompt should identify the real focus target");

    state.fixture.fail_next_discovery = true;
    expectNetworkFailure(state, "/api/papers/" + encodeURIComponent("source-sha256:not-in-delivery"), 404, "focus-switch-missing-paper");
    const switchedPath = "/explore?focus=" + encodeURIComponent("source-sha256:not-in-delivery");
    await page.evaluate(path => {
      window.history.pushState({}, "", path);
      window.dispatchEvent(new PopStateEvent("popstate", {state: {}}));
    }, switchedPath);
    await page.waitForURL(url => new URL(url).searchParams.get("focus") === "source-sha256:not-in-delivery", {timeout: 20000});
    await page.locator(".empty-state.error-state").waitFor({state: "visible", timeout: 20000});
    assert.equal(await page.locator(".explore-focus-note").count(), 0, "A failed new focus load must not retain the old focus prompt");
    assert.ok(!(await page.locator("#main").textContent() || "").includes(target.title), "A failed new focus load must not retain the old focus title");
    assert.equal(state.fixture.responses.filter(item => item.status === 500).length, 1, "The focus switch must use one browser-local discovery failure");
    check("focus URL switch clears stale prompt on new discovery failure", {
      old_focus_id: target.id,
      new_focus_id: "source-sha256:not-in-delivery",
      discovery_fixture_status: 500,
      stale_prompt_present: false,
    });
  } finally {
    state.releaseDelayedRandom();
    report.contexts.push(contextSnapshot(state));
    try { await context.close(); } catch (error) { report.cleanup_errors.push({context: state.name, error: String(error).slice(0, 500)}); }
  }
}

async function runReducedMotion(browser) {
  const session = await createContext(browser, "system-reduced-motion", {reducedMotion: true});
  const {context, page, state} = session;
  try {
    await waitForRoute(page, "/explore");
    assert.equal(await page.evaluate(() => window.matchMedia("(prefers-reduced-motion: reduce)").matches), true);
    assert.equal(await page.locator(".workspace-shell").getAttribute("data-motion"), "paused");
    const rootElement = page.locator("#main > *").first();
    const initial = await rootElement.evaluate(element => {
      const style = getComputedStyle(element), rect = element.getBoundingClientRect();
      return {animationName: style.animationName, transform: style.transform, x: rect.x, y: rect.y};
    });
    await page.waitForTimeout(500);
    const settled = await rootElement.evaluate(element => {
      const style = getComputedStyle(element), rect = element.getBoundingClientRect();
      return {animationName: style.animationName, transform: style.transform, x: rect.x, y: rect.y};
    });
    assert.equal(initial.animationName, "none", "System reduced motion must disable route animation");
    assert.equal(settled.animationName, "none");
    assert.ok(initial.transform === "none" || /^matrix\(1, 0, 0, 1, 0, 0\)$/.test(initial.transform));
    assert.ok(Math.abs(initial.x - settled.x) < 0.5 && Math.abs(initial.y - settled.y) < 0.5, "Reduced-motion route must not move");
    await page.screenshot({path: join(output, "motion-system-reduced.png")});
    report.screenshots.push("motion-system-reduced.png");
    check("system reduced motion disables animation and movement", {initial, settled});
  } finally {
    state.releaseDelayedRandom();
    report.contexts.push(contextSnapshot(state));
    try { await context.close(); } catch (error) { report.cleanup_errors.push({context: state.name, error: String(error).slice(0, 500)}); }
  }
}

if (process.argv.includes("--self-test")) {
  assert.doesNotThrow(() => assertTarget(new URL("http://127.0.0.1:4175")));
  assert.throws(() => assertTarget(new URL("http://127.0.0.2:4175")));
  assert.throws(() => assertTarget(new URL("https://example.com")));
  assert.equal(isTarget(new URL(origin)), true);
  assert.equal(isTarget(new URL("http://127.0.0.1:4174/api/discover")), targetUrl.port === "4174");
  assert.equal(isReadMethod("GET"), true);
  assert.equal(isReadMethod("HEAD"), true);
  assert.equal(isReadMethod("POST"), false);
  assert.deepEqual(responsePapers({recommendations: [{paper_id: "fixture:a", title: "A"}]}), [{paper_id: "fixture:a", title: "A"}]);
  assert.ok(titleTokens([{title: "Magnetic imaging", keywords: ["MRI"]}]).includes("Magnetic"));
  console.log("relation-motion self-test passed: loopback target, same-origin/read-only guards and paper extraction");
  process.exit(0);
}

let browser;
try {
  browser = await chromium.launch({channel: "chrome", headless: true});
  const real = await createContext(browser, "real-data-selection", {reducedMotion: false});
  let target;
  try {
    const discovery = await readJson(real.page, "/api/discover?limit=20");
    target = await chooseRealTarget(real.page, discovery);
    report.real_data.selection_probe = target;
  } finally {
    report.contexts.push(contextSnapshot(real.state));
    try { await real.context.close(); } catch (error) { report.cleanup_errors.push({context: real.state.name, error: String(error).slice(0, 500)}); }
  }
  assert.ok(target, "A real focus target is required");
  await runRealFlow(browser, target);
  await runExploreRetryRecovery(browser);
  await runFocusSwitchFailure(browser, target);
  await runRelationFailure(browser, target);
  await runReducedMotion(browser);
  assert.deepEqual(report.write_requests, [], "The acceptance must not issue business write requests");
  assert.deepEqual(report.external_requests, [], "The acceptance must not visit external origins");
  assert.deepEqual(report.server_errors, [], "Unexpected real 5xx responses must fail acceptance");
  assert.deepEqual(report.page_errors, [], "Page errors must fail acceptance");
  assert.deepEqual(report.console_errors, [], "Console errors must fail acceptance");
  assert.deepEqual(report.cleanup_errors, [], "Browser cleanup must complete");
  report.passed = true;
} catch (error) {
  report.error = String(error).slice(0, 1000);
} finally {
  try { await browser?.close(); } catch (error) { report.cleanup_errors.push({context: "browser.close", error: String(error).slice(0, 500)}); }
  if (report.cleanup_errors.length) report.passed = false;
  report.finished_at = new Date().toISOString();
  writeFileSync(join(output, "report.json"), JSON.stringify({...report, output}, null, 2), "utf8");
  console.log(JSON.stringify({passed: report.passed, checks: report.checks.length, output, data_boundary: report.data_boundary}));
  process.exitCode = report.passed ? 0 : 1;
}
