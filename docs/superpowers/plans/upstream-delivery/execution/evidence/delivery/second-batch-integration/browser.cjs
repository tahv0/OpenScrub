const {chromium}=require('/tmp/openscrub-save-as-20261116/node_modules/playwright');
const assert=require('node:assert/strict'),fs=require('node:fs');
const root='/tmp/openscrub-task651',origin='http://127.0.0.1:18651',ids=JSON.parse(fs.readFileSync(root+'/browser-jobs.json'));
const pause=ms=>new Promise(r=>setTimeout(r,ms));
async function until(fn){for(let i=0;i<1200;i++){if(await fn())return;await pause(20)}throw Error('bounded condition expired')}
(async()=>{
const browser=await chromium.launch({headless:true});
const page=await browser.newPage({viewport:{width:1365,height:1000}}),errors=[],diagnostics=[],requests=[];
page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(['error','warning'].includes(m.type()))diagnostics.push({text:m.text(),url:m.location().url})});
page.on('request',r=>requests.push({url:r.url(),method:r.method()}));page.on('dialog',d=>d.dismiss());
await page.addInitScript(()=>{
 window.qa={holdAck:false,fail:false,poll:null,accepted:0};const real=fetch.bind(window);
 window.fetch=async(url,opts={})=>{
  if(String(url).endsWith('/detections')&&opts.method==='POST'){
   qa.payload=JSON.parse(opts.body);if(qa.fail)opts={...opts,headers:{...opts.headers,'X-Task651-Fail':'yes'}};
   const r=await real(url,opts);qa.saveStatus=r.status;if(qa.holdAck){qa.committed=true;await new Promise(resolve=>qa.ack=resolve)}return r;
  }
  if(qa.poll&&String(url).match(/^api\/jobs\/[^/]+$/)){
   const kind=qa.poll;qa.poll=null;opts={...opts,headers:{...opts.headers,[kind==='503'?'X-Task651-Poll503':'X-Task651-Hold']:'yes'}};
  }return real(url,opts);
 };
 window.showSaveFilePicker=async o=>{qa.name=o.suggestedName;const dir=await navigator.storage.getDirectory();qa.file=await dir.getFileHandle('task651-'+o.suggestedName,{create:true});return {createWritable:async()=>{const w=await qa.file.createWritable();return {
 write:async b=>{if(qa.holdWrite){qa.writePending=true;await new Promise(r=>qa.write=r);qa.holdWrite=false}await w.write(b);qa.accepted+=b.length},
 close:()=>w.close(),abort:()=>w.abort()}}}};
});
await page.goto(origin);assert.equal(await page.title(),'OpenScrub');assert.equal(await page.locator('nextjs-portal,vite-error-overlay').count(),0);
async function open(id){await page.evaluate(id=>openJob(id),id);await until(()=>page.evaluate(id=>EXPORT_NAMES.id===id,id));}
async function review(){await page.getByRole('button',{name:'Re-open review',exact:true}).click();await page.locator('#bb1').waitFor();}
await open(ids.alpha);await review();assert.match(await page.locator('#ds1').innerText(),/Mixed/);
// Existing stored true, deliberately submitted true: publisher must be skipped.
const paths=JSON.parse(fs.readFileSync(root+'/browser-paths.json')),reportPath=paths[ids.alpha]+'/report.json';
const before=fs.readFileSync(reportPath),stat=fs.statSync(reportPath);
await page.locator('#bb10').click();await page.evaluate(()=>qa.holdAck=true);
await page.getByRole('button',{name:'Save edits & render',exact:true}).click();await until(()=>page.evaluate(()=>qa.committed));
assert.equal(await page.evaluate(()=>qa.payload.enabled['10']),true);assert.deepEqual(fs.readFileSync(reportPath),before);assert.equal(fs.statSync(reportPath).ino,stat.ino);
assert.ok(!fs.existsSync(root+'/publications.json'),'no-op skipped publisher');
await page.locator('#kb10').click();
// Save As and polling feedback coexist with the unacknowledged newer draft.
await page.evaluate(()=>{qa.holdWrite=true;qa.poll='503';refresh()});
await page.getByRole('button',{name:'Save redacted video as…'}).click();await until(()=>page.evaluate(()=>qa.writePending));
await until(async()=>/retrying/.test(await page.locator('#pollStatus').innerText()));
assert.match(await page.locator('#reviewSaveStatus').innerText(),/Saving/);assert.equal(await page.evaluate(()=>EDITS.enabled[10]),false);
assert.equal(await page.evaluate(id=>EXPORTS.get(id+':video').written,ids.alpha),0);
await until(async()=>await page.locator('#pollStatus').innerText()==='');
// Actual response headers plus one byte are held beyond the shipped body deadline.
await page.evaluate(()=>{qa.poll='body';refresh()});await until(()=>fs.existsSync(root+'/body-entered'));
await until(async()=>/retrying/.test(await page.locator('#pollStatus').innerText()));
assert.equal(await page.evaluate(()=>EDITS.enabled[10]),false);
fs.writeFileSync(root+'/body-release','release');await until(async()=>await page.locator('#pollStatus').innerText()==='');
const log=await page.locator('#log').innerText();assert.equal(new Set(log.split('\n')).size,log.split('\n').length,'no duplicate log append');
await open(ids.beta);await page.evaluate(()=>qa.ack());await until(()=>page.evaluate(()=>[...REVIEW_DRAFTS.values()].every(d=>!d.busy)));
assert.equal(requests.filter(r=>r.method==='POST'&&r.url.endsWith('/render')).length,0);
await open(ids.alpha);await review();assert.equal(await page.evaluate(()=>EDITS.enabled[10]),false);assert.equal(await page.locator('#kb10').getAttribute('aria-pressed'),'true');
await page.evaluate(()=>{qa.holdAck=false;qa.fail=true});await page.getByRole('button',{name:'Save edits & render',exact:true}).click();
await until(async()=>/drafts retained/.test(await page.locator('#reviewSaveStatus').innerText()));
assert.equal(await page.evaluate(()=>qa.saveStatus),500);assert.equal(await page.evaluate(()=>EDITS.enabled[10]),false);assert.deepEqual(fs.readFileSync(reportPath),before);
assert.equal(requests.filter(r=>r.method==='POST'&&r.url.endsWith('/render')).length,0);
await page.evaluate(()=>qa.write());await until(()=>page.evaluate(id=>EXPORTS.get(id+':video').phase==='saved',ids.alpha));
assert.equal(await page.evaluate(()=>qa.accepted),4194304);
const exported=await page.evaluate(async()=>Array.from(new Uint8Array(await (await qa.file.getFile()).arrayBuffer())));
assert.deepEqual(Buffer.from(exported),Buffer.from(Array.from({length:4194304},(_,i)=>i%256)));
await page.screenshot({path:root+'/browser-draft-desktop.png',fullPage:true});
// Equal stored value save is successful without publication and still starts actual render.
async function startRender(){const accepted=page.waitForResponse(r=>r.url().endsWith('/render')&&r.request().method()==='POST');await page.getByRole('button',{name:'Save edits & render',exact:true}).click();assert.equal((await accepted).status(),200)}
await page.evaluate(()=>qa.fail=false);await page.locator('#bb10').click();await startRender();
async function done(){for(let i=0;i<200;i++){const j=await(await page.request.get(origin+'/api/jobs/'+ids.alpha)).json();if(j.phase==='error')throw Error(j.error);if(j.phase==='done')return j;await pause(50)}throw Error('worker did not finish')}
await done();assert.equal(requests.filter(r=>r.method==='POST'&&r.url.endsWith('/render')).length,1);
let events=JSON.parse(fs.readFileSync(root+'/publications.json'));assert.equal(events.filter(e=>e.saving&&!e.failed).length,0);assert.ok(events.some(e=>!e.saving&&e.complete));
await open(ids.alpha);await review();
await page.locator('#kb1').click();await page.locator('#kb1').click();await page.locator('#bb4').click();await page.locator('#bb4').click();
await page.locator('#review details summary').click();await page.locator('#bb8').click();await page.locator('#bb8').click();
await page.evaluate(()=>EDITS.manual.push({manual_id:'batch651:replay',t_start:0,t_end:1.99,screen_box:[140,80,155,94]}));
const expected=await page.evaluate(()=>Object.values(EN));
await startRender();await done();
const saved=JSON.parse(fs.readFileSync(reportPath));assert.equal(saved.detections.length,14);assert.deepEqual(saved.detections.slice(0,13).map(d=>d.enabled),expected);
const initial=JSON.parse(before);for(let i=0;i<13;i++){const d=structuredClone(saved.detections[i]);d.enabled=initial.detections[i].enabled;assert.deepEqual(d,initial.detections[i]);}
for(const k of ['render_state','audio_redactions','audio_suggestions','audio_transcript','future_top'])assert.deepEqual(saved[k],initial[k]);
const replay={manual:[{manual_id:'batch651:replay',t_start:0,t_end:1.99,screen_box:[140,80,155,94]}]};
assert.equal((await page.request.post(origin+'/api/jobs/'+ids.alpha+'/detections',{data:replay})).status(),200);
assert.equal(JSON.parse(fs.readFileSync(reportPath)).detections.length,14);
await page.close();const fresh=await browser.newPage({viewport:{width:390,height:844}});fresh.on('pageerror',e=>errors.push(e.message));await fresh.goto(origin);await fresh.evaluate(id=>openJob(id),ids.alpha);await fresh.getByRole('button',{name:'Re-open review',exact:true}).click();await fresh.locator('#bb1').waitFor();
assert.equal(await fresh.locator('#ds1').innerText(),'Will stay visible');assert.equal(await fresh.locator('#ds4').innerText(),'Will be blurred');assert.equal(await fresh.locator('#ds8').textContent(),'Will be blurred');
const rows=await(await fresh.request.get(origin+'/api/jobs/'+ids.alpha+'/detections')).json();assert.deepEqual(rows.detections.map(d=>d.i),Array.from({length:14},(_,i)=>i));assert.deepEqual(rows.detections.map(d=>d.enabled),saved.detections.map(d=>d.enabled));
assert.deepEqual(await(await fresh.request.get(origin+'/api/jobs/'+ids.alpha+'/report')).json(),saved);await fresh.screenshot({path:root+'/browser-after-render-mobile.png',fullPage:true});
assert.deepEqual(errors,[]);assert.equal(diagnostics.length,2);assert.equal(diagnostics.filter(d=>d.text.includes('503')).length,1);assert.equal(diagnostics.filter(d=>d.text.includes('500')).length,1);
fs.writeFileSync(root+'/browser-results.json',JSON.stringify({origin,title:await fresh.title(),ids,errors,controlledDiagnostics:diagnostics,requests,expected,rows:rows.detections.length,output:paths[ids.alpha]+'/output.mp4',reportPath,checks:['real controlled-OCR scan','same-value no-op skips publisher and still renders','newer different draft across poll503/body deadline/recovery and job switch','no unintended render or duplicate logs','real failed publication retains draft','Save As accepted-byte status separate from polling; full destination bytes','repeated explicit group/zone controls','manual replay ID','all raw rows/indices/audio/additive data after actual render and fresh view']},null,2));
await browser.close();console.log('Task651 actual UI/HTTP/poll/draft/no-op/render/Save As/reopen passed');
})().catch(e=>{console.error(e);process.exit(1)});
