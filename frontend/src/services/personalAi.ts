import {backend} from "./backend";

export interface PersonalAi {url:string;model:string;key:string;tokenParameter:"max_tokens"|"max_completion_tokens";protocol?:"chat_completions"|"responses"}
export function personalAiPreferences(userId:number):PersonalAi {
  let value:Partial<PersonalAi>={};
  try{value=JSON.parse(localStorage.getItem("scholarlens-ai-preferences:"+userId)||"{}");}catch{}
  return {url:typeof value?.url==="string"?value.url:"",model:typeof value?.model==="string"?value.model:"",
    tokenParameter:value?.tokenParameter==="max_tokens"?"max_tokens":"max_completion_tokens",
    protocol:value?.protocol==="responses"?"responses":"chat_completions",
    key:sessionStorage.getItem("scholarlens-ai-key:"+userId)||""};
}
export function loadPersonalAi(userId:number):PersonalAi|null{
  const value=personalAiPreferences(userId);return value.url&&value.model&&value.key?value:null;
}
export function normalizePersonalAi(input:PersonalAi,requireModel=true):PersonalAi{
  const url=new URL(input.url.trim());
  if(url.protocol!=="https:"||url.username||url.password||url.search||url.hash||url.port&&url.port!=="443")throw new Error("请填写公共 HTTPS API 地址，不要附带账号或查询参数");
  const endpoint=url.href.replace(/\/$/,"");
  const protocol=endpoint.endsWith("/responses")?"responses":endpoint.endsWith("/chat/completions")?"chat_completions":input.protocol||"chat_completions";
  const value={...input,url:endpoint.replace(/\/(chat\/completions|responses)$/, ""),protocol,model:input.model.trim(),key:input.key.trim()};
  if(requireModel&&!value.model||!value.key||!/^[\x21-\x7e]+$/.test(value.model+value.key))throw new Error("请填写有效的模型名称和 API 密钥");
  if(value.url.length>2048||value.model.length>200||value.key.length>2048)throw new Error("配置内容超过长度限制");
  return value;
}
export function savePersonalAi(userId:number,input:PersonalAi):PersonalAi{
  const value=normalizePersonalAi(input);
  const {key,...preferences}=value;
  // Write the session-only secret first; roll it back if saving preferences fails.
  const secretName="scholarlens-ai-key:"+userId,previous=sessionStorage.getItem(secretName);
  sessionStorage.setItem(secretName,key);
  try{localStorage.setItem("scholarlens-ai-preferences:"+userId,JSON.stringify(preferences));}
  catch(error){if(previous===null)sessionStorage.removeItem(secretName);else sessionStorage.setItem(secretName,previous);throw error;}
  return value;
}
export function clearPersonalAi(userId:number){
  sessionStorage.removeItem("scholarlens-ai-key:"+userId);localStorage.removeItem("scholarlens-ai-preferences:"+userId);
}
export function personalAiHeaders(value?:PersonalAi|null):Record<string,string>{
  return value?{"X-ScholarLens-AI-URL":value.url,"X-ScholarLens-AI-Model":value.model,
    "X-ScholarLens-AI-Key":value.key,"X-ScholarLens-AI-Token-Parameter":value.tokenParameter,
    "X-ScholarLens-AI-Protocol":value.protocol||"chat_completions"}:{};
}
export const readPersonalModels=(value:PersonalAi,signal?:AbortSignal)=>backend<{models:string[]}>("/ai/models",{headers:personalAiHeaders(normalizePersonalAi(value,false)),signal});
export const testPersonalConnection=(value:PersonalAi,signal?:AbortSignal)=>backend<{status:string;model:string;protocol:string}>("/ai/test",{method:"POST",headers:personalAiHeaders(normalizePersonalAi(value)),signal});
