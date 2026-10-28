import test from "node:test";
import assert from "node:assert/strict";
import { loadReadingPosition, saveReadingPosition } from "../src/lib/readingPosition.ts";

const store = new Map();
globalThis.window = { localStorage: { getItem: key => store.get(key) ?? null, setItem: (key, value) => store.set(key, value) } };
const position = { ratio: .45, expanded: true, textLength: 9000, savedAt: "2026-10-28T03:00:00Z" };

test("reading positions persist per paper and account without guest leakage", () => {
  store.clear();
  assert.equal(saveReadingPosition(11, "paper-a", position), true);
  assert.deepEqual(loadReadingPosition(11, "paper-a", 9000), position);
  assert.equal(loadReadingPosition(12, "paper-a", 9000), null);
  assert.equal(loadReadingPosition(undefined, "paper-a", 9000), null);
  assert.equal(loadReadingPosition(11, "paper-b", 9000), null);
  assert.equal(loadReadingPosition(11, "paper-a", 9999), null, "changed source text invalidates its old scroll ratio");
});

test("malformed positions recover without propagating invalid ratios", () => {
  for (const invalid of ["null", "[]", "{bad", JSON.stringify({ "paper-a": { ...position, ratio: 22 } }), JSON.stringify({ "paper-a": { ...position, savedAt: "unknown" } })]) {
    store.set("scholarlens-v1:reading-positions:user-11", invalid);
    assert.equal(loadReadingPosition(11, "paper-a", 9000), null);
  }
});

test("position history stays bounded and storage failures are returned to the UI", () => {
  store.clear();
  for (let i = 0; i < 110; i++) saveReadingPosition(11, "paper-" + i, { ...position, savedAt: new Date(Date.UTC(2026, 9, 28, 0, 0, i)).toISOString() });
  const rows = JSON.parse(store.get("scholarlens-v1:reading-positions:user-11"));
  assert.equal(Object.keys(rows).length, 100);
  assert.ok(rows["paper-109"]);
  assert.equal(rows["paper-0"], undefined);
  const setItem = window.localStorage.setItem;
  window.localStorage.setItem = () => { throw new Error("quota"); };
  assert.equal(saveReadingPosition(11, "paper-a", position), false);
  window.localStorage.setItem = setItem;
});
