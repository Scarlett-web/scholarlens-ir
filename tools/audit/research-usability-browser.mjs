/** Read-only real corpus checks in an isolated browser. Never calls a model or changes server data. */
import {chromium} from "playwright";
import assert from "node:assert/strict";
import {mkdirSync,writeFileSync} from "node:fs";
import {fileURLToPath} from "node:url";
import {join} from "node:path";
import {createHash} from "node:crypto";

const origin=process.env.SCHOLARLENS_URL||"http://127.0.0.1:4174";
assert.ok(["127.0.0.1","localhost","scholarlens.lingion.cc.cd"].includes(new URL(origin).hostname));
const output=join(fileURLToPath(new URL("../../",import.meta.url)),"tools/audit/reports/research-usability-"+new Date().toISOString().replace(/[:.]/g,"-"));
mkdirSync(output,{recursive:true});
const report={passed:false,scope:"real corpus, read-only requests, isolated browser; no supplier generation",origin,checks:[]};
const browser=await chromium.launch({channel:"chrome",headless:true});
const context=await browser.newContext({viewport:{width:1440,height:900},reducedMotion:"reduce"});
if(process.env.SCHOLARLENS_PDF_ORIGIN){
  const pdfOrigin=process.env.SCHOLARLENS_PDF_ORIGIN;
  assert.equal(pdfOrigin,'http://127.0.0.1:18091');report.pdf_origin=pdfOrigin;
  await context.route('**/api/papers/**',async route=>{
    assert.equal(route.request().method(),'GET');
    return route.fulfill({response:await context.request.get(pdfOrigin+new URL(route.request().url()).pathname)});
  });
}
const page=await context.newPage(),errors=[];
page.on("pageerror",error=>errors.push(error.message));
const get=async path=>{
  // Chrome follows the Windows network route; the standalone Node client may not.
  if(new URL(origin).hostname==='scholarlens.lingion.cc.cd'){
    const result=await page.evaluate(async path=>{const r=await fetch(path);return {status:r.status,body:await r.json()};},path);
    assert.equal(result.status,200,path);return result.body;
  }
  const r=await context.request.get(origin+path);assert.ok(r.ok(),path+": "+r.status());return r.json();
};
try{
  if(new URL(origin).hostname==='scholarlens.lingion.cc.cd')await page.goto(origin,{waitUntil:'domcontentloaded'});
  const stats=await get('/api/stats');assert.equal(stats.papers,859);
  let pdfPaper;
  for(const [field,q] of [['title','magnetic'],['authors','Archibald'],['date','2004'],['affiliation','CSIRO'],['address','Nedlands'],['fulltext','magnetic']]){
    const params=new URLSearchParams({q,field,page_size:'1'}),data=await get('/api/search?'+params);
    assert.ok(data.total>0&&data.results[0].highlights[field]?.some(v=>v.includes('<em>')),field);
    const hit=data.results[0];if(field==='title')pdfPaper=hit.paper_id;
    assert.ok(Array.isArray(hit.affiliation)&&Array.isArray(hit.address)&&typeof hit.date==='string');
    await page.goto(origin+'/search?'+new URLSearchParams({q,field}));
    const row=page.locator('.paper-record').first();await row.waitFor();
    const mark=row.locator(field==='title'?'.paper-title-link mark':`[data-field="${field}"] mark`).first();
    await mark.waitFor();assert.ok((await mark.textContent()).toLowerCase().includes(q.toLowerCase()));
    assert.equal(await row.locator('mark').evaluateAll((marks,field)=>marks.every(mark=>field==='title'?Boolean(mark.closest('.paper-title-link')):Boolean(mark.closest(`[data-field="${field}"]`))||field==='date'&&Boolean(mark.closest('.paper-record-year'))),field),true,'Highlights must respect '+field);
    if(field==='fulltext')await row.getByText('全文命中',{exact:true}).waitFor();
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
    if(['affiliation','fulltext'].includes(field))await page.screenshot({path:join(output,field+'-desktop.png')});
    report.checks.push({field,q,total:data.total,highlight:true});
  }
  const exactTitle='Simulating the Dynamics of the Dancing Lights';
  const exact=await get('/api/search?'+new URLSearchParams({q:exactTitle}));
  assert.equal(exact.total,1);assert.equal(exact.results[0].title,exactTitle);
  assert.deepEqual(exact.results[0].highlights,{title:['<em>'+exactTitle+'</em>']});
  await page.goto(origin+'/search?'+new URLSearchParams({q:exactTitle}));
  const exactRow=page.locator('.paper-record').first();await exactRow.waitFor();
  assert.deepEqual(await exactRow.locator('mark').allTextContents(),[exactTitle]);
  assert.equal(await exactRow.locator('.paper-abstract mark,.paper-hit-label').count(),0);
  assert.equal(await page.getByText(/检索分数/).count(),0);assert.equal(await page.locator('.page-heading p').count(),0);
  assert.equal(await exactRow.locator('.paper-author').count(),3);
  await exactRow.getByRole('button',{name:'更多作者（还有 1 位）',exact:true}).click();
  assert.equal(await exactRow.locator('.paper-author').count(),4);
  assert.ok((await exactRow.locator('[data-field="authors"]').textContent()).includes('Ian Bell'));
  await page.screenshot({path:join(output,'exact-title-desktop.png')});
  report.checks.push({exact_title:true,title_only_highlight:true,incidental_body_highlights:false,full_author_list:true,score_hidden:true});
  const capabilities=await get('/api/capabilities');
  for(const mode of ['semantic','hybrid']){
    if(capabilities.modules[mode+'_search']?.status!=='ready'){report.checks.push({mode,title_only_highlight:'unavailable'});continue;}
    const ranked=await get('/api/search?'+new URLSearchParams({q:exactTitle,mode,page_size:'20'}));
    const same=ranked.results.find(hit=>hit.paper_id===exact.results[0].paper_id);
    assert.ok(same,'Exact title must remain a candidate in '+mode);
    assert.deepEqual(same.highlights,{title:['<em>'+exactTitle+'</em>']});
    report.checks.push({mode,title_only_highlight:true,total:ranked.total,original_score:same.score});
  }
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.screenshot({path:join(output,'search-390.png')});
  await page.setViewportSize({width:1440,height:900});
  await page.goto(origin+'/paper/'+encodeURIComponent(pdfPaper));
  await page.getByRole('button',{name:'下载 PDF',exact:true}).waitFor();
  const pending=page.waitForEvent('download');await page.getByRole('button',{name:'下载 PDF',exact:true}).click();
  const download=await pending;assert.match(download.suggestedFilename(),/\.pdf$/i);
  const stream=await download.createReadStream(),hash=createHash('sha256');let prefix=Buffer.alloc(0),bytes=0;
  for await(const chunk of stream){if(prefix.length<5)prefix=Buffer.concat([prefix,chunk]).subarray(0,5);hash.update(chunk);bytes+=chunk.length;}
  assert.equal(prefix.toString(),'%PDF-');assert.ok(bytes>1000);
  report.checks.push({pdf_download:true,bytes,sha256:hash.digest('hex')});
  await page.screenshot({path:join(output,'pdf-detail-desktop.png')});
  await page.goto(origin+'/assistant');await page.getByRole('textbox',{name:'研究问题',exact:true}).waitFor();
  for(const viewport of [{width:1366,height:768},{width:1440,height:900}]){
    await page.setViewportSize(viewport);await page.evaluate(()=>scrollTo(0,0));
    assert.ok(await page.getByRole('button',{name:'检索原文',exact:true}).evaluate(el=>el.getBoundingClientRect().bottom<=innerHeight));
    assert.ok(await page.locator('.ai-conversation').evaluate(el=>el.clientHeight>=270));
  }
  await page.screenshot({path:join(output,'assistant-desktop.png')});
  assert.deepEqual(errors,[]);report.passed=true;
}finally{await browser.close();writeFileSync(join(output,'report.json'),JSON.stringify({...report,errors},null,2));console.log(JSON.stringify({...report,output,errors}));}
