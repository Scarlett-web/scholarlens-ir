import {useEffect,useRef,useState} from "react";
import {Link} from "react-router-dom";
import {ArrowUpRight,History,RefreshCw} from "lucide-react";
import {accountApi} from "../services/backend";
import type {QueryHistory} from "../services/backend";

/** Only the latest read or clear operation may update this account's history. */
export function AccountSearchHistory(){
  const [queries,setQueries]=useState<QueryHistory[]>([]),[page,setPage]=useState(1),[total,setTotal]=useState<number|null>(null);
  const [status,setStatus]=useState<"loading"|"ready"|"error">("loading"),[error,setError]=useState("");
  const [retry,setRetry]=useState(0),[clearing,setClearing]=useState(false);
  const sequence=useRef(0),controller=useRef<AbortController|null>(null),clearLock=useRef(false);
  useEffect(()=>{
    const abort=new AbortController(),request=++sequence.current;controller.current=abort;
    setStatus("loading");setError("");setQueries([]);
    accountApi.history(page,abort.signal).then(data=>{
      if(abort.signal.aborted||sequence.current!==request)return;
      setTotal(data.total);
      const last=Math.max(1,Math.ceil(data.total/20));
      if(page>last){setPage(last);return;}
      setQueries(data.results);setStatus("ready");
    }).catch(cause=>{
      if(!abort.signal.aborted&&sequence.current===request){setError(cause instanceof Error?cause.message:"搜索历史读取失败");setStatus("error");}
    });
    return()=>{abort.abort();sequence.current++;};
  },[page,retry]);
  const clear=async()=>{
    if(clearLock.current||!window.confirm("清空当前账户的搜索历史？阅读历史和收藏不受影响。"))return;
    clearLock.current=true;setClearing(true);setError("");controller.current?.abort();const request=++sequence.current;
    try{
      await accountApi.clearHistory();
      if(sequence.current!==request)return;
      setQueries([]);setTotal(0);setStatus("ready");setPage(1);
    }catch(cause){if(sequence.current===request){setError(cause instanceof Error?cause.message:"清空失败，请重试");setStatus("error");}}
    finally{clearLock.current=false;if(sequence.current===request)setClearing(false);}
  };
  return <section className="account-panel account-search-history"><details>
    <summary><History size={17}/>搜索历史 <span>{total===null?"—":total+" 条"}</span></summary>
    <div className="results-topbar"><p>点击一条记录，继续当时的检索。</p><button className="button button-secondary" disabled={!total||clearing} onClick={()=>void clear()}>清空搜索历史</button></div>
    <div className="account-history-body" aria-live="polite" aria-busy={status==="loading"||clearing}>
      {clearing?<p role="status">正在清空搜索历史…</p>:status==="loading"?<p role="status">正在读取搜索历史…</p>:status==="error"?<div className="account-history-error" role="alert"><p>{error}</p><button className="text-action" onClick={()=>setRetry(value=>value+1)}><RefreshCw size={14}/>重新读取搜索历史</button></div>:queries.length?queries.map(item=><Link className="account-history-link" key={item.id} to={"/search?"+new URLSearchParams({q:item.q,field:item.field,mode:item.mode})}><div><strong>{item.q}</strong><span>{({keyword:"关键词",semantic:"语义",hybrid:"混合"} as Record<string,string>)[item.mode]||item.mode} · {new Date(item.created_at).toLocaleString("zh-CN")}</span></div><ArrowUpRight size={15}/></Link>):<p>还没有搜索记录。检索论文后会显示在这里。</p>}
    </div>
    {total!==null&&total>20&&<nav className="pagination" aria-label="搜索历史分页"><button disabled={page<=1||clearing||status==="loading"} onClick={()=>setPage(value=>value-1)}>上一页</button><span>{page} / {Math.max(1,Math.ceil(total/20))}</span><button disabled={page*20>=total||clearing||status==="loading"} onClick={()=>setPage(value=>value+1)}>下一页</button></nav>}
  </details></section>;
}
