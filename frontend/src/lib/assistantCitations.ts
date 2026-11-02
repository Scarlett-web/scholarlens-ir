import type {AiSource} from "../services/ai";
import {evidenceLocatorLabel} from "./evidenceLocation.ts";

export type CitationPart = {kind:"text";text:string} | {kind:"citation";number:number} | {kind:"missing"};
export interface NumberedSource {number:number;source:AiSource}

/** Resolve only against this message's sources. Never guess a paper from model text. */
export function assistantCitations(content:string,sources:AiSource[]=[]){
  const byId=new Map<string,AiSource>();
  for(const source of sources)if(source.chunk_id&&!byId.has(source.chunk_id))byId.set(source.chunk_id,source);
  const numbers=new Map<string,number>(),references:NumberedSource[]=[],parts:CitationPart[]=[];
  const add=(source:AiSource)=>{
    if(source.chunk_id&&numbers.has(source.chunk_id))return numbers.get(source.chunk_id)!;
    const number=references.length+1;
    references.push({number,source});
    if(source.chunk_id)numbers.set(source.chunk_id,number);
    return number;
  };
  let offset=0;
  for(const match of content.matchAll(/\[(chunk:[^\]\r\n]+)\]/g)){
    if(match.index!>offset)parts.push({kind:"text",text:content.slice(offset,match.index)});
    const source=byId.get(match[1]);
    parts.push(source?{kind:"citation",number:add(source)}:{kind:"missing"});
    offset=match.index!+match[0].length;
  }
  if(offset<content.length)parts.push({kind:"text",text:content.slice(offset)});
  for(const source of sources)add(source);
  return {parts,references};
}

/** Copy the same visible numbering and its sources, leaving stored/raw messages intact. */
export function assistantCitationText(content:string,sources:AiSource[]=[]){
  const {parts,references}=assistantCitations(content,sources);
  const answer=parts.map(part=>part.kind==="text"?part.text:part.kind==="citation"?`[${part.number}]`:"[来源缺失]").join("");
  if(!references.length)return answer;
  return answer+"\n\n引用来源\n"+references.map(({number,source})=>
    `[${number}] ${source.title||"论文标题暂缺"}`+(source.excerpt?"\n原文："+source.excerpt:"")+
    "\n位置："+evidenceLocatorLabel(source.locator||"")
  ).join("\n\n");
}
