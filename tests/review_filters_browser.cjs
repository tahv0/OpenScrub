// Full shipped PAGE, synthetic route fixtures; no replacement review logic.
const {chromium}=require(process.env.OPENSCRUB_PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict'),fs=require('node:fs');
const root=process.env.VERIFY_RUN,origin='http://127.0.0.1:18550';
const row=(i,category,enabled,person=-1,track=-1,confidence=.5,zone_dropped=false)=>({i,category,enabled,person,track,confidence,zone_dropped,text:'synthetic '+i,t_start:.1,t_end:2,box:[20+i*12,20,40+i*12,50]});
const initial=[row(0,'face',true,0,-1,.9),row(1,'face',false,0),row(2,'face',true,0),row(3,'face',true),row(4,'plate',false,-1,4,.9),row(5,'plate',false,-1,4),row(6,'plate',true),row(7,'email',false),row(8,'face',false,0,-1,.95,true),row(9,'plate',true,-1,4,.95,true)];
const results={browserPlugin:'unavailable',page:'full emitted PAGE',scenarios:[],errors:[],console:[]};
let browser,page;
(async()=>{browser=await chromium.launch({headless:true});page=await browser.newPage({viewport:{width:1365,height:1000},hasTouch:true,isMobile:process.env.TASK150_TOUCH_ONLY==='1'});
page.on('pageerror',e=>results.errors.push(e.message));page.on('console',m=>{if(['error','warning'].includes(m.type()))results.console.push(m.text())});
let rows=structuredClone(initial),hold=false,release=null,fail=false,holdThumbs=false;const heldThumbs=[];const requests=[];
await page.route(origin+'/**',async route=>{const req=route.request(),path=new URL(req.url()).pathname;requests.push({path,method:req.method()});
const json=body=>route.fulfill({contentType:'application/json',body:JSON.stringify(body)});
if(path==='/')return route.fulfill({contentType:'text/html',body:fs.readFileSync(root+'/page.html','utf8')});
if(path==='/api/jobs')return json(['A','B','empty'].map(id=>({id,name:'Synthetic '+id,phase:'review'})));
if(/^\/api\/jobs\/[^/]+$/.test(path))return json({id:path.split('/').at(-1),name:'Synthetic review',phase:'review',progress:1,has_output:false});
if(path.endsWith('/log'))return json({from:0,lines:[],len:0});
if(path.endsWith('/detections')){if(req.method()==='POST'){if(hold)await new Promise(r=>release=r);if(fail)return route.fulfill({status:423,contentType:'application/json',body:'{"error":"controlled busy"}'});for(const [i,v]of Object.entries(req.postDataJSON().enabled||{}))rows[+i].enabled=v;return json({ok:true});}return json({detections:path.includes('/empty/')?[]:rows,duration:4,fps:10});}
if(path.endsWith('/render'))return json({ok:true});
if(path.endsWith('/report'))return json({detections:rows.map(({box,...r})=>({...r,cbox:box,aoff:[0,0]})),audio_redactions:[],render_state:{fps:10,cum:Array(40).fill([0,0])}});
if(path.endsWith('/mediainfo'))return json({duration:4,fps:10,width:320,height:180});
if(path.endsWith('/boxes_at'))return json({ox:0,oy:0,boxes:rows.filter(x=>!x.zone_dropped)});
if(/\/(thumb|detframe)\/\d+$|\/frame_at$/.test(path)){if(holdThumbs&&path.includes('/thumb/'))await new Promise(resolve=>heldThumbs.push(resolve));try{return await route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="320" height="180"><rect width="320" height="180" fill="#233447"/><path d="M40 30h90v100H40z" fill="#abc"/></svg>'})}catch(error){if(!route.request().failure())throw error;}}
if(path==='/api/custom_cats')return json([]);if(path==='/api/allowlist')return json({words:[]});if(path==='/api/certinfo')return json({mode:'synthetic'});if(path==='/api/vault')return json({enabled:false});if(path==='/api/extras')return json({extras:[]});if(path==='/api/update_check')return json({update_available:false});if(path==='/api/quality_tier')return json({tier:'fast',needs:{}});if(path.startsWith('/api/models/'))return json({active:true,selected:'',models:[]});if(path==='/api/model_status')return json({face:true,plate:true,person:true});if(path==='/favicon.ico')return route.fulfill({status:204});return json({});});
await page.goto(origin);assert.equal(await page.title(),'OpenScrub');await page.locator('#jobs a').first().click();await page.locator('#reviewOutput').waitFor();await page.evaluate(()=>scrollTo(0,document.getElementById('detwrap').getBoundingClientRect().top+scrollY-55));await page.locator('#bb0').waitFor();
assert.match(await page.locator('body').innerText(),/Review/);
assert.equal(await page.locator('#reviewType').count(),1,'missing Detection type selector on actual full PAGE');
assert.equal(await page.locator('#reviewOutput').count(),1,'missing Output selector on actual full PAGE');
results.scenarios.push('native selectors present');
if(process.env.TASK150_RED==='1')return;
const status=async s=>assert.equal(await page.locator('#reviewFilterStatus').innerText(),s);
const filter=async(type,output)=>{await page.locator('#reviewType').selectOption(type??'');await page.locator('#reviewOutput').selectOption(output)};
// Locate through actual scheduler geometry; virtualization intentionally has no offscreen card nodes.
const placeCard=async id=>{await page.evaluate(i=>{const s=REVIEW_SCHED;s.layout();const section=s.sections.find(x=>x.ids.includes(i));if(!section)throw Error('card unavailable '+i);const n=section.ids.indexOf(i),top=section.el.getBoundingClientRect().top+scrollY+section.prefix[Math.floor(n/section.columns)]*section.scale;scrollTo(0,Math.max(0,top-100));s.layout()},id);await page.locator('#det'+id).waitFor()};
const cardAction=async id=>{await placeCard(+id.slice(2));await page.locator('#'+id).click()};

if(process.env.TASK150_TOUCH_ONLY==='1'){
 await page.evaluate(async flags=>{for(const [i,value]of Object.entries(flags))EDITS.enabled[i]=value;await loadReview()},Object.fromEntries(initial.map(r=>[r.i,!r.enabled])));
 await filter('','blur');assert.deepEqual(await page.evaluate(()=>[...REVIEW_META.byId.values()].filter(c=>reviewMatches(c,null,'blur')).map(c=>c.id).sort((a,b)=>a-b)),[0,4,7,8]);await status('4 of 7 cards match');
 await filter('','visible');assert.deepEqual(await page.evaluate(()=>[...REVIEW_META.byId.values()].filter(c=>reviewMatches(c,null,'visible')).map(c=>c.id).sort((a,b)=>a-b)),[0,3,6,9]);
 await page.locator('#reviewType').click();await page.keyboard.press('Home');await page.keyboard.press('ArrowDown');await page.keyboard.press('Enter');assert.equal(await page.locator('#reviewType').inputValue(),'face');
 await page.locator('#reviewOutput').selectOption('blur');await cardAction('kb0');await status('1 of 7 cards match');assert.match(await page.locator('#reviewFilterHint').innerText(),/outside your zones/);assert.equal(await page.locator('#reviewZones').getAttribute('open'),null);
 await page.evaluate(()=>openJob('empty'));await page.locator('#reviewOutput').waitFor();await status('0 of 0 cards match');assert.equal(await page.locator('#reviewFilterEmpty').innerText(),'No detections in this job.');await page.evaluate(()=>openJob('A'));await page.locator('#reviewOutput').waitFor();
 results.scenarios.push('opposite pending overlay, native Detection type pointer/keyboard, collapsed-zone-only matches and no detections');
}
if(process.env.TASK150_TOUCH_ONLY!=='1'){
await status('7 of 7 cards match');await filter('','blur');await status('4 of 7 cards match');await filter('','visible');await status('4 of 7 cards match');
await filter('face','visible');await status('2 of 7 cards match');assert.equal(await page.locator('#reviewZones').getAttribute('open'),null);
await filter('email','blur');await status('0 of 7 cards match');assert.equal(await page.locator('#reviewFilterEmpty').isVisible(),true);
await page.locator('#reviewFilterReset').click();await status('7 of 7 cards match');assert.equal(await page.evaluate(()=>document.activeElement.id),'reviewFilterReset');
results.scenarios.push('seven-card mixed/type/empty/reset counts');
await page.locator('#reviewOutput').focus();await page.keyboard.press('ArrowDown');await page.keyboard.press('Enter');await status('4 of 7 cards match');
await placeCard(3);await page.locator('#kb3').focus();await page.keyboard.press('Enter');await status('3 of 7 cards match');assert.equal(await page.evaluate(()=>document.activeElement.id),'reviewOutput');
await placeCard(0);await page.locator('#bb0').focus();await page.keyboard.press('Enter');assert.equal(await page.evaluate(()=>document.activeElement.id),'bb0');
results.scenarios.push('native keyboard, disappearing-control focus fallback and retained-card focus');
await page.locator('#reviewFilterReset').click();await page.locator('#reviewZones summary').click();await page.locator('#det8').waitFor({state:'visible'});
await page.evaluate(()=>{selSet.add(8);document.getElementById('det8').classList.add('selected')});await page.locator('#reviewZones summary').click();assert.deepEqual(await page.evaluate(()=>[...selSet]),[]);await page.locator('#reviewZones summary').click();assert.deepEqual(await page.evaluate(()=>[...selSet]),[]);
await filter('email','all');assert.equal(await page.locator('#reviewZones').isVisible(),false);await filter('','all');assert.equal(await page.locator('#reviewZones').getAttribute('open'),'');
results.scenarios.push('zone collapse selection pruning and open preference retained across hiding');
await page.locator('#reviewZones summary').click();
await filter('face','all');await placeCard(0);const target=page.locator('#det0');await target.scrollIntoViewIfNeeded();let b=await target.boundingBox();
await page.mouse.move(b.x+3,b.y+3);await page.mouse.down();await page.mouse.move(b.x+b.width-3,b.y+b.height-3,{steps:4});await page.mouse.up();
assert.deepEqual(await page.evaluate(()=>[...selSet]),[0]);await page.locator('.selmenu .mkeep').click();assert.deepEqual(await page.evaluate(()=>[EN[0],EN[1],EN[2]]),[false,false,false]);
await cardAction('bb0');b=await target.boundingBox();await page.mouse.move(b.x+3,b.y+3);await page.mouse.down();await page.mouse.move(b.x+30,b.y+30);await page.keyboard.press('Escape');await page.mouse.up();assert.deepEqual(await page.evaluate(()=>[...selSet]),[]);
await page.locator('#det0 img').click();await page.locator('#lb img').waitFor();assert.match(await page.locator('#lb img').getAttribute('src'),/detframe\/0$/);await page.keyboard.press('Escape');assert.equal(await page.locator('#lb').count(),0);
await page.locator('#reviewFilterReset').click();
results.scenarios.push('native marquee full-group selected action, Escape cancels active marquee, enlarged original preview');

await page.locator('button[onclick="loadBoxEdit(1)"]').click();await page.locator('#beCv').waitFor();
await page.waitForFunction(()=>BE.boxes.length>0&&BE.scale>0);await page.locator('#beCv').scrollIntoViewIfNeeded();
let cv=await page.locator('#beCv').boundingBox(),scale=await page.evaluate(()=>BE.scale);
await page.mouse.click(cv.x+42*scale,cv.y+35*scale);assert.equal(await page.evaluate(()=>BE.sel),1);
await page.locator('#beT0').fill('0.2');await page.locator('#beT1').fill('1.8');await page.locator('button[onclick="beApplyTimes()"]').click();
await page.locator('#beCv').scrollIntoViewIfNeeded();cv=await page.locator('#beCv').boundingBox();await page.mouse.move(cv.x+42*scale,cv.y+35*scale);await page.mouse.down();await page.mouse.move(cv.x+47*scale,cv.y+40*scale);
assert.equal(await page.evaluate(()=>BE.drag?.kind),'move');
await page.evaluate(()=>{window.retainedBE=BE;window.retainedEditor=document.getElementById('beCv');BE.ov[1]=[1,2,30,40];BE.times[1]=[0,1];BE.adds.push({t0:0,t1:1,box:[2,3,30,40]});BE.audio=[{t0:0,t1:1,mode:'mute'}];BE.sel=1;MAN.push({draft:true});window.draft=JSON.stringify({EN,BE,MAN,enabled:EDITS.enabled})});
const boundary=requests.length;await page.evaluate(()=>setReviewFilter('email','blur'));await page.evaluate(()=>setReviewFilter(null,'all'));
assert.equal(await page.evaluate(()=>BE===window.retainedBE&&document.getElementById('beCv')===window.retainedEditor&&JSON.stringify({EN,BE,MAN,enabled:EDITS.enabled})===window.draft),true);
assert.deepEqual(requests.slice(boundary).filter(r=>/\/(detections|report|mediainfo|boxes_at|render)$/.test(r.path)),[]);
assert.equal(await page.evaluate(()=>BE.drag?.kind),'move');await page.mouse.up();assert.equal(await page.evaluate(()=>BE.drag),null);
results.scenarios.push('editor object/node, selection, pending geometry/time/manual/audio and actual unfinished pointer gesture retained; zero metadata/save/render requests');
await page.evaluate(()=>{BE.drag=null;MAN.length=0;BE.adds.length=0;BE.ov={};BE.times={};BE.audio=[];BE.audioLoaded=false});
hold=true;await cardAction('kb0');await page.evaluate(()=>{window.saving=saveAndRender()});await page.waitForFunction(()=>EDITS.busy);await cardAction('bb0');await filter('plate','visible');hold=false;release();await page.evaluate(()=>window.saving);assert.equal(await page.evaluate(()=>EDITS.enabled[0]),true);assert.equal(requests.filter(r=>r.path.endsWith('/render')).length,0);await status('1 of 7 cards match');
fail=true;await page.evaluate(()=>saveAndRender());assert.match(await page.locator('#reviewSaveStatus').innerText(),/controlled busy/);await page.locator('#reviewFilterReset').click();assert.equal(await page.evaluate(()=>EDITS.enabled[0]),true);
await page.evaluate(()=>openJob('B'));await page.locator('#reviewType').waitFor();assert.equal(await page.locator('#reviewType').inputValue(),'');await page.evaluate(()=>openJob('A'));await page.locator('#reviewOutput').waitFor();assert.equal(await page.locator('#reviewOutput').inputValue(),'all');
results.scenarios.push('held-save newer intent, failed save, A→B→A reset and owning draft');
}

// Modest complete metadata proves actual scheduler/filter ownership beyond mounted nodes.
await page.setViewportSize({width:700,height:600});await page.waitForFunction(()=>THUMB_FLIGHTS.size===0);holdThumbs=true;
rows=Array.from({length:96},(_,i)=>row(100+i,i%2?'plate':'face',i%3!==0));
rows.push(row(220,'face',false,-1,-1,.5,true),row(221,'plate',true,-1,-1,.5,true));
await page.evaluate(()=>{openJob('B');openJob('A')});await page.locator('#reviewOutput').waitFor();
await page.locator('#reviewFilterReset').click();await placeCard(100);
await page.waitForFunction(()=>REVIEW_SCHED.bindings.size>0);assert.equal(await page.evaluate(()=>REVIEW_META.byId.size),98);assert.ok(await page.evaluate(()=>REVIEW_SCHED.bindings.size<REVIEW_META.byId.size));
await page.waitForFunction(()=>THUMB_FLIGHTS.size===4);await page.evaluate(()=>window.filteredFlights=[...THUMB_FLIGHTS]);await filter('face','blur');await status('32 of 98 cards match');await page.waitForFunction(()=>filteredFlights.some(op=>op.cancelled));assert.ok(await page.evaluate(()=>THUMB_FLIGHTS.size<=4));holdThumbs=false;heldThumbs.splice(0).forEach(release=>release());await page.waitForFunction(()=>THUMB_FLIGHTS.size===0);await placeCard(102);
const focusId=await page.evaluate(()=>{const b=[...REVIEW_SCHED.bindings.values()].find(b=>REVIEW_SCHED.matching.has(b.id));b.card.querySelector('button').focus();window.retainedFilterNode=b.card;return b.id});
await page.evaluate(()=>refreshReviewFilters());assert.equal(await page.evaluate(id=>document.getElementById('det'+id)===window.retainedFilterNode,focusId),true);
await page.evaluate(()=>{const s=REVIEW_SCHED;refreshReviewVisibleSet({jobId:s.jobId,viewGen:s.viewGen});refreshReviewVisibleSet();});
assert.equal(await page.evaluate(()=>REVIEW_SCHED.matching.size),32);
await page.locator('[data-review-next]').click();await page.waitForFunction(()=>[...REVIEW_SCHED.bindings.keys()].every(i=>REVIEW_SCHED.matching.has(i)));
await page.evaluate(()=>{window.dispatchEvent(new PageTransitionEvent('pagehide',{persisted:true}));window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}));});
await page.waitForFunction(()=>REVIEW_SCHED.owns());assert.equal(await page.evaluate(()=>REVIEW_SCHED.matching.size),32);
// Category actions affect every unmounted/hidden ordinary member, independently of zones.
// A removed card must not make the focused Output selector scroll this long
// filtered list back to its beginning. Repeat on later rows, not only the first.
for(const id of [148,154]){
 await placeCard(id);
 const before=await page.evaluate(()=>scrollY);
 assert.ok(before>500,'fixture did not reach a deep review card: '+id+' at '+before);
 await page.locator('#kb'+id).click();
 await page.waitForFunction(id=>!REVIEW_SCHED.matching.has(id),id);
 await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
 const after=await page.evaluate(()=>scrollY);
 assert.equal(await page.evaluate(()=>document.activeElement.id),'reviewOutput');
 assert.ok(after>300&&Math.abs(after-before)<700,
  'Keep visible jumped the filtered review list: card '+id+' before '+before+' after '+after);
}
results.scenarios.push('multiple deep filtered Keep visible choices preserve scroll position and fallback focus');
await page.evaluate(()=>setAll('face',false));assert.equal(await page.evaluate(()=>Array.from({length:48},(_,i)=>EN[100+i*2]).every(v=>v===false)),true);assert.equal(await page.evaluate(()=>EN[221]),true);await status('0 of 98 cards match');
await page.evaluate(()=>setAllZd(false));assert.equal(await page.evaluate(()=>EN[221]),false);
await filter('plate','all');await page.evaluate(()=>{const s=REVIEW_SCHED;refreshReviewVisibleSet({jobId:s.jobId,viewGen:s.viewGen,matchingCardIds:[]})});await page.waitForFunction(()=>REVIEW_SCHED.bindings.size===0);await page.evaluate(()=>refreshReviewFilters());assert.equal(await page.evaluate(()=>REVIEW_SCHED.matching.size),49);
const explicit=await page.evaluate(()=>{const c=[...REVIEW_META.byId.values()].find(c=>c.category==='plate'&&!c.zone&&!REVIEW_SCHED.bindings.has(c.id)&&EN[c.id]===false);if(!c)throw Error('missing unmounted selected fixture');selSet.add(c.id);selSet.add(100);bulkSet(true);return c.id});assert.equal(await page.evaluate(i=>EN[i],explicit),true);assert.equal(await page.evaluate(()=>EN[100]),false);assert.deepEqual(await page.evaluate(()=>[...selSet]),[]);
results.scenarios.push('actual scheduler: 98 complete cards, unmounted full-scope actions, matching focus, range, empty matching, BFCache retention and queue ownership');
// Restore the exact seven-card/mobile oracle and pending choices established above.
rows=structuredClone(initial);await page.evaluate(()=>{REVIEW_DRAFTS.get('A').enabled={};openJob('B');openJob('A')});await page.locator('#reviewOutput').waitFor();await page.evaluate(()=>{applyDet(0,true);applyDet(3,false)});
await page.setViewportSize({width:390,height:844});await page.locator('#reviewFilterReset').click();await page.screenshot({path:root+'/mobile.png'});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);await page.locator('#reviewOutput').selectOption('visible');// A is all true from pending bb0; B3 was kept, C4/5 and E7 remain false, Z8 is false, D6/Z9 true. Thus B/C/E/Z8 match.
await status('4 of 7 cards match');
results.scenarios.push('390px layout and native controls');
await page.locator('#reviewFilterReset').click();await placeCard(0);await page.locator('#det0').scrollIntoViewIfNeeded();const touch=await page.context().newCDPSession(page);
const touchGeometry=await page.evaluate(()=>{const e=document.getElementById('detwrap');scrollTo(0,e.getBoundingClientRect().top+scrollY);return {container:'window/vertical',scrollY,max:document.documentElement.scrollHeight-innerHeight,wrap:e.getBoundingClientRect().toJSON()}});assert.ok(touchGeometry.max>touchGeometry.scrollY+150);const scrollBefore=touchGeometry.scrollY;
results.touchGeometry=touchGeometry;fs.writeFileSync(root+'/touch-precondition.json',JSON.stringify(touchGeometry,null,2));
await touch.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:190,y:700}]});
for(let y=650;y>=300;y-=50){await touch.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:190,y}]});await page.waitForTimeout(20)}
await touch.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});assert.deepEqual(await page.evaluate(()=>[...selSet]),[]);await page.waitForFunction(before=>scrollY>before,scrollBefore);results.touchAfter=await page.evaluate(()=>scrollY);
await page.getByText('Advanced settings ▸',{exact:true}).click();const tip=page.locator('label:has(#faceheads) .qm');await tip.scrollIntoViewIfNeeded();const checked=await page.locator('#faceheads').isChecked();await tip.tap();assert.equal(await tip.evaluate(e=>e.classList.contains('open')),true);assert.equal(await page.locator('#faceheads').isChecked(),checked);assert.equal(await tip.evaluate(e=>e.style.getPropertyValue('--qw')),'250px');
results.scenarios.push('native touch scrolling leaves selection empty; mobile help tap preserves checkbox and tooltip bounds');
assert.deepEqual(results.errors,[]);await page.screenshot({path:root+'/filtered.png'});
})().catch(e=>{results.failure=e.stack;process.exitCode=1}).finally(async()=>{if(results.failure&&page){results.failureState=await page.evaluate(()=>({poll:document.getElementById('pollStatus')?.textContent,review:!!REVIEW_META,matching:REVIEW_SCHED?[...REVIEW_SCHED.matching]:[],mounted:REVIEW_SCHED?[...REVIEW_SCHED.bindings.keys()]:[]})).catch(()=>null)}if(browser)await browser.close();fs.writeFileSync(root+'/browser-results.json',JSON.stringify(results,null,2));console.log(JSON.stringify(results))});
