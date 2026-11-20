const {chromium}=require(process.env.OPENSCRUB_PLAYWRIGHT_MODULE);
const assert=require('node:assert/strict'),fs=require('node:fs');
const [url,root]=process.argv.slice(2);
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.OPENSCRUB_CHROMIUM,args:['--no-sandbox']});
 try{
  const context=await browser.newContext({viewport:{width:1100,height:900},deviceScaleFactor:1});
  try{
   const page=await context.newPage(),errors=[],writes=[],searches=[];page.setDefaultTimeout(20000);
   page.on('pageerror',e=>errors.push(e.message));
   page.on('console',m=>{if(m.type()==='error'&&!/409|504/.test(m.text()))errors.push(m.text())});
   page.on('request',r=>{
    if(r.method()==='POST'&&/\/(detections|render|track_object)$/.test(r.url()))writes.push(r.url());
    if(r.method()==='POST'&&r.url().endsWith('/plate_search'))searches.push(r.postDataJSON());
   });
   await page.goto(url);assert.equal(await page.title(),'OpenScrub');
   assert((await page.locator('body').innerText()).includes('OpenScrub'));
   assert.equal(await page.locator('vite-error-overlay,nextjs-portal').count(),0);
   await page.getByRole('link',{name:'synthetic-resize.mp4',exact:true}).click();
   await page.getByRole('button',{name:/Preview video & edit boxes/}).click();
   await page.waitForFunction(()=>beReady());await page.evaluate(()=>stopPolling());
   const initial=await (await page.request.get(url+'/api/jobs/resize/report')).text();
   await page.locator('#bePlate summary').click();
   // Matching unrelated scene text must remain a suggestion with no automatic blur.
   await page.locator('#bePlateQuery').fill('TARGET');await page.locator('#bePlateMode').selectOption('fragment');
   await page.getByRole('button',{name:'Search up to four video samples'}).click({timeout:3000});
   await page.waitForFunction(()=>document.querySelectorAll('#bePlateSamples button').length===4);
   assert.equal(searches.length,1);assert.equal(searches[0].scope,'sampled');
   const status=await page.locator('#bePlateStatus').innerText();
   assert(status.includes('4')&&status.includes('30')&&status.includes('scan-timeline')&&status.includes('only'),status);
   assert.deepEqual(await page.locator('#bePlateSamples button').count(),4);
   const labels=await page.locator('#bePlateSamples button').allTextContents();
   assert(labels[0].includes('frame 0')&&labels[1].includes('frame 9')&&
          labels[2].includes('frame 19')&&labels[3].includes('frame 29'),JSON.stringify(labels));
   assert(labels.some(label=>!label.includes('· 0 suggestions')),JSON.stringify(labels));
   assert.deepEqual(writes,[]);
   await page.screenshot({path:root+'/plate-sampled-desktop.png',fullPage:true});
   await page.setViewportSize({width:390,height:844});
   const viewport=await page.evaluate(()=>({scroll:document.documentElement.scrollWidth,client:document.documentElement.clientWidth}));
   assert(viewport.scroll<=viewport.client+2,JSON.stringify(viewport));
   await page.screenshot({path:root+'/plate-sampled-mobile.png',fullPage:true});
   await page.setViewportSize({width:1100,height:900});
   // Deliberate inspection and a fresh single-frame search retain the list so
   // another sampled hit can be opened without rerunning the video search.
   await page.locator('#bePlateSamples button').nth(0).click();
   await page.waitForFunction(()=>beReady()&&BE_VIEW.readySample.sample.index===0&&BE_VIEW.readySample.sample.requested_s>0);
   assert.equal(await page.locator('#bePlateSamples button').count(),4);
   await page.locator('#bePlateRun').click();
   await page.waitForFunction(()=>!BE_VIEW.plate.request);
   assert((await page.locator('#bePlateResults button').count())>0);
   assert.equal(await page.locator('#bePlateSamples button').count(),4);
   await page.locator('#bePlateSamples button').nth(1).click();
   await page.waitForFunction(()=>beReady()&&BE_VIEW.readySample.sample.index===9);
   assert.equal(await page.locator('#bePlateSamples button').count(),4);
   await page.locator('#bePlateQuery').fill('TARGET2');
   assert.equal(await page.locator('#bePlateSamples button').count(),0);
   await page.locator('#bePlateQuery').fill('TARGET');
   await page.getByRole('button',{name:'Search up to four video samples'}).click();
   await page.waitForFunction(()=>document.querySelectorAll('#bePlateSamples button').length===4);
   await page.locator('#bePlay').click();
   await page.waitForFunction(()=>BE.playing);
   assert.equal(await page.locator('#bePlateSamples button').count(),0);
   await page.locator('#bePlay').click();await page.waitForFunction(()=>beReady());
   await page.getByRole('button',{name:'Search up to four video samples'}).click();
   await page.waitForFunction(()=>document.querySelectorAll('#bePlateSamples button').length===4);
   let releaseFrame,startFrame,finishFrame;
   const frameGate=new Promise(r=>releaseFrame=r),frameStarted=new Promise(r=>startFrame=r),frameDone=new Promise(r=>finishFrame=r);
   await page.route('**/api/jobs/resize/plate_search',async route=>{
    const response=await route.fetch();startFrame();await frameGate;await route.fulfill({response});finishFrame();
   });
   await page.locator('#bePlateRun').click();await frameStarted;
   await page.locator('#bePlateCancel').click();releaseFrame();await frameDone;
   await page.unroute('**/api/jobs/resize/plate_search');
   await page.waitForFunction(()=>!BE_VIEW.plate.request);
   assert.equal(await page.locator('#bePlateSamples button').count(),0);
   await page.getByRole('button',{name:'Search up to four video samples'}).click();
   await page.waitForFunction(()=>document.querySelectorAll('#bePlateSamples button').length===4);
   // An ordinary seek retires it, even when both frames happened to match.
   await page.locator('#beT').fill('0.8');await page.locator('#beT').dispatchEvent('input');
   await page.waitForFunction(()=>beReady()&&BE_VIEW.readySample.sample.requested_s===.8);
   assert.equal(await page.locator('#bePlateSamples button').count(),0);
   await page.getByRole('button',{name:'Search up to four video samples'}).click();
   await page.waitForFunction(()=>document.querySelectorAll('#bePlateSamples button').length===4);
   // A different source at inspection time must not inherit old match claims.
   await page.route('**/api/jobs/resize/edit_sample?*',async route=>{
    const response=await route.fetch(),body=await response.json();
    body.sample.source_ref='changed-source';await route.fulfill({response,json:body});
   });
   await page.locator('#bePlateSamples button').nth(3).click();
   await page.waitForFunction(()=>beReady()&&BE_VIEW.readySample.sample.index===29,null,{timeout:4000});
   assert((await page.locator('#bePlateStatus').innerText()).includes('changed'));
   assert.equal(await page.locator('#bePlateSamples button').count(),0);
   assert.deepEqual(writes,[]);
   await page.unroute('**/api/jobs/resize/edit_sample?*');
   await page.evaluate(()=>beRequestSample(BE_VIEW,.6));
   await page.waitForFunction(()=>beReady()&&BE_VIEW.readySample.sample.requested_s===.6);
   await page.getByRole('button',{name:'Search up to four video samples'}).click();
   await page.waitForFunction(()=>document.querySelectorAll('#bePlateSamples button').length===4);
   // At 25 fps, 29/25 multiplied by 25 rounds below 29 in the resolver.
   await page.locator('#bePlateSamples button').nth(3).click();
   await page.waitForFunction(()=>beReady()&&BE_VIEW.readySample.sample.index===29,null,{timeout:4000});
   assert.equal(await page.locator('#bePlateSamples button').count(),4);
   assert((await page.locator('#bePlateStatus').innerText()).includes('Search this frame'));
   await page.locator('#bePlateRun').click();
   await page.waitForFunction(()=>!BE_VIEW.plate.request);
   assert((await page.locator('#bePlateResults button').count())>0,await page.locator('#bePlateStatus').innerText());
   assert.equal(await page.locator('#bePlateSamples button').count(),4);
   assert.deepEqual(writes,[]);
   // A completed sampled response cannot publish after an A→B→A seek.
   let release,start,finish;const gate=new Promise(r=>release=r),started=new Promise(r=>start=r),done=new Promise(r=>finish=r);
   await page.route('**/api/jobs/resize/plate_search',async route=>{
    if(route.request().postDataJSON()?.scope!=='sampled')return route.continue();
    const response=await route.fetch();start();await gate;await route.fulfill({response});finish();
   });
   await page.getByRole('button',{name:'Search up to four video samples'}).click();await started;
   await page.locator('#beT').fill('0.8');await page.locator('#beT').dispatchEvent('input');
   await page.waitForFunction(()=>beReady()&&BE_VIEW.readySample.sample.requested_s===.8);
   await page.locator('#beT').fill('0.6');await page.locator('#beT').dispatchEvent('input');
   await page.waitForFunction(()=>beReady()&&BE_VIEW.readySample.sample.requested_s===.6);
   release();await done;await page.unroute('**/api/jobs/resize/plate_search');
   await page.waitForFunction(()=>!BE_VIEW.plate.request);
   assert.equal(await page.locator('#bePlateSamples button').count(),0);
   let releaseCancel,startCancel,finishCancel;
   const cancelGate=new Promise(r=>releaseCancel=r),cancelStarted=new Promise(r=>startCancel=r),cancelDone=new Promise(r=>finishCancel=r);
   await page.route('**/api/jobs/resize/plate_search',async route=>{
    const response=await route.fetch();startCancel();await cancelGate;await route.fulfill({response});finishCancel();
   });
   await page.getByRole('button',{name:'Search up to four video samples'}).click();await cancelStarted;
   await page.locator('#bePlateCancel').click();releaseCancel();await cancelDone;
   await page.unroute('**/api/jobs/resize/plate_search');
   await page.waitForFunction(()=>!BE_VIEW.plate.request);
   assert((await page.locator('#bePlateStatus').innerText()).includes('No suggestions were applied'));
   assert.equal(await page.locator('#bePlateSamples button').count(),0);
   // A timeout is not reported as a completed set of negative matches.
   await page.route('**/api/jobs/resize/plate_search',route=>route.fulfill({status:504,json:{state:'timeout',error:'search_timeout'}}));
   await page.getByRole('button',{name:'Search up to four video samples'}).click();
   await page.waitForFunction(()=>document.getElementById('bePlateStatus')?.textContent.includes('timed out'));
   assert.equal(await page.locator('#bePlateSamples button').count(),0);
   await page.unroute('**/api/jobs/resize/plate_search');
   assert.deepEqual(writes,[]);assert.equal(await (await page.request.get(url+'/api/jobs/resize/report')).text(),initial);
   assert.deepEqual(errors,[],JSON.stringify(errors));
   fs.writeFileSync(root+'/plate-sampled-result.json',JSON.stringify({status,labels,viewport,searches,writes}));
   console.log('PLATE_SAMPLED_REAL_PAGE_OK');
  }finally{await context.close()}
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
