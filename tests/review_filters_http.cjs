const {chromium}=require(process.env.OPENSCRUB_PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),root=process.env.VERIFY_RUN,origin='http://127.0.0.1:18551';let browser;
(async()=>{browser=await chromium.launch({headless:true});const context=await browser.newContext({viewport:{width:1365,height:1000}}),page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.stack));page.on('dialog',d=>d.dismiss());
await page.goto(origin);assert.equal(await page.title(),'OpenScrub');await page.evaluate(()=>openJob('A'));await page.locator('#reviewOutput').waitFor();assert.equal(await page.locator('#reviewFilterStatus').innerText(),'7 of 7 cards match');
await page.locator('#kb3').click();await page.locator('#bb0').click();await page.locator('#reviewZones summary').click();await page.locator('#bb8').click();await page.locator('#kb9').click();await page.locator('#reviewZones summary').click();
await page.locator('button[onclick="loadBoxEdit(1)"]').click();await page.locator('#beCv').waitFor();
// Disclosed fixture prerequisite: base Play startup is owned by P16D.
await page.evaluate(()=>{const v=document.getElementById('beVid');v.src=`api/jobs/${CUR}/video`;v.load()});await page.waitForFunction(()=>document.getElementById('beVid').readyState>=1);
await page.locator('#bePlay').click();await page.waitForFunction(()=>document.getElementById('beVid').currentTime>.15);
const playback=await page.evaluate(()=>{window.videoNode=document.getElementById('beVid');window.editorObject=BE;return videoNode.currentTime});
await page.locator('#reviewType').selectOption('email');await page.waitForFunction(before=>videoNode.currentTime>before,playback);
assert.equal(await page.evaluate(()=>!videoNode.paused&&videoNode===document.getElementById('beVid')&&editorObject===BE),true);await page.locator('#bePlay').click();await page.locator('#reviewFilterReset').click();
await page.locator('#beT').fill('1');await page.locator('#beT').dispatchEvent('input');await page.waitForFunction(()=>BE.boxes.some(x=>x.i===1)&&BE.scale>0);
const canvas=page.locator('#beCv');await canvas.scrollIntoViewIfNeeded();let b=await canvas.boundingBox(),scale=await page.evaluate(()=>BE.scale);
await canvas.click({position:{x:82*scale,y:32*scale}});assert.equal(await page.evaluate(()=>BE.sel),1);await page.locator('#beRm').click();assert.deepEqual(await page.evaluate(()=>[EN[0],EN[1],EN[2]]),[true,false,true]);
// Pending additive fields use the existing editor/save owner; filter sees no manual cards.
await page.evaluate(()=>{BE.ov[0]=[25,25,49,49];BE.times[0]=[.2,2.5];BE.adds.push({t0:.5,t1:2.5,tref:1,box:[500,100,530,130]});BE.audio=[{t0:.5,t1:.7,mode:'mute'}];BE.audioLoaded=true;BE.audioSaved=[]});
await page.locator('#reviewType').selectOption('email');await page.locator('#reviewOutput').selectOption('blur');assert.equal(await page.locator('#reviewFilterStatus').innerText(),'0 of 7 cards match');
await context.request.post(origin+'/__qa__/control',{data:{render:false}});await page.getByRole('button',{name:'Save edits & render',exact:true}).click();await page.waitForFunction(()=>document.getElementById('reviewSaveStatus').textContent.includes('requesting render'));
const report=await(await context.request.get(origin+'/api/jobs/A/report')).json(),initial=JSON.parse(fs.readFileSync(root+'/initial-report.json'));
assert.equal(report.detections.length,11);assert.deepEqual(report.detections.slice(0,10).map(r=>r.enabled),[true,false,true,false,false,false,true,false,true,false]);
assert.deepEqual(report.detections[0].cbox,[25,25,49,49]);assert.deepEqual([report.detections[0].t_start,report.detections[0].t_end],[.2,2.5]);assert.deepEqual(report.detections[10].cbox,[500,100,530,130]);assert.deepEqual(report.audio_redactions,[{t0:.5,t1:.7,mode:'mute'}]);
for(let i=0;i<10;i++)for(const [key,value]of Object.entries(initial.detections[i]))if(key!=='enabled'&&!(i===0&&['cbox','t_start','t_end','last_seen'].includes(key)))assert.deepEqual(report.detections[i][key],value,`row${i}/${key}`);
fs.writeFileSync(root+'/pre-render-report.json',JSON.stringify(report,null,2));
const fresh=await context.newPage();await fresh.goto(origin);await fresh.evaluate(()=>openJob('A'));await fresh.locator('#reviewOutput').waitFor();assert.equal(await fresh.locator('#reviewOutput').inputValue(),'all');assert.equal(await fresh.evaluate(()=>Object.keys(EDITS.enabled).length),0);assert.deepEqual(await fresh.evaluate(()=>Array.from({length:10},(_,i)=>EN[i])),report.detections.slice(0,10).map(r=>r.enabled));
await context.request.post(origin+'/__qa__/control',{data:{render:true}});const phases=[];let job;
for(let n=0;n<200;n++){job=await(await context.request.get(origin+'/api/jobs/A')).json();phases.push(job.phase);if(['done','error'].includes(job.phase))break;await fresh.waitForTimeout(100)}assert.equal(job.phase,'done',JSON.stringify(job));assert.deepEqual(errors,[]);
const results={page:'actual HTTP full PAGE',playbackPrerequisite:'native video.load() before existing Play, P16D startup excluded',playbackPreserved:true,savedRows:report.detections.length,rawReopen:true,phase:job.phase,phases,errors};fs.writeFileSync(root+'/http-results.json',JSON.stringify(results,null,2));console.log(JSON.stringify(results));await browser.close();browser=null;
})().catch(async e=>{console.error(e);if(browser)await browser.close();process.exitCode=1});
