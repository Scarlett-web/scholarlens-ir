import test from "node:test";
import assert from "node:assert/strict";
import { computeEvaluation } from "../src/lib/evaluation.ts";

test("no judgments never invents precision or nDCG values", () => {
  const data = computeEvaluation(["a","b","c"], {});
  assert.equal(data.precisionK, null);
  assert.equal(data.ndcgK, null);
  assert.equal(data.judged, 0);
  assert.equal(data.count, 3);
});

test("top-5 precision counts grades 1 or 2 as relevant", () => {
  const data = computeEvaluation(["a","b","c","d","e"], {a:2,b:0,c:1,d:0,e:1});
  assert.equal(data.precisionAt, 5);
  assert.equal(data.precisionK, 0.6);
  assert.equal(data.judged, 5);
});

test("nDCG is one when relevant grades sorted descending", () => {
  const data = computeEvaluation(["a","b","c"], {a:2,b:1,c:0});
  assert.equal(data.ndcgK, 1);
});

test("nDCG decreases when optimal ranking order is reversed", () => {
  const data = computeEvaluation(["a","b","c"], {a:0,b:1,c:2});
  assert.ok(data.ndcgK > 0 && data.ndcgK < 1);
});

test("partial judgments don't yield fabricated metrics", () => {
  const data = computeEvaluation(["a","b","c"], {a:2,b:1});
  assert.equal(data.precisionK,null);
  assert.equal(data.ndcgK,null);
  assert.equal(data.judged,2);
});

test("all-irrelevant fully judged set yields zeros", () => {
  const data = computeEvaluation(["a","b"], {a:0,b:0});
  assert.equal(data.precisionK, 0);
  assert.equal(data.ndcgK, 0);
});
