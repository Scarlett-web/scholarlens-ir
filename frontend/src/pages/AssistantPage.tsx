import {useEffect,useRef,useState} from "react";
import {Link,useSearchParams} from "react-router-dom";
import {ArrowRight,BookOpen,CheckCircle2,RotateCcw,Send,Square,Workflow,TriangleAlert} from "lucide-react";
import {PageHeading} from "../components/Layout";
import {askAi,conversationApi,getAssistantAvailability,retrieveEvidence} from "../services/ai";
import type {AgentTrace,AiMessage,AiOperation,Conversation,Evidence} from "../services/ai";
import {useStudio} from "../App";
import {useAuth} from "../services/AuthContext";
import {DATA_SOURCE,getPaper} from "../services/papers";
import {PersonalAiSettings} from "../components/PersonalAiSettings";
import {loadPersonalAi} from "../services/personalAi";

const EXAMPLES=["magnetic resonance imaging","protein structure","quantum theory"];
function ExecutionTrace({trace}:{trace:AgentTrace}){
  const statusLabel={done:"完成",running:"进行中",queued:"待执行",empty:"无结果",skipped:"跳过",error:"未完成"};
  return <details className="agent-trace"><summary><Workflow size={14}/>执行记录<span>{trace.evidence_count} 条证据{trace.elapsed_ms!==undefined?" · "+(trace.elapsed_ms/1000).toFixed(1)+" 秒":""}</span></summary><ol>{trace.steps.map(step=><li key={step.id} data-status={step.status}><span>{step.status==="done"?<CheckCircle2 size={14}/>:step.status==="error"?<TriangleAlert size={14}/>:<span className="agent-step-dot"/>}</span><span>{step.label}{step.result_count!==undefined?" · "+step.result_count+" 项":""}</span><small>{statusLabel[step.status]}{step.elapsed_ms!==undefined?" · "+(step.elapsed_ms/1000).toFixed(1)+"s":""}</small></li>)}</ol>{trace.warnings?.map((warning,index)=><p className="agent-warning" key={index}>{warning}</p>)}</details>;
}
export function AssistantPage(){
  const [params]=useSearchParams(),focusedPaper=params.get("paper")||"";
  const {favorites}=useStudio(),{user}=useAuth();
  const [personal,setPersonal]=useState(()=>user?loadPersonalAi(user.id):null);
  const [draft,setDraft]=useState(""),[messages,setMessages]=useState<AiMessage[]>([]),[evidence,setEvidence]=useState<Evidence[]|null>(null);
  const [evidenceTrace,setEvidenceTrace]=useState<AgentTrace|undefined>();
  const [busy,setBusy]=useState(false),[error,setError]=useState("");
  const [availability,setAvailability]=useState({status:"checking",reason:"正在检查问答服务…"});
  const [operation,setOperation]=useState<AiOperation>("ask"),[selected,setSelected]=useState<string[]>(focusedPaper&&!focusedPaper.startsWith("demo-")?[focusedPaper]:[]),[focusTitle,setFocusTitle]=useState("");
  const [conversations,setConversations]=useState<Conversation[]>([]),[conversationId,setConversationId]=useState("");
  const controller=useRef<AbortController|null>(null),bottom=useRef<HTMLDivElement|null>(null),input=useRef<HTMLTextAreaElement|null>(null),conversation=useRef<HTMLDivElement|null>(null);
  const ready=DATA_SOURCE==="api"&&(Boolean(personal)||["ready","dependency_unavailable"].includes(availability.status));
  const candidates=favorites.filter(item=>!item.paper.paper_id.startsWith("demo-")).map(item=>item.paper);
  const operationValid=operation==="ask"||operation==="summarize"&&selected.length===1||operation==="compare"&&selected.length>=2&&selected.length<=10;
  useEffect(()=>{
    if(DATA_SOURCE!=="api"){setAvailability({status:"not_configured",reason:"演示模式未连接问答服务"});return;}
    let active=true;getAssistantAvailability().then(data=>{if(active)setAvailability(data.modules.ai_qa);}).catch(cause=>{if(active)setAvailability({status:"unavailable",reason:cause.message});});return()=>{active=false;};
  },[]);
  useEffect(()=>{let active=true;if(focusedPaper)void getPaper(focusedPaper).then(paper=>{if(active)setFocusTitle(paper?.title||"论文暂不可访问");}).catch(()=>{if(active)setFocusTitle("论文暂不可访问");});return()=>{active=false;};},[focusedPaper]);
  useEffect(()=>{let active=true;if(user)conversationApi.list().then(data=>{if(active)setConversations(data);}).catch(cause=>{if(active)setError(cause.message);});return()=>{active=false;};},[user]);
  useEffect(()=>{if(messages.length)bottom.current?.scrollIntoView({behavior:window.matchMedia("(prefers-reduced-motion: reduce)").matches?"auto":"smooth",block:"nearest"});},[messages]);
  useEffect(()=>{if(evidence!==null)conversation.current?.scrollTo({top:0,behavior:"instant"});},[evidence]);
  useEffect(()=>()=>controller.current?.abort(),[]);
  const request=async(action:(signal:AbortSignal)=>Promise<void>)=>{
    if(busy)return;const abort=new AbortController();controller.current=abort;setBusy(true);setError("");
    try{await action(abort.signal);}catch(cause){if(!abort.signal.aborted)setError(cause instanceof Error?cause.message:"请求失败");}
    finally{if(controller.current===abort){controller.current=null;setBusy(false);}}
  };
  const submit=()=>{
    const question=draft.trim()||(operation==="summarize"?"总结这篇论文的研究问题、方法、结果与局限。":operation==="compare"?"逐篇比较所选论文的方法、结论和局限，并列出证据。":"");
    if(!ready||!operationValid||!question)return;
    void request(async signal=>{const reply=await askAi({question,paperIds:selected,operation,conversationId,personal},signal);if(signal.aborted)return;setEvidence(null);setEvidenceTrace(undefined);setMessages(old=>[...old,{role:"user",content:question},reply]);setDraft("");if(user)setConversations(await conversationApi.list());});
  };
  const findEvidence=()=>{if(!draft.trim()||DATA_SOURCE!=="api")return;void request(async signal=>{const result=await retrieveEvidence(draft.trim(),selected,signal);if(!signal.aborted){setEvidence(result.evidence);setEvidenceTrace(result.agent);}});};
  const reset=()=>{controller.current?.abort();controller.current=null;setBusy(false);setError("");setMessages([]);setEvidence(null);setEvidenceTrace(undefined);setDraft("");setConversationId("");};
  useEffect(()=>{reset();setConversations([]);setPersonal(user?loadPersonalAi(user.id):null);},[user?.id]);
  const loginUrl="/account?"+new URLSearchParams({next:"/assistant"+(focusedPaper?"?paper="+encodeURIComponent(focusedPaper):"")});
  return <div className="workspace-page content-wrap ai-page">
    <PageHeading eyebrow="研究工具" title="证据助手" desc="先核对论文原文，再生成带来源的研究回答。"/>
    <div className="assistant-workspace">
      <div className="ai-shell">
        <div className="ai-shell-header"><div className="ai-shell-title"><Workflow size={20}/><strong>{ready?"研究证据台":"原文证据检索"}</strong><span className="agent-status">{personal?"个人 API 已填写":ready?"回答模式可用":"无需配置即可检索"}</span></div><button className="button button-secondary" onClick={reset} disabled={busy||!messages.length&&evidence===null&&!draft&&!error&&!conversationId}><RotateCcw size={16}/>清空当前内容</button></div>
        <div ref={conversation} className="ai-conversation" aria-live="polite">
          {!messages.length&&evidence===null&&<div className="ai-welcome"><h2>{ready?"从一个具体问题开始":"先找到能回答问题的原文"}</h2><p>{ready?"Agent 会先找证据，再生成回答并检查引用。":"输入关键词，查看论文中的相关片段。此功能无需配置 AI。"}</p><div className="agent-capability-row"><span><CheckCircle2 size={14}/>检索</span><span><CheckCircle2 size={14}/>核对</span><span><CheckCircle2 size={14}/>引用</span></div><div className="ai-starters" aria-label="原文检索示例">{EXAMPLES.map(question=><button key={question} disabled={busy} onClick={()=>{setDraft(question);input.current?.focus();}}>{question}<ArrowRight size={14}/></button>)}</div></div>}
          {messages.map((message,index)=><div key={index} className={"ai-chat-message "+(message.role==="user"?"from-user":"from-assistant")}><div className="ai-chat-label">{message.role==="user"?"你的问题":"研究回答"}</div><p>{message.content}</p>{message.role==="assistant"&&message.agent&&<ExecutionTrace trace={message.agent}/ >}{Boolean(message.sources?.length)&&<div className="ai-chat-citations"><strong>{message.sourceLabel||"引用来源"}</strong>{message.sources?.map((source,i)=><Link key={source.chunk_id||source.paper_id+i} to={"/paper/"+encodeURIComponent(source.paper_id)}><BookOpen size={15}/><span>{source.title}{source.excerpt&&<small>{source.excerpt}</small>}{source.locator&&<small>{source.locator}</small>}</span><ArrowRight size={15}/></Link>)}</div>}</div>)}
          {evidence!==null&&<section className="evidence-results"><div className="evidence-results-heading"><h2>原文证据</h2><span>{evidence.length} 条相关片段</span></div>{evidenceTrace&&<ExecutionTrace trace={evidenceTrace}/ >}{!evidence.length&&<p>没有找到相关片段。试试更短的关键词，或扩大右侧论文范围。</p>}{evidence.map(item=><article className="evidence-result" key={item.chunk_id}><Link to={"/paper/"+encodeURIComponent(item.paper_id)}><strong>{item.paper_title}</strong><ArrowRight size={14}/></Link><p>{item.quote}</p><small>{item.locator}</small></article>)}</section>}
          {busy&&<p className="ai-request-status" role="status">{ready?"正在处理，请稍候…":"正在检索原文…"}</p>}<div ref={bottom}/>
        </div>
        <div className="ai-compose">{error&&<div className="inline-error" role="alert">{error}</div>}<form onSubmit={event=>{event.preventDefault();if(ready)submit();else findEvidence();}}>
          <textarea ref={input} value={draft} rows={3} maxLength={2000} onChange={event=>setDraft(event.target.value)} placeholder={ready?"输入研究问题…":"输入原文关键词，例如 magnetic resonance imaging…"} aria-label="研究问题" disabled={busy}/>
          <div className="ai-compose-footer"><span>{selected.length?"限定 "+selected.length+" 篇论文":"范围：全部论文"}</span><div className="detail-buttons">{busy?<button type="button" className="button button-secondary" onClick={()=>{controller.current?.abort();controller.current=null;setBusy(false);setError("已停止本次请求");}}><Square size={15}/>停止</button>:<>{ready&&<button type="button" className="button button-secondary" disabled={!draft.trim()||DATA_SOURCE!=="api"} onClick={findEvidence}>只查原文</button>}<button type="submit" className="button button-primary" disabled={DATA_SOURCE!=="api"||(ready?(!operationValid||operation==="ask"&&!draft.trim()):!draft.trim())}>{ready?<Send size={15}/>:<BookOpen size={15}/>} {ready?(operation==="ask"?"发送问题":operation==="summarize"?"生成总结":"比较论文"):"检索原文"}</button></>}</div></div>
        </form>{ready&&!operationValid&&<p className="field-help" role="status">{operation==="summarize"?"请在右侧选择 1 篇论文。":"请在右侧选择 2 至 10 篇论文。"}</p>}</div>
      </div>
      <aside className="assistant-sidebar" aria-label="论文助手设置">
        <section className="account-panel assistant-controls"><h2>阅读方式</h2><div className="assistant-mode-options" role="group" aria-label="研究方式">{([['ask','论文问答'],['summarize','单篇总结'],['compare','多篇比较']] as const).map(([value,label])=><button key={value} aria-pressed={operation===value} disabled={busy||!ready&&value!=="ask"} title={!ready&&value!=="ask"?"配置个人 API 后使用":undefined} onClick={()=>setOperation(value)}>{label}</button>)}</div>{!ready&&<p>总结与比较需先配置个人 API。</p>}
          <details open={operation!=="ask"}><summary>论文范围 <span>{selected.length?selected.length+" 篇":"全部"}</span></summary><p>{operation==="compare"?"选择 2 至 10 篇论文。":operation==="summarize"?"选择 1 篇论文。":"从收藏中选择论文，或保持全库检索。"}</p><div className="assistant-paper-options">{focusedPaper&&!candidates.some(p=>p.paper_id===focusedPaper)&&<label><input type="checkbox" checked={selected.includes(focusedPaper)} disabled={busy||focusedPaper.startsWith("demo-")} onChange={event=>setSelected(event.target.checked?[...selected,focusedPaper]:selected.filter(id=>id!==focusedPaper))}/>{focusTitle||"正在读取指定论文…"}</label>}{candidates.map(paper=><label key={paper.paper_id}><input type="checkbox" checked={selected.includes(paper.paper_id)} disabled={busy||!selected.includes(paper.paper_id)&&selected.length>=10} onChange={event=>setSelected(event.target.checked?[...selected,paper.paper_id]:selected.filter(id=>id!==paper.paper_id))}/>{paper.title}</label>)}</div>{!candidates.length&&!focusedPaper&&<Link to="/search">检索并收藏论文 <ArrowRight size={14}/></Link>}</details>
        </section>
        <section className="account-panel assistant-conversations"><h2>对话记录</h2>{user?<><label>当前对话<select aria-label="研究对话" value={conversationId} disabled={busy} onChange={event=>{const id=event.target.value;void request(async()=>{setMessages(id?await conversationApi.messages(id):[]);setConversationId(id);setEvidence(null);});}}><option value="">临时对话</option>{conversations.map(item=><option key={item.id} value={item.id}>{item.title||"未命名对话"} · {item.message_count} 条</option>)}</select></label><div className="detail-buttons"><button className="button button-secondary" disabled={busy} onClick={()=>void request(async()=>{const created=await conversationApi.create(draft.trim()||"新的研究对话");setConversations(old=>[created,...old]);setConversationId(created.id);setMessages([]);setEvidence(null);})}>新建对话</button>{conversationId&&<button className="button button-secondary" disabled={busy} onClick={()=>{if(window.confirm("删除当前账户的这段对话及其消息？"))void request(async()=>{await conversationApi.remove(conversationId);setConversations(old=>old.filter(item=>item.id!==conversationId));setConversationId("");setMessages([]);});}}>删除对话</button>}</div><p>{conversationId?"此对话的问答会随账户保存。":"临时对话不会自动加入对话记录。"}</p></>:<p><Link to={loginUrl}>登录账户</Link>后可保存和继续对话。</p>}</section>
        {user&&DATA_SOURCE==="api"?<PersonalAiSettings key={user.id} userId={user.id} value={personal} onChange={setPersonal} disabled={busy}/>:<section className="account-panel assistant-config-note"><h2>Agent 回答</h2><p>使用个人 API 生成回答，Agent 会把检索、证据和引用串成一条工作流。</p><Link to={loginUrl}>登录后配置 <ArrowRight size={14}/></Link></section>}
        {!ready&&user&&<p className="assistant-availability">{availability.status==="checking"?"正在检查问答服务…":"填写个人 API 后，可使用论文问答、总结与比较。"}</p>}
      </aside>
    </div>
  </div>;
}
