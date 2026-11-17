const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const ROOT='/tmp/openscrub-save-as-20261116';
(async()=>{
const browser=await chromium.launch({headless:true});
const page=await browser.newPage({viewport:{width:1365,height:950},acceptDownloads:true});
const errors=[],consoleWarnings=[],exportRequests=[],samples=[];
page.on('pageerror',e=>errors.push(e.message));
page.on('console',m=>{if(['error','warning'].includes(m.type()))consoleWarnings.push(m.text());});
page.on('request',r=>{if(/\/api\/jobs\/[^/]+\/(download|report)$/.test(r.url()))exportRequests.push(r.url());});
await page.addInitScript(()=>{
 window.qa={mode:'cancel',options:[],accepted:0,fetched:0,maxAhead:0,maxChunk:0,inflight:0,maxInflight:0,pause:false,closePending:false,writeDelay:8};
 const realFetch=window.fetch;
 window.fetch=async(...args)=>{
  const r=await realFetch(...args);
  if(/api\/jobs\/[^/]+\/(download|report)$/.test(String(args[0]))&&r.body){
   const original=r.body.getReader.bind(r.body);
   r.body.getReader=()=>{const reader=original(),read=reader.read.bind(reader);reader.read=async()=>{const result=await read();if(!result.done){qa.fetched+=result.value.byteLength;qa.maxChunk=Math.max(qa.maxChunk,result.value.byteLength);qa.maxAhead=Math.max(qa.maxAhead,qa.fetched-qa.accepted);}return result;};return reader;};
  }return r;
 };
 Response.prototype.blob=()=>{throw Error('whole-response blob forbidden in QA');};
 window.showSaveFilePicker=async options=>{
  qa.options.push(options);
  if(qa.mode==='cancel')throw new DOMException('Picker cancelled','AbortError');
  if(qa.mode==='picker-error')throw Error('picker unavailable');
  if(qa.mode==='pick-pause')await new Promise(r=>qa.releasePicker=r);
  const root=await navigator.storage.getDirectory();
  qa.file=await root.getFileHandle('qa-'+options.suggestedName,{create:true});
  return {createWritable:async()=>{
   const writable=await qa.file.createWritable();
   return {write:async value=>{
    qa.inflight++;qa.maxInflight=Math.max(qa.maxInflight,qa.inflight);
    if(qa.pause)await new Promise(r=>qa.releaseWrite=r);
    if(qa.accepted-(qa.lastDelayed||0)>=256*1024){qa.lastDelayed=qa.accepted;await new Promise(r=>setTimeout(r,qa.writeDelay));}
    if(qa.mode==='write-error'){qa.inflight--;throw Error('synthetic disk full');}
    await writable.write(value);qa.accepted+=value.byteLength;qa.inflight--;
   },close:async()=>{
    if(qa.mode==='large'){qa.closePending=true;await new Promise(r=>qa.releaseClose=r);}
    if(qa.mode==='close-error')throw Error('synthetic close failure');
    await writable.close();
   },abort:async()=>{qa.aborted=true;await writable.abort();}};
  }};
 };
});
await page.goto('http://127.0.0.1:18484');assert.equal(await page.title(),'OpenScrub');
await page.evaluate(()=>openJob('alpha'));
const save=()=>page.getByRole('button',{name:'Save redacted video as…'});
await save().waitFor();assert.ok((await page.locator('body').innerText()).includes('OpenScrub'));
// Picker cancellation: a click must cause zero export network traffic.
await save().click();await page.waitForTimeout(300);assert.equal(exportRequests.length,0);assert.equal(await save().isEnabled(),true);
// Picker selection can finish after a job switch, but keeps the clicked route/name.
await page.evaluate(()=>{qa.mode='pick-pause';});await save().click();
await page.evaluate(()=>openJob('beta'));await page.waitForFunction(()=>EXPORT_NAMES.id==='beta');
await page.evaluate(()=>qa.releasePicker());await page.waitForTimeout(200);
assert.ok(exportRequests[0].endsWith('/alpha/download'));
assert.equal(await page.locator('#export-video-feedback').isHidden(),true);
// Abort this deliberately slow original export by making its next disk write fail.
await page.evaluate(()=>qa.mode='write-error');await page.waitForTimeout(200);
await page.evaluate(()=>openJob('alpha'));await page.waitForFunction(()=>document.querySelector('#export-video-status')?.textContent.includes('synthetic disk full'));
assert.ok(await save().isEnabled());
// Network and write failures keep an actionable state and support retry.
await page.route('**/api/jobs/alpha/download',r=>r.abort('failed'));
await page.evaluate(()=>qa.mode='normal');await save().click();
await page.waitForFunction(()=>document.querySelector('#export-video-status').textContent.includes('Save failed'));
assert.match(await page.locator('#export-video-status').innerText(),/Try Save As again/);
await page.unroute('**/api/jobs/alpha/download');
await page.evaluate(()=>{qa.mode='write-error';qa.accepted=qa.fetched=0;});await save().click();
await page.waitForFunction(()=>document.querySelector('#export-video-status').textContent.includes('synthetic disk full'));
await page.screenshot({path:ROOT+'/failed-write.png'});
// Real HTTP -> OPFS disk. Throttle both network and writes; delay final close.
const cdp=await page.context().newCDPSession(page);await cdp.send('Network.enable');
await cdp.send('Network.emulateNetworkConditions',{offline:false,latency:10,downloadThroughput:16*1024*1024,uploadThroughput:-1});
await page.evaluate(()=>{Object.assign(qa,{mode:'large',accepted:0,fetched:0,maxAhead:0,maxChunk:0,maxInflight:0,pause:false,aborted:false,closePending:false,lastDelayed:0});});
await save().click();await page.waitForFunction(()=>qa.accepted>1024*1024);
await page.locator('#export-video').scrollIntoViewIfNeeded();
const sampler=setInterval(async()=>{try{samples.push({time:Date.now(),...(await cdp.send('Runtime.getHeapUsage')),ui:await page.locator('#export-video-status').innerText(),...(await page.evaluate(()=>({accepted:qa.accepted,fetched:qa.fetched})))});fs.writeFileSync(ROOT+'/browser-live.json',JSON.stringify(samples.at(-1)));}catch{}},1000);
await page.waitForTimeout(3300);
assert.match(await page.locator('#export-video-status').innerText(),/%.*elapsed.*left/);
await page.screenshot({path:ROOT+'/progress-desktop.png'});
// Force a pending destination write for >5s and verify bytes stay fixed.
await page.evaluate(()=>qa.pause=true);await page.waitForFunction(()=>!!qa.releaseWrite);
const held=await page.evaluate(()=>qa.accepted);await page.waitForTimeout(5500);
let text=await page.locator('#export-video-status').innerText();assert.match(text,/Waiting for data or disk/);assert.doesNotMatch(text,/left/);assert.equal(await page.evaluate(()=>qa.accepted),held);
await page.screenshot({path:ROOT+'/waiting.png'});
// Switch away/back while transfer is pending and polling remains active.
await page.evaluate(()=>openJob('beta'));await page.waitForFunction(()=>EXPORT_NAMES.id==='beta');
assert.equal(await page.locator('#export-video-feedback').isHidden(),true);
await page.evaluate(()=>openJob('alpha'));await page.waitForFunction(()=>document.querySelector('#export-video-status')?.textContent.includes('Waiting'));
await page.evaluate(()=>{qa.pause=false;qa.releaseWrite();delete qa.releaseWrite;});
await page.waitForFunction(()=>qa.closePending||EXPORTS.get('alpha:video')?.phase==='failed',null,{timeout:180000});
assert.equal(await page.evaluate(()=>qa.closePending),true,await page.locator('#export-video-status').innerText());
text=await page.locator('#export-video-status').innerText();assert.match(text,/Finalizing/);assert.doesNotMatch(text,/Saved/);
const written=await page.evaluate(()=>qa.accepted);assert.equal(written,268435456);
const progressValue=await page.locator('#export-video-progress').evaluate(el=>({value:el.value,max:el.max}));assert.deepEqual(progressValue,{value:268435456,max:268435456});
await page.waitForTimeout(1100);assert.match(await page.locator('#export-video-status').innerText(),/Finalizing/);
await page.locator('#export-video').scrollIntoViewIfNeeded();await page.screenshot({path:ROOT+'/finalizing.png'});
await page.evaluate(()=>qa.releaseClose());await page.waitForFunction(()=>document.querySelector('#export-video-status').textContent.startsWith('Saved'));
const facts=await page.evaluate(async()=>({accepted:qa.accepted,fileSize:(await qa.file.getFile()).size,maxAhead:qa.maxAhead,maxChunk:qa.maxChunk,maxInflight:qa.maxInflight}));
assert.equal(facts.fileSize,268435456);assert.equal(facts.maxInflight,1);assert.ok(facts.maxAhead<=facts.maxChunk);
clearInterval(sampler);await cdp.send('Network.emulateNetworkConditions',{offline:false,latency:0,downloadThroughput:-1,uploadThroughput:-1});
await page.waitForTimeout(1000);assert.match(await page.locator('#export-video-status').innerText(),/^Saved/); // survived normal poll
await page.screenshot({path:ROOT+'/saved.png'});
// Repeat audit exports and a failed close use the same visible controls.
await page.evaluate(()=>qa.mode='close-error');await page.getByRole('button',{name:'Save audit report as…'}).click();
await page.waitForFunction(()=>document.querySelector('#export-report-status').textContent.includes('synthetic close failure'));
await page.evaluate(()=>qa.mode='normal');await page.getByRole('button',{name:'Save audit report as…'}).click();
await page.waitForFunction(()=>document.querySelector('#export-report-status').textContent.startsWith('Saved'));
assert.equal(await page.evaluate(async()=>(await qa.file.getFile()).size),18);
await page.getByRole('button',{name:'Save audit report as…'}).click();await page.waitForFunction(()=>document.querySelector('#export-report-status').textContent.startsWith('Saved'));
await page.setViewportSize({width:390,height:844});await page.locator('#export-video').scrollIntoViewIfNeeded();
await page.screenshot({path:ROOT+'/progress-mobile.png'});
const overflow=await page.evaluate(()=>({width:innerWidth,body:document.documentElement.scrollWidth,exportWidth:document.querySelector('#export-video').getBoundingClientRect().width}));
// Unsupported picker: direct download link, browser event, honest in-app status.
const fallback=await browser.newPage({viewport:{width:1365,height:950},acceptDownloads:true});
await fallback.addInitScript(()=>{window.showSaveFilePicker=undefined;});await fallback.goto('http://127.0.0.1:18484');await fallback.evaluate(()=>openJob('alpha'));
await fallback.getByRole('link',{name:'Download audit report',exact:true}).waitFor();
assert.equal(await fallback.getByRole('button',{name:'Save audit report as…'}).count(),0);
const downloadPromise=fallback.waitForEvent('download');await fallback.getByRole('link',{name:'Download audit report',exact:true}).click();
const download=await downloadPromise;assert.equal(download.suggestedFilename(),'synthetic.alpha_audit.json');
assert.match(await fallback.locator('#export-report-status').innerText(),/Download started — see browser downloads/);
assert.equal(await fallback.locator('#export-report-progress').isVisible(),false);
await fallback.locator('#export-report').scrollIntoViewIfNeeded();await fallback.screenshot({path:ROOT+'/fallback.png'});
assert.deepEqual(errors,[]);
const result={url:page.url(),title:await page.title(),viewports:['1365x950','390x844'],facts,overflow,errors,consoleWarnings,exportRequests,samples};
fs.writeFileSync(ROOT+'/browser-results.json',JSON.stringify(result,null,2));console.log(JSON.stringify({...result,samples:samples.length}));
await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
