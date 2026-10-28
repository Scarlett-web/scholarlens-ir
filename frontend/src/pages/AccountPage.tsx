import {PasswordRecovery} from "../components/PasswordRecovery";
import {AccountSettings} from "../components/AccountSettings";
import {useEffect,useState} from "react";
import {Link,useNavigate,useSearchParams} from "react-router-dom";
import {ArrowRight,BookOpen,Eye,EyeOff,FolderOpen,StickyNote} from "lucide-react";
import {useAuth} from "../services/AuthContext";
import {accountApi} from "../services/backend";
import type {QueryHistory} from "../services/backend";
import {PageHeading} from "../components/Layout";
import {useStudio} from "../App";
import {DATA_SOURCE} from "../services/papers";

export function AccountPage(){
  const {user,loading,login,logout,error:authError}=useAuth();
  const {workspaceError,workspaceReady,workspaceSyncing}=useStudio();
  const navigate=useNavigate(),[params]=useSearchParams();
  const [register,setRegister]=useState(false),[username,setUsername]=useState(""),[password,setPassword]=useState("");
  const [showPassword,setShowPassword]=useState(false),[capsLock,setCapsLock]=useState(false);
  const [busy,setBusy]=useState(false),[error,setError]=useState(""),[queries,setQueries]=useState<QueryHistory[]>([]),[page,setPage]=useState(1),[total,setTotal]=useState(0);
  useEffect(()=>{
    if(!user)return;
    let active=true;
    accountApi.history(page).then(data=>{if(active){setQueries(data.results);setTotal(data.total);}}).catch(cause=>{if(active)setError(cause instanceof Error?cause.message:"历史加载失败");});
    return()=>{active=false;};
  },[user,page]);
  const switchMode=(value:boolean)=>{setRegister(value);setError("");setPassword("");setShowPassword(false);setCapsLock(false);};
  const submit=async()=>{
    if(busy)return;
    setBusy(true);setError("");
    try{
      await login(username.trim(),password,register);setPassword("");setShowPassword(false);
      const next=params.get("next");
      if(next&&/^\/(?:assistant|library|upload|admin|search|paper)(?:[/?#]|$)/.test(next)&&!next.includes("\\"))navigate(next,{replace:true});
    }catch(cause){setError(cause instanceof Error?cause.message:"登录失败，请重试");}
    finally{setBusy(false);}
  };
  if(loading)return <div className="workspace-page content-wrap account-page"><div className="account-panel account-loading" role="status">正在检查登录状态…</div></div>;
  return <div className={"workspace-page content-wrap account-page"+(!user?" account-login-page":"")}>
    {!user?<div className="auth-surface">
      <aside className="auth-intro">
        <Link to="/" className="auth-wordmark"><BookOpen size={24} strokeWidth={1.6}/>ScholarLens</Link>
        <div><h2>留住每一次阅读。</h2><p>登录后，在不同设备上继续整理你的文献。</p>
          <ul className="auth-benefits">
            <li><FolderOpen size={18}/><span><strong>收藏与分类</strong><small>把值得读的论文整理在一起</small></span></li>
            <li><StickyNote size={18}/><span><strong>阅读笔记</strong><small>记录想法，下次打开接着写</small></span></li>
            <li><BookOpen size={18}/><span><strong>最近阅读</strong><small>回到上次读过的那篇论文</small></span></li>
          </ul>
        </div>
        <Link to="/search" className="auth-guest-link">先以游客身份浏览 <ArrowRight size={16}/></Link>
      </aside>
      <section className="account-panel auth-card" aria-labelledby="account-entry-title">
        <header><h1 id="account-entry-title">{register?"创建账户":"欢迎回来"}</h1><p>{register?"创建你的文献与笔记空间。":"登录你的研究账户，继续阅读。"}</p></header>
        <div className="segmented" role="group" aria-label="账户操作"><button type="button" disabled={busy} aria-pressed={!register} className={!register?"selected":""} onClick={()=>switchMode(false)}>登录</button><button type="button" disabled={busy} aria-pressed={register} className={register?"selected":""} onClick={()=>switchMode(true)}>创建账户</button></div>
        <form onSubmit={event=>{event.preventDefault();void submit();}} className="account-form" aria-busy={busy}>
          {(error||authError)&&<div className="inline-error" role="alert">{error||authError}</div>}
          <label htmlFor="account-username">用户名<input id="account-username" name="username" autoComplete="username" required minLength={3} maxLength={64} pattern="[a-zA-Z0-9_.\-]+" disabled={busy} value={username} onChange={event=>setUsername(event.target.value)} placeholder="输入用户名" aria-describedby={register?"username-help":undefined}/></label>
          {register&&<p className="field-help" id="username-help">3 至 64 位，可使用字母、数字、点、下划线和短横线。</p>}
          <div className="auth-password-field"><label htmlFor="account-password">密码</label><div className="password-control"><input id="account-password" name="password" type={showPassword?"text":"password"} autoComplete={register?"new-password":"current-password"} required minLength={10} maxLength={128} disabled={busy} value={password} onChange={event=>setPassword(event.target.value)} onKeyUp={event=>setCapsLock(event.getModifierState("CapsLock"))} onBlur={()=>setCapsLock(false)} placeholder={register?"设置至少 10 位密码":"输入密码"}/><button type="button" disabled={busy} aria-label={showPassword?"隐藏密码":"显示密码"} aria-pressed={showPassword} onClick={()=>setShowPassword(value=>!value)}>{showPassword?<EyeOff size={18}/>:<Eye size={18}/>}</button></div></div>
          {capsLock&&<p className="field-help" role="status">大写锁定已开启</p>}
          <button type="submit" className="button button-primary auth-submit" disabled={busy||DATA_SOURCE==="demo"}>{busy?(register?"正在创建账户…":"正在登录…"):register?"创建并登录":"登录"}<ArrowRight size={16}/></button>
        </form>
        <PasswordRecovery/>
        {DATA_SOURCE==="demo"&&<p role="status">演示模式未连接账户服务。</p>}
        <p className="auth-data-note">游客收藏和笔记会保留，不会自动并入账户。</p>
      </section>
    </div>:<>
      <PageHeading eyebrow="账户" title="你的研究账户" desc="管理个人资料、阅读记录与账户设置。"/>
      {authError&&<div className="inline-error" role="alert">{authError}</div>}{error&&<div className="inline-error" role="alert">{error}</div>}
      <section className="account-panel account-overview"><div className="account-identity"><span className="account-monogram" aria-hidden="true">{user.username.slice(0,1).toUpperCase()}</span><div><h2>{user.username}</h2><p>{user.role==="admin"?"管理员":"研究账户"} · <span role="status">{workspaceSyncing?"正在保存…":workspaceReady&&!workspaceError?"阅读空间已连接":"正在读取阅读空间"}</span></p></div></div>
        {workspaceError&&<div className="inline-error" role="alert">{workspaceError}。未保存的草稿保留在本机，可先导出备份。<button className="button button-secondary" onClick={()=>window.location.reload()}>重新加载</button></div>}
        <div className="detail-buttons"><Link className="button button-primary" to="/library">我的文献 <ArrowRight size={16}/></Link><Link className="button button-secondary" to="/upload">上传论文</Link>{user.role==="admin"&&<Link className="button button-secondary" to="/admin">审核工作台</Link>}
        <button className="button button-secondary account-logout" disabled={busy||workspaceSyncing} onClick={async()=>{setBusy(true);try{await logout();setError("");}catch(cause){setError(cause instanceof Error?cause.message:"退出失败");}finally{setBusy(false);}}}>退出登录</button></div>
      </section>
      <AccountSettings/>
      <section className="account-panel account-search-history"><details><summary>搜索历史 <span>{total} 条</span></summary><div className="results-topbar"><p>点击关键词，可继续上次的检索。</p><button className="button button-secondary" disabled={!total||busy} onClick={async()=>{if(!window.confirm("清空当前账户的搜索历史？阅读历史和收藏不受影响。"))return;setBusy(true);try{await accountApi.clearHistory();setQueries([]);setTotal(0);setPage(1);}catch(cause){setError(cause instanceof Error?cause.message:"清空失败");}finally{setBusy(false);}}}>清空搜索历史</button></div>
        {queries.length?queries.map(item=><Link className="account-history-link" key={item.id} to={"/search?"+new URLSearchParams({q:item.q,field:item.field,mode:item.mode})}><strong>{item.q}</strong><span> {({keyword:"关键词",semantic:"语义",hybrid:"混合"} as Record<string,string>)[item.mode]||item.mode} · {new Date(item.created_at).toLocaleString("zh-CN")}</span></Link>):<p>还没有搜索记录。检索论文后会显示在这里。</p>}
        {total>20&&<nav className="pagination" aria-label="搜索历史分页"><button disabled={page<=1} onClick={()=>setPage(page-1)}>上一页</button><span>{page} / {Math.max(1,Math.ceil(total/20))}</span><button disabled={page*20>=total} onClick={()=>setPage(page+1)}>下一页</button></nav>}
      </details></section>
    </>}
  </div>;
}
