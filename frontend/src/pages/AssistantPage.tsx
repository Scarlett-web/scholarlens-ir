import {useEffect,useRef,useState} from "react";
import {Link,useSearchParams} from "react-router-dom";
import {ArrowRight,ArrowUp,BookOpen,CheckCircle2,History,Plus,SlidersHorizontal,PlugZap,Square,Workflow,TriangleAlert,X,Copy,Check,Loader2} from "lucide-react";
import {askAi,conversationApi,getAssistantAvailability,retrieveEvidence} from "../services/ai";
import type {AgentTrace,AiMessage,AiOperation,Conversation} from "../services/ai";
import {EvidenceWorkbench} from "../components/EvidenceWorkbench";
import {evidenceHref} from "../lib/evidenceLocation";
import type {EvidenceReference} from "../lib/evidenceLocation";
import {useStudio} from "../App";
import {useAuth} from "../services/AuthContext";
import {DATA_SOURCE,getPaper} from "../services/papers";
import {PersonalAiSettings} from "../components/PersonalAiSettings";
import {loadPersonalAi} from "../services/personalAi";

const EXAMPLES=["magnetic resonance imaging","protein structure","quantum theory"];
function safeAvailabilityReason(value: unknown, fallback = "问答服务当前不可用，请稍后重试。") {
  const text = String(value ?? "").replace(/\s+/g, " ").trim();
  if (!text) return fallback;
  return text
    .replace(/Bearer\s+[^\s,;]+/gi, "Bearer [已隐藏]")
    .replace(/((?:api[_ -]?key|token|secret|password|authorization))\s*[:=]\s*[^\s,;]+/gi, "$1: [已隐藏]")
    .replace(/\b(?:sk|rk)-[A-Za-z0-9_-]{12,}\b/g, "[已隐藏]")
    .slice(0, 240);
}
function ExecutionTrace({trace}:{trace:AgentTrace}){
  const statusLabel={done:"完成",running:"进行中",queued:"待执行",empty:"无结果",skipped:"跳过",error:"未完成"};
  return <details className="agent-trace"><summary><Workflow size={14}/>执行记录<span>{trace.evidence_count} 条证据{trace.elapsed_ms!==undefined?" · "+(trace.elapsed_ms/1000).toFixed(1)+" 秒":""}</span></summary><ol>{trace.steps.map(step=><li key={step.id} data-status={step.status}><span>{step.status==="done"?<CheckCircle2 size={14}/>:step.status==="error"?<TriangleAlert size={14}/>:<span className="agent-step-dot"/>}</span><span>{step.label}{step.result_count!==undefined?" · "+step.result_count+" 项":""}</span><small>{statusLabel[step.status]}{step.elapsed_ms!==undefined?" · "+(step.elapsed_ms/1000).toFixed(1)+"s":""}</small></li>)}</ol>{trace.warnings?.map((warning,index)=><p className="agent-warning" key={index}>{warning}</p>)}</details>;
}
export function AssistantPage(){
  const [params]=useSearchParams(),focusedPaper=params.get("paper")||"";
  const {favorites,motionPaused,reducedMotion}=useStudio(),{user}=useAuth();
  const [personal,setPersonal]=useState(()=>user?loadPersonalAi(user.id):null);
  const [draft,setDraft]=useState(""),[messages,setMessages]=useState<AiMessage[]>([]),[evidence,setEvidence]=useState<EvidenceReference[]|null>(null);
  const [evidenceQuestion,setEvidenceQuestion]=useState("");
  const [evidenceTrace,setEvidenceTrace]=useState<AgentTrace|undefined>();
  const [busy,setBusy]=useState(false),[error,setError]=useState(""),[pendingQuestion,setPendingQuestion]=useState("");
  const [availability,setAvailability]=useState({status:"checking",reason:"正在检查问答服务…"});
  const [operation,setOperation]=useState<AiOperation>("ask"),[selected,setSelected]=useState<string[]>(focusedPaper&&!focusedPaper.startsWith("demo-")?[focusedPaper]:[]),[focusTitle,setFocusTitle]=useState("");
  const [conversations,setConversations]=useState<Conversation[]>([]),[conversationId,setConversationId]=useState("");
  const [tool,setTool]=useState<"reading"|"history"|"api"|null>(null),[copied,setCopied]=useState<number|null>(null);
  const toolTrigger=useRef<HTMLButtonElement|null>(null),toolHeading=useRef<HTMLHeadingElement|null>(null);
  const controller=useRef<AbortController|null>(null),bottom=useRef<HTMLDivElement|null>(null),input=useRef<HTMLTextAreaElement|null>(null),conversation=useRef<HTMLDivElement|null>(null);
  const evidencePanel=useRef<HTMLElement|null>(null);
  const demoMode=DATA_SOURCE==="demo";
  const ready=!demoMode&&(Boolean(personal)||["ready","dependency_unavailable"].includes(availability.status));
  const availabilityReason=safeAvailabilityReason(availability.reason);
  const candidates=favorites.filter(item=>!item.paper.paper_id.startsWith("demo-")).map(item=>item.paper);
  const operationValid=operation==="ask"||operation==="summarize"&&selected.length===1||operation==="compare"&&selected.length>=2&&selected.length<=10;
  const closeTool=()=>{setTool(null);toolTrigger.current?.focus();};
  const toggleTool=(value:typeof tool,event?:React.MouseEvent<HTMLButtonElement>)=>{if(event)toolTrigger.current=event.currentTarget;setTool(old=>old===value?null:value);};
  useEffect(()=>{if(!tool)return;toolHeading.current?.focus();const escape=(event:KeyboardEvent)=>{if(event.key==="Escape"){event.preventDefault();setTool(null);toolTrigger.current?.focus();}};document.addEventListener("keydown",escape);return()=>document.removeEventListener("keydown",escape);},[tool]);
  useEffect(()=>{if(input.current){input.current.style.height="auto";input.current.style.height=Math.min(input.current.scrollHeight,160)+"px";}},[draft]);
  useEffect(()=>{
    if(demoMode){setAvailability({status:"not_configured",reason:"演示模式未连接真实问答服务"});return;}
    let active=true;getAssistantAvailability().then(data=>{if(active){const module=data.modules?.ai_qa;setAvailability({status:module?.status||"unavailable",reason:safeAvailabilityReason(module?.reason)});}}).catch(cause=>{if(active)setAvailability({status:"unavailable",reason:safeAvailabilityReason(cause instanceof Error?cause.message:undefined)});});return()=>{active=false;};
  },[demoMode]);
  useEffect(()=>{let active=true;setFocusTitle("");if(focusedPaper)void getPaper(focusedPaper).then(paper=>{if(active)setFocusTitle(paper?.title||"论文暂不可访问");}).catch(()=>{if(active)setFocusTitle("论文暂不可访问");});return()=>{active=false;};},[focusedPaper]);
  useEffect(()=>{let active=true;if(user)conversationApi.list().then(data=>{if(active)setConversations(data);}).catch(cause=>{if(active)setError(cause.message);});return()=>{active=false;};},[user]);
  useEffect(()=>{if(messages.length||pendingQuestion)conversation.current?.scrollTo({top:conversation.current.scrollHeight,behavior:motionPaused||reducedMotion?"instant":"smooth"});},[messages,pendingQuestion,motionPaused,reducedMotion]);
  useEffect(()=>{if(evidence!==null&&conversation.current&&evidencePanel.current)conversation.current.scrollTo({top:evidencePanel.current.offsetTop-conversation.current.offsetTop,behavior:motionPaused||reducedMotion?"instant":"smooth"});},[evidence,motionPaused,reducedMotion]);
  useEffect(()=>()=>controller.current?.abort(),[]);
  const request=async(action:(signal:AbortSignal)=>Promise<void>)=>{
    if(controller.current)return;const abort=new AbortController();controller.current=abort;setBusy(true);setError("");
    try{await action(abort.signal);}catch(cause){if(!abort.signal.aborted)setError(cause instanceof Error?cause.message:"请求失败");}
    finally{if(controller.current===abort){controller.current=null;setBusy(false);setPendingQuestion("");}}
  };
  const submit=()=>{
    const question=draft.trim()||(operation==="summarize"?"总结这篇论文的研究问题、方法、结果与局限。":operation==="compare"?"逐篇比较所选论文的方法、结论和局限，并列出证据。":"");
    if(controller.current||!ready||!operationValid||!question)return;
    setPendingQuestion(question);setCopied(null);
    void request(async signal=>{const reply=await askAi({question,paperIds:selected,operation,conversationId,personal,history:messages},signal);if(signal.aborted)return;setEvidence(null);setEvidenceTrace(undefined);setMessages(old=>[...old,{role:"user",content:question},reply]);setPendingQuestion("");setDraft("");if(user)setConversations(await conversationApi.list());});
  };
  const findEvidence=()=>{const question=draft.trim();if(!question||DATA_SOURCE!=="api")return;void request(async signal=>{const result=await retrieveEvidence(question,selected,signal);if(!signal.aborted){setEvidence(result.evidence);setEvidenceQuestion(question);setEvidenceTrace(result.agent);}});};
  const reset=()=>{controller.current?.abort();controller.current=null;setBusy(false);setPendingQuestion("");setCopied(null);setError("");setMessages([]);setEvidence(null);setEvidenceQuestion("");setEvidenceTrace(undefined);setDraft("");setConversationId("");};
  useEffect(()=>{reset();setSelected(focusedPaper&&!focusedPaper.startsWith("demo-")?[focusedPaper]:[]);setPersonal(user?loadPersonalAi(user.id):null);},[user?.id,focusedPaper]);
  const loginUrl="/account?"+new URLSearchParams({next:"/assistant"+(focusedPaper?"?paper="+encodeURIComponent(focusedPaper):"")});
  return <div className="workspace-page content-wrap ai-page">
    <div className="assistant-workspace">
      <div className="ai-shell">
        <header className="ai-shell-header"><div className="ai-shell-title"><h1>研究助手</h1><span>{demoMode?"演示模式":personal?personal.model:ready?"论文问答":"原文检索"}</span></div><div className="assistant-tools" role="group" aria-label="助手工具">
          <button className="assistant-tool" aria-label="阅读方式" aria-expanded={tool==="reading"} aria-controls="assistant-panel-reading" onClick={event=>toggleTool("reading",event)}><SlidersHorizontal size={16}/><span>阅读方式</span></button>
          <button className="assistant-tool" aria-label="对话记录" aria-expanded={tool==="history"} aria-controls="assistant-panel-history" onClick={event=>toggleTool("history",event)}><History size={16}/><span>对话记录</span></button>
          <button className="assistant-tool" aria-label="API 设置" aria-expanded={tool==="api"} aria-controls="assistant-panel-api" onClick={event=>toggleTool("api",event)}><PlugZap size={16}/><span>API 设置</span>{personal&&<i className="assistant-config-dot" aria-hidden="true"/>}</button>
          <button className="assistant-tool assistant-new" aria-label="新对话，清空当前内容" title="新对话" onClick={()=>{reset();input.current?.focus();}} disabled={busy}><Plus size={18}/></button>
        </div></header>
        <div ref={conversation} className={"ai-conversation"+(evidence!==null&&!messages.length?" is-evidence-only":"")} aria-live="polite">
          {!messages.length&&!pendingQuestion&&evidence===null&&<div className="ai-welcome"><div className="assistant-welcome-icon"><BookOpen size={28} strokeWidth={1.4}/></div><h2>{demoMode?"演示模式 · 仅展示界面":ready?"今天想研究什么？":"从一段原文，开始探索"}</h2><p>{demoMode?"切换到 API 数据源后，可检索原文并使用问答。":ready?"聊聊你的问题，或选几篇论文一起读。":"直接检索论文片段，或连接自己的 API 开始对话。"}</p><div className="ai-starters" aria-label="原文检索示例">{EXAMPLES.map(question=><button key={question} disabled={busy||demoMode} title={demoMode?"演示模式未连接原文服务":undefined} onClick={()=>{setDraft(question);input.current?.focus();}}>{question}<ArrowRight size={14}/></button>)}</div>{!ready&&!demoMode&&<button className="text-action" onClick={event=>toggleTool("api",event)}>连接个人 API <ArrowRight size={14}/></button>}</div>}
          {messages.map((message,index)=><div key={index} className={"ai-chat-message "+(message.role==="user"?"from-user":"from-assistant")}><div className="ai-chat-label">{message.role==="user"?"你的问题":message.answerKind==="general"?"通用回答 · 未由本库文献验证":"研究回答"}</div><p>{message.content}</p>{message.role==="assistant"&&message.agent&&<ExecutionTrace trace={message.agent}/ >}{Boolean(message.sources?.length)&&<div className="ai-chat-citations"><strong>{message.sourceLabel||"引用来源"}</strong>{message.sources?.map((source,i)=><Link key={source.chunk_id||source.paper_id+i} to={source.excerpt&&source.locator?evidenceHref({paper_id:source.paper_id,locator:source.locator,quote:source.excerpt}):"/paper/"+encodeURIComponent(source.paper_id)} target="_blank" rel="noopener noreferrer"><BookOpen size={15}/><span>{source.title}{source.excerpt&&<small>{source.excerpt}</small>}{source.locator&&<small>{source.locator}</small>}</span><ArrowRight size={15}/></Link>)}{message.sources?.some(source=>source.excerpt&&source.locator&&source.chunk_id)&&<button className="text-action" disabled={busy} onClick={()=>{
            setEvidence(message.sources!.flatMap(source=>source.excerpt&&source.locator&&source.chunk_id?[{paper_id:source.paper_id,paper_title:source.title,quote:source.excerpt,locator:source.locator,chunk_id:source.chunk_id}]:[]));
            setEvidenceQuestion(messages[index-1]?.role==="user"?messages[index-1].content:"这条回答的引用来源");setEvidenceTrace(message.agent);
          }}>核对引用片段 <ArrowRight size={14}/></button>}</div>}</div>)}
          {messages.length>0&&<div className="assistant-copy-row"><button className="text-action" onClick={()=>{const index=messages.map(message=>message.role).lastIndexOf("assistant");if(index>=0)void navigator.clipboard.writeText(messages[index].content).then(()=>setCopied(index)).catch(()=>setError("复制失败，请选中文字手动复制"));}}>{copied===messages.length-1?<Check size={14}/>:<Copy size={14}/>}复制最后一条回答</button></div>}
          {pendingQuestion&&busy&&<div className="ai-chat-message from-user"><div className="ai-chat-label">你的问题</div><p>{pendingQuestion}</p></div>}
          {busy&&<p className="ai-request-status" role="status"><Loader2 size={16} className="assistant-spinner"/>{pendingQuestion?"正在整理回答…":"正在检索原文…"}</p>}
          {evidence!==null&&<section ref={evidencePanel} className="evidence-results"><div className="evidence-results-heading"><h2>原文证据</h2><span>{evidence.length} 条片段</span><button className="text-action" onClick={()=>{setEvidence(null);input.current?.focus();}}>收起证据 <X size={14}/></button></div><p className="evidence-question">{evidenceQuestion}</p>{evidenceTrace&&<ExecutionTrace trace={evidenceTrace}/ >}{evidence.length?<EvidenceWorkbench key={evidenceQuestion+evidence.map(item=>item.chunk_id).join(":")} items={evidence} question={evidenceQuestion}/>:<div className="evidence-empty"><BookOpen size={24}/><h3>没有找到相关片段</h3><p>试试更短的关键词，或在阅读方式中扩大论文范围。</p></div>}</section>}
          <div ref={bottom}/>
        </div>
        <div className="ai-compose">{error&&<div className="inline-error" role="alert">{error}</div>}<form onSubmit={event=>{event.preventDefault();if(ready)submit();else findEvidence();}}>
          <textarea ref={input} value={draft} rows={2} maxLength={2000} onChange={event=>setDraft(event.target.value)} onKeyDown={event=>{if(event.key==="Enter"&&!event.shiftKey&&!event.nativeEvent.isComposing&&event.keyCode!==229){event.preventDefault();if(!busy){if(ready)submit();else findEvidence();}}}} placeholder={ready?"随时提问，也可以接着上文聊…":"输入论文关键词，查找相关原文…"} aria-label="研究问题" disabled={busy}/>
          <div className="ai-compose-footer"><button type="button" className="assistant-scope" onClick={event=>toggleTool("reading",event)}><SlidersHorizontal size={14}/>{operation==="ask"?"论文问答":operation==="summarize"?"单篇总结":"多篇比较"}<span>· {selected.length?selected.length+" 篇":"全部论文"}</span></button><div className="detail-buttons">{busy?<button type="button" className="button button-secondary" onClick={()=>{controller.current?.abort();controller.current=null;setBusy(false);setPendingQuestion("");setError("已停止本次请求");}}><Square size={15}/>停止</button>:<>{ready&&<button type="button" className="button button-secondary" disabled={!draft.trim()||demoMode} onClick={findEvidence}>只查原文</button>}<button type="submit" className="button button-primary" disabled={demoMode||DATA_SOURCE!=="api"||(ready?(!operationValid||operation==="ask"&&!draft.trim()):!draft.trim())}>{demoMode?<BookOpen size={15}/>:ready?<ArrowUp size={18}/>:<BookOpen size={15}/>} {demoMode?"演示模式不可用":ready?(operation==="ask"?"发送问题":operation==="summarize"?"生成总结":"比较论文"):"检索原文"}</button></>}</div></div>
        </form><div className="assistant-compose-note">{demoMode?"演示模式未连接真实服务":!operationValid&&ready?<button className="text-action" onClick={event=>toggleTool("reading",event)}>{operation==="summarize"?"请选择 1 篇论文":"请选择 2 至 10 篇论文"}</button>:<><span>Enter 发送 · Shift + Enter 换行</span><span>重要结论请核对原文</span></>}</div></div>
      </div>
      <aside className="assistant-sidebar" aria-label="论文助手设置" hidden={!tool}>
        <div className="assistant-panel-header"><h2 ref={toolHeading} tabIndex={-1}>{tool==="reading"?"阅读方式":tool==="history"?"对话记录":"API 设置"}</h2><button className="assistant-tool" aria-label="关闭助手工具" onClick={closeTool}><X size={18}/></button></div>
        <div className="assistant-panel-body">
        <section id="assistant-panel-reading" className="account-panel assistant-controls" hidden={tool!=="reading"}><p className="assistant-panel-intro">自由提问，或围绕选定论文深入阅读。</p><div className="assistant-mode-options" role="group" aria-label="研究方式">{([['ask','论文问答'],['summarize','单篇总结'],['compare','多篇比较']] as const).map(([value,label])=><button key={value} aria-pressed={operation===value} disabled={busy||!ready&&value!=="ask"} title={!ready&&value!=="ask"?"配置个人 API 后使用":undefined} onClick={()=>setOperation(value)}>{label}</button>)}</div>{!ready&&<p>总结与比较需先配置个人 API。</p>}
          <details open={operation!=="ask"}><summary>论文范围 <span>{selected.length?selected.length+" 篇":"全部"}</span></summary><p>{operation==="compare"?"选择 2 至 10 篇论文。":operation==="summarize"?"选择 1 篇论文。":"从收藏中选择论文，或保持全库检索。"}</p><div className="assistant-paper-options">{focusedPaper&&!candidates.some(p=>p.paper_id===focusedPaper)&&<label><input type="checkbox" checked={selected.includes(focusedPaper)} disabled={busy||focusedPaper.startsWith("demo-")} onChange={event=>setSelected(event.target.checked?[...selected,focusedPaper]:selected.filter(id=>id!==focusedPaper))}/>{focusTitle||"正在读取指定论文…"}</label>}{candidates.map(paper=><label key={paper.paper_id}><input type="checkbox" checked={selected.includes(paper.paper_id)} disabled={busy||!selected.includes(paper.paper_id)&&selected.length>=10} onChange={event=>setSelected(event.target.checked?[...selected,paper.paper_id]:selected.filter(id=>id!==paper.paper_id))}/>{paper.title}</label>)}</div>{!candidates.length&&!focusedPaper&&<Link to="/search">检索并收藏论文 <ArrowRight size={14}/></Link>}</details>
        </section>
        <section id="assistant-panel-history" className="account-panel assistant-conversations" hidden={tool!=="history"}>{user?<><label>当前对话<select aria-label="研究对话" value={conversationId} disabled={busy} onChange={event=>{const id=event.target.value;void request(async()=>{setMessages(id?await conversationApi.messages(id):[]);setConversationId(id);setEvidence(null);});}}><option value="">临时对话</option>{conversations.map(item=><option key={item.id} value={item.id}>{item.title||"未命名对话"} · {item.message_count} 条</option>)}</select></label><div className="detail-buttons"><button className="button button-secondary" disabled={busy} onClick={()=>void request(async()=>{const created=await conversationApi.create(draft.trim()||"新的研究对话");setConversations(old=>[created,...old]);setConversationId(created.id);setMessages([]);setEvidence(null);})}>新建对话</button>{conversationId&&<button className="button button-secondary" disabled={busy} onClick={()=>{if(window.confirm("删除当前账户的这段对话及其消息？"))void request(async()=>{await conversationApi.remove(conversationId);setConversations(old=>old.filter(item=>item.id!==conversationId));setConversationId("");setMessages([]);});}}>删除对话</button>}</div><p>{conversationId?"此对话的问答会随账户保存。":"临时对话不会自动加入对话记录。"}</p></>:<p><Link to={loginUrl}>登录账户</Link>后可保存和继续对话。</p>}</section>
        <div id="assistant-panel-api" hidden={tool!=="api"}>{user&&DATA_SOURCE==="api"?<PersonalAiSettings key={user.id} userId={user.id} value={personal} onChange={setPersonal} disabled={busy}/>:<section className="account-panel assistant-config-note"><p>{demoMode?"演示模式仅展示界面，切换 API 数据源后可连接模型。":"登录后，使用自己的 API 生成回答。"}</p>{!demoMode&&<Link to={loginUrl}>登录后配置 <ArrowRight size={14}/></Link>}</section>}</div>
        {!demoMode&&user&&availability.status==="checking"&&<p className="assistant-availability" role="status">正在检查问答服务…</p>}
        {!demoMode&&!personal&&availability.status!=="checking"&&availability.status!=="ready"&&<p className="assistant-availability" role={availability.status==="unavailable"?"alert":"status"}>{availabilityReason}</p>}
        </div>
      </aside>
    </div>
  </div>;
}
