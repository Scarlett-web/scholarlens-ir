import {useEffect,useMemo,useState} from "react";
import {Link} from "react-router-dom";
import {ArrowUpRight,BookOpen,Check,Clipboard,FileText,NotebookPen,RefreshCw} from "lucide-react";
import {useStudio} from "../App";
import {getPaper} from "../services/papers";
import {evidenceHref,evidenceLocatorLabel,evidenceNote,resolveEvidenceLocation} from "../lib/evidenceLocation";
import type {EvidenceReference} from "../lib/evidenceLocation";
import type {Paper} from "../types";
import {ExactHighlight} from "./EvidencePassage";

export function EvidenceWorkbench({items,question}:{items:EvidenceReference[];question:string}) {
  const [index,setIndex]=useState(0),[paper,setPaper]=useState<Paper|null>(null),[error,setError]=useState("");
  const [loading,setLoading]=useState(true),[revision,setRevision]=useState(0),[saved,setSaved]=useState("");
  const {appendFavoriteExcerpt,workspaceReady,workspaceError,notify}=useStudio();
  const active=items[index]??items[0];
  useEffect(()=>{
    let alive=true;setPaper(null);setError("");setLoading(true);
    getPaper(active.paper_id).then(value=>{
      if(alive){setPaper(value);if(!value)setError("这篇论文暂不可访问，请打开论文核对。");}
    }).catch(cause=>{if(alive)setError(cause instanceof Error?cause.message:"原文读取失败，请重试。");}).finally(()=>{if(alive)setLoading(false);});
    return()=>{alive=false;};
  },[active.paper_id,revision]);
  useEffect(()=>setSaved(""),[active.chunk_id]);
  const current=paper?.paper_id===active.paper_id?paper:null;
  const match=useMemo(()=>current?resolveEvidenceLocation(current,active):null,[current,active]);
  const words=question.split(/\s+/).filter(word=>word.length>2).slice(0,8).join(" ");
  const copy=async()=>{
    if(!current||!match)return;
    const authors=current.authors.length?"\n作者："+current.authors.join(" · "):"";
    const year=current.year?"\n年份："+current.year:"";
    const text="论文："+current.title+authors+year+"\n\n原文：\n"+active.quote+"\n\n位置："+evidenceLocatorLabel(active.locator)+"\n阅读链接："+window.location.origin+evidenceHref(active);
    try{await navigator.clipboard.writeText(text);notify("原文片段与来源已复制");}catch{notify("复制失败，请手动选择片段复制");}
  };
  return <div className="evidence-workbench" aria-label="原文证据工作台">
    <nav className="evidence-source-list" aria-label="选择原文证据">
      <div className="evidence-list-caption"><FileText size={15}/><span>来源片段</span><small>{items.length}</small></div>
      {items.map((item,i)=><button key={item.chunk_id+":"+i} className="evidence-source-choice" aria-pressed={index===i} onClick={()=>setIndex(i)}>
        <span className="evidence-source-index">{String(i+1).padStart(2,"0")}</span><span><strong>{item.paper_title}</strong><small>{evidenceLocatorLabel(item.locator)}</small><span>{item.quote}</span></span>
      </button>)}
    </nav>
    <article className="evidence-detail" aria-label="当前证据片段" aria-busy={loading}>
      <div className="evidence-detail-kicker"><span>原文片段 {index+1} / {items.length}</span><span>{evidenceLocatorLabel(active.locator)}</span></div>
      <h3>{current?.title??active.paper_title}</h3>
      {current&&<p className="evidence-source-meta">{current.authors.length?current.authors.join(" · "):"作者信息暂缺"}{current.year?" · "+current.year:""}</p>}
      <blockquote className="evidence-quote"><ExactHighlight text={active.quote} query={words}/></blockquote>
      {loading?<p className="evidence-verification" role="status">正在与当前原文逐字核对…</p>:error?<div className="evidence-verification is-error" role="alert"><span>{error}</span><button className="text-action" onClick={()=>setRevision(value=>value+1)}><RefreshCw size={14}/>重新读取</button></div>:match?<p className="evidence-verification" role="status"><Check size={14}/>片段与当前原文一致</p>:<p className="evidence-verification is-error" role="status">片段与当前原文位置不一致，可能已更新。请打开论文核对；本次不自动定位或加入笔记。</p>}
      {match&&<details className="evidence-context"><summary>查看前后文</summary><p>{Array.from(match.text.slice(0,match.start)).slice(-160).join("")}<mark>{active.quote}</mark>{Array.from(match.text.slice(match.end)).slice(0,160).join("")}</p><small>高亮为引用原文；两侧为同一字段中的相邻文本。</small></details>}
      <div className="evidence-actions">
        <Link className="button button-primary" to={match?evidenceHref(active):"/paper/"+encodeURIComponent(active.paper_id)} target="_blank" rel="noopener noreferrer"><BookOpen size={15}/>{match?"定位原文":"打开论文"}<ArrowUpRight size={14}/></Link>
        <button className="button button-secondary" disabled={!match||!workspaceReady||Boolean(error)||saved===active.chunk_id} onClick={()=>{
          if(current&&appendFavoriteExcerpt(current,evidenceNote(active)))setSaved(active.chunk_id);
        }}><NotebookPen size={15}/>{saved===active.chunk_id?"已加入笔记":"加入笔记"}</button>
        <button className="text-action" disabled={!match} onClick={()=>void copy()}><Clipboard size={15}/>复制片段与来源</button>
      </div>
      {saved===active.chunk_id&&<p className="evidence-saved" role="status">已追加到这篇论文的当前笔记，原有内容保留。<Link to="/library">查看我的文献 <ArrowUpRight size={13}/></Link></p>}
      {workspaceError&&<p className="evidence-verification is-error" role="status">{workspaceError}</p>}
    </article>
  </div>;
}
