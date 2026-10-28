/** Isolated API fixtures. No fixture account, note or model request reaches a live backend. */
import {chromium} from "playwright";
import assert from "node:assert/strict";
import {mkdirSync,writeFileSync} from "node:fs";
import {fileURLToPath} from "node:url";
import {join} from "node:path";
const origin=process.env.SCHOLARLENS_URL||"http://127.0.0.1:4174";
assert.ok(["127.0.0.1","localhost","[::1]"].includes(new URL(origin).hostname));
const root=fileURLToPath(new URL("../../",import.meta.url));
const output=join(root,"tools/audit/reports/evidence-workflow-"+new Date().toISOString().replace(/[:.]/g,"-"));
mkdirSync(output,{recursive:true});
const quote='Magnetic imaging 😀 retains the exact <img src=x onerror="bad()"> source text.';
const prefix="Fixture introduction 😀 before the evidence. ".repeat(135);
const fulltext=prefix+quote+"\nFollowing source context. ".repeat(40);
const base={year:2024,date:"",authors:["Fixture Researcher"],affiliation:[],address:[],keywords:[],topics:[],pages:null,pdf_available:false,parse_status:"success"};
const papers={
  a:{...base,paper_id:"source:fixture-a",title:"Fixture: exact evidence beyond the initial reading fold",abstract:"Fixture abstract for the first source.",fulltext},
  b:{...base,paper_id:"source:fixture-b",title:"Fixture: a second verified source",abstract:"A second magnetic imaging source provides separate evidence.",fulltext:"Second source body."},
  c:{...base,paper_id:"source:fixture-c",title:"Fixture: changed source",abstract:"Current source has changed.",fulltext:"Changed body."},
};
const refs=[
  {paper_id:papers.a.paper_id,paper_title:papers.a.title,chunk_id:"fixture:chunk-a",quote,locator:`fulltext:chars:${Array.from(prefix).length}-${Array.from(prefix+quote).length}`,relevance_score:1},
  {paper_id:papers.b.paper_id,paper_title:papers.b.title,chunk_id:"fixture:chunk-b",quote:papers.b.abstract,locator:`abstract:chars:0-${papers.b.abstract.length}`,relevance_score:1},
  {paper_id:papers.c.paper_id,paper_title:papers.c.title,chunk_id:"fixture:chunk-c",quote:"An old quote that no longer exists.",locator:"abstract:chars:0-26",relevance_score:1},
];
const browser=await chromium.launch({channel:"chrome",headless:true});
const unhandled=[],errors=[];
const report={passed:false,scope:"local isolated API fixture UI; not real authentication, supplier generation or account persistence",checks:[]};
async function setup({user=false,note="Existing research note.",answerMode=false}={}){
  const context=await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:"reduce"});
  const favorite={paper:papers.a,collection:"全部收藏",note,savedAt:"2026-10-28T05:00:00Z"};
  await context.addInitScript(({user,favorite,allowedOrigin})=>{
    if(location.origin!==allowedOrigin)return;
    if(user&&!sessionStorage.getItem("fixture-initialized")){sessionStorage.setItem("scholarlens-session","fixture-not-a-credential");sessionStorage.setItem("fixture-initialized","1");}
    else if(!user&&!localStorage.getItem("scholarlens-v1:favorites"))localStorage.setItem("scholarlens-v1:favorites",JSON.stringify([favorite]));
    Object.defineProperty(navigator,"clipboard",{value:{writeText:async text=>{window.fixtureClipboard=text;}}});
  },{user,favorite,allowedOrigin:new URL(origin).origin});
  const state={response:refs,agentGate:null,paperGate:null,paperFail:false,requests:[],saved:[],workspace:{version:0,favorites:[favorite],history:[],collections:["全部收藏"]}};
  await context.route("**/api/**",async route=>{
    const request=route.request(),url=new URL(request.url()),path=url.pathname.slice(4),method=request.method();
    const json=(data,status=200)=>route.fulfill({status,contentType:"application/json",body:JSON.stringify(data)});
    state.requests.push({path,method});
    if(path==="/stats")return json({status:"real",papers:859});
    if(path==="/discover"&&method==="GET"&&url.searchParams.get("limit")==="20")return json({papers:Object.keys(papers).length,recommendations:Object.values(papers),example_searches:[],years:[],status:"synthetic"});
    if(path==="/capabilities")return json({modules:{ai_qa:{status:answerMode?"ready":"not_configured",reason:"Controlled fixture only: provider unavailable. Authorization Bearer synthetic-not-real-bearer-1234567890; api_key=sk-synthetic-not-real-key-1234567890."},keyword_search:{status:"ready"},semantic_search:{status:"ready"},hybrid_search:{status:"ready"}}});
    if(path==="/auth/me"&&user)return json({id:801,username:"fixture-researcher",role:"user"});
    if(path==="/me/workspace"&&method==="GET"&&user)return json(state.workspace);
    if(path==="/me/workspace"&&method==="PUT"&&user){state.saved.push(request.postDataJSON());return json({version:state.saved.length});}
    if(path==="/ai/conversations"&&method==="GET"&&user)return json([]);
    if(path==="/agent/run"&&method==="POST"){
      const body=request.postDataJSON();assert.ok(body.operation==="evidence"||answerMode&&body.operation==="ask");
      assert.equal(request.headers()["x-ai-key"],undefined);
      const response=state.response,gate=state.agentGate;state.agentGate=null;
      if(gate)await gate;
      try{return await json({evidence:response,answer:body.operation==="ask"?"Controlled fixture answer citing supplied text.":"",citations:body.operation==="ask"?[refs[0]]:[],evidence_status:body.operation==="ask"?"grounded":"evidence_only",agent:{name:"Fixture agent",version:"0.2.0",workflow:"evidence-grounded-answer",steps:[],evidence_count:response.length,grounded:body.operation==="ask"}});}catch(error){if(!gate)throw error;return;}
    }
    if(path.startsWith("/papers/")&&method==="GET"){
      const id=decodeURIComponent(path.slice(8)),paper=Object.values(papers).find(item=>item.paper_id===id);
      if(state.paperFail){state.paperFail=false;return json({error:{message:"Fixture source temporarily unavailable"}},503);}
      const gate=state.paperGate;state.paperGate=null;if(gate)await gate;
      return paper?json(paper):json({error:{message:"Fixture paper missing"}},404);
    }
    unhandled.push(method+" "+path);return json({error:{message:"Missing explicit fixture"}},501);
  });
  context.on("page",page=>page.on("pageerror",error=>errors.push(error.message)));
  const page=await context.newPage();
  return {context,page,state};
}
async function search(page,text="magnetic imaging"){
  await page.getByRole("textbox",{name:"研究问题",exact:true}).fill(text);
  await page.getByRole("button",{name:"检索原文",exact:true}).click();
}
async function screenshot(page,name){
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.screenshot({path:join(output,name+".png")});
}
try{
  const guest=await setup();const {page,state,context}=guest;
  await page.goto(origin+"/assistant");await page.getByRole("button",{name:"检索原文",exact:true}).waitFor();
  assert.ok(await page.getByRole("button",{name:"检索原文",exact:true}).evaluate(el=>el.getBoundingClientRect().bottom<=innerHeight));
  await search(page);await page.getByText("片段与当前原文一致",{exact:true}).waitFor();
  assert.equal(await page.locator(".evidence-source-choice").count(),3);
  assert.equal(await page.locator(".evidence-quote").textContent(),quote);assert.equal(await page.locator(".evidence-quote img").count(),0);
  await page.getByRole("textbox",{name:"研究问题",exact:true}).fill("draft for a later search");assert.equal(await page.locator(".evidence-question").textContent(),"magnetic imaging");
  await page.getByRole("button",{name:"复制片段与来源",exact:true}).click();
  const copied=await page.evaluate(()=>window.fixtureClipboard);assert.ok(copied.includes(quote));assert.ok(copied.includes("Fixture Researcher"));
  const copiedLink=new URL(copied.split("阅读链接：")[1]);assert.equal(copiedLink.search,"");assert.equal(new URLSearchParams(copiedLink.hash.slice(1)).get("quote"),quote);
  await page.getByRole("button",{name:"加入笔记",exact:true}).click();await page.getByText("已追加到这篇论文的当前笔记，原有内容保留。",{exact:false}).waitFor();
  const note=await page.evaluate(()=>JSON.parse(localStorage.getItem("scholarlens-v1:favorites"))[0].note);
  assert.ok(note.startsWith("Existing research note."));assert.ok(note.includes(quote));assert.ok(note.includes("正文 · 字符"));
  assert.equal(await page.getByRole("button",{name:"已加入笔记",exact:true}).isDisabled(),true);
  await page.getByText("查看前后文",{exact:true}).click();assert.ok((await page.locator(".evidence-context p").textContent()).includes("Following source context"));
  await page.locator(".evidence-results").scrollIntoViewIfNeeded();await screenshot(page,"fixture-evidence-desktop");
  const popupPromise=context.waitForEvent("page");await page.getByRole("link",{name:"定位原文",exact:true}).click();const reader=await popupPromise;
  await reader.locator("#paper-evidence-match").waitFor();assert.equal(await reader.locator("#paper-evidence-match").textContent(),quote);
  assert.equal(await reader.locator("#paper-evidence-match").evaluate(el=>el===document.activeElement),true);
  assert.ok((await reader.locator("#paper-fulltext [data-reader-text]").textContent()).length>4500);
  await screenshot(reader,"fixture-reader-position");
  await reader.evaluate(()=>{
    const article=document.querySelector('.detail-main'),offset=document.querySelector('.reader-tools').offsetHeight+24;
    const top=scrollY+article.getBoundingClientRect().top-offset+.45*(article.offsetHeight-innerHeight+offset);
    window.dispatchEvent(new Event('resize'));window.scrollTo({top,behavior:'instant'});window.dispatchEvent(new Event('scroll'));
  });
  await reader.waitForFunction(()=>JSON.parse(localStorage.getItem('scholarlens-v1:reading-positions:guest')||'{}')[decodeURIComponent(location.pathname.slice(7))]?.ratio>.4);
  await reader.getByRole("button",{name:"收起全文",exact:true}).click();assert.equal(await reader.locator("#paper-evidence-match").count(),0);
  await reader.goto(origin+"/paper/"+encodeURIComponent(papers.a.paper_id)+"#evidence=1&locator=fulltext:chars:0-5&quote=wrong");
  await reader.getByText("未能核对这条证据的位置。原文或链接可能已变化，请手动核对。",{exact:true}).waitFor();assert.equal(await reader.locator("#paper-evidence-match").count(),0);await reader.close();
  await page.locator(".evidence-source-choice").nth(1).click();await page.getByText("片段与当前原文一致",{exact:true}).waitFor();
  assert.equal(await page.locator(".evidence-quote").textContent(),papers.b.abstract);
  await page.locator(".evidence-source-choice").nth(2).click();await page.getByText("片段与当前原文位置不一致",{exact:false}).waitFor();
  assert.equal(await page.getByRole("button",{name:"加入笔记",exact:true}).isDisabled(),true);assert.equal(await page.getByRole("link",{name:"打开论文",exact:true}).getAttribute("href"),"/paper/"+encodeURIComponent(papers.c.paper_id));
  state.paperFail=true;await page.locator(".evidence-source-choice").first().click();await page.getByText("Fixture source temporarily unavailable",{exact:true}).waitFor();
  await page.getByRole("button",{name:"重新读取",exact:true}).click();await page.getByText("片段与当前原文一致",{exact:true}).waitFor();
  await page.setViewportSize({width:390,height:844});await page.locator(".evidence-detail").scrollIntoViewIfNeeded();await screenshot(page,"fixture-evidence-390");await page.setViewportSize({width:1440,height:1000});
  state.response=[];await search(page,"no matching fixture");await page.getByRole("heading",{name:"没有找到相关片段",exact:true}).waitFor();assert.equal(await page.locator(".evidence-workbench").count(),0);
  let release;state.agentGate=new Promise(resolve=>{release=resolve;});state.response=refs;
  await search(page,"cancelled fixture request");await page.getByRole("button",{name:"停止",exact:true}).click();state.response=[refs[1]];
  await search(page,"latest completed fixture");await page.getByText("片段与当前原文一致",{exact:true}).waitFor();release();
  await page.waitForTimeout(150);assert.equal(await page.locator(".evidence-source-choice").count(),1);assert.equal(await page.locator(".evidence-question").textContent(),"latest completed fixture");
  state.response=[{quote:4}];await search(page,"malformed fixture response");await page.getByRole("alert").filter({hasText:"证据服务返回格式无效"}).waitFor();assert.equal(await page.locator(".evidence-source-choice").count(),1);
  await context.close();report.checks.push("guest exact source and literal markup, context, copy provenance, append preserving notes, duplicate prevention, Unicode/deep fulltext popup focus, invalid locator, changed source, retry, empty/malformed result, cancel and late response, desktop/390 geometry");

  const user=await setup({user:true});await user.page.goto(origin+"/assistant");
  const availabilityReason=await user.page.locator(".assistant-availability").waitFor().then(async()=>user.page.locator(".assistant-availability").textContent());
  assert.ok(availabilityReason?.includes("Controlled fixture only: provider unavailable"));
  assert.ok(availabilityReason?.includes("Bearer [已隐藏]"));
  assert.ok(!availabilityReason?.includes("Bearer synthetic-not-real-bearer-1234567890"));
  assert.ok(!availabilityReason?.includes("sk-synthetic-not-real-key-1234567890"));
  report.checks.push("capability unavailability reason remains useful while Bearer and sk- synthetic samples are masked");
  await search(user.page);await user.page.getByText("片段与当前原文一致",{exact:true}).waitFor();
  await user.page.getByRole("button",{name:"加入笔记",exact:true}).click();await user.page.waitForFunction(()=>document.querySelector('.evidence-saved')!==null);
  await user.page.waitForTimeout(650);assert.equal(user.state.saved.length,1);assert.ok(user.state.saved[0].favorites[0].note.startsWith("Existing research note."));assert.ok(user.state.saved[0].favorites[0].note.includes(quote));
  let releasePaper;user.state.paperGate=new Promise(resolve=>{releasePaper=resolve;});await user.page.locator(".evidence-source-choice").nth(1).click();await user.page.getByText("正在与当前原文逐字核对…",{exact:true}).waitFor();
  await user.page.evaluate(()=>{sessionStorage.removeItem("scholarlens-session");window.dispatchEvent(new Event("scholarlens-auth-expired"));});
  await user.page.getByRole("heading",{name:"先找到能回答问题的原文",exact:true}).waitFor();releasePaper();await user.page.waitForTimeout(150);
  assert.equal(await user.page.locator(".evidence-workbench,.evidence-saved").count(),0);await user.context.close();
  report.checks.push("account fixture saves only its own appended note and discards late source reads when identity expires");

  const full=await setup({user:true,note:"x".repeat(1980)});await full.page.goto(origin+"/assistant");await search(full.page);await full.page.getByText("片段与当前原文一致",{exact:true}).waitFor();
  await full.page.getByRole("button",{name:"加入笔记",exact:true}).click();await full.page.getByText("笔记空间不足：请缩短摘录，或先在我的文献中整理已有笔记",{exact:true}).waitFor();
  assert.equal(await full.page.locator(".evidence-saved").count(),0);assert.equal(full.state.saved.length,0);await full.context.close();report.checks.push("note capacity failure preserves existing note and does not claim save success");

  const answer=await setup({answerMode:true});await answer.page.goto(origin+"/assistant");
  await answer.page.getByRole("button",{name:"发送问题",exact:true}).waitFor();await answer.page.getByRole("textbox",{name:"研究问题",exact:true}).fill("Fixture generated answer question");
  await answer.page.getByRole("button",{name:"发送问题",exact:true}).click();await answer.page.getByText("Controlled fixture answer citing supplied text.",{exact:true}).waitFor();
  assert.ok((await answer.page.locator('.ai-chat-citations a').first().getAttribute('href')).includes('#evidence=1'));
  await answer.page.getByRole("button",{name:"核对引用片段",exact:true}).click();await answer.page.getByText("片段与当前原文一致",{exact:true}).waitFor();
  assert.equal(await answer.page.locator(".evidence-question").textContent(),"Fixture generated answer question");assert.equal(await answer.page.locator(".evidence-source-choice").count(),1);
  await answer.context.close();report.checks.push("controlled answer fixture exposes direct source targets and opens cited passages in the same evidence workbench; not a real provider generation");
  assert.deepEqual(unhandled,[]);assert.deepEqual(errors,[]);report.passed=true;
}finally{
  await browser.close();writeFileSync(join(output,"report.json"),JSON.stringify({...report,unhandled,errors},null,2));console.log(JSON.stringify({...report,output,unhandled,errors}));
}
