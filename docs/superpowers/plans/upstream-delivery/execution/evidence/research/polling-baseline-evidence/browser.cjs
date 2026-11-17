const {chromium}=require('/tmp/openscrub-save-as-20261116/node_modules/playwright');
const fs=require('node:fs');
const assert=require('node:assert/strict');
const ROOT='/tmp/openscrub-polling-baseline-20261117';
const base='http://127.0.0.1:18513';
const pause=ms=>new Promise(r=>setTimeout(r,ms));
const wait=async fn=>{for(let i=0;i<100;i++){if(await fn())return;await pause(20);}throw Error('bounded condition wait expired');};
const meta=(id,extra={})=>({id,name:'synthetic job '+id,phase:'queued',progress:.2,error:null,stats:{},eta:null,has_output:false,...extra});
const tiny=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=','base64');
(async()=>{
const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
const results=[];
async function setup(name){
 const page=await browser.newPage({viewport:{width:1280,height:950}});
 const q={name,events:[],held:[],plans:[],errors:[],console:[],phase:'queued',logs:{A:['log-A'],B:['log-B']},passMeta:false,passLog:false};
 page.on('pageerror',e=>q.errors.push(e.message));
 page.on('console',m=>{if(['error','warning'].includes(m.type()))q.console.push(m.text());});
 page.on('dialog',d=>d.accept());
 await page.clock.install();
 await page.route('**/api/jobs/**',async route=>{
  const req=route.request(),u=new URL(req.url()),m=u.pathname.match(/^\/api\/jobs\/([^/]+)(?:\/(.*))?$/);
  if(!m)return route.continue();
  const [_,id,tail]=m,kind=tail||'meta';
  const e={id,kind,query:u.search,method:req.method(),n:q.events.length+1,done:false};q.events.push(e);
  if(((q.passMeta&&kind==='meta')||(q.passLog&&kind==='log'))&&req.method()==='GET'){e.pass=true;return route.continue();}
  if(tail&&['thumb/0','frame_at','preview.jpg'].includes(tail)){e.done=true;return route.fulfill({status:200,contentType:'image/png',body:tiny});}
  let data;
  if(req.method()==='DELETE')data={ok:true};
  else if(kind==='meta')data=meta(id,{phase:q.phase});
  else if(kind==='log'){let from=Number(u.searchParams.get('from')||0),lines=q.logs[id]||[];data={from,lines:lines.slice(from),len:lines.length};}
  else if(kind==='detections')data={duration:10,detections:[{i:0,category:'mrn',text:'review-'+id,enabled:true,t_start:0,t_end:1,track:-1,person:-1,confidence:.9}]};
  else if(kind==='mediainfo')data={duration:10,width:320,height:180};
  else if(kind==='report')data={detections:[],audio_redactions:[{t0:1,t1:2,mode:'mute'}],audio_suggestions:[],audio_transcript:[]};
  else if(kind==='boxes_at')data={boxes:[]};
  else data={};
  const p=q.plans.find(p=>!p.used&&(!p.kind||p.kind===kind)&&(!p.id||p.id===id));
  if(p){p.used=true;if(p.data!==undefined)data=p.data;if(p.abort){e.done=true;e.abort=true;return route.abort('failed');}if(p.hold){e.held=true;await new Promise(resolve=>q.held.push({e,release:resolve}));}}
  e.payload=data;e.done=true;
  await route.fulfill({status:p?.status||200,contentType:'application/json',body:JSON.stringify(data)}).catch(x=>e.fulfillError=x.message);
 });
 await page.goto(base);await page.waitForFunction(()=>typeof openJob==='function');
 assert.equal(await page.title(),'OpenScrub');assert.ok((await page.locator('body').innerText()).includes('OpenScrub'));
 q.page=page;return q;
}
const held=(q,kind,id)=>q.held.find(h=>!h.released&&h.e.kind===kind&&h.e.id===id);
async function release(q,kind,id){const h=held(q,kind,id);assert.ok(h);h.released=true;h.release();await pause(100);}
async function snap(q){return q.page.evaluate(()=>({cur:CUR,gen:VIEW_GEN,progress:document.getElementById('prog')?.value,heading:document.querySelector('#jobcard h2')?.textContent,phase:document.getElementById('ph')?.textContent,log:document.getElementById('log')?.textContent,logN:LOGN,review:document.getElementById('review')?.textContent,detail:detail.textContent,audio:BE.audio,drafts:REVIEW_DRAFTS.size,poll:POLL!==null}));}
async function done(q,extra={}){results.push({name:q.name,snapshot:await snap(q),events:q.events,errors:q.errors,console:q.console,unreleasedGates:q.held.filter(h=>!h.released).length,...extra});await q.page.close();}
async function opened(q,id){await q.page.evaluate(id=>openJob(id),id);await wait(async()=>await q.page.locator('#log').count()&&await q.page.locator('#log').innerText()===('log-'+id));}
// Full emitted script: metadata A arrives only after B is current.
{
 const q=await setup('late-metadata-after-switch');q.plans.push({id:'A',kind:'meta',hold:true,data:meta('A',{name:'LATE-A',progress:.9})});
 await q.page.evaluate(()=>openJob('A'));await wait(()=>held(q,'meta','A'));await opened(q,'B');await release(q,'meta','A');
 assert.equal((await snap(q)).cur,'B');assert.match((await snap(q)).heading,/job B/);assert.equal(q.events.filter(e=>e.id==='A'&&e.kind==='log').length,0);await done(q);
}
{
 const q=await setup('late-log-after-switch');q.plans.push({id:'A',kind:'log',hold:true});await q.page.evaluate(()=>openJob('A'));await wait(()=>held(q,'log','A'));await opened(q,'B');await release(q,'log','A');assert.equal((await snap(q)).log,'log-B');await done(q);
}
{
 const q=await setup('same-job-reopen-fences-old-generation');q.plans.push({id:'A',kind:'meta',hold:true,data:meta('A',{name:'LATE-SAME-A',progress:.9})});await q.page.evaluate(()=>openJob('A'));await wait(()=>held(q,'meta','A'));await opened(q,'A');await release(q,'meta','A');assert.equal((await snap(q)).gen,2);assert.equal((await snap(q)).progress,.2);await done(q);
}
{
 const q=await setup('delete-while-metadata-pending');q.plans.push({id:'A',kind:'meta',hold:true});await q.page.evaluate(()=>openJob('A'));await wait(()=>held(q,'meta','A'));await q.page.evaluate(()=>delJob('A'));await release(q,'meta','A');assert.equal((await snap(q)).cur,null);assert.equal((await snap(q)).detail,'');const count=q.events.length;await q.page.clock.runFor(2701);await pause(100);assert.equal(q.events.length,count);await done(q,{afterDeletionFakeMs:2701,noNewJobRequests:true});
}

{
 const q=await setup('actual-late-log-body-after-switch');q.passLog=true;
 await fetch(base+'/__qa__/control',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({stream_next:true,kind:'log'})});
 let headers=0,finished=0;q.page.on('response',r=>{if(r.url()===base+'/api/jobs/A/log?from=0'){headers++;r.finished().then(()=>finished++).catch(()=>{});}});
 await q.page.evaluate(()=>openJob('A'));await wait(()=>headers===1);const before=await snap(q);assert.equal(finished,0);await opened(q,'B');await fetch(base+'/__qa__/control',{method:'POST',headers:{'content-type':'application/json'},body:'{"release":true}'});await wait(()=>finished===1);await pause(50);assert.equal((await snap(q)).log,'log-B');await done(q,{before,headers,finished});
}

// Timer-driven overlap: three cycles wait in the same view at the same time.
{
 const q=await setup('timer-overlap-duplicate-log');for(let i=0;i<3;i++)q.plans.push({id:'A',kind:'log',hold:true});await q.page.evaluate(()=>openJob('A'));await wait(()=>q.held.length===1);
 await q.page.clock.runFor(901);await wait(()=>q.held.length===2);await q.page.clock.runFor(901);await wait(()=>q.held.length===3);
 const before=await snap(q);const pending=q.held.length;for(let i=0;i<3;i++)await release(q,'log','A');assert.equal((await snap(q)).log,'log-A\nlog-A\nlog-A');await q.page.locator('#jobcard').screenshot({path:ROOT+'/overlap-duplicate-log.png'});await done(q,{pendingCycles:pending,before});
}
{
 const q=await setup('same-view-late-metadata-regresses-progress');q.plans.push({id:'A',kind:'meta',hold:true,data:meta('A',{progress:.1})},{id:'A',kind:'meta',data:meta('A',{progress:.8})});await q.page.evaluate(()=>openJob('A'));await wait(()=>held(q,'meta','A'));await q.page.clock.runFor(901);await wait(async()=>(await snap(q)).progress===.8);const before=await snap(q);await release(q,'meta','A');assert.equal((await snap(q)).progress,.1);await done(q,{before});
}
// Actual HTTP headers arrive, body remains incomplete on the server.
{
 const q=await setup('metadata-headers-with-unfinished-body');q.passMeta=true;await fetch(base+'/__qa__/control',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({stream_next:true})});
 let headers=0,bodyFinished=0; q.page.on('response',r=>{if(r.url()===base+'/api/jobs/A'){headers++;r.finished().then(()=>bodyFinished++).catch(()=>{});}});
 await q.page.evaluate(()=>openJob('A'));await wait(()=>headers===1);const atHeaders=await snap(q);await q.page.clock.runFor(1801);await wait(()=>q.events.filter(e=>e.kind==='meta').length===3);await pause(100);const before={headers,bodyFinished,snapshot:await snap(q),server:await(await fetch(base+'/__qa__/state')).json()};
 assert.equal(headers,3);assert.equal(bodyFinished,2);await fetch(base+'/__qa__/control',{method:'POST',headers:{'content-type':'application/json'},body:'{"release":true}'});await wait(()=>bodyFinished===3);await done(q,{atHeaders,before,after:{headers,bodyFinished,server:await(await fetch(base+'/__qa__/state')).json()}});
}
{
 const q=await setup('transient-metadata-network-failure-then-success');q.plans.push({id:'A',kind:'meta',abort:true});await q.page.evaluate(()=>openJob('A'));await wait(()=>q.errors.length===1);const failed=await snap(q);await q.page.clock.runFor(901);await wait(async()=>(await snap(q)).log==='log-A');assert.equal(q.errors.length,1);await done(q,{failed});
}
{
 const q=await setup('transient-log-network-failure-then-success');q.plans.push({id:'A',kind:'log',abort:true});await q.page.evaluate(()=>openJob('A'));await wait(()=>q.errors.length===1);const failed=await snap(q);await q.page.clock.runFor(901);await wait(async()=>(await snap(q)).log==='log-A');await done(q,{failed});
}
{
 const q=await setup('authoritative-log-length-shrinks');q.logs.A=['A0','A1','A2','A3','A4'];await q.page.evaluate(()=>openJob('A'));await wait(async()=>(await snap(q)).logN===5);q.logs.A=['new-A0'];await q.page.clock.runFor(901);await wait(()=>q.events.filter(e=>e.kind==='log').length===2);await pause(50);await q.page.clock.runFor(901);await wait(()=>q.events.filter(e=>e.kind==='log').length===3);assert.equal((await snap(q)).logN,5);await done(q);
}

