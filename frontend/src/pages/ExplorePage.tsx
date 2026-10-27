import { useEffect, useMemo, useRef, useState } from "react";
import { RefreshCcw, Search, SlidersHorizontal, X } from "lucide-react";
import { PageHeading, IntegrationNotice } from "../components/Layout";
import { PaperCard } from "../components/PaperCard";
import { DATA_SOURCE, getDiscovery, getRandomDiscovery } from "../services/papers";
import type { Paper } from "../types";
import { TOPICS } from "../data/demoPapers";

type Order = "random" | "newest" | "oldest" | "title";
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
  const seen=useRef<string[]>([]);

  useEffect(()=>{
    let alive=true;
    getDiscovery()
      .then((r)=>{if(alive){setPapers(r.papers);setTotal(r.total);}})
      .catch((e)=>{if(alive)setError(e instanceof Error?e.message:"加载失败")})
      .finally(()=>{if(alive)setLoading(false)});
    return()=>{alive=false};
  },[]);

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

  const shuffle=async()=>{
    if(DATA_SOURCE==="demo"){setOrder("random");setSeed(n=>n+Math.floor(3+Math.random()*500));return;}
    setLoading(true);setError("");
    try{seen.current=[...new Set([...seen.current,...papers.map(p=>p.paper_id)])].slice(-200);const result=await getRandomDiscovery(seen.current);setPapers(result.papers);setOrder("random");setSeed(n=>n+1);}
    catch(cause){setError(cause instanceof Error?cause.message:"换一批失败");}finally{setLoading(false);}
  };

  return <div className="workspace-page content-wrap explore-page">
    <PageHeading eyebrow="DISCOVER / RESEARCH" title="探索论文" desc={DATA_SOURCE === "demo" ? "从研究领域出发，筛选感兴趣的主题与文献。" : "从近期论文出发，发现下一条值得追寻的研究线索。"}
      extra={<button className="button button-secondary" onClick={()=>void shuffle()} disabled={loading}>
        <RefreshCcw size={17}/> 换一批</button>}/>
    {DATA_SOURCE==="api"&&<IntegrationNotice title={"论文库 · "+total+" 篇"} desc={"当前选读 "+papers.length+" 篇候选；“换一批”会重新从真实论文库随机取样。筛选与排序作用于当前候选。"}/>}
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
      <p>{loading?"正在读取…":filtered.length+" 篇符合条件 · 当前展示最多 9 篇"}</p></div>
      {(term||topic!=="全部领域")&&<button className="button button-secondary" onClick={()=>{setTopic("全部领域");setTerm("")}}>清除筛选</button>}
    </div>
    {error?<div className="empty-state error-state"><h3>加载失败</h3><p>{error}</p></div>:
      loading?<div className="paper-skeleton-grid"><div className="paper-skeleton"/><div className="paper-skeleton"/></div>:
      filtered.length?<div className="explore-grid">{filtered.slice(0,9).map((paper,index)=>
        <PaperCard key={paper.paper_id} paper={paper} dense order={index+1}/>)}</div>:
      <div className="empty-state"><Search size={27}/><h3>这个条件下没有论文</h3>
        <p>请调整领域或关键词。</p>
        <button className="button button-secondary" onClick={()=>{setTopic("全部领域");setTerm("")}}>查看全部领域</button>
      </div>}
    {DATA_SOURCE==="demo"&&<p className="metric-footnote">本地演示中的论文全部为虚构样本；“换一批”为前端重新排列，并非个性化推荐算法。</p>}
  </div>;
}
