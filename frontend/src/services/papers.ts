import { DEMO_PAPERS } from "../data/demoPapers";
import { recommendations, searchDemo } from "../lib/search";
import type { SearchQuery, SearchResult } from "../types";
import {backend} from "./backend";
import { createPaperApi, normalizePaper } from "./paperApi";
import type { SearchCapabilities } from "./paperApi";
export { normalizePaper } from "./paperApi";

export const DATA_SOURCE: "demo" | "api" = import.meta.env.VITE_DATA_SOURCE === "api" ? "api" : "demo";
const BASE = (import.meta.env.VITE_API_BASE_URL || "/api").replace(/\/$/, "");
const api = createPaperApi(BASE);

export async function searchPapers(query: SearchQuery): Promise<SearchResult> {
  return DATA_SOURCE === "demo" ? searchDemo(query) : api.search(query);
}
export async function getPaper(id: string) {
  const demo = DEMO_PAPERS.find(paper => paper.paper_id === id);
  // Existing synthetic bookmarks remain readable and explicitly labelled after switching sources.
  return demo ?? (DATA_SOURCE === "demo" ? null : api.paper(id));
}
export async function getLibraryStats() {
  return DATA_SOURCE === "demo" ? {count: DEMO_PAPERS.length, status: "demo"} : api.stats();
}
export function getDiscoverPapers(limit = 6) {
  return DATA_SOURCE === "demo" ? recommendations(limit) : [];
}
export async function getDiscovery() {
  return DATA_SOURCE === "demo"
    ? {papers: recommendations(18), total: 18, examples: [], years: []}
    : api.discover();
}
export async function getSuggestions(q: string) {
  if (!q.trim()) return [];
  return DATA_SOURCE === "demo"
    ? DEMO_PAPERS.filter(p => p.title.toLowerCase().includes(q.toLowerCase())).slice(0,4).map(p => ({text: p.title, field: "title"}))
    : api.suggestions(q);
}
let capabilityRequest: Promise<SearchCapabilities> | undefined;
let capabilityExpires = 0;
export function getSearchCapabilities(): Promise<SearchCapabilities> {
  if (DATA_SOURCE === "demo") return Promise.resolve({keyword: {ready: true, reason: "本地字符串匹配演示"},
    semantic: {ready: false, reason: "演示模式不提供语义检索"}, hybrid: {ready: false, reason: "演示模式不提供混合检索"}});
  if (!capabilityRequest || Date.now() >= capabilityExpires) {
    capabilityExpires = Date.now() + 30000;
    capabilityRequest = api.capabilities().catch(error => {
      capabilityRequest = undefined;
      throw error;
    });
  }
  return capabilityRequest;
}
export function pdfUrl(id: string): string {
  return BASE + "/papers/" + encodeURIComponent(id) + "/pdf";
}

export async function getRandomDiscovery(exclude:string[]=[]){
  if(DATA_SOURCE==="demo")return {papers:recommendations(18)};
  const params=new URLSearchParams({limit:"9",exclude:exclude.slice(-200).join(",")});
  const data=await backend<{recommendations:unknown[]}>("/discover/random?"+params);
  return {papers:data.recommendations.map(normalizePaper)};
}
