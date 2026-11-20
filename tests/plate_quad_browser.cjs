const {chromium}=require(process.env.OPENSCRUB_PLAYWRIGHT_MODULE);
const assert=require('node:assert/strict'),fs=require('node:fs');
const [url,root]=process.argv.slice(2);
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.OPENSCRUB_CHROMIUM});
 const page=await browser.newPage({viewport:{width:1100,height:950},deviceScaleFactor:1}),errors=[],warnings=[],posts=[],responses=[];
 page.on('pageerror',e=>errors.push(e.message));
 page.on('console',m=>{if(['error','warning'].includes(m.type()))warnings.push({text:m.text(),url:m.location().url})});
 page.on('dialog',d=>d.accept(d.defaultValue()));
 page.on('request',r=>{if(r.method()==='POST')posts.push({url:r.url(),body:r.postDataJSON()})});
 page.on('response',r=>{if(r.status()===409&&/\/(thumb|detframe)\/\d+\?v=/.test(r.url()))
  responses.push((async()=>{try{const body=await r.json();return {url:r.url(),error:body.error}}catch{return {url:r.url()}}})())});
 const point=async(x,y)=>page.locator('#beCv').evaluate((cv,p)=>{const r=cv.getBoundingClientRect(),im=document.getElementById('beImg');
  return {x:r.x+p[0]*r.width/im.naturalWidth,y:r.y+p[1]*r.height/im.naturalHeight}},[x,y]);
 const drag=async(from,to)=>{await page.locator('#beCv').scrollIntoViewIfNeeded();const a=await point(...from),b=await point(...to);await page.mouse.move(a.x,a.y);await page.mouse.down();await page.mouse.move(b.x,b.y,{steps:3});await page.mouse.up()};
 try{
  await page.goto(url);assert.equal(await page.title(),'OpenScrub');assert.match(await page.locator('body').innerText(),/OpenScrub/);
  assert.equal(await page.locator('vite-error-overlay,nextjs-portal').count(),0);
  await page.getByRole('link',{name:'synthetic-plate.mp4',exact:true}).click();
  await page.getByRole('button',{name:/Preview video & edit boxes/}).click();await page.waitForFunction(()=>beReady());
  await page.evaluate(()=>stopPolling());
  const middle=await point(240,160);await page.mouse.click(middle.x,middle.y);assert.equal(await page.evaluate(()=>BE.sel),0);
  assert.match(await page.locator('#beQuadStatus').innerText(),/only to this inspected frame/);
  assert.match(await page.locator('#beQuadStatus').innerText(),/verified on Save/);
  await page.getByRole('button',{name:'Edit plate corners',exact:true}).click();
  let corners=await page.evaluate(()=>BE_VIEW.quadEdit.points);assert.deepEqual(corners,[[140,92],[340,92],[340,232],[140,232]]);
  await drag(corners[0],[175,110]);corners=await page.evaluate(()=>BE_VIEW.quadEdit.points);
  await drag(corners[1],[310,105]);
  await page.setViewportSize({width:390,height:844});await page.waitForTimeout(120);
  assert(await page.evaluate(()=>!!BE_VIEW.quadEdit&&BE.drag===null));corners=await page.evaluate(()=>BE_VIEW.quadEdit.points);
  await drag(corners[2],[315,210]);corners=await page.evaluate(()=>BE_VIEW.quadEdit.points);await drag(corners[3],[170,215]);
  const initial=await page.evaluate(()=>BE.quads[0].points);
  console.log('CORNER_DRAG_DIAGNOSTIC',JSON.stringify({initial,viewport:page.viewportSize(),canvas:await page.locator('#beCv').boundingBox(),scroll:await page.evaluate(()=>scrollY)}));
  for(let i=0;i<4;i++)for(let j=0;j<2;j++)assert(Math.abs(initial[i][j]-[[175,110],[310,105],[315,210],[170,215]][i][j])<2);
  await page.screenshot({path:root+'/mobile-corners.png',fullPage:true});
  let release,committed;const gate=new Promise(r=>release=r),started=new Promise(r=>committed=r);let first=true,ack;
  await page.route('**/api/jobs/plate/detections',async route=>{
   if(route.request().method()!=='POST')return route.continue();
   const response=await route.fetch();
   if(first){first=false;ack=await response.json();committed();await gate;
    return route.fulfill({status:200,contentType:'text/plain',body:'lost committed acknowledgement'});}
   return route.fulfill({response});
  });
  await page.getByRole('button',{name:'Save changes & re-render',exact:true}).click();await started;
  corners=await page.evaluate(()=>BE_VIEW.quadEdit.points);await drag(corners[0],[180,115]);
  await page.evaluate(()=>{applyDet(1,true);BE.audio=[{t0:0,t1:.1,mode:'mute'}];BE.audioLoaded=true});
  const newer=await page.evaluate(()=>BE.quads[0].points);release();
  await page.waitForFunction(()=>EDITS.submitted?.everUncertain&&!EDITS.busy);
  assert(ack.geometry_rows['0'].manual_plate_quad);
  await page.getByRole('button',{name:'Save changes & re-render',exact:true}).click();
  await page.waitForFunction(()=>!EDITS.busy&&!EDITS.submitted&&!!BE.quads[0]);
  let saves=posts.filter(p=>p.url.endsWith('/plate/detections'));assert.deepEqual(saves[1].body,saves[0].body);
  assert.deepEqual(await page.evaluate(()=>BE.quads[0].points),newer);
  assert.equal(posts.filter(p=>p.url.endsWith('/plate/render')).length,0);
  await page.getByRole('button',{name:'Save changes & re-render',exact:true}).click();
  await page.waitForFunction(()=>!EDITS.busy&&EDITS.status.includes('Rendering with saved edits'));
  saves=posts.filter(p=>p.url.endsWith('/plate/detections'));assert.equal(saves.length,3);
  assert.deepEqual(saves[2].body.manual_plate_quads['0'].points,newer);
  const saved=await(await page.request.get(url+'/api/jobs/plate/report')).json();
  const record=saved.detections[0].manual_plate_quad;assert(record);assert.equal(record.frame.index,0);
  for(let i=0;i<4;i++){assert(Math.abs(record.points[i][0]*640-newer[i][0])<1e-8);assert(Math.abs(record.points[i][1]*360-newer[i][1])<1e-8)}
  assert.deepEqual(saved.detections[0].opaque,{keep:true});assert.equal(saved.detections[1].enabled,true);assert.equal(saved.audio_redactions.length,1);
  let job;for(let i=0;i<900;i++){job=await(await page.request.get(url+'/api/jobs/plate')).json();if(job.phase==='error')throw Error(job.error);if(job.phase==='done'&&job.has_output)break;await page.waitForTimeout(100)}
  assert.equal(job.phase,'done');const output=await page.request.get(url+'/api/jobs/plate/download');assert(output.ok());
  fs.writeFileSync(root+'/actual-output.mp4',await output.body());fs.writeFileSync(root+'/saved-report.json',JSON.stringify(saved,null,2));
  await page.reload();await page.getByRole('link',{name:'synthetic-plate.mp4',exact:true}).click();
  await page.getByRole('button',{name:'Preview & edit blur boxes',exact:true}).click();await page.waitForFunction(()=>beReady());
  const pt=await point(240,160);await page.mouse.click(pt.x,pt.y);
  assert.equal(await page.evaluate(()=>BE.raw.find(r=>r.i===0).quad_eligibility),'eligible_sdr_frame');
  await page.getByRole('button',{name:'Edit plate corners',exact:true}).click();
  const restored=await page.evaluate(()=>BE_VIEW.quadEdit.points);
  for(let i=0;i<4;i++)for(let j=0;j<2;j++)assert(Math.abs(restored[i][j]-newer[i][j])<1e-8);
  await page.screenshot({path:root+'/reopened-corners.png',fullPage:true});
  // Ordinary box resize on a real saved quad must retire it atomically.  The
  // witness is the exact server-issued byte string, not a JSON reconstruction.
  const witness=await page.evaluate(()=>{const r=BE.raw.find(r=>r.i===0);return {token:r.quad_baseline,context:r.quad_context_eq}});
  assert.equal(typeof witness.token,'string');assert.equal(typeof witness.context,'string');
  await page.getByRole('button',{name:'Done editing corners',exact:true}).click();
  await drag([340,232],[370,250]);
  const resized=await page.evaluate(()=>BE.ov[0]);assert(resized[2]>365&&resized[3]>245);
  assert.match(await page.locator('#beQuadStatus').innerText(),/pending box change restores the full plate mask/);
  await page.getByRole('button',{name:'Save changes & re-render',exact:true}).click();
  await page.waitForFunction(()=>!EDITS.busy&&EDITS.status.includes('Rendering with saved edits'));
  const resizePayload=posts.filter(p=>p.url.endsWith('/plate/detections')).at(-1).body;
  assert.equal(resizePayload.geometry_preconditions['0'].quad_baseline,witness.token);
  assert.equal(resizePayload.geometry_preconditions['0'].quad_context_eq,witness.context);
  assert(!resizePayload.manual_plate_quads||!Object.hasOwn(resizePayload.manual_plate_quads,'0'));
  const resizedReport=await(await page.request.get(url+'/api/jobs/plate/report')).json();
  assert(!Object.hasOwn(resizedReport.detections[0],'manual_plate_quad'));
  for(let i=0;i<4;i++)assert(Math.abs(resizedReport.detections[0].cbox[i]-resized[i])<1e-8);
  let resizedJob;for(let i=0;i<900;i++){resizedJob=await(await page.request.get(url+'/api/jobs/plate')).json();
   if(resizedJob.phase==='error')throw Error(resizedJob.error);if(resizedJob.phase==='done'&&resizedJob.has_output)break;await page.waitForTimeout(100)}
  assert.equal(resizedJob.phase,'done');const resizedOutput=await page.request.get(url+'/api/jobs/plate/download');assert(resizedOutput.ok());
  fs.writeFileSync(root+'/resized-output.mp4',await resizedOutput.body());
  fs.writeFileSync(root+'/resized-report.json',JSON.stringify(resizedReport,null,2));
  // Restore a quad through the visible editor so the separate reset control
  // also acts against an actually persisted record.
  await page.reload();await page.getByRole('link',{name:'synthetic-plate.mp4',exact:true}).click();
  await page.getByRole('button',{name:'Preview & edit blur boxes',exact:true}).click();await page.waitForFunction(()=>beReady());
  const center=await point(240,160);await page.mouse.click(center.x,center.y);
  await page.getByRole('button',{name:'Edit plate corners',exact:true}).click();
  const afterResize=await page.evaluate(()=>BE_VIEW.quadEdit.points);await drag(afterResize[0],[175,110]);
  await page.getByRole('button',{name:'Save changes & re-render',exact:true}).click();
  await page.waitForFunction(()=>!EDITS.busy&&EDITS.status.includes('Rendering with saved edits'));
  const restoredReport=await(await page.request.get(url+'/api/jobs/plate/report')).json();assert(restoredReport.detections[0].manual_plate_quad);
  let restoredJob;for(let i=0;i<900;i++){restoredJob=await(await page.request.get(url+'/api/jobs/plate')).json();
   if(restoredJob.phase==='error')throw Error(restoredJob.error);if(restoredJob.phase==='done'&&restoredJob.has_output)break;await page.waitForTimeout(100)}
  assert.equal(restoredJob.phase,'done');
  await page.reload();await page.getByRole('link',{name:'synthetic-plate.mp4',exact:true}).click();
  await page.getByRole('button',{name:'Preview & edit blur boxes',exact:true}).click();await page.waitForFunction(()=>beReady());
  const resetCenter=await point(240,160);await page.mouse.click(resetCenter.x,resetCenter.y);
  // Explicit reset uses the inspected row context and the opaque baseline token.
  await page.getByRole('button',{name:'Reset to full plate mask',exact:true}).click();
  assert.equal(await page.evaluate(()=>BE.quads[0]),null);
  await page.getByRole('button',{name:'Save changes & re-render',exact:true}).click();
  await page.waitForFunction(()=>!EDITS.busy&&EDITS.status.includes('Rendering with saved edits'));
  const resetPayload=posts.filter(p=>p.url.endsWith('/plate/detections')).at(-1).body;
  assert.equal(resetPayload.manual_plate_quads['0'],null);assert.equal(typeof resetPayload.geometry_preconditions['0'].quad_baseline,'string');
  const reset=await(await page.request.get(url+'/api/jobs/plate/report')).json();
  assert(!Object.prototype.hasOwnProperty.call(reset.detections[0],'manual_plate_quad'));
  let resetJob;for(let i=0;i<900;i++){resetJob=await(await page.request.get(url+'/api/jobs/plate')).json();
   if(resetJob.phase==='error')throw Error(resetJob.error);if(resetJob.phase==='done'&&resetJob.has_output)break;await page.waitForTimeout(100)}
  assert.equal(resetJob.phase,'done');const resetOutput=await page.request.get(url+'/api/jobs/plate/download');assert(resetOutput.ok());
  fs.writeFileSync(root+'/reset-output.mp4',await resetOutput.body());
  assert.deepEqual(errors,[]);
  const conflicts=await Promise.all(responses);
  const unexpected=warnings.filter(w=>!w.text.includes('409')||!conflicts.some(c=>c.url===w.url&&['thumbnail_obsolete','thumbnail_pending'].includes(c.error)));
  assert.deepEqual(unexpected,[],JSON.stringify(warnings));
  fs.writeFileSync(root+'/browser-result.json',JSON.stringify({initial,newer,restored,resized,witness,posts,errors,warnings,render:job.phase,reset:true},null,2));
  console.log('PLATE_QUAD_PAGE_LOST_ACK_RESIZE_RENDER_REOPEN_OK');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
