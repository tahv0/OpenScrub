const {chromium}=require(process.env.OPENSCRUB_PLAYWRIGHT_MODULE);
const assert=require('node:assert/strict'), fs=require('node:fs');
const [url,root]=process.argv.slice(2);
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.OPENSCRUB_CHROMIUM,args:['--no-sandbox']});
 try{
  const context=await browser.newContext({viewport:{width:1100,height:900},deviceScaleFactor:1});
  try{
   const page=await context.newPage(), errors=[], conflicts=[], writes=[], searches=[];page.setDefaultTimeout(8000);
   page.on('pageerror',e=>errors.push(e.message));
   page.on('console',m=>{if(['error','warning'].includes(m.type())) errors.push({text:m.text(),url:m.location().url})});
   page.on('response',r=>{if(r.status()>=400)conflicts.push(r.json().then(body=>({url:r.url(),status:r.status(),error:body.error})).catch(()=>({url:r.url(),status:r.status()})))});
   page.on('request',r=>{if(r.method()==='POST'&&/\/(detections|render|track_object)$/.test(r.url()))writes.push(r.url());
      if(r.method()==='POST'&&r.url().endsWith('/plate_search'))searches.push(r.url());});
   await page.goto(url);assert.equal(await page.title(),'OpenScrub');
   assert((await page.locator('body').innerText()).includes('OpenScrub'));
   assert.equal(await page.locator('vite-error-overlay,nextjs-portal').count(),0);
   async function open(name){
    await page.getByRole('link',{name,exact:true}).click();
    await page.getByRole('button',{name:/Preview video & edit boxes/}).click();
    await page.waitForFunction(()=>beReady());
    await page.evaluate(()=>stopPolling());
   }
   await open('synthetic-resize.mp4');
   const initial=await (await page.request.get(url+'/api/jobs/resize/report')).text();
   await page.locator('#bePlate summary').click();
   assert.equal(searches.length,0);
   await page.locator('#bePlateQuery').fill('KJF572');
   await page.locator('#bePlateMode').selectOption('full');
   await page.locator('#bePlateRun').click();
   await page.waitForFunction(()=>document.querySelectorAll('#bePlateResults button').length>0);
   assert((await page.locator('#bePlateStatus').innerText()).includes('suggestion'));
   await page.locator('#bePlateResults button').first().click();
   assert.equal(await page.locator('#bePlateResults button').first().getAttribute('aria-pressed'),'true');
   assert.equal(await page.evaluate(()=>BE.adds.length),0);
   await page.locator('#beAdd').click();assert.equal(await page.evaluate(()=>BE.add),true);
   assert.equal(await page.evaluate(()=>BE.adds.length),0);
   await page.locator('#beAdd').click();assert.equal(await page.evaluate(()=>BE.add),false);
   assert.deepEqual(writes,[]);
   await page.screenshot({path:root+'/plate-search-positive.png',fullPage:true});
   await page.locator('#bePlate').screenshot({path:root+'/plate-search-controls.png'});
   // A held genuine response belongs to the old inspected frame after a seek.
   let release,started,finished;const gate=new Promise(r=>release=r),start=new Promise(r=>started=r),done=new Promise(r=>finished=r);
   await page.route('**/api/jobs/resize/plate_search',async route=>{
    if(route.request().method()!=='POST')return route.continue();
    const response=await route.fetch();started();await gate;await route.fulfill({response});finished();
   });
   await page.locator('#bePlateRun').click();await start;
   await page.locator('#beT').fill('0.5');await page.locator('#beT').dispatchEvent('input');
   await page.waitForFunction(()=>beReady()&&BE_VIEW.readySample.sample.requested_s===.5);
   release();await done;await page.unroute('**/api/jobs/resize/plate_search');
   await page.waitForFunction(()=>!BE_VIEW.plate.request);
   assert.equal(await page.locator('#bePlateResults button').count(),0);
   // A new current-frame fragment search remains available after retirement.
   await page.locator('#bePlateQuery').fill('F57');await page.locator('#bePlateMode').selectOption('fragment');
   await page.locator('#bePlateRun').click();
   await page.waitForFunction(()=>document.querySelectorAll('#bePlateResults button').length>0);
   assert.equal(await page.evaluate(()=>BE.adds.length),0);
   await page.setViewportSize({width:390,height:844});
   for(const id of ['bePlateQuery','bePlateMode']){
    const fields=await page.locator(`label[for="${id}"]`).evaluate(label=>{
     const control=label.control, text=label.getBoundingClientRect(), target=control.getBoundingClientRect();
     return {together:label.parentElement.contains(control),aligned:Math.abs(text.left-target.left)<2,
             stacked:text.bottom<=target.top};
    });
    assert.deepEqual(fields,{together:true,aligned:true,stacked:true});
   }
   await page.screenshot({path:root+'/plate-search-mobile.png',fullPage:true});
   await page.locator('#bePlate').screenshot({path:root+'/plate-search-mobile-controls.png'});
   const size=await page.evaluate(()=>({scroll:document.documentElement.scrollWidth,client:document.documentElement.clientWidth}));
   assert(size.scroll<=size.client+2,JSON.stringify(size));
   await page.setViewportSize({width:1100,height:900});
   // Explicit cancel discards even a real response already in transit.
   let releaseCancel,startCancel,finishedCancel;
   const cancelGate=new Promise(r=>releaseCancel=r),cancelStart=new Promise(r=>startCancel=r),cancelDone=new Promise(r=>finishedCancel=r);
   await page.route('**/api/jobs/resize/plate_search',async route=>{
    const response=await route.fetch();startCancel();await cancelGate;await route.fulfill({response});finishedCancel();
   });
   await page.locator('#bePlateRun').click();await cancelStart;
   await page.locator('#bePlateCancel').click();
   assert((await page.locator('#bePlateStatus').innerText()).includes('Cancellation requested'));
   releaseCancel();await cancelDone;await page.unroute('**/api/jobs/resize/plate_search');
   await page.waitForFunction(()=>!BE_VIEW.plate.request);
   assert((await page.locator('#bePlateStatus').innerText()).includes('No suggestions were applied'));
   assert.equal(await page.locator('#bePlateResults button').count(),0);
   // A real no-match and a timeout have different user-visible states.
   await page.locator('#bePlateQuery').fill('ZZZ999');await page.locator('#bePlateRun').click();
   await page.waitForFunction(()=>document.getElementById('bePlateStatus')?.textContent.includes('No matching text'));
   await page.locator('#beT').fill('0.6');await page.locator('#beT').dispatchEvent('input');
   await page.waitForFunction(()=>beReady()&&BE_VIEW.readySample.sample.requested_s===.6);
   assert((await page.locator('#bePlateStatus').innerText()).includes('Frame changed'));
   await page.locator('#bePlateQuery').fill('ZZZ998');
   assert((await page.locator('#bePlateStatus').innerText()).includes('Text or match mode changed'));
   await page.route('**/api/jobs/resize/plate_search',route=>route.fulfill({status:504,json:{state:'timeout',error:'search_timeout'}}));
   await page.locator('#bePlateRun').click();
   await page.waitForFunction(()=>document.getElementById('bePlateStatus')?.textContent.includes('timed out'));
   assert.equal(await page.locator('#bePlateResults button').count(),0);
   await page.unroute('**/api/jobs/resize/plate_search');
   await page.evaluate(()=>{const summary=document.querySelector('#bePlate summary');summary.click();summary.click()});
   assert.equal(await page.locator('#bePlateQuery').inputValue(),'');
   assert((await page.locator('#bePlateStatus').innerText()).includes('Search only the current frame'));
   // A response for an unmounted editor cannot publish into a later mount.
   await page.locator('#bePlateQuery').fill('F57');
   let releaseMount,startMount,finishedMount;
   const mountGate=new Promise(r=>releaseMount=r),mountStart=new Promise(r=>startMount=r),mountDone=new Promise(r=>finishedMount=r);
   await page.route('**/api/jobs/resize/plate_search',async route=>{
    const response=await route.fetch();startMount();await mountGate;await route.fulfill({response});finishedMount();
   });
   await page.locator('#bePlateRun').click();await mountStart;
   await page.getByRole('link',{name:'synthetic-other.mp4',exact:true}).click();
   await page.waitForFunction(()=>CUR==='other');await open('synthetic-resize.mp4');
   releaseMount();await mountDone;await page.unroute('**/api/jobs/resize/plate_search');
   assert.equal(await page.locator('#bePlateResults button').count(),0);
   assert.equal(await page.locator('#bePlateQuery').inputValue(),'');
   const after=await (await page.request.get(url+'/api/jobs/resize/report')).text();
   assert.equal(after,initial);assert.deepEqual(writes,[]);
   const observed=await Promise.all(conflicts);
   const unexpected=errors.filter(e=>!observed.some(c=>c.url===e.url&&(
      c.status===409&&/\/(thumb|detframe)\/\d+\?v=/.test(c.url)&&['thumbnail_obsolete','thumbnail_pending'].includes(c.error)||
      c.status===504&&c.url.endsWith('/plate_search')&&c.error==='search_timeout')));
   assert.deepEqual(unexpected,[],JSON.stringify({errors,conflicts:observed}));
   fs.writeFileSync(root+'/plate-search-browser-result.json',JSON.stringify({searches:searches.length,writes,errors,conflicts:observed,viewport:size}));
   console.log('PLATE_SEARCH_REAL_PAGE_OK',searches.length);
  }finally{await context.close()}
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
