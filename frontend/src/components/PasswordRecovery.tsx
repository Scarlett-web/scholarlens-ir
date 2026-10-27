import {useState} from "react";
import {backend} from "../services/backend";
import {DATA_SOURCE} from "../services/papers";

export function PasswordRecovery(){
  const [email,setEmail]=useState(""),[code,setCode]=useState(""),[password,setPassword]=useState("");
  const [busy,setBusy]=useState(false),[message,setMessage]=useState(""),[error,setError]=useState("");
  const run=async(reset:boolean)=>{
    setBusy(true);setError("");setMessage("");
    try{await backend("/auth/password-reset/"+(reset?"verify":"request"),{method:"POST",token:"",body:reset?{email,code,new_password:password}:{email}});setMessage(reset?"密码已重置，请使用新密码登录。":"请求已受理。若邮箱已验证且账户可用，请检查收件箱。");if(reset){setPassword("");setCode("");}}
    catch(cause){setError(cause instanceof Error?cause.message:"操作失败");}finally{setBusy(false);}
  };
  return <details className="password-recovery"><summary>忘记密码？</summary><form className="account-form" onSubmit={event=>{event.preventDefault();void run(true);}}><p>使用已经验证的邮箱找回。邮件服务尚未配置时，服务器会明确提示不可用。</p><label>邮箱<input type="email" autoComplete="email" required value={email} onChange={event=>setEmail(event.target.value)}/></label><button type="button" className="button button-secondary" disabled={busy||!email||DATA_SOURCE!=="api"} onClick={()=>void run(false)}>请求找回验证码</button><label>验证码<input required minLength={6} maxLength={12} autoComplete="one-time-code" value={code} onChange={event=>setCode(event.target.value)}/></label><label>新密码<input type="password" autoComplete="new-password" required minLength={10} maxLength={128} value={password} onChange={event=>setPassword(event.target.value)}/></label><button className="button button-primary" disabled={busy||DATA_SOURCE!=="api"}>重置密码</button>{message&&<p role="status">{message}</p>}{error&&<p className="inline-error" role="alert">{error}</p>}</form></details>;
}
