import {backend} from "./backend";
import {personalAiHeaders} from "./personalAi";
import type {PersonalAi} from "./personalAi";
import {readEvidenceReferences} from "../lib/evidenceLocation";

// Provider credentials are never bundled; optional personal keys stay session-only.
const rawEndpoint = (import.meta.env.VITE_AI_ENDPOINT ?? "").trim();
export const AI_ENDPOINT: string = rawEndpoint.startsWith("/api/") ? rawEndpoint : "";
export const AI_READY = Boolean(AI_ENDPOINT);
export interface AiSource {paper_id:string;title:string;excerpt?:string;chunk_id?:string;locator?:string}
export interface Evidence {paper_id:string;paper_title:string;chunk_id:string;quote:string;locator:string;relevance_score:number}
export type AiOperation="ask"|"summarize"|"compare";
export interface Conversation {id:string;title:string;message_count:number;updated_at:string}
export interface AiRequest {question:string;paperIds?:string[];conversationId?:string;operation?:AiOperation;personal?:PersonalAi|null;history?:AiMessage[]}
export interface AgentStep {id:string;tool:string;label:string;status:"done"|"running"|"queued"|"empty"|"skipped"|"error";elapsed_ms?:number;result_count?:number}
export interface AgentTrace {name:string;version:string;workflow:string;tools:{name:string;label:string}[];steps:AgentStep[];evidence_count:number;grounded:boolean;warnings?:string[];elapsed_ms?:number}
export interface AiMessage {role:"user"|"assistant";content:string;sources?:AiSource[];agent?:AgentTrace;sourceLabel?:string;answerKind?:"general"|"grounded"}
interface Answer {answer:string;evidence_status:string;citations:Evidence[];evidence:Evidence[];agent?:AgentTrace}
function sources(citations:unknown=[]):AiSource[]{
  return readEvidenceReferences(citations).map(item=>({paper_id:item.paper_id,title:item.paper_title,excerpt:item.quote,chunk_id:item.chunk_id,locator:item.locator}));
}
export function getAssistantAvailability(){
  return backend<{modules:Record<string,{status:string;reason:string}>}>("/capabilities");
}
export async function askAi(request:AiRequest,signal?:AbortSignal):Promise<AiMessage>{
  const operation=request.operation??"ask";
  const context=request.conversationId?[]:(request.history||[]).filter(item=>item.content.trim()).slice(-12).map(item=>({role:item.role,content:item.content.slice(0,1000)}));
  const response=await backend<Answer>("/agent/run",{method:"POST",signal,headers:personalAiHeaders(request.personal),body:{question:request.question,paper_ids:request.paperIds?.length?request.paperIds:null,conversation_id:request.conversationId||null,context_messages:context,operation,mode:"keyword",top_k:operation==="ask"?Math.max(5,request.paperIds?.length??0):10,stream:false}});
  if(typeof response.answer!=="string"||!Array.isArray(response.citations))throw new Error("问答服务返回格式无效");
  const fallbacks:Record<string,string>={insufficient_evidence:"尚未获得可核对的论文回答。你可以继续追问，或查看已找到的原文；无需按固定格式提问。",evidence_only:"原文证据已找到。配置个人 API 后，可以继续生成回答。",provider_unavailable:response.agent?.warnings?.at(-1)||"本次模型未能完成回答，可检查 API 配置后重试。"};
  return {role:"assistant",content:response.answer||fallbacks[response.evidence_status]||"本次没有生成回答。",sources:sources(response.answer?response.citations:response.evidence),sourceLabel:response.answer?"引用来源":"原文证据",agent:response.agent,answerKind:response.evidence_status==="general_answer"?"general":"grounded"};
}
export async function retrieveEvidence(question:string,paperIds:string[]=[],signal?:AbortSignal){
  const response=await backend<Answer>("/agent/run",{method:"POST",signal,body:{question,operation:"evidence",mode:"keyword",top_k:Math.max(5,paperIds.length),paper_ids:paperIds.length?paperIds:null}});
  return {evidence:readEvidenceReferences(response.evidence),agent:response.agent};
}
export const conversationApi={
  list:()=>backend<Conversation[]>("/ai/conversations"),
  create:(title:string)=>backend<Conversation>("/ai/conversations",{method:"POST",body:{title:title.slice(0,160)}}),
  remove:(id:string)=>backend("/ai/conversations/"+encodeURIComponent(id),{method:"DELETE"}),
  messages:async(id:string)=>{
    const rows=await backend<{role:"user"|"assistant";content:string;citations:Evidence[]}[]>("/ai/conversations/"+encodeURIComponent(id)+"/messages");
    return rows.map(item=>({role:item.role,content:item.content||(item.citations.length?"该次未生成回答，可查看保留的原文证据。":"该次未生成回答。"),sources:sources(item.citations),sourceLabel:item.content?"引用来源":"原文证据",answerKind:item.role==="assistant"&&item.content&&!item.citations.length?"general" as const:"grounded" as const}));
  }
};