{
 const q=await setup('stale-same-view-poll-starts-review-after-done');q.plans.push({id:'A',kind:'meta',hold:true,data:meta('A',{phase:'review',progress:1})},{id:'A',kind:'meta',data:meta('A',{phase:'done',progress:1,has_output:true})});
 await q.page.evaluate(()=>openJob('A'));await wait(()=>held(q,'meta','A'));await q.page.clock.runFor(901);await wait(async()=>(await snap(q)).phase==='done');const before=await snap(q);await release(q,'meta','A');await wait(async()=>(await snap(q)).review?.includes('review-A'));assert.equal((await snap(q)).phase,'review');await done(q,{before});
}
{
 const q=await setup('pending-review-publishes-after-newer-done-phase');q.phase='review';q.plans.push({id:'A',kind:'detections',hold:true});
 await q.page.evaluate(()=>openJob('A'));await wait(()=>held(q,'detections','A'));q.phase='done';await q.page.clock.runFor(901);await wait(async()=>(await snap(q)).phase==='done');const before=await snap(q);await release(q,'detections','A');await wait(async()=>(await snap(q)).review?.includes('review-A'));assert.equal((await snap(q)).phase,'done');await done(q,{before});
}


{
 const q=await setup('http503-json-is-published-without-status-check');q.plans.push({id:'A',kind:'meta',status:503,data:{error:'synthetic service unavailable'}});await q.page.evaluate(()=>openJob('A'));await wait(()=>q.errors.length===1);const failed=await snap(q);assert.match(failed.heading,/undefined/);await q.page.clock.runFor(901);await wait(async()=>(await snap(q)).phase==='queued');await done(q,{failed});
}

