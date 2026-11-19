const assert=require('node:assert/strict');
const path=require('node:path');
const {chromium}=require(process.env.OPENSCRUB_PLAYWRIGHT_MODULE);
const base=process.env.OPENSCRUB_PAGE_URL,job=process.env.OPENSCRUB_PAGE_JOB,jobB=process.env.OPENSCRUB_PAGE_JOB_B;
const artifacts=process.env.OPENSCRUB_BROWSER_ARTIFACTS;
async function pendingDomScenario(context,order){
 const page=await context.newPage(),errors=[],requests=[],consoleMessages=[];
 page.on('console',m=>{if(['error','warning'].includes(m.type()))consoleMessages.push(m.text());});
 page.on('pageerror',e=>errors.push(e.message));
 page.on('request',r=>requests.push({url:r.url(),method:r.method()}));
 let releaseMeta=()=>{},releaseImage=()=>{};
 try{
  await page.goto(base);assert.equal(await page.title(),'OpenScrub');
  await page.evaluate(id=>openJob(id),job);await page.waitForSelector('#thumb2');
  await page.waitForFunction(()=>[0,2].every(i=>document.getElementById('thumb'+i)?.naturalWidth>0));
  await page.evaluate(()=>{
   const slot=document.getElementById('beslot');slot.innerHTML='<div id="dom-editor-proof">editor</div>';
   BE.sel=7;BE.playing=true;BE.audio=[{t0:.1,t1:.2,mode:'mute'}];BE.audioSaved=[];BE.audioLoaded=true;
   BE.ov[2]=[1,2,12,13];EDITS.audioInFlight=true;EDITS.enabled[2]=false;MAN.push({manual_id:'dom-draft'});
   window.domRefs={root:document.getElementById('review'),editor:BE,editorNode:document.getElementById('dom-editor-proof'),
    draft:EDITS,drafts:REVIEW_DRAFTS,en:EN,manual:MAN,audio:BE.audio,saved:BE.audioSaved};
  });
  const published=await context.request.post(base+'api/jobs/'+job+'/detections',
   {data:{audio:[{t0:.1,t1:.4,mode:'mute'},{t0:.5,t1:.8,mode:'bleep'}]}});
  assert.equal(published.status(),200);
  let metadataSeen,metadataDone,imageSeen;
  const metaStarted=new Promise(r=>metadataSeen=r),metaFinished=new Promise(r=>metadataDone=r);
  const metaGate=new Promise(r=>releaseMeta=r),imageStarted=new Promise(r=>imageSeen=r),imageGate=new Promise(r=>releaseImage=r);
  let metadataCalls=0;
  const holdMetadata=async route=>{if(route.request().method()!=='GET')return route.continue();
   metadataCalls++;const response=await route.fetch();assert.equal(response.status(),200);
   metadataSeen();await metaGate;await route.fulfill({response});metadataDone();};
  const holdImage=async route=>{const response=await route.fetch();assert.equal(response.status(),409);
   imageSeen();if(order==='after')await imageGate;await route.fulfill({response});};
  await page.route('**/api/jobs/'+job+'/detections',holdMetadata);
  await page.route('**/api/jobs/'+job+'/detframe/2?*',holdImage);
  const requestStart=requests.length;
  await page.locator('#thumb0').click();
  await Promise.race([metaStarted,new Promise((_,reject)=>setTimeout(()=>reject(Error('pending metadata not observed')),10000))]);
  await page.evaluate(()=>{
   const owner=REVIEW_IMAGES,old=owner.lightbox;
   window.domOld={light:old,node:old.node,src:old.node.src,callback:old.node.onerror};
   old.overlay.remove();zoomDet(2);
   const img=document.getElementById('thumb0'),replacement=img.cloneNode(false);
   replacement.removeAttribute('onerror');replacement.removeAttribute('onclick');
   replacement.src='data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==';
   replacement.style.visibility='visible';img.replaceWith(replacement);
   window.domOld.card=img;window.domReplacement={light:owner.lightbox,node:owner.lightbox.node,
    src:owner.lightbox.node.src,card:replacement,cardSrc:replacement.src,cardVisibility:replacement.style.visibility};
  });
  await Promise.race([imageStarted,new Promise((_,reject)=>setTimeout(()=>reject(Error('replacement image request not observed')),10000))]);
  if(order==='before')await page.waitForFunction(()=>domReplacement.node.style.visibility==='hidden');
  releaseMeta();await metaFinished;await page.evaluate(()=>REVIEW_IMAGES.refresh);
  await page.waitForFunction(()=>{
   const card=REVIEW_IMAGES.bindings.get(2);return card.version!==domReplacement.light.version&&
    card.node.complete&&card.node.naturalWidth>0&&getComputedStyle(card.node).visibility!=='hidden';
  });
  if(order==='after'){releaseImage();await page.waitForFunction(()=>domReplacement.node.style.visibility==='hidden');}
  await page.evaluate(()=>domOld.callback());
  assert.equal(await page.evaluate(()=>{
   const r=domRefs,n=domReplacement,old=domOld;
   return !old.node.isConnected&&!old.card.isConnected&&n.node.isConnected&&n.node.src===n.src&&
    n.node.style.visibility==='hidden'&&n.card.isConnected&&n.card.src===n.cardSrc&&
    n.card.style.visibility===n.cardVisibility&&document.getElementById('review')===r.root&&
    document.getElementById('dom-editor-proof')===r.editorNode&&BE===r.editor&&EDITS===r.draft&&
    REVIEW_DRAFTS===r.drafts&&EN===r.en&&MAN===r.manual&&BE.audio===r.audio&&BE.audioSaved===r.saved&&
    BE.audioLoaded&&EDITS.audioInFlight&&BE.sel===7&&BE.playing&&BE.ov[2][0]===1&&
    EDITS.enabled[2]===false&&MAN[0].manual_id==='dom-draft'&&
    !document.querySelector('#det2 [data-thumb-status]').hidden&&
    !document.querySelector('#det2 [data-thumb-reopen]').hidden;
  }),true);
  assert.equal(metadataCalls,1);
  assert.equal(requests.slice(requestStart).filter(r=>r.method==='POST'||r.url.includes('/render')||r.url.includes('/edit_sample')).length,0);
  assert.deepEqual(errors,[]);
  assert.deepEqual(consoleMessages.filter(m=>!/Failed to load resource: (the server responded with a status of (409|503)|net::ERR_FAILED)/.test(m)),[]);
  return {order,consoleMessages,metadataCalls,oldDetached:true,replacementIntact:true,draftsIntact:true};
 }finally{releaseMeta();releaseImage();await page.close();}
}
async function reviewFixScenario(context){
 const page=await context.newPage(),errors=[],consoleMessages=[],requests=[];
 page.on('pageerror',e=>errors.push(e.message));
 page.on('console',m=>{if(['error','warning'].includes(m.type()))consoleMessages.push(m.text());});
 page.on('request',r=>requests.push({url:r.url(),method:r.method()}));
 try{
  await page.goto(base);assert.equal(await page.title(),'OpenScrub');
  await page.evaluate(id=>openJob(id),job);await page.waitForSelector('#thumb2');
  await page.waitForFunction(()=>[0,2].every(i=>document.getElementById('thumb'+i)?.naturalWidth>0));
  await page.evaluate(()=>{window.fixOriginalLoadReview=loadReview;loadReview=function(){window.fixMount=window.fixOriginalLoadReview();return window.fixMount;};
   BE.ov[2]=[2,3,14,15];BE.audio=[{t0:.1,t1:.2,mode:'mute'}];BE.audioSaved=null;BE.audioLoaded=true;
   EDITS.audioInFlight=true;MAN.push({manual_id:'fix1-pending'});
   window.fixRefs={owner:REVIEW_IMAGES,root:document.getElementById('review'),groups:TRKMEM,
    editor:BE,draft:EDITS,manual:MAN,audio:BE.audio};});
  const unavailable=route=>route.fulfill({status:503,contentType:'application/json',body:'{}'});
  await page.route('**/api/jobs/'+job+'/detections',unavailable);
  await page.evaluate(()=>{document.getElementById('thumb0').onerror();return REVIEW_IMAGES.refresh;});
  await page.unroute('**/api/jobs/'+job+'/detections',unavailable);
  await page.waitForSelector('#det0 [data-thumb-reopen]:visible');
  for(const kind of ['network','409','503']){
   const failed=route=>kind==='network'?route.abort('failed'):route.fulfill({status:+kind,contentType:'application/json',body:'{"error":"pending"}'});
   await page.route('**/api/jobs/'+job+'/detections',failed);
   await page.locator('#det0 [data-thumb-reopen]').click();await page.evaluate(()=>window.fixMount);
   await page.unroute('**/api/jobs/'+job+'/detections',failed);
   assert.equal(await page.evaluate(()=>REVIEW_IMAGES===fixRefs.owner&&document.getElementById('review')===fixRefs.root&&
    TRKMEM===fixRefs.groups&&BE===fixRefs.editor&&EDITS===fixRefs.draft&&MAN===fixRefs.manual&&BE.audio===fixRefs.audio&&
    BE.audioSaved===null&&EDITS.audioInFlight&&MAN[0].manual_id==='fix1-pending'&&BE.ov[2][0]===2),true);
  }
  await page.locator('#bb0').click();assert.equal(await page.evaluate(()=>EN[0]===false&&EN[1]===false),true);
  await page.locator('#det0 [data-thumb-reopen]').click();await page.evaluate(()=>window.fixMount);
  assert.equal(await page.evaluate(()=>REVIEW_IMAGES!==fixRefs.owner&&!REVIEW_IMAGES.attempted),true);
  // Saved V1 card and lightbox callbacks must not affect their V2 nodes.
  await page.evaluate(()=>zoomDet(2));await page.waitForFunction(()=>document.querySelector('#lb img')?.naturalWidth>0);
  await page.evaluate(()=>{window.oldCardError=document.getElementById('thumb2').onerror;
   window.oldLightError=REVIEW_IMAGES.lightbox.node.onerror;});
  assert.equal((await context.request.post(base+'api/jobs/'+job+'/detections',{data:{audio:[{t0:.1,t1:.4,mode:'mute'},{t0:.5,t1:.8,mode:'bleep'}]}})).status(),200);
  const count=requests.length;await page.evaluate(()=>{oldLightError();return REVIEW_IMAGES.refresh;});
  await page.waitForFunction(()=>{const light=REVIEW_IMAGES.lightbox;return light&&light.node.complete&&light.node.naturalWidth>0&&
   getComputedStyle(light.node).visibility!=='hidden'&&getComputedStyle(document.getElementById('thumb2')).visibility!=='hidden';});
  await page.evaluate(()=>{oldCardError();oldLightError();});
  assert.equal(await page.evaluate(()=>getComputedStyle(document.getElementById('thumb2')).visibility==='visible'&&
   getComputedStyle(REVIEW_IMAGES.lightbox.node).visibility==='visible'&&document.querySelector('#det2 [data-thumb-reopen]').hidden),true);
  assert.equal(requests.slice(count).filter(r=>r.url.endsWith('/detections')).length,1);
  await page.locator('#lb').click();
  // A held card image load must not clear a subsequently closed failed lightbox.
  await page.evaluate(()=>window.fixOriginalLoadReview());
  await page.waitForFunction(()=>[0,2].every(i=>document.getElementById('thumb'+i)?.naturalWidth>0));
  assert.equal((await context.request.post(base+'api/jobs/'+job+'/detections',{data:{audio:[{t0:.1,t1:.4,mode:'mute'},{t0:.5,t1:.8,mode:'bleep'}]}})).status(),200);
  let cardSeen,releaseCard;const cardStarted=new Promise(r=>cardSeen=r),cardGate=new Promise(r=>releaseCard=r);
  const holdCard=async route=>{const response=await route.fetch();assert.equal(response.status(),200);cardSeen();await cardGate;await route.fulfill({response});};
  const badLight=route=>route.fulfill({status:503,contentType:'application/json',body:'{}'});
  await page.route('**/api/jobs/'+job+'/thumb/2?*',holdCard);await page.route('**/api/jobs/'+job+'/detframe/2?*',badLight);
  await page.evaluate(()=>{document.getElementById('thumb0').onerror();return REVIEW_IMAGES.refresh;});
  await Promise.race([cardStarted,new Promise((_,reject)=>setTimeout(()=>reject(Error('card load not observed')),10000))]);
  await page.evaluate(()=>zoomDet(2));await page.waitForSelector('#det2 [data-thumb-reopen]:visible');
  await page.locator('#lb').click();releaseCard();
  await page.waitForFunction(()=>{const n=document.getElementById('thumb2');return n.complete&&n.naturalWidth>0&&getComputedStyle(n).visibility==='visible';});
  assert.equal(await page.locator('#det2 [data-thumb-reopen]').isVisible(),true);
  await page.unroute('**/api/jobs/'+job+'/thumb/2?*',holdCard);await page.unroute('**/api/jobs/'+job+'/detframe/2?*',badLight);
  await page.evaluate(()=>zoomDet(2));await page.waitForFunction(()=>document.querySelector('#lb img')?.naturalWidth>0&&document.querySelector('#det2 [data-thumb-reopen]').hidden);
  await page.locator('#lb').click();
  // A retired owner must stop before JSON/index work, on panel or job exit.
  await page.evaluate(()=>{window.fixRealFetch=fetch;window.staleParsed=0;fetch=async(...args)=>{
   const r=await window.fixRealFetch(...args);if(args[1]&&args[1].cache==='no-store'){const read=r.json.bind(r);r.json=()=>{window.staleParsed++;return read();};}return r;};});
  for(const kind of ['panel','job']){
   await page.evaluate(()=>window.fixOriginalLoadReview());
   await page.waitForFunction(()=>[0,2].every(i=>document.getElementById('thumb'+i)?.naturalWidth>0));
   assert.equal((await context.request.post(base+'api/jobs/'+job+'/detections',{data:{audio:[{t0:.1,t1:.4,mode:'mute'},{t0:.5,t1:.8,mode:'bleep'}]}})).status(),200);
   let seen,release;const started=new Promise(r=>seen=r),gate=new Promise(r=>release=r);
   const held=async route=>{const response=await route.fetch();seen();await gate;await route.fulfill({response});};
   await page.route('**/api/jobs/'+job+'/detections',held);
   await page.evaluate(()=>{window.staleParsed=0;window.retiredOwner=REVIEW_IMAGES;window.retiredVersion=retiredOwner.version;document.getElementById('thumb0').onerror();});
   await Promise.race([started,new Promise((_,reject)=>setTimeout(()=>reject(Error('stale metadata not observed')),10000))]);
   if(kind==='panel')await page.evaluate(()=>showPanel('compare'));
   else await page.evaluate(id=>{refresh=()=>{};openJob(id);},jobB);
   assert.equal(await page.evaluate(()=>REVIEW_IMAGES===null),true);release();
   await page.evaluate(()=>window.retiredOwner.refresh);await page.unroute('**/api/jobs/'+job+'/detections',held);
   assert.equal(await page.evaluate(()=>REVIEW_IMAGES===null&&staleParsed===0&&retiredOwner.version===retiredVersion),true);
  }
  assert.equal(requests.filter(r=>r.method==='POST'||r.url.includes('/render')||r.url.includes('/edit_sample')).length,0);
  assert.deepEqual(errors,[]);
  assert.deepEqual(consoleMessages.filter(m=>!/Failed to load resource: (the server responded with a status of (409|503)|net::ERR_FAILED)/.test(m)),[]);
  return {reopenFailures:['network',409,503],staleCallbacks:true,closedLightboxLatch:true,teardown:['panel','job'],consoleMessages};
 }finally{await page.close();}
}
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
  await page.evaluate(()=>{window.delayedRefresh=REVIEW_IMAGES.refresh;});
  await page.evaluate(id=>openJob(id),jobB);await page.waitForFunction(id=>CUR===id&&document.getElementById('thumb0'),jobB);
  await page.evaluate(id=>openJob(id),job);await page.waitForFunction(id=>CUR===id&&document.getElementById('thumb2'),job);
  await page.evaluate(()=>{window.revisitedRoot=document.getElementById('review');window.revisitedSrc=document.getElementById('thumb2').src;});
  releaseMeta();await page.evaluate(()=>window.delayedRefresh);await page.unroute('**/api/jobs/'+job+'/detections',holdMetadata);
  assert.equal(await page.evaluate(()=>document.getElementById('review')===revisitedRoot&&document.getElementById('thumb2').src===revisitedSrc),true);
  if(await page.locator('#lb').count())await page.locator('#lb').click();
  await page.waitForFunction(()=>{const n=document.getElementById('thumb2');return n&&n.complete&&n.naturalWidth>0&&getComputedStyle(n).visibility==='visible';});
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
  const pendingDom=[await pendingDomScenario(context,'before'),await pendingDomScenario(context,'after')];
  const fix1=await reviewFixScenario(context);
  console.log(JSON.stringify({url:page.url(),title:await page.title(),pendingDom,fix1,screenshots:['review-desktop.png','review-unavailable.png','review-small.png'],
   oldStatus:obsolete.status(),pixelChanged:true,recovery:true,pageErrors:errors,consoleMessages,rawRows:(await persisted.json()).detections.length,heldLostAckAndReopen:true,lateABA:true,persistentFailure:true}));
  await context.close();
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
