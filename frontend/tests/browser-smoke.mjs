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

async function exerciseReader() {
  await waitFor("document.querySelector('.reader-focus-button')!==null");
  await click('.reader-focus-button');
  await waitFor("document.querySelector('.detail-page').dataset.readingFocus==='true'");
  assert.equal(await evaluate("getComputedStyle(document.querySelector('.app-sidebar')).display"),'none');
  const position=await evaluate("(()=>{const a=document.querySelector('.detail-main'),offset=document.querySelector('.reader-tools').getBoundingClientRect().height+24;return scrollY+a.getBoundingClientRect().top-offset+.45*(a.getBoundingClientRect().height-innerHeight+offset)})()");
  await evaluate('window.scrollTo({top:'+position+',behavior:"instant"})');
  await waitFor("Number(document.querySelector('.reader-progress progress').value)>=40");
  try {await waitFor("JSON.parse(localStorage.getItem('scholarlens-v1:reading-positions:guest')||'{}')[decodeURIComponent(location.pathname.slice(7))]?.ratio>.4");}
  catch(error){console.error('Reading position diagnostic',await evaluate("(()=>{const a=document.querySelector('.detail-main');return {path:location.pathname,progress:document.querySelector('.reader-progress progress')?.value,position:scrollY,height:a?.offsetHeight,rect:a?.getBoundingClientRect().toJSON(),stored:localStorage.getItem('scholarlens-v1:reading-positions:guest'),focused:document.querySelector('.detail-page')?.dataset.readingFocus,folded:!!document.querySelector('.reader-fold-notice')}})()"));throw error;}
  const paperPath=await evaluate('location.pathname');
  await navigate(paperPath);
  await waitFor("document.querySelector('.reader-resume')!==null");
  await click('.reader-resume button:not(.icon-button)');
  await waitFor("Math.abs(Number(document.querySelector('.reader-progress progress').value)-45)<8");
  assert.ok(await evaluate("!document.querySelector('.reader-resume')"));
  await click('.reader-toolbar nav button:first-child');
  const excerpt=await evaluate("(()=>{const p=document.querySelector('#paper-abstract [data-reader-text]');const node=p.firstChild;const r=document.createRange();r.setStart(node,0);r.setEnd(node,Math.min(60,node.textContent.length));const s=getSelection();s.removeAllRanges();s.addRange(r);p.dispatchEvent(new MouseEvent('mouseup',{bubbles:true}));return s.toString().trim()})()");
  assert.ok(excerpt.length>10);
  await waitFor("document.querySelector('.reader-selection')!==null");
  await click('.reader-selection button:nth-of-type(2)');
  await waitFor("JSON.parse(localStorage.getItem('scholarlens-v1:favorites')||'[]').some(e=>e.note.includes("+q(excerpt)+"))");
  await evaluate("(()=>{const p=document.querySelector('#paper-abstract [data-reader-text]'),n=p.firstChild,r=document.createRange();r.setStart(n,5);r.setEnd(n,Math.min(70,n.textContent.length));getSelection().removeAllRanges();getSelection().addRange(r);p.dispatchEvent(new MouseEvent('mouseup',{bubbles:true}));})()");
  await waitFor("document.querySelector('.reader-selection')!==null");
  await click('.reader-selection button:nth-of-type(2)');
  assert.ok(await waitFor("JSON.parse(localStorage.getItem('scholarlens-v1:favorites')||'[]').some(e=>e.note.includes("+q(excerpt)+")&&e.note.split('摘录：').length===3)"),'append must preserve the first excerpt');
  await click('.reader-focus-button');
  await evaluate('window.scrollTo({top:0,behavior:"instant"})');
  fs.mkdirSync('output/api-integration',{recursive:true});
  const focusShot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
  fs.writeFileSync('output/api-integration/reader-focus-desktop.png',Buffer.from(focusShot.data,'base64'));
  await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape'});
  await send('Input.dispatchKeyEvent',{type:'keyUp',key:'Escape',code:'Escape'});
  await waitFor("document.querySelector('.detail-page').dataset.readingFocus==='false'");
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
  await evaluate('window.scrollTo({top:0,behavior:"instant"})');
  assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth'),'reader controls must fit at 390px');
  const mobile=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
  fs.writeFileSync('output/api-integration/reader-390.png',Buffer.from(mobile.data,'base64'));
  await send('Emulation.setDeviceMetricsOverride',{width:1440,height:900,deviceScaleFactor:1,mobile:false});
  console.log('PASS focus reader: actual scroll progress, isolated local position restore, source selection appended without replacing notes, Escape exit, desktop/390 screenshots');
}

