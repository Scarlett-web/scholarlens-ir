import type { Paper } from "../types.ts";

export type RelationKind = "author" | "keyword" | "topic" | "affiliation";
export interface RelationReason { kind: RelationKind; value: string }
export interface PaperRelation { source: string; target: string; reasons: RelationReason[] }
export interface PaperNode { paper: Paper; index: number; x: number; y: number; degree: number }
export interface PaperGraph { nodes: PaperNode[]; edges: PaperRelation[]; omitted: number }

const fields = { author: "authors", keyword: "keywords", topic: "topics", affiliation: "affiliation" } as const;
const unknown = /^(?:unknown|n\/?a|none|null|undefined|not available|anonymous|未知|暂无|无|不详|作者未知|作者信息暂缺|未分类|全部领域)$/iu;
const normalize = (value: string) => value.normalize("NFC").trim().replace(/\s+/gu, " ").toLocaleLowerCase();

/** Exact metadata matches only. This does not infer author identity or citations. */
export function buildPaperGraph(input: Paper[]): PaperGraph {
  const unique = [...new Map(input.filter(paper => paper.paper_id).map(paper => [paper.paper_id, paper])).values()];
  const papers = unique.slice(0, 20);
  const metadata = papers.map(paper => Object.fromEntries(Object.entries(fields).map(([kind, field]) =>
    [kind, new Map(paper[field].filter(value => typeof value === "string" && !unknown.test(value.trim()))
      .map(value => [normalize(value), value.trim().replace(/\s+/gu, " ")] as const).filter(([key]) => key.length >= 2))]
  )) as Record<RelationKind, Map<string, string>>);
  const edges: PaperRelation[] = [];
  for (let i = 0; i < papers.length; i++) for (let j = i + 1; j < papers.length; j++) {
    const reasons: RelationReason[] = [];
    for (const kind of Object.keys(fields) as RelationKind[]) {
      for (const [key, value] of metadata[i][kind]) if (metadata[j][kind].has(key)) reasons.push({ kind, value });
    }
    if (reasons.length) edges.push({ source: papers[i].paper_id, target: papers[j].paper_id, reasons });
  }
  const neighbors = new Map(papers.map(paper => [paper.paper_id, new Set<string>()]));
  for (const edge of edges) { neighbors.get(edge.source)!.add(edge.target); neighbors.get(edge.target)!.add(edge.source); }
  const visited = new Set<string>();
  const groups: string[][] = [];
  for (const paper of papers) {
    if (visited.has(paper.paper_id)) continue;
    const queue = [paper.paper_id]; visited.add(paper.paper_id);
    for (let index = 0; index < queue.length; index++) for (const id of neighbors.get(queue[index])!) {
      if (!visited.has(id)) { visited.add(id); queue.push(id); }
    }
    groups.push(queue);
  }
  const positions = new Map<string, { x: number; y: number }>();
  // A stable sunflower layout distributes large and small connected groups alike.
  // Geometry aids browsing and carries no semantic distance or citation meaning.
  groups.flat().forEach((id, index) => {
    const angle = index * Math.PI * (3 - Math.sqrt(5));
    const radius = papers.length === 1 ? 0 : 42 * Math.sqrt((index + .5) / papers.length);
    positions.set(id, { x: 50 + Math.cos(angle) * radius, y: 50 + Math.sin(angle) * radius });
  });
  return { nodes: papers.map((paper, index) => ({ paper, index: index + 1, ...positions.get(paper.paper_id)!, degree: neighbors.get(paper.paper_id)!.size })),
    edges, omitted: unique.length - papers.length };
}

export const relationLabels: Record<RelationKind, string> = {
  author: "同名作者", keyword: "共同关键词", topic: "共同标签", affiliation: "同名机构"
};
