import { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { BrowserRouter, Route, Routes, useLocation } from "react-router-dom";
import type { HistoryEntry, LibraryEntry, LocalUpload, Paper } from "./types";
import { readLocal, writeLocal } from "./lib/storage";
import { deleteLocalPdf, saveLocalPdf, verifyPdf } from "./lib/pdfStore";
import { normalizePaper } from "./services/papers";
import { SiteLayout } from "./components/Layout";
import { HomePage } from "./pages/HomePage";
import { SearchPage } from "./pages/SearchPage";
import { PaperPage } from "./pages/PaperPage";
import { ExplorePage } from "./pages/ExplorePage";
import { LibraryPage } from "./pages/LibraryPage";
import { AssistantPage } from "./pages/AssistantPage";
import { EvaluationPage } from "./pages/EvaluationPage";
import { UploadPage } from "./pages/UploadPage";
import { AdminPage } from "./pages/AdminPage";
import { AuthProvider, useAuth } from "./services/AuthContext";
import { accountApi, sessionToken } from "./services/backend";
import { AccountPage } from "./pages/AccountPage";
import { NotFoundPage } from "./pages/NotFoundPage";

interface StudioContextValue {
  workspaceReady: boolean;
  workspaceError: string;
  workspaceSyncing: boolean;
  favorites: LibraryEntry[];
  history: HistoryEntry[];
  collections: string[];
  uploads: LocalUpload[];
  presentation: boolean;
  motionPaused: boolean;
  reducedMotion: boolean;
  setMotionPaused(value: boolean): void;
  toast: string | null;
  notify(message: string): void;
  toggleFavorite(paper: Paper): void;
  isFavorite(id: string): boolean;
  moveFavorite(id: string, collection: string): void;
  updateFavoriteNote(id: string, note: string): void;
  addCollection(name: string): boolean;
  renameCollection(previous: string, next: string): boolean;
  removeCollection(name: string): void;
  restoreLibrary(input: unknown): { favorites: number; history: number };
  recordView(paper: Paper): void;
  clearHistory(): void;
  removeHistory(id: string): void;
  addUpload(file: File): Promise<void>;
  updateUpload(id: string, status: LocalUpload["status"], reason?: string): void;
  saveUploadNote(id: string, note: string): void;
  removeUpload(id: string): Promise<void>;
  setPresentation(value: boolean): void;
}

const StudioContext = createContext<StudioContextValue | undefined>(undefined);
export function useStudio(): StudioContextValue {
  const context = useContext(StudioContext);
  if (!context) throw new Error("useStudio requires StudioProvider");
  return context;
}

function paperSnapshot(paper: Paper): Paper {
  return {
    ...paper,
    abstract: String(paper.abstract || "").slice(0, 1800),
    fulltext: "",
    highlight: undefined,
    score: undefined
  };
}

function restoreSnapshot(value: unknown): {
  favorites: LibraryEntry[]; history: HistoryEntry[]; collections: string[];
} {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("文件不是有效的阅读空间备份");
  const raw = value as Record<string, unknown>;
  if (!Array.isArray(raw.favorites) || !Array.isArray(raw.history) || !Array.isArray(raw.collections)) {
    throw new Error("备份缺少 favorites、history 或 collections");
  }
  if (raw.favorites.length > 1000 || raw.history.length > 1000 || raw.collections.length > 100) {
    throw new Error("文件内容超过可导入上限，请检查来源");
  }
  const collections = [...new Set(["全部收藏", ...raw.collections.filter((name): name is string =>
    typeof name === "string" && name.trim().length > 0 && name.length <= 36)])];
  const seenFavorite = new Set<string>();
  const favorites: LibraryEntry[] = [];
  for (const candidate of raw.favorites) {
    if (!candidate || typeof candidate !== "object") continue;
    const value = candidate as Record<string, unknown>;
    const paper = normalizePaper(value.paper);
    if (!paper.paper_id || paper.paper_id.length > 128 || seenFavorite.has(paper.paper_id)) continue;
    seenFavorite.add(paper.paper_id);
    const collection = typeof value.collection === "string" && collections.includes(value.collection)
      ? value.collection : "全部收藏";
    favorites.push({
      paper: paperSnapshot(paper), collection, savedAt: typeof value.savedAt === "string" ? value.savedAt : new Date().toISOString(),
      note: typeof value.note === "string" ? value.note.slice(0, 2000) : ""
    });
  }
  const seenHistory = new Set<string>();
  const history: HistoryEntry[] = [];
  for (const candidate of raw.history) {
    if (!candidate || typeof candidate !== "object") continue;
    const value = candidate as Record<string, unknown>;
    const paper = normalizePaper(value.paper);
    if (!paper.paper_id || paper.paper_id.length > 128 || seenHistory.has(paper.paper_id)) continue;
    seenHistory.add(paper.paper_id);
    history.push({ paper: paperSnapshot(paper), viewedAt: typeof value.viewedAt === "string" ? value.viewedAt : new Date().toISOString() });
    if (history.length >= 50) break;
  }
  return { favorites, history, collections };
}

function StudioProvider({ children }: { children: ReactNode }) {
  const {user}=useAuth();
  const [workspaceReady,setWorkspaceReady]=useState(!user);
  const [workspaceError,setWorkspaceError]=useState("");
  const [workspaceSyncing,setWorkspaceSyncing]=useState(false);
  const version=useRef(0),dirty=useRef(false),alive=useRef(true),failed=useRef(false);
  const token=useRef(sessionToken());
  const queue=useRef(Promise.resolve());
  const pendingSaves=useRef(0);
  const [favorites, setFavorites] = useState<LibraryEntry[]>(() => {
    const entries = user ? [] : readLocal<LibraryEntry[]>("favorites", []);
    return Array.isArray(entries) ? entries.filter((e) => e?.paper?.paper_id).map((e) => ({...e,paper:paperSnapshot(e.paper)})) : [];
  });
  const [history, setHistory] = useState<HistoryEntry[]>(() => {
    const entries = user ? [] : readLocal<HistoryEntry[]>("history", []);
    return Array.isArray(entries) ? entries.filter((e) => e?.paper?.paper_id).map((e) => ({...e,paper:paperSnapshot(e.paper)})) : [];
  });
  const [collections, setCollections] = useState<string[]>(() => user ? ["全部收藏", "待读", "重点阅读"] : readLocal("collections", ["全部收藏", "待读", "重点阅读"]));
  const [uploads, setUploads] = useState<LocalUpload[]>(() => readLocal("uploads", []));
  const [presentation, setPresentation] = useState<boolean>(() => readLocal("presentation", false));
  const [motionPaused, setMotionPaused] = useState<boolean>(() => readLocal<boolean>("motion-paused", false) === true);
  const [reducedMotion, setReducedMotion] = useState(() => window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => { if (!user && !writeLocal("favorites", favorites)) setToast("收藏保存失败：浏览器本地空间可能不足。请及时导出 JSON 备份。"); }, [favorites,user]);
  useEffect(() => { if (!user && !writeLocal("history", history)) setToast("历史记录保存失败：请检查浏览器存储权限。"); }, [history,user]);
  useEffect(() => { if (!user && !writeLocal("collections", collections)) setToast("收藏分类保存失败，请检查浏览器存储容量。"); }, [collections,user]);
  useEffect(() => { if (!writeLocal("uploads", uploads)) setToast("PDF 文件记录保存失败，请导出或清理本地数据。"); }, [uploads]);
  useEffect(() => { writeLocal("presentation", presentation); }, [presentation]);
  useEffect(() => { writeLocal("motion-paused", motionPaused); }, [motionPaused]);
  useEffect(()=>{
    alive.current=true;
    let active=true;
    if(user)accountApi.workspace(token.current).then(data=>{
      if(!active)return;
      version.current=data.version;
      setFavorites(data.favorites.map(entry=>({...entry,paper:normalizePaper(entry.paper)})));
      setHistory(data.history.map(entry=>({...entry,paper:normalizePaper(entry.paper)})));
      setCollections(data.collections);setWorkspaceReady(true);
    }).catch(cause=>{if(active)setWorkspaceError(cause instanceof Error?cause.message:"账户阅读空间加载失败");});
    return()=>{active=false;alive.current=false;};
  },[user]);
  useEffect(()=>{
    if(!user||!workspaceReady||!dirty.current||failed.current)return;
    writeLocal("account-"+user.id+"-recovery",{favorites,history,collections,version:version.current});
    setWorkspaceSyncing(true);
    const timer=window.setTimeout(()=>{
      dirty.current=false;
      const data={favorites,history,collections,version:version.current};
      writeLocal("account-"+user.id+"-recovery",data);
      setWorkspaceSyncing(true);
      pendingSaves.current+=1;
      queue.current=queue.current.then(async()=>{
        if(!alive.current||failed.current)return;
        const result=await accountApi.saveWorkspace({...data,version:version.current},token.current);
        version.current=result.version;
      }).catch(cause=>{
        failed.current=true;
        if(alive.current)setWorkspaceError(cause instanceof Error?cause.message:"账户同步失败");
      }).finally(()=>{pendingSaves.current-=1;if(alive.current&&!dirty.current&&pendingSaves.current===0)setWorkspaceSyncing(false);});
    },500);
    return()=>window.clearTimeout(timer);
  },[user,workspaceReady,favorites,history,collections]);
  useEffect(()=>{
    if(!user||!workspaceSyncing)return;
    const guard=(event:BeforeUnloadEvent)=>{event.preventDefault();event.returnValue="";};
    window.addEventListener("beforeunload",guard);return()=>window.removeEventListener("beforeunload",guard);
  },[user,workspaceSyncing]);
  const editWorkspace=()=>{
    if(user&&(!workspaceReady||failed.current)){setToast(workspaceError||"账户阅读空间正在加载，请稍候");return false;}
    dirty.current=true;return true;
  };
  useEffect(() => {
    const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
    const sync = () => setReducedMotion(preference.matches);
    sync();
    preference.addEventListener("change", sync);
    return () => preference.removeEventListener("change", sync);
  }, []);
  useEffect(() => {
    if(user)return;
    const syncHistory = (event: StorageEvent) => {
      if (event.storageArea !== window.localStorage || event.key !== "scholarlens-v1:history") return;
      try {
        const raw: unknown = JSON.parse(event.newValue ?? "[]");
        if (!Array.isArray(raw)) return;
        const next: HistoryEntry[] = raw.filter(entry => entry?.paper?.paper_id)
          .slice(0, 50).map(entry => ({ ...entry, paper: paperSnapshot(entry.paper) }));
        setHistory(current => JSON.stringify(current) === JSON.stringify(next) ? current : next);
      } catch { /* Ignore malformed external data; keep the current reading history. */ }
    };
    window.addEventListener("storage", syncHistory);
    return () => window.removeEventListener("storage", syncHistory);
  }, []);
  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 3400);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const value = useMemo<StudioContextValue>(() => ({
    workspaceReady,workspaceError,workspaceSyncing, favorites, history, collections, uploads, presentation, motionPaused, reducedMotion, setMotionPaused, toast,
    notify: (message) => setToast(message),
    isFavorite: (id) => favorites.some((entry) => entry.paper.paper_id === id),
    toggleFavorite: (paper) => {
      if(user&&paper.paper_id.startsWith("demo-")){setToast("虚构演示论文仅保留在游客空间，不上传到真实账户");return;}
      if(!editWorkspace())return;
      const exists = favorites.some((item) => item.paper.paper_id === paper.paper_id);
      setFavorites((old) => exists ? old.filter((item) => item.paper.paper_id !== paper.paper_id) : [{
        paper: paperSnapshot(paper), collection: "全部收藏", savedAt: new Date().toISOString(), note: ""
      }, ...old]);
      setToast(exists ? "已取消收藏" : "已加入收藏，可在我的空间添加笔记和分类");
    },
    moveFavorite: (id, collection) => {
      if(!editWorkspace())return;
      if (!collections.includes(collection)) return;
      setFavorites((old) => old.map((entry) => entry.paper.paper_id === id ? { ...entry, collection } : entry));
      setToast("已更新收藏分类");
    },
    updateFavoriteNote: (id, note) => {
      if(!editWorkspace())return;
      setFavorites((old) => old.map((entry) => entry.paper.paper_id === id ? { ...entry, note: note.slice(0, 2000) } : entry));
    },
    addCollection: (name) => {
      if(!editWorkspace())return false;
      const clean = name.trim().slice(0, 36);
      if (!clean || collections.some((item) => item.toLocaleLowerCase() === clean.toLocaleLowerCase())) {
        setToast("分类名称为空或已经存在"); return false;
      }
      setCollections((old) => [...old, clean]); setToast("收藏分类已创建"); return true;
    },
    renameCollection: (previous, next) => {
      if(!editWorkspace())return false;
      const clean = next.trim().slice(0, 36);
      if (previous === "全部收藏" || !clean || collections.some((item) =>
        item !== previous && item.toLocaleLowerCase() === clean.toLocaleLowerCase())) {
        setToast("无法重命名：名称无效或重复"); return false;
      }
      setCollections((old) => old.map((item) => item === previous ? clean : item));
      setFavorites((old) => old.map((entry) => entry.collection === previous ? { ...entry, collection: clean } : entry));
      setToast("收藏分类已重命名"); return true;
    },
    removeCollection: (name) => {
      if(!editWorkspace())return;
      if (name === "全部收藏") return;
      setCollections((old) => old.filter((item) => item !== name));
      setFavorites((old) => old.map((entry) => entry.collection === name ? { ...entry, collection: "全部收藏" } : entry));
      setToast("分类已删除，论文已移入“全部收藏”");
    },
    restoreLibrary: (input) => {
      if(!editWorkspace())throw new Error("账户空间尚不可编辑");
      const snapshot = restoreSnapshot(input);
      if(user&&[...snapshot.favorites,...snapshot.history].some(entry=>entry.paper.paper_id.startsWith("demo-")))throw new Error("此备份包含虚构演示论文，请在游客空间导入。");
      setFavorites(snapshot.favorites); setHistory(snapshot.history); setCollections(snapshot.collections);
      setToast("已从 JSON 备份恢复收藏与历史记录");
      return { favorites: snapshot.favorites.length, history: snapshot.history.length };
    },
    recordView: (paper) => {
      if(user&&paper.paper_id.startsWith("demo-"))return;
      if(!editWorkspace())return;
      setHistory((old) => [{
      paper: paperSnapshot(paper), viewedAt: new Date().toISOString()
    }, ...old.filter((item) => item.paper.paper_id !== paper.paper_id)].slice(0, 50));},
    clearHistory: () => { if(!editWorkspace())return; setHistory([]); setToast(user?"账户浏览记录已清空":"本地浏览记录已清空"); },
    removeHistory: (id) => {if(editWorkspace())setHistory((old) => old.filter((entry) => entry.paper.paper_id !== id));},
    addUpload: async (file) => {
      const { hash } = await verifyPdf(file);
      if (uploads.some((item) => item.sha256 === hash)) throw new Error("相同内容的 PDF 已在本地队列中");
      const id = "local-" + (typeof crypto.randomUUID === "function" ? crypto.randomUUID() : Date.now().toString(36));
      await saveLocalPdf(id, file);
      setUploads((old) => [{
        id, name: file.name, size: file.size, submittedAt: new Date().toISOString(), status: "pending",
        sha256: hash, reviewNote: ""
      }, ...old]);
      setToast("PDF 已保存在当前浏览器，可在管理审核页预览");
    },
    updateUpload: (id, status, reason) => {
      setUploads((old) => old.map((item) => item.id === id ?
        { ...item, status, reviewedAt: new Date().toISOString(), reviewNote: reason?.slice(0, 500) ?? item.reviewNote } : item));
      setToast("已保存本地审核结果，正式索引未发生任何变化");
    },
    saveUploadNote: (id, note) => {
      setUploads((old)=>old.map((item)=>item.id===id?{...item,reviewNote:note.slice(0,500)}:item));
      setToast("审核备注已保存到此浏览器");
    },
    removeUpload: async (id) => {
      await deleteLocalPdf(id);
      setUploads((old) => old.filter((item) => item.id !== id));
      setToast("本地文件和审核记录已删除");
    },
    setPresentation
  }), [favorites, history, collections, uploads, presentation, motionPaused, reducedMotion, toast, user, workspaceReady,workspaceError,workspaceSyncing]);

  return <StudioContext.Provider value={value}>{children}</StudioContext.Provider>;
}

