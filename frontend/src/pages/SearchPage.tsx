import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ArrowLeft, ArrowRight, ChevronDown, Clipboard, Filter, RotateCcw, SlidersHorizontal } from "lucide-react";
import { PaperCard } from "../components/PaperCard";
import { IntegrationNotice, PageHeading } from "../components/Layout";
import { SearchBox } from "../components/SearchBox";
import { useStudio } from "../App";
import { DATA_SOURCE, searchPapers } from "../services/papers";
import { useSearchCapabilities } from "../services/useSearchCapabilities";
import {useAuth} from "../services/AuthContext";
import {accountApi} from "../services/backend";
import { FIELD_OPTIONS } from "../types";
import type { SearchField, SearchMode, SearchResult, SortBy } from "../types";
const PAGE_SIZE = 6;
function validYear(value: string): number | undefined {
  if (!value.trim()) return undefined;
  const n = Number(value);
  return Number.isInteger(n) && n >= 1800 && n <= 2100 ? n : undefined;
}

export function SearchPage() {
  const [params, setParams] = useSearchParams();
  const { notify } = useStudio();
  const {user}=useAuth();
  const lastRecorded=useRef("");
  const q = params.get("q") ?? "";
  const field = (FIELD_OPTIONS.some((x) => x.value === params.get("field")) ? params.get("field") : "all") as SearchField;
  const mode = (["keyword", "semantic", "hybrid"].includes(params.get("mode") ?? "") ?
    params.get("mode") : "keyword") as SearchMode;
  const page = Math.max(1, Number(params.get("page") ?? 1) || 1);
  const sort = (["relevance", "newest", "oldest", "title"].includes(params.get("sort") ?? "") ?
    params.get("sort") : "relevance") as SortBy;
  const fromValue = params.get("from") ?? "";
  const toValue = params.get("to") ?? "";
  const yearFrom = validYear(fromValue);
  const yearTo = validYear(toValue);
  const [draftFrom, setDraftFrom] = useState(fromValue);
  const [draftTo, setDraftTo] = useState(toValue);
  const [result, setResult] = useState<SearchResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retryKey, setRetryKey] = useState(0);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const {capabilities, error: capabilityError} = useSearchCapabilities();
  const blocked = mode !== "keyword" && !capabilities?.[mode].ready;
  const invalidYears = Boolean((fromValue && !yearFrom) || (toValue && !yearTo) ||
    (yearFrom && yearTo && yearFrom > yearTo));
  const label = useMemo(() => q ? "「" + q + "」的检索结果" : DATA_SOURCE === "api" ? "近期论文选读" : "全部论文", [q]);

  useEffect(() => { setDraftFrom(fromValue); setDraftTo(toValue); }, [fromValue, toValue]);
  useEffect(() => {
    let active = true;
    if (blocked || invalidYears) { setResult(null); setError(null); setLoading(false); return; }
    setLoading(true); setError(null); setResult(null);
    searchPapers({ q, field, mode, page, pageSize: PAGE_SIZE, sort, yearFrom, yearTo })
      .then((data) => { if (active) {setResult(data);if(user&&q.trim()&&lastRecorded.current!==JSON.stringify([user.id,q,field,mode])){lastRecorded.current=JSON.stringify([user.id,q,field,mode]);void accountApi.recordQuery(q,field,mode).catch(()=>notify("检索成功，但账户搜索历史未能保存"));}} })
      .catch((cause) => { if (active) setError(cause instanceof Error ? cause.message : "检索请求失败"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [q, field, mode, page, sort, yearFrom, yearTo, blocked, invalidYears, retryKey]);

  const update = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value); else next.delete(key);
    if (key !== "page") next.set("page", "1");
    setParams(next);
  };

  const resetFilters = () => {
    const next = new URLSearchParams(params);
    for (const key of ["from","to","sort"]) next.delete(key);
    next.set("page","1");
    setDraftFrom(""); setDraftTo(""); setParams(next);
    notify("已重置所有筛选条件");
  };

  const applyYears = () => {
    if ((draftFrom && !validYear(draftFrom)) || (draftTo && !validYear(draftTo))) {
      notify("年份请输入 1800—2100 之间的整数");
      return;
    }
    if (draftFrom && draftTo && Number(draftFrom) > Number(draftTo)) {
      notify("起始年份不能晚于结束年份");
      return;
    }
    const next = new URLSearchParams(params);
    if (draftFrom) next.set("from", draftFrom); else next.delete("from");
    if (draftTo) next.set("to", draftTo); else next.delete("to");
    next.set("page", "1");
    setParams(next);
    notify("时间筛选已应用");
  };

  const applyPreset = (from?: number, to?: number) => {
    const next = new URLSearchParams(params);
    if (from) next.set("from", String(from)); else next.delete("from");
    if (to) next.set("to", String(to)); else next.delete("to");
    next.set("page", "1");
    setParams(next);
  };

  const share = async () => {
    try { await navigator.clipboard.writeText(window.location.href); notify("已复制可分享的检索链接"); }
    catch { notify("复制失败，请使用浏览器地址栏复制当前链接"); }
  };

  const totalPages = Math.max(1, Math.ceil((result?.total ?? 0) / PAGE_SIZE));
  const pages = Array.from({length: totalPages}, (_, i) => i + 1).filter((n) =>
    totalPages <= 7 || n === 1 || n === totalPages || Math.abs(n - page) <= 1);
  return (
    <div className="workspace-page content-wrap search-page">
      <PageHeading eyebrow="RESEARCH / SEARCH" title="论文检索" desc="搜索题目、作者、机构或全文，逐步缩小结果范围。"/>
      <SearchBox variant="compact" initialQuery={q} initialField={field} initialMode={mode}/>
      {blocked && <IntegrationNotice title="此检索模式尚未就绪" desc={capabilityError || capabilities?.[mode].reason || "正在检查模型与向量索引，请稍候。"}/>}
      {DATA_SOURCE === "api" && !q.trim() && <IntegrationNotice title="先浏览，再展开检索" desc="这里选取最多20篇近期论文，分页与年份筛选仅作用于这些候选。输入关键词可检索整个论文库。"/>}
      <button className="mobile-filter-toggle" type="button" aria-expanded={filtersOpen} aria-controls="search-filters" onClick={()=>setFiltersOpen((value)=>!value)}>
        <span><Filter size={16}/> 筛选条件{yearFrom || yearTo ? " · 已设置年份" : ""}</span><ChevronDown size={16}/>
      </button>
      <div className="search-workspace">
        <aside id="search-filters" className={"filters-panel"+(filtersOpen?" filters-open":"")}>
          <div className="filter-heading"><span><Filter size={18}/> 筛选条件</span>
            <button onClick={resetFilters} title="重置全部筛选" aria-label="重置全部筛选"><RotateCcw size={17}/></button>
          </div>
          <div className="filter-section"><h3>发表年份</h3>
            <form onSubmit={(e) => {e.preventDefault();applyYears();}}>
              <div className="year-inputs">
                <label>从<input inputMode="numeric" type="number" min="1800" max="2100" placeholder="1900" value={draftFrom} onChange={(e) => setDraftFrom(e.target.value)}/></label>
                <span>—</span>
                <label>至<input inputMode="numeric" type="number" min="1800" max="2100" placeholder="2026" value={draftTo} onChange={(e) => setDraftTo(e.target.value)}/></label>
              </div>
              <button type="submit" className="filter-apply-button">应用筛选 <ArrowRight size={15}/></button>
            </form>
            <div className="quick-filters">
              <button onClick={() => applyPreset(2020, 2026)}>2020—2026</button>
              <button onClick={() => applyPreset(2015, 2019)}>2015—2019</button>
              <button onClick={() => applyPreset()}>所有年份</button>
            </div>
          </div>
          <div className="filter-section">
            <h3>检索范围</h3>
            <div className="filter-summary"><span>当前字段</span><strong>{FIELD_OPTIONS.find((v) => v.value === field)?.label}</strong></div>
            <details className="filter-data-details"><summary>关于检索数据</summary><p className="filter-small-note">{DATA_SOURCE === "demo" ?
              "本地演示按字符串出现次数排序，不属于 BM25。接入 FastAPI 后以服务器评分为准。" :
              "当前使用 API 模式，结果取决于实际后端索引和参数。"}</p></details>
          </div>
        </aside>
        <section className="results-section" aria-live="polite">
          <div className="results-topbar">
            <div><span className="eyebrow">SEARCH RESULTS</span><h2>{label}</h2>
              <p>{loading ? "正在检索…" : result ?
                "共 " + result.total + " 篇 · 第 " + Math.min(page, totalPages) + " / " + totalPages + " 页" :
                "设置检索条件后查看结果"}
                {result?.dataKind === "api" && result.durationMs !== null ? " · " + result.durationMs + " ms" : ""}
              </p></div>
            <div className="results-toolbar">
              <button className="button button-secondary button-copy" onClick={() => void share()}><Clipboard size={16}/> 分享检索</button>
              <label className="sort-select"><SlidersHorizontal size={17}/>
                <select value={sort} onChange={(e) => update("sort", e.target.value)} aria-label="排序方式">
                  <option value="relevance">相关性优先</option>
                  <option value="newest">最新年份</option>
                  <option value="oldest">最早年份</option>
                  {DATA_SOURCE === "demo" && <option value="title">标题 A—Z</option>}
                </select>
              </label>
            </div>
          </div>
          {invalidYears ? <div className="empty-state"><h3>年份范围无效</h3><p>请在左侧调整年份并点击应用筛选。</p>
            <button className="button button-secondary" onClick={() => applyPreset()}>清空年份范围</button></div> :
            blocked ? <div className="empty-state"><h3>此模式暂不可用</h3><p>{capabilities?.[mode].reason || capabilityError || "正在检查检索服务。"}</p>
              <button className="button button-primary" onClick={() => update("mode","keyword")}>切换关键词检索</button></div> :
            error ? <div className="empty-state error-state"><h3>无法获取检索结果</h3><p>{error}</p>
              <button className="button button-secondary" onClick={() => setRetryKey((value)=>value+1)}>重试</button></div> :
            loading ? <div className="paper-skeleton-grid">{Array.from({length:3},(_,i)=><div className="paper-skeleton" key={i}/>)}</div> :
            result && result.papers.length > 0 ? <>
              <div className="paper-list">{result.papers.map((paper,index) => <PaperCard key={paper.paper_id} paper={paper} query={q} order={(page-1)*PAGE_SIZE+index+1}/>)}</div>
              <nav className="pagination" aria-label="论文结果分页">
                <button disabled={page <= 1} onClick={() => update("page",String(page-1))}><ArrowLeft size={16}/> 上一页</button>
                {pages.map((n) => <button className={n===page?"active":""} key={n} aria-current={n===page?"page":undefined}
                  onClick={() => update("page",String(n))}>{n}</button>)}
                <button disabled={page >= totalPages} onClick={() => update("page",String(page+1))}>下一页 <ArrowRight size={16}/></button>
              </nav>
            </> : <div className="empty-state">
              <h3>没有找到符合条件的论文</h3><p>试试更短的关键词，调整年份，或使用“全部字段”检索。</p>
              <button className="button button-secondary" onClick={() => setParams(new URLSearchParams({q:"",field:"all",mode:"keyword"}))}>浏览全部论文</button>
            </div>}
        </section>
      </div>
    </div>
  );
}
