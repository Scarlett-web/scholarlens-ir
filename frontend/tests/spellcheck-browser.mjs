/** Real corpus spelling acceptance; no synthetic documents or automatic rewrites. */
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import {createRequire} from "node:module";
const require=createRequire(import.meta.url);
const {chromium}=require(process.env.SCHOLARLENS_PLAYWRIGHT||"playwright");
const origin=process.env.SCHOLARLENS_URL||"http://127.0.0.1:4173";
assert.ok(origin.startsWith("http://127.0.0.1:"));
const output=path.resolve("../output/corpus-expansion/spellcheck-08");
fs.mkdirSync(output,{recursive:true});
const report={status:"running",checks:{},screenshots:[],consoleErrors:[]};
report.suggestionResponses=[];
const browser=await chromium.launch({executablePath:"C:/Program Files/Google/Chrome/Application/chrome.exe",headless:true});
const page=await browser.newPage({viewport:{width:1440,height:1000},reducedMotion:"reduce"});
page.on("pageerror",e=>report.consoleErrors.push(e.message));
page.on("response",async response=>{if(response.url().includes("/api/suggest?")) report.suggestionResponses.push({status:response.status(),body:await response.json().catch(()=>null)});});
page.on("requestfailed",request=>{if(request.url().includes("/api/"))(report.requestFailures??=[]).push(request.url()+": "+request.failure()?.errorText);});
async function shot(name){await page.screenshot({path:path.join(output,name+".png"),fullPage:true});report.screenshots.push(name+".png");}
async function check(name,fn){await fn();report.checks[name]=true;}
try{
  await check("real_api_and_correction",async()=>{
    const stats=await page.request.get(origin+"/api/stats");assert.equal((await stats.json()).indexed,4000);
    const response=await page.request.get(origin+"/api/spellcheck?q=machien%20learning&field=title");
    const body=await response.json();assert.ok(body.suggestions.some(s=>s.text==="machine learning"&&s.matched_count>0));
    fs.writeFileSync(path.join(output,"real-api-example.json"),JSON.stringify(body,null,2));
    for(const q of ["machine learning","MRI","10.1234/example","中文检索"]){
      const r=await page.request.get(origin+"/api/spellcheck?q="+encodeURIComponent(q));assert.deepEqual((await r.json()).suggestions,[]);
    }
  });
  await check("typing_suggestions_and_keyboard",async()=>{
    await page.goto(origin);
    const input=page.locator("#main-search-input");await input.fill("machien learning");
    await page.getByRole("option",{name:/拼写建议：machine learning/}).waitFor();
    assert.equal(await input.inputValue(),"machien learning");
    await shot("typing-desktop");
    await input.press("ArrowDown");await input.press("Enter");
    await page.waitForURL(url=>url.pathname==="/search"&&url.searchParams.get("q")==="machine learning");
    await page.locator(".paper-record").first().waitFor();
  });
  await check("generalized_typing",async()=>{
    await page.goto(origin);
    const input=page.locator("#main-search-input");
    for(const [wrong,expected] of [["machein learning","machine learning"],["infomration retrieval","information retrieval"],["neurla networks","neural networks"],["machinelearning","machine learning"]]){
      await input.fill(wrong);
      await page.getByRole("option",{name:new RegExp("拼写建议："+expected)}).waitFor();
      assert.equal(await input.inputValue(),wrong);
      if(wrong==="machein learning")await shot("generalized-typing");
    }
  });
  await check("zero_results_manual_correction_preserves_conditions",async()=>{
    await page.goto(origin+"/search?q=machein%20learning&field=title&mode=keyword&from=2000&to=2020&sort=newest&page=1");
    const button=page.locator(".spelling-corrections").getByRole("button",{name:"machine learning",exact:true});
    await button.waitFor({timeout:30000});
    assert.equal(new URL(page.url()).searchParams.get("q"),"machein learning");
    await shot("zero-results-desktop");
    await button.click();await page.locator(".paper-record").first().waitFor();
    const params=new URL(page.url()).searchParams;
    for(const [k,v] of Object.entries({q:"machine learning",field:"title",mode:"keyword",from:"2000",to:"2020",sort:"newest",page:"1"}))assert.equal(params.get(k),v);
    await shot("corrected-results");
  });
  await check("mobile_suggestions",async()=>{
    await page.setViewportSize({width:390,height:844});await page.goto(origin);
    await page.locator("#main-search-input").fill("machien learning");
    await page.getByRole("option",{name:/拼写建议：machine learning/}).waitFor();await shot("typing-mobile");
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
    const bottom=page.locator("#main-search-suggestions").getByRole("option").last();
    await bottom.scrollIntoViewIfNeeded();
    assert.ok(await bottom.evaluate(el=>{const r=el.getBoundingClientRect();const top=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);return top===el||el.contains(top);}),"Suggestions must not be covered by the reading card");
  });
  assert.deepEqual(report.consoleErrors,[]);report.status="verified";
}catch(error){report.status="failed";report.error=error.message;report.dom=await page.evaluate(()=>({input:document.querySelector('#main-search-input')?.outerHTML,popover:document.querySelector('.suggestion-popover')?.outerHTML,bodyText:document.body.innerText.slice(0,2000)}));await shot("failure");throw error;}
finally{fs.writeFileSync(path.join(output,"browser-verification.json"),JSON.stringify(report,null,2));await browser.close();}
console.log(JSON.stringify(report,null,2));