function ScrollReset() {
  const { pathname } = useLocation();
  useEffect(() => { window.scrollTo({ top: 0, behavior: "instant" }); }, [pathname]);
  return null;
}

function AppRoutes() {
  const { presentation } = useStudio();
  return <div className={presentation ? "site-root presentation-mode" : "site-root"}>
    <ScrollReset />
    <SiteLayout><Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/search" element={<SearchPage />} />
      <Route path="/paper/:paperId" element={<PaperPage />} />
      <Route path="/explore" element={<ExplorePage />} />
      <Route path="/library" element={<LibraryPage />} />
      <Route path="/account" element={<AccountPage />} />
      <Route path="/assistant" element={<AssistantPage />} />
      <Route path="/evaluation" element={<EvaluationPage />} />
      <Route path="/upload" element={<UploadPage />} />
      <Route path="/admin" element={<AdminPage />} />
      <Route path="*" element={<NotFoundPage />} />
    </Routes></SiteLayout>
  </div>;
}

function SessionWorkspace(){
  const {user,loading}=useAuth();
  if(loading)return <div className="empty-state">正在核验登录状态…</div>;
  return <StudioProvider key={user?.id??"guest"}><AppRoutes/></StudioProvider>;
}
export default function App() {
  return <BrowserRouter><AuthProvider><SessionWorkspace/></AuthProvider></BrowserRouter>;
}
