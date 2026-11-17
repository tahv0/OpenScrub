from pathlib import Path
p=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub/tests/editor_resize_browser.cjs')
s=p.read_text()
s=s.replace("try{const page=await context.newPage(),errors=[],requests=[];", """try{const page=await context.newPage(),errors=[],requests=[],warnings=[];
await page.addInitScript(()=>{
 const Native=ResizeObserver;window.resizeObservers=[];
 window.ResizeObserver=class extends Native{
  constructor(callback){super(callback);this.callback=callback;this.disconnected=false;resizeObservers.push(this);}
  disconnect(){this.disconnected=true;super.disconnect();}
 };
});
page.on('console',m=>{if(['error','warning'].includes(m.type()))warnings.push(m.text())});""")
s=s.replace("    const data=await page.evaluate(()=>{", "    await page.evaluate(()=>{BE.sel=-1;beDraw()});\n    const data=await page.evaluate(()=>{")
s=s.replace("const before=requests.length;", "const originalGeometry=await page.evaluate(()=>JSON.stringify({ov:BE.ov,times:BE.times,adds:BE.adds,t:BE.t,boxes:BE.boxes}));\nconst before=requests.length;")
s=s.replace("assert.deepEqual(errors,[]);",r'''
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
await page.locator('#bePlay').click();await page.waitForFunction(()=>BE.playing&&BE_VIEW.transform?.media===document.getElementById('beVid'));
await page.setViewportSize({width:390,height:844});await page.waitForTimeout(120);
const videoState=await page.evaluate(()=>{const v=document.getElementById('beVid'),c=document.getElementById('beCv');const r=v.getBoundingClientRect(),q=c.getBoundingClientRect();return {video:r.width,canvas:q.width,source:v.videoWidth,owner:BE_VIEW.transform.media===v}});
assert.equal(videoState.video,videoState.canvas);assert.equal(videoState.source,640);assert(videoState.owner);
await page.locator('#bePlay').click();await page.waitForFunction(()=>!BE.playing&&document.getElementById('beImg').complete&&BE_VIEW.transform?.media===document.getElementById('beImg'));
result.video=videoState;
// Close/remount and job switches disconnect the observer; even deliberately
// delivered stale callbacks cannot clear or repaint the current mount.
await page.evaluate(()=>{window.outgoingObserver=resizeObservers.at(-1);window.outgoingImage=document.getElementById('beImg');window.lateImage=outgoingImage.onload;loadReview()});
assert(await page.evaluate(()=>outgoingObserver.disconnected));assert.equal(await page.locator('#beCv').count(),0);
await page.getByRole('button',{name:/Preview video & edit boxes/}).click();await page.waitForFunction(()=>document.getElementById('beImg')?.complete&&BE_VIEW?.transform&&BE.boxes.length===1);
const currentPixels=await page.evaluate(()=>document.getElementById('beCv').toDataURL());
await page.evaluate(()=>{outgoingObserver.callback([]);lateImage()});
assert.equal(await page.evaluate(()=>document.getElementById('beCv').toDataURL()),currentPixels);
await page.evaluate(()=>{window.oldView=BE_VIEW;window.oldObserver=resizeObservers.at(-1);openJob('resize')});
await page.getByRole('button',{name:/Preview video & edit boxes/}).click();await page.waitForFunction(()=>document.getElementById('beImg')?.complete&&BE_VIEW?.transform&&BE.boxes.length===1);
assert(await page.evaluate(()=>oldObserver.disconnected));const newPixels=await page.evaluate(()=>document.getElementById('beCv').toDataURL());
await page.evaluate(()=>oldObserver.callback([]));assert.equal(await page.evaluate(()=>document.getElementById('beCv').toDataURL()),newPixels);
assert.equal(await page.evaluate(()=>JSON.stringify({ov:BE.ov,times:BE.times,adds:BE.adds})),drafts);
const final=await measure('mobile-edited');assert(Math.max(...final.paint.edgeDelta.map(Math.abs))<=2);
// Ordinary enlarged review preview and embedded editor help survive.
assert((await page.locator('body').innerText()).includes('drag inside to move'));
await page.evaluate(()=>zoomDet(0));await page.locator('#lb img').waitFor();await page.locator('#lb').click();assert.equal(await page.locator('#lb').count(),0);
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
 await page.getByRole('button',{name:'Preview & edit blur boxes',exact:true}).click();await page.waitForFunction(()=>document.getElementById('beImg')?.complete&&BE_VIEW?.transform&&BE.boxes.length===2);
 near(await selectedBox(),chosen,1e-8);const reopened=await measure('saved-reopened');assert(Math.max(...reopened.paint.edgeDelta.map(Math.abs))<=2);
 result.persistence={chosenSource:chosen,manualSource:manual,sent,savedContent:saved.detections[0].cbox,render:actual.phase,outputBytes:(await output.body()).length};
}
result.errors=errors;result.warnings=warnings;result.requests=requests;
fs.writeFileSync(root+`/results-${dpr}.json`,JSON.stringify(result,null,2));
assert.deepEqual(errors,[]);assert(warnings.every(w=>w.includes('willReadFrequently')),warnings.join('\n'));
console.log(JSON.stringify({dpr,edgeError:result.edgeError,hit:result.liveHit,states:result.states.map(s=>s.name),persistence:result.persistence,errors,warnings}));
''')
p.write_text(s)