async function runApi() {
  const response=await browserFetch(origin+"/api/stats");
  assert.equal(response.status,200,"Vite proxy must reach FastAPI");
  const stats=await response.json();
  assert.equal(stats.status,"real");
  assert.equal(stats.papers,859);
  await waitFor("document.querySelector('.header-data-status')?.textContent.includes('859')");
  await send("Emulation.setDeviceMetricsOverride",{width:1440,height:900,deviceScaleFactor:1,mobile:false});
  await fill("#main-search-input","mag");
  await evaluate("document.querySelector('#main-search-input').focus()");
  await waitFor("document.querySelector('.suggestion-popover button')!==null");
  assert.ok(await evaluate("document.querySelector('.suggestion-popover').textContent.includes('作者建议')"));
  await send("Input.dispatchKeyEvent",{type:"keyDown",key:"ArrowDown",code:"ArrowDown"});
  await send("Input.dispatchKeyEvent",{type:"keyUp",key:"ArrowDown",code:"ArrowDown"});
  const suggestion=await waitFor("document.querySelector('[role=option][aria-selected=true]')?.textContent");
  await send("Input.dispatchKeyEvent",{type:"keyDown",key:"Escape",code:"Escape"});
  await send("Input.dispatchKeyEvent",{type:"keyUp",key:"Escape",code:"Escape"});
  await waitFor("document.querySelector('#main-search-input').getAttribute('aria-expanded')==='false'");
  await send("Input.dispatchKeyEvent",{type:"keyDown",key:"ArrowDown",code:"ArrowDown"});
  await send("Input.dispatchKeyEvent",{type:"keyUp",key:"ArrowDown",code:"ArrowDown"});
  assert.equal(await waitFor("document.querySelector('[role=option][aria-selected=true]')?.textContent"),suggestion);
  await send("Input.dispatchKeyEvent",{type:"keyDown",key:"Enter",code:"Enter",windowsVirtualKeyCode:13});
  await send("Input.dispatchKeyEvent",{type:"keyUp",key:"Enter",code:"Enter",windowsVirtualKeyCode:13});
  await waitFor("location.pathname==='/search' && document.querySelectorAll('.paper-card').length>0");
  assert.equal(await evaluate("new URLSearchParams(location.search).get('q')"),suggestion);
  await evaluate("(()=>{const el=document.querySelector(\'[aria-label=选择检索字段]\');el.value=\'all\';el.dispatchEvent(new Event(\'change\',{bubbles:true}));})()");
  await fill("#main-search-input","magnetic");
  await click(".search-submit");
  await waitFor("document.querySelectorAll('.paper-card').length===6");
  assert.ok(await evaluate("document.querySelector('.results-topbar').textContent.includes('61')"));
  assert.ok(await evaluate("document.querySelector('.paper-abstract').textContent.length>20"));
  assert.ok(await evaluate("document.querySelector('.paper-abstract mark')!==null"));
  const firstId=await evaluate("document.querySelector('.paper-card').dataset.paperId");
  assert.ok(firstId.startsWith("source-sha256:"));
  await click(".pagination button:last-child");
  await waitFor("new URLSearchParams(location.search).get('page')==='2' && document.querySelector('.paper-card')?.dataset.paperId!=="+q(firstId));
  await evaluate("(()=>{const el=document.querySelector('[aria-label=排序方式]');el.value='newest';el.dispatchEvent(new Event('change',{bubbles:true}));})()");
  await waitFor("new URLSearchParams(location.search).get('sort')==='newest' && document.querySelectorAll('.paper-card').length===6");
  await waitFor("(()=>{const years=Array.from(document.querySelectorAll('.paper-record-year')).map(el=>Number(el.textContent)).filter(Number.isFinite);return years.length>1&&years.every((year,i)=>!i||years[i-1]>=year)})()");
  const years=await evaluate("Array.from(document.querySelectorAll('.paper-record-year')).map(el=>Number(el.textContent)).filter(Number.isFinite)");
  assert.ok(years.every((year,i)=>!i||years[i-1]>=year));
  await fill(".year-inputs label:first-child input","2000");
  await click(".filter-apply-button");
  await waitFor("new URLSearchParams(location.search).get('from')==='2000' && document.querySelectorAll('.paper-card').length>0");
  await waitFor("document.querySelectorAll('.paper-record').length>0 && Array.from(document.querySelectorAll('.paper-record-year')).every(el=>Number(el.textContent)>=2000)");
  assert.ok(await evaluate("Array.from(document.querySelectorAll('.paper-record-year')).every(el=>Number(el.textContent)>=2000)"));
  const shot=await send("Page.captureScreenshot",{format:"png",captureBeyondViewport:false});
  fs.mkdirSync("output/api-integration",{recursive:true});
  fs.writeFileSync("output/api-integration/search-desktop.png",Buffer.from(shot.data,"base64"));
  await click(".paper-card .bookmark-button");
  await click(".paper-card .paper-title-link");
  await waitFor("document.querySelector('.detail-header')!==null");
  assert.ok(await evaluate("document.querySelector('.reading-paragraph').textContent.length>20"));
  assert.ok(await evaluate("document.querySelector('.detail-tags').textContent.includes('解析状态')"));
  await exerciseReader();
  await navigate("/library");
  await waitFor("document.querySelector('.library-paper-item')!==null");
  assert.ok(await evaluate("document.querySelector('.library-reading-position')?.textContent.includes('本机')"),'library should show the real isolated reading record');
  assert.ok(await evaluate("document.querySelector('.library-note-preview')?.textContent.includes('阅读笔记')"),'saved excerpts should be visible without opening a textarea');
  await click(".note-edit-button");
  await fill(".reading-note textarea","真实论文联调笔记");
  await navigate("/");
  await waitFor("document.querySelector('.recent-current-page')?.dataset.paperId.startsWith('source-sha256:')");
  await send('Emulation.setDeviceMetricsOverride',{width:1366,height:768,deviceScaleFactor:1,mobile:false});
  assert.ok(await evaluate("(()=>{const r=document.querySelector('.search-submit').getBoundingClientRect();return r.top>=0&&r.bottom<innerHeight&&document.querySelectorAll('.prism-facets path').length>=6})()"),'search must remain visible beside the prism at 1366x768');
  await click('.motion-toggle');
  assert.equal(await evaluate("document.querySelector('.apple-home').dataset.motion"),'paused');
  await click('.motion-toggle');
  await send('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'reduce'}]});
  await waitFor("document.querySelector('.motion-toggle').disabled");
  assert.equal(await evaluate("getComputedStyle(document.querySelector('.research-prism')).transform"),'none');
  await send('Emulation.setEmulatedMedia',{features:[]});
  await waitFor("['.hero-label','.hero h1','.hero-subtitle','.home-search-area'].every(s=>Number(getComputedStyle(document.querySelector(s)).opacity)>.99)");
  await evaluate("Promise.all(document.getAnimations().filter(a=>Number.isFinite(a.effect.getComputedTiming().endTime)).map(a=>a.finished.catch(()=>{})))");
  const home=await send("Page.captureScreenshot",{format:"png",captureBeyondViewport:false});
  fs.writeFileSync("output/api-integration/home-desktop.png",Buffer.from(home.data,"base64"));
  await send('Emulation.setDeviceMetricsOverride',{width:1440,height:900,deviceScaleFactor:1,mobile:false});
  await navigate("/explore");
  await waitFor("document.querySelectorAll('.paper-card').length===9");
  assert.ok(await evaluate("!document.querySelector('.topic-selector').textContent.includes('计算机科学')"));
  await click("[aria-label='探索显示方式'] button:last-child");
  await waitFor("document.querySelectorAll('.constellation-node').length===20");
  assert.ok(await evaluate("document.querySelector('.constellation-detail a').getAttribute('href').startsWith('/paper/source-sha256')"));
  const discovery=await(await browserFetch(origin+'/api/discover?limit=20')).json();
  const mapNodes=await evaluate("Array.from(document.querySelectorAll('.constellation-node')).map(node=>node.dataset.paperId)");
  assert.deepEqual(new Set(mapNodes),new Set(discovery.recommendations.map(paper=>paper.paper_id)),'map must use the actual current API candidates');
  const mapEdges=await evaluate("Array.from(document.querySelectorAll('.constellation-edges line')).map(line=>({source:line.dataset.source,target:line.dataset.target}))");
  const canonical=value=>value.normalize('NFC').trim().replace(/\s+/gu,' ').toLocaleLowerCase();
  for(const edge of mapEdges){
    const source=discovery.recommendations.find(p=>p.paper_id===edge.source),target=discovery.recommendations.find(p=>p.paper_id===edge.target);
    assert.ok(source&&target);
    assert.ok(['authors','keywords','topics','affiliation'].some(field=>(source[field]??[]).some(value=>(target[field]??[]).some(other=>canonical(value)===canonical(other)))),'every rendered edge must have actual shared metadata');
  }
  if(mapEdges.length){
    await click(".constellation-node[data-relations]:not([data-relations='0'])");
    await waitFor("document.querySelector('.constellation-reasons button')!==null");
    const selected=await evaluate("document.querySelector('.constellation-node[aria-pressed=true]').dataset.paperId");
    await click('.constellation-reasons button');
    assert.notEqual(await evaluate("document.querySelector('.constellation-node[aria-pressed=true]').dataset.paperId"),selected);
  }
  await evaluate("document.querySelector('.constellation-node:last-child').focus()");
  // Native button activation needs the Enter character, not only a raw key event.
  await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13,text:'\r',unmodifiedText:'\r'});
  await send('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
  await waitFor("document.querySelector('.constellation-node:last-child').getAttribute('aria-pressed')==='true'");
  await fill('[aria-label="筛选探索结果"]','no-matching-local-paper-20261028');
  await waitFor("document.querySelector('.empty-state h3')?.textContent.includes('没有论文')");
  assert.equal(await evaluate("document.querySelectorAll('.constellation-node').length"),0);
  await click('.empty-state button');
  await waitFor("document.querySelectorAll('.constellation-node').length===20");
  await evaluate("document.querySelector('.paper-constellation').scrollIntoView({behavior:'instant',block:'center'})");
  const mapRect=await evaluate("(()=>{const r=document.querySelector('.constellation-space').getBoundingClientRect();return {x:r.x+8,y:r.y+8}})()");
  await send('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,...mapRect});
  await send('Input.dispatchMouseEvent',{type:'mouseMoved',button:'left',x:mapRect.x+72,y:mapRect.y+32});
  await send('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,x:mapRect.x+72,y:mapRect.y+32});
  await waitFor("getComputedStyle(document.querySelector('.constellation-plane')).transform!=='none'");
  await send('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'reduce'}]});
  assert.equal(await evaluate("getComputedStyle(document.querySelector('.constellation-plane')).transform"),'none');
  await send('Emulation.setEmulatedMedia',{features:[]});
  await click('.constellation-heading button');
  const graphShot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
  fs.writeFileSync('output/api-integration/research-map-desktop.png',Buffer.from(graphShot.data,'base64'));
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
  assert.ok(await evaluate("document.documentElement.scrollWidth<=innerWidth"));
  const graphMobile=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
  fs.writeFileSync('output/api-integration/research-map-390.png',Buffer.from(graphMobile.data,'base64'));
  await send('Emulation.setDeviceMetricsOverride',{width:1440,height:900,deviceScaleFactor:1,mobile:false});
  await click("[aria-label='探索显示方式'] button:first-child");
  await waitFor("document.querySelectorAll('.paper-card').length===9");
  const priorIds=await evaluate("Array.from(document.querySelectorAll('.paper-card')).map(el=>el.dataset.paperId)");
  await click('.page-heading-extra button');
  await waitFor("document.querySelectorAll('.paper-card').length===9 && !"+JSON.stringify(priorIds)+".includes(document.querySelector('.paper-card').dataset.paperId)");
  const nextIds=await evaluate("Array.from(document.querySelectorAll('.paper-card')).map(el=>el.dataset.paperId)");
  assert.ok(nextIds.every(id=>!priorIds.includes(id)),"Random discovery should fetch a new server batch");

  await evaluate("localStorage.setItem('scholarlens-v1:eval-judgments',JSON.stringify({'api::magnetic':{["+q(firstId)+"]:'2'}}))");
  await navigate('/evaluation');
  await waitFor("document.querySelector('.evaluation-search input')!==null");
  await fill('.evaluation-search input','magnetic');
  await click('.evaluation-search button');
  await waitFor("document.querySelectorAll('.evaluation-row').length===10");
  assert.equal(await evaluate("document.querySelector('.metric-ring').dataset.ready"),'false');
  assert.equal(await evaluate("document.querySelector('.evaluation-progress-track').value"),0,'corrupted stored grades must not appear complete');
  assert.equal(await evaluate("document.querySelectorAll('.evaluation-row[data-grade=\"2\"]').length"),0);
  for(let index=1;index<=5;index++)await click('.evaluation-row:nth-of-type('+index+') .evaluation-votes button:last-child');
  await waitFor("document.querySelector('.metric-ring').dataset.ready==='true'");
  assert.equal(await evaluate("document.querySelector('.metric-scale').dataset.ready"),'false','nDCG remains unavailable with five of ten judged');
  for(let index=6;index<=10;index++)await click('.evaluation-row:nth-of-type('+index+') .evaluation-votes button:nth-of-type(2)');
  await waitFor("document.querySelector('.metric-scale').dataset.ready==='true'");
  assert.ok(await evaluate("document.querySelector('.evaluation-summary').textContent.includes('1.000')"));
  assert.equal(await evaluate("document.querySelector('.evaluation-progress-track').value"),10);
  assert.ok(await evaluate("document.querySelector('.query-timings li')!==null"));
  await evaluate("document.querySelector('.evaluation-summary').scrollIntoView({behavior:'instant',block:'center'})");
  assert.ok(await evaluate("(()=>{const r=document.querySelector('.evaluation-summary').getBoundingClientRect();return r.top>=0&&r.bottom<=innerHeight})()"),'desktop metric summary must be visible in the screenshot');
  await waitFor("Array.from(document.querySelectorAll('.evaluation-summary .metric-card')).every(el=>Number(getComputedStyle(el).opacity)>.99)");
  const metricShot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
  fs.writeFileSync('output/api-integration/evaluation-metrics-desktop.png',Buffer.from(metricShot.data,'base64'));
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
  await evaluate("document.querySelector('.evaluation-summary').scrollIntoView({behavior:'instant',block:'start'})");
  assert.ok(await evaluate("document.documentElement.scrollWidth<=innerWidth"));
  const metricMobile=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
  fs.writeFileSync('output/api-integration/evaluation-metrics-390.png',Buffer.from(metricMobile.data,'base64'));
  await send('Emulation.setDeviceMetricsOverride',{width:1440,height:900,deviceScaleFactor:1,mobile:false});
  console.log('PASS research map: actual candidates and shared metadata, node and keyboard selection, filters, drag, reduced motion, list fallback; library local position and note preview; evaluation pending/partial/complete metrics and actual engine timings');

  await navigate("/search?q=&mode=keyword");
  await waitFor("document.querySelectorAll('.paper-card').length===6");
  assert.ok(await evaluate("document.querySelector('#main').textContent.includes('最多20篇')"));
  const capabilities=await (await browserFetch(origin+"/api/capabilities")).json();
  const modeChecks=[];
  for(const mode of ['semantic','hybrid']){
    const ready=capabilities.modules[mode+'_search'].status==='ready';
    if(process.env.SCHOLARLENS_REQUIRE_VECTORS==='1')assert.ok(ready,mode+' must be ready');
    await navigate('/search?q=brain%20magnetic%20resonance%20imaging&mode='+mode);
    if(ready){
      await waitFor("document.querySelectorAll('.paper-card').length===6",30000);
      const response=await browserFetch(origin+'/api/search?q=brain%20magnetic%20resonance%20imaging&mode='+mode+'&page_size=6');
      assert.equal(response.status,200);const data=await response.json();
      const firstPage=await evaluate("Array.from(document.querySelectorAll('.paper-card')).map(el=>el.dataset.paperId)");
      assert.deepEqual(firstPage,data.results.map(row=>row.paper_id),'UI must show the actual '+mode+' ranking');
      assert.ok(data.results.every(row=>row.score>0));
      assert.ok(await evaluate("!document.querySelector('[aria-label=检索方式] option[value="+mode+"]').disabled"));
      const shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
      fs.writeFileSync('output/api-integration/search-'+mode+'-desktop.png',Buffer.from(shot.data,'base64'));
      await click('.pagination button:last-child');
      await waitFor("new URLSearchParams(location.search).get('page')==='2' && document.querySelectorAll('.paper-card').length===6 && document.querySelector('.paper-card').dataset.paperId!=="+q(firstPage[0]),30000);
      const secondPage=await evaluate("Array.from(document.querySelectorAll('.paper-card')).map(el=>el.dataset.paperId)");
      assert.ok(secondPage.every(id=>!firstPage.includes(id)),'Vector pages must not repeat papers');
      modeChecks.push({mode,status:'passed',total:data.total,first_page:firstPage,second_page:secondPage});
    }else{
      await waitFor("document.querySelector('#main').textContent.includes('向量索引或本地模型尚未就绪')");
      assert.equal(await evaluate("document.querySelectorAll('.paper-card').length"),0);
      modeChecks.push({mode,status:'unavailable-shown'});
    }
  }
  fs.writeFileSync('output/api-integration/search-modes-browser.json',JSON.stringify(modeChecks,null,2));

  await navigate("/paper/demo-001");
  await waitFor("document.querySelector('.detail-header')!==null");
  assert.ok(await evaluate("document.querySelector('.detail-tags').textContent.includes('演示')"));
  await navigate("/paper/source-sha256:not-in-delivery");
  await waitFor("document.querySelector('#main').textContent.includes('没有找到这篇论文')");
  await send("Emulation.setDeviceMetricsOverride",{width:390,height:844,deviceScaleFactor:1,mobile:true});
  await navigate("/");
  await waitFor("document.querySelector('.header-data-status')?.textContent.includes('859')");
  assert.ok(await evaluate("document.documentElement.scrollWidth<=innerWidth"));
  const mobile=await send("Page.captureScreenshot",{format:"png",captureBeyondViewport:false});
  fs.writeFileSync("output/api-integration/home-390.png",Buffer.from(mobile.data,"base64"));
  console.log("PASS real API browser: 859 papers, keyboard suggestions and Escape reopening, 61 magnetic hits, BM25 snippets, pagination, year sorting/filtering, detail, local favorites/notes, recent reading, server random discovery, empty query, semantic/hybrid capabilities and actual ranking/pagination when ready, old demo bookmark, missing detail, desktop/390 geometry");
}

async function browserFetch(url){
  // Keep HTTPS checks on the same Chrome network path as the UI under test.
  const result=await evaluate("fetch("+q(url)+").then(async r=>({status:r.status,body:await r.text()}))");
  return {status:result.status,json:async()=>JSON.parse(result.body)};
}
async function run(){
  processHandle=spawn(chrome,[
    "--headless=new","--disable-gpu","--no-first-run","--no-default-browser-check",
    "--disable-background-networking","--remote-debugging-port=0","--window-size=1440,900",
    "--user-data-dir="+profile,"about:blank"
  ],{stdio:"ignore",windowsHide:true});
  const port=await waitPort();
  const newTab=await fetch("http://127.0.0.1:"+port+"/json/new?"+encodeURIComponent(origin+"/"),{method:"PUT"});
  if(!newTab.ok)throw new Error("Chrome could not create a test tab: HTTP "+newTab.status);
  const tab=await newTab.json();
  connection=await connect(tab.webSocketDebuggerUrl);
  await send("Page.enable");
  await send("Runtime.enable");
  await waitFor("document.querySelector('#main-search-input') !== null");
  await waitFor("document.querySelector('.header-data-status') && !document.querySelector('.header-data-status').textContent.includes('正在连接')");
  if(await evaluate("!document.querySelector('.header-data-status').textContent.includes('演示空间')")) return runApi();

  await fill("#main-search-input","computer");
  await click(".search-submit");
  await waitFor("location.pathname==='/search' && document.querySelectorAll('.paper-card').length > 0");
  const count=await evaluate("document.querySelectorAll('.paper-card').length");
  assert.ok(count>0,"search should return results");
  console.log("PASS search:",count,"result card(s)");

  await navigate("/search?q=&field=all&mode=keyword");
  await waitFor("document.querySelectorAll('.paper-card').length===6");
  await click(".pagination button:last-child");
  await waitFor("new URLSearchParams(location.search).get('page')==='2'");
  console.log("PASS real result pagination");

  await navigate("/search?q=computer&field=all&mode=keyword");
  await waitFor("document.querySelectorAll('.paper-card').length>0");
  await fill(".year-inputs label:first-child input","2024");
  await click(".filter-apply-button");
  await waitFor("new URLSearchParams(location.search).get('from')==='2024'");
  await click(".filter-heading button");
  await waitFor("!new URLSearchParams(location.search).has('from')");
  await waitFor("document.querySelectorAll('.paper-card').length>0");
  console.log("PASS year filter apply + reset");

  await click(".paper-card .bookmark-button");
  await click(".paper-card .paper-title-link");
  await waitFor("location.pathname.startsWith('/paper/') && document.querySelector('.detail-header') !== null");
  console.log("PASS detail navigation");

  await navigate("/library");
  await waitFor("location.pathname==='/library' && document.querySelector('.library-paper-item') !== null");
  await click(".note-edit-button");
  await waitFor("document.querySelector('.reading-note textarea') !== null");
  await fill(".reading-note textarea","要对照模型结构和检索结果写阅读笔记");
  await waitFor("document.querySelector('.reading-note textarea').value.includes('阅读笔记')");
  console.log("PASS bookmark + library notes");

  const downloadDir=path.join(profile,"downloads");
  fs.mkdirSync(downloadDir,{recursive:true});
  await send("Page.setDownloadBehavior",{behavior:"allow",downloadPath:downloadDir});
  await click(".library-actions button:last-child");
  const backupPath=path.join(downloadDir,"scholarlens-library-backup.json");
  const begun=Date.now();
  while(!fs.existsSync(backupPath)&&Date.now()-begun<8000)await delay(160);
  assert.ok(fs.existsSync(backupPath),"JSON backup should download");
  const backup=JSON.parse(fs.readFileSync(backupPath,"utf8"));
  assert.ok(Array.isArray(backup.favorites)&&backup.favorites.length>0);
  assert.ok(backup.favorites.some((entry)=>String(entry.note).includes("阅读笔记")));
  await evaluate("window.confirm=()=>true");
  const backupString=JSON.stringify(backup);
  await evaluate("(()=>{const file=new File(["+q(backupString)+"],'restored.json',{type:'application/json'});const dt=new DataTransfer();dt.items.add(file);const input=document.querySelector('.library-actions input[type=file]');input.files=dt.files;input.dispatchEvent(new Event('change',{bubbles:true}));return true})()");
  await waitFor("document.querySelector('.toast') && document.querySelector('.toast').textContent.includes('恢复')");
  console.log("PASS library JSON export + restore");

  await navigate("/evaluation");
  await waitFor("document.querySelectorAll('.evaluation-row').length>0");
  const labeled=await evaluate("(()=>{const buttons=document.querySelectorAll('.evaluation-votes button:nth-of-type(2)');buttons.forEach((button)=>button.click());return buttons.length})()");
  assert.ok(labeled>0);
  await waitFor("document.querySelector('.metric-value') && document.querySelector('.metric-value').textContent.includes('%')");
  console.log("PASS manual relevance labels + live metrics:",labeled);

  await navigate("/upload?storage=local");
  await waitFor("document.querySelector('input[type=file]')!==null");
  const simulated=await evaluate("(()=>{const file=new File(['%PDF-1.4\\n1 0 obj\\n<< /Type /Catalog >>\\nendobj\\n%%EOF\\n'],'test-local-preview.pdf',{type:'application/pdf'});const dt=new DataTransfer();dt.items.add(file);const input=document.querySelector('input[type=file]');input.files=dt.files;input.dispatchEvent(new Event('change',{bubbles:true}));return true})()");
  assert.equal(simulated,true);
  await waitFor("document.querySelector('.selected-file .button-primary') !== null");
  await click(".selected-file .button-primary");
  await waitFor("document.querySelector('.file-queue-row')!==null",15000);
  console.log("PASS real local PDF saved to IndexedDB");

  await evaluate("(()=>{const f=new File(['%PDF-1.4\\n1 0 obj\\n<< /Type /Catalog >>\\nendobj\\n%%EOF\\n'],'test-local-preview.pdf',{type:'application/pdf'});const dt=new DataTransfer();dt.items.add(f);const input=document.querySelector('input[type=file]');input.files=dt.files;input.dispatchEvent(new Event('change',{bubbles:true}));return true})()");
  await waitFor("document.querySelector('.selected-file .button-primary')!==null");
  await click(".selected-file .button-primary");
  await waitFor("document.querySelector('.inline-error') && document.querySelector('.inline-error').textContent.includes('相同内容')");
  console.log("PASS local PDF duplicate detection");

  await navigate("/admin?storage=local");
  await waitFor("document.querySelector('.review-entry')!==null");
  await fill(".review-note textarea","已核验格式，需人工确认论文来源");
  await click(".review-actions button:nth-child(2)");
  await waitFor("document.querySelector('.review-entry .review-note textarea').value.includes('已核验')");
  await click(".review-actions .button-primary");
  await waitFor("document.querySelector('.review-entry .status-approved')!==null");
  await evaluate("document.querySelector('.review-actions .button-secondary').focus()");
  await click(".review-actions .button-secondary");
  await waitFor("document.querySelector('.pdf-viewer-frame')!==null");
  assert.equal(await evaluate("document.querySelector('dialog.pdf-viewer-backdrop').matches(':modal')"),true);
  assert.equal(await evaluate("document.querySelector('.pdf-viewer').contains(document.activeElement)"),true);
  assert.equal(await evaluate("document.body.style.overflow"),"hidden");
  await evaluate("document.querySelector('.pdf-viewer-actions a').focus()");
  await send("Input.dispatchKeyEvent",{type:"keyDown",key:"Tab",code:"Tab",windowsVirtualKeyCode:9,modifiers:8});
  await send("Input.dispatchKeyEvent",{type:"keyUp",key:"Tab",code:"Tab",windowsVirtualKeyCode:9,modifiers:8});
  assert.equal(await evaluate("document.querySelector('dialog.pdf-viewer-backdrop').contains(document.activeElement)"),true,"PDF focus must not escape to the background");
  await evaluate("document.querySelector('.pdf-viewer-header .icon-button').focus()");
  await send("Input.dispatchKeyEvent",{type:"keyDown",key:"Escape",code:"Escape",windowsVirtualKeyCode:27});
  await send("Input.dispatchKeyEvent",{type:"keyUp",key:"Escape",code:"Escape",windowsVirtualKeyCode:27});
  await waitFor("document.querySelector('.pdf-viewer')===null");
  assert.equal(await evaluate("document.activeElement===document.querySelector('.review-actions .button-secondary')"),true);
  assert.notEqual(await evaluate("document.body.style.overflow"),"hidden");
  await click(".review-actions .button-secondary");
  await waitFor("document.querySelector('.pdf-viewer-frame')!==null");
  await click(".pdf-viewer-header .icon-button");
  console.log("PASS local review state + PDF modal focus, Escape, return focus and scroll restoration");

  await navigate("/assistant");
  await waitFor("document.querySelector('.ai-compose form button:not([type=button])')!==null");
  assert.equal(await evaluate("document.querySelector('.ai-compose form button:not([type=button])').disabled"),true);
  assert.equal(await evaluate("document.querySelectorAll('.ai-chat-message').length"),0);
  console.log("PASS AI intentionally disabled until user configures an endpoint");
  assert.equal(await evaluate("document.querySelectorAll('.sidebar-tools .tool-item').length"),4);
  await click(".tool-item[href='/evaluation']");
  await waitFor("location.pathname==='/evaluation'");
  console.log("PASS sidebar exposes all secondary workflows");
  await navigate("/a-page-that-does-not-exist");
  await waitFor("document.querySelector('.missing-page') !== null");
  assert.ok(await evaluate("document.querySelector('.missing-page h1').textContent.includes('找')"));
  await click(".missing-page-actions a[href='/search']");
  await waitFor("location.pathname === '/search'");
  console.log("PASS branded 404 and recovery navigation");

  // This is an isolated temporary profile; never modifies the user's own reading history.
  await evaluate("localStorage.removeItem('scholarlens-v1:history')");
  await navigate("/");
  await waitFor("document.querySelector('.recent-deck[data-count=\"0\"]')!==null");
  assert.equal(await evaluate("document.querySelectorAll('.recent-current-page,.recent-page-dots button').length"),0);
  for(let i=1;i<=6;i++){
    const id="demo-"+String(i).padStart(3,"0");
    await navigate("/paper/"+id);
    await waitFor("document.querySelector('.detail-header h1')!==null");
    await waitFor("JSON.parse(localStorage.getItem('scholarlens-v1:history')||'[]')[0]?.paper.paper_id==="+q(id));
    await navigate("/");
    await waitFor("document.querySelector('.recent-current-page')?.dataset.paperId==="+q(id));
    assert.equal(await evaluate("Number(document.querySelector('.recent-deck').dataset.count)"),Math.min(i,5));
    assert.equal(await evaluate("document.querySelectorAll('.recent-page-dots button').length"),Math.min(i,5));
    if(i===1)assert.equal(await evaluate("document.querySelector('.recent-next').disabled"),true);
  }
  await click(".recent-autoplay");
  assert.equal(await evaluate("document.querySelector('.recent-autoplay').getAttribute('aria-pressed')"),"true");
  assert.equal(await evaluate("(()=>{const el=document.querySelector('.recent-next');const r=el.getBoundingClientRect();return el.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2))})()"),true,"3D paper must not obscure its page controls");
  await pointerClick(".recent-next");
  await waitFor("document.querySelector('.recent-current-page')?.dataset.paperId==='demo-005'");
  await waitFor("document.querySelector('.recent-deck').dataset.state==='ready'");
  await click(".recent-page-dots button:last-child");
  await waitFor("document.querySelector('.recent-current-page')?.dataset.paperId==='demo-002'");
  await waitFor("document.querySelector('.recent-deck').dataset.state==='ready'");
  await click(".recent-next");
  await waitFor("document.querySelector('.recent-current-page')?.dataset.paperId==='demo-006'");
  await navigate("/paper/demo-003");
  await waitFor("JSON.parse(localStorage.getItem('scholarlens-v1:history')||'[]')[0]?.paper.paper_id==='demo-003'");
  await navigate("/");
  await waitFor("document.querySelector('.recent-current-page')?.dataset.paperId==='demo-003'");
  assert.equal(await evaluate("Number(document.querySelector('.recent-deck').dataset.count)"),5);
  assert.equal(await evaluate("JSON.parse(localStorage.getItem('scholarlens-v1:history')).filter(e=>e.paper.paper_id==='demo-003').length"),1);
  await click(".site-motion-toggle");
  await waitFor("document.querySelector('.workspace-shell').dataset.motion==='paused'");
  await navigate("/search?q=computer");
  await waitFor("document.querySelector('.workspace-shell')?.dataset.motion==='paused'");
  await click(".site-motion-toggle");
  console.log("PASS recent reading: empty, 1–5 pages, latest-5 cap, duplicate revisit, persisted order, manual flip, wraparound, global motion preference");

  await send("Emulation.setDeviceMetricsOverride",{width:390,height:844,deviceScaleFactor:1,mobile:true});
  await navigate("/");
  await waitFor("document.querySelector('.search-form')!==null");
  const mobile = await evaluate("(()=>{const rect=(s)=>{const e=document.querySelector(s);if(!e)return null;const r=e.getBoundingClientRect();return {x:Math.round(r.x),y:Math.round(r.y),width:Math.round(r.width),height:Math.round(r.height)}};return {viewport:innerWidth,scrollWidth:document.documentElement.scrollWidth,menu:rect('.mobile-menu-button'),form:rect('.search-form'),field:rect('.field-select-wrap'),input:rect('.search-input-wrap'),submit:rect('.search-submit')}})()");
  assert.ok(mobile.scrollWidth <= mobile.viewport,"Mobile page must not overflow horizontally");
  assert.equal(mobile.field.y,mobile.input.y,"Mobile query and scope must align");
  assert.ok(mobile.submit.y >= mobile.field.y + mobile.field.height,"Mobile search action must not overlap query");
  assert.ok(mobile.menu.x>=0 && mobile.menu.x+mobile.menu.width<=390,"Mobile menu must remain visible");
  const shot=await send("Page.captureScreenshot",{format:"png",captureBeyondViewport:false,fromSurface:true});
  fs.writeFileSync("qa-skill-mobile-cdp.png",Buffer.from(shot.data,"base64"));
  await click(".mobile-menu-button");
  await waitFor("document.querySelector('.mobile-nav a') !== null");
  console.log("PASS mobile search geometry and navigation");
  console.log("PASS all browser smoke tests");
}
try{await run()}
finally{
  try{connection?.close()}catch{}
  for(const item of pending.values())clearTimeout(item.timer);
  try{processHandle?.kill()}catch{}
  try{fs.rmSync(profile,{recursive:true,force:true,maxRetries:2,retryDelay:150})}catch{}
}
