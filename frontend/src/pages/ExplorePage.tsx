import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { AlertCircle, List, Network, RefreshCcw, Search, SlidersHorizontal, X } from "lucide-react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { PageHeading, IntegrationNotice } from "../components/Layout";
import { PaperCard } from "../components/PaperCard";
import { DATA_SOURCE, getDiscovery, getPaper, getRandomDiscovery } from "../services/papers";
import type { Paper } from "../types";
import { TOPICS } from "../data/demoPapers";

type Order = "random" | "newest" | "oldest" | "title";
const PaperConstellation = lazy(() => import("../components/PaperConstellation").catch(() => ({
  default: () => <div className="empty-state error-state" role="alert"><h3>关系图暂未加载成功</h3><p>可切回列表继续浏览，或刷新页面重试。</p><button type="button" className="button button-secondary" onClick={()=>window.location.reload()}>刷新页面</button></div>
})));
function scramble(id:string,seed:number):number {
  let x=seed*17+101;
  for (let i=0;i<id.length;i++) x=(x*31+id.charCodeAt(i))|0;
  return (x>>>0)/4294967296;
}
export function ExplorePage() {
  const [topic,setTopic]=useState("全部领域");
  const [term,setTerm]=useState("");
  const [order,setOrder]=useState<Order>("newest");
  const [papers,setPapers]=useState<Paper[]>([]);
  const [seed,setSeed]=useState(1);
  const [error,setError]=useState("");
  const [loading,setLoading]=useState(true);
  const [total,setTotal]=useState(0);
  const [view,setView]=useState<"list"|"map">("list");
  const [focusPaper,setFocusPaper]=useState<Paper|null>(null);
  const [focusError,setFocusError]=useState("");
  const [retryToken,setRetryToken]=useState(0);
  const [searchParams]=useSearchParams();
  const navigate=useNavigate();
  const focusId=searchParams.get("focus")||"";
  const seen=useRef<string[]>([]);
  const requestToken=useRef(0);

  useEffect(()=>{
    let alive=true;
    const token=++requestToken.current;
    setLoading(true);setError("");setFocusError("");setFocusPaper(null);
    const focusRequest: Promise<{paper: Paper|null; error: string}> = focusId
      ? getPaper(focusId).then(paper=>({paper,error:paper?"":"没有找到这篇聚焦论文。"})).catch(cause=>({
        paper:null,
        error:cause instanceof Error?cause.message:"这篇论文暂时无法读取"
      }))
      : Promise.resolve({paper:null,error:""});
    Promise.all([getDiscovery(), focusRequest])
      .then(([r,focusedResult])=>{if(alive&&token===requestToken.current){
        const focused=focusedResult.paper;
        setFocusPaper(focused);
        setFocusError(focusedResult.error);
        setTopic("全部领域");setTerm("");
        setPapers(focused ? [focused,...r.papers.filter(item=>item.paper_id!==focused.paper_id)] : r.papers);
        setTotal(r.total);
        if(focused)setView("map");
      }})
      .catch((e)=>{if(alive&&token===requestToken.current)setError(e instanceof Error?e.message:"加载失败")})
      .finally(()=>{if(alive&&token===requestToken.current)setLoading(false)});
    return()=>{alive=false};
  },[focusId,retryToken]);

  const counts=useMemo(()=>(DATA_SOURCE==="demo" ? TOPICS : ["全部领域", ...new Set(papers.flatMap(p=>p.topics))]).map((label)=>({
    label,count:label==="全部领域"?papers.length:papers.filter((p)=>p.topics.includes(label)).length
  })),[papers]);

  const filtered=useMemo(()=>{
    const input=term.trim().toLocaleLowerCase();
    return papers.filter((paper)=>{
      if(topic!=="全部领域"&&!paper.topics.includes(topic))return false;
      if(!input)return true;
      return [paper.title,paper.abstract,paper.keywords.join(" "),paper.authors.join(" ")]
        .join(" ").toLocaleLowerCase().includes(input);
    }).sort((a,b)=>{
      if(order==="newest")return (b.year??0)-(a.year??0);
      if(order==="oldest")return (a.year??0)-(b.year??0);
      if(order==="title")return a.title.localeCompare(b.title);
      return scramble(a.paper_id,seed)-scramble(b.paper_id,seed);
    });
  },[papers,term,topic,order,seed]);
  const focusVisible=Boolean(focusPaper&&filtered.some(paper=>paper.paper_id===focusPaper.paper_id));

  const shuffle=async()=>{
    if(DATA_SOURCE==="demo"){setOrder("random");setSeed(n=>n+Math.floor(3+Math.random()*500));return;}
    const token=++requestToken.current;
    const focusAtStart=focusPaper;
    setLoading(true);setError("");
    try{seen.current=[...new Set([...seen.current,...papers.map(p=>p.paper_id)])].slice(-200);const result=await getRandomDiscovery(seen.current);
      if(token!==requestToken.current)return;
      setPapers(focusAtStart ? [focusAtStart,...result.papers.filter(item=>item.paper_id!==focusAtStart.paper_id)] : result.papers);
      setOrder("random");setSeed(n=>n+1);}
    catch(cause){if(token===requestToken.current)setError(cause instanceof Error?cause.message:"换一批失败");}
    finally{if(token===requestToken.current)setLoading(false);}
  };

  return <div className="workspace-page content-wrap explore-page">
    <PageHeading eyebrow="DISCOVER / RESEARCH" title="探索论文" desc={DATA_SOURCE === "demo" ? "从研究领域出发，筛选感兴趣的主题与文献。" : "从近期论文出发，发现下一条值得追寻的研究线索。"}
      extra={<button className="button button-secondary" onClick={()=>void shuffle()} disabled={loading}>
        <RefreshCcw size={17}/> 换一批</button>}/>
    {DATA_SOURCE==="api"&&<IntegrationNotice title={"论文库 · "+total+" 篇"} desc={"当前选读 "+papers.length+" 篇候选；“换一批”会重新从真实论文库随机取样。筛选与排序作用于当前候选。"}/>}
    {(focusPaper||focusError)&&<div className={"explore-focus-note"+(focusError?" is-error":"")} role={focusError?"alert":"status"}>{focusError?<AlertCircle size={16}/>:<Network size={16}/>}<span>{focusError?"无法载入聚焦论文，已恢复普通探索候选。"+focusError:focusVisible?("已将“"+focusPaper!.title+"”加入候选并在关系图中聚焦。连线只代表可核对的共同元数据。"):"当前筛选已排除聚焦论文；清除筛选后可在关系图中聚焦。"}</span><button className="text-action" type="button" onClick={()=>{++requestToken.current;setFocusPaper(null);setFocusError("");navigate("/explore",{replace:true});}}>退出聚焦</button></div>}
    <section className="explore-controls">
      <div className="topic-selector" role="group" aria-label="研究领域">
        {counts.map((item)=><button key={item.label}
          className={topic===item.label?"selected":""}
          disabled={item.count===0&&item.label!=="全部领域"}
          aria-pressed={topic===item.label}
          onClick={()=>setTopic(item.label)}>{item.label}<span>{item.count}</span></button>)}
      </div>
      <div className="explore-search-row">
        <label className="library-search"><Search size={17}/>
          <input value={term} onChange={(e)=>setTerm(e.target.value)}
            placeholder="筛选题目、作者、摘要或关键词…" aria-label="筛选探索结果"/>
          {term&&<button aria-label="清空探索关键词" onClick={()=>setTerm("")}><X size={15}/></button>}
        </label>
        <label className="sort-select"><SlidersHorizontal size={16}/>
          <select value={order} onChange={(e)=>setOrder(e.target.value as Order)} aria-label="探索结果排序">
            <option value="newest">最新发表</option>
            <option value="oldest">最早发表</option>
            <option value="title">标题顺序</option>
            <option value="random">随机顺序</option>
          </select>
        </label>
      </div>
    </section>
    <div className="results-topbar"><div><span className="eyebrow">BROWSE PAPERS</span>
      <h2>{topic==="全部领域"?"全部研究领域":topic}</h2>
      <p>{loading?"正在读取…":filtered.length+" 篇符合条件 · "+(view==="list"?"列表最多展示 9 篇":"关系图最多展示 20 篇")+(focusPaper?" · 已聚焦一篇论文":"")}</p></div>
      <div className="explore-view-controls">
        {(term||topic!=="全部领域")&&<button className="text-action" onClick={()=>{setTopic("全部领域");setTerm("")}}>清除筛选</button>}
        <div className="segmented" role="group" aria-label="探索显示方式">
          <button type="button" className={view==="list"?"selected":""} aria-pressed={view==="list"} onClick={()=>setView("list")}><List size={16}/> 列表</button>
          <button type="button" className={view==="map"?"selected":""} aria-pressed={view==="map"} onClick={()=>setView("map")}><Network size={16}/> 关系图</button>
        </div>
      </div>
    </div>
    {error?<div className="empty-state error-state" role="alert"><h3>加载失败</h3><p>{error}</p><button type="button" className="button button-secondary" onClick={()=>setRetryToken(value=>value+1)} disabled={loading}><RefreshCcw size={16}/>重新读取</button></div>:
      loading?<div className="paper-skeleton-grid"><div className="paper-skeleton"/><div className="paper-skeleton"/></div>:
      filtered.length?view==="map"?<Suspense fallback={<div className="empty-state" role="status">正在准备论文关系图…</div>}><PaperConstellation papers={filtered} focusId={focusPaper?.paper_id}/></Suspense>:
        <div className="explore-grid">{filtered.slice(0,9).map((paper,index)=>
        <PaperCard key={paper.paper_id} paper={paper} dense order={index+1}/>)}</div>:
      <div className="empty-state"><Search size={27}/><h3>这个条件下没有论文</h3>
        <p>请调整领域或关键词。</p>
        <button className="button button-secondary" onClick={()=>{setTopic("全部领域");setTerm("")}}>查看全部领域</button>
      </div>}
    {DATA_SOURCE==="demo"&&<p className="metric-footnote">本地演示中的论文全部为虚构样本；“换一批”为前端重新排列，并非个性化推荐算法。</p>}
  </div>;
}
