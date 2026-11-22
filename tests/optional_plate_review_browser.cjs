const {chromium}=require(process.env.OPENSCRUB_PLAYWRIGHT_MODULE);
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const [url,root]=process.argv.slice(2),fixture=JSON.parse(fs.readFileSync(path.join(root,'runtime/fixture.json')));
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.OPENSCRUB_CHROMIUM,args:['--no-sandbox']});
 try{
  for(const [label,width,height] of [['desktop',1365,1000],['mobile',390,844]]){
   const page=await browser.newPage({viewport:{width,height}}),errors=[],warnings=[];
   page.on('pageerror',e=>errors.push(e.message));
   page.on('console',m=>{if(['error','warning'].includes(m.type()))warnings.push(m.text())});
   page.on('dialog',d=>d.accept());
   await page.goto(url);assert.equal(await page.title(),'OpenScrub');
   assert((await page.locator('body').innerText()).includes('OpenScrub'));
   assert.equal(await page.locator('vite-error-overlay,nextjs-portal').count(),0);
   const metadata=await page.request.get(url+'/api/jobs/'+fixture.jobs[label]+'/detections');
   assert.equal(metadata.status(),200,await metadata.text());
   await page.getByRole('link',{name:'policy-review-'+label+'.mp4',exact:true}).click();
   await page.locator('#reviewSection0').scrollIntoViewIfNeeded();
   try{await page.waitForSelector('#ds1',{timeout:7000})}catch(e){
    console.error('REVIEW_STATE',JSON.stringify(await page.evaluate(()=>({cards:[...document.querySelectorAll('.det')].map(x=>x.id),review:document.getElementById('review')?.innerText,detail:document.getElementById('detail')?.innerText,errors:document.getElementById('review-load-error')?.innerText}))));
    console.error('PAGE_ERRORS',JSON.stringify({errors,warnings}));throw e;
   }
   const before=await page.locator('#ds1').innerText();
   // Frames 1-2 support an automatic mask that covers the whole track,
   // including the low-support first hit and the interpolated sample.
   assert(before.includes('3 of 3 samples will be blurred'),before);
   assert(before.includes('3 automatic masks'),before);
   assert(!before.includes('uncertain observation'),before);
   assert(!before.includes('unsupported sample'),before);
   assert((await page.locator('#review').innerText()).includes('Plate policy: Review uncertain'));
   assert.equal(await page.locator('#bb1').getAttribute('aria-pressed'),'false');
   assert.equal(await page.locator('#kb1').getAttribute('aria-pressed'),'false');
   await page.locator('#review').screenshot({path:path.join(root,'unhandled-'+label+'.png')});
   await page.getByRole('button',{name:/Preview video & edit boxes/}).click();
   await page.waitForFunction(()=>beReady());
   await page.locator('#beT').fill('0.2');await page.locator('#beT').dispatchEvent('input');
   await page.waitForFunction(()=>beReady()&&BE_VIEW.readySample.sample.index===1);
   assert.deepEqual(await page.evaluate(()=>BE.raw.map(r=>r.i)),[0]);
   // Row 0 belongs to the automatically masked track, so its box is active.
   assert.deepEqual(await page.evaluate(()=>BE.boxes.map(r=>r.i)),[0]);
   await page.locator('#beT').fill('0.4');await page.locator('#beT').dispatchEvent('input');
   await page.waitForFunction(()=>beReady()&&BE_VIEW.readySample.sample.index===2);
   assert.deepEqual(await page.evaluate(()=>BE.raw.map(r=>r.i)),[1]);
   assert.deepEqual(await page.evaluate(()=>BE.boxes.map(r=>r.i)),[1]);
   await page.locator('#beAdd').click();assert(await page.locator('#beAdd').evaluate(e=>e.classList.contains('on')));
   await page.locator('#beAdd').click();
   await page.locator('#beTrk').click();assert(await page.locator('#beTrk').evaluate(e=>e.classList.contains('on')));
   await page.locator('#beTrk').click();
   await page.locator('#reviewSection0').scrollIntoViewIfNeeded();
   await page.locator('#kb1').click();
   assert.equal(await page.locator('#kb1').getAttribute('aria-pressed'),'true');
   const saved=page.waitForResponse(r=>r.url().endsWith('/detections')&&r.request().method()==='POST');
   const rendered=page.waitForResponse(r=>r.url().endsWith('/render')&&r.request().method()==='POST');
   await page.getByRole('button',{name:'Save edits & render',exact:true}).click();assert.equal((await saved).status(),200);
   await rendered;
   const report=await (await page.request.get(url+'/api/jobs/'+fixture.jobs[label]+'/report')).json();
   assert.deepEqual(report.detections.map(r=>r.output_choice),['keep','keep','keep']);
   assert.deepEqual(report.detections.map(r=>r.enabled),[false,false,false]);
   await page.reload();await page.getByRole('link',{name:'policy-review-'+label+'.mp4',exact:true}).click();
   await page.locator('#reviewSection0').scrollIntoViewIfNeeded();await page.waitForSelector('#ds1');
   const reopened=await page.locator('#ds1').innerText();
   assert(!reopened.includes('uncertain observation'),reopened);
   assert(!reopened.includes('unsupported sample'),reopened);
   assert.equal(await page.locator('#kb1').getAttribute('aria-pressed'),'true');
   await page.screenshot({path:path.join(root,'review-'+label+'.png'),fullPage:true});
   assert.deepEqual(errors,[]);assert.deepEqual(warnings,[]);
   await page.close();
  }
  console.log('OPTIONAL_PLATE_REVIEW_BROWSER_OK');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
