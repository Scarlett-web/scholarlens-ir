import {useEffect,useRef,useState} from "react";
import {Link,useSearchParams} from "react-router-dom";
import {ArrowRight,BookOpen,RotateCcw,Send,Sparkles,Square} from "lucide-react";
import {IntegrationNotice,PageHeading} from "../components/Layout";
import {askAi,conversationApi,getAssistantAvailability,retrieveEvidence} from "../services/ai";
import type {AiMessage,AiOperation,Conversation,Evidence} from "../services/ai";
import {useStudio} from "../App";
import {useAuth} from "../services/AuthContext";
import {DATA_SOURCE,getPaper} from "../services/papers";
import {PersonalAiSettings} from "../components/PersonalAiSettings";
import {loadPersonalAi} from "../services/personalAi";

const EXAMPLES=["这个研究方向有哪些核心问题？","帮我梳理不同方法的优缺点","哪些论文提供了可靠的实验依据？"];
export function AssistantPage(){
  const [params]=useSearchParams(),focusedPaper=params.get("paper")||"";
  const {favorites}=useStudio(),{user}=useAuth();
  const [personal,setPersonal]=useState(()=>user?loadPersonalAi(user.id):null);
  const [draft,setDraft]=useState(""),[messages,setMessages]=useState<AiMessage[]>([]),[evidence,setEvidence]=useState<Evidence[]|null>(null);
  const [busy,setBusy]=useState(false),[error,setError]=useState("");
  const [availability,setAvailability]=useState({status:"checking",reason:"正在检查问答服务…"});
  const [operation,setOperation]=useState<AiOperation>("ask"),[selected,setSelected]=useState<string[]>(focusedPaper&&!focusedPaper.startsWith("demo-")?[focusedPaper]:[]),[focusTitle,setFocusTitle]=useState("");
  const [conversations,setConversations]=useState<Conversation[]>([]),[conversationId,setConversationId]=useState("");
  const controller=useRef<AbortController|null>(null),bottom=useRef<HTMLDivElement|null>(null);
  const ready=DATA_SOURCE==="api"&&(Boolean(personal)||["ready","dependency_unavailable"].includes(availability.status));
  const candidates=favorites.filter(item=>!item.paper.paper_id.startsWith("demo-")).map(item=>item.paper);
  const operationValid=operation==="ask"||operation==="summarize"&&selected.length===1||operation==="compare"&&selected.length>=2&&selected.length<=10;
  useEffect(()=>{
    if(DATA_SOURCE!=="api"){setAvailability({status:"not_configured",reason:"演示模式未连接问答服务"});return;}
    let active=true;getAssistantAvailability().then(data=>{if(active)setAvailability(data.modules.ai_qa);}).catch(cause=>{if(active)setAvailability({status:"unavailable",reason:cause.message});});return()=>{active=false;};
  },[]);
  useEffect(()=>{let active=true;if(focusedPaper)void getPaper(focusedPaper).then(paper=>{if(active)setFocusTitle(paper?.title||"论文暂不可访问");}).catch(()=>{if(active)setFocusTitle("论文暂不可访问");});return()=>{active=false;};},[focusedPaper]);
  useEffect(()=>{let active=true;if(user)conversationApi.list().then(data=>{if(active)setConversations(data);}).catch(cause=>{if(active)setError(cause.message);});return()=>{active=false;};},[user]);
  useEffect(()=>{if(messages.length)bottom.current?.scrollIntoView({behavior:"smooth",block:"nearest"});},[messages]);
  useEffect(()=>()=>controller.current?.abort(),[]);
  const request=async(action:(signal:AbortSignal)=>Promise<void>)=>{
    if(busy)return;const abort=new AbortController();controller.current=abort;setBusy(true);setError("");
    try{await action(abort.signal);}catch(cause){if(!abort.signal.aborted)setError(cause instanceof Error?cause.message:"请求失败");}
    finally{if(controller.current===abort){controller.current=null;setBusy(false);}}
  };
  const submit=()=>{
    const question=draft.trim()||(operation==="summarize"?"总结这篇论文的研究问题、方法、结果与局限。":operation==="compare"?"逐篇比较所选论文的方法、结论和局限，并列出证据。":"");
    if(!ready||!operationValid||!question)return;
    void request(async signal=>{const reply=await askAi({question,paperIds:selected,operation,conversationId,personal},signal);if(signal.aborted)return;setMessages(old=>[...old,{role:"user",content:question},reply]);setDraft("");if(user)setConversations(await conversationApi.list());});
  };
  const reset=()=>{controller.current?.abort();controller.current=null;setBusy(false);setError("");setMessages([]);setEvidence(null);setDraft("");setConversationId("");};
  useEffect(()=>{reset();setConversations([]);setPersonal(user?loadPersonalAi(user.id):null);},[user?.id]);
  return <div className="workspace-page content-wrap ai-page">
    <PageHeading eyebrow="RESEARCH ASSISTANT" title="让阅读，多一个视角。" desc="查找真实原文证据，再提出值得深入的问题。"/>
    {!ready&&<IntegrationNotice title="AI 生成尚未启用" desc={availability.reason+"。原文证据检索可独立使用，不会生成模拟回答。"}/>}
    {user&&DATA_SOURCE==="api"?<PersonalAiSettings key={user.id} userId={user.id} value={personal} onChange={setPersonal} disabled={busy}/>:DATA_SOURCE==="api"&&<p><Link to="/account">登录</Link>后可填写自己的 API 地址、模型与密钥。</p>}
    <section className="account-panel assistant-controls">
      <div className="detail-buttons" role="group" aria-label="研究方式">{([['ask','论文问答'],['summarize','单篇总结'],['compare','多篇比较']] as const).map(([value,label])=><button key={value} aria-pressed={operation===value} className={"button "+(operation===value?"button-primary":"button-secondary")} disabled={busy} onClick={()=>setOperation(value)}>{label}</button>)}</div>
      <details open={operation!=="ask"}><summary>论文范围 · 已选 {selected.length} 篇</summary><p>{operation==="compare"?"选择2—10篇论文逐篇比较。":operation==="summarize"?"选择一篇论文生成总结。":"不选择时从全库检索；也可指定论文。"}可先收藏文献，再回到这里选择。</p>
        <div className="assistant-paper-options">{focusedPaper&&!candidates.some(p=>p.paper_id===focusedPaper)&&<label><input type="checkbox" checked={selected.includes(focusedPaper)} disabled={busy||focusedPaper.startsWith("demo-")} onChange={event=>setSelected(event.target.checked?[...selected,focusedPaper]:selected.filter(id=>id!==focusedPaper))}/>{focusTitle||"正在读取指定论文…"}</label>}{candidates.map(paper=><label key={paper.paper_id}><input type="checkbox" checked={selected.includes(paper.paper_id)} disabled={busy||!selected.includes(paper.paper_id)&&selected.length>=10} onChange={event=>setSelected(event.target.checked?[...selected,paper.paper_id]:selected.filter(id=>id!==paper.paper_id))}/>{paper.title}</label>)}</div>
        {!candidates.length&&!focusedPaper&&<Link to="/search">去检索并收藏论文 <ArrowRight size={14}/></Link>}
      </details>
      {user?<div className="assistant-session-row"><label>研究对话<select aria-label="研究对话" value={conversationId} disabled={busy} onChange={event=>{const id=event.target.value;void request(async()=>{setMessages(id?await conversationApi.messages(id):[]);setConversationId(id);setEvidence(null);});}}><option value="">临时对话</option>{conversations.map(item=><option key={item.id} value={item.id}>{item.title||"未命名对话"} · {item.message_count} 条消息</option>)}</select></label><button className="button button-secondary" disabled={busy} onClick={()=>void request(async()=>{const created=await conversationApi.create(draft.trim()||"新的研究对话");setConversations(old=>[created,...old]);setConversationId(created.id);setMessages([]);setEvidence(null);})}>保存新对话</button><button className="button button-secondary" disabled={busy||!conversationId} onClick={()=>{if(window.confirm("删除当前账户的这段对话及其消息？"))void request(async()=>{await conversationApi.remove(conversationId);setConversations(old=>old.filter(item=>item.id!==conversationId));setConversationId("");setMessages([]);});}}>删除对话</button></div>:<p><Link to="/account">登录</Link>后可以保存和继续研究对话。AI 未配置时仍可管理已有对话。</p>}
    </section>
    <div className="ai-shell">
      <div className="ai-shell-header"><div className="ai-shell-title"><div className="ai-shell-icon"><Sparkles size={22}/></div><div><strong>研究助手</strong><span>{personal?"使用当前账户的个人 API":ready?"使用服务器问答服务":"原文检索可用 · AI 待配置"}</span></div></div><button className="button button-secondary" onClick={reset} disabled={busy||!messages.length&&!draft&&!error&&!conversationId}><RotateCcw size={16}/>新对话</button></div>
      <div className="ai-conversation" aria-live="polite">
        {!messages.length&&<div className="ai-welcome"><div className="ai-welcome-mark"><Sparkles size={33}/></div><h2>你想从哪一个问题开始？</h2><p>先检索相关片段，每条证据都能回到论文。</p><div className="ai-starters">{EXAMPLES.map(question=><button key={question} disabled={busy} onClick={()=>setDraft(question)}>{question}<ArrowRight size={14}/></button>)}</div></div>}
        {messages.map((message,index)=><div key={index} className={"ai-chat-message "+(message.role==="user"?"from-user":"from-assistant")}><div className="ai-chat-label">{message.role==="user"?"你的问题":"研究回答"}</div><p>{message.content}</p>{Boolean(message.sources?.length)&&<div className="ai-chat-citations"><strong>引用来源</strong>{message.sources?.map((source,i)=><Link key={source.chunk_id||source.paper_id+i} to={"/paper/"+encodeURIComponent(source.paper_id)}><BookOpen size={15}/><span>{source.title}{source.excerpt&&<small>{source.excerpt}</small>}{source.locator&&<small>{source.locator}</small>}</span><ArrowRight size={15}/></Link>)}</div>}</div>)}
        {busy&&<p className="ai-request-status" role="status">正在处理请求…</p>}<div ref={bottom}/>
      </div>
      <div className="ai-compose">{error&&<div className="inline-error" role="alert">{error}</div>}<form onSubmit={event=>{event.preventDefault();submit();}}><textarea value={draft} rows={2} maxLength={2000} onChange={event=>setDraft(event.target.value)} placeholder="输入研究问题或原文关键词…" aria-label="研究问题"/><div className="ai-compose-footer"><span>{ready?"生成内容需核验原文":"AI 未配置 · 可先查原文"}</span><div className="detail-buttons">{busy?<button type="button" className="button button-secondary" onClick={()=>{controller.current?.abort();controller.current=null;setBusy(false);setError("已停止本次请求");}}><Square size={15}/>停止</button>:<><button type="button" className="button button-secondary" disabled={!draft.trim()||DATA_SOURCE!=="api"} onClick={()=>void request(async signal=>{const rows=await retrieveEvidence(draft.trim(),selected,signal);if(!signal.aborted)setEvidence(rows);})}><BookOpen size={15}/>检索原文证据</button><button className="button button-primary" disabled={!ready||!operationValid||operation==="ask"&&!draft.trim()}><Send size={15}/>{operation==="ask"?"发送问题":operation==="summarize"?"生成总结":"比较论文"}</button></>}</div></div></form></div>
    </div>
    {evidence!==null&&<section className="account-panel evidence-results"><h2>原文证据 · {evidence.length}</h2>{!evidence.length&&<p>没有找到足够相关的片段，请调整关键词或论文范围。</p>}{evidence.map(item=><article className="server-upload-row" key={item.chunk_id}><Link to={"/paper/"+encodeURIComponent(item.paper_id)}><strong>{item.paper_title}</strong></Link><p>{item.quote}</p><small>{item.locator}</small></article>)}</section>}
    <div className="ai-reading-note"><BookOpen size={20}/><div><strong>好的问题，往往始于阅读。</strong><p>先打开一篇论文，再带着问题回到这里。</p></div><Link to="/search">去找一篇论文 <ArrowRight size={16}/></Link></div>
  </div>;
}
