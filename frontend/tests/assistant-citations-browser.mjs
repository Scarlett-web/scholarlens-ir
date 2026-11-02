/** Mock API browser acceptance: no provider credentials, production requests or corpus writes. */
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import {createRequire} from "node:module";
const require=createRequire(import.meta.url);
const {chromium}=require(process.env.SCHOLARLENS_PLAYWRIGHT||"playwright");
const origin=process.env.SCHOLARLENS_URL||"http://127.0.0.1:4176";
assert.equal(new URL(origin).hostname,"127.0.0.1");
const output=path.resolve("../output/assistant-citations");
fs.mkdirSync(output,{recursive:true});
const a={paper_id:"mock-citation-a",paper_title:"Mock 中文论文 A",chunk_id:"chunk:"+"a".repeat(64),quote:'Mock 原文 A：<img src=x onerror="window.__unsafe=true">，保持逐字文本。',locator:"abstract:chars:0-120"};
const b={paper_id:"mock-citation-b",paper_title:"Mock English paper B",chunk_id:"chunk:"+"b".repeat(64),quote:"Mock exact source B & Unicode βeta.",locator:"fulltext:chars:30-160"};
const c={...a,chunk_id:"chunk:"+"c".repeat(64),quote:"Mock 论文 A 的第二个片段。",locator:"fulltext:chars:200-240"};
const body=`先引用另一篇文献 [${b.chunk_id}]，再引用中文文献 [${a.chunk_id}]。重复使用 [${b.chunk_id}]。\n\n`+
  `长回答用于布局验收 [${c.chunk_id}]。\n\n`.repeat(32);
