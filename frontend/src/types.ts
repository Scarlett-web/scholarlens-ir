export type SearchField = "all" | "title" | "authors" | "date" | "affiliation" | "address" | "fulltext";
export type SearchMode = "keyword" | "semantic" | "hybrid";
export type SortBy = "relevance" | "newest" | "oldest" | "title";

export interface Paper {
  paper_id: string;
  title: string;
  authors: string[];
  year: number | null;
  date: string;
  affiliation: string[];
  address: string[];
  abstract: string;
  fulltext: string;
  keywords: string[];
  topics: string[];
  pages: number | null;
  pdf_available: boolean;
  parse_status: "success" | "partial" | "error" | "unknown";
  source_file?: string;
  score?: number;
  highlight?: Record<string, string[]>;
}

export interface SearchQuery {
  q: string;
  mode?: SearchMode;
  field: SearchField;
  page: number;
  pageSize: number;
  sort: SortBy;
  yearFrom?: number;
  yearTo?: number;
}

export interface SearchResult {
  papers: Paper[];
  total: number;
  page: number;
  pageSize: number;
  durationMs: number | null;
  dataKind: "demo" | "api";
}

export interface LibraryEntry {
  paper: Paper;
  collection: string;
  savedAt: string;
  note?: string;
}

export interface HistoryEntry {
  paper: Paper;
  viewedAt: string;
}

export interface LocalUpload {
  id: string;
  name: string;
  size: number;
  submittedAt: string;
  status: "pending" | "approved" | "rejected";
  sha256?: string;
  reviewedAt?: string;
  reviewNote?: string;
}

export const FIELD_OPTIONS: { value: SearchField; label: string; short: string }[] = [
  { value: "all", label: "全部字段", short: "全部" },
  { value: "title", label: "论文标题", short: "标题" },
  { value: "authors", label: "作者", short: "作者" },
  { value: "date", label: "发表日期 / 年份", short: "日期" },
  { value: "affiliation", label: "作者机构", short: "机构" },
  { value: "address", label: "机构地址", short: "地址" },
  { value: "fulltext", label: "论文全文", short: "全文" }
];

export const MODE_OPTIONS: { value: SearchMode; label: string; hint: string }[] = [
  { value: "keyword", label: "Keyword", hint: "经典关键词检索" },
  { value: "semantic", label: "Semantic", hint: "按研究主题与语义查找" },
  { value: "hybrid", label: "Hybrid", hint: "融合关键词与语义相关性" }
];
