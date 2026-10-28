import {useState} from "react";
import {clearPersonalAi,personalAiPreferences,savePersonalAi} from "../services/personalAi";
import type {PersonalAi} from "../services/personalAi";

export function PersonalAiSettings({userId,value,onChange,disabled}:{userId:number;value:PersonalAi|null;onChange(value:PersonalAi|null):void;disabled:boolean}){
  const [draft,setDraft]=useState(()=>personalAiPreferences(userId)),[message,setMessage]=useState(""),[error,setError]=useState("");
  return <section className="account-panel personal-ai-settings"><details open={!value}><summary>个人 API 设置 · {value?"已填写":"未配置"}</summary>
    <p>使用你自己的 OpenAI 兼容接口。仅对当前账户与标签页生效，不影响其他人。URL 和模型保存在此浏览器；密钥仅在此标签页会话中保存，退出后清除。</p>
    <form className="account-form" onSubmit={event=>{event.preventDefault();try{const saved=savePersonalAi(userId,draft);onChange(saved);setDraft(saved);setError("");setMessage("个人配置已保存。可直接用自然语言提问；只有模型实际返回后才代表连接成功。");}catch(cause){setError(cause instanceof Error?cause.message:"配置保存失败");}}}>
      <label>API Base URL<input type="url" autoComplete="off" required aria-label="个人API地址" value={draft.url} placeholder="https://你的服务地址/v1" maxLength={2048} disabled={disabled} onChange={event=>setDraft({...draft,url:event.target.value})}/></label>
      <label>模型名称<input autoComplete="off" required aria-label="个人API模型" value={draft.model} maxLength={200} disabled={disabled} onChange={event=>setDraft({...draft,model:event.target.value})}/></label>
      <label>API 密钥<input type="password" autoComplete="off" required aria-label="个人API密钥" value={draft.key} maxLength={2048} spellCheck={false} disabled={disabled} onChange={event=>setDraft({...draft,key:event.target.value})}/></label>
      <label>Token 参数<select aria-label="个人API令牌参数" value={draft.tokenParameter} disabled={disabled} onChange={event=>setDraft({...draft,tokenParameter:event.target.value as PersonalAi["tokenParameter"]})}><option value="max_completion_tokens">max_completion_tokens</option><option value="max_tokens">max_tokens</option></select></label>
      <div className="detail-buttons"><button className="button button-primary" disabled={disabled}>保存个人配置</button><button type="button" className="button button-secondary" disabled={disabled} onClick={()=>{clearPersonalAi(userId);onChange(null);setDraft({url:"",model:"",key:"",tokenParameter:"max_completion_tokens"});setMessage("个人配置已清除");setError("");}}>清除个人配置</button></div>
      {message&&<p role="status">{message}</p>}{error&&<p role="alert" className="inline-error">{error}</p>}
    </form>
  </details></section>;
}
