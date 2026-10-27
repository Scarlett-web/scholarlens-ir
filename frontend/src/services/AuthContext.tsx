import {createContext,useContext,useEffect,useState} from "react";
import type {ReactNode} from "react";
import {accountApi,sessionToken,setSession} from "./backend";
import type {User} from "./backend";
import {DATA_SOURCE} from "./papers";

interface Auth {user:User|null;loading:boolean;error:string;login(username:string,password:string,register?:boolean):Promise<void>;logout():Promise<void>}
const Context=createContext<Auth|null>(null);
export function useAuth(){const value=useContext(Context);if(!value)throw new Error("AuthProvider required");return value;}
export function AuthProvider({children}:{children:ReactNode}){
  const [user,setUser]=useState<User|null>(null),[loading,setLoading]=useState(true),[error,setError]=useState("");
  useEffect(()=>{
    let active=true;
    if(DATA_SOURCE==="demo"||!sessionToken()){setLoading(false);return;}
    accountApi.me().then(value=>{if(active)setUser(value);}).catch(cause=>{if(active)setError(cause instanceof Error?cause.message:"无法检查登录状态");}).finally(()=>{if(active)setLoading(false);});
    return()=>{active=false;};
  },[]);
  useEffect(()=>{const expire=()=>{setUser(null);setError("登录已过期，请重新登录。游客数据仍保留。");};window.addEventListener("scholarlens-auth-expired",expire);return()=>window.removeEventListener("scholarlens-auth-expired",expire);},[]);
  const login=async(username:string,password:string,register=false)=>{
    if(DATA_SOURCE==="demo")throw new Error("演示模式不连接账户服务");
    if(register)await accountApi.register(username,password);
    const result=await accountApi.login(username,password);
    setSession(result.access_token);setError("");setUser(result.user);
  };
  const logout=async()=>{await accountApi.logout();setSession("");setUser(null);};
  return <Context.Provider value={{user,loading,error,login,logout}}>{children}</Context.Provider>;
}
