import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, BarChart3, CheckCircle2, Clock3, Download, RotateCcw, Search, Target } from "lucide-react";
import { IntegrationNotice, PageHeading } from "../components/Layout";
import { ToolNavigation } from "../components/ToolNavigation";
import { DATA_SOURCE, searchPapers } from "../services/papers";
import { computeEvaluation } from "../lib/evaluation";
import type { Relevance, RelevanceJudgments } from "../lib/evaluation";
import type { SearchResult } from "../types";
import { readLocal, writeLocal, downloadJson } from "../lib/storage";

type SavedJudgments = Record<string, RelevanceJudgments>;
const LABELS: {value:Relevance;label:string;detail:string}[] = [
  {value:0,label:"无关",detail:"与查询不相关"},
  {value:1,label:"相关",detail:"能够提供有用信息"},
  {value:2,label:"高度相关",detail:"直接回答研究需求"}
];

export function EvaluationPage() {
  const [draft, setDraft] = useState("computer");
  const [currentQuery, setCurrentQuery] = useState("computer");
  const [runVersion, setRunVersion] = useState(0);
  const [data, setData] = useState<SearchResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState<SavedJudgments>(() => readLocal("eval-judgments", {}));
  const key = DATA_SOURCE + "::" + currentQuery.toLocaleLowerCase();
  const grades = saved[key] ?? {};

  useEffect(() => {
    if (!currentQuery.trim()) { setData(null); setLoading(false); return; }
    let active = true;
    setLoading(true); setError(""); setData(null);
    searchPapers({q:currentQuery,field:"all",page:1,pageSize:10,sort:"relevance"})
      .then((results) => { if (active) setData(results); })
      .catch((cause) => { if(active)setError(cause instanceof Error?cause.message:"查询失败"); })
      .finally(() => { if(active)setLoading(false); });
    return () => {active=false};
  }, [currentQuery, runVersion]);

  useEffect(() => { writeLocal("eval-judgments",saved); },[saved]);
  const ids = useMemo(() => data?.papers.map((paper) => paper.paper_id) ?? [], [data]);
  const metrics = computeEvaluation(ids, grades);
  const progress = ids.length ? Math.round(100 * metrics.judged / ids.length) : 0;

  const grade = (id:string,value:Relevance) =>
    setSaved((old) => ({...old,[key]:{...(old[key]??{}),[id]:value}}));

  const clear = () => {
    if (!window.confirm("确认清除这个查询的人工标注？操作不可撤销。")) return;
    setSaved((old) => {
      const next = {...old}; delete next[key]; return next;
    });
  };

  const exportResults = () => {
    if (!data) return;
    downloadJson("scholarlens-evaluation-" + currentQuery.replace(/[^a-zA-Z0-9\u4e00-\u9fa5]/g,"-") + ".json",{
      exportedAt:new Date().toISOString(),
      query:currentQuery,
      retrievalMode:DATA_SOURCE==="demo"?"synthetic-string-match":"backend-keyword",
      ranking:data.papers.map((paper,index)=>({
        rank:index+1,paper_id:paper.paper_id,title:paper.title,
        relevance:grades[paper.paper_id]??null
      })),
      metrics:{precision:metrics.precisionK,precisionAt:metrics.precisionAt,
        ndcg:metrics.ndcgK,ndcgAt:metrics.ndcgAt},
      note:"Only manually judged retrieved documents; recall not computed."
    });
  };

  return <div className="workspace-page content-wrap evaluation-page">
    <PageHeading eyebrow="RETRIEVAL / EVALUATION" title="检索评测" desc="输入查询、标注论文相关性，计算可核查的检索指标。"/>
    <ToolNavigation/>
    <IntegrationNotice title="这是可操作的人工标注工作台" desc={DATA_SOURCE==="demo" ?
      "本地使用虚构样本和字符串匹配。这里计算的是你标注样本上的指标，不能用作 Elasticsearch BM25 的真实实验成绩。" :
      "结果来自当前 FastAPI 接口；指标基于你在本浏览器所做的相关性标注。正式论文报告仍需完整查询集和标注规范。"} />
    <section className="evaluation-workbench">
      <form className="evaluation-search" onSubmit={(e)=>{e.preventDefault();if(draft.trim()){setCurrentQuery(draft.trim());setRunVersion(v=>v+1)}}}>
        <div><span className="eyebrow">STEP 01 · YOUR QUERY</span><h2>选择检索问题</h2><p>建议使用明确的学术关键词，以便逐项判断论文相关性。</p></div>
        <label><Search size={19}/><input value={draft} onChange={e=>setDraft(e.target.value)} placeholder="输入评测查询…" aria-label="评测查询词" required/>
          <button className="button button-primary" type="submit">运行查询 <ArrowRight size={16}/></button></label>
      </form>
      {error && <div className="inline-error" role="alert">{error}</div>}
      <div className="evaluation-progress">
        <div><span className="eyebrow">STEP 02 · RELEVANCE JUDGMENT</span><h2>逐篇判断相关性</h2>
          <p>同一个查询的标注会自动保存在当前浏览器。建议为当前全部结果标注。</p></div>
        <div className="evaluation-progress-data"><strong>{metrics.judged} / {ids.length}</strong><span>已标注</span>
          <div className="evaluation-progress-track"><span style={{width:progress+"%"}}/></div>
        </div>
      </div>
      {loading?<div className="paper-skeleton-grid">{Array.from({length:3},(_,i)=><div className="paper-skeleton" key={i}/>)}</div>:
        data&&data.papers.length ? <div className="evaluation-rows">{data.papers.map((paper,index)=>
          <article className="evaluation-row" key={paper.paper_id}>
            <div className="evaluation-row-content"><span className="eval-rank">#{index+1} · {paper.year??"年份未知"}</span>
              <Link to={"/paper/"+encodeURIComponent(paper.paper_id)}><h3>{paper.title}</h3></Link>
              <p>{paper.authors.join(" · ")||"作者信息暂缺"}</p>
              <p>{paper.abstract.slice(0,210)}{paper.abstract.length>210?"…":""}</p>
            </div>
            <div className="evaluation-votes"><span>相关性分级</span>{LABELS.map(option=>
              <button className={grades[paper.paper_id]===option.value?"selected":""} key={option.value}
                title={option.detail} aria-pressed={grades[paper.paper_id]===option.value}
                onClick={()=>grade(paper.paper_id,option.value)}>{option.value} · {option.label}</button>)}
            </div>
          </article>)}</div>
        :!error&&<div className="empty-state"><h3>没有可标注的论文</h3><p>请调整查询后重新检索。</p></div>}
      <div className="evaluation-toolbar">
        <button className="button button-secondary" onClick={clear} disabled={!metrics.judged}><RotateCcw size={17}/> 清空当前标注</button>
        <button className="button button-secondary" onClick={exportResults} disabled={!data}><Download size={17}/> 导出标注与指标</button>
      </div>
    </section>
    <section className="evaluation-summary">
      <div className="section-heading"><div><span className="eyebrow">STEP 03 · RESULTS</span><h2>人工标注结果</h2></div><span className="table-status">只计算已完整标注的当前结果</span></div>
      <div className="metric-grid">
        <div className="metric-card"><div className="metric-icon"><Target size={22}/></div><h3>Precision@{metrics.precisionAt||5}</h3>
          <strong className="metric-value">{metrics.precisionK===null?"—":(100*metrics.precisionK).toFixed(1)+"%"}</strong>
          <p>前 {metrics.precisionAt||5} 条中被你判断为相关或高度相关的论文比例。</p>
        </div>
        <div className="metric-card"><div className="metric-icon"><BarChart3 size={22}/></div><h3>nDCG@{metrics.ndcgAt||10}</h3>
          <strong className="metric-value">{metrics.ndcgK===null?"—":metrics.ndcgK.toFixed(3)}</strong>
          <p>当前标注结果的排序质量；使用 0 / 1 / 2 三级相关性。</p>
        </div>
        <div className="metric-card"><div className="metric-icon"><CheckCircle2 size={22}/></div><h3>标注完成率</h3>
          <strong className="metric-value">{ids.length?progress+"%":"—"}</strong>
          <p>本次返回的 {ids.length} 篇论文中，已完成标注的比例。</p>
        </div>
        <div className="metric-card"><div className="metric-icon"><Clock3 size={22}/></div><h3>查询耗时</h3>
          <strong className="metric-value">{data?.dataKind==="api"&&data.durationMs!==null?data.durationMs+" ms":"—"}</strong>
          <p>{DATA_SOURCE==="demo"?"本地模拟不展示伪造的服务器耗时。":"接口请求耗时，具体统计口径须核对后端。"} </p>
        </div>
      </div>
      <p className="metric-footnote">{metrics.message} Recall 需要完整的语料相关性标注池，目前不计算。不同检索方法的公平对比还需要固定查询集与实验脚本。</p>
    </section>
  </div>;
}
