import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { PointerEvent } from "react";
import { ArrowRight, BookOpen, ChevronLeft, ChevronRight, Clock3, Pause, Play, Quote } from "lucide-react";
import { Link } from "react-router-dom";
import { useStudio } from "../App";
import { DATA_SOURCE } from "../services/papers";
import type { HistoryEntry } from "../types";

function ReadingFace({ entry, preview = false }: { entry: HistoryEntry; preview?: boolean }) {
  const { paper } = entry;
  return <>
    <div className="hero-paper-meta">{paper.year ?? "年份暂缺"}<span>·</span>{paper.topics?.[0] || "阅读记录"}</div>
    {preview ? <div className="hero-paper-title">{paper.title}</div> :
      <Link className="hero-paper-title" title={paper.title} to={"/paper/" + encodeURIComponent(paper.paper_id)}>{paper.title}</Link>}
    <p className="hero-paper-authors">{paper.authors?.join(" · ") || "作者信息暂缺"}</p>
    <div className="hero-paper-excerpt"><Quote size={18}/><p>{paper.abstract || "这篇文献暂无摘要，打开原文继续阅读。"}</p></div>
    <div className="hero-paper-bottom"><span>{paper.paper_id.startsWith("demo-") ? "演示论文 · 虚构内容" : "来自你的阅读记录"}</span>
      {preview ? <span className="recent-preview-arrow"><ArrowRight size={18}/></span> :
        <Link to={"/paper/" + encodeURIComponent(paper.paper_id)} aria-label={"继续阅读：" + paper.title}><ArrowRight size={18}/></Link>}
    </div>
  </>;
}

