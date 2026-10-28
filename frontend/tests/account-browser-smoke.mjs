/**
 * Chrome DevTools Protocol browser smoke test without external test libraries.
 * Windows-only. Run while npm run preview -- --port 4173 is active.
 * Uses a fresh temporary browser profile and leaves the user's own Chrome intact.
 */
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawn } from "node:child_process";

const chrome = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const origin = process.env.SCHOLARLENS_URL || "http://127.0.0.1:4173";
const profile = fs.mkdtempSync(path.join(os.tmpdir(),"scholarlens-smoke-"));
if (!fs.existsSync(chrome)) throw new Error("Chrome not found: "+chrome);

let processHandle, connection;
let serial=0;
const pending = new Map();
const delay = (ms) => new Promise((resolve)=>setTimeout(resolve,ms));

async function waitPort(timeout=15000) {
  const filename=path.join(profile,"DevToolsActivePort");
  const start=Date.now();
  while(Date.now()-start<timeout){
    if(fs.existsSync(filename)){
      const lines=fs.readFileSync(filename,"utf8").trim().split(/\r?\n/);
      if(lines.length>=2)return Number(lines[0]);
    }
    await delay(130);
  }
  throw new Error("Chrome did not create a debugging port");
}

async function connect(url){
  const ws=new WebSocket(url);
  await new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>reject(new Error("Browser WebSocket connection timed out")),8000);
    ws.addEventListener("open",()=>{clearTimeout(timer);resolve();},{once:true});
    ws.addEventListener("error",()=>{clearTimeout(timer);reject(new Error("Browser WebSocket connection error"));},{once:true});
  });
  ws.addEventListener("message",(event)=>{
    const data=JSON.parse(String(event.data));
    if(!data.id||!pending.has(data.id))return;
    const {resolve,reject,timer}=pending.get(data.id);
    clearTimeout(timer);
    pending.delete(data.id);
    if(data.error)reject(new Error(data.error.message||"CDP error"));
    else resolve(data.result);
  });
  return ws;
}

function send(method,params={}){
  return new Promise((resolve,reject)=>{
    const id=++serial;
    const timer=setTimeout(()=>{pending.delete(id);reject(new Error("CDP timeout: "+method))},13000);
    pending.set(id,{resolve,reject,timer});
    connection.send(JSON.stringify({id,method,params}));
  });
}

async function evaluate(expression){
  const result=await send("Runtime.evaluate",{expression,returnByValue:true,awaitPromise:true});
  if(result.exceptionDetails)throw new Error("Browser evaluation: "+(result.exceptionDetails.text??"unknown"));
  return result.result?.value;
}

async function waitFor(expression,timeout=13000){
  const start=Date.now();
  while(Date.now()-start<timeout){
    try{const result=await evaluate(expression);if(result)return result}catch{}
    await delay(180);
  }
  throw new Error("Timed out waiting for: "+expression);
}

async function navigate(url) {
  await send("Page.navigate",{url:origin+url});
  await waitFor("document.querySelector('#root') !== null");
}

const q=(str)=>JSON.stringify(str);
async function click(selector){
  const value=await evaluate("(()=>{const el=document.querySelector("+q(selector)+");if(!el)return false;el.click();return true})()");
  assert.equal(value,true,"Could not click "+selector);
}

async function fill(selector,value){
  const expression="(()=>{const el=document.querySelector("+q(selector)+");if(!el)return false;"+
    "const proto=el.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;"+
    "const setter=Object.getOwnPropertyDescriptor(proto,'value').set;"+
    "setter.call(el,"+q(value)+");"+
    "el.dispatchEvent(new Event('input',{bubbles:true}));"+
    "el.dispatchEvent(new Event('change',{bubbles:true}));return true})()";
  assert.equal(await evaluate(expression),true,"Could not fill "+selector);
}

async function pointerClick(selector){
  const point=await evaluate("(()=>{const el=document.querySelector("+q(selector)+");if(!el)return null;const r=el.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()");
  assert.ok(point,"Missing pointer target "+selector);
  await send("Input.dispatchMouseEvent",{type:"mouseMoved",...point});
  await send("Input.dispatchMouseEvent",{type:"mousePressed",...point,button:"left",clickCount:1});
  await send("Input.dispatchMouseEvent",{type:"mouseReleased",...point,button:"left",clickCount:1});
}


