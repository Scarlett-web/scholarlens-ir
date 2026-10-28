import { useEffect, useMemo, useState } from "react";
import { ArrowUpRight, Network, RefreshCcw } from "lucide-react";
import { Link } from "react-router-dom";
import { DATA_SOURCE, getDiscovery } from "../services/papers";
import { DEMO_PAPERS } from "../data/demoPapers";
import { buildPaperGraph, relationLabels } from "../lib/paperRelations";
import type { Paper } from "../types";

/** Show exact metadata overlaps before sending the reader to the full map. */
export function PaperRelationsPanel({ paper }: { paper: Paper }) {
  const [candidates, setCandidates] = useState<Paper[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [retryToken, setRetryToken] = useState(0);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    const request = DATA_SOURCE === "demo" ? Promise.resolve({ papers: DEMO_PAPERS }) : getDiscovery();
    request.then((result) => {
      if (active) setCandidates(result.papers.filter(item => item.paper_id !== paper.paper_id));
    }).catch((cause) => {
      if (active) setError(cause instanceof Error ? cause.message : "关系候选暂时不可用");
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [paper.paper_id, retryToken]);

  const graph = useMemo(() => buildPaperGraph([paper, ...candidates.slice(0, 19)]), [paper, candidates]);
  const relations = useMemo(() => {
    const edges = graph.edges.filter(edge => edge.source === paper.paper_id || edge.target === paper.paper_id);
    return edges.map(edge => {
      const id = edge.source === paper.paper_id ? edge.target : edge.source;
      const other = graph.nodes.find(node => node.paper.paper_id === id)?.paper;
      return other ? { other, reasons: edge.reasons } : null;
    }).filter((item): item is { other: Paper; reasons: typeof graph.edges[number]["reasons"] } => Boolean(item)).slice(0, 3);
  }, [graph, paper.paper_id]);

  return <section className="detail-relations" aria-labelledby="paper-relations-title">
    <div className="detail-relations-heading">
      <div><span className="eyebrow">METADATA CONNECTIONS</span><h2 id="paper-relations-title">从这篇论文继续探索</h2></div>
      <Network size={18} aria-hidden="true" />
    </div>
    <p className="detail-relations-intro">{DATA_SOURCE === "api" ? "按作者与机构的原始记录寻找共同线索" : "按作者、关键词、主题或机构的原始记录寻找共同线索"}，不推断引用关系或语义相似度。</p>
    {loading ? <p className="detail-relations-state" role="status"><RefreshCcw size={15}/> 正在读取关系候选…</p> : error ?
      <p className="detail-relations-state" role="alert">暂时无法读取候选论文：{error}<button type="button" className="text-action" onClick={()=>setRetryToken(value=>value+1)}><RefreshCcw size={14}/> 重试</button></p> : relations.length ?
      <div className="detail-relations-list">{relations.map(({ other, reasons }) => <Link key={other.paper_id} className="detail-relation-item" to={"/paper/" + encodeURIComponent(other.paper_id)}>
        <span className="detail-relation-main"><strong>{other.title}</strong><small>{other.authors.join(" · ") || "作者信息暂缺"}</small></span>
        <span className="detail-relation-reasons">{reasons.map(reason => relationLabels[reason.kind] + "：" + reason.value).join("；")}</span>
        <ArrowUpRight size={16} aria-hidden="true" />
      </Link>)}</div> :
      <p className="detail-relations-state">当前候选中没有可核对的共同字段。你仍可以打开关系图，换一批论文继续寻找线索。</p>}
    <Link className="detail-relations-map" to={"/explore?focus=" + encodeURIComponent(paper.paper_id)}><Network size={15}/> 在关系图中查看候选 <ArrowUpRight size={14}/></Link>
  </section>;
}
