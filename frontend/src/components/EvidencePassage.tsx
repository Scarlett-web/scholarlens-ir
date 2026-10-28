import type {EvidenceMatch} from "../lib/evidenceLocation";
import {exactTextParts} from "../lib/evidenceLocation";

export function ExactHighlight({text,query=""}:{text:string;query?:string}) {
  return <>{exactTextParts(text,query).map((part,i)=>part.match?<mark key={i}>{part.text}</mark>:part.text)}</>;
}

export function EvidencePassage({text,match,query=""}:{text:string;match?:EvidenceMatch|null;query?:string}) {
  if(!match)return <ExactHighlight text={text} query={query}/>;
  return <><ExactHighlight text={text.slice(0,match.start)} query={query}/><mark id="paper-evidence-match" className="reader-evidence-match" tabIndex={-1}>{text.slice(match.start,match.end)}</mark><ExactHighlight text={text.slice(match.end)} query={query}/></>;
}
