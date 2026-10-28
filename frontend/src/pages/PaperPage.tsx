import {backend} from "../services/backend";
import { useEffect, useMemo, useState } from "react";
import { Link, useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, ArrowUpRight, Bookmark, Calendar, ChevronDown, ChevronUp, Clipboard, Download, ExternalLink, FileQuestion, FileText, Quote, Search, Sparkles } from "lucide-react";
import { useStudio } from "../App";
import { DemoBadge, IntegrationNotice } from "../components/Layout";
import { Highlight, PaperCard } from "../components/PaperCard";
import { DATA_SOURCE, getPaper, pdfUrl } from "../services/papers";
import { DEMO_PAPERS } from "../data/demoPapers";
import type { Paper } from "../types";

type CitationStyle = "apa" | "mla" | "bibtex";
function citationFor(p: Paper, style:CitationStyle):string {
  const authors=p.authors.length?p.authors.join(", "):"作者信息待核实";
  const year=p.year??"n.d.";
  if(style==="mla")return authors+'. "'+p.title+'." '+year+'. [来源与期刊信息待核实]';
  if(style==="bibtex"){
    const nameParts=(p.authors[0]??"unknown").split(" ");
    const key=(nameParts[nameParts.length-1]??"unknown").replace(/[^a-zA-Z]/g,"")+
      (p.year??"nd")+"_"+p.title.toLowerCase().replace(/[^a-z0-9]+/g,"_").slice(0,20);
    return "@misc{"+key+",\n  title={"+p.title+"},\n  author={"+authors+
      "},\n  year={"+(p.year??"")+"},\n  note={请核验正式出版信息后使用}\n}";
  }
  return authors+". ("+year+"). "+p.title+". [来源与出版信息待核实]";
}

