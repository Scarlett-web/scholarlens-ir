import {ServerUploadWorkbench} from "../components/ServerUploadWorkbench";
import { useRef, useState } from "react";
import { AlertCircle, CheckCircle2, FileText, FolderOpen, ShieldCheck, Trash2, UploadCloud } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import { useStudio } from "../App";
import { IntegrationNotice, PageHeading } from "../components/Layout";
import { LocalPdfViewer } from "../components/LocalPdfViewer";

const LIMIT_MB = 15;
function LocalUploadPage() {
  const input = useRef<HTMLInputElement>(null);
  const [selected, setSelected] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [preview, setPreview] = useState<{ id: string; name: string } | null>(null);
  const { uploads, addUpload, removeUpload, notify } = useStudio();

  const choose = (file?: File) => {
    if (!file) return;
    setError("");
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setSelected(null);
      setError("只能选择 PDF 文件");
      return;
    }
    if (file.size > LIMIT_MB * 1024 * 1024) {
      setSelected(null);
      setError("文件超过 15MB 限制，请换一个 PDF");
      return;
    }
    setSelected(file);
  };

  const save = async () => {
    if (!selected) return;
    setBusy(true);
    setError("");
    try {
      await addUpload(selected);
      setSelected(null);
      if (input.current) input.current.value = "";
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "保存失败，请检查浏览器存储权限");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id: string) => {
    if (!window.confirm("确定删除此 PDF 文件及本地审核记录吗？此操作无法撤销。")) return;
    try { await removeUpload(id); }
    catch (cause) { notify(cause instanceof Error ? cause.message : "删除失败"); }
  };

  return (
    <div className="workspace-page content-wrap">
      <PageHeading eyebrow="文件管理" title="PDF 工作区" desc="将 PDF 保存在本机浏览器，随时预览并提交本地审核。"/>
      <IntegrationNotice title="本地文件工作区 · 与正式数据库隔离" desc="文件只保存在当前浏览器，不会上传或进入公共论文库。清除浏览器数据会删除这些文件，请保留原件。"/>
      <div className="upload-grid">
        <div className="upload-panel">
          <div className={selected ? "upload-drop has-file" : "upload-drop"}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {e.preventDefault(); choose(e.dataTransfer.files?.[0]);}}>
            <UploadCloud size={36} strokeWidth={1.6}/>
            <h2>添加本地论文 PDF</h2>
            <p>拖入 PDF，或选择文件。每份文件不超过 15 MB。</p>
            <button className="button button-secondary" type="button" onClick={() => input.current?.click()}>
              <FolderOpen size={16}/> 选择 PDF 文件
            </button>
            <input hidden ref={input} type="file" accept=".pdf,application/pdf"
              onChange={(e) => choose(e.target.files?.[0])}/>
          </div>
          {selected && <div className="selected-file">
            <FileText size={22}/>
            <span>{selected.name}<small>{(selected.size / 1048576).toFixed(2)} MB · 待验证</small></span>
            <button className="button button-secondary" onClick={() => {setSelected(null);if(input.current)input.current.value="";}}>取消</button>
            <button className="button button-primary" onClick={save} disabled={busy}>
              {busy ? "正在核验和保存…" : "保存到本地队列"}
            </button>
          </div>}
          {error && <div className="inline-error" role="alert"><AlertCircle size={17}/>{error}</div>}
          <div className="upload-benefits">
            <div><CheckCircle2 size={17}/><span>真实 PDF 内容保存在浏览器中</span></div>
            <div><CheckCircle2 size={17}/><span>支持本地预览、删除和审核记录</span></div>
            <div><ShieldCheck size={17}/><span>无需上传，即可预览原文</span></div>
          </div>
        </div>
        <div className="upload-aside">
          <ShieldCheck size={25}/>
          <h3>本机预览，服务端收录</h3>
          <p>本机文件只留在此浏览器。需要进入检索库时，请切换到服务端上传。</p>
          <ol>
            <li>验证格式、大小和内容哈希</li>
            <li>管理员审核与重复检测</li>
            <li>提取 PDF 文本并核验解析质量</li>
            <li>写入独立上传索引，开放检索</li>
          </ol>
          <p className="upload-guidance">本机审核仅用于整理文件，不会发布到检索库。服务端收录需要重新上传并通过管理员审核。</p>
          <Link className="button button-secondary button-full" to="/admin?storage=local">打开本机审核</Link>
          <Link className="button button-secondary button-full" to="/upload">切换服务端上传</Link>
        </div>
      </div>
      <section className="uploaded-list">
        <div className="section-heading">
          <div><span className="eyebrow">LOCAL FILES</span><h2>本地 PDF 队列</h2></div>
          <span className="table-status">{uploads.length} 个文件</span>
        </div>
        {uploads.length ? uploads.map((entry) => <div className="file-queue-row" key={entry.id}>
          <div className="file-queue-icon"><FileText size={23}/></div>
          <div className="file-queue-main"><strong>{entry.name}</strong>
            <span>{(entry.size / 1048576).toFixed(2)} MB · {new Date(entry.submittedAt).toLocaleString("zh-CN")}</span>
            {entry.sha256 && <code title={entry.sha256}>SHA-256: {entry.sha256.slice(0, 16)}…</code>}
            {entry.reviewNote && <span>审核意见：{entry.reviewNote}</span>}
          </div>
          <span className={"status-pill status-" + entry.status}>{entry.status==="pending"?"待审核":entry.status==="approved"?"本地已通过":"本地已拒绝"}</span>
          <div className="file-queue-actions">
            <button className="button button-secondary" onClick={() => setPreview({id: entry.id, name:entry.name})}>查看 PDF</button>
            <button className="icon-button" title="删除本地 PDF" aria-label={"删除"+entry.name} onClick={() => void remove(entry.id)}><Trash2 size={18}/></button>
          </div>
        </div>) : <div className="empty-state">
          <FileText size={30}/><h3>还没有本地 PDF</h3><p>选择一篇真实 PDF，即可体验保存、预览与审核完整流程。</p>
        </div>}
      </section>
      {preview && <LocalPdfViewer id={preview.id} title={preview.name} onClose={() => setPreview(null)}/>}
    </div>
  );
}

export function UploadPage(){
  const [params,setParams]=useSearchParams();
  const local=params.get("storage")==="local";
  const setLocal=(value:boolean)=>{const next=new URLSearchParams(params);if(value)next.set("storage","local");else next.delete("storage");setParams(next);};
  return <><div className="content-wrap workbench-switch segmented" role="group" aria-label="文件保存位置"><button type="button" aria-pressed={!local} className={!local?"selected":""} onClick={()=>setLocal(false)}>账户上传</button><button type="button" aria-pressed={local} className={local?"selected":""} onClick={()=>setLocal(true)}>本机文件</button></div>{local?<LocalUploadPage/>:<ServerUploadWorkbench admin={false}/>}</>;
}
