const fs=require('node:fs'),assert=require('node:assert/strict');
const ROOT='/home/tahv0/src/OpenScrub/.superpowers/sdd/README/runtime/task9';
process.env.TMPDIR=ROOT+'/tmp';process.env.PLAYWRIGHT_BROWSERS_PATH='/tmp/openscrub-save-as-20261116/browsers';
const{chromium}=require('/tmp/openscrub-save-as-20261116/node_modules/playwright');
const BASE='http://127.0.0.1:18509';let browser;const results=[],errors=[],warnings=[];
const check=(name,data)=>{results.push({name,...data});fs.writeFileSync(ROOT+'/evidence/browser-results.json',JSON.stringify({results,errors,warnings},null,2));console.log(name,JSON.stringify(data))};
(async()=>{browser=await chromium.launch({headless:true});
const context=await browser.newContext({viewport:{width:1365,height:950}});const page=await context.newPage();
page.on('pageerror',e=>errors.push(e.stack));page.on('console',e=>{if(['error','warning'].includes(e.type()))warnings.push(e.text())});
await context.addInitScript(()=>{
 window.qa={requests:[],active:0,maxActive:0,created:[],revoked:[],loads:[]};
 const f=window.fetch;window.fetch=async function(url,opts){
  const thumb=/\/thumb\/\d+/.test(String(url)),entry={url:String(url),method:opts?.method||'GET'};qa.requests.push(entry);
  if(!thumb)return f(url,opts);qa.active++;qa.maxActive=Math.max(qa.maxActive,qa.active);
  let done=false;const finish=()=>{if(!done){done=true;qa.active--;entry.settled=true;}};
  try{const r=await f(url,opts);entry.headers=true;const blob=r.blob.bind(r);r.blob=async()=>{try{return await blob()}finally{finish()}};return r;}
  catch(e){finish();throw e;}
 };
 const create=URL.createObjectURL.bind(URL),revoke=URL.revokeObjectURL.bind(URL);
 URL.createObjectURL=v=>{const u=create(v);qa.created.push(u);return u};URL.revokeObjectURL=u=>{qa.revoked.push(u);revoke(u)};
 document.addEventListener('load',e=>{if(e.target.matches?.('#detwrap img'))qa.loads.push(e.target.closest('.det').id)},true);
});
const control=body=>context.request.post(BASE+'/__qa__/control',{data:body}).then(r=>r.json());
const open=async id=>{await page.evaluate(id=>openJob(id),id);await page.waitForSelector('#review');};
const start=async()=>{await page.evaluate(()=>scrollTo(0,document.getElementById('detwrap').getBoundingClientRect().top+scrollY-55));await page.waitForTimeout(220)};
const facts=()=>page.evaluate(()=>({cards:document.querySelectorAll('#detwrap .det').length,images:document.querySelectorAll('#detwrap img').length,rows:document.querySelectorAll('.reviewrow').length,spacers:document.querySelectorAll('.reviewspacer').length,sections:document.querySelectorAll('.reviewgrid').length,
 normal:REVIEW_SCHED.normalIds.length,pins:document.querySelectorAll('[data-focus-pin="1"]').length,selected:[...selSet],flight:THUMB_FLIGHTS.size,queue:REVIEW_SCHED.queue.length,maxActive:qa.maxActive,active:qa.active,
 visible:[...REVIEW_SCHED.bindings.values()].filter(b=>{const r=b.card.getBoundingClientRect();return r.bottom>55&&r.top<innerHeight&&b.card.dataset.focusPin!=='1'}).map(b=>b.id),
 ids:[...REVIEW_SCHED.bindings.keys()],columns:REVIEW_SCHED.sections.map(s=>s.columns),range:document.querySelector('[data-review-range]').textContent,
 viewport:[innerWidth,innerHeight],zoom:document.body.style.zoom,scroll:scrollY,height:document.documentElement.scrollHeight,
 badGrid:[...document.querySelectorAll('.reviewrow')].filter(e=>getComputedStyle(e).gridTemplateColumns.split(' ').some(v=>parseFloat(v)<174)).length,
 unloaded:[...REVIEW_SCHED.bindings.values()].filter(b=>REVIEW_SCHED.eligible.get(b.id)?.rank===0&&!(b.img.complete&&b.img.naturalWidth>0)&&!b.img.parentElement.classList.contains('unavailable')).map(b=>b.id)}));
const settle=async()=>page.waitForFunction(()=>[...REVIEW_SCHED.bindings.values()].every(b=>REVIEW_SCHED.eligible.get(b.id)?.rank!==0||(b.img.complete&&b.img.naturalWidth>0)||b.img.parentElement.classList.contains('unavailable')));
const record=async name=>{await settle();const f=await facts();assert.ok(f.normal<=64);assert.ok(f.cards<=65);assert.ok(f.pins<=1);assert.ok(f.maxActive<=4);assert.equal(f.badGrid,0);check(name,f);return f};
await page.goto(BASE);assert.equal(await page.title(),'OpenScrub');assert.match(await page.locator('body').innerText(),/OpenScrub/);
await open('small');await start();await record('small-desktop');
assert.equal(await page.locator('details .det').count(),0);assert.equal(await page.locator('details img').count(),0);
await page.locator('[data-review-zones] summary').click();await page.waitForTimeout(250);await record('small-zones-open');
const zoneId=await page.locator('details .det').first().getAttribute('id');
await page.evaluate(id=>{selSet.add(+id.slice(3));document.getElementById(id).classList.add('selected')},zoneId);
await page.locator('[data-review-zones] summary').click();await page.waitForTimeout(250);
assert.equal(await page.locator('details .det').count(),0);assert.equal(await page.evaluate(()=>selSet.size),0);check('closed-zone-work',{cards:0,queue:await page.evaluate(()=>REVIEW_SCHED.queue.filter(x=>x.b.id>=18).length)});
// A handful of actual cold-route decodes, then all remaining layout uses cache hits.
await open('cold');await start();await record('cold-real-route');
await open('empty');await start();assert.equal(await page.locator('#detwrap .det').count(),0);check('empty',{range:await page.locator('[data-review-range]').innerText()});
await open('large');await start();await record('large-first');
// Native focus survives an ordinary scroll jump; only one subtree is pinned.
await page.locator('#detwrap .det button').first().focus();await page.evaluate(()=>window.focusBtn=document.activeElement);
await page.evaluate(()=>scrollTo(0,document.documentElement.scrollHeight));await page.waitForTimeout(450);await record('large-last-focus-pin');
assert.equal(await page.evaluate(()=>document.activeElement===focusBtn&&focusBtn.isConnected),true);
assert.ok((await facts()).ids.includes(1799));
await page.locator('[data-review-prev]').focus();await page.keyboard.press('Enter');await page.waitForTimeout(300);assert.equal(await page.evaluate(()=>document.activeElement.closest('.det')!==null),true);await record('native-previous-enter');
await page.locator('[data-review-next]').focus();await page.keyboard.press('Space');await page.waitForTimeout(300);assert.equal(await page.evaluate(()=>document.activeElement.closest('.det')!==null),true);await record('native-next-space');
await page.keyboard.press('Tab');assert.ok(await page.evaluate(()=>document.activeElement.tagName==='BUTTON'));check('native-tab',{active:await page.evaluate(()=>document.activeElement.id)});
// Jump both ways across categories, use the actual native grid at zoom widths.
for(const fraction of [.45,.8,.1,1,0]){
 await page.evaluate(f=>scrollTo(0,f?document.documentElement.scrollHeight*f:document.querySelector('#detwrap').getBoundingClientRect().top+scrollY-55),fraction);
 await page.waitForTimeout(220);await record('jump-'+fraction);
}
for(const zoom of ['1.25','2','1']){await page.evaluate(z=>document.body.style.zoom=z,zoom);await page.waitForTimeout(350);await record('desktop-zoom-'+zoom);}
await page.setViewportSize({width:390,height:844});await page.waitForTimeout(350);await record('390px-layout');await page.screenshot({path:ROOT+'/evidence/narrow.png'});
// Real touch input keeps scrolling rather than starting a marquee.
const touch=await browser.newContext({viewport:{width:390,height:844},hasTouch:true,isMobile:true});const tp=await touch.newPage();await tp.goto(BASE);await tp.evaluate(()=>openJob('large'));await tp.waitForSelector('#review');await tp.locator('.reviewranges').scrollIntoViewIfNeeded();await tp.waitForTimeout(250);
await tp.touchscreen.tap(190,700);assert.equal(await tp.locator('.marq').count(),0);check('narrow-touch',{marquee:0,viewport:await tp.evaluate(()=>[innerWidth,innerHeight])});await touch.close();
await page.setViewportSize({width:1365,height:950});await page.waitForTimeout(350);await start();
// A real marquee retains its bounded hit-test set while scrolling; Escape cancels.
await page.locator('[data-review-next]').focus();await start();
let visibleId=(await facts()).visible[0];let card=await page.locator('#det'+visibleId).boundingBox();
await page.mouse.move(card.x+2,card.y+2);await page.mouse.down();await page.mouse.move(card.x+card.width+5,card.y+card.height-2,{steps:5});
assert.equal(await page.evaluate(()=>REVIEW_SCHED.gesture),true);const heldCount=await page.locator('#detwrap .det').count();await page.evaluate(()=>scrollBy(0,400));await page.waitForTimeout(100);assert.equal(await page.locator('#detwrap .det').count(),heldCount);
await page.mouse.up();const selected=await page.evaluate(()=>[...selSet]);assert.ok(selected.length>0);await page.evaluate(()=>scrollTo(0,document.documentElement.scrollHeight));await page.waitForTimeout(250);assert.deepEqual(await page.evaluate(()=>[...selSet]),selected);
await page.evaluate(()=>scrollTo(0,document.querySelector('#detwrap').getBoundingClientRect().top+scrollY-55));await page.waitForTimeout(250);
for(const id of selected)assert.equal(await page.locator('#det'+id).evaluate(e=>e.classList.contains('selected')),true);
check('marquee-unmount-remount',{selected,cards:await page.locator('#detwrap .det').count()});await page.keyboard.press('Escape');assert.equal(await page.locator('.selmenu').count(),0);
// Local movement retains editor/draft/video identity and does no metadata/save I/O.
await page.getByRole('button',{name:/Preview video & edit boxes/}).click();await page.waitForSelector('#beCv');await page.locator('#beT').focus();await page.keyboard.press('ArrowRight');await page.keyboard.press('ArrowRight');await page.waitForFunction(()=>BE.raw?.length>0&&document.getElementById('beCv').width>0);
await page.evaluate(()=>{window.editorNode=document.getElementById('beCv');window.editorState=BE;BE.add=true;BE.addAnchor=[550,270];BE.addFloat=[570,290];MAN.push({t_start:.1,t_end:.3,screen_box:[580,280,600,300]});BE.audio.push({t0:1,t1:1.2,mode:'bleep'});BE.ov[0]=[16,16,40,46];BE.times[0]=[.2,3.5];});
const snapshot=await page.evaluate(()=>JSON.stringify({ov:BE.ov,times:BE.times,adds:BE.adds,anchor:BE.addAnchor,audio:BE.audio,manual:MAN}));
const requestMark=await page.evaluate(()=>qa.requests.length);
await page.evaluate(()=>scrollTo(0,document.documentElement.scrollHeight));await page.waitForTimeout(220);await page.setViewportSize({width:1100,height:850});await page.waitForTimeout(220);
assert.equal(await page.evaluate(()=>editorNode===document.getElementById('beCv')&&editorState===BE),true);assert.equal(await page.evaluate(()=>JSON.stringify({ov:BE.ov,times:BE.times,adds:BE.adds,anchor:BE.addAnchor,audio:BE.audio,manual:MAN})),snapshot);
assert.deepEqual(await page.evaluate(mark=>qa.requests.slice(mark).filter(r=>r.url.includes('/detections')||r.method==='POST'||r.url.includes('/mediainfo')),requestMark),[]);
check('editor-local-ownership',{identity:true,drafts:true,metadataOrSaveRequests:0});
await page.evaluate(()=>{BE.add=false;BE.addAnchor=null;BE.addFloat=null;BE.t=1});await page.locator('#bePlay').click();await page.evaluate(()=>document.getElementById('beVid').load());await page.waitForFunction(()=>BE.playing&&document.getElementById('beVid').currentTime>1);
await page.evaluate(()=>{window.videoNode=document.getElementById('beVid');scrollTo(0,document.documentElement.scrollHeight)});await page.waitForTimeout(220);assert.equal(await page.evaluate(()=>videoNode===document.getElementById('beVid')&&BE.playing),true);await page.evaluate(()=>document.getElementById('beVid').pause());check('playback-scroll',{sameVideo:true,playing:true,nativeLoadForRetainedBasePreloadNone:true});
// Held real save ACK: newer opposite choice remains pending through window move.
await control({save:false});await page.evaluate(()=>{applyDet(0,false);window.heldSave=saveAndRender();applyDet(0,true);scrollTo(0,document.documentElement.scrollHeight)});await page.waitForTimeout(200);await control({save:true});await page.evaluate(()=>heldSave);
assert.equal(await page.evaluate(()=>EDITS.enabled[0]),true);assert.match(await page.locator('#reviewSaveStatus').innerText(),/Newer edits/);check('held-save-newer-opposite',{pending:true});
await control({save_status:423});await page.evaluate(()=>saveAndRender());assert.equal(await page.evaluate(()=>EDITS.enabled[0]),true);assert.match(await page.locator('#reviewSaveStatus').innerText(),/drafts retained/);await control({save_status:200});check('failed-save-window',{retained:true});
// Real route ordering gates complement, rather than replace, ungated completion.
await control({hold:['large']});await open('beta');await open('large');await start();await page.waitForTimeout(200);
let gated=await facts();assert.ok(gated.flight<=4);await page.evaluate(()=>scrollTo(0,document.documentElement.scrollHeight));await page.waitForTimeout(180);await open('beta');await control({release_all:true});await start();await record('replacement-after-held-thumbs');
check('gated-switch',{maxActive:await page.evaluate(()=>qa.maxActive)});
await page.evaluate(()=>{window.oldOwner=REVIEW_SCHED;dispatchEvent(new PageTransitionEvent('pagehide'));dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}));});await page.waitForTimeout(180);assert.equal(await page.evaluate(()=>oldOwner.disposed&&REVIEW_SCHED!==oldOwner),true);check('pagehide-resume',{metadataReused:true});
await page.screenshot({path:ROOT+'/evidence/desktop.png'});
check('qa-health',{url:page.url(),title:await page.title(),errors,warnings});assert.deepEqual(errors,[]);
const state=await (await context.request.get(BASE+'/__qa__/state')).json();fs.writeFileSync(ROOT+'/evidence/server-observations.json',JSON.stringify(state,null,2));
await page.evaluate(()=>disposeReview());await page.waitForTimeout(150);const cleanup=await page.evaluate(()=>({live:qa.created.filter(u=>!qa.revoked.includes(u)),duplicateRevokes:qa.revoked.length-new Set(qa.revoked).size,active:qa.active}));assert.deepEqual(cleanup.live,[]);assert.equal(cleanup.duplicateRevokes,0);check('cleanup',cleanup);
await browser.close();browser=null;
})().catch(async e=>{console.error(e);check('FAILED',{error:e.stack});if(browser)await browser.close();process.exitCode=1});
