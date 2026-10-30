/** Real local corpus UI acceptance. Requires an API production preview at :4173. */
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import {createRequire} from "node:module";
const require = createRequire(import.meta.url);
const {chromium} = require(process.env.SCHOLARLENS_PLAYWRIGHT || "playwright");
const origin = process.env.SCHOLARLENS_URL || "http://127.0.0.1:4173";
assert.ok(origin.startsWith("http://127.0.0.1:"), "Local acceptance only");
const output = path.resolve("../output/corpus-expansion/frontend-06");
fs.mkdirSync(output,{recursive:true});
const records = fs.readFileSync("../output/corpus-expansion/prepare-02/merged_papers.jsonl","utf8").trim().split("\n").map(JSON.parse);
const report = {status:"running",origin,checks:{},screenshots:[],consoleErrors:[]};
const browser = await chromium.launch({executablePath:"C:/Program Files/Google/Chrome/Application/chrome.exe",headless:true});
const page = await browser.newPage({viewport:{width:1440,height:1000},reducedMotion:"reduce"});
page.on("pageerror",error=>report.consoleErrors.push(error.message));
async function shot(name){await page.screenshot({path:path.join(output,name+".png"),fullPage:true});report.screenshots.push(name+".png");}
async function check(name,fn){await fn();report.checks[name]=true;}
async function search(q,mode="keyword",extra=""){
  await page.goto(origin+"/search?q="+encodeURIComponent(q)+"&mode="+mode+extra);
  await page.locator(".paper-record").first().waitFor({timeout:90000});
}
try {
  await check("home_real_total",async()=>{
    await page.goto(origin);
    await page.getByText("真实论文库 · 4,000 篇",{exact:true}).waitFor({timeout:30000});
    await shot("home-desktop");
  });
  for(const mode of ["keyword","semantic","hybrid"]){
    await check(mode+"_ui",async()=>{await search("information retrieval",mode);await shot("search-"+mode);});
  }
  await check("pagination_and_highlight",async()=>{
    await search("the");
    assert.ok(await page.locator(".paper-record mark, .paper-record em").count());
    const ids=await page.locator(".paper-record").evaluateAll(nodes=>nodes.map(n=>n.dataset.paperId));
    await page.getByRole("button",{name:"下一页",exact:true}).click();
    await page.waitForURL(/page=2/);
    await page.waitForFunction(before=>{const nodes=[...document.querySelectorAll('.paper-record')];return nodes.length>0&&nodes.every(n=>!before.includes(n.dataset.paperId));},ids);
  });
  await check("year_filter_sort",async()=>{
    await search("the","keyword","&from=2000&to=2020&sort=newest");
    const years=(await page.locator('.paper-record-year').allTextContents()).map(Number);
    assert.ok(years.length>0&&years.every(y=>y>=2000&&y<=2020));
    assert.deepEqual(years,[...years].sort((a,b)=>b-a));
  });
  for(const [batch,record] of [["old",records[0]],["new",records[859]]]){
    await check(batch+"_paper_search_detail",async()=>{
      await search(record.title,"keyword","&field=title");
      const target=page.locator('.paper-record[data-paper-id="'+record.paper_id+'"] a').first();
      await target.click();
      await page.locator(".detail-page").waitFor();
      if(batch==="old") await page.getByText("PDF 尚不可用",{exact:true}).waitFor();
      else {
        await page.getByRole("button",{name:"在线阅读 PDF",exact:true}).click();
        await page.locator("iframe.embedded-reader-frame").waitFor();
        const response=await page.request.get(origin+"/api/papers/"+encodeURIComponent(record.paper_id)+"/pdf",{headers:{Range:"bytes=0-4"}});
        assert.equal(response.status(),206);assert.equal((await response.body()).toString(),"%PDF-");
      }
      await shot("detail-"+batch);
    });
  }
  await check("explore_candidates",async()=>{
    await page.goto(origin+"/explore");
    await page.getByText("论文库 · 4,000 篇",{exact:true}).waitFor();
    await page.getByRole("link",{name:"前往全库检索"}).waitFor();
    await shot("explore-desktop");
  });
  await check("mobile_390",async()=>{
    await page.setViewportSize({width:390,height:844});
    await page.goto(origin);await page.getByText("真实论文库 · 4,000 篇",{exact:true}).waitFor();await shot("home-mobile");
    await search("information retrieval");await shot("search-mobile");
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),"Mobile horizontal overflow");
  });
  assert.deepEqual(report.consoleErrors,[]);
  report.status="verified";
} catch(error){report.status="failed";report.error=error.message;await shot("failure");throw error;}
finally{fs.writeFileSync(path.join(output,"browser-verification.json"),JSON.stringify(report,null,2));await browser.close();}
console.log(JSON.stringify(report,null,2));
