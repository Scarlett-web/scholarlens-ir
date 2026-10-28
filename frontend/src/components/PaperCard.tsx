import { useId, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight, Bookmark, FileText } from "lucide-react";
import type { Paper, SearchField } from "../types";
import { useStudio } from "../App";
import { highlightParts, safePlainText } from "../lib/search";
import { DemoBadge } from "./Layout";
import { serverHighlightParts } from "../lib/serverHighlight";
import { isExactTitleQuery, resultHighlightScope } from "../lib/highlight";

export function Highlight({ text, query }: { text: string; query: string }) {
  return <>{highlightParts(text, query).map(({ text: part, match }, index) =>
    match ? <mark key={index}>{part}</mark> : <span key={index}>{part}</span>)}</>;
}

export function ServerHighlight({text}: {text: string}) {
  return <>{serverHighlightParts(text).map((part, index) => part.match ? <mark key={index}>{part.text}</mark> : <span key={index}>{part.text}</span>)}</>;
}

function PaperAuthors({paper,query,highlight=true}:{paper:Paper;query:string;highlight?:boolean}) {
  const [expanded,setExpanded]=useState(false);
  const id=useId();
  const normalized=(text:string)=>text.trim().replace(/\s+/gu," ").toLocaleLowerCase();
  const fragments=(highlight?paper.highlight?.authors??[]:[]).map(text=>({text,parts:serverHighlightParts(text)}));
  const authorQuery=highlight?query:"";
  const authors=paper.authors.map((name,index)=>{
    const fragment=fragments.find(item=>normalized(item.parts.map(part=>part.text).join(""))===normalized(name));
    const matched=fragment?fragment.parts.some(part=>part.match):highlightParts(name,authorQuery).some(part=>part.match);
    return {name,index,fragment:fragment?.text,matched};
  });
  const laterMatch=authors.slice(0,3).some(author=>author.matched)?undefined:authors.find(author=>author.index>=3&&author.matched);
  const preview=laterMatch?[...authors.slice(0,2),laterMatch]:authors.slice(0,3);
  const visible=expanded?authors:preview;
  return <div className="paper-authors" data-field="authors">
    <span id={id}>{visible.length?visible.map((author,index)=><span className="paper-author" key={author.index}>{index>0&&<span aria-hidden="true"> · </span>}{author.fragment?<ServerHighlight text={author.fragment}/>:<Highlight text={author.name} query={authorQuery}/>}</span>):"作者信息暂缺"}</span>
    {authors.length>3&&<button type="button" className="paper-authors-toggle" aria-expanded={expanded} aria-controls={id} onClick={()=>setExpanded(value=>!value)}>{expanded?"收起作者":"更多作者（还有 "+(authors.length-3)+" 位）"}</button>}
  </div>;
}

export function PaperCard({ paper, query = "", dense = false, order }: { paper: Paper; query?: string; dense?: boolean; order?: number }) {
  const { isFavorite, toggleFavorite, workspaceReady, workspaceError } = useStudio();
  const saved = isFavorite(paper.paper_id);
  const excerpt = safePlainText(paper.abstract || paper.fulltext || "暂无摘要").slice(0, dense ? 170 : 260);
  const titleOnly=resultHighlightScope(paper.title,query)==="title";
  const snippet = titleOnly?undefined:paper.highlight?.abstract?.[0] || paper.highlight?.fulltext?.[0];
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
        <h3>{titleOnly?<mark>{paper.title}</mark>:<Highlight text={paper.title} query={query} />}</h3><ArrowUpRight size={18} />
      </Link>
      <PaperAuthors key={paper.paper_id+query} paper={paper} query={query} highlight={!titleOnly}/>
      <p className="paper-abstract">{snippet ? <ServerHighlight text={snippet}/> : <><Highlight text={excerpt} query={titleOnly?"":query} />{(paper.abstract || paper.fulltext).length > excerpt.length ? "…" : ""}</>}</p>
      <div className="paper-card-footer">
        <div className="paper-keywords">{paper.keywords.slice(0, 3).map((term) => <span key={term}>{term}</span>)}</div>
        <Link to={"/paper/" + encodeURIComponent(paper.paper_id)} className="paper-read-link">查看详情 <ArrowUpRight size={14} /></Link>
      </div>
    </article>
  );
}


