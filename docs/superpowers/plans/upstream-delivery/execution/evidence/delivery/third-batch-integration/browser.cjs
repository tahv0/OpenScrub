const {chromium}=require('/tmp/openscrub-save-as-20261116/node_modules/playwright');
const assert=require('node:assert/strict'),fs=require('node:fs');
const root='/tmp/openscrub-task652',origin='http://127.0.0.1:18652',ids=JSON.parse(fs.readFileSync(root+'/browser-jobs.json'));
const pause=ms=>new Promise(r=>setTimeout(r,ms));
async function until(fn){for(let i=0;i<1200;i++){if(await fn())return;await pause(20)}throw Error('bounded condition expired')}
(async()=>{
const browser=await chromium.launch({headless:true});
try {
const page=await browser.newPage({viewport:{width:1365,height:1000}}),errors=[],diagnostics=[],requests=[];
page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(['error','warning'].includes(m.type()))diagnostics.push({text:m.text(),url:m.location().url})});
page.on('request',r=>requests.push({url:r.url(),method:r.method()}));page.on('dialog',d=>d.dismiss());
await page.addInitScript(()=>{
 window.qa={holdAck:false,fail:false};const real=fetch.bind(window);
 window.fetch=async(url,opts={})=>{
  if(String(url).endsWith('/detections')&&opts.method==='POST'){
   qa.payload=JSON.parse(opts.body);if(qa.fail)opts={...opts,headers:{...opts.headers,'X-Task652-Fail':'yes'}};
   const r=await real(url,opts);qa.saveStatus=r.status;if(qa.holdAck){qa.committed=true;await new Promise(resolve=>qa.ack=resolve)}return r;
  }return real(url,opts);
 };
});
await page.goto(origin);assert.equal(await page.title(),'OpenScrub');assert.ok(await page.locator('body').innerText());assert.equal(await page.locator('nextjs-portal,vite-error-overlay').count(),0);
async function open(){await page.evaluate(id=>openJob(id),ids.alpha);await until(()=>page.evaluate(id=>EXPORT_NAMES.id===id,ids.alpha));}
async function review(){await page.getByRole('button',{name:'Re-open review',exact:true}).click();await page.locator('#bb1').waitFor();}
await open();await review();assert.match(await page.locator('#ds1').innerText(),/Mixed/);
const paths=JSON.parse(fs.readFileSync(root+'/browser-paths.json')),reportPath=paths[ids.alpha]+'/report.json';
const before=fs.readFileSync(reportPath),stat=fs.statSync(reportPath);
await page.locator('#bb10').click();await page.evaluate(()=>qa.holdAck=true);
await page.getByRole('button',{name:'Save edits & render',exact:true}).click();await until(()=>page.evaluate(()=>qa.committed));
assert.equal(await page.evaluate(()=>qa.payload.enabled['10']),true);assert.deepEqual(fs.readFileSync(reportPath),before);assert.equal(fs.statSync(reportPath).ino,stat.ino);
assert.ok(!fs.existsSync(root+'/publications.json'),'no-op skipped publisher');
await page.locator('#kb10').click();await page.evaluate(()=>qa.ack());
await until(()=>page.evaluate(()=>[...REVIEW_DRAFTS.values()].every(d=>!d.busy)));
assert.equal(await page.evaluate(()=>EDITS.enabled[10]),false);
assert.equal(requests.filter(r=>r.method==='POST'&&r.url.endsWith('/render')).length,0);
await page.evaluate(()=>{qa.holdAck=false;qa.fail=true});await page.getByRole('button',{name:'Save edits & render',exact:true}).click();
await until(async()=>/drafts retained/.test(await page.locator('#reviewSaveStatus').innerText()));
assert.equal(await page.evaluate(()=>qa.saveStatus),500);assert.equal(await page.evaluate(()=>EDITS.enabled[10]),false);assert.deepEqual(fs.readFileSync(reportPath),before);
assert.equal(requests.filter(r=>r.method==='POST'&&r.url.endsWith('/render')).length,0);
await page.screenshot({path:root+'/browser-draft-desktop.png',fullPage:true});
let expectedPublications=0;
async function startRender(){
 expectedPublications++;
 const accepted=page.waitForResponse(r=>r.url().endsWith('/render')&&r.request().method()==='POST');
 await page.getByRole('button',{name:'Save edits & render',exact:true}).click();assert.equal((await accepted).status(),200);
 await until(async()=>{
  const j=await(await page.request.get(origin+'/api/jobs/'+ids.alpha)).json();if(j.phase==='error')throw Error(j.error);
  const events=fs.existsSync(root+'/publications.json')?JSON.parse(fs.readFileSync(root+'/publications.json')):[];
  return j.phase==='done'&&events.filter(e=>!e.saving&&e.complete).length===expectedPublications;
 });
}
await page.evaluate(()=>qa.fail=false);await page.locator('#bb10').click();await startRender();
let events=JSON.parse(fs.readFileSync(root+'/publications.json'));assert.equal(events.filter(e=>e.saving&&!e.failed).length,0);
await open();await review();
await page.locator('#kb1').click();await page.locator('#kb1').click();await page.locator('#bb4').click();await page.locator('#bb4').click();
await page.locator('#review details summary').click();await page.locator('#bb8').click();await page.locator('#bb8').click();
await page.evaluate(()=>EDITS.manual.push({manual_id:'batch652:replay',t_start:0,t_end:1.99,screen_box:[140,80,155,94]}));
const expected=await page.evaluate(()=>Object.values(EN));await startRender();
const saved=JSON.parse(fs.readFileSync(reportPath));assert.equal(saved.detections.length,14);assert.deepEqual(saved.detections.slice(0,13).map(d=>d.enabled),expected);
const initial=JSON.parse(before);for(let i=0;i<13;i++){const d=structuredClone(saved.detections[i]);d.enabled=initial.detections[i].enabled;assert.deepEqual(d,initial.detections[i]);}
for(const k of ['render_state','audio_redactions','audio_suggestions','audio_transcript','future_top'])assert.deepEqual(saved[k],initial[k]);
const replay={manual:[{manual_id:'batch652:replay',t_start:0,t_end:1.99,screen_box:[140,80,155,94]}]};
assert.equal((await page.request.post(origin+'/api/jobs/'+ids.alpha+'/detections',{data:replay})).status(),200);assert.equal(JSON.parse(fs.readFileSync(reportPath)).detections.length,14);
await page.close();const fresh=await browser.newPage({viewport:{width:390,height:844}});fresh.on('pageerror',e=>errors.push(e.message));fresh.on('console',m=>{if(['error','warning'].includes(m.type()))diagnostics.push({text:m.text(),url:m.location().url})});
await fresh.goto(origin);await fresh.evaluate(id=>openJob(id),ids.alpha);await fresh.getByRole('button',{name:'Re-open review',exact:true}).click();await fresh.locator('#bb1').waitFor();
assert.equal(await fresh.locator('#ds1').innerText(),'Will stay visible');assert.equal(await fresh.locator('#ds4').innerText(),'Will be blurred');assert.equal(await fresh.locator('#ds8').textContent(),'Will be blurred');
const rows=await(await fresh.request.get(origin+'/api/jobs/'+ids.alpha+'/detections')).json();assert.deepEqual(rows.detections.map(d=>d.i),Array.from({length:14},(_,i)=>i));assert.deepEqual(rows.detections.map(d=>d.enabled),saved.detections.map(d=>d.enabled));
assert.deepEqual(await(await fresh.request.get(origin+'/api/jobs/'+ids.alpha+'/report')).json(),saved);await fresh.screenshot({path:root+'/browser-after-render-mobile.png',fullPage:true});
assert.deepEqual(errors,[]);assert.deepEqual(diagnostics,[{text:'Failed to load resource: the server responded with a status of 500 (INTERNAL SERVER ERROR)',url:origin+'/api/jobs/'+ids.alpha+'/detections'}]);
fs.writeFileSync(root+'/browser-results.json',JSON.stringify({origin,title:await fresh.title(),ids,errors,controlledDiagnostics:diagnostics,requests,expected,rows:rows.detections.length,output:paths[ids.alpha]+'/output.mp4',reportPath,checks:['same-value no-op skips publisher and still renders','newer different draft retained through held acknowledgement and failed save; no unintended render','repeated explicit group/independent zone controls','manual replay ID','actual accepted render plus real report publisher completion','all raw rows/indices/audio/additive data after render and fresh browser']},null,2));
console.log('Task652 actual PAGE/HTTP/draft/no-op/render/reopen passed');
} finally {await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
