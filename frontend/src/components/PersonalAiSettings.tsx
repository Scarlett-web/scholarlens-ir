import {useEffect,useRef,useState} from "react";
import {Check,Loader2,PlugZap} from "lucide-react";
import {clearPersonalAi,personalAiPreferences,readPersonalModels,savePersonalAi,testPersonalConnection} from "../services/personalAi";
import type {PersonalAi} from "../services/personalAi";

export function PersonalAiSettings({userId,value,onChange,disabled}:{userId:number;value:PersonalAi|null;onChange(value:PersonalAi|null):void;disabled:boolean}){
  const [draft,setDraft]=useState(()=>personalAiPreferences(userId));
  const [message,setMessage]=useState(""),[error,setError]=useState("");
  const [models,setModels]=useState<string[]>([]),[pending,setPending]=useState<"models"|"test"|null>(null);
  const controller=useRef<AbortController|null>(null);
  useEffect(()=>()=>controller.current?.abort(),[]);
  const locked=disabled||Boolean(pending);
  const update=(patch:Partial<PersonalAi>)=>{setDraft(old=>({...old,...patch}));setMessage("");setError("");if(patch.url!==undefined||patch.key!==undefined)setModels([]);};
  const check=async(kind:"models"|"test")=>{
    if(controller.current)return;
    const abort=new AbortController();controller.current=abort;setPending(kind);setMessage("");setError("");
    try{
      if(kind==="models"){
        const result=await readPersonalModels(draft,abort.signal);setModels(result.models);
        setMessage(result.models.length?`已读取 ${result.models.length} 个模型，请选择或手动填写。读取列表尚未验证模型生成。`:"接口没有返回模型名称，请手动填写。");
      }else{
        const result=await testPersonalConnection(draft,abort.signal);
        setMessage(`连接成功：${result.model} 已实际返回文字。保存后用于问答。`);
      }
    }catch(cause){if(!abort.signal.aborted)setError(cause instanceof Error?cause.message:"连接失败");}
    finally{if(controller.current===abort){controller.current=null;setPending(null);}}
  };
  return <section className="personal-ai-settings" aria-label="个人 API 设置">
    <p className="assistant-panel-intro">连接你自己的模型服务。当前{value?"已保存配置":"尚未配置"}，其他账户不会共享。</p>
    <form className="account-form" onSubmit={event=>{event.preventDefault();try{const saved=savePersonalAi(userId,draft);onChange(saved);setDraft(saved);setError("");setMessage("配置已保存。可先测试连接，或直接开始对话。");}catch(cause){setError(cause instanceof Error?cause.message:"配置保存失败");}}}>
      <label>API Base URL<input type="url" autoComplete="off" required aria-label="个人API地址" value={draft.url} placeholder="https://你的服务地址/v1" maxLength={2048} disabled={locked} onChange={event=>update({url:event.target.value})}/></label>
      <label>API 密钥<input type="password" autoComplete="off" required aria-label="个人API密钥" value={draft.key} maxLength={2048} spellCheck={false} disabled={locked} onChange={event=>update({key:event.target.value})}/></label>
      <label>接口协议<select aria-label="个人API协议" value={draft.protocol||"chat_completions"} disabled={locked} onChange={event=>update({protocol:event.target.value as PersonalAi["protocol"]})}><option value="chat_completions">Chat Completions</option><option value="responses">Responses</option></select></label>
      <div className="personal-ai-model-heading"><label htmlFor="personal-ai-model">模型名称</label><button type="button" className="text-action" disabled={locked||!draft.url.trim()||!draft.key.trim()} onClick={()=>void check("models")}>{pending==="models"?<Loader2 size={14} className="assistant-spinner"/>:null}读取模型列表</button></div>
      <input id="personal-ai-model" list="personal-ai-model-list" autoComplete="off" required aria-label="个人API模型" value={draft.model} placeholder="选择列表中的模型，或手动填写" maxLength={200} disabled={locked} onChange={event=>update({model:event.target.value})}/>
      <datalist id="personal-ai-model-list">{models.map(model=><option key={model} value={model}/>)}</datalist>
      {models.length>0&&<label>可用模型<select aria-label="选择可用模型" disabled={locked} value={models.includes(draft.model)?draft.model:""} onChange={event=>update({model:event.target.value})}><option value="" disabled>请选择一个模型</option>{models.map(model=><option key={model} value={model}>{model}</option>)}</select></label>}
      {draft.protocol!=="responses"&&<details className="personal-ai-advanced"><summary>兼容选项</summary><label>Token 参数<select aria-label="个人API令牌参数" value={draft.tokenParameter} disabled={locked} onChange={event=>update({tokenParameter:event.target.value as PersonalAi["tokenParameter"]})}><option value="max_completion_tokens">max_completion_tokens</option><option value="max_tokens">max_tokens</option></select></label></details>}
      <div className="personal-ai-actions"><button type="button" className="button button-secondary" disabled={locked||!draft.url.trim()||!draft.key.trim()||!draft.model.trim()} onClick={()=>void check("test")}>{pending==="test"?<Loader2 size={15} className="assistant-spinner"/>:<PlugZap size={15}/>}测试连接</button><button className="button button-primary" disabled={locked}><Check size={15}/>保存个人配置</button></div>
      <p className="field-help">测试会发送一次简短请求，可能消耗少量 API 额度。URL 和模型保存在此浏览器；密钥仅在此标签页保存，退出后清除。</p>
      {message&&<p role="status" className="personal-ai-feedback">{message}</p>}{error&&<p role="alert" className="inline-error">{error}</p>}
      <button type="button" className="text-action personal-ai-clear" disabled={locked} onClick={()=>{clearPersonalAi(userId);onChange(null);setDraft(personalAiPreferences(userId));setModels([]);setMessage("个人配置已清除");setError("");}}>清除个人配置</button>
    </form>
  </section>;
}
