const assert = require('node:assert/strict');
const path = require('node:path');
const {chromium} = require(process.env.OPENSCRUB_PLAYWRIGHT_MODULE);
const base = process.env.OPENSCRUB_PAGE_URL, job = process.env.OPENSCRUB_PAGE_JOB, jobB = process.env.OPENSCRUB_PAGE_JOB_B;
const artifacts = process.env.OPENSCRUB_BROWSER_ARTIFACTS;

// Replacement, panel exit and job navigation retire the scheduler and its
// lightbox; callbacks retained from the old blob cannot alter a new review.
async function lightboxTeardown(context, kind) {
 const page=await context.newPage(), errors=[], requests=[];
 page.on('pageerror',e=>errors.push(e.message));
 page.on('request',r=>requests.push({url:r.url(),method:r.method()}));
 try {
  await page.goto(base);await page.evaluate(id=>openJob(id),job);
  await page.locator('#detwrap').scrollIntoViewIfNeeded();
  await page.waitForFunction(()=>document.querySelector('#det2 img')?.naturalWidth>0);
  await page.locator('#det2 img').click();
  await page.waitForFunction(()=>document.querySelector('#lb img')?.naturalWidth>0);
  await page.evaluate(()=>{BE.ov[2]=[2,3,14,15];BE.audio=[{t0:.1,t1:.2,mode:'mute'}];
   EDITS.audioInFlight=true;MAN.push({manual_id:'teardown-draft'});
   const light=REVIEW_SCHED.lightbox,card=REVIEW_SCHED.bindings.get(2);
   window.oldProof={card:card.img,cardError:card.img.onerror,cardLoad:card.img.onload,owner:REVIEW_SCHED,root:document.getElementById('review'),overlay:light.overlay,
    img:light.img,error:light.img.onerror,load:light.img.onload,editor:BE,draft:EDITS,manual:MAN,audio:BE.audio};});
  if(kind==='replacement'){
   for(const kind of ['network','409','503']){
    const failed=route=>kind==='network'?route.abort('failed'):
     route.fulfill({status:+kind,contentType:'application/json',body:'{"error":"pending"}'});
    await page.route('**/api/jobs/'+job+'/detections',failed);
    await page.evaluate(()=>loadReview());await page.unroute('**/api/jobs/'+job+'/detections',failed);
    assert.equal(await page.evaluate(()=>REVIEW_SCHED===oldProof.owner&&document.getElementById('review')===oldProof.root&&
     oldProof.overlay.isConnected&&BE===oldProof.editor&&EDITS===oldProof.draft&&MAN===oldProof.manual&&BE.audio===oldProof.audio),true);
   }
   await page.evaluate(()=>loadReview());
  } else if(kind==='panel') await page.evaluate(()=>showPanel('compare'));
  else await page.evaluate(id=>openJob(id),jobB);
  assert.equal(await page.evaluate(()=>!oldProof.overlay.isConnected&&!oldProof.img.isConnected&&REVIEW_SCHED!==oldProof.owner),true);
  assert.equal(await page.locator('#lb').count(),0);
  if(kind==='panel')await page.evaluate(()=>loadReview());
  if(kind==='job')await page.evaluate(id=>openJob(id),job);
  await page.locator('#detwrap').scrollIntoViewIfNeeded();
  await page.waitForFunction(()=>document.querySelector('#det2 img')?.naturalWidth>0);
  await page.locator('#det2 img').click();
  await page.waitForFunction(()=>document.querySelector('#lb img')?.naturalWidth>0);
  await page.evaluate(()=>{BE.ov[2]=[4,5,16,17];MAN.push({manual_id:'new-owner'});
   const light=REVIEW_SCHED.lightbox;window.newProof={owner:REVIEW_SCHED,overlay:light.overlay,img:light.img,src:light.img.src,
    card:document.querySelector('#det2 img'),cardSrc:document.querySelector('#det2 img').src,
    editor:BE,draft:EDITS,manual:MAN};oldProof.error();oldProof.load();oldProof.cardError();oldProof.cardLoad();});
  assert.equal(await page.evaluate(()=>REVIEW_SCHED===newProof.owner&&newProof.overlay.isConnected&&newProof.img.isConnected&&
   newProof.img.src===newProof.src&&newProof.card.isConnected&&newProof.card.src===newProof.cardSrc&&BE===newProof.editor&&EDITS===newProof.draft&&MAN===newProof.manual&&
   MAN.some(x=>x.manual_id==='new-owner')&&BE.ov[2][0]===4),true);
  assert.equal(requests.filter(r=>r.method==='POST'||r.url.includes('/render')||r.url.includes('/edit_sample')).length,0);
  assert.deepEqual(errors,[]);
 } finally {await page.close();}
}

