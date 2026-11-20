const {chromium}=require(process.env.OPENSCRUB_PLAYWRIGHT_MODULE);
const fs=require('node:fs'),assert=require('node:assert/strict');
const [url,root,mode,previous,reopenJob]=process.argv.slice(2),oracles=JSON.parse(fs.readFileSync(root+'/runtime/media-oracles.json'));
(async()=>{const browser=await chromium.launch({headless:true,executablePath:process.env.OPENSCRUB_CHROMIUM});
try{
if(mode==='reopen'){
 const context=await browser.newContext({viewport:{width:1100,height:950},deviceScaleFactor:2});
 try{const page=await context.newPage(),errors=[],warnings=[],writes=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(['error','warning'].includes(m.type()))warnings.push(m.text())});
  page.on('request',r=>{if(r.method()==='POST'&&/detections|render/.test(r.url()))writes.push(r.url())});
  const saved=JSON.parse(fs.readFileSync(previous+'/saved-report.json'));
  await page.goto(url);assert.equal(await page.title(),'OpenScrub');
  await page.getByRole('link',{name:reopenJob==='resize'?'synthetic-resize.mp4':'exact-cfr24.mp4',exact:true}).click();
  await page.getByRole('button',{name:/Preview video & edit boxes/}).click();await page.waitForFunction(()=>beReady());
  await page.locator('#beT').fill('0.2');await page.locator('#beT').dispatchEvent('input');await page.waitForFunction(()=>beReady()&&BE_VIEW.readySample.sample.requested_s===.2);
  const actual=await(await page.request.get(url+'/api/jobs/'+reopenJob+'/report')).json();assert.deepEqual(actual,saved);
  const displayed=await page.evaluate(()=>({raw:BE.raw,audio:BE.audio,choices:EN,sample:BE_VIEW.readySample.sample}));
  assert.deepEqual(displayed.raw.find(r=>r.i===0).base.cbox,saved.detections[0].cbox);
  assert.deepEqual(displayed.raw.find(r=>r.i===0).base.span.slice(0,2),[saved.detections[0].t_start,saved.detections[0].t_end]);
  assert.equal(displayed.choices[1],saved.detections[1].enabled);
  assert.deepEqual(displayed.audio,saved.audio_redactions);assert(saved.detections.some(r=>r.manual_id));
  await page.screenshot({path:root+'/fresh-process.png',fullPage:true});
  fs.writeFileSync(root+'/fresh-process.json',JSON.stringify({job:reopenJob,actual,displayed,errors,warnings,writes},null,2));
  assert.deepEqual(errors,[]);assert.deepEqual(warnings,[]);assert.deepEqual(writes,[]);
  console.log('FRESH_PROCESS_PAGE_PERSISTENCE_OK',reopenJob);
 }finally{await context.close()}
 return;
}
for(const dpr of [1,2]){const context=await browser.newContext({viewport:{width:1100,height:950},deviceScaleFactor:dpr});
try{let page;try{page=await context.newPage();}catch(e){throw e;}const errors=[],warnings=[],expectedConsole=[],posts=[],samples=[],thumbnailConflicts=[];
page.on('response',r=>{if(r.status()===409&&/\/(thumb|detframe)\/\d+\?v=/.test(r.url()))
 thumbnailConflicts.push(r.json().then(body=>({url:r.url(),error:body.error})).catch(()=>({url:r.url(),error:null})));});
page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(['warning','error'].includes(m.type())){if(m.location().url.endsWith('/api/jobs/cfr24/render')&&m.text().includes('409'))expectedConsole.push({text:m.text(),url:m.location().url});else warnings.push({text:m.text(),url:m.location().url})}});
page.on('request',r=>{if(r.method()==='POST')posts.push({url:r.url(),body:r.postDataJSON()});if(r.url().includes('/edit_sample?'))samples.push(r.url())});
page.on('response',async r=>{if(r.url().includes('/edit_sample?')){try{const b=await r.json();if(b.image)b.image={mime:b.image.mime,prefix:b.image.base64.slice(0,24),length:b.image.base64.length};fs.writeFileSync(root+`/wire-${dpr}.json`,JSON.stringify(b,null,2))}catch(_){}}});
page.on('dialog',d=>d.accept(d.defaultValue()));
await page.addInitScript(()=>{
 const decode=HTMLImageElement.prototype.decode;
 HTMLImageElement.prototype.decode=async function(){if(window.holdDecode&&!this.isConnected){window.decodeStarted=true;await new Promise(r=>window.releaseDecode=r)}return decode.call(this)};
 const create=URL.createObjectURL,revoke=URL.revokeObjectURL;window.liveSampleURLs=new Set();window.maximumSampleURLs=0;window.sampleURLCreations=0;
 // Thumbnail scheduling has its own blob URLs. Attribute only URLs created by
 // the exact-sample pipeline so the two independent owners can coexist here.
 URL.createObjectURL=function(...args){const u=create.apply(this,args);
  if(/\bbeApplySample\b/.test(new Error().stack)){sampleURLCreations++;liveSampleURLs.add(u);maximumSampleURLs=Math.max(maximumSampleURLs,liveSampleURLs.size)}return u};
 URL.revokeObjectURL=function(u){liveSampleURLs.delete(u);return revoke.call(this,u)};
});
await page.goto(url);assert.equal(await page.title(),'OpenScrub');assert((await page.locator('body').innerText()).includes('OpenScrub'));
assert.equal(await page.locator('vite-error-overlay,nextjs-portal').count(),0);
async function open(label){await page.getByRole('link',{name:'exact-'+label+'.mp4',exact:true}).click();await page.getByRole('button',{name:/Preview video & edit boxes/}).click();await page.waitForFunction(()=>beReady()).catch(async e=>{console.log('PAGE_FAILURE_STATE',JSON.stringify(await page.evaluate(()=>({label:document.getElementById('beL')?.textContent,ready:BE_VIEW?.readySample,transform:BE_VIEW?.transform&&{sw:BE_VIEW.transform.sw,width:BE_VIEW.transform.width},loading:BE_VIEW?.loading,image:{src:BE_VIEW?.img.src,width:BE_VIEW?.img.naturalWidth,height:BE_VIEW?.img.naturalHeight,complete:BE_VIEW?.img.complete},raw:BE.raw,active:!!EDIT_SAMPLE_IO.active,wanted:!!EDIT_SAMPLE_IO.wanted}))));throw e});await page.evaluate(()=>stopPolling())}
async function scrub(t){await page.locator('#beT').fill(String(t));await page.locator('#beT').dispatchEvent('input');await page.waitForFunction(t=>beReady()&&BE_VIEW.readySample.sample.requested_s===t,t)}
async function point(x,y){return page.locator('#beCv').evaluate((cv,[x,y])=>{const r=cv.getBoundingClientRect(),im=document.getElementById('beImg');return {x:r.x+x*r.width/im.naturalWidth,y:r.y+y*r.height/im.naturalHeight}},[x,y])}
async function click(x,y){const p=await point(x,y);await page.mouse.click(p.x,p.y)}
const result={dpr,media:[],coalescing:{}};
for(const [label,t,index] of [['cfr24',.2,4],['cfr5',1.9,9],['normalized',.5,6]]){
 await open(label);await scrub(t);
 const got=await page.evaluate(()=>{const ready=BE_VIEW.readySample,im=BE_VIEW.img;
  const cv=document.createElement('canvas');cv.width=im.naturalWidth;cv.height=im.naturalHeight;
  const g=cv.getContext('2d',{willReadFrequently:true});g.drawImage(im,0,0);const p=g.getImageData(0,0,cv.width,cv.height).data;
  let marker=0;for(let k=0;k<6;k++)marker|=(p[(14*cv.width+14+12*k)*4]>128)<<k;
  return {sample:ready.sample,marker,raw:BE.raw,boxes:BE.boxes,ready:beReady(),precondition:ready.precondition};});
 const oracle=oracles[label];assert.equal(got.sample.index,index);assert.equal(got.sample.canonical_s,oracle.canonical);
 assert.equal(got.sample.observed_s,Number(oracle.pts.split('/')[0])/(Number(oracle.pts.split('/')[1])||1));
 assert.equal(got.marker,oracle.marker);assert.deepEqual(got.sample.offset,[2*index,-index]);
 assert.deepEqual(got.boxes[0].box,oracle.source_box);assert.deepEqual(got.raw.slice(0,2).map(r=>r.i),[0,1]);assert.equal(got.raw[1].enabled,false);assert(!got.boxes.some(r=>r.i===1));
 assert.equal(Object.keys(got.precondition).length,8);result.media.push({label,t,oracle,got});
 await page.screenshot({path:root+`/exact-${dpr}-${label}.png`,fullPage:true});
}
await open('cfr24');await scrub(.2);
// Hold the HTTP body, replace desired requests across same-BE and A->B->A mounts.
let releaseBody,bodyStarted;const bodyGate=new Promise(r=>releaseBody=r),bodyStart=new Promise(r=>bodyStarted=r);
await page.route('**/api/jobs/cfr24/edit_sample?t=0.3',async route=>{const response=await route.fetch();bodyStarted();await bodyGate;await route.fulfill({response})});
await page.locator('#beT').fill('0.3');await page.locator('#beT').dispatchEvent('input');await bodyStart;
const before=samples.length;await page.evaluate(()=>{document.getElementById('beT').value=.4;beScrub();loadBoxEdit(1)});
await page.waitForFunction(()=>BE_VIEW?.readySample===null);assert.equal(await page.evaluate(()=>beReady()),false);
await page.getByRole('link',{name:'exact-cfr5.mp4',exact:true}).click();await page.getByRole('button',{name:/Preview video & edit boxes/}).click();
await page.getByRole('link',{name:'exact-cfr24.mp4',exact:true}).click();await page.getByRole('button',{name:/Preview video & edit boxes/}).click();
await page.waitForFunction(()=>CUR==='cfr24'&&BE_VIEW);await page.locator('#beT').fill('0.2');await page.locator('#beT').dispatchEvent('input');
assert.equal(samples.length,before,'a held body must retain the global slot');releaseBody();await page.waitForFunction(()=>beReady()&&BE_VIEW.readySample.sample.requested_s===.2);
await page.unroute('**/api/jobs/cfr24/edit_sample?t=0.3');result.coalescing.body=true;
// Detached decode holds the same slot; only the latest desired time is issued.
await page.evaluate(()=>{holdDecode=true;decodeStarted=false});await page.locator('#beT').fill('0.5');await page.locator('#beT').dispatchEvent('input');await page.waitForFunction(()=>decodeStarted);
const decodeBefore=samples.length;await page.locator('#beT').fill('0.6');await page.locator('#beT').dispatchEvent('input');await page.locator('#beT').fill('0.7');await page.locator('#beT').dispatchEvent('input');
assert.equal(samples.length,decodeBefore);assert.equal(await page.evaluate(()=>beReady()),false);
await page.evaluate(()=>{holdDecode=false;releaseDecode()});await page.waitForFunction(()=>beReady()&&BE_VIEW.readySample.sample.requested_s===.7);
assert.equal(samples.length,decodeBefore+1);assert(await page.evaluate(()=>sampleURLCreations>0&&maximumSampleURLs<=2));result.coalescing.decode=true;
await scrub(.2);await page.evaluate(()=>{BE.win=[1,1.5]});const rejectedPosts=posts.length;
await page.locator('#beTrk').click();await click(10,20);await click(45,60);assert.equal(posts.length,rejectedPosts);assert.deepEqual(await page.evaluate(()=>BE.win),[1,1.5]);
await page.evaluate(()=>BE.win=[0,BE.dur]);
// Actual Add creation uses canonical frame evidence and a stable immutable ID.
await page.locator('#beAdd').click();await click(95,35);await click(130,75);await page.locator('#beAdd').click();
const addition=await page.evaluate(()=>BE.adds[0]);assert.equal(addition.tref,4/24);assert.equal(Object.keys(addition.sample_precondition).length,8);assert(addition.manual_id);
// Real strict Track append; hold its actual status response while reopening.
let statusStarted,releaseStatus;const statusStart=new Promise(r=>statusStarted=r),statusGate=new Promise(r=>releaseStatus=r);let gated=true;
await page.route('**/api/jobs/cfr24/track_status',async route=>{const response=await route.fetch();if(gated){gated=false;statusStarted();await statusGate}await route.fulfill({response})});
await page.locator('#beTrk').click();await click(10,20);await click(45,60);await statusStart;
const launch=posts.findLast(p=>p.url.endsWith('/track_object'));assert.equal(launch.body.t_ref,4/24);assert.equal(launch.body.seed.index,4);assert.equal(Object.keys(launch.body.seed).length,8);
await page.evaluate(()=>{window.retiredTrackView=BE_VIEW;loadBoxEdit(1)});await page.waitForFunction(()=>BE_VIEW!==retiredTrackView&&beReady());
const ownedSerial=await page.evaluate(()=>BE_VIEW.serial);releaseStatus();
await page.waitForFunction(()=>document.getElementById('reviewTrackStatus')?.textContent.includes('Tracked 1 position'));
assert.equal(await page.evaluate(()=>BE_VIEW.serial),ownedSerial);
assert.equal(await page.evaluate(()=>BE.adds[0].manual_id),addition.manual_id);await page.unroute('**/api/jobs/cfr24/track_status');result.staleTrackInert=true;
// Detached completion is visible outside the old editor; review it deliberately.
await page.getByRole('button',{name:'Review tracked positions',exact:true}).click();
await page.waitForFunction(()=>REVIEW_SCHED?.owns()&&!EDITS.track);
assert((await page.locator('#review').innerText()).includes('tracked object'));
assert.equal(await page.evaluate(()=>BE.adds[0].manual_id),addition.manual_id);
await page.getByRole('button',{name:/Preview video & edit boxes/}).click();await page.waitForFunction(()=>beReady());
result.detachedTrackReview=true;
// Owned success refreshes review and obtains a new inspected exact sample.
await scrub(.2);await page.evaluate(()=>window.ownedTrackView=BE_VIEW);await page.locator('#beTrk').click();await click(50,20);await click(85,60);
await page.waitForFunction(()=>BE_VIEW!==ownedTrackView&&beReady());assert((await page.locator('#review').innerText()).includes('tracked object'));result.ownedTrackRefresh=true;
if(dpr===2){
 // Move the ordinary row through shipped pointer handlers, then lose the real
 // committed ACK. A newer opposite-kind edit survives identical retry first.
 await scrub(.2);const box=await page.evaluate(()=>BE.boxes.find(b=>b.i===0).box);
 await click(box[2]-1,box[3]-1);assert.equal(await page.evaluate(()=>BE.sel),0);
 const a=await point(box[2]-1,box[3]-1);await page.mouse.move(a.x,a.y);await page.mouse.down();await page.mouse.move(a.x+3,a.y+2);await page.mouse.up();
 let first=true,committedPayload,committedACK;
 await page.route('**/api/jobs/cfr24/detections',async route=>{
  if(route.request().method()!=='POST')return route.continue();
  const sent=route.request().postDataJSON();const response=await route.fetch();
  if(first){first=false;committedPayload=sent;committedACK=await response.json();await route.fulfill({status:200,contentType:'text/plain',body:'lost committed acknowledgement'});}
  else await route.fulfill({response});
 });
 await page.evaluate(()=>{applyDet(1,true);BE.audioLoaded=true;BE.audio.push({t0:0,t1:.1,mode:'mute'})});
 await page.getByRole('button',{name:'Save changes & re-render',exact:true}).click();await page.waitForFunction(()=>EDITS.submitted?.everUncertain&&!EDITS.busy);
 assert(committedACK.ok);assert(committedPayload.geometry_preconditions['0']);assert.equal(committedPayload.manual[0].manual_id,addition.manual_id);assert(committedPayload.manual[0].sample_precondition);
 await page.locator('#beT0').fill('0.1');await page.locator('#beT1').fill('1');await page.getByRole('button',{name:'Apply times',exact:true}).click();
 await page.getByRole('button',{name:'Save changes & re-render',exact:true}).click();await page.waitForFunction(()=>!EDITS.submitted&&!EDITS.busy&&!!BE.times[0]);
 const saves=posts.filter(p=>p.url.endsWith('/detections'));assert.deepEqual(saves.at(-1).body,committedPayload);
 assert.deepEqual(await page.evaluate(()=>BE.geometry[0].precondition.base),committedACK.geometry_rows['0'].base);
 assert.equal(await page.evaluate(()=>BE.adds.length),0);
 // Refuse render only after the final save commits; saved rows stay real and
 // the next explicit Save must not append the manual box again.
 await page.route('**/api/jobs/cfr24/render',route=>route.fulfill({status:409,json:{error:'synthetic_render_refusal'}}));
 await page.getByRole('button',{name:'Save changes & re-render',exact:true}).click();await page.waitForFunction(()=>!EDITS.busy&&EDITS.status.includes('render was not confirmed'));
 const saved=await(await page.request.get(url+'/api/jobs/cfr24/report')).json();fs.writeFileSync(root+'/saved-report.json',JSON.stringify(saved,null,2));assert.equal(saved.detections.filter(r=>r.manual_id===addition.manual_id).length,1);
 assert.deepEqual(saved.detections[0].t_start,.1);assert.equal(saved.detections[1].enabled,true);assert.deepEqual(saved.detections[1].opaque,{kept:[1,2,3]});assert.equal(saved.audio_redactions.length,1);
 result.persistence={committedPayload,committedACK,saved,identicalRetry:true};
 fs.writeFileSync(root+`/exact-results-${dpr}.json`,JSON.stringify(result,null,2));
 await page.reload();await page.getByRole('link',{name:'exact-cfr24.mp4',exact:true}).click();await page.getByRole('button',{name:/Preview video & edit boxes/}).click();await page.waitForFunction(()=>beReady());await scrub(.2);
 assert.deepEqual(await page.evaluate(()=>BE.raw.find(r=>r.i===0).base.span.slice(0,2)),[.1,1]);assert.equal(await page.evaluate(()=>BE.audio.length),1);
}
await page.screenshot({path:root+`/exact-${dpr}-final.png`,fullPage:true});
const conflicts=await Promise.all(thumbnailConflicts);
const unexpected=warnings.filter(w=>!w.text.includes('409')||!conflicts.some(c=>c.url===w.url&&c.error==='thumbnail_obsolete'));
result.errors=errors;result.warnings=warnings;result.thumbnailConflicts=conflicts;result.expectedConsole=expectedConsole;result.posts=posts;result.samples=samples;
fs.writeFileSync(root+`/exact-results-${dpr}.json`,JSON.stringify(result,null,2));assert.deepEqual(errors,[]);assert.deepEqual(unexpected,[],JSON.stringify({warnings,conflicts}));
console.log(JSON.stringify({dpr,media:result.media.map(x=>({label:x.label,index:x.got.sample.index,marker:x.got.marker})),coalescing:result.coalescing,staleTrackInert:true,ownedTrackRefresh:true,persistence:!!result.persistence}));
}finally{await context.close()}}}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
