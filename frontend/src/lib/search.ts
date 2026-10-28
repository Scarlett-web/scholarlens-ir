import { DEMO_PAPERS } from "../data/demoPapers";
import type { Paper, SearchField, SearchQuery, SearchResult } from "../types";

function searchableField(paper: Paper, field: SearchField): string {
  if (field === "title") return paper.title;
  if (field === "authors") return paper.authors.join(" ");
  if (field === "date") return [paper.date, paper.year ?? ""].join(" ");
  if (field === "affiliation") return paper.affiliation.join(" ");
  if (field === "address") return paper.address.join(" ");
  if (field === "fulltext") return paper.fulltext;
  return [
    paper.title, paper.authors.join(" "), paper.year ?? "", paper.date,
    paper.affiliation.join(" "), paper.address.join(" "),
    paper.abstract, paper.fulltext, paper.keywords.join(" ")
  ].join(" ");
}

export function getDemoRanked(query: SearchQuery): Paper[] {
  const input = query.q.toLocaleLowerCase().trim();
  const words = [...new Set(input.split(/\s+/g).filter(Boolean))];
  const candidate = DEMO_PAPERS.filter((paper) => {
    if (query.yearFrom && (!paper.year || paper.year < query.yearFrom)) return false;
    if (query.yearTo && (!paper.year || paper.year > query.yearTo)) return false;
    return true;
  });
  const ranked = candidate.map((paper) => {
    if (!input) return { paper, score: 0 };
    const hay = searchableField(paper, query.field).toLocaleLowerCase();
    if (!words.some((word) => hay.includes(word))) return { paper, score: -1 };
    let score = 0;
    for (const word of words) {
      score += hay.split(word).length - 1;
      if (paper.title.toLocaleLowerCase().includes(word)) score += query.field === "all" ? 7 : 3;
      if (paper.keywords.some((k) => k.toLocaleLowerCase().includes(word))) score += query.field === "all" ? 3 : 0;
    }
    if (hay.includes(input)) score += 5;
    return { paper, score };
  }).filter(({ score }) => score >= 0);
  ranked.sort((a, b) => {
    if (query.sort === "newest") return (b.paper.year ?? 0) - (a.paper.year ?? 0);
    if (query.sort === "oldest") return (a.paper.year ?? 0) - (b.paper.year ?? 0);
    if (query.sort === "title") return a.paper.title.localeCompare(b.paper.title);
    return b.score - a.score || (b.paper.year ?? 0) - (a.paper.year ?? 0);
  });
  return ranked.map(({ paper }) => paper);
}

export function searchDemo(query: SearchQuery): SearchResult {
  const all = getDemoRanked(query);
  const offset = (query.page - 1) * query.pageSize;
  return { papers: all.slice(offset, offset + query.pageSize), total: all.length,
    page: query.page, pageSize: query.pageSize, durationMs: null, dataKind: "demo" };
}

/** HTML-like text is rendered as safe React text; no dangerouslySetInnerHTML. */
export function safePlainText(value: string): string {
  return value.replace(/<[^>]*>/g, "");
}

export function highlightParts(value: string, query: string): { text: string; match: boolean }[] {
  const plain = safePlainText(value);
  const terms = [...new Set(query.trim().split(/\s+/g).filter(Boolean))].sort((a, b) => b.length - a.length);
  if (!terms.length) return [{ text: plain, match: false }];
  const specials = "\\^$.*+?()[]{}|";
  const escaped = terms.map((term) => term.split("").map((ch) => specials.includes(ch) ? "\\" + ch : ch).join(""));
  const expression = new RegExp("(" + escaped.join("|") + ")", "gi");
  return plain.split(expression).filter(Boolean).map((text) => ({
    text, match: terms.some((term) => term.toLocaleLowerCase() === text.toLocaleLowerCase())
  }));
}

export function recommendations(limit = 3): Paper[] {
  return [...DEMO_PAPERS].sort((a, b) => (b.year ?? 0) - (a.year ?? 0)).slice(0, limit);
}
