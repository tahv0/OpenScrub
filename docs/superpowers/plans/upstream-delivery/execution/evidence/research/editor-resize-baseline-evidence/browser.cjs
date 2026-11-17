const {chromium}=require('/tmp/openscrub-save-as-20261116/node_modules/playwright');
const fs=require('node:fs'),assert=require('node:assert/strict');
const root='/tmp/openscrub-editor-resize-baseline-20261117';
(async()=>{
 let browser;
 const all={environment:{plugin:'Browser plugin not available in skills/tool catalog; authorized regular Playwright fallback',playwright:require('/tmp/openscrub-save-as-20261116/node_modules/playwright/package.json').version,node:process.version,platform:process.platform,dpr:1},versions:[]};
 try{
 browser=await chromium.launch({headless:true,executablePath:'/tmp/openscrub-save-as-20261116/browsers/chromium-1255/chrome-linux64/chrome'});all.environment.browser=browser.version();
 for(const [label,port] of [['baseline',18561],['p07a',18562]]){
  const context=await browser.newContext({viewport:{width:1365,height:1000},deviceScaleFactor:1});
  try{
   const page=await context.newPage(),errors=[],warnings=[],requests=[];
   page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(['error','warning'].includes(m.type()))warnings.push(m.text())});
   page.on('request',r=>requests.push({method:r.method(),url:r.url()}));
   await context.route('**/*',route=>new URL(route.request().url()).hostname==='127.0.0.1'?route.continue():route.abort());
   await page.goto('http://127.0.0.1:'+port);
   await page.getByRole('link',{name:'synthetic-resize.mp4',exact:true}).click();
   await page.getByRole('button',{name:/Preview video & edit boxes/}).click();
   await page.waitForFunction(()=>document.getElementById('beImg')?.naturalWidth===640&&BE.boxes.length===1&&document.getElementById('beCv').width===640);
   const result={label,identity:{url:page.url(),title:await page.title(),nonblank:(await page.locator('body').innerText()).includes('OpenScrub'),frameworkOverlays:await page.locator('vite-error-overlay,nextjs-portal').count()},states:[]};
   async function measure(name){
    const data=await page.evaluate(()=>{
     const img=document.getElementById('beImg'),cv=document.getElementById('beCv');
     const geom=el=>{const r=el.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height,clientWidth:el.clientWidth,clientHeight:el.clientHeight}};
     const image=geom(img),canvas=geom(cv),sourceBox=BE.boxes[0].box;
     const px=cv.getContext('2d').getImageData(0,0,cv.width,cv.height),a=px.data;
     // Measure the production painting itself: bounds of the opaque red stroke,
     // and all nontransparent pixels, with an empty/nonselected editor state.
     function bounds(pred){let x0=Infinity,y0=Infinity,x1=-1,y1=-1,n=0;for(let y=0;y<cv.height;y++)for(let x=0;x<cv.width;x++){const i=(y*cv.width+x)*4;if(pred(a[i],a[i+1],a[i+2],a[i+3])){x0=Math.min(x0,x);y0=Math.min(y0,y);x1=Math.max(x1,x);y1=Math.max(y1,y);n++}}return n?{x0,y0,x1,y1,count:n}:null}
     const red=bounds((r,g,b,a)=>r>190&&g<80&&b<80&&a>240),paint=bounds((r,g,b,a)=>a>0);
     const cssEdges=b=>[canvas.x+b.x0*canvas.width/cv.width,canvas.y+b.y0*canvas.height/cv.height,canvas.x+(b.x1+1)*canvas.width/cv.width,canvas.y+(b.y1+1)*canvas.height/cv.height];
     const expected=[image.x+sourceBox[0]*image.width/img.naturalWidth,image.y+sourceBox[1]*image.height/img.naturalHeight,image.x+sourceBox[2]*image.width/img.naturalWidth,image.y+sourceBox[3]*image.height/img.naturalHeight];
     const rendered=cssEdges(red),center=[(expected[0]+expected[2])/2,(expected[1]+expected[3])/2];
     const sample=(x,y)=>{const ix=Math.floor((x-canvas.x)*cv.width/canvas.width),iy=Math.floor((y-canvas.y)*cv.height/canvas.height);if(ix<0||iy<0||ix>=cv.width||iy>=cv.height)return null;return Array.from(a.slice((iy*cv.width+ix)*4,(iy*cv.width+ix)*4+4))};
     return {viewport:{width:innerWidth,height:innerHeight},scroll:{x:scrollX,y:scrollY},image:{...image,naturalWidth:img.naturalWidth,naturalHeight:img.naturalHeight,src:img.src},canvas:{...canvas,width:cv.width,height:cv.height},BE:{scale:BE.scale,t:BE.t,ox:BE.ox,oy:BE.oy,sel:BE.sel,box:sourceBox,overrides:BE.ov},paint:{redStroke: red,allPixels:paint,renderedCssOuterEdges:rendered,expectedCssBoxEdges:expected,edgeDelta:rendered.map((v,i)=>v-expected[i]),expectedCenter:center,expectedCenterPixel:sample(...center)},sourceToImage:{x:image.width/img.naturalWidth,y:image.height/img.naturalHeight}};
    });
    data.name=name;result.states.push(data);
    await page.screenshot({path:`${root}/${label}-${name}.png`,fullPage:true});
    // Crop includes entire old canvas so overflow and source target can be inspected.
    await page.locator('#beCv').screenshot({path:`${root}/${label}-${name}-editor.png`});
    return data;
   }
   await measure('desktop');
   await page.evaluate(()=>{window.researchImg=document.getElementById('beImg');window.researchCanvas=document.getElementById('beCv');window.resizeLoadCount=0;researchImg.addEventListener('load',()=>resizeLoadCount++)});
   const countBefore=requests.length;
   await page.setViewportSize({width:390,height:844});
   await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
   await page.waitForTimeout(100);
   const live=await measure('mobile-live');
   async function hitVisualCenter(s){
    const p={x:(s.BE.box[0]+s.BE.box[2])/2*s.sourceToImage.x,y:(s.BE.box[1]+s.BE.box[3])/2*s.sourceToImage.y};
    await page.locator('#beCv').click({position:p});
    const hit={imageRelativeCssPoint:p,selected:await page.evaluate(()=>BE.sel)};
    await page.locator('#beCv').click({position:{x:10,y:10}});return hit;
   }
   result.livePointerHit=await hitVisualCenter(live);
   result.liveResize={sameElements:await page.evaluate(()=>researchImg===document.getElementById('beImg')&&researchCanvas===document.getElementById('beCv')),imageLoadEvents:await page.evaluate(()=>resizeLoadCount),frameRequests:requests.slice(countBefore).filter(r=>/frame_at|boxes_at/.test(r.url))};
   await page.evaluate(()=>beDraw());await measure('mobile-redraw');
   await page.locator('#beT').fill('0.5');await page.locator('#beT').dispatchEvent('input');
   await page.waitForFunction(()=>BE.t===.5&&document.getElementById('beImg')?.complete&&BE.scale<.8&&document.getElementById('beCv').width<400);
   const scrub=await measure('mobile-scrub');
   result.scrubPointerHit=await hitVisualCenter(scrub);
   // Existing production review entrypoint closes the editor through showPanel.
   await page.evaluate(()=>loadReview());
   result.editorClosed=await page.locator('#beCv').count()===0;
   // The ordinary Preview button reopens it through showPanel/loadBoxEdit.
   await page.getByRole('button',{name:/Preview video & edit boxes/}).click();
   await page.waitForFunction(()=>document.getElementById('beImg')?.complete&&document.getElementById('beImg').naturalWidth===640&&BE.boxes.length===1&&document.getElementById('beCv').width<400);
   await measure('mobile-reopen');
   result.reopenNewElements=await page.evaluate(()=>researchImg!==document.getElementById('beImg')&&researchCanvas!==document.getElementById('beCv'));
   // Source report must remain exactly the original target, no HTTP mutations.
   result.report=await(await page.request.get(`http://127.0.0.1:${port}/api/jobs/resize/report`)).json();
   for(const s of result.states){
    const drift=Math.max(...s.paint.edgeDelta.map(Math.abs));
    if(['mobile-live','mobile-redraw'].includes(s.name)){assert(drift>100);assert.equal(s.paint.expectedCenterPixel[3],0)}
    else {assert(drift<=1.1);assert(s.paint.expectedCenterPixel[3]>0)}
   }
   assert.equal(result.livePointerHit.selected,-1);assert.equal(result.scrubPointerHit.selected,0);assert.equal(result.editorClosed,true);assert.equal(result.reopenNewElements,true);
   assert.deepEqual(result.report.detections[0].cbox,[120,80,320,220]);
   result.errors=errors;result.warnings=warnings;result.mutations=requests.filter(r=>r.method!=='GET');
   assert.deepEqual(errors,[]);assert.equal(result.identity.title,'OpenScrub');assert.equal(result.identity.frameworkOverlays,0);assert.deepEqual(result.mutations,[]);
   all.versions.push(result);
   fs.writeFileSync(root+'/results.json',JSON.stringify(all,null,2));
   console.log(JSON.stringify({label,states:result.states.map(s=>({name:s.name,image:s.image.width,canvas:s.canvas.width,scale:s.BE.scale,delta:s.paint.edgeDelta,expectedCenterPixel:s.paint.expectedCenterPixel})),errors,warnings}));
  }finally{await context.close()}
 }
 }finally{if(browser)await browser.close();all.browserClosed=true;fs.writeFileSync(root+'/results.json',JSON.stringify(all,null,2))}
})().catch(e=>{console.error(e);process.exitCode=1});
