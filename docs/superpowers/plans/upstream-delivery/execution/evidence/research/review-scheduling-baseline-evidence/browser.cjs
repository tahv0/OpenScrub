const {chromium}=require('/tmp/openscrub-save-as-20261116/node_modules/playwright');
const fs=require('node:fs');
const assert=require('node:assert/strict');
const ROOT='/tmp/openscrub-review-scheduling-20261117';
const BASE='http://127.0.0.1:'+ (process.env.QA_PORT||18509);
const SOURCE=process.env.QA_SOURCE||'baseline';
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const state=async()=>await(await fetch(BASE+'/__qa__/state')).json();
const control=async data=>await fetch(BASE+'/__qa__/control',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
async function waitUntil(fn,ms=5000){let end=Date.now()+ms;while(Date.now()<end){if(await fn())return;await sleep(50);}throw Error('bounded condition timeout');}
(async()=>{
const browser=await chromium.launch({headless:true});
const results={source:SOURCE,base:BASE,browser:browser.version(),viewport:{width:1365,height:950},
  fallback:'Browser plugin not available; reused existing Playwright and Chromium, no installs',cases:[]};
try{
 for(const [job,count] of (SOURCE==='baseline'?[['small',12],['oneK',1000],['tenK',10000]]:[['small',12]])){
  await control({release_all:true});
  await sleep(100);
  const offset=(await state()).events.length;
  await control({hold:[job]});
  const context=await browser.newContext({viewport:results.viewport});
  const page=await context.newPage();
  const cdp=await context.newCDPSession(page);
  await cdp.send('Performance.enable');
  const pending=new Set(),requests=[],finished=[],failed=[],errors=[],warnings=[],mutations=[];
  const cdpRequests=new Map(),cdpDone=new Set(),cdpFailed=[];
  await cdp.send('Network.enable');
  cdp.on('Network.requestWillBeSent',e=>{if(e.type==='Image'&&e.request.url.includes('/thumb/'))cdpRequests.set(e.requestId,e.request.url);});
  cdp.on('Network.loadingFinished',e=>{if(cdpRequests.has(e.requestId))cdpDone.add(e.requestId);});
  cdp.on('Network.loadingFailed',e=>{if(cdpRequests.has(e.requestId))cdpFailed.push({id:e.requestId,error:e.errorText,canceled:e.canceled});});
  page.on('request',r=>{if(r.resourceType()==='image'&&r.url().includes('/thumb/')){pending.add(r);requests.push({url:r.url(),at:Date.now()});}});
  page.on('requestfinished',r=>{if(pending.delete(r))finished.push(r.url());});
  page.on('requestfailed',r=>{if(pending.delete(r))failed.push({url:r.url(),error:r.failure()?.errorText});});
  page.on('pageerror',e=>errors.push({message:e.message,stack:e.stack,at:Date.now()}));
  page.on('console',m=>{if(['warning','error'].includes(m.type()))warnings.push(m.text());});
  page.on('request',r=>{if(r.method()!=='GET')mutations.push({url:r.url(),method:r.method()});});
  await page.addInitScript(()=>{
   window.qa={longTasks:[],loads:[]};
   new PerformanceObserver(list=>{for(const x of list.getEntries())qa.longTasks.push({start:x.startTime,duration:x.duration});}).observe({type:'longtask',buffered:true});
   document.addEventListener('load',e=>{if(e.target instanceof HTMLImageElement&&e.target.src.includes('/thumb/')){const b=e.target.getBoundingClientRect();qa.loads.push({url:e.target.src,at:performance.now(),visible:b.bottom>0&&b.top<innerHeight});}},true);
  });
  const snap=async label=>{
   const dom=await page.evaluate(()=>{
    const cards=[...document.querySelectorAll('#detwrap .det')];
    const visible=cards.filter(c=>{const b=c.getBoundingClientRect();return b.bottom>0&&b.top<innerHeight;});
    const images=[...document.querySelectorAll('#detwrap img')];
    return {title:document.title,cur:CUR,cards:cards.length,images:images.length,
     lazyImages:images.filter(i=>i.loading==='lazy').length,
     visible:visible.map(c=>({id:c.id,url:c.querySelector('img').src,complete:c.querySelector('img').complete&&c.querySelector('img').naturalWidth>0})),
     loaded:images.filter(i=>i.complete&&i.naturalWidth>0).length,
     scrollY,scrollHeight:document.documentElement.scrollHeight,
     qa,resourceCompleted:performance.getEntriesByType('resource').filter(x=>x.name.includes('/thumb/')&&x.responseEnd>0).length,
     controls:[...document.querySelectorAll('#review button,#review select,#review input')].slice(0,12).map(x=>({tag:x.tagName,text:x.textContent.trim(),type:x.type})),
     mixed:{members:TRKMEM[2],enabled:[EN[1],EN[2]],button:document.getElementById('bb2')?.textContent}};
   });
   const server=(await state()).events.slice(offset);
   const perf=Object.fromEntries((await cdp.send('Performance.getMetrics')).metrics.filter(m=>['JSHeapUsedSize','JSHeapTotalSize','TaskDuration','ScriptDuration','LayoutDuration','Nodes','Documents','LayoutCount'].includes(m.name)).map(m=>[m.name,m.value]));
   return {label,at:Date.now(),dom,network:{requested:requests.length,finished:finished.length,failed:failed.length,outstanding:pending.size,
    cdpRequested:cdpRequests.size,cdpFinished:cdpDone.size,cdpFailed:cdpFailed.length,cdpOutstanding:cdpRequests.size-cdpDone.size-cdpFailed.length,
    visibleRequested:dom.visible.filter(c=>requests.some(r=>r.url===c.url)).map(c=>c.id),
    firstRequests:requests.slice(0,8),lastRequests:requests.slice(-8),failureExamples:failed.slice(0,8)},server,perf};
  };
  await page.goto(BASE,{waitUntil:'domcontentloaded'});
  assert.equal(await page.title(),'OpenScrub');
  await page.evaluate(id=>openJob(id),job);
  await page.waitForFunction(n=>document.querySelectorAll('#detwrap .det').length===n,count,{timeout:10000});
  await waitUntil(async()=>(await state()).events.slice(offset).filter(e=>e.job===job).length>=6);
  const defaultViewport=await page.evaluate(()=>({scrollY,cardsVisible:[...document.querySelectorAll('#detwrap .det')].filter(c=>{const b=c.getBoundingClientRect();return b.bottom>0&&b.top<innerHeight;}).length}));
  await page.locator('#detwrap .det').first().scrollIntoViewIfNeeded();
  await sleep(250);
  const initial=await snap('initial-held');
  assert.equal(initial.dom.images,count);
  if(job==='small')await page.screenshot({path:ROOT+'/'+SOURCE+'-small-initial.png'});
  await page.locator('#detwrap .det').last().scrollIntoViewIfNeeded();
  await sleep(250);
  const jumped=await snap('large-jump-held');
  if(job==='tenK')await page.screenshot({path:ROOT+'/'+SOURCE+'-tenK-jump.png'});
  const tokens=jumped.server.filter(e=>e.job===job&&!e.returned).map(e=>e.token);
  await control({release:tokens});
  await waitUntil(async()=>(await state()).events.slice(offset).filter(e=>e.job===job).length>tokens.length);
  await sleep(250);
  const afterRelease=await snap('jump-after-first-flight-released');
  // Real ordinary choice button; the representative begins with mixed member states.
  await page.locator('#bb2').click({timeout:5000});
  const choice=await page.evaluate(()=>({members:TRKMEM[2],enabled:[EN[1],EN[2]],button:document.getElementById('bb2').textContent,
    pendingDraft:typeof EDITS==='undefined'?null:{...EDITS.enabled}}));
  assert.deepEqual(choice.enabled,[false,false]);
  const beforeSwitch=await snap('choice-before-switch');
  await page.evaluate(()=>openJob('beta'));
  await sleep(250);
  const switched=await snap('beta-while-old-held');
  await control({release_all:true});
  await page.waitForFunction(()=>CUR==='beta'&&document.querySelectorAll('#detwrap .det').length===3,null,{timeout:5000});
  await sleep(350);
  const released=await snap('beta-after-old-release');
  assert.equal(released.dom.cur,'beta');
  assert.ok(released.dom.visible.every(c=>c.url.includes('/beta/')));
  await page.screenshot({path:ROOT+'/'+SOURCE+'-'+job+'-beta.png'});
  let reopenedChoice=null;
  if(job==='small'){
   await page.evaluate(id=>openJob(id),job);
   await page.waitForFunction(n=>document.querySelectorAll('#detwrap .det').length===n,count,{timeout:10000});
   reopenedChoice=await page.evaluate(()=>({enabled:[EN[1],EN[2]],button:document.getElementById('bb2').textContent}));
  }
  const entry={job,count,defaultViewport,initial,jumped,afterRelease,choice,beforeSwitch,switched,released,reopenedChoice,mutations,errors,warnings};
  results.cases.push(entry);
  fs.writeFileSync(ROOT+'/browser-'+SOURCE+'.json',JSON.stringify(results,null,2));
  await context.close();
  await control({release_all:true});
 }
 // Unheld cold production thumbnails prove the generated media exercises actual decoding.
 if(SOURCE==='baseline'){
  const offset=(await state()).events.length;
  const context=await browser.newContext({viewport:results.viewport});
  const page=await context.newPage();
  await page.goto(BASE,{waitUntil:'domcontentloaded'});
  await page.evaluate(()=>openJob('cold'));
  await page.waitForFunction(()=>document.querySelectorAll('#detwrap img').length===3&&[...document.querySelectorAll('#detwrap img')].every(x=>x.complete&&x.naturalWidth>0));
  results.cold={events:(await state()).events.slice(offset),images:await page.locator('#detwrap img').count()};
  await page.screenshot({path:ROOT+'/baseline-cold.png'});
  await context.close();
 }
 fs.writeFileSync(ROOT+'/browser-'+SOURCE+'.json',JSON.stringify(results,null,2));
 console.log(JSON.stringify({source:SOURCE,cases:results.cases.map(c=>({job:c.job,cards:c.initial.dom.cards,requested:c.initial.network.requested,server:c.initial.server.length,
  jumpVisible:c.jumped.dom.visible.map(v=>v.id),nextServer:c.afterRelease.server.slice(6).map(x=>x.i),failuresAtSwitch:c.switched.network.failed,reopened:c.reopenedChoice})),cold:results.cold}));
}finally{await control({release_all:true});await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
