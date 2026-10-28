import { useEffect, useRef, useState, type RefObject } from "react";
import { BookOpen, Check, Clipboard, Focus, Highlighter, RotateCcw, X } from "lucide-react";
import { useAuth } from "../services/AuthContext";
import { useStudio } from "../App";
import { loadReadingPosition, saveReadingPosition, type ReadingPosition } from "../lib/readingPosition";
import type { Paper } from "../types";

interface Props {
  paper: Paper;
  articleRef: RefObject<HTMLElement>;
  expanded: boolean;
  setExpanded(value: boolean): void;
  focused: boolean;
  setFocused(value: boolean): void;
}

export function ReadingToolbar({ paper, articleRef, expanded, setExpanded, focused, setFocused }: Props) {
  const { user } = useAuth();
  const { appendFavoriteExcerpt, notify, workspaceReady } = useStudio();
  const [progress, setProgress] = useState(0);
  const [saved] = useState(() => loadReadingPosition(user?.id, paper.paper_id, paper.fulltext.length));
  const [restoring, setRestoring] = useState<ReadingPosition | null>(null);
  const [restoreOffered, setRestoreOffered] = useState(Boolean(saved && saved.ratio > .02));
  const [storageFailed, setStorageFailed] = useState(false);
  const [selection, setSelection] = useState("");
  const [active, setActive] = useState("paper-abstract");
  const toolbar = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const article = articleRef.current;
    if (!article) return;
    let frame = 0, timer = 0;
    let pending: ReadingPosition | null = null;
    const offset = () => (toolbar.current?.getBoundingClientRect().height ?? 64) + 24;
    const persist = () => {
      if (!pending) return;
      if (!saveReadingPosition(user?.id, paper.paper_id, pending)) setStorageFailed(true);
      pending = null;
    };
    const measure = (save: boolean) => {
      frame = 0;
      const rect = article.getBoundingClientRect();
      const distance = Math.max(1, rect.height - window.innerHeight + offset());
      const ratio = Math.max(0, Math.min(1, (offset() - rect.top) / distance));
      setProgress(Math.round(ratio * 100));
      const sections = ["paper-abstract", "paper-fulltext"];
      const current = sections.filter(id => {
        const element = document.getElementById(id);
        return element && element.getClientRects().length && element.getBoundingClientRect().top <= offset() + 80;
      });
      setActive(current.at(-1) ?? "paper-abstract");
      if (save && ratio > .02 && rect.top < offset()) {
        pending = { ratio, expanded, textLength: paper.fulltext.length, savedAt: new Date().toISOString() };
        window.clearTimeout(timer);
        timer = window.setTimeout(persist, 350);
      }
    };
    const scroll = () => { if (!frame) frame = requestAnimationFrame(() => measure(true)); };
    const resize = () => { if (!frame) frame = requestAnimationFrame(() => measure(false)); };
    const observer = new ResizeObserver(resize);
    observer.observe(article);
    measure(false);
    window.addEventListener("scroll", scroll, { passive: true });
    window.addEventListener("resize", resize);
    window.addEventListener("pagehide", persist);
    return () => {
      cancelAnimationFrame(frame);window.clearTimeout(timer);persist();observer.disconnect();
      window.removeEventListener("scroll", scroll);
      window.removeEventListener("resize", resize);
      window.removeEventListener("pagehide", persist);
    };
  }, [articleRef, expanded, focused, paper.paper_id, paper.fulltext.length, user?.id]);

  useEffect(() => {
    if (!restoring) return;
    const frame = requestAnimationFrame(() => {
      const article = articleRef.current;
      if (!article) return;
      const offset = (toolbar.current?.getBoundingClientRect().height ?? 64) + 24;
      const distance = Math.max(1, article.getBoundingClientRect().height - window.innerHeight + offset);
      window.scrollTo({ top: window.scrollY + article.getBoundingClientRect().top - offset + restoring.ratio * distance, behavior: "instant" });
      setRestoring(null);setRestoreOffered(false);
    });
    return () => cancelAnimationFrame(frame);
  }, [restoring, expanded, articleRef]);

  useEffect(() => {
    const article = articleRef.current;
    if (!article) return;
    const readSelection = () => {
      const range = window.getSelection();
      const start = range?.anchorNode?.parentElement?.closest("[data-reader-text]");
      const end = range?.focusNode?.parentElement?.closest("[data-reader-text]");
      setSelection(range && start && start === end && article.contains(start) ? range.toString().trim() : "");
    };
    article.addEventListener("mouseup", readSelection);
    article.addEventListener("keyup", readSelection);
    return () => {article.removeEventListener("mouseup", readSelection);article.removeEventListener("keyup", readSelection);};
  }, [articleRef]);

  useEffect(() => {
    if (!focused) return;
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") setFocused(false); };
    document.addEventListener("keydown", escape);
    return () => document.removeEventListener("keydown", escape);
  }, [focused, setFocused]);

  const jump = (id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: "instant", block: "start" });
    document.getElementById(id)?.focus({ preventScroll: true });
    setActive(id);
  };
  return <div className="reader-tools" ref={toolbar}>
    <div className="reader-toolbar">
      <nav aria-label="本页阅读导航">
        {[["paper-abstract", "摘要"], ["paper-fulltext", "正文"], ...(!focused ? [["paper-info", "文献信息"], ["paper-citation", "参考工具"]] : [])].map(([id, label]) =>
          <button key={id} type="button" aria-current={active === id ? "location" : undefined} onClick={() => jump(id)}>{label}</button>)}
      </nav>
      <div className="reader-progress" title="按当前展开内容和滚动位置计算，不代表已完成阅读">
        <BookOpen size={14}/><span>{expanded || paper.fulltext.length <= 4500 ? "阅读位置" : "已展开内容"} {progress}%</span>
        <progress max="100" value={progress} aria-label="当前展开内容的阅读位置"/>
      </div>
      <button className="reader-focus-button" type="button" aria-pressed={focused} onClick={() => {setFocused(!focused);if (!focused) setExpanded(true);}}>
        {focused ? <X size={16}/> : <Focus size={16}/>} {focused ? "退出专注" : "专注阅读"}
      </button>
    </div>
    {restoreOffered && saved && <div className="reader-resume"><span><RotateCcw size={14}/> 上次读到 {Math.round(saved.ratio * 100)}% <small>位置仅保存在当前浏览器</small></span>
      <button type="button" onClick={() => {setExpanded(saved.expanded);setRestoring(saved);}}>继续上次阅读</button>
      <button className="icon-button" type="button" aria-label="暂不恢复阅读位置" onClick={() => setRestoreOffered(false)}><X size={14}/></button>
    </div>}
    {selection && <div className="reader-selection" aria-label="选中文本操作">
      <span><Highlighter size={16}/><span>{selection}</span></span>
      <button type="button" onClick={async () => {try {await navigator.clipboard.writeText(selection);notify("所选原文已复制");} catch {notify("复制失败，请使用浏览器复制命令");}}}><Clipboard size={14}/> 复制</button>
      <button type="button" disabled={!workspaceReady || selection.length > 1900} title={selection.length > 1900 ? "摘录过长，请缩短所选文本" : "追加到这篇论文的收藏笔记，保留已有内容"} onClick={() => {if (appendFavoriteExcerpt(paper, selection)) {setSelection("");window.getSelection()?.removeAllRanges();}}}><Check size={14}/> 加入笔记</button>
      <button className="icon-button" type="button" aria-label="收起摘录操作" onClick={() => setSelection("")}><X size={14}/></button>
    </div>}
    {storageFailed && <p className="reader-storage-error" role="status">阅读位置未能保存，请检查浏览器存储权限；本次仍可继续阅读。</p>}
  </div>;
}
