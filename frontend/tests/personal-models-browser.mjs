/** Isolated Mock API acceptance. No real accounts, provider keys or generation. */
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import {createRequire} from "node:module";
const require=createRequire(import.meta.url);
const {chromium}=require(process.env.SCHOLARLENS_PLAYWRIGHT||"playwright");
const origin=process.env.SCHOLARLENS_URL||"http://127.0.0.1:4176";
assert.equal(new URL(origin).hostname,"127.0.0.1");
const output=path.resolve("../output/personal-models");
fs.mkdirSync(output,{recursive:true});
const report={kind:"Mock API browser acceptance",checks:[],errors:[],modelRequests:[],testRequests:[],externalRequests:[]};
const browser=await chromium.launch({executablePath:process.env.SCHOLARLENS_CHROME||"C:/Program Files/Google/Chrome/Application/chrome.exe",headless:true});
let userId=741,catalogMode="ok",releaseFetch;
const secret="mock-only-model-picker-key";
const context=await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:"reduce"});
await context.addInitScript(()=>sessionStorage.setItem("scholarlens-session","mock-model-picker-session"));
await context.route("**/*",async route=>{
  const request=route.request(),url=new URL(request.url());
  if(url.origin!==origin){report.externalRequests.push(url.origin);await route.abort();return;}
  if(!url.pathname.startsWith("/api/")){await route.continue();return;}
  const p=url.pathname;
  let data=[];
  if(p==="/api/auth/me")data={id:userId,username:"mock-model-user-"+userId,role:"user"};
  else if(p==="/api/stats")data={papers:859,status:"real"};
  else if(p==="/api/capabilities")data={modules:{ai_qa:{status:"not_configured"},keyword_search:{status:"ready"}}};
  else if(p==="/api/me/workspace")data={version:0,favorites:[],history:[],collections:[]};
  else if(p==="/api/ai/models"){
    const h=request.headers();
    assert.equal(h["x-scholarlens-ai-key"],secret);
    report.modelRequests.push({model:h["x-scholarlens-ai-model"],url:h["x-scholarlens-ai-url"]});
    if(catalogMode==="slow")await new Promise(resolve=>{releaseFetch=resolve;});
    if(catalogMode==="error"){await route.fulfill({status:502,json:{error:{code:"ai_authentication_failed",message:"个人 API 认证失败，请检查密钥"}}});return;}
    data={models:catalogMode==="empty"?[]:["mock-chat-a","mock-chat-b","mock-reasoning",...Array.from({length:50},(_,i)=>"mock-extra-"+i),"mock-chat-a","invalid model",null,17]};
  }else if(p==="/api/ai/test"){
    const h=request.headers();
    assert.equal(h["x-scholarlens-ai-key"],secret);
    report.testRequests.push({model:h["x-scholarlens-ai-model"],url:h["x-scholarlens-ai-url"]});
    data={status:"ready",model:h["x-scholarlens-ai-model"],protocol:h["x-scholarlens-ai-protocol"]};
  }
  await route.fulfill({json:data});
});
const page=await context.newPage();
page.on("pageerror",error=>report.errors.push(error.message));
const settings=page.getByRole("region",{name:"个人 API 设置",exact:true});
const current=page.getByLabel("个人API模型",{exact:true});
const fetchModels=page.getByRole("button",{name:"获取模型",exact:true});
const save=page.getByRole("button",{name:"保存个人配置",exact:true});
const check=async(name,action)=>{await action();report.checks.push(name);console.log("PASS "+name);};
async function open(){await page.goto(origin+"/assistant");await page.getByRole("button",{name:"API 设置",exact:true}).click();await settings.waitFor();}
async function feedback(text){await page.getByRole("status").filter({hasText:text}).waitFor();}
try{
  await open();
  await check("fetch needs only URL and session-only key, no model or generation",async()=>{
    assert.equal(await fetchModels.isDisabled(),true);
    await page.getByLabel("个人API地址",{exact:true}).fill("https://models.example/v1");
    await page.getByLabel("个人API密钥",{exact:true}).fill(secret);
    assert.equal(await current.isDisabled(),true);
    catalogMode="slow";await fetchModels.click();
    await page.waitForFunction(()=>document.querySelector('[aria-label="个人API地址"]').disabled);
    assert.equal(await page.getByRole("button",{name:"正在获取…",exact:true}).isDisabled(),true);
    for(let attempt=0;!releaseFetch&&attempt<500;attempt++)await new Promise(resolve=>setTimeout(resolve,10));
    assert.equal(typeof releaseFetch,"function","Model request must reach the isolated fixture");
    releaseFetch();catalogMode="ok";
    await page.getByLabel("筛选服务商模型",{exact:true}).waitFor();
    assert.equal(report.modelRequests[0].model,"");assert.equal(report.testRequests.length,0);
    assert.equal(await settings.getByRole("checkbox").count(),53);
    assert.equal(await current.inputValue(),"");
    assert.equal(await page.evaluate(()=>JSON.stringify(localStorage).includes("mock-only-model-picker-key")),false);
  });
  await check("filter, batch selection, explicit add and retain existing current model",async()=>{
    await page.getByLabel("筛选服务商模型",{exact:true}).fill("MOCK-CHAT");
    assert.equal(await settings.getByRole("checkbox").count(),2);
    await page.getByRole("button",{name:"选择筛选结果",exact:true}).click();
    await page.getByRole("button",{name:"加入可选模型（2）",exact:true}).click();
    assert.equal(await current.inputValue(),"mock-chat-a");
    await page.getByLabel("筛选服务商模型",{exact:true}).fill("reasoning");
    await page.getByRole("checkbox",{name:"添加 mock-reasoning",exact:true}).check();
    await page.getByRole("button",{name:"加入可选模型（1）",exact:true}).click();
    assert.equal(await current.inputValue(),"mock-chat-a");
    await current.selectOption("mock-chat-b");await save.click();await feedback("配置已保存");
    const state=await page.evaluate(()=>({pref:JSON.parse(localStorage.getItem("scholarlens-ai-preferences:741")),key:sessionStorage.getItem("scholarlens-ai-key:741")}));
    assert.equal(state.pref.model,"mock-chat-b");assert.deepEqual(state.pref.preferredModels,["mock-chat-a","mock-chat-b","mock-reasoning"]);
    assert.equal("key" in state.pref,false);assert.equal(state.key,secret);
    await page.screenshot({path:path.join(output,"desktop-model-picker.png")});
  });
  await check("connection test sends chosen model, reload persists shortlist without fetching",async()=>{
    await page.getByRole("button",{name:"测试连接",exact:true}).click();await feedback("连接成功");
    assert.equal(report.testRequests.at(-1).model,"mock-chat-b");
    const count=report.modelRequests.length;await open();
    assert.equal(await current.inputValue(),"mock-chat-b");assert.equal(await current.locator("option").count(),4);
    assert.equal(report.modelRequests.length,count);
  });
  await check("current removal requires a new choice; manual add validates and deduplicates",async()=>{
    await page.getByRole("button",{name:"移除 mock-chat-b",exact:true}).click();
    assert.equal(await current.inputValue(),"");assert.equal(await save.isDisabled(),true);
    await current.selectOption("mock-chat-a");
    const manual=page.getByLabel("手动模型名称",{exact:true});
    await manual.fill("invalid model");await page.getByRole("button",{name:"添加",exact:true}).click();
    await page.getByRole("alert").filter({hasText:"有效的模型名称"}).waitFor();
    await manual.fill("custom-model");await manual.press("Enter");
    assert.equal(await current.inputValue(),"mock-chat-a");
    await manual.fill("custom-model");await page.getByRole("button",{name:"添加",exact:true}).click();
    assert.equal(await current.locator('option[value="custom-model"]').count(),1);
    await current.selectOption("custom-model");await save.click();await feedback("配置已保存");
  });
  await check("empty and failed provider lists allow manual fallback and preserve saved choice",async()=>{
    catalogMode="empty";await fetchModels.click();await feedback("没有返回模型名称");
    assert.equal(await current.inputValue(),"custom-model");
    catalogMode="error";await fetchModels.click();
    await page.getByRole("alert").filter({hasText:"认证失败"}).waitFor();
    assert.equal(await current.inputValue(),"custom-model");
    await page.getByLabel("手动模型名称",{exact:true}).fill("manual-fallback");
    await page.getByRole("button",{name:"添加",exact:true}).click();
    assert.equal(await current.locator('option[value="manual-fallback"]').count(),1);
  });
  await check("changing endpoint clears prior catalog and models without saving over old configuration",async()=>{
    await page.getByLabel("个人API地址",{exact:true}).fill("https://different.example/v1");
    assert.equal(await current.isDisabled(),true);assert.equal(await current.inputValue(),"");
    assert.equal(await page.getByLabel("获取到的模型",{exact:true}).count(),0);
    const pref=await page.evaluate(()=>JSON.parse(localStorage.getItem("scholarlens-ai-preferences:741")));
    assert.equal(pref.url,"https://models.example/v1");assert.equal(pref.model,"custom-model");
  });
  await check("legacy single-model preferences migrate and different accounts stay isolated",async()=>{
    const first=await page.evaluate(()=>localStorage.getItem("scholarlens-ai-preferences:741"));
    await page.evaluate(()=>{localStorage.setItem("scholarlens-ai-preferences:742",JSON.stringify({url:"https://legacy.example/v1",model:"legacy-model",tokenParameter:"max_tokens"}));sessionStorage.setItem("scholarlens-ai-key:742","mock-only-legacy-key");});
    userId=742;await open();
    assert.equal(await current.inputValue(),"legacy-model");assert.equal(await current.locator("option").count(),2);
    assert.equal(await page.getByLabel("个人API密钥",{exact:true}).inputValue(),"mock-only-legacy-key");
    await page.getByRole("button",{name:"清除个人配置",exact:true}).click();
    assert.equal(await current.isDisabled(),true);
    const state=await page.evaluate(()=>({a:localStorage.getItem("scholarlens-ai-preferences:741"),b:localStorage.getItem("scholarlens-ai-preferences:742"),key:sessionStorage.getItem("scholarlens-ai-key:742")}));
    assert.equal(state.a,first);assert.equal(state.b,null);assert.equal(state.key,null);
  });
  assert.deepEqual(report.errors,[]);assert.deepEqual(report.externalRequests,[]);
  report.status="PASS";console.log("PASS personal model picker: "+report.checks.length+" groups (Mock API)");
}catch(error){report.status="FAIL";report.failure=String(error);await page.screenshot({path:path.join(output,"failure.png")});throw error;}
finally{fs.writeFileSync(path.join(output,"browser-report.json"),JSON.stringify(report,null,2));await browser.close();}
