import {useEffect,useRef,useState} from "react";
import {Check,Loader2,PlugZap,Plus,Search,X} from "lucide-react";
import {clearPersonalAi,personalAiPreferences,personalModelIds,readPersonalModels,savePersonalAi,testPersonalConnection} from "../services/personalAi";
import type {PersonalAi} from "../services/personalAi";

export function PersonalAiSettings({userId,value,onChange,disabled}:{userId:number;value:PersonalAi|null;onChange(value:PersonalAi|null):void;disabled:boolean}){
  const [draft,setDraft]=useState(()=>personalAiPreferences(userId));
  const [message,setMessage]=useState(""),[error,setError]=useState("");
  const [models,setModels]=useState<string[]|null>(null),[pending,setPending]=useState<"models"|"test"|null>(null);
  const [filter,setFilter]=useState(""),[checked,setChecked]=useState<string[]>([]),[manual,setManual]=useState("");
  const controller=useRef<AbortController|null>(null);
  useEffect(()=>()=>controller.current?.abort(),[]);
  const locked=disabled||Boolean(pending);
  const preferred=personalModelIds(draft.preferredModels);
  const filtered=(models||[]).filter(model=>model.toLocaleLowerCase().includes(filter.trim().toLocaleLowerCase()));
  const update=(patch:Partial<PersonalAi>)=>{
    setDraft(old=>({...old,...patch,...(patch.url!==undefined&&patch.url!==old.url?{model:"",preferredModels:[]}:{} )}));
    setMessage("");setError("");
    if(patch.url!==undefined||patch.key!==undefined){setModels(null);setChecked([]);setFilter("");}
  };
  const addModels=(ids:string[])=>{
    const valid=personalModelIds(ids),next=personalModelIds([...preferred,...valid]);
    if(!valid.length){setError("请输入有效的模型名称，不要包含空格或中文。");return;}
    if(next.length===preferred.length){setMessage("这些模型已在可选列表中。");setError("");return;}
    const current=draft.model||valid[0];
    update({preferredModels:next,model:current});setChecked([]);setManual("");
    setMessage(`已加入 ${next.length-preferred.length} 个模型。${draft.model?"当前模型保持不变。":`当前选择：${current}。`}保存后用于对话。`);
  };
  const removeModel=(model:string)=>{
    update({preferredModels:preferred.filter(id=>id!==model),...(draft.model===model?{model:""}:{})});
    if(draft.model===model)setMessage("已移除当前模型，请重新选择后保存。");
  };
  const check=async(kind:"models"|"test")=>{
    if(controller.current)return;
    const abort=new AbortController();controller.current=abort;setPending(kind);setMessage("");setError("");
    if(kind==="models"){setModels(null);setChecked([]);setFilter("");}
    try{
      if(kind==="models"){
        const result=await readPersonalModels(draft,abort.signal);setModels(result.models);
        setMessage(result.models.length?`获取到 ${result.models.length} 个模型。勾选需要的模型，加入可选列表。`:"服务商没有返回模型名称，可以在下方手动添加。");
      }else{
        const result=await testPersonalConnection(draft,abort.signal);
        setMessage(`连接成功：${result.model} 已实际返回文字。保存后用于问答。`);
      }
    }catch(cause){if(!abort.signal.aborted)setError((cause instanceof Error?cause.message:"连接失败")+(kind==="models"?"。也可以手动添加模型。":""));}
    finally{if(controller.current===abort){controller.current=null;setPending(null);}}
  };
  return <section className="personal-ai-settings" aria-label="个人 API 设置">
    <p className="assistant-panel-intro">连接自己的模型服务。获取模型后按需添加，再选择一个用于对话。{value?"当前已保存配置。":""}</p>
    <form className="account-form" onSubmit={event=>{
      event.preventDefault();
      try{const saved=savePersonalAi(userId,draft);onChange(saved);setDraft(saved);setError("");setMessage("配置已保存，当前模型："+saved.model+"。");}
      catch(cause){setError(cause instanceof Error?cause.message:"配置保存失败");}
    }}>
      <label>API Base URL<input type="url" autoComplete="off" required aria-label="个人API地址" value={draft.url} placeholder="https://你的服务地址/v1" maxLength={2048} disabled={locked} onChange={event=>update({url:event.target.value})}/></label>
      <label>API 密钥<input type="password" autoComplete="off" required aria-label="个人API密钥" value={draft.key} maxLength={2048} spellCheck={false} disabled={locked} onChange={event=>update({key:event.target.value})}/></label>
      <label>接口协议<select aria-label="个人API协议" value={draft.protocol||"chat_completions"} disabled={locked} onChange={event=>update({protocol:event.target.value as PersonalAi["protocol"]})}><option value="chat_completions">Chat Completions</option><option value="responses">Responses</option></select></label>
      <div className="personal-ai-model-heading"><span>模型管理</span><button type="button" className="button button-secondary" disabled={locked||!draft.url.trim()||!draft.key.trim()} onClick={()=>void check("models")}>{pending==="models"?<Loader2 size={14} className="assistant-spinner"/>:<Plus size={14}/>} {pending==="models"?"正在获取…":"获取模型"}</button></div>
      {models!==null&&<div className="personal-ai-catalog" aria-label="获取到的模型">
        <div className="personal-ai-catalog-search"><Search size={15} aria-hidden="true"/><input type="search" aria-label="筛选服务商模型" placeholder="搜索模型名称" value={filter} disabled={locked} onChange={event=>setFilter(event.target.value)} onKeyDown={event=>{if(event.key==="Enter")event.preventDefault();}}/></div>
        <div className="personal-ai-catalog-heading"><span>显示 {filtered.length} / {models.length} 个</span><button type="button" className="text-action" disabled={locked||!filtered.some(id=>!preferred.includes(id))} onClick={()=>setChecked(old=>personalModelIds([...old,...filtered.filter(id=>!preferred.includes(id))]))}>选择筛选结果</button></div>
        <div className="personal-ai-catalog-list" role="group" aria-label="服务商模型">
          {filtered.map(model=><label className="personal-ai-catalog-option" key={model}>
            <input type="checkbox" aria-label={"添加 "+model} checked={preferred.includes(model)||checked.includes(model)} disabled={locked||preferred.includes(model)} onChange={event=>setChecked(old=>event.target.checked?[...old,model]:old.filter(id=>id!==model))}/>
            <span>{model}</span>{preferred.includes(model)&&<small>已添加</small>}
          </label>)}
          {!filtered.length&&<p className="field-help">{models.length?"没有匹配的模型，试试其他名称。":"列表为空，可以手动添加模型。"}</p>}
        </div>
        <div className="personal-ai-catalog-actions"><button type="button" className="button button-secondary" disabled={locked||!checked.length} onClick={()=>addModels(checked)}>加入可选模型{checked.length?"（"+checked.length+"）":""}</button>{checked.length>0&&<button type="button" className="text-action" disabled={locked} onClick={()=>setChecked([])}>清空待选</button>}</div>
      </div>}
      <label>当前模型<select id="personal-ai-model" required aria-label="个人API模型" value={draft.model} disabled={locked||!preferred.length} onChange={event=>update({model:event.target.value})}><option value="" disabled>选择用于对话的模型</option>{preferred.map(model=><option key={model} value={model}>{model}</option>)}</select></label>
      {preferred.length>0?<div className="personal-ai-shortlist" aria-label="我的可选模型">{preferred.map(model=><span className="personal-ai-model-chip" key={model}><span title={model}>{model}</span><button type="button" aria-label={"移除 "+model} disabled={locked} onClick={()=>removeModel(model)}><X size={12}/></button></span>)}</div>:<p className="field-help">还没有可选模型。点击“获取模型”，或在下方手动添加。</p>}
      <label htmlFor="personal-ai-manual">手动添加模型</label>
      <div className="personal-ai-manual"><input id="personal-ai-manual" aria-label="手动模型名称" value={manual} autoComplete="off" placeholder="服务商提供的模型名称" maxLength={200} spellCheck={false} disabled={locked} onChange={event=>setManual(event.target.value)} onKeyDown={event=>{if(event.key==="Enter"){event.preventDefault();if(manual.trim())addModels([manual.trim()]);}}}/><button type="button" className="button button-secondary" disabled={locked||!manual.trim()} onClick={()=>addModels([manual.trim()])}>添加</button></div>
      {draft.protocol!=="responses"&&<details className="personal-ai-advanced"><summary>兼容选项</summary><label>Token 参数<select aria-label="个人API令牌参数" value={draft.tokenParameter} disabled={locked} onChange={event=>update({tokenParameter:event.target.value as PersonalAi["tokenParameter"]})}><option value="max_completion_tokens">max_completion_tokens</option><option value="max_tokens">max_tokens</option></select></label></details>}
      <div className="personal-ai-actions"><button type="button" className="button button-secondary" disabled={locked||!draft.url.trim()||!draft.key.trim()||!draft.model.trim()} onClick={()=>void check("test")}>{pending==="test"?<Loader2 size={15} className="assistant-spinner"/>:<PlugZap size={15}/>}测试连接</button><button className="button button-primary" disabled={locked||!draft.model}><Check size={15}/>保存个人配置</button></div>
      <p className="field-help">获取列表不生成回答。测试连接会发送一次简短请求，可能消耗少量额度。模型列表与 URL 仅保存在此浏览器，按账户隔离；密钥仅在此标签页保存，退出后清除。</p>
      {message&&<p role="status" className="personal-ai-feedback">{message}</p>}{error&&<p role="alert" className="inline-error">{error}</p>}
      <button type="button" className="text-action personal-ai-clear" disabled={locked} onClick={()=>{clearPersonalAi(userId);onChange(null);setDraft(personalAiPreferences(userId));setModels(null);setChecked([]);setManual("");setFilter("");setMessage("个人配置已清除");setError("");}}>清除个人配置</button>
    </form>
  </section>;
}
