import type { Paper, SearchMode, SearchQuery, SearchResult } from "../types";

export function record(raw: unknown): Record<string, unknown> {
  return raw && typeof raw === "object" && !Array.isArray(raw) ? raw as Record<string, unknown> : {};
}
function strings(value: unknown): string[] {
  if (Array.isArray(value)) return value.filter((v): v is string => typeof v === "string");
  return typeof value === "string" && value.trim() ? [value] : [];
}
function number(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  const result = Number(value);
  return Number.isFinite(result) ? result : null;
}
function highlights(value: unknown): Record<string, string[]> {
  return Object.fromEntries(Object.entries(record(value)).map(([key, items]) => [key, strings(items)]));
}
export function normalizePaper(value: unknown): Paper {
  const p = record(value), pages = record(p.pages);
  const status = p.parse_status ?? record(p.source_status).parse_status ?? record(p.quality).parse_status;
  return {
    paper_id: String(p.paper_id ?? p.id ?? ""), title: String(p.title ?? "标题暂缺"),
    authors: strings(p.authors ?? p.writers), year: number(p.year), date: String(p.date ?? ""),
    affiliation: strings(p.affiliation ?? p.affiliations), address: strings(p.address ?? p.addresses),
    abstract: String(p.abstract ?? p.abstract_snippet ?? p.digest ?? ""),
    fulltext: String(p.fulltext ?? p.full_text ?? ""), keywords: strings(p.keywords), topics: strings(p.topics),
    pages: number(typeof p.pages === "object" ? pages.count ?? pages.total : p.pages),
    pdf_available: p.pdf_available === true,
    parse_status: status === "success" || status === "partial" || status === "error" ? status : "unknown",
    source_file: typeof p.source_file === "string" ? p.source_file : undefined,
    score: number(p.score) ?? undefined, highlight: highlights(p.highlights ?? p.highlight)
  };
}
export function buildSearchParams(query: SearchQuery): URLSearchParams {
  if (query.sort === "title") throw new Error("当前检索服务不支持全库标题排序，请选择相关性或年份排序。");
  const params = new URLSearchParams({q: query.q.trim(), field: query.field, mode: query.mode ?? "keyword",
    page: String(query.page), page_size: String(query.pageSize),
    sort: query.sort === "newest" ? "year_desc" : query.sort === "oldest" ? "year_asc" : "relevance"});
  if (query.yearFrom !== undefined) params.set("year_from", String(query.yearFrom));
  if (query.yearTo !== undefined) params.set("year_to", String(query.yearTo));
  return params;
}
export interface Discovery {
  papers: Paper[];
  total: number;
  examples: { q: string; field: string }[];
  years: { year: number; papers: number }[];
}
export type SearchCapabilities = Record<SearchMode, { ready: boolean; reason: string }>;

export function createPaperApi(base: string, transport: typeof fetch = fetch) {
  const root = base.replace(/\/$/, "");
  async function request(path: string, missingIsNull = false): Promise<unknown> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 20000);
    try {
      const response = await transport(root + path, {headers: {Accept: "application/json"}, signal: controller.signal});
      if (missingIsNull && response.status === 404) return null;
      const json: unknown = await response.json().catch(() => null);
      if (!response.ok) {
        const error = record(record(json).error);
        throw new Error(typeof error.message === "string" ? error.message : "后端请求失败（HTTP " + response.status + "）。");
      }
      if (json === null) throw new Error("后端没有返回有效 JSON，请检查 API 代理地址。");
      return json;
    } catch (error) {
      if (controller.signal.aborted) throw new Error("后端请求超时，请稍后重试。");
      if (error instanceof TypeError) throw new Error("无法连接论文服务，请检查网络后重试。");
      throw error;
    } finally { clearTimeout(timer); }
  }
  async function discover(limit = 20): Promise<Discovery> {
    const data = record(await request("/discover?limit=" + Math.min(20, Math.max(1, limit))));
    return {papers: (Array.isArray(data.recommendations) ? data.recommendations : []).map(normalizePaper),
      total: number(data.papers) ?? 0,
      examples: (Array.isArray(data.example_searches) ? data.example_searches : []).map(item => {
        const row = record(item); return {q: String(row.q ?? ""), field: String(row.field ?? "all")};
      }),
      years: (Array.isArray(data.years) ? data.years : []).map(item => {
        const row = record(item); return {year: Number(row.year), papers: Number(row.papers)};
      })};
  }
  return {
    discover,
    async search(query: SearchQuery): Promise<SearchResult> {
      if (!query.q.trim()) {
        const selection = await discover();
        const papers = selection.papers.filter(p => (!query.yearFrom || (p.year !== null && p.year >= query.yearFrom)) &&
          (!query.yearTo || (p.year !== null && p.year <= query.yearTo)));
        if (query.sort === "oldest") papers.sort((a,b) => (a.year ?? Infinity) - (b.year ?? Infinity));
        if (query.sort === "title") papers.sort((a,b) => a.title.localeCompare(b.title));
        return {papers: papers.slice((query.page - 1) * query.pageSize, query.page * query.pageSize), total: papers.length,
          page: query.page, pageSize: query.pageSize, durationMs: null, dataKind: "api"};
      }
      const json = record(await request("/search?" + buildSearchParams(query)));
      const data = record(json.data ?? json);
      const rows = data.results ?? data.items ?? data.hits;
      return {papers: (Array.isArray(rows) ? rows : []).map(hit => {
        const wrapper = record(hit), paper = normalizePaper(wrapper._source ?? wrapper.paper ?? hit);
        paper.score = number(wrapper._score ?? wrapper.score) ?? paper.score;
        if (wrapper.highlights || wrapper.highlight) paper.highlight = highlights(wrapper.highlights ?? wrapper.highlight);
        return paper;
      }), total: number(record(data.total).value ?? data.total) ?? 0,
      page: number(data.page) ?? query.page, pageSize: number(data.page_size) ?? query.pageSize,
      durationMs: number(data.took_ms), dataKind: "api"};
    },
    async paper(id: string): Promise<Paper | null> {
      const json = await request("/papers/" + encodeURIComponent(id), true);
      if (json === null) return null;
      const raw = record(json); return normalizePaper(raw.paper ?? raw.data ?? raw);
    },
    async stats() {
      const json = record(await request("/stats")), data = record(json.data ?? json);
      return {count: number(data.papers ?? data.indexed ?? data.total) ?? 0, status: String(data.status ?? "api")};
    },
    async suggestions(q: string): Promise<{text: string; field: string}[]> {
      const data = record(await request("/suggest?" + new URLSearchParams({q, limit: "4"})));
      return (Array.isArray(data.suggestions) ? data.suggestions : []).map(item => {
        const row = record(item); return {text: String(row.text ?? ""), field: String(row.field ?? "all")};
      }).filter(item => item.text);
    },
    async capabilities(): Promise<SearchCapabilities> {
      const data = record(await request("/capabilities")), modules = record(data.modules);
      return Object.fromEntries((["keyword", "semantic", "hybrid"] as const).map(mode => {
        const item = record(modules[mode + "_search"]);
        return [mode, {ready: item.status === "ready", reason: String(item.reason ?? "服务尚未就绪")}];
      })) as SearchCapabilities;
    }
  };
}
