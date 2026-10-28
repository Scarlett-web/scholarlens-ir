import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight, Network, RotateCcw } from "lucide-react";
import { buildPaperGraph, relationLabels } from "../lib/paperRelations";
import type { Paper } from "../types";

/** Keep a visible focus node inside the graph's bounded input without changing other order. */
export function prioritizeFocus(papers: Paper[], focusId?: string): Paper[] {
  if (!focusId) return papers;
  const index = papers.findIndex(paper => paper.paper_id === focusId);
  if (index <= 0) return papers;
  return [papers[index], ...papers.slice(0, index), ...papers.slice(index + 1)];
}

export default function PaperConstellation({ papers, focusId }: { papers: Paper[]; focusId?: string }) {
  const graph = useMemo(() => buildPaperGraph(prioritizeFocus(papers, focusId)), [papers, focusId]);
  const [selected, setSelected] = useState("");
  useEffect(() => {
    setSelected(focusId && graph.nodes.some(node => node.paper.paper_id === focusId) ? focusId : "");
  }, [focusId, graph]);
  const active = graph.nodes.find(node => node.paper.paper_id === selected)
    ?? graph.nodes.reduce<(typeof graph.nodes)[number] | undefined>((best, node) => !best || node.degree > best.degree ? node : best, undefined);
  const scene = useRef<HTMLDivElement>(null);
  const frame = useRef(0);
  const drag = useRef<{ x: number; y: number } | null>(null);
  useEffect(() => () => cancelAnimationFrame(frame.current), []);
  if (!active) return null;
  const relations = graph.edges.filter(edge => edge.source === active.paper.paper_id || edge.target === active.paper.paper_id);
  const adjacent = new Set(relations.flatMap(edge => [edge.source, edge.target]));
  const reset = () => { cancelAnimationFrame(frame.current); scene.current?.style.removeProperty("--map-rx"); scene.current?.style.removeProperty("--map-ry"); };
  return <section className="paper-constellation" aria-label="当前候选论文关系图">
    <div className="constellation-map">
      <div className="constellation-heading"><span><Network size={16}/> {graph.nodes.length} 篇论文 · {graph.edges.length} 组关联</span>
        <button className="text-action" type="button" onClick={reset}><RotateCcw size={14}/> 复位视角</button></div>
      <div className="constellation-space" onPointerDown={event => {
        if ((event.target as Element).closest("button") || event.button !== 0) return;
        drag.current = { x: event.clientX, y: event.clientY }; event.currentTarget.setPointerCapture(event.pointerId);
      }} onPointerMove={event => {
        if (!drag.current) return;
        const x = Math.max(-8, Math.min(8, (event.clientX - drag.current.x) / 24));
        const y = Math.max(-6, Math.min(6, (drag.current.y - event.clientY) / 32));
        cancelAnimationFrame(frame.current);
        frame.current = requestAnimationFrame(() => { scene.current?.style.setProperty("--map-rx", y + "deg"); scene.current?.style.setProperty("--map-ry", x + "deg"); });
      }} onPointerUp={event => { drag.current = null; if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId); }}
        onPointerCancel={() => { drag.current = null; }}>
        <div className="constellation-plane" ref={scene}>
          <svg className="constellation-edges" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
            {graph.edges.map(edge => {
              const source = graph.nodes.find(node => node.paper.paper_id === edge.source)!;
              const target = graph.nodes.find(node => node.paper.paper_id === edge.target)!;
              return <line key={edge.source + edge.target} data-source={edge.source} data-target={edge.target} x1={source.x} y1={source.y} x2={target.x} y2={target.y}
                data-active={edge.source === active.paper.paper_id || edge.target === active.paper.paper_id}/>;
            })}
          </svg>
          <div className="constellation-nodes" role="group" aria-label="选择论文查看关联">
            {graph.nodes.map(node => <button key={node.paper.paper_id} type="button" className="constellation-node"
              style={{ left: node.x + "%", top: node.y + "%", "--node-size": 32 + Math.min(16, node.degree * 4) + "px" } as CSSProperties}
              data-paper-id={node.paper.paper_id} data-relations={node.degree} data-related={adjacent.has(node.paper.paper_id)} aria-pressed={node === active}
              aria-label={node.index + ". " + node.paper.title} title={node.paper.title}
              onClick={() => setSelected(node.paper.paper_id)}>
              <span>{String(node.index).padStart(2, "0")}</span><small>{node.paper.year ?? "年份未知"}</small>
            </button>)}
          </div>
        </div>
      </div>
      <p className="constellation-caption">点击节点，或用 Tab 定位后按回车选择。拖动空白处轻转视角；节点大小表示本图关联数。</p>
    </div>
    <aside className="constellation-detail" aria-label="所选论文与连线依据">
      <span className="section-kicker">论文 {String(active.index).padStart(2, "0")} · {active.paper.year ?? "年份未知"}</span>
      <h3>{active.paper.title}</h3><p className="constellation-authors">{active.paper.authors.join(" · ") || "作者信息暂缺"}</p>
      <Link className="text-action" to={"/paper/" + encodeURIComponent(active.paper.paper_id)}>阅读这篇论文 <ArrowUpRight size={15}/></Link>
      <div className="constellation-reasons"><h4>{relations.length ? "与 " + relations.length + " 篇候选存在共同字段" : "尚无共同字段"}</h4>
        {!relations.length && <p>这批候选中暂未找到可核对的共同元数据。仍可打开原文，或换一批继续探索。</p>}
        {relations.map(edge => {
          const other = graph.nodes.find(node => node.paper.paper_id === (edge.source === active.paper.paper_id ? edge.target : edge.source))!;
          return <button type="button" key={other.paper.paper_id} onClick={() => setSelected(other.paper.paper_id)}>
            <span>{String(other.index).padStart(2, "0")} · {other.paper.title}</span>
            <small>{edge.reasons.map(reason => relationLabels[reason.kind] + "：" + reason.value).join("；")}</small>
          </button>;
        })}
      </div>
      <p className="constellation-scope">连线来自当前候选的原始元数据，相同姓名需核对身份。这里不表示引用关系或语义距离。{graph.omitted > 0 ? "另有 " + graph.omitted + " 篇未显示，可缩小筛选范围。" : ""}</p>
    </aside>
  </section>;
}
