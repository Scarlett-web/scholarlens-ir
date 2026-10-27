import {PasswordRecovery} from "../components/PasswordRecovery";
import {AccountSettings} from "../components/AccountSettings";
import {useEffect,useState} from "react";
import {Link} from "react-router-dom";
import {useAuth} from "../services/AuthContext";
import {accountApi} from "../services/backend";
import type {QueryHistory} from "../services/backend";
import {PageHeading,IntegrationNotice} from "../components/Layout";
import {useStudio} from "../App";
import {DATA_SOURCE} from "../services/papers";

export function AccountPage(){
  const {user,login,logout,error:authError}=useAuth();
  const {workspaceError,workspaceReady,workspaceSyncing}=useStudio();
  const [register,setRegister]=useState(false),[username,setUsername]=useState(""),[password,setPassword]=useState("");
  const [busy,setBusy]=useState(false),[error,setError]=useState(""),[queries,setQueries]=useState<QueryHistory[]>([]),[page,setPage]=useState(1),[total,setTotal]=useState(0);
  useEffect(()=>{
    if(!user)return;
    let active=true;
    accountApi.history(page).then(data=>{if(active){setQueries(data.results);setTotal(data.total);}}).catch(cause=>{if(active)setError(cause instanceof Error?cause.message:"历史加载失败");});
    return()=>{active=false;};
  },[user,page]);
  const submit=async()=>{
    setBusy(true);setError("");
    try{await login(username.trim(),password,register);setPassword("");}
    catch(cause){setError(cause instanceof Error?cause.message:"登录失败");}
    finally{setBusy(false);}
  };
  return <div className="workspace-page content-wrap account-page">
    <PageHeading eyebrow="YOUR RESEARCH ACCOUNT" title={user?"你的研究账户":"登录研究空间"} desc="让收藏、笔记与阅读线索，跟随你的账户。"/>
    {authError&&<div className="inline-error" role="alert">{authError}</div>}
    {error&&<div className="inline-error" role="alert">{error}</div>}
    {!user?<section className="account-panel">
      <div className="segmented"><button aria-pressed={!register} className={!register?"selected":""} onClick={()=>setRegister(false)}>登录</button><button aria-pressed={register} className={register?"selected":""} onClick={()=>setRegister(true)}>创建账户</button></div>
      <form onSubmit={event=>{event.preventDefault();void submit();}} className="account-form">
        <label>用户名<input name="username" autoComplete="username" required minLength={3} maxLength={64} pattern="[a-zA-Z0-9_.\-]+" value={username} onChange={event=>setUsername(event.target.value)} placeholder="3—64位字母、数字、点、下划线或短横线"/></label>
        <label>密码<input name="password" type="password" autoComplete={register?"new-password":"current-password"} required minLength={10} maxLength={128} value={password} onChange={event=>setPassword(event.target.value)}/></label>
        <p>密码至少10位。游客收藏和笔记会保留，不会自动上传或覆盖账户数据。</p>
        <button className="button button-primary" disabled={busy||DATA_SOURCE==="demo"}>{busy?"正在处理…":register?"注册并登录":"登录"}</button>
      </form>
      <PasswordRecovery/>
      {DATA_SOURCE==="demo"&&<p>演示模式未连接账户服务。</p>}
    </section>:<>
      <section className="account-panel"><h2>{user.username}</h2><p>{user.role==="admin"?"管理员":"研究账户"} · {workspaceSyncing?"正在保存…":workspaceReady&&!workspaceError?"阅读空间已连接":"正在读取阅读空间"}</p>
        {workspaceError&&<div className="inline-error" role="alert">{workspaceError}。未保存的草稿保留在本机，可先在“我的文献”导出备份。<button className="button button-secondary" onClick={()=>window.location.reload()}>重新加载服务器数据</button></div>}
        <div className="detail-buttons"><Link className="button button-primary" to="/library">打开我的文献</Link><Link className="button button-secondary" to="/upload">上传论文</Link>{user.role==="admin"&&<Link className="button button-secondary" to="/admin">审核工作台</Link>}
        <button className="button button-secondary" disabled={busy||workspaceSyncing} onClick={async()=>{setBusy(true);try{await logout();}catch(cause){setError(cause instanceof Error?cause.message:"退出失败");}finally{setBusy(false);}}}>退出登录</button></div>
      </section>
      <AccountSettings/>
      <section className="account-panel"><div className="results-topbar"><h2>搜索历史 · {total}</h2><button className="button button-secondary" disabled={!total} onClick={async()=>{if(!window.confirm("清空当前账户的搜索历史？阅读历史和收藏不受影响。"))return;try{await accountApi.clearHistory();setQueries([]);setTotal(0);setPage(1);}catch(cause){setError(cause instanceof Error?cause.message:"清空失败");}}}>清空搜索历史</button></div>
        {queries.length?queries.map(item=><Link className="account-history-link" key={item.id} to={"/search?"+new URLSearchParams({q:item.q,field:item.field,mode:item.mode})}><strong>{item.q}</strong><span>{item.mode} · {new Date(item.created_at).toLocaleString()}</span></Link>):<p>搜索后，关键词和检索方式会记录在这里。</p>}
        <nav className="pagination" aria-label="搜索历史分页"><button disabled={page<=1} onClick={()=>setPage(page-1)}>上一页</button><span>{page} / {Math.max(1,Math.ceil(total/20))}</span><button disabled={page*20>=total} onClick={()=>setPage(page+1)}>下一页</button></nav>
      </section>
    </>}
    <IntegrationNotice title="游客与账户各有自己的空间" desc="登录后使用账户收藏和阅读历史，退出后恢复原游客空间。本机PDF文件仍留在浏览器；要发送到服务器，请在PDF工作区选择服务端上传。"/>
  </div>;
}
