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
  const { isFavorite, toggleFavorite, workspaceReady } = useStudio();
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
          disabled={!workspaceReady} onClick={() => toggleFavorite(paper)}><Bookmark size={19} fill={saved ? "currentColor" : "none"} /></button>
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
