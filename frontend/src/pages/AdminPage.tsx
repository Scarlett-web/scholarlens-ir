import {ServerUploadWorkbench} from "../components/ServerUploadWorkbench";
import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Check, ClipboardCheck, FileSearch, Filter, RotateCcw, Shield, Trash2, X } from "lucide-react";
import { useStudio } from "../App";
import { IntegrationNotice, PageHeading } from "../components/Layout";
import { ToolNavigation } from "../components/ToolNavigation";
import { LocalPdfViewer } from "../components/LocalPdfViewer";
import type { LocalUpload } from "../types";

type StatusFilter = "all" | LocalUpload["status"];
const FILTERS: {value:StatusFilter;label:string}[] = [
  {value:"all",label:"全部"}, {value:"pending",label:"待审核"},
  {value:"approved",label:"已通过"}, {value:"rejected",label:"已拒绝"}
];

function LocalAdminPage(){
  const { uploads, updateUpload, saveUploadNote, removeUpload, notify } = useStudio();
  const [filter,setFilter] = useState<StatusFilter>("all");
  const [term,setTerm] = useState("");
  const [notes,setNotes] = useState<Record<string,string>>({});
  const [preview,setPreview] = useState<{id:string;name:string}|null>(null);

  const records = useMemo(() => uploads.filter((item) =>
    (filter==="all" || item.status===filter) && item.name.toLocaleLowerCase().includes(term.toLocaleLowerCase().trim())
  ),[uploads,filter,term]);

  const deleteEntry = async (id:string) => {
    if (!window.confirm("确定删除本地文件和审核记录？该操作不可恢复。")) return;
    try { await removeUpload(id); } catch (error) { notify(error instanceof Error ? error.message : "删除失败"); }
  };

  return <div className="workspace-page content-wrap">
    <PageHeading eyebrow="LOCAL REVIEW WORKBENCH" title="审核工作台" desc="查看本地 PDF、记录审核意见并管理审核状态。"/>
    <ToolNavigation/>
    <IntegrationNotice title="本地审核，不等于正式入库" desc="此页只整理当前浏览器里的 PDF。正式审批、解析和入库请切换到服务端审核，由服务器核验管理员身份。"/>
    <div className="admin-stats">
      <div><ClipboardCheck size={22}/><span>本地文件总数</span><strong>{uploads.length}</strong></div>
      <div><Shield size={22}/><span>待审核</span><strong>{uploads.filter((u)=>u.status==="pending").length}</strong></div>
      <div><Check size={22}/><span>本地已通过</span><strong>{uploads.filter((u)=>u.status==="approved").length}</strong></div>
    </div>
    <section className="admin-queue">
      <div className="section-heading"><div><span className="eyebrow">REVIEW QUEUE</span><h2>审核队列</h2></div>
        <Link className="button button-secondary" to="/upload?storage=local">添加本机 PDF</Link></div>
      <div className="admin-filters">
        <label><FileSearch size={17}/><input placeholder="按文件名筛选…" value={term} onChange={(e)=>setTerm(e.target.value)} aria-label="按文件名搜索"/></label>
        <div className="admin-filter-chips" role="group" aria-label="按审核状态筛选">
          {FILTERS.map((item)=><button className={filter===item.value?"active":""} key={item.value}
            onClick={()=>setFilter(item.value)}><Filter size={13}/>{item.label}</button>)}
        </div>
      </div>
      {records.length ? records.map((item) => <div className="review-entry" key={item.id}>
        <div className="review-file-info">
          <div><strong>{item.name}</strong><span className={"status-pill status-"+item.status}>
            {item.status==="pending"?"待审核":item.status==="approved"?"本地已通过":"本地已拒绝"}
          </span></div>
          <p>{(item.size/1048576).toFixed(2)} MB · {new Date(item.submittedAt).toLocaleString("zh-CN")}</p>
          {item.sha256&&<code title={item.sha256}>SHA-256 {item.sha256}</code>}
          {item.reviewedAt&&<p>最后审核：{new Date(item.reviewedAt).toLocaleString("zh-CN")}</p>}
        </div>
        <label className="review-note">审核意见（保存在本机）
          <textarea maxLength={500} rows={2} placeholder="可填写格式、重复、质量等说明…"
            value={notes[item.id] ?? item.reviewNote ?? ""}
            onChange={(e)=>setNotes((old)=>({...old,[item.id]:e.target.value}))}/>
        </label>
        <div className="review-actions">
          <button className="button button-secondary" onClick={()=>setPreview({id:item.id,name:item.name})}><FileSearch size={16}/> 查看原文</button>
          <button className="button button-secondary" onClick={()=>saveUploadNote(item.id,notes[item.id]??item.reviewNote??"")}>保存意见</button>
          <button className="button button-primary" disabled={item.status==="approved"} onClick={()=>updateUpload(item.id,"approved",notes[item.id]??item.reviewNote)}><Check size={16}/> 通过</button>
          <button className="button button-secondary" disabled={item.status==="rejected"} onClick={()=>updateUpload(item.id,"rejected",notes[item.id]??item.reviewNote)}><X size={16}/> 拒绝</button>
          <button className="icon-button" title="恢复待审核" disabled={item.status==="pending"} onClick={()=>updateUpload(item.id,"pending",notes[item.id]??item.reviewNote)}><RotateCcw size={18}/></button>
          <button className="icon-button" title="删除记录和文件" onClick={()=>void deleteEntry(item.id)}><Trash2 size={18}/></button>
        </div>
      </div>) : <div className="empty-state"><FileSearch size={29}/><h3>当前筛选下没有文件</h3><p>更换筛选条件，或者从上传中心加入 PDF。</p>
        {(filter!=="all"||term)&&<button className="button button-secondary" onClick={()=>{setFilter("all");setTerm("")}}>查看全部记录</button>}
      </div>}
      <p className="metric-footnote">审核状态和意见存于 localStorage，PDF 字节存于 IndexedDB。浏览器清理数据后可能丢失。</p>
    </section>
    {preview&&<LocalPdfViewer id={preview.id} title={preview.name} onClose={()=>setPreview(null)}/>}
  </div>
}

export function AdminPage(){
  const [params,setParams]=useSearchParams();
  const local=params.get("storage")==="local";
  const setLocal=(value:boolean)=>{const next=new URLSearchParams(params);if(value)next.set("storage","local");else next.delete("storage");setParams(next);};
  return <><div className="content-wrap workbench-switch segmented" role="group" aria-label="文件保存位置"><button type="button" aria-pressed={!local} className={!local?"selected":""} onClick={()=>setLocal(false)}>服务端审核</button><button type="button" aria-pressed={local} className={local?"selected":""} onClick={()=>setLocal(true)}>本机文件</button></div>{local?<LocalAdminPage/>:<ServerUploadWorkbench admin={true}/>}</>;
}
