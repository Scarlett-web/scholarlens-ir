import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Bookmark, BookOpen, ChevronDown, Clock3, Download, FolderPlus, History, Import, Pencil, Search, StickyNote, Trash2, X } from "lucide-react";
import { useStudio } from "../App";
import {useAuth} from "../services/AuthContext";
import { PageHeading } from "../components/Layout";
import { PaperCard } from "../components/PaperCard";
import { downloadJson } from "../lib/storage";

type LibraryTab = "saved" | "history";
type SavedSort = "saved" | "year" | "title";

export function LibraryPage() {
  const {user}=useAuth();
  const {
    favorites, history, collections, addCollection, renameCollection, removeCollection,
    moveFavorite, updateFavoriteNote, clearHistory, removeHistory, restoreLibrary, notify, workspaceSyncing, workspaceError
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

  const importFile = async (file?: File) => {
    if (!file) return;
    if (file.size > 2 * 1024 * 1024) { notify("仅支持 2MB 以内的 JSON 阅读空间备份"); return; }
    if (!window.confirm("导入备份将替换当前浏览器中的收藏夹和历史记录，确定继续吗？")) {if(importInput.current)importInput.current.value="";return;}
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
    <PageHeading eyebrow="PERSONAL RESEARCH SPACE" title="我的文献" desc="整理收藏、分组与阅读笔记，接着上次的研究继续。"/>
    <p className="library-local-note"><BookOpen size={16}/> {user?"当前为账户阅读空间，收藏、分类与笔记保存到服务器。":"游客收藏与笔记保存在此浏览器，登录可使用独立的账户空间。"} 可随时导出备份。</p>
    <div className="library-toolbar">
      <div className="segmented">
        <button className={tab==="saved"?"selected":""} onClick={()=>{setTab("saved");setTerm("")}}><Bookmark size={16}/> 我的收藏 <span>{favorites.length}</span></button>
        <button className={tab==="history"?"selected":""} onClick={()=>{setTab("history");setTerm("")}}><History size={16}/> 浏览历史 <span>{history.length}</span></button>
      </div>
      <div className="library-actions">
        <button className="button button-secondary" onClick={()=>importInput.current?.click()}><Import size={16}/> 导入备份</button>
        <input ref={importInput} type="file" accept=".json,application/json" hidden
          onChange={(e)=>void importFile(e.target.files?.[0])}/>
        <button className="button button-secondary" onClick={() => downloadJson("scholarlens-library-backup.json", {
          version:1, exportedAt:new Date().toISOString(), favorites, history, collections
        })}><Download size={16}/> 导出 JSON</button>
      </div>
    </div>
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
      <aside className={"library-sidebar"+(foldersOpen?" library-folders-open":"")}>
        <button className="mobile-folder-toggle" type="button" aria-expanded={foldersOpen} aria-controls="library-folders" onClick={()=>setFoldersOpen((value)=>!value)}>
          <span>分类 · {folder === "全部" ? "所有文献" : folder === "全部收藏" ? "未分类" : folder}</span><ChevronDown size={16}/>
        </button>
        <div className="library-folder-content" id="library-folders">
        <div className="filter-heading"><span>我的分类</span><FolderPlus size={16}/></div>
        <div className="folder-list">
          <button className={folder==="全部"?"active":""} onClick={()=>{setFolder("全部");setFoldersOpen(false)}}>所有文献 <span>{favorites.length}</span></button>
          {collections.map((collection) => <div className="folder-row" key={collection}>
            {renaming===collection ? <form className="folder-rename" onSubmit={(e)=>{e.preventDefault();rename(collection)}}>
                <input autoFocus value={renameValue} maxLength={36} aria-label="重命名分类"
                  onChange={(e)=>setRenameValue(e.target.value)}/>
                <button type="submit" aria-label="保存新名称">保存</button>
                <button type="button" aria-label="取消" onClick={()=>setRenaming(null)}><X size={13}/></button>
              </form> : <>
                <button className={folder===collection?"active":""} onClick={()=>{setFolder(collection);setFoldersOpen(false)}}>
                  {collection === "全部收藏" ? "未分类" : collection}<span>{favorites.filter((entry)=>entry.collection===collection).length}</span>
                </button>
                {collection!=="全部收藏"&&<div className="folder-actions">
                  <button title="重命名分类" aria-label={"重命名"+collection}
                    onClick={()=>{setRenaming(collection);setRenameValue(collection)}}><Pencil size={13}/></button>
                  <button title="删除分类" aria-label={"删除"+collection} onClick={()=>{
                    if (window.confirm("删除分类“"+collection+"”？其中的论文会移入“全部收藏”。")) {
                      removeCollection(collection);if(folder===collection)setFolder("全部");
                    }
                  }}><X size={13}/></button>
                </div>}
              </>}
          </div>)}
        </div>
        <form className="create-folder" onSubmit={(e)=>{e.preventDefault();if(addCollection(newFolder))setNewFolder("")}}>
          <input value={newFolder} onChange={(e)=>setNewFolder(e.target.value)} maxLength={36}
            placeholder="新分类名称" aria-label="新分类名称"/>
          <button type="submit" title="创建分类" aria-label="创建分类"><FolderPlus size={18}/></button>
        </form>
        </div>
      </aside>
      <section className="library-main">
        <div className="results-topbar"><div><h2>{folder==="全部"?"全部收藏":folder==="全部收藏"?"未分类":folder}</h2>
          <p>共 {filtered.length} 篇论文 · 可添加私人阅读笔记</p></div></div>
        {filtered.length?<div className="paper-list">{filtered.map((entry) => <div className="library-paper-item" key={entry.paper.paper_id}>
          <PaperCard paper={entry.paper}/>
          <div className="saved-paper-controls">
            <Clock3 size={14}/> 收藏于 {new Date(entry.savedAt).toLocaleDateString("zh-CN")}
            <label>分类 <select value={entry.collection} onChange={(e)=>moveFavorite(entry.paper.paper_id,e.target.value)}>
              {collections.map((collection)=><option value={collection} key={collection}>{collection === "全部收藏" ? "未分类" : collection}</option>)}
            </select></label>
            <button className="note-edit-button" onClick={()=>setEditingNote(editingNote===entry.paper.paper_id?null:entry.paper.paper_id)}>
              <StickyNote size={15}/>{entry.note?"查看 / 修改笔记":"添加笔记"}
            </button>
          </div>
          {editingNote===entry.paper.paper_id && <div className="reading-note">
            <label>我的阅读笔记
              <textarea rows={3} maxLength={2000} value={entry.note??""}
                placeholder="记录研究要点、疑问、后续阅读计划…"
                onChange={(e)=>updateFavoriteNote(entry.paper.paper_id,e.target.value)}/>
            </label><p role="status">{user?(workspaceError?"保存失败，草稿已留在本机，请检查账户连接":workspaceSyncing?"正在保存到账户…":"笔记已保存到账户"):"笔记自动保存在此浏览器"} · {entry.note?.length??0}/2000 字</p>
          </div>}
        </div>)}</div>:<div className="empty-state library-empty">
          <span className="library-empty-icon"><Bookmark size={24} strokeWidth={1.7}/></span>
          <h3>{term?"没有找到匹配的文献":favorites.length?"这个分类还没有论文":"还没有收藏论文"}</h3>
          <p>{term?"试试更短的关键词，或清除当前筛选。":favorites.length?"在全部收藏中选择论文，将它移入这个分类。":"在检索结果中收藏论文，即可在这里分类和记录笔记。"}</p>
          <div className="library-empty-actions">
            {term?<button type="button" className="button button-primary" onClick={()=>setTerm("")}>清空搜索条件</button>
              :favorites.length?<button className="button button-primary" onClick={()=>setFolder("全部")}>查看全部收藏</button>:<Link to="/search" className="button button-primary">检索论文</Link>}
            <Link to="/explore" className="button button-secondary">探索研究主题</Link>
          </div>
        </div>}
      </section>
    </div>:<section className="history-panel">
      <div className="results-topbar"><div><h2>最近浏览</h2><p>自动记录最近 50 篇不同论文，不包含 PDF 文件。</p></div>
        <button disabled={!history.length} className="button button-secondary" onClick={()=>{
          if (window.confirm(user?"确定清空当前账户的浏览记录？":"确定清空此浏览器的浏览记录？")) clearHistory();
        }}><Trash2 size={16}/> 清空历史</button></div>
      {filteredHistory.length?filteredHistory.map((entry)=><div className="history-row" key={entry.paper.paper_id}>
        <Link to={"/paper/"+encodeURIComponent(entry.paper.paper_id)}><BookOpen size={18}/><span>{entry.paper.title}</span></Link>
        <span>{new Date(entry.viewedAt).toLocaleString("zh-CN")}</span>
        <button aria-label={"删除"+entry.paper.title} title="移除这条历史记录" onClick={()=>removeHistory(entry.paper.paper_id)}><X size={16}/></button>
      </div>):<div className="empty-state">{term?"没有匹配的浏览记录":"打开论文详情后，这里会记录你的阅读历史。"}</div>}
    </section>}
  </div>;
}
