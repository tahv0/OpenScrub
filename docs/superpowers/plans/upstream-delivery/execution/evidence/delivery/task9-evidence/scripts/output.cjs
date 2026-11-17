const fs=require('node:fs'),assert=require('node:assert/strict');const ROOT='/home/tahv0/src/OpenScrub/.superpowers/sdd/README/runtime/task9';process.env.TMPDIR=ROOT+'/tmp';process.env.PLAYWRIGHT_BROWSERS_PATH='/tmp/openscrub-save-as-20261116/browsers';const{chromium}=require('/tmp/openscrub-save-as-20261116/node_modules/playwright');let browser;
(async()=>{browser=await chromium.launch({headless:true});const context=await browser.newContext({viewport:{width:1365,height:950}}),page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.stack));
// Exact-base, small only: actual PAGE and real metadata/JPEG routes, no timing.
await page.goto('http://127.0.0.1:18510');await page.evaluate(()=>openJob('small'));await page.waitForSelector('#review');await page.locator('#kb2').click();assert.equal(await page.evaluate(()=>EN[1]===false&&EN[2]===false),true);
const baseline=await page.evaluate(()=>({cards:document.querySelectorAll('#detwrap .det').length,images:document.querySelectorAll('#detwrap img').length,closedZoneCards:document.querySelectorAll('details .det').length,group:TRKMEM[2],choice:[EN[1],EN[2]]}));
await page.evaluate(()=>openJob('beta'));await page.waitForSelector('#review');await page.evaluate(()=>openJob('small'));await page.waitForSelector('#review');assert.equal(await page.evaluate(()=>EN[1]===false&&EN[2]===false),true);baseline.revisitDraft=true;
await page.goto('http://127.0.0.1:18509');await page.evaluate(()=>openJob('small'));await page.waitForSelector('#review');await page.evaluate(()=>scrollTo(0,document.getElementById('detwrap').getBoundingClientRect().top+scrollY-55));await page.waitForTimeout(200);
const candidate=await page.evaluate(()=>({cards:document.querySelectorAll('#detwrap .det').length,images:document.querySelectorAll('#detwrap img').length,closedZoneCards:document.querySelectorAll('details .det').length,groups:REVIEW_META.byId.size}));
await page.locator('#kb0').click();await page.locator('#bb2').click();
await page.locator('#review details summary').click();await page.locator('#bb18').click();await page.locator('#kb19').click();await page.locator('#review details summary').click();
await page.getByRole('button',{name:/Preview video & edit boxes/}).click();await page.locator('#beT').focus();for(let i=0;i<10;i++)await page.keyboard.press('ArrowRight');
await page.waitForFunction(()=>BE.raw?.length&&BE.scale>0&&document.getElementById('beCv').width>0);
const canvas=page.locator('#beCv');await canvas.scrollIntoViewIfNeeded();let box=await canvas.boundingBox(),scale=await page.evaluate(()=>BE.scale);
await canvas.click({position:{x:75*scale,y:25*scale}});assert.equal(await page.evaluate(()=>BE.sel),2);
await page.mouse.move(box.x+75*scale,box.y+25*scale);await page.mouse.down();await page.mouse.move(box.x+95*scale,box.y+33*scale,{steps:5});await page.mouse.up();
await page.locator('#beT0').fill('0.2');await page.locator('#beT1').fill('3.5');await page.getByRole('button',{name:'Apply times',exact:true}).click();
await canvas.click({position:{x:75*scale,y:25*scale}});assert.equal(await page.evaluate(()=>BE.sel),1);await page.locator('#beRm').click();assert.equal(await page.evaluate(()=>EN[1]===false&&EN[2]===true),true);
// Actual additive region UI. Preserve the unfinished two-click gesture through
// a local window move before completing it and accepting its two native prompts.
await page.locator('#beAdd').click();await canvas.click({position:{x:550*scale,y:280*scale}});
const anchor=await page.evaluate(()=>BE.addAnchor.slice());await page.evaluate(()=>{window.editor=document.getElementById('beCv');scrollTo(0,document.documentElement.scrollHeight)});await page.waitForTimeout(180);assert.deepEqual(await page.evaluate(()=>BE.addAnchor),anchor);assert.equal(await page.evaluate(()=>editor===document.getElementById('beCv')),true);
const prompts=['0.5','2.5'];page.on('dialog',async d=>{if(d.type()==='prompt')await d.accept(prompts.shift());else await d.dismiss()});
await canvas.click({position:{x:590*scale,y:310*scale}});assert.equal(await page.evaluate(()=>BE.adds.length),1);await page.locator('#beAdd').click();
await page.locator('#beAMode').selectOption('bleep');await page.locator('#beMute').click();await page.locator('#beTL').scrollIntoViewIfNeeded();box=await page.locator('#beTL').boundingBox();await page.mouse.move(box.x+box.width*.375,box.y+63);await page.mouse.down();await page.mouse.move(box.x+box.width*.5,box.y+63,{steps:5});await page.mouse.up();assert.equal(await page.evaluate(()=>BE.audio.length),2);
await page.screenshot({path:ROOT+'/evidence/editor-real-edits.png'});
await page.setViewportSize({width:390,height:844});await page.evaluate(()=>scrollTo(0,document.documentElement.scrollHeight));await page.waitForTimeout(220);assert.equal(await page.locator('#det0').count(),0);assert.equal(await page.evaluate(()=>EN[0]===false&&EN[1]===false&&EN[2]===true&&EN[18]===true&&EN[19]===false),true);
// Actual save remains intact; only the following render dispatch is gated.
await context.request.post('http://127.0.0.1:18509/__qa__/control',{data:{render:false}});
await page.getByRole('button',{name:'Save edits & render',exact:true}).click();await page.waitForFunction(()=>document.getElementById('reviewSaveStatus').textContent.includes('requesting render'));
const fixture=JSON.parse(fs.readFileSync(ROOT+'/evidence/fixtures-candidate.json')).find(x=>x.job==='small');const reportPath=fixture.dir+'/report.json';const saved=JSON.parse(fs.readFileSync(reportPath)),initial=JSON.parse(fs.readFileSync(ROOT+'/evidence/initial-candidate-small.json'));
assert.equal(saved.detections.length,initial.detections.length+1);assert.deepEqual(saved.detections.slice(0,3).map(x=>x.enabled),[false,false,true]);assert.deepEqual(saved.detections.slice(18,20).map(x=>x.enabled),[true,false]);
for(let i=0;i<initial.detections.length;i++)for(const k of Object.keys(initial.detections[i])){
 if(k==='enabled'||(i===2&&['cbox','t_start','t_end','last_seen'].includes(k)))continue;assert.deepEqual(saved.detections[i][k],initial.detections[i][k],`row${i} ${k}`);
}
assert.equal(saved.detections[2].last_seen,.2);assert.deepEqual(saved.detections[2].cbox.map(Math.round),[85,23,109,53]);assert.deepEqual([saved.detections[2].t_start,saved.detections[2].t_end],[.2,3.5]);assert.equal(saved.audio_redactions.length,2);
assert.deepEqual(saved.detections.at(-1).cbox.map(Math.round),[550,280,590,310]);assert.deepEqual([saved.detections.at(-1).t_start,saved.detections.at(-1).t_end],[.5,2.5]);
fs.writeFileSync(ROOT+'/evidence/pre-render-verified.json',JSON.stringify(saved,null,2));
// A fresh page obtains saved decisions over actual HTTP before rendering.
const fresh=await context.newPage();await fresh.goto('http://127.0.0.1:18509');await fresh.evaluate(()=>openJob('small'));await fresh.waitForSelector('#review');assert.equal(await fresh.evaluate(()=>EN[0]===false&&EN[1]===false&&EN[2]===true&&EN[18]===true&&EN[19]===false),true);
const reopened=await fresh.evaluate(()=>({rows:Object.keys(ROWCARD).length,groups:REVIEW_META.byId.size,pending:Object.keys(EDITS.enabled).length,flags:[EN[0],EN[1],EN[2],EN[18],EN[19]]}));assert.equal(reopened.rows,21);assert.equal(reopened.pending,0);
await context.request.post('http://127.0.0.1:18509/__qa__/control',{data:{render:true}});
let job;const phases=[];for(let n=0;n<120;n++){job=await(await context.request.get('http://127.0.0.1:18509/api/jobs/small?sample='+n)).json();phases.push(job.phase);if(['done','error'].includes(job.phase))break;await fresh.waitForTimeout(100)}
assert.equal(job.phase,'done',JSON.stringify(job));
fs.writeFileSync(ROOT+'/evidence/output-browser-results.json',JSON.stringify({baseline,candidate,reopened,savedRows:saved.detections.length,job,errors},null,2));assert.deepEqual(errors,[]);console.log(JSON.stringify({baseline,candidate,reopened,savedRows:saved.detections.length,phase:job.phase,errors}));await browser.close();browser=null;
})().catch(async e=>{console.error(e);if(browser)await browser.close();process.exitCode=1});
