const {chromium}=require('/tmp/openscrub-save-as-20261116/node_modules/playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),crypto=require('node:crypto');
const root='/tmp/openscrub-task650',ids=JSON.parse(fs.readFileSync(root+'/browser-jobs.json'));
(async()=>{
 const browser=await chromium.launch({headless:true});
 const page=await browser.newPage({viewport:{width:1365,height:1000}});
 const errors=[],warnings=[],requests=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(['error','warning'].includes(m.type()))warnings.push(m.text())});
 page.on('request',r=>{if(/\/(detections|render|download|report)$/.test(r.url()))requests.push({url:r.url(),method:r.method()})});
 page.on('dialog',d=>d.dismiss());
 await page.addInitScript(()=>{
  window.qa={mode:'normal',accepted:0,holdAck:false,fail:false,closePending:false};
  const real=window.fetch.bind(window);
  window.fetch=async(url,opts={})=>{
   if(String(url).endsWith('/detections')&&opts.method==='POST'){
    if(qa.fail)opts={...opts,headers:{...opts.headers,'X-Task650-Fail':'yes'}};
    const response=await real(url,opts);qa.saveStatus=response.status;
    if(qa.holdAck){qa.saveCommitted=true;await new Promise((resolve,reject)=>{qa.ack=resolve;qa.lose=reject})}
    return response;
   }return real(url,opts);
  };
  window.showSaveFilePicker=async options=>{
   qa.suggested=options.suggestedName;
   if(qa.mode==='pickHold')await new Promise(r=>qa.pick=r);
   const storage=await navigator.storage.getDirectory();qa.file=await storage.getFileHandle('qa-'+options.suggestedName,{create:true});
   return {createWritable:async()=>{
    const writable=await qa.file.createWritable();return {
     write:async bytes=>{if(qa.holdWrite){qa.writePending=true;await new Promise(r=>qa.write=r);qa.holdWrite=false}await writable.write(bytes);qa.accepted+=bytes.byteLength},
     close:async()=>{if(qa.holdClose){qa.closePending=true;await new Promise(r=>qa.close=r)}await writable.close()},
     abort:()=>writable.abort()
    };
   }};
  };
 });
 await page.goto('http://127.0.0.1:18650');assert.equal(await page.title(),'OpenScrub');
 assert.match(await page.locator('body').innerText(),/OpenScrub/);
 assert.equal(await page.locator('nextjs-portal,vite-error-overlay').count(),0);
 await page.evaluate(id=>openJob(id),ids.alpha);
 await page.getByRole('button',{name:'Save redacted video as…'}).waitFor();
 // Capture job/file at the actual button click, while its controlled picker is pending.
 await page.evaluate(()=>{qa.mode='pickHold';qa.holdWrite=true;qa.holdClose=true});
 await page.getByRole('button',{name:'Save redacted video as…'}).click();
 await page.waitForFunction(()=>!!qa.pick);
 await page.evaluate(id=>openJob(id),ids.beta);await page.waitForFunction(id=>EXPORT_NAMES.id===id,ids.beta);
 await page.evaluate(()=>qa.pick());await page.waitForFunction(()=>qa.writePending);
 assert.equal(await page.locator('#export-video-feedback').isHidden(),true);
 assert.ok(requests.some(r=>r.url.endsWith('/'+ids.alpha+'/download')));
 await page.evaluate(id=>openJob(id),ids.alpha);await page.waitForFunction(id=>EXPORT_NAMES.id===id,ids.alpha);
 await page.getByRole('button',{name:'Re-open review',exact:true}).click();await page.locator('#bb0').waitFor();
 await page.locator('#bb0').click();assert.equal(await page.locator('#bb0').innerText(),'Keep');
 await page.evaluate(()=>qa.holdAck=true);
 await page.getByRole('button',{name:'Save edits & render',exact:true}).click();
 await page.waitForFunction(()=>qa.saveCommitted);
 // A later edit and a job switch survive a committed response held in fetch.
 await page.locator('#bb1').click();assert.equal(await page.locator('#bb1').innerText(),'Keep');
 await page.evaluate(id=>openJob(id),ids.beta);await page.waitForFunction(id=>EXPORT_NAMES.id===id,ids.beta);
 await page.evaluate(()=>qa.ack());await page.waitForFunction(()=>[...REVIEW_DRAFTS.values()].every(d=>!d.busy));
 assert.equal(requests.filter(r=>r.url.endsWith('/render')&&r.method==='POST').length,0);
 await page.evaluate(id=>openJob(id),ids.alpha);await page.waitForFunction(id=>EXPORT_NAMES.id===id,ids.alpha);
 await page.getByRole('button',{name:'Re-open review',exact:true}).click();await page.locator('#bb1').waitFor();
 assert.equal(await page.locator('#bb1').innerText(),'Keep');
 const before=await page.evaluate(async()=>await(await fetch(`api/jobs/${CUR}/report`)).json());
 assert.equal(before.detections[0].enabled,false);assert.equal(before.detections[1].enabled,true);
 // The actual publication boundary fails and returns HTTP500. Draft and review stay usable.
 await page.evaluate(()=>{qa.holdAck=false;qa.fail=true});
 await page.getByRole('button',{name:'Save edits & render',exact:true}).click();
 await page.waitForFunction(()=>document.getElementById('reviewSaveStatus').textContent.includes('drafts retained'));
 assert.equal(await page.evaluate(()=>qa.saveStatus),500);
 assert.equal(requests.filter(r=>r.url.endsWith('/render')&&r.method==='POST').length,0);
 assert.equal(await page.locator('#bb1').innerText(),'Keep');
 assert.deepEqual(await page.evaluate(async()=>await(await fetch(`api/jobs/${CUR}/report`)).json()),before);
 // Unaccepted destination bytes stay at zero; finish data then hold the real OPFS close.
 assert.equal(await page.evaluate(id=>EXPORTS.get(id+':video').written,ids.alpha),0);
 await page.evaluate(()=>qa.write());await page.waitForFunction(()=>qa.closePending);
 assert.match(await page.locator('#export-video-status').innerText(),/Finalizing/);
 assert.equal(await page.evaluate(()=>qa.accepted),4194304);
 assert.equal(await page.evaluate(id=>EXPORTS.get(id+':video').active,ids.alpha),true);
 await page.screenshot({path:root+'/browser-pending-desktop.png',fullPage:true});
 await page.evaluate(id=>openJob(id),ids.beta);await page.waitForFunction(id=>EXPORT_NAMES.id===id,ids.beta);
 assert.equal(await page.locator('#export-video-feedback').isHidden(),true);
 await page.evaluate(()=>qa.close());
 await page.waitForFunction(id=>EXPORTS.get(id+':video').phase==='saved',ids.alpha);
 await page.evaluate(id=>openJob(id),ids.alpha);await page.waitForFunction(()=>document.getElementById('export-video-status')?.textContent.startsWith('Saved'));
 const facts=await page.evaluate(async()=>{const f=await qa.file.getFile();return {size:f.size,name:qa.suggested,bytes:Array.from(new Uint8Array(await f.arrayBuffer()).slice(0,256))}});
 assert.equal(facts.size,4194304);assert.equal(facts.name,'synthetic-alpha_redacted.mp4');assert.deepEqual(facts.bytes,Array.from({length:256},(_,i)=>i));
 await page.setViewportSize({width:390,height:844});await page.screenshot({path:root+'/browser-saved-mobile.png',fullPage:true});
 assert.deepEqual(errors,[]);
 fs.writeFileSync(root+'/browser-results.json',JSON.stringify({url:page.url(),title:await page.title(),errors,warnings,requests,facts,checks:['real emitted UI and HTTP','controlled picker; real OPFS writes/close','picker held across job switch','review ACK held across newer edit and job switch','HTTP500 report publish failure retains draft and no render','accepted bytes stay zero until write','finalizing until destination close','job/kind state isolation']},null,2));
 console.log('Task650 combined Chromium/actual HTTP/real OPFS schedules: passed');
 await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
