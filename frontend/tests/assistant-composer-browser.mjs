/** Controlled browser regression; all API responses are Mock and no credentials are used. */
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import {createRequire} from "node:module";
const require=createRequire(import.meta.url);
const {chromium}=require(process.env.SCHOLARLENS_PLAYWRIGHT||"playwright");
const origin=process.env.SCHOLARLENS_URL||"http://127.0.0.1:4176";
assert.equal(new URL(origin).hostname,"127.0.0.1");
const output=path.resolve(process.env.SCHOLARLENS_COMPOSER_OUTPUT||"../output/assistant-composer");
fs.mkdirSync(output,{recursive:true});
const report={kind:"Mock browser acceptance",checks:[],errors:[]};
const browser=await chromium.launch({executablePath:"C:/Program Files/Google/Chrome/Application/chrome.exe",headless:true});
const context=await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:"reduce"});
await context.addInitScript(()=>sessionStorage.setItem("scholarlens-session","mock-composer-session"));
const page=await context.newPage();
page.setDefaultTimeout(6000);
page.on("pageerror",error=>report.errors.push(error.message));
const pending=[];
const papers=[1,2].map(id=>({paper_id:"mock-composer-"+id,title:"Mock paper "+id,authors:[],abstract:"Mock abstract",year:2024}));
await context.route("**/api/**",async route=>{
  const p=new URL(route.request().url()).pathname;
  let data=[];
  if(p==="/api/auth/me")data={id:745,username:"mock-composer-user",role:"user"};
  else if(p==="/api/stats")data={indexed:2,status:"real"};
  else if(p==="/api/capabilities")data={modules:{ai_qa:{status:"ready"}}};
  else if(p==="/api/me/workspace")data={version:0,favorites:papers.map(paper=>({paper,collection:"Mock",note:"",savedAt:Date.now()})),history:[],collections:["Mock"]};
  else if(p==="/api/agent/run"){
    let settle;
    const result=new Promise(resolve=>{settle=resolve;});
    pending.push({payload:route.request().postDataJSON(),settle});
    const response=await result;
    try{await route.fulfill(response);}catch(error){if(!/closed|cancel|intercept|invalid/i.test(error.message))throw error;}
    return;
  }
  await route.fulfill({json:data});
});
const input=page.getByRole("textbox",{name:"研究问题"});
const send=page.getByRole("button",{name:"发送问题",exact:true});
const stop=page.getByRole("button",{name:"停止",exact:true});
const check=async(name,action)=>{await action();report.checks.push(name);console.log("PASS "+name);};
const waitUntil=async(predicate)=>{const until=Date.now()+6000;while(!predicate()){assert.ok(Date.now()<until,"Timed out waiting for Mock request");await new Promise(resolve=>setTimeout(resolve,20));}};
async function submit(text,keyboard=false){
  await input.fill(text);
  const count=pending.length;
  if(keyboard)await input.press("Enter");else await send.click();
  await waitUntil(()=>pending.length===count+1);
  await stop.waitFor();
  assert.equal(await input.inputValue(),"","Composer must clear while request is still pending");
  return pending.at(-1);
}
const success=(request,answer="Mock completed answer")=>request.settle({json:{answer,citations:[],evidence:[],evidence_status:"general_answer"}});
const failure=request=>request.settle({status:503,json:{detail:"Mock upstream unavailable"}});
async function idle(){await stop.waitFor({state:"hidden"});}
async function visibleComposer(){
  const box=await input.boundingBox();
  assert.ok(box&&box.y>=0&&box.y+box.height<=page.viewportSize().height,"Composer stays in viewport");
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),"No horizontal overflow");
}
try{
  await page.goto(origin+"/assistant");
  await send.waitFor();
  await check("button submission clears immediately; response preserves next draft; duplicate Enter blocked",async()=>{
    const request=await submit("  Mock first question  ");
    assert.equal(request.payload.question,"Mock first question");
    assert.equal(await page.locator(".from-user p").last().innerText(),"Mock first question");
    await visibleComposer();
    await page.screenshot({path:path.join(output,"desktop-pending-empty.png")});
    await input.fill("Mock next draft");
    const count=pending.length;
    await input.press("Enter");
    assert.equal(pending.length,count);
    success(request);await idle();
    assert.equal(await input.inputValue(),"Mock next draft");
    assert.equal(await page.locator(".from-user p").last().innerText(),"Mock first question");
  });
  await check("Enter submits once; Shift+Enter remains a newline",async()=>{
    await input.fill("Mock line one");await input.press("Shift+Enter");await input.press("x");
    assert.equal(await input.inputValue(),"Mock line one\nx");
    const request=await submit("Mock keyboard question",true);success(request);await idle();
    assert.equal(await input.inputValue(),"");
  });
  await check("failure restores original draft including whitespace",async()=>{
    const request=await submit("  Mock retry question\n ");failure(request);await idle();
    assert.equal(await input.inputValue(),"  Mock retry question\n ");
    assert.match(await page.getByRole("alert").innerText(),/HTTP 503/);
  });
  await check("failure preserves a newly entered draft",async()=>{
    const request=await submit("Mock failing question");await input.fill("Mock newer draft");failure(request);await idle();
    assert.equal(await input.inputValue(),"Mock newer draft");
  });
  await check("stop restores original draft; late completion cannot change a new request",async()=>{
    const stopped=await submit("  Mock stopped question  ");await stop.click();await idle();
    assert.equal(await input.inputValue(),"  Mock stopped question  ");
    const active=await submit("Mock replacement question");await input.fill("Mock protected draft");
    success(stopped,"Mock stale answer");success(active,"Mock replacement answer");await idle();
    assert.equal(await input.inputValue(),"Mock protected draft");
    assert.equal(await page.getByText("Mock stale answer",{exact:true}).count(),0);
    await page.getByText("Mock replacement answer",{exact:true}).waitFor();
  });
  await check("stop preserves a newly entered draft",async()=>{
    const request=await submit("Mock stop without overwrite");await input.fill("Mock draft before stop");await stop.click();await idle();
    success(request);assert.equal(await input.inputValue(),"Mock draft before stop");
  });
  await check("summary and comparison defaults clear immediately and preserve the next draft",async()=>{
    for(const [label,operation,button,count] of [["单篇总结","summarize","生成总结",1],["多篇比较","compare","比较论文",2]]){
      await input.fill("");await page.getByRole("button",{name:"阅读方式",exact:true}).click();
      await page.getByRole("button",{name:label,exact:true}).click();
      const boxes=page.locator(".assistant-paper-options input[type=checkbox]");
      for(let i=0;i<count;i++)await boxes.nth(i).check();
      await page.getByRole("button",{name:"关闭助手工具"}).click();
      const before=pending.length;await page.getByRole("button",{name:button,exact:true}).click();await waitUntil(()=>pending.length===before+1);
      assert.equal(await input.inputValue(),"");const request=pending.at(-1);
      assert.equal(request.payload.operation,operation);assert.equal(request.payload.paper_ids.length,count);assert.ok(request.payload.question.length);
      await input.fill("Mock draft after "+operation);success(request);await idle();
      assert.equal(await input.inputValue(),"Mock draft after "+operation);
    }
  });
  await check("new conversation clears intentionally; empty input cannot send",async()=>{
    await page.getByRole("button",{name:"新对话，清空当前内容"}).click();assert.equal(await input.inputValue(),"");
    await page.getByRole("button",{name:"阅读方式",exact:true}).click();await page.getByRole("button",{name:"论文问答",exact:true}).click();
    await page.getByRole("button",{name:"关闭助手工具"}).click();assert.equal(await send.isDisabled(),true);
  });
  await check("390px mobile clears while waiting and keeps the composer visible",async()=>{
    await page.setViewportSize({width:390,height:844});const request=await submit("Mock mobile question");
    await visibleComposer();await page.screenshot({path:path.join(output,"mobile-pending-empty.png")});
    await input.fill("Mock mobile next draft");success(request);await idle();
    assert.equal(await input.inputValue(),"Mock mobile next draft");await visibleComposer();
  });
  assert.deepEqual(report.errors,[]);report.status="passed";
}catch(error){report.status="failed";report.failure=error.stack;await page.screenshot({path:path.join(output,"failure.png")}).catch(()=>{});throw error;}
finally{for(const request of pending)success(request);fs.writeFileSync(path.join(output,"browser-report.json"),JSON.stringify(report,null,2));await browser.close();console.log(JSON.stringify(report));}
