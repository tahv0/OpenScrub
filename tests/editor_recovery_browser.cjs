const {chromium}=require(process.env.OPENSCRUB_PLAYWRIGHT_MODULE);
const assert=require('node:assert/strict'),fs=require('node:fs');
const [url,root]=process.argv.slice(2);
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.OPENSCRUB_CHROMIUM});
 const page=await browser.newPage({viewport:{width:1100,height:950}}),errors=[],warnings=[],requests=[];
 page.on('pageerror',e=>errors.push(e.message));
 page.on('console',m=>{if(['warning','error'].includes(m.type()))warnings.push(m.text())});
 page.on('request',r=>{if(r.method()==='GET'&&r.url().endsWith('/cfr24/detections'))requests.push(r.url())});
 page.on('dialog',d=>d.accept());
 try{
  await page.goto(url);assert.equal(await page.title(),'OpenScrub');
  assert((await page.locator('body').innerText()).includes('OpenScrub'));
  assert.equal(await page.locator('vite-error-overlay,nextjs-portal').count(),0);
  await page.getByRole('link',{name:'exact-cfr24.mp4',exact:true}).click();
  await page.getByRole('button',{name:/Preview video & edit boxes/}).click();await page.waitForFunction(()=>beReady());
  const target=await page.evaluate(()=>BE.boxes.find(b=>b.i===0).box),cv=page.locator('#beCv');
  const point=async(x,y)=>cv.evaluate((el,p)=>{const r=el.getBoundingClientRect(),im=document.getElementById('beImg');
   return {x:r.x+p[0]*r.width/im.naturalWidth,y:r.y+p[1]*r.height/im.naturalHeight}},[x,y]);
  const center=await point((target[0]+target[2])/2,(target[1]+target[3])/2);
  await page.mouse.click(center.x,center.y);await page.mouse.move(center.x,center.y);await page.mouse.down();
  await page.mouse.move(center.x+4,center.y+3);await page.mouse.up();
  assert(await page.evaluate(()=>!!BE.geometry[0]&&!!BE.ov[0]));
  await page.evaluate(()=>{applyDet(1,true);BE.audio=[{t0:0,t1:.1,mode:'mute'}];BE.audioLoaded=true;
   MAN.push({manual_id:'keep-draft',t_start:0,t_end:1,t_ref:0,screen_box:[1,2,20,22]});stopPolling()});
  let release,entered;const gate=new Promise(r=>release=r),started=new Promise(r=>entered=r);let first=true;
  const pattern='**/api/jobs/cfr24/detections';
  await page.route(pattern,async route=>{if(route.request().method()!=='GET'||!first)return route.continue();
   first=false;const response=await route.fetch();entered();await gate;await route.fulfill({response});});
  const before=requests.length;await page.evaluate(()=>openJob('cfr24'));await started;
  await page.getByRole('button',{name:'Discard geometry and inspect',exact:true}).click();
  await page.waitForFunction(()=>beReady());await page.evaluate(()=>window.inspectedEditor=BE_VIEW);
  release();await page.waitForTimeout(1400);
  assert.equal(requests.length-before,1,'poll preempted explicit editor with another review request');
  assert(await page.evaluate(()=>BE_VIEW===inspectedEditor&&beReady()&&!BE.ov[0]&&EDITS.enabled[1]===true&&
   MAN.some(x=>x.manual_id==='keep-draft')&&BE.audio.length===1));
  assert.equal(await page.locator('#review').count(),0);
  await page.getByRole('button',{name:'Open review',exact:true}).waitFor();
  await page.screenshot({path:root+'/pending-review.png',fullPage:true});
  await page.getByRole('button',{name:'Open review',exact:true}).click();
  await page.waitForFunction(()=>REVIEW_SCHED?.owns()&&AUTO_REVIEW?.state==='ready');
  assert.equal(requests.length-before,2);
  assert(await page.evaluate(()=>EDITS.enabled[1]===true&&MAN.some(x=>x.manual_id==='keep-draft')&&BE.audio.length===1));
  assert.deepEqual(errors,[]);assert.deepEqual(warnings,[]);
  await page.screenshot({path:root+'/restored-review.png',fullPage:true});
  fs.writeFileSync(root+'/recovery.json',JSON.stringify({page:url,heldAutomatic:true,editorPreserved:true,
   requests:requests.length-before,explicitReview:true,draftsPreserved:true,errors,warnings},null,2));
  console.log('AUTO_REVIEW_SUPERSESSION_AND_DELIBERATE_RECOVERY_OK');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
