const {chromium}=require('/tmp/openscrub-save-as-20261116/node_modules/playwright');
const assert=require('node:assert/strict'),fs=require('node:fs');
const root='/tmp/openscrub-task631',job=JSON.parse(fs.readFileSync(root+'/browser-job.json'));
const snap=()=>{const s=fs.statSync(job.path,{bigint:true});return {bytes:fs.readFileSync(job.path).toString(),ino:String(s.ino),mtime:String(s.mtimeNs),mode:String(s.mode)}};
(async()=>{
 const browser=await chromium.launch({headless:true});const page=await browser.newPage({viewport:{width:1280,height:950}});
 const errors=[],logs=[];page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(['warning','error'].includes(m.type()))logs.push(m.text())});
 await page.addInitScript(()=>{window.qa={requests:[],held:[],hold:true,commits:0,renders:0};const real=window.fetch.bind(window);
 window.fetch=async(url,options={})=>{if(String(url).endsWith('/render')&&options.method==='POST')qa.renders++;
 if(String(url).endsWith('/detections')&&options.method==='POST'){qa.requests.push(JSON.parse(options.body));const result=await real(url,options);qa.commits++;
 if(qa.hold)await new Promise(resolve=>qa.held.push(resolve));return result;}return real(url,options)};});
 await page.goto('http://127.0.0.1:18463');assert.equal(await page.title(),'OpenScrub');assert.match(await page.locator('body').innerText(),/OpenScrub/);
 await page.evaluate(id=>openJob(id),job.id);await page.waitForFunction(()=>!!document.getElementById('bb0'));
 // Actual bulk Keep button deliberately submits an already-kept value.
 await page.evaluate(()=>{selSet.add(0);showSelMenu(200,200)});await page.locator('.selmenu .mkeep').click();
 assert.equal(await page.evaluate(()=>EDITS.enabled[0]),false);const before=snap();
 await page.getByRole('button',{name:'Save edits & render',exact:true}).click();await page.waitForFunction(()=>qa.commits===1);
 assert.deepEqual(snap(),before);assert.deepEqual(JSON.parse(fs.readFileSync(root+'/browser-publications.json')),[]);
 assert.equal(await page.evaluate(()=>qa.requests[0].enabled[0]),false);
 await page.locator('#bb0').click();assert.equal(await page.evaluate(()=>EDITS.enabled[0]),true);
 await page.evaluate(()=>qa.held.shift()());await page.waitForFunction(()=>!EDITS.busy);
 assert.equal(await page.evaluate(()=>EDITS.enabled[0]),true);assert.equal(await page.evaluate(()=>qa.renders),0);
 assert.match(await page.locator('#reviewSaveStatus').innerText(),/Newer edits/);
 await page.screenshot({path:root+'/browser-newer.png'});
 // Fail a real changed publication inside the actual route, retaining the draft.
 fs.writeFileSync(root+'/fail-next','fail');await page.evaluate(()=>qa.hold=false);
 await page.getByRole('button',{name:'Save edits & render',exact:true}).click();await page.waitForFunction(()=>!EDITS.busy&&qa.commits===2);
 assert.equal(await page.evaluate(()=>EDITS.enabled[0]),true);assert.equal(await page.evaluate(()=>qa.renders),0);
 assert.deepEqual(snap(),before);assert.match(await page.locator('#reviewSaveStatus').innerText(),/not confirmed.*retained/);
 await page.screenshot({path:root+'/browser-failed.png'});
 // Restore the stored Keep value deliberately, then ordinary save-and-render.
 await page.locator('#bb0').click();assert.equal(await page.evaluate(()=>EDITS.enabled[0]),false);
 await page.getByRole('button',{name:'Save edits & render',exact:true}).click();
 await page.waitForFunction(()=>qa.renders===1&&!EDITS.busy);
 let state;const stateDeadline=Date.now()+30000;do{state=await page.evaluate(async id=>await (await fetch('api/jobs/'+id)).json(),job.id);if(state.phase==='done')break;assert.ok(Date.now()<stateDeadline,'render did not finish');await new Promise(r=>setTimeout(r,20))}while(true);assert.equal(state.has_output,true);
 const deadline=Date.now()+10000;while(!JSON.parse(fs.readFileSync(root+'/browser-publications.json')).some(x=>!x.save_route&&x.complete)){assert.ok(Date.now()<deadline,'render publication never completed');await new Promise(r=>setTimeout(r,10))}
 const current=JSON.parse(fs.readFileSync(job.path));assert.equal(current.detections[0].enabled,false);assert.deepEqual(current.custom,{preserved:true});
 const pubs=JSON.parse(fs.readFileSync(root+'/browser-publications.json'));assert.equal(pubs.filter(x=>x.save_route).length,1);assert.equal(pubs[0].failed,true);
 assert.ok(pubs.some(x=>!x.save_route));assert.deepEqual(errors,[]);
 await page.evaluate(id=>openJob(id),job.id);await page.waitForFunction(()=>document.querySelector('#detail')?.textContent.includes('Download redacted video'));
 await page.screenshot({path:root+'/browser-rendered.png'});
 fs.writeFileSync(root+'/browser-results.json',JSON.stringify({url:page.url(),title:await page.title(),requests:await page.evaluate(()=>qa.requests),renders:await page.evaluate(()=>qa.renders),publications:pubs,errors,console:logs,current},null,2));
 await browser.close();console.log('same-value acknowledgement, newer edit, real failed-save retention, no-op save-and-render: passed');
})().catch(e=>{console.error(e);process.exit(1)});
