import {useEffect,useRef,useState} from "react";
import {Link} from "react-router-dom";
import {useAuth} from "../services/AuthContext";
import {uploadApi} from "../services/backend";
import type {ServerUpload} from "../services/backend";
import {PageHeading} from "./Layout";

const labels:Record<string,string>={pending:"待审核",approved:"已批准，待解析",rejected:"已拒绝",processing:"正在解析与入库",indexed:"已进入关键词索引",failed:"处理失败",dependency_unavailable:"解析服务不可用"};
export function ServerUploadWorkbench({admin=false}:{admin?:boolean}){
  const {user}=useAuth();
  const [rows,setRows]=useState<ServerUpload[]>([]),[page,setPage]=useState(1),[total,setTotal]=useState(0);
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState(false),[error,setError]=useState(""),[message,setMessage]=useState(""),[revision,setRevision]=useState(0);
  const [notes,setNotes]=useState<Record<string,string>>({});
  const [preview,setPreview]=useState<{url:string;name:string}|null>(null);
  const fileInput=useRef<HTMLInputElement>(null);
  const allowed=Boolean(user&&(!admin||user.role==="admin"));
  useEffect(()=>{
    if(!allowed)return;
    let active=true;
    setLoading(true);
    const load=()=>uploadApi.list(admin,page).then(data=>{if(active){setRows(data.results);setTotal(data.total);}}).catch(cause=>{if(active)setError(cause instanceof Error?cause.message:"队列加载失败");}).finally(()=>{if(active)setLoading(false);});
    void load();const timer=window.setInterval(()=>void load(),8000);
    return()=>{active=false;window.clearInterval(timer);};
  },[allowed,admin,page,revision]);
  useEffect(()=>()=>{if(preview)URL.revokeObjectURL(preview.url);},[preview]);
  const run=async(action:()=>Promise<unknown>)=>{
    if(busy)return;setBusy(true);setError("");setMessage("");
    try{const result=await action();setRevision(value=>value+1);if(result&&typeof result==="object"&&"status" in result&&"chunks" in result)setMessage("上传文献向量化："+String(result.status)+" · "+String(result.chunks)+" 个片段");}catch(cause){setError(cause instanceof Error?cause.message:"操作失败");}finally{setBusy(false);}
  };
  const download=async(row:ServerUpload)=>{
    const blob=await uploadApi.docx(row.id),url=URL.createObjectURL(blob),link=document.createElement("a");
    link.href=url;link.download=row.original_name.replace(/\.pdf$/i,"")+".docx";link.click();window.setTimeout(()=>URL.revokeObjectURL(url),60000);
  };
  return <div className="workspace-page content-wrap">
    <PageHeading eyebrow={admin?"论文审核":"文件管理"} title={admin?"服务端审核":"上传研究文献"} desc="提交 PDF，查看审核和处理进度。"/>
    {!allowed?<section className="account-panel"><h2>{user?"需要管理员身份":admin?"登录管理员账户后审核":"登录后上传论文"}</h2><p>{user?"服务端会校验角色，普通研究账户可以管理自己的上传。":"本机 PDF 仍可在上方“本机文件”中使用。"}</p><Link className="button button-primary" to={user?"/upload":"/account?next="+encodeURIComponent(admin?"/admin":"/upload")}>{user?"我的上传":"登录账户"}</Link></section>:<>
      <section className="account-panel"><div className="detail-buttons">
        <button className="button button-primary" disabled={busy} onClick={()=>fileInput.current?.click()}>选择 PDF 并上传</button>
        <button className="button button-secondary" disabled={busy} onClick={()=>setRevision(value=>value+1)}>刷新状态</button>
        {admin&&<button className="button button-secondary" disabled={busy} onClick={()=>void run(()=>uploadApi.vectorize())}>重试上传文献向量化</button>}
      </div><p>最大 20 MiB、300 页。上传后先审核，再由管理员解析。文本型 PDF 支持本地提取；扫描件需 OCR。上传索引与基础论文库隔离。</p>
      <input ref={fileInput} hidden type="file" accept=".pdf,application/pdf" onChange={event=>{const file=event.target.files?.[0];event.target.value="";if(!file)return;if(!file.name.toLowerCase().endsWith(".pdf")||file.size>20*1048576){setError("请选择不超过20 MiB的PDF文件");return;}void run(async()=>{await uploadApi.upload(file,admin);setPage(1);});}}/>
      </section>
      {error&&<div className="inline-error" role="alert">{error}</div>}{message&&<p role="status">{message}</p>}
      <section className="account-panel"><h2>{admin?"审核队列":"我的上传"} · {total}</h2>
      {loading&&<p role="status">正在读取上传记录…</p>}
      {!loading&&!error&&!rows.length&&<p>还没有上传记录。可以先添加一篇有文本层的 PDF。</p>}
      {rows.map(row=><article key={row.id} className="server-upload-row">
        <div><strong>{row.original_name}</strong><span className="status-pill">{labels[row.status]||row.status}</span><p>{(row.size/1048576).toFixed(2)} MiB · {new Date(row.created_at).toLocaleString()} · 处理 {row.attempts} 次</p>{row.reason&&<p role="status">{row.reason}</p>}</div>
        {admin&&row.status==="pending"&&<label>审核意见<textarea maxLength={1000} value={notes[row.id]||""} onChange={event=>setNotes({...notes,[row.id]:event.target.value})}/></label>}
        <div className="detail-buttons">
          <button className="button button-secondary" disabled={busy} onClick={()=>void run(async()=>{const blob=await uploadApi.preview(row.id);setPreview({url:URL.createObjectURL(blob),name:row.original_name});})}>查看 PDF</button>
          <button className="button button-secondary" disabled={busy} onClick={()=>void run(()=>download(row))}>下载 DOCX</button>
          {row.paper_id&&<Link className="button button-secondary" to={"/paper/"+encodeURIComponent(row.paper_id)}>打开论文</Link>}
          {admin&&row.status==="pending"&&<><button className="button button-primary" disabled={busy} onClick={()=>void run(()=>uploadApi.review(row.id,"approve",notes[row.id]||""))}>批准</button><button className="button button-secondary" disabled={busy} onClick={()=>void run(()=>uploadApi.review(row.id,"reject",notes[row.id]||""))}>拒绝</button></>}
          {admin&&["approved","failed","dependency_unavailable"].includes(row.status)&&<button className="button button-primary" disabled={busy} onClick={()=>void run(()=>uploadApi.process(row.id))}>解析并入库</button>}
          {admin&&row.status!=="processing"&&<button className="button button-secondary" disabled={busy} onClick={()=>{if(window.confirm("归档此审核记录？源PDF和已有索引会保留。"))void run(()=>uploadApi.archive(row.id));}}>归档记录</button>}
        </div>
      </article>)}
      {total>20&&<nav className="pagination" aria-label="上传记录分页"><button disabled={page<=1||busy} onClick={()=>setPage(page-1)}>上一页</button><span>{page} / {Math.max(1,Math.ceil(total/20))}</span><button disabled={page*20>=total||busy} onClick={()=>setPage(page+1)}>下一页</button></nav>}
      </section>
    </>}
    {preview&&<section className="account-panel"><div className="results-topbar"><h2>{preview.name}</h2><button className="button button-secondary" onClick={()=>setPreview(null)}>关闭预览</button></div><iframe className="server-pdf-preview" title={preview.name} src={preview.url}/></section>}
  </div>;
}