export function PaperPage() {
  const {paperId=""}=useParams();
  const navigate=useNavigate();
  const [paper,setPaper]=useState<Paper|null>(null);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState("");
  const [expanded,setExpanded]=useState(false);
  const [readingSearch,setReadingSearch]=useState("");
  const [citationStyle,setCitationStyle]=useState<CitationStyle>("apa");
  const [pdfOpen,setPdfOpen]=useState(false);
  const [converting,setConverting]=useState(false);
  const {isFavorite,toggleFavorite,recordView,notify,workspaceReady}=useStudio();

  useEffect(()=>{
    let alive=true;
    setLoading(true);setPaper(null);setError("");setPdfOpen(false);setExpanded(false);
    getPaper(paperId).then((value)=>{
      if(!alive)return;
      setPaper(value);
    }).catch((cause)=>{if(alive)setError(cause instanceof Error?cause.message:"获取论文详情失败")})
      .finally(()=>{if(alive)setLoading(false)});
    return ()=>{alive=false};
  },[paperId]);
  useEffect(()=>{if(paper&&workspaceReady)recordView(paper);},[paper,workspaceReady]);
  useEffect(()=>{ if(paper) document.title=paper.title+" · ScholarLens"; },[paper]);
  const related=useMemo(()=>{
    if(!paper||DATA_SOURCE!=="demo")return [];
    return DEMO_PAPERS.filter((p)=>p.paper_id!==paper.paper_id)
      .map((p)=>({
        paper:p, score:p.keywords.filter(k=>paper.keywords.some(v=>v===k)).length*2+
          p.topics.filter(k=>paper.topics.includes(k)).length
      })).filter(p=>p.score>0).sort((a,b)=>b.score-a.score).slice(0,3).map(p=>p.paper);
  },[paper]);
  const full=paper?.fulltext??"";
  const demoPaper=paper?.paper_id.startsWith("demo-") ?? false;
  const displayText=expanded?full:full.slice(0,4500);
  const canOpenPdf=Boolean(paper?.pdf_available&&DATA_SOURCE==="api");

  const copy=async(text:string,success:string)=>{
    try{await navigator.clipboard.writeText(text);notify(success);}catch{notify("复制失败，请尝试手动复制");}
  };
  const downloadCitation=()=>{
    if(!paper)return;
    const text=citationFor(paper,citationStyle);
    const blob=new Blob([text],{type:"text/plain;charset=utf-8"});
    const url=URL.createObjectURL(blob),a=document.createElement("a");
    a.href=url;a.download=paper.paper_id+"-citation"+(citationStyle==="bibtex"?".bib":".txt");
    document.body.appendChild(a);a.click();a.remove();URL.revokeObjectURL(url);
    notify("已导出参考信息，请核验出版来源");
  };

  return <div className="workspace-page content-wrap detail-page">
    <button className="back-link" onClick={()=>{if(Number.isInteger(window.history.state?.idx)&&window.history.state.idx>0)navigate(-1);else navigate("/search",{replace:true});}}><ArrowLeft size={16}/> 返回上一页</button>
    {loading?<div className="empty-state"><FileText size={29}/> 正在加载论文…</div>:
    error?<div className="empty-state error-state">{error}<Link to="/search" className="button button-secondary">返回检索</Link></div>:
    !paper?<div className="empty-state"><FileQuestion size={33}/><h2>没有找到这篇论文</h2><Link to="/search" className="button button-primary">返回搜索</Link></div>:<>
      <div className="detail-header">
        <div className="detail-tags">{demoPaper?<DemoBadge/>:<span className="paper-source-tag">来自论文检索服务</span>}
          {paper.year&&<span className="year-pill"><Calendar size={14}/>{paper.year}</span>}
          {paper.parse_status!=="unknown"&&<span className="year-pill">解析状态：{{success:"已解析",partial:"部分解析",error:"解析异常"}[paper.parse_status]}</span>}
        </div>
        <h1>{paper.title}</h1>
        <p className="detail-authors">{paper.authors.length?paper.authors.join(" · "):"作者信息暂缺"}</p>
        <div className="detail-buttons">
          <button className="button button-primary" disabled={!workspaceReady} onClick={()=>toggleFavorite(paper)}>
            <Bookmark size={17} fill={isFavorite(paper.paper_id)?"currentColor":"none"}/>
            {isFavorite(paper.paper_id)?"已收藏 · 点击移除":"加入收藏"}
          </button>
          <button className="button button-secondary" onClick={()=>void copy(window.location.href,"论文页面链接已复制")}><Clipboard size={16}/> 分享论文</button>
          {canOpenPdf?<button className="button button-secondary" onClick={()=>setPdfOpen(!pdfOpen)}>
            <FileText size={17}/>{pdfOpen?"收起 PDF":"在线阅读 PDF"}
          </button>:<span className="button button-disabled" aria-disabled="true"><FileText size={17}/> PDF 尚不可用</span>}
          {canOpenPdf&&<button className="button button-secondary" disabled={converting} onClick={async()=>{setConverting(true);try{const blob=await backend<Blob>("/papers/"+encodeURIComponent(paper.paper_id)+"/docx",{blob:true});const url=URL.createObjectURL(blob),link=document.createElement("a");link.href=url;link.download=paper.title.replace(/[\\/:*?"<>|]/g,"_").slice(0,100)+".docx";link.click();window.setTimeout(()=>URL.revokeObjectURL(url),60000);notify("DOCX 已下载：文本转换，不保留复杂版式");}catch(cause){notify(cause instanceof Error?cause.message:"转换失败");}finally{setConverting(false);}}}><Download size={16}/>{converting?"正在转换…":"下载 DOCX"}</button>}
          <Link className="button button-secondary" to={"/assistant?paper="+encodeURIComponent(paper.paper_id)}>
            <Sparkles size={16}/> 论文 AI 助手
          </Link>
        </div>
      </div>
      {canOpenPdf&&pdfOpen&&<section className="embedded-reader">
        <div className="embedded-reader-header"><h2>PDF 在线阅读</h2>
          <a href={pdfUrl(paper.paper_id)} target="_blank" rel="noopener noreferrer" className="button button-secondary">
            <ExternalLink size={16}/> 在独立窗口打开
          </a>
        </div><iframe className="embedded-reader-frame" src={pdfUrl(paper.paper_id)} title={"PDF 原文："+paper.title}/>
        <p>正在阅读原始 PDF。若浏览器无法内嵌显示，请选择“在独立窗口打开”，也可使用阅读器下载原件。</p>
      </section>}
      <div className="detail-grid">
        <article className="detail-main">
          <div className="reading-section">
            <span className="eyebrow">ABSTRACT</span><h2>论文摘要</h2>
            <p className="reading-paragraph">{paper.abstract||"源数据没有提供摘要。"}</p>
            {paper.abstract&&<button className="text-action" onClick={()=>void copy(paper.abstract,"摘要已复制")}>
              <Clipboard size={15}/> 复制摘要
            </button>}
          </div>
          <div className="reading-section">
            <span className="eyebrow">FULL TEXT</span><h2>论文全文</h2>
            {full?<><label className="reader-search"><Search size={17}/>
                <input value={readingSearch} onChange={(e)=>setReadingSearch(e.target.value)} placeholder="在当前全文中查找关键词…" aria-label="全文查找"/>
                {readingSearch&&<span>{full.toLocaleLowerCase().split(readingSearch.toLocaleLowerCase()).length-1} 处匹配</span>}
              </label>
              <div className="reading-paragraph pre-line"><Highlight text={displayText} query={readingSearch}/>{!expanded&&full.length>displayText.length?"\n\n…（部分内容已折叠）":""}</div>
              {full.length>4500&&<button className="text-action" onClick={()=>setExpanded(!expanded)}>
                {expanded?<ChevronUp size={16}/>:<ChevronDown size={16}/>}
                {expanded?"收起全文":"展开全部全文"}
              </button>}</>:<p className="muted">{canOpenPdf?"这篇论文暂无提取文本，请使用上方的 PDF 原文阅读。":"源数据没有提供可阅读的文本。"}</p>}
          </div>
          <IntegrationNotice title="引用前请核对原始文献" desc={demoPaper?
            "本页是虚构示例论文，所有作者、题目、摘要均不可作为真实学术引用。":
            "论文信息来自检索接口，但当前系统未自动验证出版社、DOI 和正式发表信息。"} />
          {related.length>0&&<section className="related-section"><span className="eyebrow">RELATED TOPICS</span>
            <h2>也许你会感兴趣</h2><p>基于本地演示样本的主题和关键词相似性排序，并非语义检索。</p>
            <div className="paper-list">{related.map(item=><PaperCard key={item.paper_id} paper={item} dense/>)}</div>
          </section>}
        </article>
        <aside className="detail-sidebar">
          <div className="info-panel"><h3>文献信息</h3>
            {[
              ["论文编号",paper.paper_id],
              ["发表年份",paper.year??"未知"],
              ["发表日期",paper.date||"未提供"],
              ["作者机构",paper.affiliation.join(" · ")||"未提供"],
              ["机构地址",paper.address.join(" · ")||"未提供"],
              ["原文页数",paper.pages??"未提供"]
            ].map(([label,value])=><div className="info-row" key={label}>
              <span>{label}</span><strong>{value}</strong>
            </div>)}
          </div>
          <div className="info-panel"><h3>主题与关键词</h3>
            <div className="topic-pills">{paper.keywords.length?
              paper.keywords.map((item)=><Link to={"/search?q="+encodeURIComponent(item)+"&field=all"} key={item}>
                {item} <ArrowUpRight size={12}/>
              </Link>):<span>尚无关键词</span>}
            </div>
          </div>
          <div className="info-panel citation-panel"><h3>参考信息工具</h3>
            <p className="muted">可选择格式、复制或导出；缺失的出版信息不会编造。</p>
            <label className="form-label">格式
              <select value={citationStyle} onChange={(e)=>setCitationStyle(e.target.value as CitationStyle)}>
                <option value="apa">APA（简化）</option><option value="mla">MLA（简化）</option><option value="bibtex">BibTeX（待核验）</option>
              </select>
            </label>
            <pre className="citation-preview">{citationFor(paper,citationStyle)}</pre>
            <div className="citation-buttons">
              <button className="button button-secondary" onClick={()=>void copy(citationFor(paper,citationStyle),"参考信息已复制")}>
                <Quote size={15}/> 复制
              </button>
              <button className="button button-secondary" onClick={downloadCitation}>
                <Download size={15}/> 导出
              </button>
            </div>
          </div>
        </aside>
      </div>
    </>}
  </div>;
}
