const {chromium}=require('/tmp/openscrub-save-as-20261116/node_modules/playwright');
const assert=require('node:assert/strict'),fs=require('fs');
const root='/tmp/openscrub-task71',url='http://127.0.0.1:18487';
(async()=>{
 const browser=await chromium.launch({headless:true});const page=await browser.newPage({viewport:{width:1365,height:1000}});
 const errors=[],warnings=[],results=[];page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(['error','warning'].includes(m.type()))warnings.push(m.text())});
 page.on('dialog',d=>d.accept(d.defaultValue()));
 async function fresh(editor=true){await page.goto(url);await page.getByRole('link',{name:'synthetic-alpha.mp4',exact:true}).click();await page.getByRole('button',{name:'Save edits & render',exact:true}).waitFor();
 if(editor){await page.getByRole('button',{name:/Preview video & edit boxes/}).click();await page.waitForFunction(()=>BE.audioLoaded===true);}
 }
 async function addDraft(){await page.locator('#bb0').click();await page.locator('#beAdd').click();await page.locator('#beCv').click({position:{x:50,y:60}});await page.locator('#beCv').click({position:{x:110,y:120}});
 await page.locator('#beMute').click();const r=await page.locator('#beTL').boundingBox();await page.mouse.move(r.x+r.width*0.4,r.y+60);await page.mouse.down();await page.mouse.move(r.x+r.width*0.7,r.y+60);await page.mouse.up();
 assert.equal(await page.evaluate(()=>BE.adds.length),1);assert.equal(await page.evaluate(()=>BE.audio.length),2);
 }
 function saveButton(editor){return page.getByRole('button',{name:editor?'Save changes & re-render':'Save edits & render',exact:true})}
 let renders=[];
 await page.route('**/api/jobs/*/render',async route=>{renders.push(route.request().url());await route.fulfill({json:{ok:true}})});
 for(const editor of [false,true])for(const failure of ['409','423','500','network','json','body']){
  await fresh(true);await addDraft();renders=[];
  await page.route('**/api/jobs/*/detections',async route=>{if(route.request().method()!=='POST')return route.continue();
   if(failure==='network')return route.abort('failed');
   await route.fulfill(failure==='json'?{status:200,contentType:'application/json',body:'{broken'}:{status:failure==='body'?200:+failure,json:{error:'synthetic '+failure}});
  });
  await saveButton(editor).click();await page.getByRole('status').filter({hasText:'Save was not confirmed'}).waitFor();
  assert.deepEqual(await page.evaluate(()=>({manual:BE.adds.length,audio:BE.audio.length})),{manual:1,audio:2});assert.equal(renders.length,0);assert(await page.locator('#beCv').isVisible());assert(await saveButton(editor).isEnabled());
  if(failure==='409'&&editor)await page.screenshot({path:root+'/failed-save.png',fullPage:true});
  results.push({case:`${editor?'editor':'review'} ${failure}`,passed:true});await page.unroute('**/api/jobs/*/detections');
 }
 // Deferred save: toggling back and a new manual/audio draft must survive.
 await fresh();await addDraft();renders=[];let release,submitted;const wait=new Promise(r=>release=r);
 await page.route('**/api/jobs/*/detections',async route=>{if(route.request().method()!=='POST')return route.continue();submitted=route.request().postDataJSON();await wait;await route.fulfill({json:{ok:true}})});
 await saveButton(false).click();await page.waitForFunction(()=>EDITS.busy);await page.locator('#bb0').click();
 await page.evaluate(()=>{BE.adds.push({t0:0,t1:1,tref:0,box:[400,180,450,240]});BE.audio.push({t0:1.5,t1:1.8,mode:'bleep'})});
 // A second entry point while pending is ignored even from keyboard/programmatic invocation.
 await page.evaluate(()=>beSave());release();await page.getByRole('status').filter({hasText:'Newer edits are still pending'}).waitFor();
 assert.equal(renders.length,0);assert.deepEqual(await page.evaluate(()=>({choice:EDITS.enabled[0],manual:BE.adds.length,audio:BE.audio.length})),{choice:true,manual:1,audio:3});assert.equal(submitted.manual.length,1);assert.deepEqual(submitted.enabled,{'0':false});
 await page.screenshot({path:root+'/newer-pending-desktop.png',fullPage:true});await page.setViewportSize({width:390,height:844});await page.screenshot({path:root+'/newer-pending-mobile.png',fullPage:true});await page.setViewportSize({width:1365,height:1000});results.push({case:'deferred newer edits + cross-button duplicate submit',passed:true});await page.unroute('**/api/jobs/*/detections');
 // A -> B -> A owns a fresh view; failed old drafts remain recoverable.
 for(const success of [true,false]){
 await fresh();await addDraft();renders=[];let resume;const gate=new Promise(r=>resume=r);
 await page.route('**/api/jobs/*/detections',async route=>{if(route.request().method()!=='POST')return route.continue();await gate;await route.fulfill({status:success?200:423,json:success?{ok:true}:{error:'busy'}})});
 await saveButton(true).click();await page.waitForFunction(()=>EDITS.busy);await page.getByRole('link',{name:'synthetic-beta.mp4',exact:true}).click();await page.getByRole('link',{name:'synthetic-alpha.mp4',exact:true}).click();await page.waitForFunction(()=>CUR==='alpha');resume();await page.waitForFunction(()=>!EDITS.busy);assert.equal(renders.length,0);assert.equal(await page.evaluate(()=>BE.adds.length),success?0:1);results.push({case:`A B A late ${success?'ack':'rejection'}`,passed:true});await page.unroute('**/api/jobs/*/detections');
 }
 // Allowlist adds another await, during which a new choice must remain pending.
 await fresh();await addDraft();renders=[];let allowResume;const allowGate=new Promise(r=>allowResume=r);
 await page.route('**/api/jobs/*/detections',async route=>route.request().method()==='POST'?route.fulfill({json:{ok:true,suggest_allowlist:['Synthetic QA']}}):route.continue());
 await page.route('**/api/allowlist',async route=>{if(route.request().method()!=='POST')return route.continue();await allowGate;await route.fulfill({json:{ok:true}})});
 await saveButton(true).click();await page.waitForFunction(()=>EDITS.busy&&BE.adds.length===0);await page.locator('#bb0').click();allowResume();await page.getByRole('status').filter({hasText:'Newer edits are still pending'}).waitFor();assert.equal(renders.length,0);results.push({case:'allowlist await preserves new choice',passed:true});await page.unroute('**/api/allowlist');await page.unroute('**/api/jobs/*/detections');
 // Save acknowledged, render rejected: retry does not append committed additions.
 await fresh();await addDraft();let bodies=[];await page.route('**/api/jobs/*/detections',async route=>{if(route.request().method()!=='POST')return route.continue();bodies.push(route.request().postDataJSON());await route.fulfill({json:{ok:true}})});
 await page.unroute('**/api/jobs/*/render');let renderCount=0;await page.route('**/api/jobs/*/render',async route=>{renderCount++;await route.fulfill({status:renderCount===1?500:200,json:renderCount===1?{error:'synthetic render failure'}:{ok:true}})});
 await saveButton(true).click();await page.getByRole('status').filter({hasText:'render was not confirmed'}).waitFor();assert.equal(await page.evaluate(()=>BE.adds.length),0);await saveButton(true).click();await page.getByRole('status').filter({hasText:'Rendering with saved edits'}).waitFor();assert.equal(bodies[0].manual.length,1);assert.equal(bodies[1].manual.length,0);results.push({case:'render rejection retries without committed manual additions',passed:true});await page.unroute('**/api/jobs/*/detections');await page.unroute('**/api/jobs/*/render');
 // Actual HTTP save + actual engine render, with all payload kinds verified before rendering.
 await fresh();await addDraft();await page.evaluate(()=>{BE.ov[1]=[160,50,250,140];BE.times[1]=[0.2,1.8]});
 let savedReport,sent;await page.route('**/api/jobs/alpha/detections',async route=>{if(route.request().method()!=='POST')return route.continue();sent=route.request().postDataJSON();const response=await route.fetch();savedReport=await (await page.request.get(url+'/api/jobs/alpha/report')).json();await route.fulfill({response});});
 await saveButton(true).click();await page.getByRole('status').filter({hasText:'Rendering with saved edits'}).waitFor();
 assert.deepEqual(sent.enabled,{'0':false});assert.equal(savedReport.detections[0].enabled,false);assert.deepEqual(savedReport.detections[1].cbox,[160,50,250,140]);assert.equal(savedReport.detections[1].t_start,0.2);assert.equal(savedReport.detections[1].t_end,1.8);assert.equal(savedReport.detections.length,3);assert.equal(savedReport.audio_redactions.length,2);
 let actual;for(let attempt=0;attempt<900;attempt++){
  actual=await page.evaluate(async()=>await(await fetch('api/jobs/alpha?qa='+Date.now(),{cache:'no-store'})).json());
  if(actual.phase==='error')throw Error(actual.error);if(actual.phase==='done'&&actual.has_output)break;
  await page.waitForTimeout(100);
 }
 fs.writeFileSync(root+'/actual-job.json',JSON.stringify(actual,null,2));assert.equal(actual.phase,'done');assert.equal(actual.has_output,true);const download=await page.request.get(url+'/api/jobs/alpha/download');assert(download.ok());fs.writeFileSync(root+'/actual-output.mp4',await download.body());fs.writeFileSync(root+'/actual-saved-report.json',JSON.stringify(savedReport,null,2));
 results.push({case:'actual HTTP save + engine render',passed:true,payload:sent,phase:actual.phase,outputBytes:(await download.body()).length});
 await page.screenshot({path:root+'/actual-render-done.png',fullPage:true});
 const identity={url:page.url(),title:await page.title(),nonblank:(await page.locator('body').innerText()).includes('OpenScrub'),overlay:await page.locator('vite-error-overlay,nextjs-portal').count()};
 fs.writeFileSync(root+'/browser-results.json',JSON.stringify({environment:{browser:'Chromium headless Linux',plugin:'Browser plugin not available',viewports:['1365x1000','390x844']},identity,errors,warnings,results},null,2));
 assert.deepEqual(errors,[]);assert.equal(identity.overlay,0);console.log(JSON.stringify({passed:results.length,identity,errors,warnings},null,2));await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
