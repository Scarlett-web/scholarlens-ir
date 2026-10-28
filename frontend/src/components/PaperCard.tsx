import { Link } from "react-router-dom";
import { ArrowUpRight, Bookmark, FileText } from "lucide-react";
import type { Paper } from "../types";
import { useStudio } from "../App";
import { highlightParts, safePlainText } from "../lib/search";
import { DemoBadge } from "./Layout";
import { serverHighlightParts } from "../lib/serverHighlight";

export function Highlight({ text, query }: { text: string; query: string }) {
  return <>{highlightParts(text, query).map(({ text: part, match }, index) =>
    match ? <mark key={index}>{part}</mark> : <span key={index}>{part}</span>)}</>;
}

function ServerHighlight({text}: {text: string}) {
  return <>{serverHighlightParts(text).map((part, index) => part.match ? <mark key={index}>{part.text}</mark> : <span key={index}>{part.text}</span>)}</>;
}

export function PaperCard({ paper, query = "", dense = false, order }: { paper: Paper; query?: string; dense?: boolean; order?: number }) {
  const { isFavorite, toggleFavorite, workspaceReady, workspaceError } = useStudio();
  const saved = isFavorite(paper.paper_id);
  const excerpt = safePlainText(paper.abstract || paper.fulltext || "暂无摘要").slice(0, dense ? 170 : 260);
  const snippet = paper.highlight?.abstract?.[0] || paper.highlight?.fulltext?.[0];
  return (
    <article className={"paper-card " + (dense ? "paper-card-dense" : "")} data-paper-id={paper.paper_id}>
      {order !== undefined && <span className="paper-list-index" aria-hidden="true">{String(order).padStart(2,"0")}</span>}
      <div className="paper-card-top">
        <div className="paper-meta-line">
          {paper.paper_id.startsWith("demo-") ? <DemoBadge /> : <span className="paper-source-tag"><FileText size={13} /> 学术论文</span>}
          {paper.year && <span>{paper.year}</span>}
          {paper.topics.length > 0 && <span>{paper.topics[0]}</span>}
        </div>
        <button className={saved ? "icon-button bookmark-button saved" : "icon-button bookmark-button"}
          title={saved ? "取消收藏" : "收藏论文"} aria-label={saved ? "取消收藏论文" : "收藏论文"} aria-pressed={saved}
          disabled={!workspaceReady||Boolean(workspaceError)} onClick={() => toggleFavorite(paper)}><Bookmark size={19} fill={saved ? "currentColor" : "none"} /></button>
      </div>
      <Link className="paper-title-link" to={"/paper/" + encodeURIComponent(paper.paper_id)}>
        <h3><Highlight text={paper.title} query={query} /></h3><ArrowUpRight size={18} />
      </Link>
      <div className="paper-authors">{paper.authors.length ? paper.authors.join(" · ") : "作者信息暂缺"}</div>
      <p className="paper-abstract">{snippet ? <ServerHighlight text={snippet}/> : <><Highlight text={excerpt} query={query} />{(paper.abstract || paper.fulltext).length > excerpt.length ? "…" : ""}</>}</p>
      <div className="paper-card-footer">
        <div className="paper-keywords">{paper.keywords.slice(0, 3).map((term) => <span key={term}>{term}</span>)}</div>
        <Link to={"/paper/" + encodeURIComponent(paper.paper_id)} className="paper-read-link">查看详情 <ArrowUpRight size={14} /></Link>
      </div>
    </article>
  );
}


/** Search rows keep the returned order and metadata separate from reading actions. */
export function SearchRecord({paper,query,order}:{paper:Paper;query:string;order:number}) {
  const {isFavorite,toggleFavorite,workspaceReady,workspaceError}=useStudio();
  const saved=isFavorite(paper.paper_id);
  const detail="/paper/"+encodeURIComponent(paper.paper_id);
  const snippet=paper.highlight?.abstract?.[0]||paper.highlight?.fulltext?.[0];
  const excerpt=safePlainText(paper.abstract||paper.fulltext||"暂无摘要或正文片段").slice(0,260);
  const scored=typeof paper.score==="number"&&Number.isFinite(paper.score);
  return <article className="paper-card paper-record" data-paper-id={paper.paper_id}>
    <div className="paper-record-rail"><span className="paper-list-index" aria-label={"结果 "+order}>{String(order).padStart(2,"0")}</span><span className={"paper-record-year"+(!paper.year?" is-unknown":"")} aria-label={paper.year?"年份："+paper.year:"年份未提供"}>{paper.year??"未提供"}</span></div>
    <div className="paper-record-content">
      <div className="paper-meta-line">{paper.paper_id.startsWith("demo-")?<DemoBadge/>:<span className="paper-source-tag">论文记录</span>}{paper.pdf_available&&<span>PDF 原件可用</span>}{scored&&<span title="检索引擎返回的原始评分，仅用于当前查询排序，不代表置信度">检索分数 {paper.score!.toLocaleString("zh-CN",{maximumFractionDigits:3})}</span>}</div>
      <Link className="paper-title-link" to={detail}><h3><Highlight text={paper.title} query={query}/></h3></Link>
      <div className="paper-authors">{paper.authors.length?paper.authors.join(" · "):"作者信息暂缺"}</div>
      <p className="paper-abstract">{snippet?<ServerHighlight text={snippet}/>:<><Highlight text={excerpt} query={query}/>{(paper.abstract||paper.fulltext).length>excerpt.length?"…":""}</>}</p>
      {paper.keywords.length>0&&<div className="paper-keywords paper-record-keywords">{paper.keywords.slice(0,3).map(term=><span key={term}>{term}</span>)}</div>}
    </div>
    <div className="paper-record-actions">
      <button className={"paper-record-save bookmark-button"+(saved?" saved":"")} aria-label={saved?"取消收藏论文":"收藏论文"} aria-pressed={saved} disabled={!workspaceReady||Boolean(workspaceError)} onClick={()=>toggleFavorite(paper)}><Bookmark size={16} fill={saved?"currentColor":"none"}/><span>{saved?"已收藏":"收藏"}</span></button>
      <Link className="paper-read-link" to={detail}>阅读论文 <ArrowUpRight size={14}/></Link>
      <Link className="paper-record-evidence" to={"/assistant?"+new URLSearchParams({paper:paper.paper_id})}>查原文证据 <ArrowUpRight size={14}/></Link>
    </div>
  </article>;
}
