import {backend} from "./backend";
import {personalAiHeaders} from "./personalAi";
import type {PersonalAi} from "./personalAi";

// Provider credentials are never bundled; optional personal keys stay session-only.
const rawEndpoint = (import.meta.env.VITE_AI_ENDPOINT ?? "").trim();
export const AI_ENDPOINT: string = rawEndpoint.startsWith("/api/") ? rawEndpoint : "";
export const AI_READY = Boolean(AI_ENDPOINT);
export interface AiSource {paper_id:string;title:string;excerpt?:string;chunk_id?:string;locator?:string}
export interface AiMessage {role:"user"|"assistant";content:string;sources?:AiSource[]}
export interface Evidence {paper_id:string;paper_title:string;chunk_id:string;quote:string;locator:string;relevance_score:number}
export type AiOperation="ask"|"summarize"|"compare";
export interface Conversation {id:string;title:string;message_count:number;updated_at:string}
export interface AiRequest {question:string;paperIds?:string[];conversationId?:string;operation?:AiOperation;personal?:PersonalAi|null}
interface Answer {answer:string;evidence_status:string;citations:Evidence[]}
function sources(citations:Evidence[]=[]):AiSource[]{
  return citations.map(item=>({paper_id:item.paper_id,title:item.paper_title,excerpt:item.quote,chunk_id:item.chunk_id,locator:item.locator}));
}
export function getAssistantAvailability(){
  return backend<{modules:Record<string,{status:string;reason:string}>}>("/capabilities");
}
export async function askAi(request:AiRequest,signal?:AbortSignal):Promise<AiMessage>{
  const operation=request.operation??"ask";
  const response=await backend<Answer>(operation==="ask"?"/ask":"/ai/"+operation,{method:"POST",signal,headers:personalAiHeaders(request.personal),body:{question:request.question,paper_ids:request.paperIds?.length?request.paperIds:null,conversation_id:request.conversationId||null,mode:"keyword",top_k:operation==="ask"?5:10,stream:false}});
  if(typeof response.answer!=="string"||!Array.isArray(response.citations))throw new Error("问答服务返回格式无效");
  return {role:"assistant",content:response.evidence_status==="insufficient_evidence"?"当前论文证据不足，无法形成有依据的回答。请调整问题或所选论文。":response.answer,sources:sources(response.citations)};
}
export function retrieveEvidence(question:string,paperIds:string[]=[],signal?:AbortSignal){
  return backend<Evidence[]>("/evidence",{method:"POST",signal,body:{question,mode:"keyword",top_k:5,paper_ids:paperIds.length?paperIds:null}});
}
export const conversationApi={
  list:()=>backend<Conversation[]>("/ai/conversations"),
  create:(title:string)=>backend<Conversation>("/ai/conversations",{method:"POST",body:{title:title.slice(0,160)}}),
  remove:(id:string)=>backend("/ai/conversations/"+encodeURIComponent(id),{method:"DELETE"}),
  messages:async(id:string)=>{
    const rows=await backend<{role:"user"|"assistant";content:string;citations:Evidence[]}[]>("/ai/conversations/"+encodeURIComponent(id)+"/messages");
    return rows.map(item=>({role:item.role,content:item.content||"当前证据不足。",sources:sources(item.citations)}));
  }
};
