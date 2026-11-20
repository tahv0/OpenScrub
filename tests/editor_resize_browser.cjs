const {chromium}=require(process.env.OPENSCRUB_PLAYWRIGHT_MODULE);
const fs=require('node:fs'),assert=require('node:assert/strict');
const [url,root]=process.argv.slice(2);
(async()=>{const browser=await chromium.launch({headless:true,executablePath:process.env.OPENSCRUB_CHROMIUM});
try{for(const dpr of [1,2]){const context=await browser.newContext({viewport:{width:1365,height:1000},deviceScaleFactor:dpr});
try{const page=await context.newPage(),errors=[],requests=[],warnings=[],responses=[];
page.on('response',r=>{if(r.status()===409)responses.push((async()=>{let body={};try{body=await r.json()}catch{};return {url:r.url(),body}})())});
await page.addInitScript(()=>{
 const Native=ResizeObserver;window.resizeObservers=[];
 window.ResizeObserver=class extends Native{
  constructor(callback){super(callback);this.callback=callback;this.disconnected=false;resizeObservers.push(this);}
  disconnect(){this.disconnected=true;super.disconnect();}
 };
});
page.on('console',m=>{if(['error','warning'].includes(m.type()))warnings.push(m.text())});page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>requests.push({method:r.method(),url:r.url()}));
page.on('dialog',d=>{console.log('dialog: '+d.message());d.accept(d.defaultValue())});
await page.goto(url);assert.equal(await page.title(),'OpenScrub');assert((await page.locator('body').innerText()).includes('OpenScrub'));assert.equal(await page.locator('vite-error-overlay,nextjs-portal').count(),0);
await page.getByRole('link',{name:'synthetic-resize.mp4',exact:true}).click();await page.getByRole('button',{name:/Preview video & edit boxes/}).click();
await page.waitForFunction(()=>document.getElementById('beImg')?.naturalWidth===640&&BE.boxes.length===1);
const result={dpr,states:[]};
   async function measure(name){
    await page.evaluate(()=>{BE.sel=-1;beDraw()});
    const data=await page.evaluate(()=>{
     const img=document.getElementById(BE.playing?'beVid':'beImg'),cv=document.getElementById('beCv');
     const geom=el=>{const r=el.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height,clientWidth:el.clientWidth,clientHeight:el.clientHeight}};
     const image=geom(img),canvas=geom(cv),sourceBox=BE.boxes[0].box;
     const boxes=BE.boxes.map(b=>b.box),extent=[Math.min(...boxes.map(b=>b[0])),Math.min(...boxes.map(b=>b[1])),Math.max(...boxes.map(b=>b[2])),Math.max(...boxes.map(b=>b[3]))];
     const px=cv.getContext('2d').getImageData(0,0,cv.width,cv.height),a=px.data;
     // Measure the production painting itself: bounds of the opaque red stroke,
     // and all nontransparent pixels, with an empty/nonselected editor state.
     function bounds(pred){let x0=Infinity,y0=Infinity,x1=-1,y1=-1,n=0;for(let y=0;y<cv.height;y++)for(let x=0;x<cv.width;x++){const i=(y*cv.width+x)*4;if(pred(a[i],a[i+1],a[i+2],a[i+3])){x0=Math.min(x0,x);y0=Math.min(y0,y);x1=Math.max(x1,x);y1=Math.max(y1,y);n++}}return n?{x0,y0,x1,y1,count:n}:null}
     const red=bounds((r,g,b,a)=>r>190&&g<80&&b<80&&a>240),paint=bounds((r,g,b,a)=>a>0);
     const cssEdges=b=>[canvas.x+b.x0*canvas.width/cv.width,canvas.y+b.y0*canvas.height/cv.height,canvas.x+(b.x1+1)*canvas.width/cv.width,canvas.y+(b.y1+1)*canvas.height/cv.height];
     const expected=[image.x+extent[0]*image.width/(img.naturalWidth||img.videoWidth),image.y+extent[1]*image.height/(img.naturalHeight||img.videoHeight),image.x+extent[2]*image.width/(img.naturalWidth||img.videoWidth),image.y+extent[3]*image.height/(img.naturalHeight||img.videoHeight)];
     const rendered=cssEdges(red),center=[(expected[0]+expected[2])/2,(expected[1]+expected[3])/2];
     const sample=(x,y)=>{const ix=Math.floor((x-canvas.x)*cv.width/canvas.width),iy=Math.floor((y-canvas.y)*cv.height/canvas.height);if(ix<0||iy<0||ix>=cv.width||iy>=cv.height)return null;return Array.from(a.slice((iy*cv.width+ix)*4,(iy*cv.width+ix)*4+4))};
     return {viewport:{width:innerWidth,height:innerHeight},scroll:{x:scrollX,y:scrollY},image:{...image,naturalWidth:(img.naturalWidth||img.videoWidth),naturalHeight:(img.naturalHeight||img.videoHeight),src:img.src},canvas:{...canvas,width:cv.width,height:cv.height},BE:{scale:BE.scale,t:BE.t,ox:BE.ox,oy:BE.oy,sel:BE.sel,box:sourceBox,overrides:BE.ov},paint:{redStroke: red,allPixels:paint,renderedCssOuterEdges:rendered,expectedCssBoxEdges:expected,edgeDelta:rendered.map((v,i)=>v-expected[i]),expectedCenter:center,expectedCenterPixel:sample(...center)},sourceToImage:{x:image.width/(img.naturalWidth||img.videoWidth),y:image.height/(img.naturalHeight||img.videoHeight)}};
    });
    data.name=name;result.states.push(data);fs.writeFileSync(root+`/results-${dpr}.json`,JSON.stringify(result,null,2));
    await page.screenshot({path:`${root}/${dpr}-${name}.png`,fullPage:true});
    // Crop includes entire old canvas so overflow and source target can be inspected.
    await page.locator('#beCv').screenshot({path:`${root}/${dpr}-${name}-editor.png`});
    return data;
   }
await measure('desktop');
await page.evaluate(()=>{window.originalImg=document.getElementById('beImg');window.originalCv=document.getElementById('beCv');window.imageLoads=0;originalImg.addEventListener('load',()=>imageLoads++)});
const originalGeometry=await page.evaluate(()=>JSON.stringify({ov:BE.ov,times:BE.times,adds:BE.adds,t:BE.t,boxes:BE.boxes}));
const before=requests.length;
await page.setViewportSize({width:390,height:844});await page.waitForTimeout(150);
const live=await measure('mobile-live');
await page.locator('#beCv').click({position:{x:(live.BE.box[0]+live.BE.box[2])/2*live.sourceToImage.x,y:(live.BE.box[1]+live.BE.box[3])/2*live.sourceToImage.y}});
result.liveHit=await page.evaluate(()=>BE.sel);
result.edgeError=Math.max(...live.paint.edgeDelta.map(Math.abs));
fs.writeFileSync(root+`/results-${dpr}.json`,JSON.stringify(result,null,2));
assert(result.edgeError<=2,`painted edge drift ${result.edgeError} CSS px; visible target hit ${result.liveHit}`);assert.equal(result.liveHit,0);

assert(await page.evaluate(()=>originalImg===document.getElementById('beImg')&&originalCv===document.getElementById('beCv')&&imageLoads===0));
assert.deepEqual(requests.slice(before).filter(r=>/frame_at|boxes_at/.test(r.url)),[]);
assert.equal(await page.evaluate(()=>JSON.stringify({ov:BE.ov,times:BE.times,adds:BE.adds,t:BE.t,boxes:BE.boxes})),originalGeometry);
assert.deepEqual(await page.evaluate(()=>[BE.ox,BE.oy]),[20,12]);
async function point(x,y){return page.evaluate(([x,y])=>{const r=(BE.playing?document.getElementById('beVid'):document.getElementById('beImg')).getBoundingClientRect();return {x:r.x+x*r.width/640,y:r.y+y*r.height/360}},[x,y]);}
async function click(x,y){const p=await point(x,y);await page.mouse.click(p.x,p.y);}
async function drag(x,y,xx,yy){const a=await point(x,y),b=await point(xx,yy);await page.mouse.move(a.x,a.y);await page.mouse.down();await page.mouse.move(b.x,b.y,{steps:3});await page.mouse.up();}
function near(actual,expected,tolerance=2){assert.equal(actual.length,expected.length);actual.forEach((n,i)=>assert(Math.abs(n-expected[i])<=tolerance,`${actual} != ${expected}`));}
async function selectedBox(){return page.evaluate(()=>BE.boxes[0].box.slice());}
// Grow without any media reload; use independent production pixel bounds again.
await page.setViewportSize({width:1365,height:1000});await page.waitForTimeout(120);
const grown=await measure('desktop-grown');assert(Math.max(...grown.paint.edgeDelta.map(Math.abs))<=2);
assert.equal(await page.evaluate(()=>imageLoads),0);
assert.deepEqual(requests.slice(before).filter(r=>/frame_at|boxes_at/.test(r.url)),[]);
// Fractional layout plus separate X/Y backing ratios, in both DPR contexts.
await page.locator('#beImg').evaluate(e=>e.style.width='487.375px');
await page.waitForTimeout(120);const fractional=await measure('fractional');
assert(Math.max(...fractional.paint.edgeDelta.map(Math.abs))<=2);
assert.equal(fractional.image.width,487.375);
assert(Math.abs(fractional.canvas.width-fractional.image.width*dpr)<=.5);
const box=await selectedBox();await click((box[0]+box[2])/2,(box[1]+box[3])/2);assert.equal(await page.evaluate(()=>BE.sel),0);
await drag(220,162,245.5,180.25);const moved=await selectedBox();near(moved,[165.5,110.25,365.5,250.25]);
near(await page.evaluate(()=>BE.ov[0]),moved.map((n,i)=>n-(i%2?12:20)),1e-8);
await drag(moved[2],moved[3],moved[2]+15.25,moved[3]+12.5);const corner=await selectedBox();near(corner,[moved[0],moved[1],moved[2]+15.25,moved[3]+12.5]);
// Resize in the middle of a move: keep edits already applied, stop the old drag.
let a=await point((corner[0]+corner[2])/2,(corner[1]+corner[3])/2);await page.mouse.move(a.x,a.y);await page.mouse.down();await page.mouse.move(a.x+12,a.y+7);
const applied=await selectedBox();assert(await page.evaluate(()=>!!BE.drag));
await page.setViewportSize({width:390,height:844});await page.waitForTimeout(120);
assert.equal(await page.evaluate(()=>BE.drag),null);await page.mouse.move(a.x+80,a.y+60);await page.mouse.up();assert.deepEqual(await selectedBox(),applied);
await click((applied[0]+applied[2])/2,(applied[1]+applied[3])/2);await drag((applied[0]+applied[2])/2,(applied[1]+applied[3])/2,(applied[0]+applied[2])/2+5,(applied[1]+applied[3])/2+4);
const deliberate=await selectedBox();near(deliberate,applied.map((n,i)=>n+(i%2?4:5)));
// A half-drawn addition is the only discarded draft on a resize.
await page.locator('#beAdd').click();await click(410,240);assert(await page.evaluate(()=>!!BE.addAnchor));
await page.setViewportSize({width:470,height:844});await page.waitForTimeout(120);
assert.equal(await page.evaluate(()=>BE.addAnchor),null);assert.equal(await page.evaluate(()=>BE.adds.length),0);
await click(400.25,220.5);await click(490.75,300.25);
assert.equal(await page.evaluate(()=>BE.adds.length),1);near(await page.evaluate(()=>BE.adds[0].box),[400.25,220.5,490.75,300.25]);await page.locator('#beAdd').click();
const drafts=await page.evaluate(()=>JSON.stringify({ov:BE.ov,times:BE.times,adds:BE.adds}));
// Hidden/zero element geometry invalidates edits, and recovers when visible.
await page.locator('#beImg').evaluate(e=>e.style.display='none');await page.waitForTimeout(120);
assert.equal(await page.evaluate(()=>BE_VIEW.transform),null);
await page.locator('#beCv').dispatchEvent('pointerdown',{clientX:100,clientY:100,pointerId:1});
assert.equal(await page.evaluate(()=>JSON.stringify({ov:BE.ov,times:BE.times,adds:BE.adds})),drafts);
await page.locator('#beImg').evaluate(e=>{e.style.display='';e.style.width='0px'});await page.waitForTimeout(120);
assert.equal(await page.evaluate(()=>BE_VIEW.transform),null);
await page.locator('#beImg').evaluate(e=>e.style.width='');await page.waitForTimeout(120);
assert(await page.evaluate(()=>!!BE_VIEW.transform));
// Unloaded current image must reject input while its real frame request waits.
let release;const gate=new Promise(r=>release=r);let started;const pending=new Promise(r=>started=r);
await page.route('**/frame_at?t=0.7',async route=>{started();await gate;await route.continue()});
await page.locator('#beT').fill('0.7');await page.locator('#beT').dispatchEvent('input');await pending;
assert.equal(await page.evaluate(()=>BE_VIEW.transform),null);
await page.locator('#beCv').dispatchEvent('pointerdown',{clientX:100,clientY:100,pointerId:1});
assert.equal(await page.evaluate(()=>BE.drag),null);release();await page.waitForFunction(()=>document.getElementById('beImg').complete&&BE_VIEW.transform!==null);await page.unroute('**/frame_at?t=0.7');
// Actual video playback and live resize, then ordinary pause/scrub switches back.
await page.locator('#bePlay').click();await page.waitForTimeout(300);
fs.writeFileSync(root+`/video-start-${dpr}.json`,JSON.stringify(await page.evaluate(()=>{const v=document.getElementById('beVid');return {playing:BE.playing,ready:v.readyState,network:v.networkState,src:v.src,preload:v.preload,error:v.error?.message,transform:!!BE_VIEW.transform,canPlay:v.canPlayType('video/mp4')}}),null,2));
await page.waitForFunction(()=>BE.playing&&BE_VIEW.transform?.media===document.getElementById('beVid'));
await page.setViewportSize({width:390,height:844});await page.waitForTimeout(120);
const videoState=await page.evaluate(()=>{const v=document.getElementById('beVid'),c=document.getElementById('beCv');const r=v.getBoundingClientRect(),q=c.getBoundingClientRect();return {video:r.width,canvas:q.width,source:v.videoWidth,owner:BE_VIEW.transform.media===v}});
assert.equal(videoState.video,videoState.canvas);assert.equal(videoState.source,640);assert(videoState.owner);
const videoPixels=await measure('video-mobile');assert(Math.max(...videoPixels.paint.edgeDelta.map(Math.abs))<=2);
await page.locator('#bePlay').click();await page.waitForFunction(()=>!BE.playing&&document.getElementById('beImg').complete&&BE_VIEW.transform?.media===document.getElementById('beImg'));
result.video=videoState;
// Close/remount and job switches disconnect the observer; even deliberately
// delivered stale callbacks cannot clear or repaint the current mount.
await page.evaluate(async()=>{window.outgoingObserver=resizeObservers.at(-1);window.outgoingImage=document.getElementById('beImg');window.lateImage=outgoingImage.onload;await loadReview()});
assert(await page.evaluate(()=>outgoingObserver.disconnected));assert.equal(await page.locator('#beCv').count(),0);
await page.getByRole('button',{name:/Preview video & edit boxes/}).click();await page.waitForFunction(()=>document.getElementById('beImg')?.complete&&BE_VIEW?.transform&&BE.boxes.length===1);
const currentPixels=await page.evaluate(()=>document.getElementById('beCv').toDataURL());
await page.evaluate(()=>{outgoingObserver.callback([]);lateImage()});
assert.equal(await page.evaluate(()=>document.getElementById('beCv').toDataURL()),currentPixels);
await page.evaluate(()=>{window.oldView=BE_VIEW;window.oldObserver=resizeObservers.at(-1)});
await page.getByRole('link',{name:'synthetic-other.mp4',exact:true}).click();await page.waitForFunction(()=>CUR==='other');
await page.getByRole('link',{name:'synthetic-resize.mp4',exact:true}).click();await page.waitForFunction(()=>CUR==='resize');
await page.getByRole('button',{name:/Preview video & edit boxes/}).click();await page.waitForFunction(()=>document.getElementById('beImg')?.complete&&BE_VIEW?.transform&&BE.boxes.length===1);
assert(await page.evaluate(()=>oldObserver.disconnected));const newPixels=await page.evaluate(()=>document.getElementById('beCv').toDataURL());
await page.evaluate(()=>oldObserver.callback([]));assert.equal(await page.evaluate(()=>document.getElementById('beCv').toDataURL()),newPixels);
assert.equal(await page.evaluate(()=>JSON.stringify({ov:BE.ov,times:BE.times,adds:BE.adds})),drafts);
const final=await measure('mobile-edited');assert(Math.max(...final.paint.edgeDelta.map(Math.abs))<=2);
// Ordinary enlarged review preview and embedded editor help survive.
assert((await page.locator('body').innerText()).includes('drag inside to move'));
await page.evaluate(()=>loadReview());await page.locator('#det0 img').click();await page.locator('#lb img').waitFor();await page.locator('#lb').click();assert.equal(await page.locator('#lb').count(),0);
await page.getByRole('button',{name:/Preview video & edit boxes/}).click();await page.waitForFunction(()=>document.getElementById('beImg')?.complete&&BE_VIEW?.transform&&BE.boxes.length===1);
if(dpr===2){
 // Save via the actual endpoint. Intercept only to retain the submitted bytes.
 let sent;await page.route('**/api/jobs/resize/detections',async route=>{if(route.request().method()==='POST')sent=route.request().postDataJSON();await route.continue()});
 const chosen=await selectedBox(),manual=await page.evaluate(()=>BE.adds[0].box.slice());
 await page.getByRole('button',{name:'Save changes & re-render',exact:true}).click();
 await page.getByRole('status').filter({hasText:'Rendering with saved edits'}).waitFor();
 const saved=await(await page.request.get(url+'/api/jobs/resize/report')).json();
 near(saved.detections[0].cbox,chosen.map((n,i)=>n-(i%2?12:20)),1e-8);
 near(sent.box_overrides['0'],saved.detections[0].cbox,1e-8);assert.equal(saved.detections.length,2);
 fs.writeFileSync(root+'/saved-report.json',JSON.stringify(saved,null,2));
 let actual;for(let i=0;i<900;i++){actual=await(await page.request.get(url+'/api/jobs/resize')).json();if(actual.phase==='error')throw Error(actual.error);if(actual.phase==='done'&&actual.has_output)break;await page.waitForTimeout(100)}
 assert.equal(actual.phase,'done');assert(actual.has_output);
 const output=await page.request.get(url+'/api/jobs/resize/download');assert(output.ok());fs.writeFileSync(root+'/actual-output.mp4',await output.body());
 await page.reload();await page.getByRole('link',{name:'synthetic-resize.mp4',exact:true}).click();
 await page.getByRole('button',{name:'Preview & edit blur boxes',exact:true}).click();await page.waitForFunction(()=>document.getElementById('beImg')?.complete&&BE_VIEW?.transform&&BE.boxes.length===2);
 near(await selectedBox(),chosen,1e-8);const reopened=await measure('saved-reopened');assert(Math.max(...reopened.paint.edgeDelta.map(Math.abs))<=2);
 result.persistence={chosenSource:chosen,manualSource:manual,sent,savedContent:saved.detections[0].cbox,render:actual.phase,outputBytes:(await output.body()).length};
}
result.errors=errors;result.warnings=warnings;result.requests=requests;
fs.writeFileSync(root+`/results-${dpr}.json`,JSON.stringify(result,null,2));
assert.deepEqual(errors,[]);
const conflicts=await Promise.all(responses);const obsolete=conflicts.filter(r=>/\/(thumb|detframe)\/\d+\?v=/.test(r.url)&&r.body.error==='thumbnail_obsolete');
const resourceWarnings=warnings.filter(w=>w.includes('Failed to load resource: the server responded with a status of 409'));
assert(resourceWarnings.length<=obsolete.length&&warnings.every(w=>w.includes('willReadFrequently')||resourceWarnings.includes(w)),JSON.stringify({warnings,conflicts}));
result.obsoleteThumbnailResponses=obsolete;
console.log(JSON.stringify({dpr,edgeError:result.edgeError,hit:result.liveHit,states:result.states.map(s=>s.name),persistence:result.persistence,errors,warnings}));

}finally{await context.close()}}}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