(async () => {
 const browser = await chromium.launch({headless:true, executablePath:process.env.OPENSCRUB_CHROMIUM, args:['--no-sandbox']});
 try {
  const context = await browser.newContext({viewport:{width:1280,height:900}});
  const page = await context.newPage(), errors = [], warnings = [], requests = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('console', m => {if (['error','warning'].includes(m.type())) warnings.push(m.text());});
  page.on('request', r => requests.push({url:r.url(),method:r.method()}));
  await page.goto(base);
  assert.equal(page.url(),base); assert.equal(await page.title(),'OpenScrub');
  assert.match(await page.locator('body').innerText(),/OpenScrub/);
  await page.evaluate(id => openJob(id),job);
  // Cards are virtualized: scroll the section into the scheduler's viewport.
  await page.locator('#detwrap').scrollIntoViewIfNeeded();
  await page.waitForFunction(() => [0,2].every(i => document.querySelector(`#det${i} img`)?.naturalWidth > 0));
  assert.match(await page.locator('#review').innerText(),/outside your zones/);
  await page.screenshot({path:path.join(artifacts,'review-desktop.png')});
  const old = requests.find(r => r.url.includes('/thumb/2?')).url;
  const first = await context.request.get(old); assert.equal(first.status(),200);
  const oldBytes = await first.body(), etag = first.headers().etag;
  const save = await context.request.post(base+'api/jobs/'+job+'/detections',{data:{box_overrides:{'2':[1,1,12,12]}}});
  assert.equal(save.status(),200,await save.text());
  const obsolete = await context.request.get(old,{headers:{'If-None-Match':etag}});
  assert.equal(obsolete.status(),409);
  await page.evaluate(() => {window.reviewRefs={root:document.getElementById('review'),editor:BE,draft:EDITS};});
  // The scheduler fetches image blobs, so the stale request is the detframe
  // fetch rather than an <img src> request. Changed rows stay unavailable.
  await page.locator('#det0 img').click();
  await page.waitForSelector('#det2 [data-thumb-reopen]:visible');
  assert.equal(await page.locator('#det2 .thumbwell').evaluate(n=>n.classList.contains('unavailable')),true);
  assert.equal(await page.evaluate(() => reviewRefs.root===document.getElementById('review') && reviewRefs.editor===BE && reviewRefs.draft===EDITS),true);
  await page.locator('#lb').click();
  await page.screenshot({path:path.join(artifacts,'review-unavailable.png')});
  await page.locator('#det2 [data-thumb-reopen]').click();
  await page.waitForFunction(() => document.getElementById('review')!==reviewRefs.root && document.querySelector('#det2 img')?.naturalWidth>0);
  const fresh = requests.filter(r => r.url.includes('/thumb/2?')).at(-1).url;
  assert.notEqual(fresh,old);
  const second = await context.request.get(fresh); assert.equal(second.status(),200);
  assert.notDeepEqual(await second.body(),oldBytes);
  await page.evaluate(() => {window.reviewRefs={root:document.getElementById('review'),editor:BE,draft:EDITS};});
  const audio = await context.request.post(base+'api/jobs/'+job+'/detections',{data:{audio:[{t0:.1,t1:.4,mode:'mute'}]}});
  assert.equal(audio.status(),200,await audio.text());
  const start = requests.length;
  await page.locator('#det2 img').click();
  await page.waitForFunction(() => document.querySelector('#lb img')?.naturalWidth>0 &&
   document.querySelector('#det2 img')?.naturalWidth>0 && REVIEW_SCHED.meta.thumbnails.attempted);
  const state = await page.evaluate(() => ({version:REVIEW_SCHED.meta.thumbnails.version,
   same:reviewRefs.root===document.getElementById('review')&&reviewRefs.editor===BE&&reviewRefs.draft===EDITS}));
  const recovered = requests.slice(start);
  assert.ok(recovered.some(r=>r.url.includes('/detframe/2?') && r.url.includes('v='+state.version)));
  assert.ok(recovered.some(r=>r.url.includes('/thumb/2?') && r.url.includes('v='+state.version)));
  assert.equal(state.same,true);
  assert.equal(recovered.filter(r=>r.method==='POST'||r.url.includes('/edit_sample')).length,0);
  await page.locator('#lb').click();
  // A lost save acknowledgement must not discard newer drafts, including
  // when a stale preview causes the user to reopen the review during the save.
  let releaseAck, committed, originalSubmission;
  const ackGate=new Promise(r=>releaseAck=r), commitDone=new Promise(r=>committed=r);
  const held=async route=>{if(route.request().method()!=='POST')return route.continue();
   originalSubmission=route.request().postDataJSON();
   await route.fetch();committed();await ackGate;await route.abort('failed');};
  await page.route('**/api/jobs/'+job+'/detections',held);
  await page.evaluate(()=>{applyDet(2,false);BE.audio=[{t0:.1,t1:.4,mode:'mute'}];BE.audioLoaded=true;
   window.heldRefs={editor:BE,draft:EDITS,manual:MAN,audio:BE.audio};window.heldSave=saveAndRender();});
  await commitDone;
  await page.evaluate(()=>{applyDet(2,true);BE.ov[2]=[2,2,14,14];
   MAN.push({manual_id:'page-newer',t_start:.1,t_end:.8,t_ref:.2,screen_box:[3,3,15,15]});
   BE.audio.push({t0:.5,t1:.8,mode:'bleep'});});
  await page.locator('#det2 img').click();
  await page.waitForSelector('#det2 [data-thumb-reopen]:visible');
  await page.locator('#lb').click();
  await page.locator('#det2 [data-thumb-reopen]').click();
  await page.waitForFunction(()=>document.getElementById('review')!==reviewRefs.root && !!document.querySelector('#det2 img'));
  releaseAck();assert.equal(await page.evaluate(()=>window.heldSave),false);
  assert.equal(await page.evaluate(()=>BE===heldRefs.editor&&EDITS===heldRefs.draft&&MAN===heldRefs.manual&&
   BE.audio===heldRefs.audio&&BE.audioSaved===null&&BE.audio.length===2&&EN[2]===true&&
   MAN[0].manual_id==='page-newer'&&BE.ov[2][0]===2),true);
  await page.unroute('**/api/jobs/'+job+'/detections',held);
  const retries=[];let renderCalls=0;
  await page.route('**/api/jobs/'+job+'/detections',route=>{
   if(route.request().method()==='POST')retries.push(route.request().postDataJSON());return route.continue();});
  await page.route('**/api/jobs/'+job+'/render',route=>{renderCalls++;
   return route.fulfill({status:409,contentType:'application/json',body:'{"error":"test render held"}'});});
  await page.evaluate(()=>saveAndRender());
  assert.deepEqual(retries[0],originalSubmission,'first retry changed the unconfirmed submission');
  assert.equal(renderCalls,0,'retry rendered while newer edits remained pending');
  assert.equal(await page.evaluate(()=>EDITS.enabled[2]===true&&BE.ov[2][0]===2&&
   MAN.some(x=>x.manual_id==='page-newer')&&BE.audio.length===2),true);
  const retryRaw=await context.request.get(base+'api/jobs/'+job+'/detections');
  const retryRows=(await retryRaw.json()).detections;assert.equal(retryRows.length,4);assert.equal(retryRows[2].enabled,false);
  await page.evaluate(()=>saveAndRender());
  assert.equal(retries.length,2);assert.equal(renderCalls,1);
  assert.equal(retries[1].enabled['2'],true);assert.equal(retries[1].manual[0].manual_id,'page-newer');
  const raw=await context.request.get(base+'api/jobs/'+job+'/detections');
  const rows=(await raw.json()).detections;assert.equal(rows.length,5);assert.equal(rows[2].enabled,true);
  assert.ok(rows.some(row=>row.text==='user-drawn'));
  // A recovery response from A must not mutate a new A review after A→B→A.
  await page.evaluate(()=>loadReview());
  await page.waitForFunction(()=>document.querySelector('#det2 img')?.naturalWidth>0);
  assert.equal((await context.request.post(base+'api/jobs/'+job+'/detections',{data:{audio:[{t0:.1,t1:.45,mode:'mute'},{t0:.5,t1:.8,mode:'bleep'}]}})).status(),200);
  let releaseMeta,metaEntered;const gate=new Promise(r=>releaseMeta=r),started=new Promise(r=>metaEntered=r);
  let holdFirst=true;
  const holdMetadata=async route=>{if(route.request().method()!=='GET'||!holdFirst)return route.continue();
   holdFirst=false;const response=await route.fetch();metaEntered();await gate;await route.fulfill({response}).catch(()=>{});};
  await page.route('**/api/jobs/'+job+'/detections',holdMetadata);
  await page.locator('#det2 img').click();await Promise.race([started,new Promise((_,reject)=>setTimeout(()=>reject(Error('metadata request not observed')),10000))]);
  await page.evaluate(id=>openJob(id),jobB);await page.waitForFunction(id=>CUR===id&&!!document.getElementById('review'),jobB);
  await page.evaluate(id=>openJob(id),job);await page.waitForFunction(id=>CUR===id&&!!document.getElementById('review'),job);
  await page.locator('#detwrap').scrollIntoViewIfNeeded();
  await page.waitForFunction(()=>document.querySelector('#det2 img')?.naturalWidth>0);
  await page.evaluate(()=>{window.revisitedRoot=document.getElementById('review');window.revisitedSrc=document.querySelector('#det2 img').src;});
  releaseMeta();await page.unroute('**/api/jobs/'+job+'/detections',holdMetadata);
  assert.equal(await page.evaluate(()=>document.getElementById('review')===revisitedRoot&&document.querySelector('#det2 img').src===revisitedSrc),true);
  assert.equal(await page.locator('#lb').count(),0);
  // A failed recovery spends the review's budget once; only explicit
  // reopening creates a new budget and retrieves the latest preview.
  assert.equal((await context.request.post(base+'api/jobs/'+job+'/detections',{data:{audio:[{t0:.1,t1:.46,mode:'mute'},{t0:.5,t1:.8,mode:'bleep'}]}})).status(),200);
  let metadataCalls=0;
  const unavailable=route=>{metadataCalls++;return route.fulfill({status:503,contentType:'application/json',body:'{}'});};
  await page.route('**/api/jobs/'+job+'/detections',unavailable);
  const failureStart=requests.length;
  await page.locator('#det2 img').click();
  await page.waitForSelector('#det2 [data-thumb-reopen]:visible');
  await page.locator('#lb').click();
  await page.locator('#det2 img').click();
  await page.waitForSelector('#det2 [data-thumb-reopen]:visible');
  await page.locator('#lb').click();
  assert.equal(metadataCalls,1);
  assert.equal(requests.slice(failureStart).filter(r=>r.method==='POST'||r.url.includes('/edit_sample')).length,0);
  await page.unroute('**/api/jobs/'+job+'/detections',unavailable);
  await page.locator('#det2 [data-thumb-reopen]').click();
  await page.waitForFunction(()=>document.getElementById('review')!==revisitedRoot && document.querySelector('#det2 img')?.naturalWidth>0);
  await page.setViewportSize({width:390,height:844});
  await page.locator('#detwrap').scrollIntoViewIfNeeded();
  await page.screenshot({path:path.join(artifacts,'review-small.png')});
  assert.deepEqual(errors,[]);
  assert.deepEqual(warnings.filter(m=>!/Failed to load resource: (the server responded with a status of (409|503)|net::ERR_FAILED)/.test(m)),[]);
  console.log(JSON.stringify({url:page.url(),title:await page.title(),oldStatus:obsolete.status(),pixelChanged:true,
   placeholderAndReopen:true,audioRecovery:true,heldLostAckAndReopen:true,lateABA:true,persistentFailure:true,pageErrors:errors,consoleMessages:warnings,
   screenshots:['review-desktop.png','review-unavailable.png','review-small.png']}));
  for(const kind of ['panel','job','replacement'])await lightboxTeardown(context,kind);
  await context.close();
 } finally {await browser.close();}
})().catch(e => {console.error(e);process.exitCode=1;});
