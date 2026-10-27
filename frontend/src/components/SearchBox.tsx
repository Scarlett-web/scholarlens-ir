import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, ChevronDown, Clock3, Search, Trash2 } from "lucide-react";
import { FIELD_OPTIONS } from "../types";
import type { SearchField, SearchMode } from "../types";
import { DATA_SOURCE, getSuggestions } from "../services/papers";
import { useSearchCapabilities } from "../services/useSearchCapabilities";
import { readLocal, writeLocal } from "../lib/storage";

interface Props {
  variant?: "hero" | "compact";
  initialQuery?: string;
  initialField?: SearchField;
  initialMode?: SearchMode;
}

export function SearchBox({ variant = "hero", initialQuery = "", initialField = "all", initialMode = "keyword" }: Props) {
  const navigate = useNavigate();
  const [q, setQ] = useState(initialQuery);
  const [field, setField] = useState<SearchField>(initialField);
  const [mode, setMode] = useState<SearchMode>(initialMode);
  const [suggestions, setSuggestions] = useState<{text: string; field: string}[]>([]);
  const {capabilities, error: capabilityError} = useSearchCapabilities();
  const [focused, setFocused] = useState(false);
  const [recent, setRecent] = useState<string[]>(() => readLocal<string[]>("recent-queries", []));

  useEffect(() => { setQ(initialQuery); }, [initialQuery]);
  useEffect(() => { setField(initialField); }, [initialField]);
  useEffect(() => { setMode(initialMode); }, [initialMode]);
  useEffect(() => {
    let active = true;
    setSuggestions([]);
    if (!focused || q.trim().length < 2) return;
    const timer = window.setTimeout(() => {
      getSuggestions(q.trim()).then(items => { if (active) setSuggestions(items); }).catch(() => { if (active) setSuggestions([]); });
    }, 220);
    return () => { active = false; window.clearTimeout(timer); };
  }, [q, focused]);
  const recentVisible = focused && q.trim().length === 0 && recent.length > 0;

  const submit = (term = q, suggestionField = field) => {
    const clean = term.trim();
    if (!clean) { document.getElementById("main-search-input")?.focus(); return; }
    setFocused(false);
    const next = [clean, ...recent.filter((item) => item.toLocaleLowerCase() !== clean.toLocaleLowerCase())].slice(0, 8);
    setRecent(next);
    writeLocal("recent-queries", next);
    const params = new URLSearchParams({ q: clean, field: suggestionField, mode, page: "1" });
    navigate("/search?" + params.toString());
  };

  const clearRecent = () => {
    setRecent([]);
    writeLocal("recent-queries", [] as string[]);
  };

  return (
    <div className={"search-module search-module-" + variant}>
      <form className="search-form" onSubmit={(event) => { event.preventDefault(); submit(); }} role="search">
        <div className="field-select-wrap">
          <select value={field} onChange={(event) => setField(event.target.value as SearchField)} aria-label="选择检索字段">
              {FIELD_OPTIONS.map((item) => <option key={item.value} value={item.value} disabled={mode === "semantic" && !["all","title","fulltext"].includes(item.value)}>
              {variant === "compact" ? item.short : item.label}
            </option>)}
          </select>
          <span className="field-caret" aria-hidden="true">⌄</span>
        </div>
        <div className="search-input-wrap">
          <Search size={20} strokeWidth={1.8} />
          <input id="main-search-input" value={q} onChange={(event) => setQ(event.target.value)}
            onFocus={() => setFocused(true)}
            onBlur={() => window.setTimeout(() => setFocused(false), 180)}
            placeholder="搜索论文、作者、机构或研究主题…" autoComplete="off" aria-label="论文关键词" />
          {(suggestions.length > 0 || recentVisible) && <div className="suggestion-popover" role="listbox" aria-label="搜索建议">
            {recentVisible ? <div className="suggestion-head">
              <span><Clock3 size={13}/> 最近搜索 · 仅保存在此浏览器</span>
              <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={clearRecent} aria-label="清空最近搜索">
                <Trash2 size={13}/> 清空
              </button>
            </div> : <span>{DATA_SOURCE === "demo" ? "本地示例论文标题建议" : "论文标题与作者建议"}</span>}
            {(recentVisible ? recent.map(text => ({text, field})) : suggestions).map((item) =>
              <button key={item.text} type="button" onMouseDown={(event) => event.preventDefault()} onClick={() => submit(item.text, (FIELD_OPTIONS.some(x => x.value === item.field) ? item.field : field) as SearchField)}>
                {item.text}<ArrowRight size={14}/>
              </button>)}
          </div>}
        </div>
        <button type="submit" className="search-submit">{variant === "hero" ? "开始检索" : "搜索"} <ArrowRight size={18}/></button>
      </form>
      <details className="search-options">
        <summary>{mode === "keyword" ? "关键词检索" : mode === "semantic" ? "语义检索" : "混合检索"} <ChevronDown size={14}/></summary>
        <div className="search-options-panel">
          <label>检索方式 <select aria-label="检索方式" value={mode} onChange={event => {
            const next = event.target.value as SearchMode;
            setMode(next);
            if (next === "semantic" && !["all","title","fulltext"].includes(field)) setField("all");
          }}>
            <option value="keyword">关键词检索</option>
            <option value="semantic" disabled={!capabilities?.semantic.ready}>语义检索{capabilities?.semantic.ready ? "" : " · 未就绪"}</option>
            <option value="hybrid" disabled={!capabilities?.hybrid.ready}>混合检索{capabilities?.hybrid.ready ? "" : " · 未就绪"}</option>
          </select></label>
          <p>{capabilityError || capabilities?.[mode].reason || "正在检查检索服务…"}</p>
          {!capabilities?.semantic.ready && <p>{capabilities?.semantic.reason || "语义与混合模式需本地模型和向量索引就绪。"}</p>}
        </div>
      </details>
    </div>
  );
}
