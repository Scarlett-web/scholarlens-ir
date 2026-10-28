/** Local UI contracts only. All account, search and file responses are explicit fixtures. */
import {chromium} from 'playwright';
import assert from 'node:assert/strict';
import {mkdirSync,writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {join} from 'node:path';
const origin=process.env.SCHOLARLENS_URL||'http://127.0.0.1:4174';
assert.ok(['127.0.0.1','localhost','[::1]'].includes(new URL(origin).hostname));
const output=join(fileURLToPath(new URL('../../',import.meta.url)),'tools/audit/reports/search-account-'+new Date().toISOString().replace(/[:.]/g,'-'));
mkdirSync(output,{recursive:true});
const browser=await chromium.launch({channel:'chrome',headless:true}),contexts=[],unhandled=[],errors=[];
const report={passed:false,scope:'isolated local UI fixtures; not real authentication, account storage, avatar validation or supplier generation',checks:[]};
const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6mWQAAAAASUVORK5CYII=','base64');
const base={authors:['Fixture Researcher'],date:'',affiliation:[],address:[],abstract:'Fixture evidence for magnetic imaging.',fulltext:'Fixture body.',keywords:['magnetic'],topics:[],pages:null,parse_status:'success'};
const papers=[{...base,paper_id:'fixture:search-a',title:'Fixture magnetic research record with a long title that wraps inside its content column and keeps actions clear',year:2024,pdf_available:true,score:0},{...base,paper_id:'fixture:search-b',title:'Fixture source without year or PDF',year:null,pdf_available:false,score:0.345}];
const history=Array.from({length:21},(_,i)=>({id:i+1,q:'Fixture query '+(i+1),field:'title',mode:'keyword',created_at:'2026-10-28T05:00:00Z'}));
const deferred=()=>{let release;return {promise:new Promise(resolve=>{release=resolve;}),release:()=>release()};};
async function until(check){for(let i=0;i<100;i++){if(check())return;await new Promise(resolve=>setTimeout(resolve,20));}assert.fail('Fixture response did not finish');}
async function setup({user=false,admin=false,motion='reduce'}={}){
 const context=await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:motion});contexts.push(context);
 if(user)await context.addInitScript(({allowed})=>{if(location.origin===allowed&&!sessionStorage.getItem('fixture-initialized')){sessionStorage.setItem('scholarlens-session','fixture-not-a-credential');sessionStorage.setItem('fixture-initialized','1');}},{allowed:new URL(origin).origin});
 const state={fail:{history:false,profile:false,notices:false,users:false,clear:false},gates:{},queries:[...history],requests:[],avatarGets:0,deleted:0,staleFinished:0,notices:[],users:[{id:801,username:'fixture-researcher',role:'admin',disabled:false},{id:802,username:'fixture-second-user',role:'user',disabled:false}],profile:{username:'fixture-researcher',display_name:'Fixture reader',email:'',email_verified:false,avatar_available:true}};
 await context.route('**/api/**',async route=>{
  const request=route.request(),url=new URL(request.url()),path=url.pathname.slice(4),method=request.method();
  state.requests.push({path,method,query:url.search});
  const json=(value,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(value)});
  const gated=async(key,value)=>{const gate=state.gates[key];state.gates[key]=null;if(gate)await gate.promise;try{return await json(value,state.fail[key]?503:200);}catch(error){if(!gate)throw error;}finally{if(gate)state.staleFinished++;}};
  if(path==='/stats')return json({status:'real',papers:859});
  if(path==='/capabilities')return json({modules:Object.fromEntries(['keyword_search','semantic_search','hybrid_search'].map(key=>[key,{status:'ready'}]))});
  if(path==='/suggest')return json({suggestions:[]});
  if(path==='/search'){
   const rows=(state.searchRows||papers).filter(p=>(!url.searchParams.has('year_from')||p.year>=Number(url.searchParams.get('year_from')))&&(!url.searchParams.has('year_to')||p.year!==null&&p.year<=Number(url.searchParams.get('year_to'))));
   return json({results:rows,total:state.searchTotal??13,page:Number(url.searchParams.get('page')||1),page_size:6,took_ms:7});
  }
  if(path==='/discover')return json({recommendations:papers,papers:859,years:[],example_searches:[]});
  if(path.startsWith('/papers/')&&method==='GET')return json(papers.find(p=>p.paper_id===decodeURIComponent(path.slice(8)))||papers[0]);
  if(path==='/auth/login'&&method==='POST'){
   assert.equal(request.postDataJSON().username,'fixture-user');
   const gate=state.gates.login;if(gate)await gate.promise;
   return json({error:{message:'Fixture login temporarily unavailable'}},503);
  }
  if(path==='/auth/me'&&user)return json({id:801,username:'fixture-researcher',role:admin?'admin':'user'});
  if(path==='/me/workspace'&&user&&method==='GET')return json({version:0,favorites:[],history:[],collections:['全部收藏']});
  if(path==='/me/history'&&user){
   if(method==='GET'){
    const page=Number(url.searchParams.get('page')||1),snapshot={results:state.queries.slice((page-1)*20,page*20),total:state.queries.length};
    return gated('history',state.fail.history?{error:{message:'Fixture history unavailable'}}:snapshot);
   }
   if(method==='DELETE'){state.deleted++;if(state.fail.clear)return json({error:{message:'Fixture clear failed'}},503);state.queries=[];return json({status:'ok'});}
  }
  if(path==='/me/profile'&&method==='GET'&&user)return gated('profile',state.fail.profile?{error:{message:'Fixture profile unavailable'}}:state.profile);
  if(path==='/me/profile'&&method==='PATCH'&&user){state.profile={...state.profile,...request.postDataJSON()};return json(state.profile);}
  if(path==='/me/avatar'&&user){
   if(method==='GET'){state.avatarGets++;return route.fulfill({status:200,contentType:'image/png',body:png});}
   if(method==='POST')return json({username:'fixture-researcher',display_name:'Fixture reader',email:'',email_verified:false,avatar_available:true});
  }
  if(path==='/me/notifications'&&method==='GET'&&user)return gated('notices',state.fail.notices?{error:{message:'Fixture notifications unavailable'}}:{results:state.notices,total:state.notices.length});
  if(path==='/me/notifications/901/read'&&method==='POST'&&user){state.notices=state.notices.map(n=>({...n,read:true}));return json({status:'ok'});}
  if(path==='/admin/users'&&method==='GET'&&admin)return gated('users',state.fail.users?{error:{message:'Fixture account list unavailable'}}:{results:state.users,total:state.users.length});
  if(path==='/admin/users/802'&&method==='PATCH'&&admin){const change=request.postDataJSON();state.users=state.users.map(u=>u.id===802?{...u,...change}:u);return json(state.users[1]);}
  unhandled.push(method+' '+path);return json({error:{message:'No explicit fixture'}},501);
 });
 context.on('page',p=>p.on('pageerror',error=>errors.push(error.message)));
 const page=await context.newPage();return {page,context,state};
}
async function noOverflow(page){assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);}
try{
 const guest=await setup(),{page,state}=guest;
 await page.goto(origin+'/search?q=fixture&field=title&mode=hybrid&from=2000&to=2026&page=2&sort=newest');
 await page.locator('.paper-record').first().waitFor();assert.equal(await page.locator('.search-conditions button').count(),4);
 assert.equal(await page.locator('.paper-list-index').first().textContent(),'07');
 assert.equal(await page.getByText(/检索分数/).count(),0);
 assert.equal(await page.locator('.page-heading p').count(),0);
 assert.equal(await page.locator('.paper-record').first().getByRole('link',{name:'查原文证据'}).getAttribute('href'),'/assistant?paper=fixture%3Asearch-a');
 await page.getByRole('button',{name:'移除字段：论文标题',exact:true}).click();
 await page.waitForFunction(()=>!new URLSearchParams(location.search).has('field')&&new URLSearchParams(location.search).get('page')==='1');
 await page.locator('.paper-record').first().waitFor();
 await page.getByRole('button',{name:'移除年份：2000 — 2026',exact:true}).click();
 await page.getByRole('button',{name:'移除混合检索',exact:true}).click();
 await page.locator('.paper-record-year.is-unknown').waitFor();
 assert.equal(await page.locator('.paper-record-year.is-unknown').getAttribute('aria-label'),'年份未提供');
 assert.equal(await page.locator('.paper-record').nth(1).getByText('PDF 原件可用',{exact:true}).count(),0);
 await page.locator('.paper-record').first().getByRole('button',{name:'收藏论文',exact:true}).click();
 await page.locator('.paper-record').first().getByRole('button',{name:'取消收藏论文',exact:true}).waitFor();
 assert.equal(await page.locator('.paper-record').first().evaluate(row=>{const main=row.querySelector('.paper-record-content').getBoundingClientRect(),title=row.querySelector('h3').getBoundingClientRect(),actions=row.querySelector('.paper-record-actions').getBoundingClientRect();return title.right<=main.right&&main.right<=actions.left;}),true);
 await noOverflow(page);await page.screenshot({path:join(output,'search-desktop.png')});
 await page.setViewportSize({width:390,height:844});await noOverflow(page);await page.screenshot({path:join(output,'search-390.png')});
 await page.setViewportSize({width:1440,height:1000});
 await page.getByRole('button',{name:'移除关键词：fixture',exact:true}).click();
 await page.getByText('近期论文选读',{exact:true}).waitFor();
 assert.equal(new URL(page.url()).searchParams.has('q'),false);
 report.checks.push('search row order, year, hidden score and removed heading note, direct evidence and reading links, guest favorite, filter removal resets page and preserves other parameters, blank discover boundary, desktop/390 geometry');

 const names=['Fixture First Author','Fixture Second Author','Fixture Third Author','Fixture Fourth Researcher','Fixture Fifth Author','Fixture Sixth Author'];
 state.searchRows=[{...papers[0],authors:names}];state.searchTotal=222;
 await page.goto(origin+'/search?q=fixture&field=title&mode=keyword&from=2000&to=2026&page=1&sort=newest');
 const row=page.locator('.paper-record').first(),authors=row.locator('[data-field="authors"]'),nav=page.getByRole('navigation',{name:'论文结果分页',exact:true});
 await row.waitFor();assert.equal(await authors.locator('.paper-author').count(),3);
 assert.ok((await authors.textContent()).includes('Fixture Third Author'));
 await authors.getByRole('button',{name:'更多作者（还有 3 位）',exact:true}).click();
 assert.equal(await authors.locator('.paper-author').count(),6);
 for(const name of names)assert.ok((await authors.textContent()).includes(name));
 assert.equal(await authors.getByRole('button',{name:'收起作者',exact:true}).getAttribute('aria-expanded'),'true');
 await authors.getByRole('button',{name:'收起作者',exact:true}).click();assert.equal(await authors.locator('.paper-author').count(),3);
 const pageItems=()=>nav.locator('button[aria-label^="第 "],.pagination-gap').allTextContents();
 assert.deepEqual(await pageItems(),['1','2','3','4','5','…','37']);
 await page.screenshot({path:join(output,'pagination-first-desktop.png')});
 await nav.getByRole('button',{name:'第 5 页',exact:true}).click();await page.waitForFunction(()=>new URLSearchParams(location.search).get('page')==='5');await row.waitFor();
 assert.deepEqual(await pageItems(),['1','…','4','5','6','…','37']);
 for(const [key,value] of Object.entries({q:'fixture',field:'title',mode:'keyword',from:'2000',to:'2026',sort:'newest'}))assert.equal(new URL(page.url()).searchParams.get(key),value);
 await nav.getByRole('button',{name:'第 37 页',exact:true}).click();await row.waitFor();
 assert.deepEqual(await pageItems(),['1','…','33','34','35','36','37']);assert.equal(await nav.getByRole('button',{name:'下一页',exact:true}).isDisabled(),true);
 await page.setViewportSize({width:390,height:844});await noOverflow(page);await page.setViewportSize({width:1440,height:1000});
 state.searchRows=[{...papers[0],authors:names,highlights:{authors:['Fixture Fourth <em>Researcher</em>']}}];
 await page.goto(origin+'/search?q=Researcher&field=authors');await row.waitFor();
 assert.equal(await authors.locator('.paper-author').count(),3);assert.equal(await authors.locator('mark').textContent(),'Researcher');
 assert.ok((await authors.textContent()).includes('Fixture First Author'));assert.ok((await authors.textContent()).includes('Fixture Fourth Researcher'));
 await authors.getByRole('button',{name:'更多作者（还有 3 位）',exact:true}).click();
 assert.equal(await authors.locator('.paper-author').count(),6);await noOverflow(page);
 await page.screenshot({path:join(output,'authors-expanded-desktop.png')});
 state.searchRows=undefined;state.searchTotal=undefined;
 report.checks.push('six original authors expand/collapse; a later matched author stays visible and marked; 37-page first/middle/end windows include ellipses, preserve URL filters and stay within desktop/390 viewport');

 const exactTitle='Simulating the Dynamics of the Dancing Lights';
 state.searchRows=[{...papers[0],title:exactTitle,authors:['Lights Researcher','Second Author','Third Author','Fourth Author'],date:'2002',affiliation:['Dancing Lights Institute'],address:['Lights City'],abstract:'The lights and dynamics appear in this abstract.',highlights:{title:['<em>Simulating</em> the <em>Dynamics</em> of the <em>Dancing</em> <em>Lights</em>'],authors:['<em>Lights</em> Researcher'],affiliation:['Dancing <em>Lights</em> Institute'],fulltext:['Northern <em>Lights</em> give a linkage between science and art.']}}];state.searchTotal=1;
 for(const mode of ['keyword','hybrid','semantic'])for(const field of ['all','title']){
   await page.goto(origin+'/search?'+new URLSearchParams({q:exactTitle,field,mode}));await row.waitFor();
   assert.deepEqual(await row.locator('mark').allTextContents(),[exactTitle]);
   assert.equal(await row.locator('.paper-abstract mark,.paper-hit-label').count(),0);
   assert.equal(await row.locator('.paper-authors mark,.paper-record-metadata mark').count(),0);
   assert.ok((await row.locator('.paper-abstract').textContent()).includes('lights and dynamics'));
 }
 await page.screenshot({path:join(output,'title-only-desktop.png')});
 await page.setViewportSize({width:390,height:844});await noOverflow(page);await page.screenshot({path:join(output,'title-only-390.png')});await page.setViewportSize({width:1440,height:1000});
 state.searchRows[0].highlights=undefined;
 await page.goto(origin+'/search?'+new URLSearchParams({q:exactTitle,field:'all'}));await row.waitFor();assert.deepEqual(await row.locator('mark').allTextContents(),[exactTitle]);
 state.searchRows[0].highlights={title:['Simulating the Dynamics of the Dancing <em>Lights</em>'],fulltext:['Northern <em>Lights</em> give a linkage between science and art.']};
 for(const field of ['fulltext','all']){
   await page.goto(origin+'/search?'+new URLSearchParams({q:'Lights',field}));await row.waitFor();
   assert.deepEqual(await row.locator('.paper-abstract mark').allTextContents(),['Lights']);
   assert.equal(await row.locator('.paper-title-link mark').count(),field==='all'?1:0);
 }
 state.searchRows=undefined;state.searchTotal=undefined;
 report.checks.push('complete title yields one whole-title mark and plain abstract across three modes; old split-word responses and empty highlight fallback cannot mark incidental body/metadata/author words; fulltext-only and ordinary keyword queries retain valid body highlights');

 await page.goto(origin+'/account');await page.getByRole('heading',{name:'欢迎回来',exact:true}).waitFor();
 await page.getByLabel('用户名',{exact:true}).fill('fixture-user');await page.getByLabel('密码',{exact:true}).fill('fixture-only-password');
 await page.getByRole('button',{name:'显示密码',exact:true}).click();assert.equal(await page.getByLabel('密码',{exact:true}).getAttribute('type'),'text');
 await page.getByRole('button',{name:'创建账户',exact:true}).click();assert.equal(await page.getByLabel('密码',{exact:true}).inputValue(),'');assert.equal(await page.getByLabel('密码',{exact:true}).getAttribute('autocomplete'),'new-password');
 await page.getByRole('button',{name:'登录',exact:true}).first().click();
 await page.getByLabel('密码',{exact:true}).fill('fixture-only-password');state.gates.login=deferred();
 await page.locator('button[type=submit]').first().click();await page.getByRole('button',{name:'正在登录…',exact:true}).waitFor();assert.equal(await page.getByLabel('用户名',{exact:true}).isDisabled(),true);
 state.gates.login.release();await page.getByText('Fixture login temporarily unavailable',{exact:true}).waitFor();assert.equal(await page.getByLabel('用户名',{exact:true}).isEnabled(),true);
 await noOverflow(page);await page.screenshot({path:join(output,'login-desktop.png')});
 await page.setViewportSize({width:390,height:844});await noOverflow(page);await page.screenshot({path:join(output,'login-390.png')});
 const motion=await setup({motion:'no-preference'});await motion.page.goto(origin+'/account');await motion.page.locator('.auth-benefits li').first().waitFor();
 const initial=await motion.page.locator('.auth-benefits li').first().evaluate(el=>getComputedStyle(el).transform);assert.notEqual(initial,'none');
 await motion.page.getByLabel('用户名',{exact:true}).focus();await motion.page.waitForFunction(before=>getComputedStyle(document.querySelector('.auth-benefits li')).transform!==before,initial);
 await motion.page.evaluate(()=>{localStorage.setItem('scholarlens-v1:motion-paused','true');});await motion.page.reload();
 assert.equal(await motion.page.locator('.auth-benefits li').first().evaluate(el=>getComputedStyle(el).transform),'none');
 assert.equal(await motion.page.locator('.auth-benefits li').first().evaluate(el=>getComputedStyle(el,'::before').animationName),'none');
 report.checks.push('login/register mode, password visibility and autocomplete, pending/failure recovery; layered glass responds to focus and motion pause without fake content');

 const account=await setup({user:true,admin:true}),a=account.page,s=account.state;
 s.fail={...s.fail,profile:true,notices:true,users:true,history:true};const initialHistory=deferred();s.gates.history=initialHistory;
 await a.goto(origin+'/account');await a.getByRole('heading',{name:'你的研究账户',exact:true}).waitFor();
 await a.locator('.account-search-history summary').click();await a.getByText('正在读取搜索历史…',{exact:true}).waitFor();assert.equal(await a.getByText('还没有搜索记录。检索论文后会显示在这里。',{exact:true}).count(),0);
 initialHistory.release();await a.getByRole('button',{name:'重新读取搜索历史',exact:true}).waitFor();
 assert.equal(await a.getByText('还没有搜索记录。检索论文后会显示在这里。',{exact:true}).count(),0);
 await a.getByRole('button',{name:'重新读取个人资料',exact:true}).waitFor();s.fail.profile=false;
 await a.getByRole('button',{name:'重新读取个人资料',exact:true}).click();await a.getByLabel('显示名称',{exact:true}).waitFor();await a.getByRole('img',{name:'我的头像',exact:true}).waitFor();
 const avatars=s.avatarGets;await a.getByLabel('显示名称',{exact:true}).fill('Fixture edited name');await a.getByLabel('用户名',{exact:true}).fill('fixture-edited');
 await a.evaluate(()=>new Promise(requestAnimationFrame));assert.equal(s.avatarGets,avatars,'Editing profile must not refetch the avatar');
 const avatarRefresh=a.waitForResponse(response=>new URL(response.url()).pathname==='/api/me/avatar'&&response.request().method()==='GET');
 await a.locator('input[type=file]').setInputFiles({name:'fixture-avatar.png',mimeType:'image/png',buffer:png});await avatarRefresh;assert.equal(s.avatarGets,avatars+1);
 await a.getByLabel('显示名称',{exact:true}).fill('Fixture saved display name');await a.getByRole('button',{name:'保存资料',exact:true}).click();await a.getByText('资料已保存',{exact:true}).waitFor();assert.equal(s.profile.display_name,'Fixture saved display name');
 await a.getByRole('button',{name:'通知',exact:true}).click();await a.getByRole('button',{name:'重新读取通知',exact:true}).waitFor();assert.equal(await a.getByText('暂无通知。上传审核和入库结果会出现在这里。',{exact:true}).count(),0);
 s.fail.notices=false;await a.getByRole('button',{name:'重新读取通知',exact:true}).click();await a.getByText('暂无通知。上传审核和入库结果会出现在这里。',{exact:true}).waitFor();
 await a.getByRole('button',{name:'账户管理',exact:true}).click();await a.getByRole('button',{name:'重新读取账户列表',exact:true}).waitFor();await a.getByRole('heading',{name:'账户管理 · —',exact:true}).waitFor();
 s.fail.users=false;await a.getByRole('button',{name:'重新读取账户列表',exact:true}).click();await a.getByRole('heading',{name:'账户管理 · 2',exact:true}).waitFor();
 a.once('dialog',dialog=>dialog.accept());await a.getByRole('button',{name:'设为管理员',exact:true}).click();await a.getByText('fixture-second-user · admin · 可用',{exact:true}).waitFor();assert.equal(s.users[1].role,'admin');
 s.fail.history=false;await a.getByRole('button',{name:'重新读取搜索历史',exact:true}).click();await a.getByRole('link',{name:/Fixture query 1 /}).first().waitFor();
 assert.equal(await a.locator('.account-history-link').count(),20);
 s.fail.clear=true;a.once('dialog',dialog=>dialog.accept());await a.getByRole('button',{name:'清空搜索历史',exact:true}).click();await a.getByText('Fixture clear failed',{exact:true}).waitFor();assert.equal(await a.getByText('还没有搜索记录。检索论文后会显示在这里。',{exact:true}).count(),0);
 s.fail.clear=false;await a.getByRole('button',{name:'重新读取搜索历史',exact:true}).click();await a.locator('.account-history-link').first().waitFor();
 const oldPage=deferred();s.gates.history=oldPage;await a.getByRole('navigation',{name:'搜索历史分页',exact:true}).getByRole('button',{name:'下一页',exact:true}).click();await a.getByText('正在读取搜索历史…',{exact:true}).waitFor();
 a.once('dialog',dialog=>dialog.accept());await a.getByRole('button',{name:'清空搜索历史',exact:true}).click();await a.getByText('还没有搜索记录。检索论文后会显示在这里。',{exact:true}).waitFor();
 oldPage.release();await until(()=>s.staleFinished>=2);assert.equal(await a.locator('.account-history-link').count(),0);assert.equal(s.deleted,2);
 await a.getByRole('button',{name:'个人资料',exact:true}).click();await noOverflow(a);await a.screenshot({path:join(output,'account-desktop.png')});
 s.notices=[{id:901,message:'Fixture upload review notification',read:false,created_at:'2026-10-28T05:00:00Z'}];await a.reload();await a.getByRole('button',{name:'通知',exact:true}).click();await a.getByRole('button',{name:'标记已读',exact:true}).click();await a.getByRole('button',{name:'已读',exact:true}).waitFor();assert.equal(s.notices[0].read,true);
 report.checks.push('account read loading/failure/retry, no false empty/zero counts, history pagination and clear failure, old page response cannot restore cleared records; profile edits do not refetch avatar and upload refreshes it; notifications and admin list retry independently');

 const expired=await setup({user:true}),pendingHistory=deferred();expired.state.gates.history=pendingHistory;
 await expired.page.goto(origin+'/account');await expired.page.getByRole('heading',{name:'你的研究账户',exact:true}).waitFor();
 await expired.page.evaluate(()=>{sessionStorage.removeItem('scholarlens-session');window.dispatchEvent(new Event('scholarlens-auth-expired'));});
 await expired.page.getByRole('heading',{name:'欢迎回来',exact:true}).waitFor();pendingHistory.release();await until(()=>expired.state.staleFinished===1);assert.equal(await expired.page.locator('.account-history-link').count(),0);
 report.checks.push('expired account unmounts private history and discards its delayed response');
 assert.deepEqual(unhandled,[]);assert.deepEqual(errors,[]);report.passed=true;
}finally{
 await Promise.all(contexts.map(context=>context.close()));await browser.close();
 Object.assign(report,{unhandled,errors});writeFileSync(join(output,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify({...report,output}));
}
