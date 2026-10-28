import {useEffect, useMemo, useRef, useState} from "react";
import {Link} from "react-router-dom";
import {AlertCircle, ArrowRight, CheckCircle2, FileText, FolderOpen, LockKeyhole, RefreshCw, Search, UploadCloud, X} from "lucide-react";
import {uploadApi} from "../services/backend";
import type {ServerUpload, User} from "../services/backend";
import {canProcessUpload, uploadReason, uploadWorkflow} from "../lib/uploadWorkflow";
import {PageHeading} from "./Layout";
import {UploadTimeline} from "./UploadTimeline";

type QueueFilter = "all" | "pending" | "processing" | "indexed" | "attention";
const filters: {value: QueueFilter; label: string}[] = [
  {value:"all",label:"全部"},{value:"pending",label:"待审核"},{value:"processing",label:"待处理 / 处理中"},
  {value:"indexed",label:"可检索"},{value:"attention",label:"需关注"},
];
function matches(row: ServerUpload, filter: QueueFilter) {
  if (filter === "all") return true;
  if (filter === "processing") return row.status === "approved" || row.status === "processing";
  if (filter === "attention") return ["failed","dependency_unavailable","rejected"].includes(row.status) || !uploadWorkflow(row.status).known;
  return row.status === filter;
}