/** Search rows keep the returned order and metadata separate from reading actions. */
export function SearchRecord({paper,query,order,field="all"}:{paper:Paper;query:string;order:number;field?:SearchField}) {
  const {isFavorite,toggleFavorite,workspaceReady,workspaceError}=useStudio();
  const saved=isFavorite(paper.paper_id);
  const detail="/paper/"+encodeURIComponent(paper.paper_id);
  const scope=resultHighlightScope(paper.title,query,field);
  const queryFor=(target:SearchField)=>scope==="all"||scope===target?query:"";
  const highlights=Object.fromEntries(Object.entries(paper.highlight??{}).filter(([key])=>scope==="all"||scope===key));
  const exactTitle=Boolean(queryFor("title"))&&isExactTitleQuery(paper.title,query);
  const snippet=highlights.abstract?.[0]||highlights.fulltext?.[0];
  const excerpt=safePlainText(paper.abstract||paper.fulltext||"暂无摘要或正文片段").slice(0,260);
  return <article className="paper-card paper-record" data-paper-id={paper.paper_id}>
      <div className="paper-record-rail"><span className="paper-list-index" aria-label={"结果 "+order}>{String(order).padStart(2,"0")}</span><span className={"paper-record-year"+(!paper.year?" is-unknown":"")} aria-label={paper.year?"年份："+paper.year:"年份未提供"}><Highlight text={String(paper.year??"未提供")} query={queryFor("date")}/></span></div>
    <div className="paper-record-content">
      <div className="paper-meta-line">{paper.paper_id.startsWith("demo-")?<DemoBadge/>:<span className="paper-source-tag">论文记录</span>}{paper.pdf_available&&<span>PDF 原件可用</span>}</div>
      <Link className="paper-title-link" to={detail}><h3>{exactTitle?<mark>{paper.title}</mark>:highlights.title?.[0]?<ServerHighlight text={highlights.title[0]}/>:<Highlight text={paper.title} query={queryFor("title")}/>}</h3></Link>
      <PaperAuthors key={paper.paper_id+query} paper={paper} query={query} highlight={Boolean(queryFor("authors"))}/>
      <div className="paper-record-metadata">{([['date','日期',paper.date],['affiliation','机构',paper.affiliation.join(" · ")],['address','地址',paper.address.join(" · ")]] as const).map(([metadataField,label,text])=>(text||highlights[metadataField]?.length)?<p key={metadataField} data-field={metadataField}><span>{label}</span>{highlights[metadataField]?.length?<ServerHighlight text={highlights[metadataField].join(" · ")}/>:<Highlight text={text} query={queryFor(metadataField)}/>}</p>:null)}</div>
      <p className="paper-abstract" data-field={highlights.fulltext?.length?"fulltext":"abstract"}>{highlights.fulltext?.length?<><span className="paper-hit-label">{highlights.fulltext.some(text=>serverHighlightParts(text).some(part=>part.match))?"全文命中":"全文片段"}</span><ServerHighlight text={highlights.fulltext[0]}/></>:snippet?<ServerHighlight text={snippet}/>:<><Highlight text={excerpt} query={queryFor("fulltext")}/>{(paper.abstract||paper.fulltext).length>excerpt.length?"…":""}</>}</p>
      {paper.keywords.length>0&&<div className="paper-keywords paper-record-keywords">{paper.keywords.slice(0,3).map(term=><span key={term}>{term}</span>)}</div>}
    </div>
    <div className="paper-record-actions">
      <button className={"paper-record-save bookmark-button"+(saved?" saved":"")} aria-label={saved?"取消收藏论文":"收藏论文"} aria-pressed={saved} disabled={!workspaceReady||Boolean(workspaceError)} onClick={()=>toggleFavorite(paper)}><Bookmark size={16} fill={saved?"currentColor":"none"}/><span>{saved?"已收藏":"收藏"}</span></button>
      <Link className="paper-read-link" to={detail}>阅读论文 <ArrowUpRight size={14}/></Link>
      <Link className="paper-record-evidence" to={"/assistant?"+new URLSearchParams({paper:paper.paper_id})}>查原文证据 <ArrowUpRight size={14}/></Link>
    </div>
  </article>;
}
