const {chromium}=require(process.env.OPENSCRUB_PLAYWRIGHT_MODULE);
const assert=require('node:assert/strict'),fs=require('node:fs');
const [url,root]=process.argv.slice(2);
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.OPENSCRUB_CHROMIUM,args:['--no-sandbox']});
 try{
  const context=await browser.newContext({viewport:{width:1100,height:900},deviceScaleFactor:1});
  try{
   const page=await context.newPage(),errors=[],writes=[],tracks=[];
   page.setDefaultTimeout(10000);
   page.on('pageerror',e=>errors.push(e.message));
   page.on('console',m=>{if(m.type()==='error'&&!m.text().includes('409'))errors.push(m.text())});
   page.on('request',r=>{
    if(r.method()==='POST'&&/\/(detections|render|track_object)$/.test(r.url()))writes.push(r.url());
    if(r.method()==='POST'&&r.url().endsWith('/track_object'))tracks.push(r.postDataJSON());
   });
   await page.goto(url);assert.equal(await page.title(),'OpenScrub');
   assert((await page.locator('body').innerText()).includes('OpenScrub'));
   assert.equal(await page.locator('vite-error-overlay,nextjs-portal').count(),0);
   await page.getByRole('link',{name:'synthetic-resize.mp4',exact:true}).click();
   await page.getByRole('button',{name:/Preview video & edit boxes/}).click();
   await page.waitForFunction(()=>beReady());await page.evaluate(()=>stopPolling());
   await page.locator('#beT').fill('0.5');await page.locator('#beT').dispatchEvent('input');
   await page.waitForFunction(()=>beReady()&&BE_VIEW.readySample.sample.requested_s===.5);
   const initial=await (await page.request.get(url+'/api/jobs/resize/report')).text();
   await page.locator('#bePlate summary').click();await page.locator('#bePlateQuery').fill('F57');
   await page.locator('#bePlateMode').selectOption('fragment');
   async function searchAndSelect(){
    await page.locator('#bePlateRun').click();
    await page.waitForFunction(()=>document.querySelectorAll('#bePlateResults button').length>0);
    await page.locator('#bePlateResults button').first().click();
   }
   await searchAndSelect();
   assert.deepEqual(writes,[]);
   await page.getByRole('button',{name:'Adjust for tracking'}).click();
   assert.deepEqual(writes,[]);
   await page.getByRole('button',{name:'Cancel region'}).click();
   assert.deepEqual(writes,[]);
   assert.equal(await (await page.request.get(url+'/api/jobs/resize/report')).text(),initial);
   await page.getByRole('button',{name:'Adjust for tracking'}).click();
   await page.locator('#beT').fill('0.6');await page.locator('#beT').dispatchEvent('input');
   await page.waitForFunction(()=>beReady()&&BE_VIEW.readySample.sample.requested_s===.6);
   assert.equal(await page.getByRole('button',{name:'Track this region'}).count(),0);
   assert.deepEqual(writes,[]);
   await page.locator('#beT').fill('0.5');await page.locator('#beT').dispatchEvent('input');
   await page.waitForFunction(()=>beReady()&&BE_VIEW.readySample.sample.requested_s===.5);
   assert.equal(await page.getByRole('button',{name:'Track this region'}).count(),0);
   await page.locator('#beT').fill('0.6');await page.locator('#beT').dispatchEvent('input');
   await page.waitForFunction(()=>beReady()&&BE_VIEW.readySample.sample.requested_s===.6);
   await searchAndSelect();await page.getByRole('button',{name:'Adjust for tracking'}).click();
   await page.locator('#bePlateQuery').fill('F58');
   assert.equal(await page.getByRole('button',{name:'Track this region'}).count(),0);
   assert.deepEqual(writes,[]);
   await page.locator('#bePlateQuery').fill('F57');
   await searchAndSelect();await page.getByRole('button',{name:'Adjust for tracking'}).click();
   const before=await page.evaluate(()=>({box:[...BE_VIEW.plate.region.box],seed:structuredClone(BE_VIEW.readySample.precondition),
    time:BE_VIEW.readySample.sample.canonical_s}));
   await page.locator('#beCv').scrollIntoViewIfNeeded();
   const handle=await page.evaluate(()=>{
    const r=BE_VIEW.cv.getBoundingClientRect(),tr=BE_VIEW.transform,b=BE_VIEW.plate.region.box;
    return {x:r.left+b[0]*tr.sx,y:r.top+b[1]*tr.sy,sx:tr.sx,sy:tr.sy};
   });
   await page.mouse.move(handle.x,handle.y);await page.mouse.down();
   await page.mouse.move(handle.x-20*handle.sx,handle.y-15*handle.sy,{steps:4});await page.mouse.up();
   const expanded=await page.evaluate(()=>[...BE_VIEW.plate.region.box]);
   assert(expanded[0]<before.box[0]-15&&expanded[1]<before.box[1]-10,JSON.stringify({before,expanded}));
   const center=await page.evaluate(()=>{
    const r=BE_VIEW.cv.getBoundingClientRect(),tr=BE_VIEW.transform,b=BE_VIEW.plate.region.box;
    return {x:r.left+(b[0]+b[2])/2*tr.sx,y:r.top+(b[1]+b[3])/2*tr.sy,sx:tr.sx,sy:tr.sy};
   });
   await page.mouse.move(center.x,center.y);await page.mouse.down();
   await page.mouse.move(center.x+7*center.sx,center.y+4*center.sy,{steps:4});await page.mouse.up();
   const edited=await page.evaluate(()=>[...BE_VIEW.plate.region.box]);
   assert(edited[0]>expanded[0]+5&&edited[1]>expanded[1]+2,JSON.stringify({expanded,edited}));
   assert.deepEqual(writes,[]);
   // Resizing ends a live region drag without losing its last applied box.
   const dragPoint=await page.evaluate(()=>{
    const r=BE_VIEW.cv.getBoundingClientRect(),tr=BE_VIEW.transform,b=BE_VIEW.plate.region.box;
    return {x:r.left+(b[0]+b[2])/2*tr.sx,y:r.top+(b[1]+b[3])/2*tr.sy,sx:tr.sx,sy:tr.sy};
   });
   await page.mouse.move(dragPoint.x,dragPoint.y);await page.mouse.down();
   await page.mouse.move(dragPoint.x+4*dragPoint.sx,dragPoint.y+3*dragPoint.sy);
   const beforeResize=await page.evaluate(()=>[...BE_VIEW.plate.region.box]);
   await page.setViewportSize({width:390,height:844});
   await page.waitForFunction(()=>BE_VIEW.transform?.width<500);
   assert.deepEqual(await page.evaluate(()=>BE_VIEW.plate.region.box),beforeResize);
   assert.equal(await page.evaluate(()=>BE_VIEW.plate.region.drag),null);
   await page.mouse.up();
   await page.setViewportSize({width:1100,height:900});
   const readyBox=await page.evaluate(()=>[...BE_VIEW.plate.region.box]);
   await page.screenshot({path:root+'/plate-track-ready.png',fullPage:true});
   await page.setViewportSize({width:390,height:844});
   await page.screenshot({path:root+'/plate-track-mobile.png',fullPage:true});
   const viewport=await page.evaluate(()=>({scroll:document.documentElement.scrollWidth,client:document.documentElement.clientWidth}));
   assert(viewport.scroll<=viewport.client+2,JSON.stringify(viewport));
   await page.setViewportSize({width:1100,height:900});
   await page.evaluate(()=>{BE.win=[0,.2];beTLDraw()});
   await page.getByRole('button',{name:'Track this region'}).click();
   assert((await page.locator('#bePlateStatus').innerText()).includes('timeline window'));
   assert.deepEqual(writes,[]);
   await page.evaluate(()=>{BE.win=[0,BE.dur];beTLDraw()});
   await page.getByRole('button',{name:'Track this region'}).click();
   for(let n=0;n<100;n++){
    const state=await (await page.request.get(url+'/api/jobs/resize/track_status')).json();
    if(state.state==='done'){assert.equal(state.error,null);break;}
    if(n===99)throw Error('track did not complete');
    await new Promise(resolve=>setTimeout(resolve,100));
   }
   assert.equal(tracks.length,1);assert.deepEqual(tracks[0].seed,before.seed);
   assert.equal(tracks[0].t_ref,before.time);assert.deepEqual(tracks[0].box,readyBox);
   assert.equal(tracks[0].seed.index,6);assert.equal(tracks[0].t_ref,.6);
   const actual=JSON.parse(fs.readFileSync(root+'/runtime/track-seed.json','utf8'));
   assert.equal(actual.index,6);assert.equal(actual.t_ref,.6);assert.deepEqual(actual.box,readyBox);
   const report=await (await page.request.get(url+'/api/jobs/resize/report')).text();
   assert.notEqual(report,initial);assert.deepEqual(errors,[],JSON.stringify(errors));
   // A selected suggestion must take over from a live corner editor without
   // turning its approximate OCR region into a saved change or a track.
   const writesBefore=writes.length;
   await page.goto(url);
   await page.getByRole('link',{name:'synthetic-plate.mp4',exact:true}).click();
   await page.getByRole('button',{name:/Preview video & edit boxes/}).click();
   await page.waitForFunction(()=>beReady());await page.evaluate(()=>stopPolling());
   await page.locator('#beCv').scrollIntoViewIfNeeded();
   const platePoint=await page.evaluate(()=>{const r=BE_VIEW.cv.getBoundingClientRect(),tr=BE_VIEW.transform;
    return {x:r.left+220*tr.sx,y:r.top+150*tr.sy};});
   await page.mouse.click(platePoint.x,platePoint.y);
   await page.getByRole('button',{name:'Edit plate corners',exact:true}).click();
   assert(await page.evaluate(()=>!!BE_VIEW.quadEdit));
   await page.locator('#bePlate summary').click();await page.locator('#bePlateQuery').fill('F57');
   await page.locator('#bePlateMode').selectOption('fragment');await searchAndSelect();
   await page.getByRole('button',{name:'Adjust for tracking'}).click();
   assert.equal(await page.evaluate(()=>BE_VIEW.quadEdit),null);
   const cornerBefore=await page.evaluate(()=>[...BE_VIEW.plate.region.box]);
   await page.locator('#beCv').scrollIntoViewIfNeeded();
   const cornerPoint=await page.evaluate(()=>{const r=BE_VIEW.cv.getBoundingClientRect(),tr=BE_VIEW.transform,b=BE_VIEW.plate.region.box;
    return {x:r.left+b[0]*tr.sx,y:r.top+b[1]*tr.sy,sx:tr.sx,sy:tr.sy};});
   await page.mouse.move(cornerPoint.x,cornerPoint.y);await page.mouse.down();
   await page.mouse.move(cornerPoint.x-12*cornerPoint.sx,cornerPoint.y-8*cornerPoint.sy,{steps:3});await page.mouse.up();
   const cornerAfter=await page.evaluate(()=>[...BE_VIEW.plate.region.box]);
   assert(cornerAfter[0]<cornerBefore[0]-8&&cornerAfter[1]<cornerBefore[1]-5,
    JSON.stringify({cornerBefore,cornerAfter,cornerPoint}));
   assert.equal(writes.length,writesBefore);assert.deepEqual(errors,[],JSON.stringify(errors));
   fs.writeFileSync(root+'/plate-track-result.json',JSON.stringify({before,edited,tracks,actual,viewport}));
   console.log('PLATE_TRACK_REAL_PAGE_OK');
  }finally{await context.close()}
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
