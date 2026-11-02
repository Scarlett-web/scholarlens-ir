import test from "node:test";
import assert from "node:assert/strict";
import {assistantCitations,assistantCitationText} from "../src/lib/assistantCitations.ts";

const a={paper_id:"paper-a",title:"Mock 论文 A",chunk_id:"chunk:a",excerpt:"Exact source A",locator:"abstract:chars:0-14"};
const b={paper_id:"paper-b",title:"Mock 论文 B",chunk_id:"chunk:b",excerpt:"Exact source B",locator:"fulltext:chars:20-34"};
test("number by first mention across arbitrary papers, retaining repeat IDs and same-paper fragments",()=>{
  const c={...a,chunk_id:"chunk:c",excerpt:"Another passage"};
  const result=assistantCitations("B [chunk:b] A [chunk:a] B again [chunk:b] C [chunk:c]",[a,c,b,a]);
  assert.deepEqual(result.parts.filter(p=>p.kind==="citation").map(p=>p.number),[1,2,1,3]);
  assert.deepEqual(result.references.map(r=>r.source),[b,a,c]);
});
test("unknown sources are never assigned to other papers or mistaken for verified citations",()=>{
  const result=assistantCitations("Unknown [chunk:missing] known [chunk:a]",[a]);
  assert.equal(result.parts.filter(p=>p.kind==="missing").length,1);
  assert.deepEqual(result.references.map(r=>r.source),[a]);
  assert.equal(assistantCitationText("[chunk:missing]"),"[来源缺失]");
});
test("no citations, literal HTML, saved sources without locators and unused evidence remain representable",()=>{
  const raw='<img src=x onerror="bad()"> Plain text [1]';
  assert.deepEqual(assistantCitations(raw).parts,[{kind:"text",text:raw}]);
  assert.equal(assistantCitationText(raw),raw);
  assert.deepEqual(assistantCitations("No markers",[b,a]).references.map(r=>r.source),[b,a]);
  assert.match(assistantCitationText("[chunk:a]",[{...a,locator:""}]),/原文位置暂不可识别/);
});
test("copy uses the displayed citation order and includes exact source text without internal IDs",()=>{
  const copied=assistantCitationText("B [chunk:b] A [chunk:a]",[a,b]);
  assert.ok(copied.startsWith("B [1] A [2]"));
  assert.ok(copied.includes("[1] Mock 论文 B\n原文：Exact source B"));
  assert.ok(copied.includes("位置：正文 · 字符 21–34"));
  assert.ok(!copied.includes("chunk:"));
});
test("numbering is message-local and independent of title, language, or identifier length",()=>{
  for(let i=0;i<60;i++){
    const source={...a,paper_id:`arbitrary/${i}`,chunk_id:"chunk:"+String(i).padStart(64,"0"),title:i%2?"English":"中文文献"};
    assert.equal(assistantCitations(`Result [${source.chunk_id}]`,[source]).references[0].number,1);
    assert.equal(assistantCitations(`Result [${source.chunk_id}]`,[source]).references[0].source.paper_id,source.paper_id);
  }
});