const papers=[a,b].map(item=>({paper_id:item.paper_id,title:item.paper_title,authors:[],abstract:item.quote,fulltext:" ".repeat(30)+item.quote+" ".repeat(160),year:2024}));
const report={kind:"Mock browser acceptance",checks:[],errors:[],requests:[]};
const browser=await chromium.launch({executablePath:"C:/Program Files/Google/Chrome/Application/chrome.exe",headless:true});
const context=await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:"reduce"});
await context.addInitScript(()=>{
  sessionStorage.setItem("scholarlens-session","mock-browser-session");
  Object.defineProperty(navigator,"clipboard",{value:{writeText:async text=>{window.__copied=text;}}});
});
const page=await context.newPage();
page.on("pageerror",error=>report.errors.push(error.message));
await context.route("**/api/**",async route=>{
  const url=new URL(route.request().url()),p=url.pathname;
  let data;
  if(p==="/api/auth/me")data={id:741,username:"mock-browser-user",role:"user"};
  else if(p==="/api/stats")data={indexed:2,status:"real"};
  else if(p==="/api/capabilities")data={modules:{ai_qa:{status:"ready"}}};
  else if(p==="/api/me/workspace")data={version:0,favorites:papers.map(paper=>({paper,collection:"Mock",note:"",savedAt:Date.now()})),history:[],collections:["Mock"]};
  else if(p==="/api/ai/conversations")data=[{id:"mock-history",title:"Mock 历史对话",message_count:3,updated_at:"2026-11-02"}];
  else if(p==="/api/ai/conversations/mock-history/messages")data=[{role:"user",content:"Mock 历史问题",citations:[]},{role:"assistant",content:`历史回答 [${a.chunk_id}] 缺少来源 [chunk:unknown]。`,citations:[{...a,locator:""}]},{role:"assistant",content:"Mock 通用回答，没有文献引用。",citations:[]}];
  else if(p==="/api/agent/run"){
    const payload=route.request().postDataJSON();report.requests.push(payload);
    data={answer:body,citations:[a,c,b],evidence:[],evidence_status:"sufficient"};
  }else if(p.startsWith("/api/papers/"))data=papers.find(paper=>paper.paper_id===decodeURIComponent(p.split("/").at(-1)));
  else data=[];
  await route.fulfill({json:data??{}});
});
const check=async(name,fn)=>{await fn();report.checks.push(name);};
const screenshot=async name=>page.screenshot({path:path.join(output,name+".png")});
async function composerVisible(){
  await page.waitForFunction(()=>{const el=document.querySelector('textarea[aria-label="研究问题"]');const r=el?.getBoundingClientRect();return r&&r.y>=0&&r.bottom<=innerHeight;},{},{timeout:3000});
  const rect=await page.getByRole("textbox",{name:"研究问题"}).boundingBox();
  assert.ok(rect&&rect.y>=0&&rect.y+rect.height<=page.viewportSize().height,"Composer must stay visible");
  const geometry=await page.evaluate(()=>({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,overflow:[...document.querySelectorAll("body *")].filter(el=>{const r=el.getBoundingClientRect();return r.width>0&&r.right>innerWidth+1;}).slice(0,15).map(el=>({tag:el.tagName,className:el.className,right:el.getBoundingClientRect().right}))}));
  assert.ok(geometry.scrollWidth<=geometry.width+1,JSON.stringify(geometry));
}
try{
  await page.goto(origin+"/assistant");
  await page.getByRole("button",{name:"发送问题",exact:true}).waitFor();
  await check("live multi-paper citations and repeated numbers",async()=>{
    await page.getByRole("textbox",{name:"研究问题"}).fill("Mock 比较这两篇文献的研究思路");
    await page.getByRole("button",{name:"发送问题",exact:true}).click();
    await page.locator(".assistant-inline-citation").first().waitFor();
    assert.deepEqual((await page.locator(".assistant-inline-citation").allTextContents()).slice(0,4),["[1]","[2]","[1]","[3]"]);
    assert.ok(!(await page.locator(".assistant-answer-text").innerText()).includes("chunk:"));
    assert.match(await page.locator(".assistant-source-link").first().innerText(),/Mock English paper B/);
    await composerVisible();
    assert.ok(await page.locator(".ai-conversation").evaluate(el=>el.scrollHeight>el.clientHeight));
    await page.locator(".ai-conversation").evaluate(el=>el.scrollTop=0);
    await screenshot("desktop-numbered-answer");
  });
  await check("click, correct paper target, exact excerpt and keyboard close",async()=>{
    const button=page.locator(".assistant-inline-citation").first();await button.click();
    const dialog=page.getByRole("dialog");await dialog.waitFor();
    assert.match(await dialog.innerText(),/Mock exact source B & Unicode βeta/);
    const href=await dialog.getByRole("link").getAttribute("href");
    assert.ok(href.startsWith("/paper/"+b.paper_id+"#"));
    assert.equal(new URLSearchParams(href.split("#")[1]).get("quote"),b.quote);
    await screenshot("desktop-citation-detail");
    const opened=context.waitForEvent("page");await dialog.getByRole("link").click();
    const paperPage=await opened;await paperPage.locator("#paper-evidence-match").waitFor();
    assert.equal(await paperPage.locator("#paper-evidence-match").innerText(),b.quote);
    await paperPage.close();
    await page.keyboard.press("Escape");await dialog.waitFor({state:"hidden"});
    assert.equal(await button.evaluate(el=>document.activeElement===el),true);
    await page.locator(".assistant-inline-citation").nth(1).click();
    assert.equal(await dialog.locator("blockquote").innerText(),a.quote);
    assert.equal(await dialog.locator("img").count(),0);assert.equal(await page.evaluate(()=>window.__unsafe),undefined);
    await dialog.getByRole("button",{name:"关闭引用原文"}).click();
  });
  await check("copy keeps numbers and sources, hides internal IDs",async()=>{
    await page.getByRole("button",{name:"复制最后一条回答"}).click();
    const copied=await page.evaluate(()=>window.__copied);
    assert.ok(copied.includes("[1]"));assert.ok(copied.includes("Mock English paper B"));assert.ok(!copied.includes("chunk:"));
  });
  await check("summary and comparison use the same rendering",async()=>{
    for(const [label,operation,send,count] of [["单篇总结","summarize","生成总结",1],["多篇比较","compare","比较论文",2]]){
      await page.getByRole("button",{name:"阅读方式",exact:true}).click();
      await page.getByRole("button",{name:label,exact:true}).click();
      const boxes=page.locator(".assistant-paper-options input[type=checkbox]");
      for(let i=0;i<count;i++)await boxes.nth(i).check();
      await page.getByRole("button",{name:"关闭助手工具"}).click();
      await page.getByRole("button",{name:send,exact:true}).click();
      await page.waitForFunction(expected=>document.querySelectorAll(".assistant-answer-text").length===expected,operation==="summarize"?2:3);
      assert.equal(report.requests.at(-1).operation,operation);assert.equal(report.requests.at(-1).paper_ids.length,count);
      await composerVisible();
    }
  });
  await check("mobile long answer and citation window stay in viewport",async()=>{
    await page.setViewportSize({width:390,height:844});
    await composerVisible();
    await page.locator(".assistant-inline-citation").last().click();
    const dialog=page.getByRole("dialog");
    const rect=await dialog.boundingBox();assert.ok(rect&&rect.x>=0&&rect.x+rect.width<=390&&rect.y>=0&&rect.y+rect.height<=844);
    await screenshot("mobile-citation-detail");
    await page.keyboard.press("Escape");
    await screenshot("mobile-answer-composer");
    await page.setViewportSize({width:1440,height:600});await composerVisible();
  });
  await check("saved conversation, missing source and general answers",async()=>{
    await page.setViewportSize({width:1440,height:1000});
    await page.getByRole("button",{name:"对话记录",exact:true}).click();
    await page.getByRole("combobox",{name:"研究对话"}).selectOption("mock-history");
    await page.getByRole("button",{name:"关闭助手工具"}).click();
    await page.locator(".assistant-citation-missing").waitFor();
    assert.equal(await page.locator(".assistant-inline-citation").count(),1);
    await page.locator(".assistant-inline-citation").click();
    const dialog=page.getByRole("dialog");assert.match(await dialog.innerText(),/原文位置暂不可识别/);
    assert.equal(await dialog.getByRole("link").getAttribute("href"),"/paper/"+a.paper_id);
    await page.keyboard.press("Escape");await composerVisible();await screenshot("history-citations");
  });
  assert.deepEqual(report.errors,[]);report.status="passed";
}catch(error){report.status="failed";report.failure=error.stack;await screenshot("failure");throw error;}
finally{fs.writeFileSync(path.join(output,"browser-report.json"),JSON.stringify(report,null,2));await browser.close();console.log(JSON.stringify({...report,requests:report.requests.map(({operation,paper_ids})=>({operation,paper_ids}))}));}
