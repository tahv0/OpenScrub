const {chromium}=require(process.env.OPENSCRUB_PLAYWRIGHT_MODULE);
const assert=require('node:assert/strict');
const [url]=process.argv.slice(2);
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.OPENSCRUB_CHROMIUM,args:['--no-sandbox']});
 try{
  const page=await browser.newPage({viewport:{width:1100,height:900}}),errors=[],saves=[],resumes=[],samples=[];
  page.setDefaultTimeout(15000);
  page.on('pageerror',e=>errors.push(e.message));
  page.on('console',m=>{if(m.type()==='error'&&!/409/.test(m.text()))errors.push(m.text())});
  page.on('dialog',d=>d.accept(d.defaultValue()));
  page.on('request',r=>{
   if(r.url().includes('/checkpoint/edit_sample?'))samples.push(Number(new URL(r.url()).searchParams.get('t')));
   if(r.method()==='POST'&&r.url().endsWith('/checkpoint/detections'))saves.push(r.postDataJSON());
   if(r.method()==='POST'&&r.url().endsWith('/checkpoint/resume'))resumes.push(r.postDataJSON());
  });
  await page.route('**/api/jobs/checkpoint/resume',route=>route.fulfill({status:202,json:{ok:true,state:'queued'}}));
  await page.goto(url);await page.getByRole('link',{name:'real-checkpoint.mp4',exact:true}).click();
  await page.getByRole('button',{name:/Preview video & edit boxes/}).click();
  await page.waitForFunction(()=>beReady());await page.evaluate(()=>stopPolling());
  assert((await page.locator('#review').innerText()).includes('9 of 24'));
  const meta=await(await page.request.get(url+'/api/jobs/checkpoint/detections')).json();
  assert.equal(meta.processed_duration,1.5);assert.equal(meta.fps,6);assert.equal(meta.processed_frames,9);
  assert.equal(await page.locator('#beT').getAttribute('max'),'8');
  await page.locator('#beT').fill('8');await page.locator('#beT').dispatchEvent('input');
  await page.waitForFunction(()=>beReady()&&BE_VIEW.readySample.sample.index===8);
  assert(samples.every(t=>t>=0&&t<1.5));
  assert.equal(await page.locator('#bePlay').isVisible(),false);
  assert.equal(await page.locator('#beTrk').isVisible(),false);
  await page.locator('#beCv').scrollIntoViewIfNeeded();await page.locator('#beAdd').click();
  for(const [x,y] of [[10,10],[50,50]]){
   const p=await page.locator('#beCv').evaluate((cv,[x,y])=>{const r=cv.getBoundingClientRect(),im=document.getElementById('beImg');return {x:r.x+x*r.width/im.naturalWidth,y:r.y+y*r.height/im.naturalHeight}},[x,y]);
   await page.mouse.click(p.x,p.y);
  }
  assert.equal(await page.evaluate(()=>BE.adds.length),1);
  const manual=await page.evaluate(()=>BE.adds[0]);assert(manual.t1<=1.5);
  await page.getByRole('button',{name:'Save & Resume',exact:true}).first().click();
  await page.waitForFunction(()=>!EDITS.busy&&EDITS.status.includes('resuming'));
  assert.equal(saves.length,1);assert.equal(resumes.length,1);
  assert.match(resumes[0].resume_token,/^[a-f0-9]{64}$/);
  assert.equal(saves[0].manual[0].manual_id,manual.manual_id);
  const report=await(await page.request.get(url+'/api/jobs/checkpoint/report')).json();
  assert.equal(report.detections.filter(row=>row.manual_id===manual.manual_id).length,1);
  assert.deepEqual(errors,[],JSON.stringify(errors));
  console.log('CHECKPOINT_ACTUAL_BACKEND_PAGE_OK',JSON.stringify({samples,resumes}));
  await page.close();
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
