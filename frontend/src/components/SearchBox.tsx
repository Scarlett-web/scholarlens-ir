import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, ChevronDown, Clock3, Search, Trash2 } from "lucide-react";
import { FIELD_OPTIONS } from "../types";
import type { SearchField, SearchMode } from "../types";
import { DATA_SOURCE, getSuggestions } from "../services/papers";
import { useSearchCapabilities } from "../services/useSearchCapabilities";
import { readLocal, writeLocal } from "../lib/storage";
import { normalizeSearchField } from "../lib/searchParams";

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
  const [dismissed, setDismissed] = useState(false);
  const [activeSuggestion, setActiveSuggestion] = useState(-1);
  const [recent, setRecent] = useState<string[]>(() => {
    const stored = readLocal<unknown>("recent-queries", []);
    return Array.isArray(stored) ? stored.filter((item): item is string => typeof item === "string").slice(0,8) : [];
  });

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
  const choices = recentVisible ? recent.map(text => ({text, field})) : suggestions;
  const showChoices = focused && !dismissed && choices.length > 0;
  useEffect(() => { setActiveSuggestion(-1); }, [q, suggestions]);

  const submit = (term = q, suggestionField = field) => {
    const clean = term.trim();
    if (!clean) { document.getElementById("main-search-input")?.focus(); return; }
    setFocused(false);
    const next = [clean, ...recent.filter((item) => item.toLocaleLowerCase() !== clean.toLocaleLowerCase())].slice(0, 8);
    setRecent(next);
    writeLocal("recent-queries", next);
    const params = new URLSearchParams({ q: clean, field: normalizeSearchField(suggestionField, mode), mode, page: "1" });
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
        <div className="search-input-wrap" onBlur={event => {
          if (!event.currentTarget.contains(event.relatedTarget)) setFocused(false);
        }}>
          <Search size={20} strokeWidth={1.8} />
          <input id="main-search-input" value={q} onChange={(event) => {setQ(event.target.value);setDismissed(false);}}
            onFocus={() => {setFocused(true);setDismissed(false);setActiveSuggestion(-1);}}
            role="combobox" aria-autocomplete="list" aria-expanded={showChoices}
            aria-controls={showChoices ? "main-search-suggestions" : undefined}
            aria-activedescendant={showChoices && activeSuggestion >= 0 ? "search-choice-" + activeSuggestion : undefined}
            onKeyDown={event => {
              if (event.nativeEvent.isComposing) return;
              if (event.key === "Escape") { event.preventDefault(); setDismissed(true); setActiveSuggestion(-1); return; }
              if ((event.key === "ArrowDown" || event.key === "ArrowUp") && choices.length) {
                event.preventDefault(); setFocused(true); setDismissed(false);
                const next = event.key === "ArrowDown" ? (activeSuggestion + 1) % choices.length : (activeSuggestion <= 0 ? choices.length - 1 : activeSuggestion - 1);
                setActiveSuggestion(next);
                document.getElementById("search-choice-" + next)?.scrollIntoView({block:"nearest"});
              } else if (event.key === "Enter" && showChoices && activeSuggestion >= 0) {
                event.preventDefault(); const choice = choices[activeSuggestion];
                if (choice) submit(choice.text, normalizeSearchField(choice.field, mode));
              }
            }}
            placeholder="搜索论文、作者、机构或研究主题…" autoComplete="off" aria-label="论文关键词" />
          {showChoices && <div className="suggestion-popover">
            {recentVisible ? <div className="suggestion-head">
              <span><Clock3 size={13}/> 最近搜索 · 仅保存在此浏览器</span>
              <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={clearRecent} aria-label="清空最近搜索">
                <Trash2 size={13}/> 清空
              </button>
            </div> : <span>{DATA_SOURCE === "demo" ? "本地示例论文标题建议" : "论文标题与作者建议"}</span>}
            <div id="main-search-suggestions" role="listbox" aria-label="搜索建议">
              {choices.map((item,index) => <button key={item.field+":"+item.text} id={"search-choice-"+index} type="button" role="option" tabIndex={-1}
                aria-selected={index===activeSuggestion} onMouseDown={event=>event.preventDefault()}
                onClick={()=>submit(item.text, normalizeSearchField(item.field,mode))}>
                {item.text}<ArrowRight size={14}/>
              </button>)}
            </div>
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
