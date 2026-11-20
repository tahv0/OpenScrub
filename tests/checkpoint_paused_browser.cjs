const {chromium}=require(process.env.OPENSCRUB_PLAYWRIGHT_MODULE);
const assert=require('node:assert/strict'),fs=require('node:fs');
const [url,root]=process.argv.slice(2);
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.OPENSCRUB_CHROMIUM,args:['--no-sandbox']});
 try{
  const context=await browser.newContext({viewport:{width:1100,height:900},deviceScaleFactor:1});
  try{
   const page=await context.newPage(),errors=[],samples=[],writes=[],saves=[],resumes=[],unsupported=[];page.setDefaultTimeout(10000);
   page.on('pageerror',e=>errors.push(e.message));
   page.on('console',m=>{if(m.type()==='error'&&!/400|409/.test(m.text()))errors.push(m.text())});
   page.on('request',r=>{
    if(r.url().includes('/resize/edit_sample?'))samples.push(Number(new URL(r.url()).searchParams.get('t')));
    if(/\/resize\/(video|boxes_at|frame_at)(\?|$)/.test(r.url()))unsupported.push(r.url());
    if(r.method()==='POST'&&/\/(render|track_object)$/.test(r.url()))writes.push(r.url());
    if(r.method()==='POST'&&r.url().endsWith('/resume'))resumes.push(r.postDataJSON());
   });
   const dialogAnswers=[];
   page.on('dialog',d=>d.accept(dialogAnswers.length?dialogAnswers.shift():d.defaultValue()));
   await page.route('**/api/jobs/resize',async route=>{
    if(route.request().method()!=='GET')return route.continue();
    const response=await route.fetch(),body=await response.json();
    Object.assign(body,{phase:'paused',checkpoint_unfinished:true,has_output:false});
    await route.fulfill({response,json:body});
   });
   let releasedBounds=false;
   await page.route('**/api/jobs/resize/edit_sample?*',async route=>{
    const response=await route.fetch(),body=await response.json();
    if(response.ok())for(const row of body.boxes){
     row.scan_frame_bounds=row.i===0&&!releasedBounds?[0,8]:null;
     if(row.i===0&&releasedBounds)row.row_context_eq='b'.repeat(64);
    }
    await route.fulfill({response,json:body});
   });
   let holdSave=null,rejectSave=false,loseSaveAck=false,processedFrames=8,processedDuration=.8;
   await page.route('**/api/jobs/resize/detections',async route=>{
    if(route.request().method()==='POST'&&rejectSave){
     rejectSave=false;return route.fulfill({status:400,json:{error:'invalid_sample_request'}});
    }
    const response=await route.fetch(),body=await response.json();
    if(route.request().method()==='GET')Object.assign(body,{duration:2,fps:10,processed_duration:processedDuration,processed_frames:processedFrames,total_frames:20});
    else {saves.push(route.request().postDataJSON());body.resume_token='opaque-fixture-token';
     if(body.geometry_rows?.['0']&&saves.at(-1).time_overrides?.['0']){
      body.geometry_rows['0'].row_context_eq='b'.repeat(64);body.geometry_rows['0'].scan_frame_bounds=null;releasedBounds=true;
     }
     if(loseSaveAck){loseSaveAck=false;return route.fulfill({status:200,contentType:'text/plain',body:'lost acknowledgement'});}
     if(holdSave){const held=holdSave;holdSave=null;held.start();await held.gate;}}
    await route.fulfill({response,json:body});
   });
   let holdResume=null;
   await page.route('**/api/jobs/resize/resume',async route=>{
    if(holdResume){const held=holdResume;holdResume=null;held.start();await held.gate;}
    await route.fulfill({status:202,json:{ok:true,state:'running'}});
   });
   const hold=()=>{let release,start;const gate=new Promise(r=>release=r),started=new Promise(r=>start=r);return {gate,started,start,release};};
   await page.goto(url);assert.equal(await page.title(),'OpenScrub');
   assert((await page.locator('body').innerText()).includes('OpenScrub'));
   assert.equal(await page.locator('vite-error-overlay,nextjs-portal').count(),0);
   async function openPaused(){
    await page.getByRole('link',{name:'synthetic-resize.mp4',exact:true}).click();
    await page.getByRole('button',{name:/Preview video & edit boxes/}).click();
    await page.waitForFunction(()=>beReady());await page.evaluate(()=>stopPolling());
   }
   await openPaused();
   assert((await page.locator('#review').innerText()).includes('8 of 20'));
   assert.equal(await page.locator('#bePlay').isVisible(),false);
   assert.equal(await page.locator('#beTrk').isVisible(),false);
   assert.equal(await page.getByRole('button',{name:/^Save .*render/i}).count(),0);
   assert((await page.locator('#beslot').innerText()).includes('Automatic audio scanning is incomplete'));
   await page.evaluate(()=>{beTogglePlay();beTrackMode()});assert.deepEqual(unsupported,[]);
   assert.equal(await page.locator('#beT').getAttribute('max'),'7');
   await page.locator('#beT').fill('7');await page.locator('#beT').dispatchEvent('input');
   await page.waitForFunction(()=>beReady()&&BE_VIEW.readySample.sample.index===7);
   assert(samples.every(t=>t>=0&&t<.8),JSON.stringify(samples));
   const last=samples.length;await page.evaluate(()=>beRequestSample(BE_VIEW,.8));
   await page.waitForTimeout(100);assert.equal(samples.length,last);
   await page.locator('#beT').fill('7');await page.locator('#beT').dispatchEvent('input');
   await page.waitForFunction(()=>beReady()&&BE_VIEW.readySample.sample.index===7);
   await page.locator('#beCv').scrollIntoViewIfNeeded();
   async function point(x,y){return page.locator('#beCv').evaluate((cv,[x,y])=>{const r=cv.getBoundingClientRect(),im=document.getElementById('beImg');return {x:r.x+x*r.width/im.naturalWidth,y:r.y+y*r.height/im.naturalHeight}},[x,y]);}
   await page.locator('#beAdd').click();dialogAnswers.push('0','0.9');
   const firstPoint=await point(350,220);await page.mouse.click(firstPoint.x,firstPoint.y);
   await page.getByRole('button',{name:'Save & Resume',exact:true}).first().click();
   await page.waitForTimeout(250);assert.equal(saves.length,0);assert.equal(resumes.length,0);
   await page.locator('#beCv').scrollIntoViewIfNeeded();
   const secondPoint=await point(420,260);await page.mouse.click(secondPoint.x,secondPoint.y);
   assert.equal(await page.evaluate(()=>BE.adds.length),0);
   for(const xy of [[350,220],[420,260]]){const p=await point(...xy);await page.mouse.click(p.x,p.y)}
   assert.equal(await page.evaluate(()=>BE.adds.length),1);
   assert.equal(await page.evaluate(()=>BE.adds[0].t1),.8);
   await page.locator('#beAdd').click();const selected=await point(200,150);await page.mouse.click(selected.x,selected.y);
   assert.equal(await page.evaluate(()=>BE.sel),0);
   await page.locator('#beT0').fill('0.1');await page.locator('#beT1').fill('0.8');
   await page.getByRole('button',{name:'Apply times'}).click();
   assert.deepEqual(await page.evaluate(()=>BE.geometry[0].precondition.scan_frame_bounds),[0,8]);
   await page.locator('#beMute').click();
   const timeline=await page.locator('#beTL').boundingBox();
   await page.mouse.move(timeline.x+timeline.width*.2,timeline.y+60);await page.mouse.down();
   await page.mouse.move(timeline.x+timeline.width*.95,timeline.y+60);await page.mouse.up();
   assert.equal(await page.evaluate(()=>BE.audio.length),1);
   assert(await page.evaluate(()=>BE.audio[0].t1<=BE.dur&&BE.dur===.8));
   // A confirmed 4xx leaves drafts editable, with no automatic resume.
   rejectSave=true;await page.getByRole('button',{name:'Save & Resume',exact:true}).first().click();
   await page.waitForFunction(()=>!EDITS.busy);
   assert.equal(await page.evaluate(()=>EDITS.submitted),null);
   assert.equal(await page.evaluate(()=>BE.adds.length),1);assert.deepEqual(await page.evaluate(()=>BE.times[0]),[.1,.8]);
   assert.equal(resumes.length,0);
   // A committed save with an unreadable ACK remains uncertain and must be
   // retried identically before newer edits can trigger another action.
   loseSaveAck=true;await page.getByRole('button',{name:'Save & Resume',exact:true}).first().click();
   await page.waitForFunction(()=>!EDITS.busy&&EDITS.submitted?.everUncertain);
   assert.equal(resumes.length,0);assert.equal(await page.evaluate(()=>BE.adds.length),1);
   // Edits arriving while a save is in flight cancel this resume attempt.
   holdSave=hold();const firstSave=holdSave;
   await page.getByRole('button',{name:'Save & Resume',exact:true}).first().click();await firstSave.started;
   await page.evaluate(()=>applyDet(0,false));firstSave.release();
   await page.waitForFunction(()=>!EDITS.busy&&hasReviewEdits(EDITS));
   assert.equal(resumes.length,0);assert.equal(await page.evaluate(()=>EDITS.enabled[0]),false);
   assert.deepEqual(saves[1],saves[0]);
   assert.equal(saves[0].manual[0].t_end,.8);
   assert.deepEqual(saves[0].geometry_preconditions['0'].scan_frame_bounds,[0,8]);
   await page.waitForFunction(()=>beReady()&&BE_VIEW.readySample.rows.find(r=>r.i===0)?.scan_frame_bounds===null);
   assert.equal(await page.evaluate(()=>BE_VIEW.readySample.rows.find(r=>r.i===0).row_context_eq),'b'.repeat(64));
   // A saved response after A→B→A must not resume the old view.
   holdSave=hold();const stale=holdSave;
   await page.getByRole('button',{name:'Save & Resume',exact:true}).first().click();await stale.started;
   await page.getByRole('link',{name:'synthetic-other.mp4',exact:true}).click();
   await page.waitForFunction(()=>CUR==='other');await openPaused();
   await page.evaluate(()=>applyDet(0,true));stale.release();
   await page.waitForFunction(()=>!REVIEW_DRAFTS.get('resize').busy);
   assert.equal(resumes.length,0);assert.equal(await page.evaluate(()=>EDITS.enabled[0]),true);
   // Resume receives the exact token from the acknowledged save. A newer edit
   // during the resume request survives instead of being discarded.
   holdResume=hold();const pending=holdResume;
   await page.getByRole('button',{name:'Save & Resume',exact:true}).first().click();await pending.started;
   await page.evaluate(()=>applyDet(0,false));pending.release();
   await page.waitForFunction(()=>!EDITS.busy);
   assert.deepEqual(resumes,[{resume_token:'opaque-fixture-token'}]);
   assert.equal(await page.evaluate(()=>EDITS.enabled[0]),false);
   assert((await page.locator('#reviewSaveStatus').innerText()).includes('pending'));
   assert.deepEqual(writes,[]);assert.deepEqual(unsupported,[]);assert.deepEqual(errors,[],JSON.stringify(errors));
   await page.screenshot({path:root+'/checkpoint-paused.png',fullPage:true});
   await page.setViewportSize({width:390,height:844});
   await page.screenshot({path:root+'/checkpoint-paused-mobile.png',fullPage:true});
   // A one-frame prefix still permits an in-prefix audio span and has only
   // its one inspectable frame; rounding to tenths must not erase it.
   processedFrames=1;processedDuration=.1;await page.reload();await openPaused();
   assert.equal(await page.locator('#beT').getAttribute('max'),'0');
   assert.equal(await page.evaluate(()=>BE_VIEW.readySample.sample.index),0);
   await page.locator('#beMute').click();await page.locator('#beTL').scrollIntoViewIfNeeded();
   const tiny=await page.locator('#beTL').boundingBox();
   await page.mouse.move(tiny.x+tiny.width*.1,tiny.y+60);await page.mouse.down();
   await page.mouse.move(tiny.x+tiny.width*.9,tiny.y+60);await page.mouse.up();
   assert.equal(await page.evaluate(()=>BE.audio.length),1);
   assert(await page.evaluate(()=>BE.audio[0].t0>=0&&BE.audio[0].t1<=.1));
   fs.writeFileSync(root+'/checkpoint-paused-result.json',JSON.stringify({samples,saves,resumes,writes}));
   console.log('CHECKPOINT_PAUSED_REAL_PAGE_OK');
  }finally{await context.close()}
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
