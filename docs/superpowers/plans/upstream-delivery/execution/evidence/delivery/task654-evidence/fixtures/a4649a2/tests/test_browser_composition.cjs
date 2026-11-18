const {chromium}=require(process.env.OPENSCRUB_PLAYWRIGHT_MODULE);
const fs=require('node:fs'),assert=require('node:assert/strict');
const base=process.env.COMBINED_BASE,root=process.env.VERIFY_RUN+'/logs';
const pause=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.OPENSCRUB_CHROMIUM,args:['--no-sandbox']});
 const page=await browser.newPage({viewport:{width:1280,height:950}}),errors=[],diagnostics=[],records=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(['error','warning'].includes(m.type()))diagnostics.push({text:m.text(),url:m.location().url})});
 page.on('dialog',d=>d.dismiss());
 const control=async data=>{const r=await page.request.post(base+'/__qa__/control',{data});assert.equal(r.status(),200);return r.json()};
 const state=async()=> (await page.request.get(base+'/__qa__/state')).json();
 async function wait(fn){for(let n=0;n<250;n++){if(await fn())return;await pause(20)}throw Error('bounded combined condition expired')}
 async function settled(){await wait(()=>page.evaluate(()=>POLL_CYCLE===null))}
 async function review(id){await page.evaluate(id=>openJob(id),id);await wait(()=>page.locator('#jobcard').count());
  await page.evaluate(()=>loadReview());await wait(()=>page.evaluate(()=>REVIEW_SCHED?.owns()));}
 try{
  await page.goto(base);assert.equal(await page.title(),'OpenScrub');assert.match(await page.locator('body').innerText(),/OpenScrub/);
  assert.equal(await page.locator('vite-error-overlay,nextjs-portal').count(),0);assert.equal(page.url(),base+'/');
  await control({hold_log:true,hold_thumb:true});
  await review('A');await wait(async()=> (await state()).log_entered>=1);
  await page.evaluate(()=>scrollTo(0,document.getElementById('detwrap').getBoundingClientRect().top+scrollY-55));
  await wait(()=>page.evaluate(()=>THUMB_FLIGHTS.size>0));
  await page.evaluate(()=>{window.firstView=REVIEW_SCHED;window.firstLog=RECENT_LOG;window.slotMax=THUMB_FLIGHTS.size;
   window.slotWatch=setInterval(()=>slotMax=Math.max(slotMax,THUMB_FLIGHTS.size),5)});
  await review('B');await review('A');
  assert(await page.evaluate(()=>firstView.disposed&&REVIEW_SCHED!==firstView));
  await control({hold_log:false,hold_thumb:false});await settled();
  await wait(()=>page.evaluate(()=>THUMB_FLIGHTS.size===0));
  const ownership=await page.evaluate(()=>({maxSlots:slotMax,normal:REVIEW_SCHED.normalIds.length,
   descriptors:REVIEW_META.byId.size,members:Object.keys(ROWCARD).length,title:document.querySelector('#jobcard h2').firstChild.textContent.trim()}));
  assert(ownership.maxSlots<=4);assert(ownership.normal<=64);assert.equal(ownership.descriptors,101);assert.equal(ownership.members,102);
  assert.equal(ownership.title,'Family &amp; friends — café.mp4');records.push({ownership});
  // Actual failed thumbnail response creates a pending retry; pagehide/show are
  // controlled event dispatch, not native BFCache or native visibility proof.
  let injected=false;await page.route('**/thumb/**',route=>{if(!injected){injected=true;return route.fulfill({status:503,body:'controlled preview refusal'})}return route.continue()});
  await page.evaluate(()=>loadReview());await wait(()=>page.evaluate(()=>REVIEW_SCHED?.owns()));
  await page.evaluate(()=>scrollTo(0,document.getElementById('detwrap').getBoundingClientRect().top+scrollY-55));
  await wait(()=>page.evaluate(()=>[...REVIEW_SCHED.retries.values()].some(r=>r.failures===1)));
  const retry=await page.evaluate(()=>{const pair=[...REVIEW_SCHED.retries].find(([id,r])=>r.failures===1);selSet.add(pair[0]);
   window.beforeHide=REVIEW_SCHED;window.dispatchEvent(new Event('pagehide'));return {id:pair[0],readyAt:pair[1].readyAt,failures:pair[1].failures}});
  assert(await page.evaluate(()=>beforeHide.disposed&&beforeHide.bindings.size===0&&POLL_CYCLE===null));
  await page.evaluate(()=>window.dispatchEvent(new Event('pageshow')));
  assert(await page.evaluate(({id,readyAt,failures})=>REVIEW_SCHED!==beforeHide&&REVIEW_SCHED.retries.get(id).readyAt===readyAt&&REVIEW_SCHED.retries.get(id).failures===failures,retry));
  await page.unroute('**/thumb/**');records.push({controlledLifecycle:retry});
  // Complete category choices include rows whose cards are absent.
  await page.evaluate(()=>setAll('email',false));
  assert(await page.evaluate(()=>Object.keys(EN).length===102&&Object.values(EN).every(x=>x===false)));
  await page.getByRole('button',{name:/Preview video & edit boxes/}).click();
  await wait(()=>page.evaluate(()=>BE_VIEW?.transform&&document.getElementById('beImg').naturalWidth===320));
  await page.evaluate(()=>{window.editorOwner=BE_VIEW;window.editorNode=document.getElementById('beCv');window.editorDraft=BE});
  await page.locator('#beAdd').click();
  const box=await page.locator('#beCv').boundingBox();await page.mouse.click(box.x+box.width*.6,box.y+box.height*.6);
  assert(await page.evaluate(()=>!!BE.addAnchor));
  const gesture=await page.evaluate(()=>JSON.stringify(BE.addAnchor));
  await page.evaluate(()=>scrollTo(0,document.documentElement.scrollHeight));await pause(80);
  assert(await page.evaluate(g=>BE_VIEW===editorOwner&&document.getElementById('beCv')===editorNode&&BE===editorDraft&&JSON.stringify(BE.addAnchor)===g,gesture));
  await page.locator('#beAdd').click();
  await page.locator('#bePlay').click();
  await wait(()=>page.evaluate(()=>BE.playing&&BE_VIEW.transform?.media===document.getElementById('beVid')&&!document.getElementById('beVid').paused));
  await page.evaluate(()=>window.playingNode=document.getElementById('beVid'));
  await page.setViewportSize({width:390,height:844});await pause(80);
  await page.evaluate(()=>scrollTo(0,document.documentElement.scrollHeight));await pause(80);
  assert(await page.evaluate(()=>BE_VIEW===editorOwner&&BE===editorDraft&&document.getElementById('beVid')===playingNode&&BE.playing&&BE_VIEW.transform.width===playingNode.getBoundingClientRect().width));
  records.push({ordinaryPlayResizeAndCardMovement:true});
  await page.screenshot({path:root+'/combined-narrow.png'});
  await page.locator('#bePlay').click();await wait(()=>page.evaluate(()=>!BE.playing));
  // Real save is committed before holding its successful ACK body. A newer
  // opposite choice remains pending, without stale render dispatch.
  await page.evaluate(()=>{BE.audio=[{t0:1,t1:1.2,mode:'bleep'}];BE.audioLoaded=true;applyDet(0,true)});
  await control({hold_ack:true});await page.evaluate(()=>{window.savePromise=saveAndRender()});
  await wait(async()=> (await state()).ack_entered>=1);
  await page.evaluate(()=>{applyDet(0,false);scrollTo(0,document.documentElement.scrollHeight)});
  await control({hold_ack:false});await page.evaluate(()=>savePromise);
  assert(await page.evaluate(()=>EDITS.enabled[0]===false&&/Newer edits/.test(EDITS.status)&&document.getElementById('review')!==null));
  await control({fail_save:true});await page.evaluate(()=>saveAndRender());
  assert(await page.evaluate(()=>EDITS.enabled[0]===false&&/drafts retained/.test(EDITS.status)));
  await control({fail_save:false});
  // This retry is a real save; stop just the subsequent render request using a
  // controlled refusal, so a fresh page can inspect complete saved raw/audio.
  await page.route('**/api/jobs/A/render',route=>route.fulfill({status:409,json:{error:'controlled intermediate render hold'}}));
  await page.evaluate(()=>saveAndRender());
  const saved=await(await page.request.get(base+'/api/jobs/A/report')).json();assert.equal(saved.detections.length,102);
  assert(saved.detections.every(r=>r.enabled===false));assert.deepEqual(saved.audio_redactions,[{t0:1,t1:1.2,mode:'bleep'}]);
  const fresh=await browser.newPage({viewport:{width:1280,height:950}});fresh.on('pageerror',e=>errors.push(e.message));
  await fresh.goto(base);await fresh.evaluate(()=>openJob('A'));await fresh.waitForSelector('#review');
  assert(await fresh.evaluate(()=>Object.keys(EN).length===102&&Object.values(EN).every(x=>x===false)&&Object.keys(EDITS.enabled).length===0));
  await fresh.getByRole('button',{name:/Preview video & edit boxes/}).click();await wait(()=>fresh.evaluate(()=>BE.audioLoaded));
  assert.deepEqual(await fresh.evaluate(()=>BE.audio),[{t0:1,t1:1.2,mode:'bleep'}]);
  records.push({heldSuccessfulAck:true,failedSave:true,freshRawAudioReopen:true,rows:saved.detections.length});
  await fresh.screenshot({path:root+'/combined-desktop.png'});await fresh.close();
  assert.deepEqual(errors,[]);const expected=diagnostics.filter(d=>/503|423|409/.test(d.text));
  assert.equal(diagnostics.length,expected.length,JSON.stringify(diagnostics));
  const report={records,errors,diagnostics,browser:browser.version(),url:page.url(),title:await page.title(),viewports:[[1280,950],[390,844]],lifecycle:'controlled pagehide/pageshow; native BFCache/visibility not claimed'};
  fs.writeFileSync(root+'/combined-browser.json',JSON.stringify(report,null,2));console.log(JSON.stringify(report));
 }finally{await control({hold_log:false,hold_thumb:false,hold_ack:false}).catch(()=>{});await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
