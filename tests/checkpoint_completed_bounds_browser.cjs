const {chromium}=require(process.env.OPENSCRUB_PLAYWRIGHT_MODULE);
const assert=require('node:assert/strict');
const [url]=process.argv.slice(2);
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.OPENSCRUB_CHROMIUM,args:['--no-sandbox']});
 try{
  const context=await browser.newContext({viewport:{width:1100,height:900}});
  try{
   const page=await context.newPage(),errors=[],saves=[];page.setDefaultTimeout(10000);
   page.on('pageerror',e=>errors.push(e.message));
   page.on('console',m=>{if(m.type()==='error'&&!m.text().includes('409'))errors.push(m.text())});
   let released=false;
   await page.route('**/api/jobs/resize/edit_sample?*',async route=>{
    const response=await route.fetch(),body=await response.json();
    if(response.ok())for(const row of body.boxes){
     if(row.i===0){row.scan_frame_bounds=released?null:[0,20];if(released)row.row_context_eq='c'.repeat(64);}
    }
    await route.fulfill({response,json:body});
   });
   await page.route('**/api/jobs/resize/detections',async route=>{
    if(route.request().method()!=='POST')return route.continue();
    const response=await route.fetch(),body=await response.json(),payload=route.request().postDataJSON();
    saves.push(payload);
    if(body.geometry_rows?.['0']&&payload.time_overrides?.['0']){
     body.geometry_rows['0'].scan_frame_bounds=null;body.geometry_rows['0'].row_context_eq='c'.repeat(64);released=true;
    }
    await route.fulfill({response,json:body});
   });
   await page.route('**/api/jobs/resize/render',route=>route.fulfill({status:409,json:{error:'synthetic_render_refusal'}}));
   await page.goto(url);assert.equal(await page.title(),'OpenScrub');
   await page.getByRole('link',{name:'synthetic-resize.mp4',exact:true}).click();
   await page.getByRole('button',{name:/Preview video & edit boxes/}).click();
   await page.waitForFunction(()=>beReady());await page.evaluate(()=>stopPolling());
   await page.locator('#beCv').scrollIntoViewIfNeeded();
   const point=await page.locator('#beCv').evaluate(cv=>{const r=cv.getBoundingClientRect(),im=document.getElementById('beImg');return {x:r.x+200*r.width/im.naturalWidth,y:r.y+150*r.height/im.naturalHeight}});
   await page.mouse.click(point.x,point.y);assert.equal(await page.evaluate(()=>BE.sel),0);
   await page.locator('#beT0').fill('0');await page.locator('#beT1').fill('1.5');
   await page.getByRole('button',{name:'Apply times'}).click();
   assert.deepEqual(await page.evaluate(()=>BE.geometry[0].precondition.scan_frame_bounds),[0,20]);
   await page.getByRole('button',{name:'Save changes & re-render'}).click();
   await page.waitForFunction(()=>!EDITS.busy&&EDITS.status.includes('render was not confirmed'));
   assert.deepEqual(saves[0].geometry_preconditions['0'].scan_frame_bounds,[0,20]);
   assert.equal(await page.evaluate(()=>BE.times[0]),undefined);
   await page.waitForFunction(()=>beReady()&&BE_VIEW.readySample.rows.find(r=>r.i===0)?.scan_frame_bounds===null);
   assert.equal(await page.evaluate(()=>BE_VIEW.readySample.rows.find(r=>r.i===0).row_context_eq),'c'.repeat(64));
   assert.deepEqual(errors,[],JSON.stringify(errors));
   console.log('CHECKPOINT_COMPLETED_BOUNDS_REAL_PAGE_OK');
  }finally{await context.close()}
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
