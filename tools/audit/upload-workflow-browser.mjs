/** Local interface fixtures only. Never sends fixture uploads/reviews to a real backend. */
import {chromium} from "playwright";
import assert from "node:assert/strict";
import {mkdirSync,readFileSync,writeFileSync} from "node:fs";
import {join} from "node:path";
import {fileURLToPath} from "node:url";

const origin = process.env.SCHOLARLENS_URL || "http://127.0.0.1:4174";
assert.ok(["127.0.0.1","localhost","[::1]"].includes(new URL(origin).hostname),"Fixtures require a local frontend preview");
const root = fileURLToPath(new URL("../../",import.meta.url));
const reportDir = process.env.SCHOLARLENS_REPORT_DIR || join(root,"tools/audit/reports/upload-workflow-"+new Date().toISOString().replace(/[:.]/g,"-"));
mkdirSync(reportDir,{recursive:true});
const pdf = readFileSync(join(root,"frontend/tests/fixtures/browser-upload.pdf"));
const report = {scope:"isolated browser API fixtures; not real authentication, parsing or indexing",passed:false,checks:[]};
const browser = await chromium.launch({channel:"chrome",headless:true});
const unhandled = [], errors = [];
const makeRows = () => ["pending","approved","processing","indexed","failed","dependency_unavailable","rejected","future_backend_state"].map((status,index)=>({
  id:"fixture-"+status,original_name:"fixture-"+status+".pdf",size:pdf.length,status,
  reason:status==="failed"?"pdf_requires_ocr":status==="rejected"?"Fixture reviewer requested the original source":"",
  created_at:"2026-10-28T04:00:00Z",updated_at:"2026-10-28T04:01:00Z",attempts:status==="pending"?0:1,
  paper_id:status==="indexed"?"upload:fixture-indexed":null,archived:false,
}));
async function setup(role) {
  const context = await browser.newContext({viewport:{width:1440,height:960},reducedMotion:"reduce"});
  const state = {rows:makeRows(),uploads:0,previews:0,lists:0,activeLists:0,maxLists:0,failNext:false,delayNext:0,previewGate:null,decisions:[],archives:[]};
  if(role) await context.addInitScript(()=>sessionStorage.setItem("scholarlens-session","fixture-session-not-a-credential"));
  await context.route("**/api/**",async route => {
    const req = route.request(), url = new URL(req.url()), path = url.pathname.slice(4), method = req.method();
    const json = (data,status=200) => route.fulfill({status,contentType:"application/json",body:JSON.stringify(data)});
    if(path==="/stats") return json({status:"real",papers:859,years:[]});
    if(path==="/capabilities") return json({modules:{keyword_search:{status:"ready"},semantic_search:{status:"ready"},hybrid_search:{status:"ready"}}});
    if(path==="/auth/me") return json({id:role==="admin"?902:901,username:"fixture-"+role,role});
    if(path==="/me/workspace") return json({version:0,favorites:[],history:[],collections:[]});
    if((path==="/uploads"||path==="/admin/uploads")&&method==="GET") {
      state.lists++; state.activeLists++; state.maxLists=Math.max(state.maxLists,state.activeLists);
      const fail=state.failNext, delay=state.delayNext;state.failNext=false;state.delayNext=0;
      try {
        if(delay)await new Promise(r=>setTimeout(r,delay));
        if(fail)return await json({error:{message:"Fixture queue temporarily unavailable",code:"fixture_unavailable"}},503);
        const rows=url.searchParams.get("page")==="2"?[{...state.rows[0],id:"fixture-page-two",original_name:"fixture-page-two.pdf"}]:state.rows;
        return await json({results:rows,total:27});
      } finally {state.activeLists--;}
    }
    if((path==="/uploads"||path==="/admin/uploads")&&method==="POST") {
      state.uploads++;
      const row={...state.rows[0],id:"fixture-new",original_name:"browser-upload.pdf",status:"pending"};
      state.rows=[row,...state.rows];return json(row);
    }
    if(path.endsWith("/pdf")) {
      state.previews++;if(state.previewGate)await state.previewGate;
      return route.fulfill({status:200,contentType:"application/pdf",body:pdf});
    }
    if(path.endsWith("/docx")) return route.fulfill({status:200,contentType:"application/vnd.openxmlformats-officedocument.wordprocessingml.document",body:Buffer.from("fixture-conversion-response")});
    if(path.endsWith("/review")) {
      const id=path.split("/").at(-2), body=req.postDataJSON();state.decisions.push({id,...body});
      const row=state.rows.find(row=>row.id===id);row.status=body.decision==="approve"?"approved":"rejected";row.reason=body.reason;return json(row);
    }
    if(path.endsWith("/process")) {const row=state.rows.find(row=>row.id===path.split("/").at(-2));row.status="processing";row.attempts++;return json(row,202);}
    if(path==="/admin/uploads/vectorize")return json({status:"dependency_unavailable",chunks:0});
    if(path.startsWith("/admin/uploads/")&&method==="DELETE") {
      const id=path.split("/").at(-1);state.archives.push(id);state.rows=state.rows.filter(row=>row.id!==id);
      return json({archived:true,source_preserved:true,indexed_document_preserved:true});
    }
    unhandled.push(method+" "+path);return json({error:{message:"Missing explicit fixture",code:"missing_fixture"}},501);
  });
  const page = await context.newPage();page.on("pageerror",error=>errors.push(error.message));
  return {context,page,state};
}
async function screenshot(page,name) {
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,name+" must fit the viewport");
  await page.screenshot({path:join(reportDir,name+".png"),fullPage:false});
}
try {
  const guest=await setup(null);
  await guest.page.goto(origin+"/upload");await guest.page.getByRole("heading",{name:"登录后，进度随账户保存"}).waitFor();
  assert.equal(await guest.page.locator("input[type=file]").count(),0);
  assert.equal(guest.state.lists,0);await screenshot(guest.page,"guest-upload-desktop");
  await guest.page.setViewportSize({width:390,height:844});await screenshot(guest.page,"guest-upload-390");
  await guest.page.goto(origin+"/admin");await guest.page.getByRole("heading",{name:"登录管理员账户后审核"}).waitFor();
  assert.equal(await guest.page.locator(".review-console-overview strong").allTextContents().then(x=>x.every(t=>t.includes("—"))),true);
  assert.equal(guest.state.lists,0);await guest.context.close();report.checks.push("guest workspace and admin gate make no private queue requests or fabricated zero counts");

  const user=await setup("user");await user.page.goto(origin+"/upload");await user.page.locator(".server-upload-row").first().waitFor();
  await user.page.locator("input[type=file]").setInputFiles({name:"empty.pdf",mimeType:"application/pdf",buffer:Buffer.alloc(0)});
  await user.page.getByRole("alert").filter({hasText:"非空"}).waitFor();assert.equal(user.state.uploads,0);
  await user.page.locator("input[type=file]").setInputFiles(join(root,"frontend/tests/fixtures/browser-upload.pdf"));
  await user.page.locator(".server-selected-file").waitFor();assert.equal(user.state.uploads,0,"selection must not submit immediately");
  await user.page.getByRole("button",{name:"取消所选文件"}).click();assert.equal(await user.page.locator(".server-selected-file").count(),0);
  await user.page.locator("input[type=file]").setInputFiles(join(root,"frontend/tests/fixtures/browser-upload.pdf"));
  await user.page.getByRole("button",{name:"提交审核",exact:true}).click();await user.page.getByText("browser-upload.pdf",{exact:true}).waitFor();assert.equal(user.state.uploads,1);
  await user.page.getByRole("button",{name:"查看 PDF",exact:true}).first().click();await user.page.locator(".server-pdf-preview").waitFor();
  assert.equal(await user.page.getByRole("button",{name:"关闭预览"}).evaluate(el=>el===document.activeElement),true);
  await user.page.getByRole("button",{name:"关闭预览"}).click();assert.equal(await user.page.locator(".server-pdf-preview").count(),0);
  await user.page.goto(origin+"/admin");await user.page.getByRole("heading",{name:"需要管理员身份"}).waitFor();assert.equal(await user.page.locator(".server-upload-row").count(),0);
  await user.context.close();report.checks.push("research account validates empty file, stages and cancels selection, confirms exactly one upload, previews with focus, and cannot open the admin queue");

  const admin=await setup("admin");const {page,state}=admin;
  await page.goto(origin+"/admin");await page.locator(".server-upload-row").nth(7).waitFor();
  assert.equal(await page.locator(".upload-timeline").count(),8);
  assert.deepEqual(await page.locator('[data-status="rejected"] .upload-timeline li').evaluateAll(items=>items.map(el=>el.dataset.state)),["done","blocked","waiting","waiting"]);
  assert.equal(await page.locator('[data-status="processing"] .upload-timeline [data-state="current"]').textContent(),"解析与关键词入库当前阶段");
  assert.equal(await page.locator('[data-status="future_backend_state"] .status-pill').textContent(),"未知处理状态");
  assert.equal(await page.locator('[data-status="failed"]').textContent().then(x=>x.includes("OCR")),true);
  assert.equal(await page.locator('.review-console-overview [data-status="attention"] strong').textContent(),"4");
  await screenshot(page,"fixture-review-desktop");
  await page.locator('.server-upload-row[data-status="pending"]').screenshot({path:join(reportDir,"fixture-review-decision.png")});
  await page.getByRole("group",{name:"本页处理状态"}).getByRole("button",{name:"需关注",exact:true}).click();assert.equal(await page.locator(".server-upload-row").count(),4);
  await page.getByRole("group",{name:"本页处理状态"}).getByRole("button",{name:"全部",exact:true}).click();
  const pending=page.locator('.server-upload-row[data-status="pending"]');await pending.locator("textarea").fill("Fixture source reviewed");await pending.getByRole("button",{name:"批准",exact:true}).click();
  await page.locator('.server-upload-row[data-status="approved"]').nth(1).waitFor();assert.deepEqual(state.decisions[0],{id:"fixture-pending",decision:"approve",reason:"Fixture source reviewed"});
  await page.locator('.server-upload-row[data-status="approved"]').first().getByRole("button",{name:"解析并入库",exact:true}).click();
  await page.locator('.server-upload-row[data-status="processing"]').nth(1).waitFor();
  assert.equal(await page.getByRole("status").filter({hasText:"处理任务已提交，完成状态以队列为准。"}).count(),1,"HTTP 202 is accepted work, not completed indexing");
  const downloading=page.waitForEvent("download");await page.getByRole("button",{name:"下载 PDF",exact:true}).first().click();assert.match((await downloading).suggestedFilename(),/\.pdf$/);
  page.once("dialog",dialog=>dialog.accept());await page.locator('.server-upload-row[data-status="rejected"]').getByRole("button",{name:"归档",exact:true}).click();
  await page.waitForFunction(()=>document.querySelectorAll('.server-upload-row[data-status="rejected"]').length===0);assert.equal(state.archives[0],"fixture-rejected");
  const queueCountBeforeFailedRefresh=await page.locator(".server-upload-row").count();
  const firstQueueTextBeforeFailedRefresh=(await page.locator(".server-upload-row").first().innerText()).trim();
  state.failNext=true;await page.getByRole("button",{name:"刷新状态",exact:true}).click();await page.getByRole("alert").filter({hasText:"Fixture queue temporarily unavailable"}).waitFor();
  assert.equal(await page.locator(".server-upload-row").count(),queueCountBeforeFailedRefresh,"a failed refresh must preserve the last successful queue count");
  assert.equal((await page.locator(".server-upload-row").first().innerText()).trim(),firstQueueTextBeforeFailedRefresh,"a failed refresh must preserve the last successful first record");
  await page.getByRole("button",{name:"重新读取",exact:true}).click();await page.locator(".server-upload-row").first().waitFor();assert.equal(await page.getByRole("alert").count(),0,"recovered queue must clear stale failure");
  state.delayNext=9000;await page.getByRole("button",{name:"刷新状态",exact:true}).click();await page.locator(".upload-queue-loading").waitFor();
  await page.locator(".server-upload-row").first().waitFor({timeout:15000});assert.equal(state.maxLists,1,"a slow list request must not overlap with interval polling");
  await page.getByRole("navigation",{name:"上传记录分页"}).getByRole("button",{name:"下一页"}).click();await page.getByText("fixture-page-two.pdf",{exact:true}).waitFor();
  await page.setViewportSize({width:390,height:844});await screenshot(page,"fixture-review-390");
  report.checks.push("admin actual-contract fixtures: all states, truthful combined stages, current-page counts/filters, review body, process, download, archive, error recovery, nonoverlapping 9-second request, and pagination");
  await page.setViewportSize({width:1440,height:960});await page.goto(origin+"/admin");await page.locator(".server-upload-row").first().waitFor();
  let releasePreview;state.previewGate=new Promise(resolve=>{releasePreview=resolve;});
  const previews=state.previews;await page.getByRole("button",{name:"查看 PDF",exact:true}).first().click();
  await page.waitForFunction(()=>document.querySelector('.upload-action-status')?.textContent.includes("读取 PDF中"));
  await page.evaluate(()=>{sessionStorage.removeItem("scholarlens-session");window.dispatchEvent(new Event("scholarlens-auth-expired"));});
  await page.getByRole("heading",{name:"登录管理员账户后审核"}).waitFor();releasePreview();
  await page.waitForTimeout(300);assert.ok(state.previews>previews);assert.equal(await page.locator(".server-upload-row,.server-pdf-preview,.server-review-note").count(),0);
  await admin.context.close();report.checks.push("expired identity unmounts private queue/drafts and rejects a late PDF preview response");
  assert.deepEqual(unhandled,[]);assert.deepEqual(errors,[]);report.passed=true;
} finally {
  await browser.close();writeFileSync(join(reportDir,"report.json"),JSON.stringify({...report,unhandled,errors},null,2));
  console.log(JSON.stringify({...report,reportDir,unhandled,errors}));
}