const accounts=[];
const report={checks:[],account_ids:[],cleanup:[]};
async function api(path,method='GET',body,token=''){
 const options={method,headers:{'Content-Type':'application/json',...(token?{Authorization:'Bearer '+token}:{})},body:body===undefined?undefined:JSON.stringify(body)};
 // Exercise the browser's HTTPS path, including cleanup, instead of a separate Node TLS client.
 return evaluate("fetch("+q(origin+'/api'+path)+","+JSON.stringify(options)+").then(async r=>({status:r.status,data:await r.json()}))");
}
async function register(){
 const account={username:'sl_accept_'+Date.now()+'_'+accounts.length,password:crypto.randomUUID()+'aA1!'};
 accounts.push(account);
 await navigate('/account');await waitFor("document.querySelector('.account-form input[name=username]')!==null");
 await click('.account-panel .segmented button:last-child');
 await fill('[name=username]',account.username);await fill('[name=password]',account.password);
 await pointerClick('[aria-label=显示密码]');
 assert.equal(await evaluate("document.querySelector('[name=password]').type"),'text');
 await pointerClick('[aria-label=隐藏密码]');
 assert.equal(await evaluate("document.querySelector('[name=password]').type"),'password');
 await click('.account-form button[type=submit], .account-form button.button-primary');
 await waitFor("document.querySelector('.account-page h1')?.textContent==='你的研究账户'");
 await waitFor("document.querySelector('.account-page')?.textContent.includes('阅读空间已连接')");
 account.token=await evaluate("sessionStorage.getItem('scholarlens-session')");
 assert.ok(account.token,'Login must create a real server session');
 const me=await api('/auth/me','GET',undefined,account.token);
 assert.equal(me.status,200);report.account_ids.push(me.data.id);
 return account;
}
async function uiLogout(){
 await navigate('/account');await waitFor("document.querySelector('.account-page')?.textContent.includes('阅读空间已连接')");
 await evaluate("[...document.querySelectorAll('.account-page button')].find(b=>b.textContent==='退出登录').click()");
 await waitFor("document.querySelector('.account-form input[name=username]')!==null");
 assert.equal(await evaluate("sessionStorage.getItem('scholarlens-session')"),null);
}
async function run(){
 processHandle=spawn(chrome,['--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check','--disable-background-networking','--remote-debugging-port=0','--window-size=1440,900','--user-data-dir='+profile,'about:blank'],{stdio:'ignore',windowsHide:true});
 const port=await waitPort();const tab=await (await fetch('http://127.0.0.1:'+port+'/json/new?'+encodeURIComponent(origin+'/'),{method:'PUT'})).json();
 connection=await connect(tab.webSocketDebuggerUrl);await send('Page.enable');await send('Runtime.enable');
 await navigate('/search?q=magnetic');await waitFor("document.querySelectorAll('.paper-card').length>0");
 const paperId=await evaluate("document.querySelector('.paper-card').dataset.paperId");
 await click('.paper-card .bookmark-button');
 const guest=await evaluate("localStorage.getItem('scholarlens-v1:favorites')");
 const a=await register();report.checks.push('register-login-through-ui');
 assert.equal((await api('/me/workspace','GET',undefined,a.token)).data.favorites.length,0,'Guest data must not upload on login');
 await navigate('/paper/'+encodeURIComponent(paperId));await waitFor("document.querySelector('.detail-header')!==null");
 await waitFor("document.querySelector('.detail-buttons .button-primary')?.disabled===false");
 await click('.detail-buttons .button-primary');
 await waitFor("document.querySelector('.detail-buttons .button-primary')?.textContent.includes('已收藏')");
 await click('a[href="/library"]');await waitFor("document.querySelector('.library-paper-item')!==null");
 await click('.note-edit-button');await fill('.reading-note textarea','End-to-end persistence note');
 await waitFor("document.querySelector('.toast')===null",6000).catch(()=>{});
 let snapshot;
 for(let i=0;i<50;i++){snapshot=(await api('/me/workspace','GET',undefined,a.token)).data;if(snapshot.favorites?.[0]?.note==='End-to-end persistence note'&&snapshot.history?.[0]?.paper.paper_id===paperId)break;await delay(150);}
 assert.equal(snapshot.favorites?.[0]?.note,'End-to-end persistence note');
 assert.equal(snapshot.history?.[0]?.paper.paper_id,paperId);
 assert.equal((await api('/me/favorites','GET',undefined,a.token)).data.total,1);
 report.checks.push('favorite-note-reading-native-persistence');
 await navigate('/account');await waitFor("document.querySelector('.account-form')!==null");
 const shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});fs.mkdirSync('output/api-integration',{recursive:true});fs.writeFileSync('output/api-integration/account-authenticated.png',Buffer.from(shot.data,'base64'));
 await uiLogout();assert.equal((await api('/auth/me','GET',undefined,a.token)).status,401);report.checks.push('logout-revokes-server-token');
 assert.equal(await evaluate("localStorage.getItem('scholarlens-v1:favorites')"),guest,'Guest state must remain byte-for-byte intact');
 const b=await register();assert.equal((await api('/me/workspace','GET',undefined,b.token)).data.favorites.length,0);report.checks.push('second-user-isolation');
 await uiLogout();
 await fill('[name=username]',a.username);await fill('[name=password]',a.password);await click('.account-form button.button-primary');
 await waitFor("document.querySelector('.account-page h1')?.textContent==='你的研究账户'");
 await waitFor("document.querySelector('.account-page')?.textContent.includes('阅读空间已连接')");
 a.token=await evaluate("sessionStorage.getItem('scholarlens-session')");
 await navigate('/library');await waitFor("document.querySelector('.library-paper-item')!==null");
 await click('.note-edit-button');assert.equal(await evaluate("document.querySelector('.reading-note textarea').value"),'End-to-end persistence note');
 report.checks.push('relogin-reload-note-restoration');
 await navigate('/upload');await waitFor("document.querySelector('.account-panel input[type=file]')!==null");
 const root=await send('DOM.getDocument');const input=await send('DOM.querySelector',{nodeId:root.root.nodeId,selector:'.account-panel input[type=file]'});
 await send('DOM.setFileInputFiles',{nodeId:input.nodeId,files:[path.resolve('tests/fixtures/browser-upload.pdf')]});
 await waitFor("document.querySelector('.server-selected-file')!==null");
 await click('.server-selected-file .button-primary');
 await waitFor("document.querySelector('.server-upload-row strong')?.textContent==='browser-upload.pdf'");
 assert.ok(await evaluate("document.querySelector('.server-upload-row').textContent.includes('待审核')"));
 await click('.server-upload-row button:first-child');
 await waitFor("document.querySelector('.server-pdf-preview')?.src.startsWith('blob:')");
 report.checks.push('server-upload-pending-and-authenticated-pdf-preview');
 await navigate('/admin');await waitFor("document.querySelector('.account-panel h2')?.textContent==='需要管理员身份'");
 assert.equal(await evaluate("document.querySelectorAll('.server-upload-row').length"),0);report.checks.push('ordinary-user-admin-gate');

 await navigate('/account');await waitFor("document.querySelector('[aria-label=显示名称]')!==null");
 await fill('[aria-label=显示名称]','Acceptance researcher');
 await click('.account-form button.button-primary');
 await waitFor("document.querySelector('.account-page')?.textContent.includes('资料已保存')");
 assert.equal((await api('/me/profile','GET',undefined,a.token)).data.display_name,'Acceptance researcher');report.checks.push('profile-update-through-ui');
 await pointerClick('.account-settings-nav button:nth-child(2)');
 assert.ok(await evaluate("[...document.querySelectorAll('.account-settings section')].some(el=>!el.hidden&&el.textContent.includes('修改密码'))"));
 assert.equal(await evaluate("document.querySelector('[aria-label=显示名称]').closest('section').hidden"),true);
 await pointerClick('.account-settings-nav button:first-child');
 assert.equal(await evaluate("document.querySelector('[aria-label=显示名称]').closest('section').hidden"),false);
 report.checks.push('password-visibility-and-account-section-navigation');
 await navigate('/assistant');await waitFor("document.querySelector('[aria-label=研究对话]')!==null");
 await waitFor("document.querySelector('.ai-compose button[type=submit]')?.textContent.includes('检索原文')");
 assert.ok(await evaluate("document.querySelector('.ai-compose button[type=submit]').getBoundingClientRect().bottom<=innerHeight"),'Assistant primary action must be visible on the desktop first screen');
 await fill('[aria-label=研究问题]','magnetic resonance imaging');await pointerClick('.ai-compose button[type=submit]');
 await waitFor("document.querySelectorAll('.evidence-result').length>0",60000);
 assert.ok(await evaluate("document.querySelector('.evidence-result p').textContent.length>20"));
 report.checks.push('unconfigured-ai-can-retrieve-real-evidence');
 await evaluate("[...document.querySelectorAll('button')].find(b=>b.textContent==='新建对话').click()");
 await waitFor("document.querySelector('[aria-label=研究对话]').value.startsWith('conv-')");
 const conversation=await evaluate("document.querySelector('[aria-label=研究对话]').value");
 await navigate('/assistant');await waitFor("Array.from(document.querySelector('[aria-label=研究对话]')?.options||[]).some(o=>o.value==="+q(conversation)+")");
 await evaluate("(()=>{const el=document.querySelector('[aria-label=研究对话]');el.value="+q(conversation)+";el.dispatchEvent(new Event('change',{bubbles:true}));})()");
 await waitFor("document.querySelector('[aria-label=研究对话]').value==="+q(conversation));
 await evaluate("window.confirm=()=>true;[...document.querySelectorAll('button')].find(b=>b.textContent==='删除对话').click()");
 await waitFor("!Array.from(document.querySelector('[aria-label=研究对话]')?.options||[]).some(o=>o.value==="+q(conversation)+")");
 assert.ok(!(await api('/ai/conversations','GET',undefined,a.token)).data.some(row=>row.id===conversation));report.checks.push('conversation-create-reopen-delete-through-ui');

 await click('.personal-ai-settings summary');
 await fill('[aria-label=个人API地址]','https://provider.example/v1');
 await fill('[aria-label=个人API模型]','acceptance-model');
 await fill('[aria-label=个人API密钥]','test-only-session-credential');
 await click('.personal-ai-settings .button-primary');
 await waitFor("document.querySelector('.personal-ai-settings summary').textContent.includes('已填写')");
 assert.ok(await evaluate("Object.values(sessionStorage).includes('test-only-session-credential')"));
 assert.ok(!await evaluate("Object.values(localStorage).join('').includes('test-only-session-credential')"));
 await navigate('/assistant');await waitFor("document.querySelector('.personal-ai-settings summary')?.textContent.includes('已填写')");
 await uiLogout();
 assert.ok(!await evaluate("Object.values(sessionStorage).join('').includes('test-only-session-credential')"));
 await fill('[name=username]',b.username);await fill('[name=password]',b.password);await click('.account-form button.button-primary');
 await waitFor("document.querySelector('.account-page')?.textContent.includes('阅读空间已连接')");
 await navigate('/assistant');await waitFor("document.querySelector('.personal-ai-settings summary')?.textContent.includes('未配置')");
 assert.equal(await evaluate("document.querySelector('[aria-label=个人API地址]').value"),'');
 await uiLogout();await fill('[name=username]',a.username);await fill('[name=password]',a.password);await click('.account-form button.button-primary');
 await waitFor("document.querySelector('.account-page')?.textContent.includes('阅读空间已连接')");
 a.token=await evaluate("sessionStorage.getItem('scholarlens-session')");
 report.checks.push('personal-api-session-only-persistence-logout-clear-and-two-user-isolation');

 await navigate('/search?q=magnetic');await waitFor("document.querySelectorAll('.paper-card').length===6");
 // Results render before the asynchronous history write completes, especially over HTTPS.
 // Wait for that first query to persist before measuring whether pagination adds records.
 await waitFor("fetch('/api/me/history',{headers:{Authorization:'Bearer '+sessionStorage.getItem('scholarlens-session')}}).then(async r=>r.ok&&(await r.json()).results.some(item=>item.q==='magnetic'&&item.field==='all'&&item.mode==='keyword'))");
 const count=(await api('/me/history','GET',undefined,a.token)).data.total;
 await click('.pagination button:last-child');await waitFor("new URLSearchParams(location.search).get('page')==='2' && document.querySelectorAll('.paper-card').length===6");
 assert.equal((await api('/me/history','GET',undefined,a.token)).data.total,count,'Pagination must not create search-history records');report.checks.push('search-history-deduplication');

 assert.equal((await api('/auth/logout','POST',undefined,a.token)).status,200);
 await navigate('/account');await waitFor("document.querySelector('.account-form input[name=username]')!==null");
 assert.equal(await evaluate("sessionStorage.getItem('scholarlens-session')"),null);
 assert.equal(await evaluate("localStorage.getItem('scholarlens-v1:favorites')"),guest);
 report.checks.push('server-revoked-session-clears-ui-and-restores-guest');
 await fill('[name=username]',a.username);await fill('[name=password]',a.password);await click('.account-form button.button-primary');
 await waitFor("document.querySelector('.account-page')?.textContent.includes('阅读空间已连接')");
 a.token=await evaluate("sessionStorage.getItem('scholarlens-session')");

 await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
 for(const route of ['/account','/upload','/assistant']){
   await navigate(route);await waitFor("document.querySelector('.workspace-page h1')!==null");
   assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth'),route+' must not overflow at 390px');
   assert.ok(await evaluate("(()=>{const r=document.querySelector('.mobile-menu-button').getBoundingClientRect();return r.x>=0&&r.right<=innerWidth})()"),route+' must keep navigation accessible with a signed-in username');
   const mobileShot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
   fs.writeFileSync('output/api-integration/'+route.slice(1)+'-authenticated-390.png',Buffer.from(mobileShot.data,'base64'));
 }
 await send('Emulation.setDeviceMetricsOverride',{width:1440,height:900,deviceScaleFactor:1,mobile:false});
 report.checks.push('authenticated-pages-390px-geometry');
 await uiLogout();
 await navigate('/account?next=%2Fassistant');await waitFor("document.querySelector('.auth-submit')!==null");
 await fill('[name=username]',a.username);await fill('[name=password]',a.password);await pointerClick('.auth-submit');
 await waitFor("location.pathname==='/assistant'&&document.querySelector('[aria-label=研究问题]')!==null");
 report.checks.push('login-returns-to-requested-workflow');
 await uiLogout();
 await navigate('/upload?storage=local');await waitFor("document.querySelector('.upload-drop input[type=file]')!==null");
 const localRoot=await send('DOM.getDocument');const localInput=await send('DOM.querySelector',{nodeId:localRoot.root.nodeId,selector:'.upload-drop input[type=file]'});
 await send('DOM.setFileInputFiles',{nodeId:localInput.nodeId,files:[path.resolve('tests/fixtures/browser-upload.pdf')]});
 await waitFor("document.querySelector('.selected-file .button-primary')!==null");await click('.selected-file .button-primary');
 await waitFor("document.querySelector('.file-queue-row strong')?.textContent==='browser-upload.pdf'");
 const localUpload=await evaluate("JSON.parse(localStorage.getItem('scholarlens-v1:uploads'))[0]");
 assert.match(localUpload.sha256,/^[a-f0-9]{64}$/);
 await navigate('/upload?storage=local');await waitFor("document.querySelector('.file-queue-row strong')?.textContent==='browser-upload.pdf'");
 await click('.file-queue-actions .button');await waitFor("document.querySelector('.pdf-viewer-frame')?.src.startsWith('blob:')");
 assert.ok(await evaluate("document.querySelector('dialog.pdf-viewer-backdrop').matches(':modal')"));
 await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
 await send('Input.dispatchKeyEvent',{type:'keyUp',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
 await waitFor("document.querySelector('.pdf-viewer')===null");
 await click('.upload-aside a[href="/admin?storage=local"]');await waitFor("document.querySelector('.review-entry')!==null");
 await fill('.review-note textarea','Local-only acceptance review');await click('.review-actions .button-primary');
 await waitFor("document.querySelector('.review-entry .status-approved')!==null");
 await navigate('/admin?storage=local');await waitFor("document.querySelector('.review-entry .status-approved')!==null");
 assert.ok(await evaluate("document.querySelector('.review-note textarea').value.includes('Local-only acceptance review')"));
 assert.equal((await api('/stats')).data.papers,859,'Local approval must not modify the real base index');
 report.checks.push('local-pdf-indexeddb-reload-preview-and-review-isolation');
 console.log('PASS authenticated browser: '+report.checks.join(', '));
}
try{await run();report.status='passed';}
catch(error){report.status='failed';report.error=error.message;try{report.page=await evaluate("({url:location.pathname,h1:document.querySelector('h1')?.textContent,alert:document.querySelector('[role=alert]')?.textContent,toast:document.querySelector('.toast')?.textContent})");const image=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});fs.writeFileSync('output/api-integration/account-e2e-failure.png',Buffer.from(image.data,'base64'));}catch{}throw error;}
finally{
 for(const account of accounts){
   try{
     const login=await api('/auth/login','POST',{username:account.username,password:account.password});
     if(login.status===200){const result=await api('/auth/deactivate','POST',{username:account.username,password:account.password},login.data.access_token);report.cleanup.push({username:account.username,status:result.status});}
   }catch(error){report.cleanup.push({username:account.username,error:error.message});}
 }
 fs.mkdirSync('output/api-integration',{recursive:true});fs.writeFileSync('output/api-integration/account-e2e-report.json',JSON.stringify(report,null,2));
 try{connection?.close()}catch{};if(processHandle&&!processHandle.killed)processHandle.kill();
 // Disposable Chrome profile contains no user's browser state. Leave it for normal temporary-file cleanup.
}
