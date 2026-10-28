export interface EvidenceReference {paper_id:string;paper_title:string;chunk_id:string;quote:string;locator:string}
export type EvidenceField = "title" | "abstract" | "fulltext";
export interface EvidenceTarget {locator:string;quote:string}
export interface EvidenceMatch {field:EvidenceField;start:number;end:number;text:string}
const fieldLabels = {title:"标题",abstract:"摘要",fulltext:"正文"};

export function readEvidenceReferences(value:unknown):EvidenceReference[] {
  if(!Array.isArray(value)||value.length>50)throw new Error("证据服务返回格式无效");
  return value.map(item=>{
    if(!item||typeof item!=="object"||["paper_id","paper_title","chunk_id","quote","locator"].some(key=>typeof item[key]!=="string")||!item.paper_id||!item.chunk_id||!item.quote.trim()||item.quote.length>2000)throw new Error("证据服务返回格式无效");
    return {paper_id:item.paper_id,paper_title:item.paper_title,chunk_id:item.chunk_id,quote:item.quote,locator:item.locator};
  });
}

/** React escapes these strings. Preserve the original text, including literal markup. */
export function exactTextParts(text:string,query:string) {
  const terms=[...new Set(query.trim().split(/\s+/u).filter(Boolean))].slice(0,16).sort((a,b)=>b.length-a.length);
  if(!terms.length)return [{text,match:false}];
  const escaped=terms.map(term=>term.replace(/[.*+?^${}()|[\]\\]/g,"\\$&"));
  return text.split(new RegExp("("+escaped.join("|")+")","giu")).filter(Boolean).map(part=>({text:part,match:terms.some(term=>term.toLocaleLowerCase()===part.toLocaleLowerCase())}));
}

export function parseEvidenceLocator(locator:string) {
  const match = /^(title|abstract|fulltext):chars:(\d{1,10})-(\d{1,10})$/.exec(locator);
  if (!match||match[0]!==locator) return null;
  const start=Number(match[2]),end=Number(match[3]);
  return end>start ? {field:match[1] as EvidenceField,start,end} : null;
}

export function evidenceLocatorLabel(locator:string) {
  const parsed=parseEvidenceLocator(locator);
  return parsed ? `${fieldLabels[parsed.field]} · 字符 ${parsed.start+1}–${parsed.end}` : "原文位置暂不可识别";
}

/** Backend offsets count Unicode code points. Return browser UTF-16 indices only after an exact match. */
export function resolveEvidenceLocation(source:Record<EvidenceField,string>,target:EvidenceTarget):EvidenceMatch|null {
  const locator=parseEvidenceLocator(target.locator);
  if(!locator||!target.quote.trim()||target.quote.length>2000)return null;
  const text=source[locator.field];
  if(locator.end>text.length)return null;
  let point=0,offset=0,start=-1,end=-1;
  for(const character of text) {
    if(point===locator.start)start=offset;
    offset+=character.length;point++;
    if(point===locator.end){end=offset;break;}
  }
  if(start<0||end<0)return null;
  const relative=text.slice(start,end).indexOf(target.quote);
  if(relative<0)return null;
  return {field:locator.field,start:start+relative,end:start+relative+target.quote.length,text};
}

export function evidenceTargetFromHash(hash:string):EvidenceTarget|null {
  if(hash.length>24000)return null;
  const params=new URLSearchParams(hash.replace(/^#/,""));
  const locator=params.get("locator")??"",quote=params.get("quote")??"";
  return params.get("evidence")==="1"&&parseEvidenceLocator(locator)&&quote.trim()&&quote.length<=2000 ? {locator,quote} : null;
}

export function evidenceHref(reference:Pick<EvidenceReference,"paper_id"|"locator"|"quote">) {
  const path="/paper/"+encodeURIComponent(reference.paper_id);
  if(!parseEvidenceLocator(reference.locator)||!reference.quote.trim()||reference.quote.length>2000)return path;
  return path+"#"+new URLSearchParams({evidence:"1",locator:reference.locator,quote:reference.quote});
}

export function evidenceNote(reference:Pick<EvidenceReference,"quote"|"locator">) {
  return reference.quote+"\n\n位置："+evidenceLocatorLabel(reference.locator);
}
