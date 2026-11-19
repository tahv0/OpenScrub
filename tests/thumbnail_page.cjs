const assert=require('node:assert/strict');
const path=require('node:path');
const {chromium}=require(process.env.OPENSCRUB_PLAYWRIGHT_MODULE);
const base=process.env.OPENSCRUB_PAGE_URL,job=process.env.OPENSCRUB_PAGE_JOB,jobB=process.env.OPENSCRUB_PAGE_JOB_B;
const artifacts=process.env.OPENSCRUB_BROWSER_ARTIFACTS;
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.OPENSCRUB_CHROMIUM,args:['--no-sandbox']});
 try{
  const context=await browser.newContext({viewport:{width:1280,height:900}});
  const page=await context.newPage(), errors=[],consoleMessages=[],requests=[];
  page.on('console',m=>{if(['error','warning'].includes(m.type()))consoleMessages.push(m.text());});
  page.on('pageerror',e=>errors.push(e.message));
  page.on('request',r=>requests.push({url:r.url(),method:r.method()}));
  await page.goto(base);assert.equal(page.url(),base);assert.equal(await page.title(),'OpenScrub');
  assert.ok((await page.locator('body').innerText()).includes('OpenScrub'));
  await page.evaluate(id=>openJob(id),job);
  await page.waitForSelector('#thumb0');
  await page.locator('#review details summary').click();
  await page.waitForFunction(()=>[0,2,3].every(i=>document.getElementById('thumb'+i)?.naturalWidth>0));
  assert.equal(await page.locator('#review').count(),1);
  assert.ok((await page.locator('#review').innerText()).includes('outside your zones'));
  await page.locator('#review').scrollIntoViewIfNeeded();
  await page.screenshot({path:path.join(artifacts,'review-desktop.png')});
  const old=await page.locator('#thumb2').getAttribute('src');
  const first=await context.request.get(old);assert.equal(first.status(),200);
  const oldBytes=await first.body(),etag=first.headers().etag;
  const save=await context.request.post(base+'api/jobs/'+job+'/detections',{data:{box_overrides:{'2':[1,1,12,12]}}});
  assert.equal(save.status(),200,await save.text());
  const obsolete=await context.request.get(old,{headers:{'If-None-Match':etag}});assert.equal(obsolete.status(),409);
  // Another image initiates recovery; the already loaded, changed row must
  // become an explicit placeholder rather than continue showing old pixels.
  await page.locator('#thumb0').click();await page.waitForSelector('#det2 [data-thumb-status]:visible');
  assert.equal(await page.locator('#thumb2').evaluate(el=>getComputedStyle(el).visibility),'hidden');
  await page.locator('#lb').click();
  await page.screenshot({path:path.join(artifacts,'review-unavailable.png')});
  await page.locator('#det2 [data-thumb-reopen]').click();
  await page.waitForFunction(()=>document.getElementById('thumb2')?.naturalWidth>0&&getComputedStyle(document.getElementById('thumb2')).visibility!=='hidden');
  const fresh=await page.locator('#thumb2').getAttribute('src');assert.notEqual(fresh,old);
  const second=await context.request.get(fresh);assert.equal(second.status(),200);assert.notDeepEqual(await second.body(),oldBytes);
  await page.evaluate(()=>{window.testReviewRefs={root:document.getElementById('review'),editor:BE,draft:EDITS};});
  // A raw-row-preserving audio publication invalidates V. Opening the lightbox
  // issues a real stale request and uses the mounted review's single recovery.
  const audio=await context.request.post(base+'api/jobs/'+job+'/detections',{data:{audio:[{t0:.1,t1:.4,mode:'mute'}]}});
  assert.equal(audio.status(),200,await audio.text());
  const count=requests.length;
  await page.locator('#thumb2').click();
  await page.waitForFunction(()=>document.querySelector('#lb img')?.naturalWidth>0);
  const state=await page.evaluate(()=>({attempted:REVIEW_IMAGES.attempted,version:REVIEW_IMAGES.version,
   card:document.getElementById('thumb2').src,light:document.querySelector('#lb img').src}));
  assert.equal(state.attempted,true);assert.ok(state.card.includes('v='+state.version));assert.ok(state.light.includes('v='+state.version));
  await page.waitForFunction(()=>getComputedStyle(document.getElementById('thumb2')).visibility!=='hidden'&&getComputedStyle(document.querySelector('#lb img')).visibility!=='hidden');
  assert.equal(await page.evaluate(()=>window.testReviewRefs.root===document.getElementById('review')&&window.testReviewRefs.editor===BE&&window.testReviewRefs.draft===EDITS),true);
  assert.equal(requests.slice(count).filter(r=>r.method==='POST').length,0);
  assert.equal(requests.slice(count).filter(r=>r.url.includes('/edit_sample')).length,0);
  await page.locator('#lb').click();
  // Hold a response after the real server commits, then lose that ACK while a
  // newer edit and an explicit review reopening are in flight.
  let releaseAck,commitDone;const committed=new Promise(r=>commitDone=r),gate=new Promise(r=>releaseAck=r);
  const held=async route=>{if(route.request().method()!=='POST')return route.continue();await route.fetch();commitDone();await gate;await route.abort('failed');};
  await page.route('**/api/jobs/'+job+'/detections',held);
  await page.evaluate(()=>{toggleDet(2);BE.audio=[{t0:.1,t1:.4,mode:'mute'}];BE.audioLoaded=true;
   window.heldRefs={editor:BE,draft:EDITS,manual:MAN,audio:BE.audio};window.heldSave=saveAndRender();});
  await committed;
  await page.evaluate(()=>{toggleDet(2);BE.ov[2]=[2,2,14,14];
   MAN.push({manual_id:'page-newer',t_start:.1,t_end:.8,t_ref:.2,screen_box:[3,3,15,15]});
   BE.audio.push({t0:.5,t1:.8,mode:'bleep'});});
  await page.locator('#thumb2').click();
  await page.waitForSelector('#det2 [data-thumb-reopen]:visible');
  await page.locator('#lb').click();
  await page.locator('#det2 [data-thumb-reopen]').click();
  await page.waitForFunction(()=>REVIEW_IMAGES&&!REVIEW_IMAGES.attempted&&REVIEW_IMAGES.root&&REVIEW_IMAGES.root!==window.testReviewRefs.root&&document.getElementById('thumb2'));
  releaseAck();assert.equal(await page.evaluate(()=>window.heldSave),false);
  assert.equal(await page.evaluate(()=>BE===heldRefs.editor&&EDITS===heldRefs.draft&&MAN===heldRefs.manual&&
   BE.audio===heldRefs.audio&&BE.audioSaved===null&&BE.audio.length===2&&EN[2]===true&&
   MAN[0].manual_id==='page-newer'&&BE.ov[2][0]===2),true);
  await page.unroute('**/api/jobs/'+job+'/detections',held);
  await page.route('**/api/jobs/'+job+'/render',route=>route.fulfill({status:409,contentType:'application/json',body:JSON.stringify({error:'test render held'})}));
  await page.evaluate(()=>saveAndRender());
  const reopened=await context.newPage();await reopened.goto(base);await reopened.evaluate(id=>openJob(id),job);
  await reopened.waitForSelector('#thumb2');
  const raw=await context.request.get(base+'api/jobs/'+job+'/detections');
  const rows=(await raw.json()).detections;assert.equal(rows.length,5);assert.equal(rows[2].enabled,true);
  assert.ok(rows.some(row=>row.text==='user-drawn'));await reopened.close();
  // Hold old A's recovery while visiting B and returning to A. The delayed
  // response must not touch the new A review or its image bindings.
  await page.evaluate(()=>loadReview());await page.waitForFunction(()=>document.getElementById('thumb2')?.naturalWidth>0);
  assert.equal((await context.request.post(base+'api/jobs/'+job+'/detections',{data:{audio:[{t0:.1,t1:.4,mode:'mute'},{t0:.5,t1:.8,mode:'bleep'}]}})).status(),200);
  let releaseMeta,metaEntered;const metaGate=new Promise(r=>releaseMeta=r),metaStarted=new Promise(r=>metaEntered=r);
  let holdFirst=true;
  const holdMetadata=async route=>{if(route.request().method()!=='GET'||!holdFirst)return route.continue();
   holdFirst=false;const response=await route.fetch();metaEntered();await metaGate;await route.fulfill({response});};
  await page.route('**/api/jobs/'+job+'/detections',holdMetadata);
  await page.locator('#thumb2').click();await Promise.race([metaStarted,new Promise((_,reject)=>setTimeout(()=>reject(Error('metadata request not observed')),10000))]);
  await page.evaluate(id=>openJob(id),jobB);await page.waitForFunction(id=>CUR===id&&document.getElementById('thumb0'),jobB);
  await page.evaluate(id=>openJob(id),job);await page.waitForFunction(id=>CUR===id&&document.getElementById('thumb2'),job);
  await page.evaluate(()=>{window.revisitedRoot=document.getElementById('review');window.revisitedSrc=document.getElementById('thumb2').src;});
  releaseMeta();await page.unroute('**/api/jobs/'+job+'/detections',holdMetadata);
  await page.waitForTimeout(100);
  assert.equal(await page.evaluate(()=>document.getElementById('review')===revisitedRoot&&document.getElementById('thumb2').src===revisitedSrc),true);
  if(await page.locator('#lb').count())await page.locator('#lb').click();
  // Persistent metadata failure spends exactly one attempt; a deliberate
  // reopen is the only operation that creates a new budget.
  assert.equal((await context.request.post(base+'api/jobs/'+job+'/detections',{data:{audio:[{t0:.1,t1:.4,mode:'mute'},{t0:.5,t1:.8,mode:'bleep'}]}})).status(),200);
  let metadataCalls=0;const unavailable=route=>{metadataCalls++;return route.fulfill({status:503,contentType:'application/json',body:'{}'});};
  await page.route('**/api/jobs/'+job+'/detections',unavailable);
  const recoveryStart=requests.length;await page.locator('#thumb2').click();
  await page.waitForSelector('#det2 [data-thumb-reopen]:visible');await page.locator('#lb').click();
  await page.locator('#thumb2').click();await page.waitForSelector('#det2 [data-thumb-reopen]:visible');await page.locator('#lb').click();
  assert.equal(metadataCalls,1);assert.equal(requests.slice(recoveryStart).filter(r=>r.method==='POST'||r.url.includes('/edit_sample')).length,0);
  await page.unroute('**/api/jobs/'+job+'/detections',unavailable);
  await page.locator('#det2 [data-thumb-reopen]').click();await page.waitForFunction(()=>REVIEW_IMAGES&&!REVIEW_IMAGES.attempted&&REVIEW_IMAGES.root&&REVIEW_IMAGES.root===document.getElementById('review')&&REVIEW_IMAGES.root!==window.revisitedRoot);
  await page.setViewportSize({width:390,height:844});
  await page.locator('#review').scrollIntoViewIfNeeded();
  await page.screenshot({path:path.join(artifacts,'review-small.png')});
  assert.deepEqual(errors,[]);
  assert.deepEqual(consoleMessages.filter(m=>!/Failed to load resource: (the server responded with a status of (409|503)|net::ERR_FAILED)/.test(m)),[]);
  const persisted=await context.request.get(base+'api/jobs/'+job+'/detections');assert.equal(persisted.status(),200);
  console.log(JSON.stringify({url:page.url(),title:await page.title(),screenshots:['review-desktop.png','review-unavailable.png','review-small.png'],
   oldStatus:obsolete.status(),pixelChanged:true,recovery:true,pageErrors:errors,consoleMessages,rawRows:(await persisted.json()).detections.length,heldLostAckAndReopen:true,lateABA:true,persistentFailure:true}));
  await context.close();
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