export function RecentReadingDeck() {
  const { history, motionPaused, reducedMotion } = useStudio();
  const entries = useMemo(() => {
    const seen = new Set<string>();
    return [...history].sort((a, b) => (Date.parse(b.viewedAt) || 0) - (Date.parse(a.viewedAt) || 0))
      .filter(({ paper }) => {
        if (!paper?.paper_id || seen.has(paper.paper_id)) return false;
        seen.add(paper.paper_id); return true;
      }).slice(0, 5);
  }, [history]);
  const [selected, setSelected] = useState<string | null>(null);
  const [turn, setTurn] = useState<{ entry: HistoryEntry; direction: "next" | "previous" } | null>(null);
  const [automatic, setAutomatic] = useState(true);
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const [visible, setVisible] = useState(false);
  const deckRef = useRef<HTMLDivElement>(null);
  const swipeStart = useRef<{ x: number; y: number } | null>(null);
  const suppressClick = useRef(false);
  const restoreTitleFocus = useRef(false);
  const index = Math.max(0, entries.findIndex(({ paper }) => paper.paper_id === selected));
  const entry = entries[index];
  const motionEnabled = !motionPaused && !reducedMotion;
  const canRotate = entries.length > 1;
  const autoRunning = automatic && motionEnabled && canRotate && visible && !hovered && !focused;

  const goTo = useCallback((nextIndex: number, direction: "next" | "previous") => {
    if (!entry || turn || nextIndex === index || !entries[nextIndex]) return;
    if (motionEnabled) setTurn({ entry, direction });
    setSelected(entries[nextIndex].paper.paper_id);
  }, [entries, entry, index, motionEnabled, turn]);
  const step = (direction: number) => {
    if (canRotate) goTo((index + direction + entries.length) % entries.length, direction > 0 ? "next" : "previous");
  };
  useEffect(() => {
    if (!turn) return;
    if (!motionEnabled) { setTurn(null); return; }
    // Also completes if the animation is interrupted by a preference change or hidden tab.
    const timer = window.setTimeout(() => setTurn(null), 740);
    return () => window.clearTimeout(timer);
  }, [turn, motionEnabled]);
  useEffect(() => {
    const deck = deckRef.current;
    if (!deck) return;
    let inView = false;
    const sync = () => setVisible(inView && !document.hidden);
    const observer = new IntersectionObserver(([item]) => { inView = item.isIntersecting; sync(); }, { threshold: .4 });
    observer.observe(deck);
    document.addEventListener("visibilitychange", sync);
    return () => { observer.disconnect(); document.removeEventListener("visibilitychange", sync); };
  }, []);
  useEffect(() => {
    if (!autoRunning || turn) return;
    const timer = window.setTimeout(() => goTo((index + 1) % entries.length, "next"), 7000);
    return () => window.clearTimeout(timer);
  }, [autoRunning, turn, index, entries.length, goTo]);
  useEffect(() => {
    if (turn || !restoreTitleFocus.current) return;
    restoreTitleFocus.current = false;
    deckRef.current?.querySelector<HTMLAnchorElement>(".recent-current-page .hero-paper-title")?.focus({ preventScroll: true });
  }, [selected, turn]);

  const finishSwipe = (event: PointerEvent<HTMLDivElement>) => {
    const start = swipeStart.current; swipeStart.current = null;
    if (!start) return;
    const dx = event.clientX - start.x, dy = event.clientY - start.y;
    if (Math.abs(dx) > 45 && Math.abs(dx) > Math.abs(dy) * 1.3 && canRotate) {
      suppressClick.current = true; step(dx < 0 ? 1 : -1);
    }
  };
  return <div ref={deckRef} className="recent-deck" role="region" aria-roledescription="轮播" aria-label="最近阅读"
    data-count={entries.length} data-state={turn ? "turning" : "ready"}
    onPointerEnter={event => { if (event.pointerType === "mouse") setHovered(true); }} onPointerLeave={() => { setHovered(false); swipeStart.current = null; }}
    onFocusCapture={() => setFocused(true)} onBlurCapture={event => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setFocused(false); }}
    onPointerDown={event => { suppressClick.current = false; if (event.pointerType === "touch") swipeStart.current = { x: event.clientX, y: event.clientY }; }}
    onPointerUp={finishSwipe} onPointerCancel={() => { swipeStart.current = null; }}
    onClickCapture={event => { if (suppressClick.current) { event.preventDefault(); event.stopPropagation(); suppressClick.current = false; } }}
    onKeyDown={event => {
      if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
      event.preventDefault();
      if (canRotate && !turn && event.target instanceof Element && event.target.closest(".recent-current-page")) restoreTitleFocus.current = true;
      step(event.key === "ArrowRight" ? 1 : -1);
    }}>
    <div className="hero-paper-sheet">
      <div className="hero-paper-top"><span><Clock3 size={15}/>最近阅读</span><span>{entries.length ? "最近 " + entries.length + " 篇" : "等待第一篇"}</span></div>
      {entry ? <>
        <div className="recent-page-viewport">
          <div key={entry.paper.paper_id} className="recent-current-page" data-paper-id={entry.paper.paper_id} role="group" aria-roledescription="页面" aria-label={`第 ${index + 1} 篇，共 ${entries.length} 篇`}>
            <ReadingFace entry={entry}/>
          </div>
          {turn && <div className={"recent-turning-page turn-" + turn.direction} aria-hidden="true" onAnimationEnd={event => { if (event.target === event.currentTarget) setTurn(null); }}>
            <div className="recent-turn-front"><ReadingFace entry={turn.entry} preview/></div>
            <div className="recent-turn-back"><BookOpen size={32} strokeWidth={1}/><span/><span/><span/></div>
          </div>}
        </div>
        <div className="recent-pagination">
          <button type="button" className="recent-prev" aria-label="上一篇阅读记录" disabled={!canRotate || !!turn} onClick={() => step(-1)}><ChevronLeft size={18}/></button>
          <div className="recent-pagination-center"><span className="recent-page-count" aria-live={autoRunning ? "off" : "polite"}>{index + 1}<span> / {entries.length}</span></span>
            <div className="recent-page-dots">{entries.map(({ paper }, i) => <button key={paper.paper_id} type="button" disabled={!!turn} aria-label={`查看第 ${i + 1} 篇：${paper.title}`} aria-current={i === index ? "true" : undefined} onClick={() => goTo(i, i > index ? "next" : "previous")}><span/></button>)}</div>
          </div>
          <button type="button" className="recent-next" aria-label="下一篇阅读记录" disabled={!canRotate || !!turn} onClick={() => step(1)}><ChevronRight size={18}/></button>
          {canRotate && <button type="button" className="recent-autoplay" aria-label={automatic ? "暂停自动翻页" : "开启自动翻页"} aria-pressed={!automatic} disabled={!motionEnabled} onClick={() => setAutomatic(!automatic)}>{automatic ? <Pause size={13}/> : <Play size={13}/>}</button>}
        </div>
      </> : <div className="empty-artifact-box">
        <div className="empty-artifact-glow">
          <BookOpen size={32} strokeWidth={1.6}/>
        </div>
        <div className="hero-capsule-badge" style={{marginBottom: "12px", padding: "4px 14px"}}>
          <span className="badge-dot"/>
          <span className="badge-title">3D 透镜空间</span>
          <span className="badge-sep">·</span>
          <span>探索就绪</span>
        </div>
        <h3>开启你的学术阅读</h3>
        <p>检索文献并打开原文，你的最近阅读足迹与笔记进度将在此以 3D 叠层形式实时呈现。</p>
        <div className="empty-artifact-features">
          <span>✦ {DATA_SOURCE === "api" ? "真实论文库" : "18 篇演示论文"}</span>
          <span>✦ 毫秒级原文定位</span>
          <span>✦ 多维证据链核查</span>
        </div>
        <Link to="/search" className="button button-primary" style={{display: "inline-flex", alignItems: "center", gap: "8px", textDecoration: "none"}}>
          开始探索文献 <ArrowRight size={16}/>
        </Link>
      </div>}
    </div>
  </div>;
}