export function UploadWorkflowDesk({admin, user, authLoading}: {admin: boolean; user: User | null; authLoading: boolean}) {
  const allowed = Boolean(user && (!admin || user.role === "admin"));
  const [rows,setRows] = useState<ServerUpload[]>([]), [page,setPage] = useState(1), [total,setTotal] = useState<number | null>(null);
  const [loading,setLoading] = useState(allowed), [loadError,setLoadError] = useState(""), [error,setError] = useState("");
  const [busy,setBusy] = useState(""), [message,setMessage] = useState(""), [revision,setRevision] = useState(0);
  const [selected,setSelected] = useState<File | null>(null), [dragging,setDragging] = useState(false);
  const [filter,setFilter] = useState<QueueFilter>("all"), [term,setTerm] = useState("");
  const [notes,setNotes] = useState<Record<string,string>>({}), [lastSync,setLastSync] = useState("");
  const [preview,setPreview] = useState<{url:string;name:string} | null>(null);
  const [dataContext,setDataContext] = useState("");
  const [loadErrorContext,setLoadErrorContext] = useState("");
  const input = useRef<HTMLInputElement>(null), alive = useRef(true), actionLock = useRef(false);
  const requestToken = useRef(0), queueSnapshot = useRef({context:"",hasData:false});
  const previewPanel = useRef<HTMLElement>(null), previewTrigger = useRef<HTMLButtonElement | null>(null);
  const contextKey = [user?.id ?? "guest",user?.role ?? "guest",admin ? "admin" : "account",page,filter].join(":");
  const contextKeyRef = useRef(contextKey);
  contextKeyRef.current = contextKey;
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  useEffect(() => () => {if (preview) URL.revokeObjectURL(preview.url);}, [preview]);
  useEffect(() => {if(preview){previewPanel.current?.scrollIntoView({block:"start",behavior:"auto"});previewPanel.current?.querySelector("button")?.focus({preventScroll:true});}},[preview]);
  useEffect(() => {
    const token = ++requestToken.current;
    const sameContext = queueSnapshot.current.context === contextKey;
    if (!sameContext) {
      setSelected(null); setDragging(false);
    }
    const preserveSnapshot = allowed && sameContext && queueSnapshot.current.hasData;
    queueSnapshot.current = {context: contextKey, hasData: preserveSnapshot};
    if (!allowed) {
      setRows([]); setTotal(null); setDataContext(""); setLoadError(""); setLoadErrorContext("");
      setLoading(false); setLastSync(""); setNotes({}); setPreview(null);
      return;
    }
    if (!preserveSnapshot) {
      setRows([]); setTotal(null); setDataContext(""); setLoadError(""); setLoadErrorContext("");
      setLastSync(""); setNotes({}); setPreview(null); setError(""); setMessage("");
    } else {
      setLoadError(""); setLoadErrorContext("");
    }
    let active = true, timer: number | undefined;
    const controller = new AbortController();
    setLoading(true); setLoadError("");
    if (preserveSnapshot) {
      setDataContext(contextKey);
    }
    const current = () => active && token === requestToken.current;
    const schedule = () => {timer = window.setTimeout(() => {if(!current())return;if(document.visibilityState === "visible") void load(); else schedule();},8000);};
    const load = async () => {
      if (!current()) return;
      try {
        const data = await uploadApi.list(admin,page,controller.signal);
        if (current()) {
          setRows(data.results); setTotal(data.total); setDataContext(contextKey); setLoadError(""); setLoadErrorContext("");
          setLastSync(new Date().toLocaleTimeString("zh-CN")); queueSnapshot.current = {context: contextKey, hasData: true};
        }
      } catch (cause) {
        if (current()) {setLoadError(cause instanceof Error ? cause.message : "队列读取失败，请重试。");setLoadErrorContext(contextKey);}
      } finally {
        if (current()) {setLoading(false); schedule();}
      }
    };
    void load();
    return () => {active = false; controller.abort(); window.clearTimeout(timer);};
  }, [allowed,admin,contextKey,page,revision]);
  const run = async (label: string, action: () => Promise<unknown>, refresh = true) => {
    if (actionLock.current) return;
    const actionContext = contextKey;
    actionLock.current = true; setBusy(label); setError(""); setMessage("");
    try {
      const result = await action();
      if (!alive.current || contextKeyRef.current !== actionContext) return;
      const feedback: Record<string,string> = {"提交审核":"文件已提交，等待管理员审核。","解析与入库":"处理任务已提交，完成状态以队列为准。","批准审核":"审核已批准，等待解析。","拒绝审核":"审核结果已保存。","归档记录":"记录已归档，原文和已有索引保留。","读取 PDF":"PDF 预览已打开。","下载 PDF":"PDF 原件下载已发起。"};
      setMessage(result && typeof result === "object" && "status" in result && "chunks" in result
        ? result.status === "ready" ? "向量处理完成 · " + String(result.chunks) + " 个片段" : "向量处理暂未完成，请检查服务状态或稍后重试。"
        : feedback[label] ?? "操作已提交，请查看最新状态。");
      if (refresh) setRevision(value => value + 1);
    } catch (cause) {if (alive.current && contextKeyRef.current === actionContext) setError(cause instanceof Error ? cause.message : "操作未完成，请重试。");}
    finally {if (alive.current) {actionLock.current = false; setBusy("");}}
  };
  const choose = (file?: File) => {
    if (!file || busy) return;
    setError("");
    if (!file.name.toLowerCase().endsWith(".pdf") || !file.size || file.size > 20*1048576) {
      setSelected(null); setError("请选择非空且不超过 20 MiB 的 PDF 文件。"); return;
    }
    setSelected(file);
  };
  const submit = () => {
    if (!selected) return;
    const file = selected, actionContext = contextKey;
    void run("提交审核", async () => {
      await uploadApi.upload(file,admin);
      if (alive.current && contextKeyRef.current === actionContext) {setSelected(null); setPage(1);}
    });
  };
  const visibleRows = dataContext === contextKey ? rows : [];
  const visibleTotal = dataContext === contextKey ? total : null;
  const currentLoadError = loadErrorContext === contextKey ? loadError : "";
  const queueLoading = loading || (allowed && dataContext !== contextKey && !currentLoadError);
  const visible = useMemo(() => visibleRows.filter(row => matches(row,filter) && row.original_name.toLocaleLowerCase().includes(term.trim().toLocaleLowerCase())), [visibleRows,filter,term]);
  const previewFile = (row: ServerUpload) => {
    const actionContext = contextKey;
    void run("读取 PDF", async () => {
      const blob = await uploadApi.preview(row.id);
      if (alive.current && contextKeyRef.current === actionContext) setPreview({url:URL.createObjectURL(blob),name:row.original_name});
    },false);
  };
  const download = (row: ServerUpload) => {
    const actionContext = contextKey;
    void run("下载 PDF", async () => {
      const blob = await uploadApi.preview(row.id);
      if (!alive.current || contextKeyRef.current !== actionContext) return;
    const url = URL.createObjectURL(blob), link = document.createElement("a");
    link.href = url; link.download = row.original_name.replace(/\.pdf$/i,"") + ".pdf"; link.click();
    window.setTimeout(() => URL.revokeObjectURL(url),60000);
    },false);
  };
  const intake = <section className="account-panel upload-intake">
    <div className={"upload-drop server-upload-drop" + (dragging ? " is-dragging" : "") + (selected ? " has-file" : "")}
      onDragEnter={event => {event.preventDefault(); if(allowed&&!busy)setDragging(true);}}
      onDragOver={event => {event.preventDefault(); event.dataTransfer.dropEffect = allowed&&!busy ? "copy" : "none";}}
      onDragLeave={event => {if(!(event.relatedTarget instanceof Node)||!event.currentTarget.contains(event.relatedTarget))setDragging(false);}}
      onDrop={event => {event.preventDefault(); setDragging(false); if(allowed)choose(event.dataTransfer.files[0]);}}>
      <div className="upload-paper-scene" aria-hidden="true"><span/><span/><span><FileText size={40} strokeWidth={1.4}/><small>PDF</small></span></div>
      <span className="upload-intake-label">PDF → 研究文献</span>
      <h2>{selected ? "文件已选好" : "把下一篇论文放进来"}</h2>
      <p>{allowed ? "拖入一份 PDF，或选择文件。确认后提交审核。" : "登录后提交到自己的账户，随时查看审核与收录状态。"}</p>
      {allowed ? <><button className={"button " + (selected ? "button-secondary" : "button-primary")} disabled={Boolean(busy)} onClick={() => input.current?.click()}><FolderOpen size={16}/>{selected ? "换一份文件" : "选择 PDF 文件"}</button>
        <input ref={input} hidden type="file" accept=".pdf,application/pdf" onChange={event => {choose(event.target.files?.[0]);event.target.value="";}}/></>
        : <Link className="button button-secondary" to="/upload?storage=local"><FolderOpen size={16}/>先用本机文件</Link>}
      <small className="upload-limit">最大 20 MiB · 最多 300 页 · 需未加密</small>
    </div>
    {selected && <div className="selected-file server-selected-file"><FileText size={24}/><span>{selected.name}<small>{(selected.size/1048576).toFixed(2)} MiB · 服务器将在提交后核验文件内容</small></span>
      <button className="icon-button" disabled={Boolean(busy)} aria-label="取消所选文件" onClick={() => setSelected(null)}><X size={16}/></button>
      <button className="button button-primary" disabled={Boolean(busy)} onClick={submit}><UploadCloud size={16}/>{busy === "提交审核" ? "正在发送与核验…" : "提交审核"}</button>
    </div>}
    <p className="upload-intake-note">文本型 PDF 可提取正文；扫描件需先完成 OCR。审核通过后由管理员处理，关键词索引与向量处理分别确认。</p>
  </section>;
  return <div className={"workspace-page content-wrap upload-workflow-page" + (admin ? " review-console-page" : "")}>
    <PageHeading eyebrow={admin ? "论文审核" : "文件管理"} title={admin ? "审核与收录" : "PDF 工作区"} desc={admin ? "核对原文、作出审核决定，再跟进解析与收录。" : "从一份 PDF 开始，跟进它进入检索库的每一步。"}/>
    {authLoading ? <div className="upload-workflow-loading" role="status">正在确认账户…</div> : <>
      {!admin ? <div className="upload-workflow-grid">{intake}<aside className="account-panel upload-workflow-aside">
        <span className="upload-aside-symbol"><LockKeyhole size={22}/></span><h2>{user ? "你的账户文件" : "登录后，进度随账户保存"}</h2>
        <p>原文保留在服务端，审核结果和处理原因会留在上传记录里。</p>
        {!allowed && <Link className="button button-primary button-full" to="/account?next=%2Fupload">登录并上传 <ArrowRight size={16}/></Link>}
        <ol className="upload-flow-guide"><li><span>01</span><div><strong>提交 PDF</strong><small>核验格式、大小与重复内容</small></div></li><li><span>02</span><div><strong>管理员审核</strong><small>先看原文，再批准或说明原因</small></div></li><li><span>03</span><div><strong>解析与收录</strong><small>处理完成后开放关键词检索</small></div></li></ol>
        <p>只想在此浏览器预览，可切换“本机文件”。本机审核不会发布到论文库。</p>
      </aside></div> : <>
        <section className="review-console-overview" aria-label="本页审核状态"><div className="review-console-caption"><span>队列总记录数</span><strong>{allowed && visibleTotal !== null ? visibleTotal : "—"}<small>条服务端记录</small></strong></div>
          {filters.slice(1).map(item => <div key={item.value} data-status={item.value}><span>本页 · {item.label}</span><strong>{allowed && visibleTotal !== null ? visibleRows.filter(row=>matches(row,item.value)).length : "—"}</strong></div>)}
        </section>
        {!allowed && <section className="account-panel review-access-gate"><LockKeyhole size={28}/><div><h2>{user ? "需要管理员身份" : "登录管理员账户后审核"}</h2><p>{user ? "研究账户可以查看自己的上传；审核决定与入库操作由管理员完成。" : "核对 PDF 原文，记录审核意见，并跟进已批准文件的处理结果。"}</p></div><Link className="button button-primary" to={user ? "/upload" : "/account?next=%2Fadmin"}>{user ? "我的上传" : "登录账户"}<ArrowRight size={16}/></Link></section>}
      </>}
      {allowed && <>
        {admin && <details className="review-upload-extra"><summary>补充上传一份 PDF</summary>{intake}</details>}
        {error && <div className="inline-error" role="alert"><AlertCircle size={16}/>{error}</div>}
        {busy ? <p className="upload-action-status" role="status">{busy}中，请稍候…</p> : message && <p className="upload-action-status" role="status"><CheckCircle2 size={16}/>{message}</p>}
        <section className="account-panel upload-queue-panel" aria-label={admin ? "审核队列" : "我的上传"} aria-busy={queueLoading}>
          <div className="upload-queue-heading"><div><h2>{admin ? "审核队列" : "我的上传"}<span>{visibleTotal ?? "—"}</span></h2><p>{dataContext === contextKey && lastSync ? "上次同步 " + lastSync + " · 本页状态每 8 秒检查一次" : "正在读取账户记录"}</p></div><div className="upload-queue-tools"><button className="button button-secondary" disabled={Boolean(busy)||queueLoading} onClick={()=>setRevision(value=>value+1)}><RefreshCw size={16}/>刷新状态</button>{admin && <button className="text-action" disabled={Boolean(busy)} onClick={()=>void run("重试向量处理",()=>uploadApi.vectorize())}>重试向量处理</button>}</div></div>
          <div className="upload-queue-filters"><label><Search size={16}/><input aria-label="筛选本页上传文件" placeholder="筛选本页文件名…" value={term} onChange={event=>setTerm(event.target.value)}/></label><div role="group" aria-label="本页处理状态">{filters.map(item=><button key={item.value} aria-pressed={filter===item.value} onClick={()=>setFilter(item.value)}>{item.label}</button>)}</div></div>
          {currentLoadError && <div className="inline-error" role="alert">{currentLoadError} {visibleTotal !== null && "当前仍显示上次成功读取的记录。"}<button className="text-action" onClick={()=>setRevision(value=>value+1)}>重新读取</button></div>}
          {queueLoading && <div className="upload-queue-loading" role="status">正在读取上传记录…<span/><span/></div>}
          {!queueLoading && !currentLoadError && !visible.length && <div className="empty-state upload-queue-empty"><FileText size={28}/><h3>{visibleRows.length ? "本页没有符合条件的文件" : "下一篇文献，从这里开始"}</h3><p>{visibleRows.length ? "可清除筛选或翻页查看其他记录。" : "提交一份 PDF 后，这里会显示审核、处理结果和原文入口。"}</p>{(term||filter!=="all") && <button className="button button-secondary" onClick={()=>{setTerm("");setFilter("all");}}>清除本页筛选</button>}</div>}
          {visible.map(row => <article key={row.id} className="server-upload-row" data-status={row.status}>
            <div className="server-upload-heading"><span className="server-upload-file-icon" aria-hidden="true"><FileText size={24}/></span><div><strong>{row.original_name}</strong><p>{(row.size/1048576).toFixed(2)} MiB · 提交于 {new Date(row.created_at).toLocaleString("zh-CN")}</p></div><span className={"status-pill upload-status-"+(uploadWorkflow(row.status).known ? row.status : "unknown")}>{uploadWorkflow(row.status).label}</span></div>
            <UploadTimeline status={row.status}/>
            {row.reason && <p className="upload-reason"><AlertCircle size={15}/>{uploadReason(row.reason)}</p>}
            <div className="upload-row-meta"><span>最后更新 {new Date(row.updated_at).toLocaleString("zh-CN")}</span><span>已发起处理 {row.attempts} 次</span>{row.status === "indexed" && <span>向量状态单独确认</span>}</div>
            {admin && row.status === "pending" && <label className="review-note server-review-note">审核意见<textarea maxLength={1000} rows={2} placeholder="填写来源、格式或质量方面的核对意见…" value={notes[row.id]||""} onChange={event=>setNotes(old=>({...old,[row.id]:event.target.value}))}/></label>}
            <div className="upload-row-footer"><div className="detail-buttons"><button className="button button-secondary" disabled={Boolean(busy)} onClick={event=>{previewTrigger.current=event.currentTarget;previewFile(row);}}>查看 PDF</button><button className="text-action" disabled={Boolean(busy)} onClick={()=>download(row)}>下载 PDF</button>{row.paper_id && <Link className="text-action" to={"/paper/"+encodeURIComponent(row.paper_id)}>打开论文 <ArrowRight size={14}/></Link>}</div>
              {admin && <div className="detail-buttons review-decision-actions">{row.status === "pending" && <><button className="button review-reject" disabled={Boolean(busy)} onClick={()=>void run("拒绝审核",()=>uploadApi.review(row.id,"reject",notes[row.id]||""))}>拒绝</button><button className="button button-primary" disabled={Boolean(busy)} onClick={()=>void run("批准审核",()=>uploadApi.review(row.id,"approve",notes[row.id]||""))}>批准</button></>}{canProcessUpload(row.status) && <button className="button button-primary" disabled={Boolean(busy)} onClick={()=>void run("解析与入库",()=>uploadApi.process(row.id))}>{row.status === "approved" ? "解析并入库" : "重试解析与入库"}</button>}{row.status !== "processing" && <button className="text-action" disabled={Boolean(busy)} onClick={()=>{if(window.confirm("归档此审核记录？源 PDF 和已有索引会保留。"))void run("归档记录",()=>uploadApi.archive(row.id));}}>归档</button>}</div>}
            </div>
          </article>)}
          {visibleTotal !== null && visibleTotal > 20 && <nav className="pagination" aria-label="上传记录分页"><button disabled={page<=1||Boolean(busy)||queueLoading} onClick={()=>setPage(page-1)}>上一页</button><span>{page} / {Math.ceil(visibleTotal/20)}</span><button disabled={page*20>=visibleTotal||Boolean(busy)||queueLoading} onClick={()=>setPage(page+1)}>下一页</button></nav>}
        </section>
      </>}
    </>}
    {preview && allowed && dataContext === contextKey && <section ref={previewPanel} className="account-panel server-preview-panel"><div className="results-topbar"><h2>{preview.name}</h2><button className="button button-secondary" onClick={()=>{setPreview(null);previewTrigger.current?.focus();}}>关闭预览</button></div><iframe className="server-pdf-preview" title={preview.name} src={preview.url}/></section>}
  </div>;
}
