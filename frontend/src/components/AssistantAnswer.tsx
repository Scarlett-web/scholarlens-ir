import {useEffect,useId,useMemo,useRef,useState} from "react";
import {Link} from "react-router-dom";
import {ArrowUpRight,BookOpen,X} from "lucide-react";
import type {AiSource} from "../services/ai";
import {assistantCitations} from "../lib/assistantCitations";
import {evidenceHref,evidenceLocatorLabel} from "../lib/evidenceLocation";

/** Shared by live replies and saved conversations, for any returned paper/fragment. */
export function AssistantAnswer({content,sources,sourceLabel}:{content:string;sources?:AiSource[];sourceLabel?:string}){
  const {parts,references}=useMemo(()=>assistantCitations(content,sources),[content,sources]);
  const [active,setActive]=useState<number|null>(null);
  const dialog=useRef<HTMLDialogElement|null>(null),heading=useId();
  const reference=references.find(item=>item.number===active);
  useEffect(()=>{if(reference&&!dialog.current?.open)dialog.current?.showModal();},[reference]);
  return <>
    <p className="assistant-answer-text">{parts.map((part,index)=>part.kind==="text"?part.text:part.kind==="missing"?
      <span key={index} className="assistant-citation-missing" title="当前回答没有返回这条标记的来源，无法核对">[来源缺失]</span>:
      <button key={index} type="button" className="assistant-inline-citation" aria-label={`查看引用 ${part.number} 的原文`} aria-haspopup="dialog" onClick={()=>setActive(part.number)}>[{part.number}]</button>
    )}</p>
    {references.length>0&&<div className="ai-chat-citations assistant-numbered-sources"><strong>{sourceLabel||"引用来源"} · {references.length} 条片段</strong><ol>
      {references.map(({number,source})=><li key={number}><button type="button" className="assistant-source-link" aria-label={`查看引用 ${number}：${source.title||"论文标题暂缺"}`} aria-haspopup="dialog" onClick={()=>setActive(number)}><span>[{number}]</span><span>{source.title||"论文标题暂缺"}<small>{evidenceLocatorLabel(source.locator||"")}</small></span><BookOpen size={15}/></button></li>)}
    </ol></div>}
    <dialog ref={dialog} className="assistant-citation-dialog" aria-labelledby={heading} onClose={()=>setActive(null)} onClick={event=>{if(event.target===event.currentTarget){const rect=event.currentTarget.getBoundingClientRect();if(event.clientX<rect.left||event.clientX>rect.right||event.clientY<rect.top||event.clientY>rect.bottom)event.currentTarget.close();}}}>
      {reference&&<><header><span>引用 [{reference.number}] · 原文证据</span><button type="button" className="assistant-tool" aria-label="关闭引用原文" autoFocus onClick={()=>dialog.current?.close()}><X size={18}/></button></header>
        <div className="assistant-citation-body"><h2 id={heading}>{reference.source.title||"论文标题暂缺"}</h2><p className="assistant-citation-position">{evidenceLocatorLabel(reference.source.locator||"")}</p>
          {reference.source.excerpt?<blockquote>{reference.source.excerpt}</blockquote>:<p>这条历史引用没有保存原文片段，请打开论文核对。</p>}
          <Link className="button button-primary" to={evidenceHref({paper_id:reference.source.paper_id,locator:reference.source.locator||"",quote:reference.source.excerpt||""})} target="_blank" rel="noopener noreferrer"><BookOpen size={15}/>打开论文核对原文<ArrowUpRight size={14}/></Link>
        </div></>}
    </dialog>
  </>;
}