// Downstream review owns the initiating job/view; a stale result cannot populate B.
{
 const q=await setup('downstream-review-after-switch');q.phase='review';q.plans.push({id:'A',kind:'detections',hold:true});await q.page.evaluate(()=>openJob('A'));await wait(()=>held(q,'detections','A'));await q.page.evaluate(()=>openJob('B'));await wait(async()=>(await snap(q)).review?.includes('review-B'));await release(q,'detections','A');assert.ok(!(await snap(q)).review.includes('review-A'));await done(q);
}
{
 const q=await setup('downstream-audio-report-after-switch');q.phase='review';q.plans.push({id:'A',kind:'report',hold:true,data:{detections:[],audio_redactions:[{t0:7,t1:8,mode:'bleep'}]}});await q.page.evaluate(()=>openJob('A'));await wait(async()=>(await snap(q)).review?.includes('review-A'));await q.page.getByRole('button',{name:'▶ Preview video & edit boxes (before rendering)'}).click();await wait(()=>held(q,'report','A'));await q.page.evaluate(()=>openJob('B'));await wait(async()=>(await snap(q)).review?.includes('review-B'));await release(q,'report','A');assert.deepEqual((await snap(q)).audio,[]);await done(q);
}
{
 const q=await setup('simulated-hidden-and-frozen-tab-resume');await opened(q,'A');
 // Native CDP freeze/resume is available. Headless target stays visible; no claim of real background-tab throttling.
 const cdp=await q.page.context().newCDPSession(q.page);const lifecycle=[];try{await cdp.send('Page.setWebLifecycleState',{state:'frozen'});lifecycle.push('frozen');await pause(100);await cdp.send('Page.setWebLifecycleState',{state:'active'});lifecycle.push('active');}catch(e){lifecycle.push(e.message);}
 const nativeVisibility=await q.page.evaluate(()=>document.visibilityState);
 await q.page.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,get:()=>true});Object.defineProperty(document,'visibilityState',{configurable:true,get:()=> 'hidden'});document.dispatchEvent(new Event('visibilitychange'));});
 const before=q.events.length;await q.page.clock.runFor(901);await wait(()=>q.events.length>=before+2);const hidden=await snap(q);
 await q.page.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,get:()=>false});Object.defineProperty(document,'visibilityState',{configurable:true,get:()=> 'visible'});document.dispatchEvent(new Event('visibilitychange'));});
 await q.page.clock.runFor(901);await wait(()=>q.events.length>=before+4);await done(q,{lifecycle,nativeVisibility,hidden,visibilitySimulation:true});
}
await browser.close();fs.writeFileSync(ROOT+'/browser-results.json',JSON.stringify({browser:'Chromium/Playwright existing fallback',results},null,2));console.log(JSON.stringify(results.map(r=>({name:r.name,requests:r.events.length,errors:r.errors,cur:r.snapshot.cur,log:r.snapshot.log})),null,2));
})().catch(e=>{fs.writeFileSync(ROOT+'/browser-error.txt',e.stack);console.error(e);process.exit(1)});
