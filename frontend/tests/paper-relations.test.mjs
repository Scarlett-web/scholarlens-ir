import test from "node:test";
import assert from "node:assert/strict";
import { buildPaperGraph } from "../src/lib/paperRelations.ts";

const paper = (id, fields = {}) => ({ paper_id: id, title: id, authors: [], keywords: [], topics: [], affiliation: [], year: 2026, ...fields });
test("connections expose exact field evidence without inferring citations or title similarity", () => {
  const graph = buildPaperGraph([paper("a", { authors: ["Ada  Chen"], keywords: ["MRI"] }),
    paper("b", { authors: ["ada chen"], keywords: ["mri"], affiliation: ["Other Lab"] }),
    paper("c", { title: "MRI Ada Chen", authors: ["Ada C."] })]);
  assert.equal(graph.edges.length, 1);
  assert.deepEqual(graph.edges[0].reasons, [{ kind: "author", value: "Ada Chen" }, { kind: "keyword", value: "MRI" }]);
  assert.equal(graph.nodes[2].degree, 0);
});
test("unknown metadata and absent fields leave isolated nodes with no fabricated edges", () => {
  const graph = buildPaperGraph([paper("a", { authors: ["Unknown", " ", "n/a"], topics: ["未分类"] }),
    paper("b", { authors: ["unknown", "N/A"], topics: ["未分类"] })]);
  assert.equal(graph.nodes.length, 2);
  assert.equal(graph.edges.length, 0);
});
test("shared institutions and labels retain separate reasons and no self edges", () => {
  const graph = buildPaperGraph([paper("a", { affiliation: ["Université de Test"], topics: ["Physics"] }),
    paper("b", { affiliation: ["Universite\u0301 de Test"], topics: ["physics"] }), paper("a")]);
  assert.equal(graph.nodes.length, 2);
  // Duplicate IDs use their final snapshot and cannot create an artificial relation.
  assert.equal(graph.edges.length, 0);
  const connected = buildPaperGraph([paper("a", { affiliation: ["Université de Test"], topics: ["Physics"] }),
    paper("b", { affiliation: ["Universite\u0301 de Test"], topics: ["physics"] })]);
  assert.deepEqual(connected.edges[0].reasons.map(reason => reason.kind), ["topic", "affiliation"]);
});
test("layout is stable, bounded, and has no missing edge endpoints", () => {
  const input = Array.from({ length: 26 }, (_, i) => paper("p" + i, { authors: [i % 2 ? "Reader A" : "Reader B"] }));
  const graph = buildPaperGraph(input);
  assert.deepEqual(graph, buildPaperGraph(input));
  assert.equal(graph.nodes.length, 20); assert.equal(graph.omitted, 6);
  const ids = new Set(graph.nodes.map(node => node.paper.paper_id));
  assert.ok(graph.nodes.every(node => node.x > 0 && node.x < 100 && node.y > 0 && node.y < 100));
  assert.ok(graph.edges.every(edge => edge.source !== edge.target && ids.has(edge.source) && ids.has(edge.target)));
  assert.deepEqual(buildPaperGraph([]), { nodes: [], edges: [], omitted: 0 });
});
