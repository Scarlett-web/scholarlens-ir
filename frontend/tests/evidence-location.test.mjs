import test from "node:test";
import assert from "node:assert/strict";
import {evidenceHref,evidenceTargetFromHash,parseEvidenceLocator,resolveEvidenceLocation,evidenceNote,exactTextParts,readEvidenceReferences} from "../src/lib/evidenceLocation.ts";
const source={title:"Real paper",abstract:"Alpha βeta",fulltext:"😀 before\nAn exact quote.\nAfter the quote."};
test("Unicode code point locators resolve to exact browser offsets",()=>{
  const match=resolveEvidenceLocation(source,{locator:"fulltext:chars:0-24",quote:"An exact quote"});
  assert.ok(match);assert.equal(source.fulltext.slice(match.start,match.end),"An exact quote");
  assert.equal(match.start,10,"surrogate pair before quote counts as two browser units");
});
test("a validated citation may be a substring within its original chunk",()=>{
  const match=resolveEvidenceLocation(source,{locator:"abstract:chars:0-10",quote:"βeta"});
  assert.equal(source.abstract.slice(match.start,match.end),"βeta");
  assert.equal(resolveEvidenceLocation(source,{locator:"abstract:chars:0-5",quote:"βeta"}),null);
});
test("changed source, malformed fields, bad ranges and oversized quotes never get a guessed match",()=>{
  for(const locator of ["__proto__:chars:0-1","fulltext:chars:-1-9","fulltext:chars:9-2","fulltext:chars:0-999","fulltext:chars:0-100000000000","fulltext:chars:0-0"]) {
    assert.equal(resolveEvidenceLocation(source,{locator,quote:"An"}),null);
  }
  assert.equal(resolveEvidenceLocation(source,{locator:"title:chars:0-10",quote:"real paper"}),null,"case changes are not exact evidence");
  assert.equal(resolveEvidenceLocation(source,{locator:"title:chars:0-10",quote:" "}),null);
  assert.equal(resolveEvidenceLocation(source,{locator:"title:chars:0-10",quote:"x".repeat(2001)}),null);
  assert.equal(parseEvidenceLocator("fulltext:chars:0-1\n"),null);
});
test("reading targets round trip in fragments without placing quote text in the server query",()=>{
  const reference={paper_id:"source:/ id?",locator:"abstract:chars:0-10",quote:"βeta & <script>"};
  const link=new URL(evidenceHref(reference),"https://example.invalid");
  assert.equal(link.search,"");assert.equal(decodeURIComponent(link.pathname.slice(7)),reference.paper_id);
  assert.deepEqual(evidenceTargetFromHash(link.hash),{locator:reference.locator,quote:reference.quote});
  for(const hash of ["#evidence=1","#evidence=0&locator=title:chars:0-1&quote=x","#evidence=1&locator=x&quote=y","#"+"x".repeat(24001)])assert.equal(evidenceTargetFromHash(hash),null);
  assert.equal(evidenceHref({...reference,locator:"invalid"}).includes("#"),false);
  assert.ok(evidenceNote(reference).includes("字符 1–10"));
});
test("plain-text evidence keeps literal markup and safe keyword matches byte for byte",()=>{
  const text='<img src=x onerror="bad()"> βeta a+b &amp;';
  const parts=exactTextParts(text,"βeta a+b");
  assert.equal(parts.map(x=>x.text).join(""),text);
  assert.deepEqual(parts.filter(x=>x.match).map(x=>x.text),["βeta","a+b"]);
  assert.equal(readEvidenceReferences([{paper_id:"p",paper_title:"t",chunk_id:"c",quote:text,locator:"title:chars:0-10"}])[0].quote,text);
  for(const value of [null,[{}],[{paper_id:"p",paper_title:"t",chunk_id:"c",quote:42,locator:"x"}]])assert.throws(()=>readEvidenceReferences(value),/格式/);
});
