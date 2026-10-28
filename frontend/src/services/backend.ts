import type { HistoryEntry, LibraryEntry } from "../types";

const BASE = (import.meta.env.VITE_API_BASE_URL || "/api").replace(/\/$/, "");
const SESSION = "scholarlens-session";
export interface User { id: number; username: string; role: string }
export interface ServerUpload { id: string; original_name: string; size: number; status: string; reason: string; created_at: string; updated_at: string; paper_id: string | null; attempts: number; archived: boolean }
export interface QueryHistory { id: number; q: string; field: string; mode: string; created_at: string }
export interface WorkspaceData { version: number; favorites: LibraryEntry[]; history: HistoryEntry[]; collections: string[] }
export class BackendError extends Error {
  constructor(message: string, public status: number, public code: string) { super(message); }
}
export function sessionToken() { return sessionStorage.getItem(SESSION) || ""; }
export function setSession(token: string) {
  if (token) sessionStorage.setItem(SESSION, token); else sessionStorage.removeItem(SESSION);
  if (!token) for (const name of Object.keys(sessionStorage)) if (name.startsWith("scholarlens-ai-key:")) sessionStorage.removeItem(name);
}
interface Options {method?: string; body?: unknown; token?: string; blob?: boolean; signal?: AbortSignal; headers?: Record<string,string>}
export async function backend<T>(path: string, options: Options = {}): Promise<T> {
  const headers = new Headers({Accept: options.blob ? "application/pdf" : "application/json"});
  for (const [name,value] of Object.entries(options.headers??{})) headers.set(name,value);
  const token = options.token ?? sessionToken();
  if (token) headers.set("Authorization", "Bearer " + token);
  const form = options.body instanceof FormData;
  if (options.body !== undefined && !form) headers.set("Content-Type", "application/json");
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), options.blob ? 60000 : 120000);
  const cancel = () => controller.abort();
  options.signal?.addEventListener("abort", cancel, {once:true});
  if (options.signal?.aborted) controller.abort();
  try {
    const response = await fetch(BASE + path, {method: options.method ?? "GET", headers,
      body: options.body === undefined ? undefined : form ? options.body as FormData : JSON.stringify(options.body), signal: controller.signal});
    if (!response.ok) {
      const raw = await response.json().catch(() => null);
      const secondaryCredentialFailure = raw?.error?.code === "invalid_credentials" && options.method === "POST"
        && (path === "/auth/password" || path === "/auth/deactivate");
      if (response.status === 401 && !secondaryCredentialFailure && token && token === sessionToken()) {
        setSession(""); window.dispatchEvent(new Event("scholarlens-auth-expired"));
      }
      throw new BackendError(raw?.error?.message || "请求失败（HTTP " + response.status + "）", response.status, raw?.error?.code || "request_failed");
    }
    return (options.blob ? await response.blob() : await response.json()) as T;
  } catch (cause) {
    if (controller.signal.aborted && !options.signal?.aborted) throw new Error("请求超时，请稍后重试。");
    if (cause instanceof TypeError) throw new Error("无法连接服务，请检查网络后重试。");
    throw cause;
  } finally {
    window.clearTimeout(timeout); options.signal?.removeEventListener("abort", cancel);
  }
}
export const accountApi = {
  me: () => backend<User>("/auth/me"),
  register: (username: string, password: string) => backend<User>("/auth/register", {method:"POST",body:{username,password},token:""}),
  login: (username: string, password: string) => backend<{user:User;access_token:string}>("/auth/login", {method:"POST",body:{username,password},token:""}),
  logout: () => backend("/auth/logout", {method:"POST"}),
  workspace: (token: string, signal?: AbortSignal) => backend<WorkspaceData>("/me/workspace", {token,signal}),
  saveWorkspace: (data: WorkspaceData, token: string) => backend<{version:number}>("/me/workspace", {method:"PUT",token,body:{
    version:data.version,collections:data.collections,
    favorites:data.favorites.map(item=>({paper_id:item.paper.paper_id,collection:item.collection,note:item.note??"",savedAt:item.savedAt})),
    history:data.history.map(item=>({paper_id:item.paper.paper_id,viewedAt:item.viewedAt}))}}),
  history: (page=1,signal?:AbortSignal) => backend<{results:QueryHistory[];total:number}>("/me/history?page_size=20&page="+page,{signal}),
  recordQuery: (q: string, field: string, mode: string) => backend("/me/history", {method:"POST",body:{q,field,mode}}),
  clearHistory: () => backend("/me/history", {method:"DELETE"})
};
export const uploadApi = {
  list: (admin=false,page=1,signal?:AbortSignal) => backend<{results:ServerUpload[];total:number}>((admin?"/admin/uploads":"/uploads")+"?page_size=20&page="+page,{signal}),
  upload: (file: File, admin=false) => { const form=new FormData();form.append("file",file);return backend<ServerUpload>(admin?"/admin/uploads":"/uploads",{method:"POST",body:form}); },
  review: (id:string,decision:"approve"|"reject",reason:string) => backend<ServerUpload>("/admin/uploads/"+encodeURIComponent(id)+"/review",{method:"POST",body:{decision,reason}}),
  process: (id:string) => backend<ServerUpload>("/admin/uploads/"+encodeURIComponent(id)+"/process",{method:"POST"}),
  archive: (id:string) => backend("/admin/uploads/"+encodeURIComponent(id),{method:"DELETE"}),
  vectorize: () => backend("/admin/uploads/vectorize",{method:"POST"}),
  docx: (id:string) => backend<Blob>("/uploads/"+encodeURIComponent(id)+"/docx",{blob:true}),
  preview: (id:string) => backend<Blob>("/uploads/"+encodeURIComponent(id)+"/pdf",{blob:true})
};
