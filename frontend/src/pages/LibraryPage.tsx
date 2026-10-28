import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Bookmark, BookOpen, ChevronDown, Clock3, Download, FolderPlus, History, Import, Pencil, Search, StickyNote, Trash2, X } from "lucide-react";
import { useStudio } from "../App";
import {useAuth} from "../services/AuthContext";
import { PageHeading } from "../components/Layout";
import { PaperCard } from "../components/PaperCard";
import { ReadingPositionHint } from "../components/ReadingPositionHint";
import { downloadJson } from "../lib/storage";

type LibraryTab = "saved" | "history";
type SavedSort = "saved" | "year" | "title";

export function LibraryPage() {
  const {user}=useAuth();
  const {
    favorites, history, collections, addCollection, renameCollection, removeCollection,
    moveFavorite, updateFavoriteNote, clearHistory, removeHistory, restoreLibrary, notify,
    workspaceReady, workspaceSyncing, workspaceError, retryWorkspaceRead
  } = useStudio();
  const [tab, setTab] = useState<LibraryTab>("saved");
  const [folder, setFolder] = useState("全部");
  const [newFolder, setNewFolder] = useState("");
  const [renaming, setRenaming] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [term, setTerm] = useState("");
  const [sort, setSort] = useState<SavedSort>("saved");
  const [editingNote, setEditingNote] = useState<string | null>(null);
  const [foldersOpen, setFoldersOpen] = useState(false);
  const importInput = useRef<HTMLInputElement>(null);
  const editable = workspaceReady && !workspaceError;
  const latest = history[0];

  const filtered = favorites.filter((entry) => {
    const paper = entry.paper;
    const content = [paper.title, paper.authors.join(" "), paper.keywords.join(" "), entry.note || ""]
      .join(" ").toLocaleLowerCase();
    return (folder === "全部" || entry.collection === folder) && content.includes(term.trim().toLocaleLowerCase());
  }).sort((a,b) => {
    if (sort === "title") return a.paper.title.localeCompare(b.paper.title);
    if (sort === "year") return (b.paper.year ?? 0) - (a.paper.year ?? 0);
    return new Date(b.savedAt).getTime() - new Date(a.savedAt).getTime();
  });
  const filteredHistory = history.filter((entry) => [entry.paper.title, entry.paper.authors.join(" ")]
    .join(" ").toLocaleLowerCase().includes(term.toLocaleLowerCase().trim()));
  const collectionName = (name: string) => name === "全部收藏" ? "未分类" : name;

  const importFile = async (file?: File) => {
    if (!file) return;
    if (file.size > 2 * 1024 * 1024) { notify("仅支持 2MB 以内的 JSON 阅读空间备份"); return; }
    const message = user
      ? "导入备份将替换当前账户的收藏、分类和浏览记录，并同步到服务器。建议先导出当前备份，确定继续吗？"
      : "导入备份将替换当前浏览器中的收藏、分类和浏览记录，确定继续吗？";
    if (!window.confirm(message)) {if(importInput.current)importInput.current.value="";return;}
    try {
      const json = JSON.parse(await file.text()) as unknown;
      const summary = restoreLibrary(json);
      setFolder("全部"); setTerm("");
      notify("已恢复 " + summary.favorites + " 篇收藏和 " + summary.history + " 条历史记录");
    } catch (error) {
      notify(error instanceof Error ? error.message : "JSON 备份读取失败");
    } finally {
      if (importInput.current) importInput.current.value = "";
    }
  };

  const rename = (previous:string) => {
    const next = renameValue.trim();
    if (renameCollection(previous,next)) {
      if (folder === previous) setFolder(next);
      setRenaming(null); setRenameValue("");
    }
  };

  return <div className="workspace-page content-wrap library-page">
    <PageHeading eyebrow="PERSONAL RESEARCH SPACE" title="我的文献" desc="整理收藏与笔记，接着上次的位置阅读。"/>
    <p className="library-local-note"><BookOpen size={16}/> {user?"账户空间 · 收藏、分类与笔记保存到服务器，阅读位置保留在本机。":"游客空间 · 收藏、笔记与阅读位置保留在此浏览器。"} 可导出备份。</p>
    <div className="library-toolbar">
      <div className="segmented" aria-label="文献视图">
        <button aria-pressed={tab==="saved"} className={tab==="saved"?"selected":""} onClick={()=>{setTab("saved");setTerm("")}}><Bookmark size={16}/> 我的收藏 <span>{workspaceReady?favorites.length:"—"}</span></button>
        <button aria-pressed={tab==="history"} className={tab==="history"?"selected":""} onClick={()=>{setTab("history");setTerm("")}}><History size={16}/> 浏览历史 <span>{workspaceReady?history.length:"—"}</span></button>
      </div>
      <div className="library-actions">
        <button disabled={!editable} className="button button-secondary" onClick={()=>importInput.current?.click()}><Import size={16}/> 导入备份</button>
        <input ref={importInput} type="file" accept=".json,application/json" hidden
          onChange={(e)=>void importFile(e.target.files?.[0])}/>
        <button disabled={!workspaceReady} className="button button-secondary" onClick={() => downloadJson("scholarlens-library-backup.json", {
          version:1, exportedAt:new Date().toISOString(), favorites, history, collections
        })}><Download size={16}/> 导出 JSON</button>
      </div>
    </div>
    {!workspaceReady?<section className="library-read-state" aria-busy={!workspaceError}>
      {workspaceError?<><h2>账户文献未能读取</h2><p role="alert">{workspaceError}</p><p>现有文献不会被空列表替换。检查连接后，可以重新读取。</p><button className="button button-primary" type="button" onClick={retryWorkspaceRead}>重新读取账户文献</button></>
        :<><h2 role="status">正在读取账户文献…</h2><p>正在载入收藏、分类和浏览记录。</p><div className="library-loading-lines" aria-hidden="true"><span/><span/><span/></div></>}
    </section>:<>
    {user&&workspaceError&&<section className="library-sync-error" role="alert">
      <strong>账户同步未完成，当前页面仍保留文献和草稿。</strong><p>{workspaceError}</p><p>请先导出 JSON 备份。为保护未同步内容，暂时停止修改，不会重新读取并覆盖草稿。</p>
    </section>}
    {tab==="saved"&&latest&&<section className="library-resume" aria-label="接着上次阅读">
      <BookOpen size={24}/><div><span>上次打开</span><Link to={"/paper/"+encodeURIComponent(latest.paper.paper_id)}>{latest.paper.title}</Link></div>
      <ReadingPositionHint paperId={latest.paper.paper_id}/>
      <Link className="library-resume-open" to={"/paper/"+encodeURIComponent(latest.paper.paper_id)}>打开论文</Link>
    </section>}
    <div className="library-search-row">
      <label className="library-search"><Search size={17}/>
        <input value={term} onChange={(e)=>setTerm(e.target.value)}
          placeholder={tab==="saved"?"搜索论文标题、作者、关键词或笔记":"搜索浏览历史"}
          aria-label={tab==="saved"?"筛选收藏论文":"筛选历史记录"}/>
        {term&&<button aria-label="清空搜索" onClick={()=>setTerm("")}><X size={15}/></button>}
      </label>
      {tab==="saved"&&<label className="sort-select"><span>排序</span><select value={sort} onChange={e=>setSort(e.target.value as SavedSort)}>
        <option value="saved">最近收藏</option><option value="year">发表年份</option><option value="title">标题顺序</option>
      </select></label>}
    </div>
    {tab==="saved"?<div className="library-grid">
      <aside aria-label="文献分类" className={"library-sidebar"+(foldersOpen?" library-folders-open":"")}>
        <button className="mobile-folder-toggle" type="button" aria-expanded={foldersOpen} aria-controls="library-folders" onClick={()=>setFoldersOpen((value)=>!value)}>
          <span>分类 · {folder === "全部" ? "所有文献" : collectionName(folder)}</span><ChevronDown size={16}/>
        </button>
        <div className="library-folder-content" id="library-folders">
        <div className="filter-heading"><span>文献分类</span><FolderPlus size={16}/></div>
        <div className="folder-list">
          <button aria-label="查看分类：所有文献" aria-pressed={folder==="全部"} className={folder==="全部"?"active":""} onClick={()=>{setFolder("全部");setFoldersOpen(false)}}>所有文献 <span className="folder-count">{favorites.length}</span></button>
          {collections.map((collection) => <div className="folder-row" key={collection}>
            {renaming===collection ? <form className="folder-rename" onSubmit={(e)=>{e.preventDefault();rename(collection)}}>
                <input autoFocus value={renameValue} maxLength={36} aria-label="重命名分类" disabled={!editable}
                  onChange={(e)=>setRenameValue(e.target.value)}/>
                <button type="submit" aria-label="保存新名称" disabled={!editable}>保存</button>
                <button type="button" aria-label="取消" onClick={()=>setRenaming(null)}><X size={13}/></button>
              </form> : <>
                <button aria-label={"查看分类："+collectionName(collection)} aria-pressed={folder===collection} className={folder===collection?"active":""} onClick={()=>{setFolder(collection);setFoldersOpen(false)}}>
                  <span className="folder-name">{collectionName(collection)}</span><span className="folder-count">{favorites.filter((entry)=>entry.collection===collection).length}</span>
                </button>
                {collection!=="全部收藏"&&<div className="folder-actions">
                  <button title="重命名分类" aria-label={"重命名"+collection} disabled={!editable}
                    onClick={()=>{setRenaming(collection);setRenameValue(collection)}}><Pencil size={13}/></button>
                  <button title="删除分类" aria-label={"删除"+collection} disabled={!editable} onClick={()=>{
                    if (window.confirm("删除分类“"+collection+"”？其中的论文会移入“未分类”。")) {
                      removeCollection(collection);if(folder===collection)setFolder("全部");
                    }
                  }}><X size={13}/></button>
                </div>}
              </>}
          </div>)}
        </div>
        <form className="create-folder" onSubmit={(e)=>{e.preventDefault();if(addCollection(newFolder)){setFolder(newFolder.trim());setNewFolder("");setTerm("");}}}>
          <input value={newFolder} onChange={(e)=>setNewFolder(e.target.value)} maxLength={36} disabled={!editable}
            placeholder="新分类名称" aria-label="新分类名称"/>
          <button type="submit" title="创建分类" aria-label="创建分类" disabled={!editable}><FolderPlus size={18}/></button>
        </form>
        </div>
      </aside>
      <section className="library-main" aria-label="收藏论文">
        <div className="results-topbar"><div><h2>{folder==="全部"?"全部收藏":collectionName(folder)}</h2>
          <p>共 {filtered.length} 篇论文 · {filtered.filter(entry=>entry.note?.trim()).length} 篇有阅读笔记</p></div><span className="library-shelf-label">研究书架</span></div>
        {filtered.length?<div className="paper-list">{filtered.map((entry) => <div className={"library-paper-item"+(entry.note||editingNote===entry.paper.paper_id?" has-note":"")} key={entry.paper.paper_id}>
          <div className="library-paper-main">
          <PaperCard paper={entry.paper}/>
          <ReadingPositionHint paperId={entry.paper.paper_id}/>
          <div className="saved-paper-controls">
            <Clock3 size={14}/> 收藏于 {new Date(entry.savedAt).toLocaleDateString("zh-CN")}
            <label>分类 <select value={entry.collection} disabled={!editable} onChange={(e)=>moveFavorite(entry.paper.paper_id,e.target.value)}>
              {collections.map((collection)=><option value={collection} key={collection}>{collectionName(collection)}</option>)}
            </select></label>
            <button className="note-edit-button" disabled={!editable&&!entry.note} onClick={()=>setEditingNote(editingNote===entry.paper.paper_id?null:entry.paper.paper_id)}>
              <StickyNote size={15}/>{entry.note?(editable?"查看 / 修改笔记":"查看笔记"):"添加笔记"}
            </button>
          </div>
          </div>
          {(entry.note||editingNote===entry.paper.paper_id)&&<aside className="library-paper-note" aria-label={"阅读笔记："+entry.paper.title}>
          {editingNote!==entry.paper.paper_id?<button className="library-note-preview" type="button" onClick={()=>setEditingNote(entry.paper.paper_id)}>
            <StickyNote size={16}/><span><strong>阅读笔记</strong><span>{entry.note!.length>180?entry.note!.slice(0,180)+"…":entry.note}</span></span>
          </button>:<div className="reading-note">
            <label>我的阅读笔记
              <textarea rows={4} maxLength={2000} value={entry.note??""} readOnly={!editable}
                placeholder="记录研究要点、疑问、后续阅读计划…"
                onChange={(e)=>updateFavoriteNote(entry.paper.paper_id,e.target.value)}/>
            </label><p role="status">{user?(workspaceError?"保存失败，当前页面保留草稿，请先导出备份":workspaceSyncing?"正在保存到账户…":"笔记已保存到账户"):"笔记自动保存在此浏览器"} · {entry.note?.length??0}/2000 字</p>
          </div>}
          </aside>}
        </div>)}</div>:<div className="empty-state library-empty">
          <div className="library-empty-shelf" aria-hidden="true"><span/><span/><span/></div>
          <h3>{term?"没有找到匹配的文献":favorites.length?"这个分类还没有论文":"你的研究书架还是空的"}</h3>
          <p>{term?"试试更短的关键词，或清除当前筛选。":favorites.length?"在全部收藏中选择论文，将它移入这个分类。":"从一篇论文开始，留下第一条线索。收藏后可分组、摘录，并接着上次的位置阅读。"}</p>
          <div className="library-empty-actions">
            {term?<button type="button" className="button button-primary" onClick={()=>setTerm("")}>清空搜索条件</button>
              :favorites.length?<button className="button button-primary" onClick={()=>setFolder("全部")}>查看全部收藏</button>:<Link to="/search" className="button button-primary">检索论文</Link>}
            <Link to="/explore" className="button button-secondary">探索研究主题</Link>
          </div>
        </div>}
      </section>
    </div>:<section className="history-panel">
      <div className="results-topbar"><div><h2>最近浏览</h2><p>自动记录最近 50 篇不同论文，不包含 PDF 文件。</p></div>
        <button disabled={!history.length||!editable} className="button button-secondary" onClick={()=>{
          if (window.confirm(user?"确定清空当前账户的浏览记录？":"确定清空此浏览器的浏览记录？")) clearHistory();
        }}><Trash2 size={16}/> 清空历史</button></div>
      {filteredHistory.length?filteredHistory.map((entry)=><div className="history-row" key={entry.paper.paper_id}>
        <div className="history-reading-info"><Link to={"/paper/"+encodeURIComponent(entry.paper.paper_id)}><BookOpen size={18}/><span>{entry.paper.title}</span></Link>
          <ReadingPositionHint paperId={entry.paper.paper_id}/></div>
        <span>{new Date(entry.viewedAt).toLocaleString("zh-CN")}</span>
        <button disabled={!editable} aria-label={"删除"+entry.paper.title} title="移除这条历史记录" onClick={()=>removeHistory(entry.paper.paper_id)}><X size={16}/></button>
      </div>):<div className="empty-state">{term?"没有匹配的浏览记录":"打开论文详情后，这里会记录你的阅读历史。"}</div>}
    </section>}
    </>}
  </div>;
}
