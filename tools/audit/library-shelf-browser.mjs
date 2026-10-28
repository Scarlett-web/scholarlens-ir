/** Isolated library UI contracts. Every API response is an explicit local fixture. */
import {chromium} from 'playwright';
import assert from 'node:assert/strict';
import {mkdirSync,writeFileSync,readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {join} from 'node:path';
const origin=process.env.SCHOLARLENS_URL||'http://127.0.0.1:4175';
assert.ok(['127.0.0.1','localhost','[::1]'].includes(new URL(origin).hostname));
const output=join(fileURLToPath(new URL('../../',import.meta.url)),'tools/audit/reports/library-shelf-'+new Date().toISOString().replace(/[:.]/g,'-'));
mkdirSync(output,{recursive:true});
const base={authors:['Fixture Researcher'],date:'',affiliation:[],address:[],abstract:'Fixture source for the research shelf layout.',fulltext:'Fixture source body.',keywords:['imaging'],topics:[],pages:null,pdf_available:false,parse_status:'success'};
const papers=[{...base,paper_id:'fixture:shelf-a',title:'Fixture: magnetic imaging methods and the research questions kept beside them',year:2024},{...base,paper_id:'fixture:shelf-b',title:'Fixture: comparing a second source',year:2022}];
const snapshot={version:0,favorites:papers.map((paper,i)=>({paper,collection:i?'待读':'重点阅读',note:i?'':'Fixture reading note. Keep the method and limitations next to the source.',savedAt:`2026-10-${28-i}T05:00:00Z`})),history:[{paper:papers[0],viewedAt:'2026-10-28T05:00:00Z'}],collections:['全部收藏','待读','重点阅读']};
const deferred=()=>{let release;return {promise:new Promise(resolve=>{release=resolve;}),release:()=>release()};};
const browser=await chromium.launch({channel:'chrome',headless:true}),contexts=[],unhandled=[],errors=[];
const report={passed:false,scope:'isolated local fixtures, not production account writes or cross-device position sync',checks:[]};
async function setup({user=false,empty=false,motion='reduce'}={}){
 const context=await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:motion});contexts.push(context);
 await context.addInitScript(({allowed,user,empty,snapshot})=>{
  if(location.origin!==allowed||sessionStorage.getItem('fixture-initialized'))return;
  sessionStorage.setItem('fixture-initialized','1');
  if(user)sessionStorage.setItem('scholarlens-session','fixture-not-a-credential');
  const guest=user?{favorites:[snapshot.favorites[1]],history:[],collections:['全部收藏','待读']}:snapshot;
  for(const key of ['favorites','history','collections'])localStorage.setItem('scholarlens-v1:'+key,JSON.stringify(empty?(key==='collections'?['全部收藏']:[]):guest[key]));
  localStorage.setItem('scholarlens-v1:reading-positions:'+(user?'user-801':'guest'),JSON.stringify({'fixture:shelf-a':{ratio:.42,expanded:true,textLength:1000,savedAt:new Date().toISOString()}}));
 },{allowed:new URL(origin).origin,user,empty,snapshot});
 const state={workspace:structuredClone(snapshot),failRead:false,failWrite:false,gate:null,requests:[],staleFinished:0};
 await context.route('**/api/**',async route=>{
  const request=route.request(),path=new URL(request.url()).pathname.slice(4),method=request.method();
  state.requests.push({path,method});
  const json=(value,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(value)});
  if(path==='/stats')return json({status:'real',papers:859});
  if(path==='/capabilities')return json({modules:{}});
  if(path==='/auth/me'&&user)return json({id:801,username:'fixture-reader',role:'user'});
  if(path==='/me/workspace'&&user){
   if(method==='GET'){
    const gate=state.gate;state.gate=null;
    if(gate)await gate.promise;
    try{return await json(state.failRead?{error:{message:'Fixture read unavailable'}}:state.workspace,state.failRead?503:200);}
    catch(error){if(!gate)throw error;}finally{if(gate)state.staleFinished++;}
   }
   if(method==='PUT'){
    if(state.failWrite)return json({error:{message:'Fixture write unavailable'}},503);
    state.workspace={...request.postDataJSON(),version:state.workspace.version+1};return json({version:state.workspace.version});
   }
  }
  unhandled.push(method+' '+path);return json({error:{message:'No explicit fixture'}},501);
 });
 context.on('page',p=>p.on('pageerror',error=>errors.push(error.message)));
 const page=await context.newPage();page.setDefaultTimeout(10000);return {context,page,state};
}
const noOverflow=async page=>assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
const readCount=s=>s.requests.filter(r=>r.path==='/me/workspace'&&r.method==='GET').length;
const writeCount=s=>s.requests.filter(r=>r.path==='/me/workspace'&&r.method==='PUT').length;
async function exportLibrary(page,name){
 const waiting=page.waitForEvent('download');await page.getByRole('button',{name:'导出 JSON',exact:true}).click();
 const download=await waiting;const path=join(output,name);await download.saveAs(path);return JSON.parse(readFileSync(path,'utf8'));
}
try{
 const guest=await setup(),p=guest.page;
 await p.goto(origin+'/library');await p.locator('.library-paper-item').first().waitFor();
 assert.equal(await p.locator('.library-paper-item').count(),2);
 assert.equal(await p.locator('.library-resume .library-reading-position').textContent(),'上次记录 42% · 本机继续阅读');
 assert.equal(await p.locator('.library-resume-open').getAttribute('href'),'/paper/fixture%3Ashelf-a');
 const geometry=await p.locator('.library-paper-item.has-note').evaluate(el=>{const main=el.querySelector('.library-paper-main').getBoundingClientRect(),note=el.querySelector('.library-paper-note').getBoundingClientRect();return {adjacent:main.right<=note.left,top:Math.abs(main.top-note.top)<12};});assert.deepEqual(geometry,{adjacent:true,top:true});
 await p.locator('.library-paper-item').first().hover();assert.equal(await p.locator('.library-paper-item').first().evaluate(el=>getComputedStyle(el,'::before').transform),'none');
 await noOverflow(p);await p.screenshot({path:join(output,'library-desktop.png'),fullPage:true});
 await p.getByLabel('筛选收藏论文',{exact:true}).fill('limitations');assert.equal(await p.locator('.library-paper-item').count(),1);await p.getByRole('button',{name:'清空搜索',exact:true}).click();
 await p.getByRole('combobox',{name:'排序',exact:true}).selectOption('title');assert.ok((await p.locator('.library-paper-item h3').first().textContent()).includes('comparing'));
 await p.getByRole('combobox',{name:'排序',exact:true}).selectOption('year');assert.ok((await p.locator('.library-paper-item h3').first().textContent()).includes('magnetic'));
 await p.getByLabel('新分类名称',{exact:true}).fill('Fixture collection');await p.getByRole('button',{name:'创建分类',exact:true}).click();await p.getByRole('heading',{name:'Fixture collection',exact:true}).waitFor();
 await p.getByRole('button',{name:'重命名Fixture collection',exact:true}).click();await p.getByLabel('重命名分类',{exact:true}).fill('Fixture renamed');await p.getByRole('button',{name:'保存新名称',exact:true}).click();
 await p.getByRole('button',{name:'查看分类：所有文献',exact:true}).click();await p.locator('.library-paper-item').first().getByRole('combobox',{name:'分类',exact:true}).selectOption('Fixture renamed');
 await p.getByRole('button',{name:'查看分类：Fixture renamed',exact:true}).click();assert.equal(await p.locator('.library-paper-item').count(),1);
 p.once('dialog',dialog=>dialog.accept());await p.getByRole('button',{name:'删除Fixture renamed',exact:true}).click();await p.getByRole('button',{name:'查看分类：未分类',exact:true}).click();assert.equal(await p.locator('.library-paper-item').count(),1);
 await p.locator('.library-note-preview').click();await p.getByRole('textbox',{name:'我的阅读笔记',exact:true}).fill('Fixture edited reading note');
 const backup=await exportLibrary(p,'guest-backup.json');assert.equal(backup.favorites[0].note,'Fixture edited reading note');
 await p.getByRole('button',{name:'查看分类：所有文献',exact:true}).click();await p.setViewportSize({width:390,height:844});await noOverflow(p);await p.screenshot({path:join(output,'library-390.png'),fullPage:true});
 let guestPrompt='';p.once('dialog',dialog=>{guestPrompt=dialog.message();return dialog.dismiss();});await p.locator('input[type=file]').setInputFiles({name:'backup.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(backup))});assert.ok(guestPrompt.includes('当前浏览器'));assert.equal(await p.locator('.library-paper-item').count(),2);
 report.checks.push('horizontal collections create/rename/move/delete; note search, year/title sort; adjacent notes desktop and 390 no overflow; real local 42% position and resume link; guest note edit/export and browser import warning');

 const loading=await setup({user:true}),a=loading.page,s=loading.state;const gate=deferred();s.gate=gate;s.failRead=true;
 await a.goto(origin+'/library');await a.getByText('正在读取账户文献…',{exact:true}).waitFor();assert.equal(await a.locator('.library-empty').count(),0);assert.ok((await a.locator('.segmented').textContent()).includes('—'));assert.equal(await a.getByRole('button',{name:'导出 JSON',exact:true}).isDisabled(),true);
 gate.release();await a.getByRole('button',{name:'重新读取账户文献',exact:true}).waitFor();assert.equal(await a.locator('.library-empty').count(),0);await a.screenshot({path:join(output,'workspace-read-error.png')});
 s.failRead=false;await a.getByRole('button',{name:'重新读取账户文献',exact:true}).click();await a.locator('.library-paper-item').first().waitFor();assert.equal(readCount(s),2);assert.equal(writeCount(s),0);
 let accountPrompt='';a.once('dialog',dialog=>{accountPrompt=dialog.message();return dialog.dismiss();});await a.locator('input[type=file]').setInputFiles({name:'backup.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(backup))});assert.ok(accountPrompt.includes('当前账户')&&accountPrompt.includes('同步到服务器'));assert.equal(writeCount(s),0);
 s.failWrite=true;await a.locator('.library-note-preview').click();await a.getByRole('textbox',{name:'我的阅读笔记',exact:true}).fill('Fixture unsynced recovery draft');await a.locator('.library-sync-error').waitFor();
 assert.equal(await a.locator('.library-paper-item').count(),2);assert.equal(await a.getByRole('textbox',{name:'我的阅读笔记',exact:true}).inputValue(),'Fixture unsynced recovery draft');assert.equal(await a.getByRole('textbox',{name:'我的阅读笔记',exact:true}).getAttribute('readonly'),'');
 assert.equal(await a.getByRole('button',{name:'创建分类',exact:true}).isDisabled(),true);assert.equal(await a.locator('.library-paper-item').first().getByRole('button',{name:'取消收藏论文',exact:true}).isDisabled(),true);
 assert.equal((await exportLibrary(a,'recovery-backup.json')).favorites[0].note,'Fixture unsynced recovery draft');
 const recovery=await a.evaluate(()=>JSON.parse(localStorage.getItem('scholarlens-v1:account-801-recovery')));assert.equal(recovery.favorites[0].note,'Fixture unsynced recovery draft');
 await a.waitForTimeout(650);assert.equal(readCount(s),2);assert.equal(writeCount(s),1);assert.equal(await a.getByRole('button',{name:'重新读取账户文献',exact:true}).count(),0);await a.screenshot({path:join(output,'workspace-sync-error.png')});
 report.checks.push('account initial loading/503/retry never claims empty or zero; no PUT on read; account import warning; failed PUT retains visible and local recovery draft, export enabled, edits blocked, no auto reread or write retry');

 const expired=await setup({user:true}),pending=deferred();expired.state.gate=pending;
 await expired.page.goto(origin+'/library');await expired.page.getByText('正在读取账户文献…',{exact:true}).waitFor();
 await expired.page.evaluate(()=>{sessionStorage.removeItem('scholarlens-session');window.dispatchEvent(new Event('scholarlens-auth-expired'));});await expired.page.locator('.library-paper-item').first().waitFor();pending.release();
 for(let i=0;i<100&&!expired.state.staleFinished;i++)await expired.page.waitForTimeout(20);
 assert.equal(expired.state.staleFinished,1);assert.ok((await expired.page.locator('.library-local-note').textContent()).includes('游客空间'));assert.equal(writeCount(expired.state),0);
 assert.equal(await expired.page.locator('.library-paper-item').count(),1);assert.ok((await expired.page.locator('.library-paper-item h3').textContent()).includes('comparing'));assert.equal(await expired.page.locator('.library-resume').count(),0);
 const empty=await setup({empty:true});await empty.page.goto(origin+'/library');await empty.page.getByRole('heading',{name:'你的研究书架还是空的',exact:true}).waitFor();assert.equal(await empty.page.locator('.library-resume').count(),0);await empty.page.screenshot({path:join(output,'library-empty.png')});
 const paused=await setup({motion:'no-preference'});await paused.page.goto(origin+'/library');await paused.page.evaluate(()=>localStorage.setItem('scholarlens-v1:motion-paused','true'));await paused.page.reload();await paused.page.locator('.library-paper-item').first().hover();assert.equal(await paused.page.locator('.library-paper-item').first().evaluate(el=>getComputedStyle(el,'::before').transform),'none');
 report.checks.push('expired account discards delayed private response and preserves guest shelf; genuinely empty shelf has no invented resume; motion pause and system reduced motion supported');
 assert.deepEqual(unhandled,[]);assert.deepEqual(errors,[]);report.passed=true;
}finally{
 await Promise.all(contexts.map(context=>context.close()));await browser.close();Object.assign(report,{unhandled,errors});writeFileSync(join(output,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify({...report,output}));
}
