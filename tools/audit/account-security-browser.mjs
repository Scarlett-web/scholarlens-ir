/** Real local account acceptance. Always starts its own fixture; never accepts a service URL. */
import {chromium} from 'playwright';
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {mkdirSync,writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {once} from 'node:events';
import {createInterface} from 'node:readline';
import {randomUUID} from 'node:crypto';

const repo=fileURLToPath(new URL('../../',import.meta.url));
const output=join(repo,'tools/audit/reports/account-security-'+new Date().toISOString().replace(/[:.]/g,'-'));
mkdirSync(output,{recursive:true});
const python=join(repo,'backend/.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python');
const server=spawn(python,['-u','-m','backend.tests.account_fixture','--output',output],{
 cwd:repo,stdio:['ignore','pipe','pipe'],env:{...process.env,PYTHONUNBUFFERED:'1'},
});
const report={passed:false,scope:'fresh loopback fixture, real account/workspace routes and SQLite; no ES, production accounts, email or supplier',checks:[]};
let browser,serverError='',origin='',gateRelease;
const errors=[],external=[],pages=[],browserInternal=[];
server.stderr.on('data',chunk=>{serverError+=chunk.toString();});
const exited=once(server,'exit');
let readyTimer;
try{
 const identity=await Promise.race([
  new Promise((resolve,reject)=>{
   const lines=createInterface({input:server.stdout});
   lines.once('line',line=>{try{resolve(JSON.parse(line));}catch{reject(new Error('Fixture did not return its identity'));}finally{lines.close();}});
   server.once('error',reject);
   server.once('exit',()=>reject(new Error('Isolated fixture exited before readiness')));
  }),
  new Promise((_,reject)=>{readyTimer=setTimeout(()=>reject(new Error('Fixture readiness timed out')),15000);}),
 ]);
 clearTimeout(readyTimer);
 assert.ok(Number.isInteger(identity.port)&&identity.port>0);
 origin='http://127.0.0.1:'+identity.port;
 const handshake=await fetch(origin+'/__isolated_account_fixture__?'+new URLSearchParams({value:identity.challenge}),{redirect:'error'});
 assert.equal(handshake.status,200);
 assert.deepEqual(await handshake.json(),{isolated:true,challenge:identity.challenge,external_services:false});
 report.checks.push('owned random-port fixture and per-instance challenge verified before any write');
 browser=await chromium.launch({channel:'chrome',headless:true});
 const context=await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
 context.on('page',page=>{pages.push(page);page.on('pageerror',error=>errors.push(error.message));});
 await context.route('**/*',route=>{
  const url=route.request().url(),parsed=new URL(url);
  // Native PDF viewer data resources and owned Blob URLs do not contact remote hosts.
  if(route.request().method()==='GET'&&(
    parsed.protocol==='data:'||
    parsed.protocol==='blob:'&&parsed.origin===origin||url==='about:blank'
  ))return route.continue();
  const nativePdfResource=parsed.protocol==='chrome:'&&parsed.host==='resources'||
    parsed.protocol==='chrome-extension:'&&parsed.host==='mhjfbmdgcfjbbpaeojofohoefgiehjai';
  if(route.request().method()==='GET'&&nativePdfResource){browserInternal.push({protocol:parsed.protocol,host:parsed.host,path:parsed.pathname});return route.continue();}
  if(!url.startsWith(origin+'/')){external.push({protocol:parsed.protocol,host:parsed.host,path:parsed.pathname.slice(0,160),method:route.request().method()});return route.abort();}
  return route.continue();
 });
 const page=await context.newPage();
 page.on('dialog',dialog=>dialog.message().startsWith('确认停用此账户')?dialog.accept():dialog.dismiss());
 const accountResponse=await page.goto(origin+'/account',{waitUntil:'domcontentloaded'});
 assert.equal(accountResponse?.status(),200);
 const cspHeader=accountResponse?.headers()['content-security-policy']||'';
 assert.ok(cspHeader,'Account HTML response must include Content-Security-Policy');
 const csp=new Map(cspHeader.split(';').map(part=>part.trim().split(/\s+/)).filter(parts=>parts[0]).map(([name,...sources])=>[name,sources]));
 const requireCspSources=(name,sources)=>{
  const actual=csp.get(name);assert.ok(actual,`CSP must declare ${name}`);
  for(const source of sources)assert.ok(actual.includes(source),`CSP ${name} must include ${source}`);
 };
 requireCspSources('default-src',["'self'"]);requireCspSources('script-src',["'self'"]);requireCspSources('connect-src',["'self'"]);
 requireCspSources('style-src',["'self'","'unsafe-inline'"]);requireCspSources('img-src',["'self'",'data:','blob:']);
 requireCspSources('frame-src',["'self'",'blob:']);requireCspSources('object-src',["'self'",'blob:']);
 requireCspSources('base-uri',["'self'"]);requireCspSources('form-action',["'self'"]);requireCspSources('frame-ancestors',["'self'"]);
 const blobPdf=await page.evaluate(async()=>{
  const violations=[];const onViolation=event=>violations.push({directive:event.effectiveDirective,blockedURI:event.blockedURI});
  document.addEventListener('securitypolicyviolation',onViolation);
  const objects=['<< /Type /Catalog /Pages 2 0 R >>','<< /Type /Pages /Kids [3 0 R] /Count 1 >>','<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 300] /Resources << >> >>'];
  let pdf='%PDF-1.4\n';const offsets=[0];
  objects.forEach((body,index)=>{offsets.push(pdf.length);pdf+=(index+1)+' 0 obj\n'+body+'\nendobj\n';});
  const xref=pdf.length;pdf+='xref\n0 4\n0000000000 65535 f \n'+offsets.slice(1).map(offset=>String(offset).padStart(10,'0')+' 00000 n \n').join('')+'trailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n'+xref+'\n%%EOF\n';
  const url=URL.createObjectURL(new Blob([pdf],{type:'application/pdf'}));const iframe=document.createElement('iframe');
  iframe.title='Synthetic PDF CSP check';iframe.setAttribute('aria-hidden','true');iframe.style.cssText='position:fixed;width:1px;height:1px;opacity:0;pointer-events:none';
  let loaded=false;
  try{
   await new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>reject(new Error('Synthetic PDF Blob iframe did not load')),10000);
    iframe.addEventListener('load',()=>{loaded=true;clearTimeout(timer);resolve();},{once:true});
    iframe.addEventListener('error',()=>{clearTimeout(timer);reject(new Error('Synthetic PDF Blob iframe failed to load'));},{once:true});
    iframe.src=url;document.body.appendChild(iframe);
   });
   await new Promise(resolve=>setTimeout(resolve,100));
   return {loaded,violations};
  }finally{iframe.remove();URL.revokeObjectURL(url);document.removeEventListener('securitypolicyviolation',onViolation);}
 });
 assert.equal(blobPdf.loaded,true);assert.deepEqual(blobPdf.violations,[],'Synthetic PDF Blob iframe must not trigger a CSP violation');
 assert.deepEqual(external,[],'PDF viewer must not contact external network resources');
 report.csp={header_present:true,required_directives:[...csp.keys()],pdf_blob_iframe:blobPdf};
 report.checks.push('account HTML carries the required CSP, the real login flow remains usable, and a local synthetic PDF Blob iframe loads without CSP violations');
 const api=async(path,{method='GET',body,token}={})=>{
  const response=await context.request.fetch(origin+'/api'+path,{method,data:body,headers:token?{Authorization:'Bearer '+token}:{},maxRedirects:0});
  return {status:response.status(),data:await response.json()};
 };
 const responseFor=path=>page.waitForResponse(response=>new URL(response.url()).pathname==='/api'+path&&response.request().method()==='POST');
 const session=()=>page.evaluate(()=>sessionStorage.getItem('scholarlens-session'));
 const keyPresent=()=>page.evaluate(()=>Object.keys(sessionStorage).some(name=>name.startsWith('scholarlens-ai-key:')));
 const markKey=()=>page.evaluate(()=>sessionStorage.setItem('scholarlens-ai-key:isolated-acceptance','fixture-only-not-a-provider-key'));
 const noOverflow=async()=>assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 const loggedIn=async()=>{
  await page.getByRole('heading',{name:'你的研究账户',exact:true}).waitFor();
  await page.getByText('阅读空间已连接',{exact:true}).waitFor();
 };
 const loginUI=async(credentials)=>{
  await page.goto(origin+'/account');
  await page.getByLabel('用户名',{exact:true}).fill(credentials.username);
  await page.getByLabel('密码',{exact:true}).fill(credentials.password);
  await page.locator('.auth-submit').click();await loggedIn();
 };
 const security=async()=>{
  await page.goto(origin+'/account');await loggedIn();
  await page.getByRole('button',{name:'账户安全',exact:true}).click();
  await page.getByLabel('当前密码',{exact:true}).waitFor();
 };
 const password=async(current,next)=>{
  await page.getByLabel('当前密码',{exact:true}).fill(current);
  await page.getByLabel('新密码',{exact:true}).fill(next);
  const response=responseFor('/auth/password');
  await page.getByRole('button',{name:'修改并重新登录',exact:true}).click();
  return response;
 };
 const deactivate=async(credentials)=>{
  const detail=page.locator('details').filter({has:page.locator('summary',{hasText:'停用账户'})});
  if(!await detail.evaluate(el=>el.open))await detail.locator('summary').click();
  await page.getByLabel('确认用户名',{exact:true}).fill(credentials.username);
  await page.getByLabel('确认密码',{exact:true}).fill(credentials.password);
  const response=responseFor('/auth/deactivate');
  await page.getByRole('button',{name:'确认停用',exact:true}).click();
  return response;
 };
 const alice={username:'fixture_alice',password:'fixture-original-'+randomUUID()};
 const nextPassword='fixture-replacement-'+randomUUID();
 const bob={username:'fixture_bob',password:'fixture-original-'+randomUUID()};
 await page.goto(origin+'/account');
 await page.getByRole('button',{name:'创建账户',exact:true}).click();
 await page.getByLabel('用户名',{exact:true}).fill(alice.username);
 await page.getByLabel('密码',{exact:true}).fill(alice.password);
 await page.getByRole('button',{name:'创建并登录',exact:true}).click();await loggedIn();
 const original=await session();assert.ok(original);
 const second=(await api('/auth/login',{method:'POST',body:alice})).data.access_token;assert.ok(second);
 assert.equal((await api('/auth/register',{method:'POST',body:bob})).status,201);
 report.checks.push('real UI registration/login and second independent server session');

 const workspace=(await api('/me/workspace',{token:original})).data;
 assert.equal((await api('/me/workspace',{method:'PUT',token:original,body:{version:workspace.version,collections:['全部收藏','待读'],favorites:[{paper_id:'fixture:account-paper',collection:'待读',note:'Private fixture note'}],history:[]}})).status,200);
 await page.goto(origin+'/library');
 await page.getByRole('button',{name:'查看 / 修改笔记',exact:true}).click();
 const note=page.getByRole('textbox',{name:'我的阅读笔记',exact:true});await note.waitFor();
 assert.equal(await note.inputValue(),'Private fixture note');
 const saved=page.waitForResponse(response=>new URL(response.url()).pathname==='/api/me/workspace'&&response.request().method()==='PUT');
 await note.fill('Edited fixture note through the real UI');assert.equal((await saved).status(),200);
 await page.reload();await page.getByRole('button',{name:'查看 / 修改笔记',exact:true}).click();
 await note.waitFor();assert.equal(await note.inputValue(),'Edited fixture note through the real UI');
 report.checks.push('real account workspace write, UI note edit, server persistence and browser reload');

 await security();await markKey();
 const wrong=await password('fixture-wrong-password',nextPassword);
 assert.equal(wrong.status(),401);
 const wrongBody=await wrong.json();
 await page.waitForFunction(()=>document.querySelector('[role=alert]')||!sessionStorage.getItem('scholarlens-session'));
 const observed={error_code:wrongBody.error?.code,server_session_valid:(await api('/auth/me',{token:original})).status===200,ui_session_retained:(await session())===original,session_configuration_retained:await keyPresent()};
 report.wrong_password_observation=observed;
 assert.ok(observed.server_session_valid&&observed.ui_session_retained&&observed.session_configuration_retained,'Wrong current password must preserve the still-valid account session and configuration');
 assert.equal(observed.error_code,'invalid_credentials');
 await page.getByText('当前密码错误',{exact:true}).waitFor();
 await noOverflow();await page.screenshot({path:join(output,'wrong-password-desktop.png')});
 await page.setViewportSize({width:390,height:844});await noOverflow();await page.screenshot({path:join(output,'wrong-password-390.png')});
 await page.setViewportSize({width:1440,height:1000});
 report.checks.push('wrong current password remains in account, shows retryable error and retains session configuration; desktop/390 geometry');

 const wrongDeactivate=await deactivate({...alice,password:'fixture-wrong-password'});
 assert.equal(wrongDeactivate.status(),401);assert.equal((await wrongDeactivate.json()).error.code,'invalid_credentials');
 await page.getByText('请确认当前用户名和密码',{exact:true}).waitFor();
 assert.ok((await session())===original);assert.ok(await keyPresent());
 assert.equal((await api('/auth/me',{token:second})).status,200);
 report.checks.push('wrong deactivation credentials preserve both real sessions and permit retry');

 assert.equal((await password(alice.password,nextPassword)).status(),200);
 await page.getByRole('heading',{name:'欢迎回来',exact:true}).waitFor();
 assert.ok(!await session());assert.equal(await keyPresent(),false);
 for(const token of [original,second])assert.equal((await api('/auth/me',{token})).status,401);
 assert.equal((await api('/auth/login',{method:'POST',body:alice})).status,401);
 alice.password=nextPassword;await loginUI(alice);
 let current=await session();assert.ok(current);
 const afterChange=(await api('/me/workspace',{token:current})).data;
 assert.equal(afterChange.favorites[0].note,'Edited fixture note through the real UI');
 report.checks.push('successful UI password change revokes all prior sessions, clears client configuration and preserves notes; only new password works');

 await security();await markKey();
 assert.equal((await api('/auth/logout',{method:'POST',token:current})).status,200);
 const revoked=await password(alice.password,'fixture-unused-next-password');
 assert.equal(revoked.status(),401);assert.equal((await revoked.json()).error.code,'unauthenticated');
 await page.getByRole('heading',{name:'欢迎回来',exact:true}).waitFor();
 assert.ok(!await session());assert.equal(await keyPresent(),false);
 report.checks.push('real revoked token at the same password endpoint still clears login and session configuration');

 await loginUI(alice);await security();await markKey();current=await session();
 assert.equal((await api('/auth/logout',{method:'POST',token:current})).status,200);
 let fetchedResolve;const fetched=new Promise(resolve=>{fetchedResolve=resolve;});
 const gate=new Promise(resolve=>{gateRelease=resolve;});
 const hold=async route=>{const response=await route.fetch({maxRedirects:0});fetchedResolve();await gate;await route.fulfill({response});};
 await page.route('**/api/auth/password',hold);
 await page.getByLabel('当前密码',{exact:true}).fill(alice.password);
 await page.getByLabel('新密码',{exact:true}).fill('fixture-unused-next-password');
 const delayed=responseFor('/auth/password');await page.getByRole('button',{name:'修改并重新登录',exact:true}).click();
 await fetched;
 const freshLogin=await api('/auth/login',{method:'POST',body:alice});assert.equal(freshLogin.status,200);
 const fresh=freshLogin.data.access_token;
 await page.evaluate(token=>sessionStorage.setItem('scholarlens-session',token),fresh);
 gateRelease();assert.equal((await delayed).status(),401);
 await page.getByRole('alert').filter({hasText:'登录'}).waitFor();
 assert.ok((await session())===fresh);assert.ok(await keyPresent());
 assert.equal((await api('/auth/me',{token:fresh})).status,200);
 await page.unroute('**/api/auth/password',hold);
 report.checks.push('a real delayed 401 for an old token cannot erase a newer session or its configuration');

 await security();
 const extra=(await api('/auth/login',{method:'POST',body:alice})).data.access_token;
 assert.equal((await deactivate(alice)).status(),200);
 await page.getByRole('heading',{name:'欢迎回来',exact:true}).waitFor();
 assert.ok(!await session());assert.equal(await keyPresent(),false);
 for(const token of [fresh,extra])assert.equal((await api('/auth/me',{token})).status,401);
 assert.equal((await api('/auth/login',{method:'POST',body:alice})).status,401);
 await loginUI(bob);const bobToken=await session();
 assert.deepEqual((await api('/me/workspace',{token:bobToken})).data.favorites,[]);
 assert.equal(await keyPresent(),false);
 await page.getByRole('button',{name:'退出登录',exact:true}).click();
 await page.getByRole('heading',{name:'欢迎回来',exact:true}).waitFor();
 assert.equal((await api('/auth/me',{token:bobToken})).status,401);
 report.checks.push('successful deactivation revokes all sessions and prevents login; second user has an isolated empty workspace and can log out normally');
 assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
 report.passed=true;
}catch(error){
 report.error=error.message;
 if(pages[0])await pages[0].screenshot({path:join(output,'failure.png')}).catch(()=>{});
 process.exitCode=1;
}finally{
 clearTimeout(readyTimer);gateRelease?.();
 await browser?.close();
 if(server.exitCode===null)server.kill();
 await Promise.race([exited,new Promise(resolve=>setTimeout(resolve,5000).unref())]);
 Object.assign(report,{page_errors:errors,external_requests:external,browser_internal_resources:browserInternal,fixture_stopped:server.exitCode!==null||server.signalCode!==null});
 if(!report.fixture_stopped||serverError){report.passed=false;report.fixture_error=serverError.slice(-1500);process.exitCode=1;}
 writeFileSync(join(output,'report.json'),JSON.stringify(report,null,2));
 console.log(JSON.stringify({...report,output}));
}
