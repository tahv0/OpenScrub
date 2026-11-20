const {chromium}=require(process.env.OPENSCRUB_PLAYWRIGHT_MODULE);
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const [url,root]=process.argv.slice(2);
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.OPENSCRUB_CHROMIUM,args:['--no-sandbox']});
 try{
  const context=await browser.newContext({viewport:{width:1100,height:900}});
  try{
   const page=await context.newPage(),errors=[];page.setDefaultTimeout(8000);
   page.on('pageerror',e=>errors.push(e.message));
   page.on('console',m=>{if(['error','warning'].includes(m.type()))errors.push(m.text())});
   page.on('dialog',d=>{d.accept().catch(()=>{});});
   await page.goto(url);assert.equal(await page.title(),'OpenScrub');
   assert((await page.locator('body').innerText()).includes('OpenScrub'));
   assert.equal(await page.locator('vite-error-overlay,nextjs-portal').count(),0);
   await page.locator('#file').setInputFiles(path.join(root,'runtime','source.mp4'));
   await page.waitForFunction(()=>S.dur>0&&S.wins.length>0);
   await page.locator('#cats .catrow').filter({hasText:/plate/i}).first().locator('input[type=checkbox]').check();
   await page.locator('details summary').filter({hasText:'Advanced settings'}).click();
   assert.equal(await page.locator('#verifyhdrplates').isChecked(),false);
   const note=await page.locator('#verifyhdrplatesNote').innerText();
   assert.match(note,/PQ\/HLG/);assert.match(note,/after restart/);assert.match(note,/full plate box/);
   async function scan(){
    const response=page.waitForResponse(r=>r.url().endsWith('/api/jobs')&&r.request().method()==='POST');
    await page.locator('button.start').click();const r=await response;assert.equal(r.status(),200);
    const id=(await r.json()).jobs[0];
    const options=JSON.parse(fs.readFileSync(path.join(root,'runtime','openscrub_jobs',id,'options.json')));
    await page.waitForFunction(()=>!document.querySelector('button.start').disabled);
    return options;
   }
   const ordinary=await scan();assert(!Object.hasOwn(ordinary,'verify_hdr_plate_frames'));
   await page.locator('#verifyhdrplates').check();
   await page.screenshot({path:root+'/hdr-proof-desktop.png',fullPage:true});
   const enabled=await scan();assert.equal(enabled.verify_hdr_plate_frames,true);
   const remaining={...enabled};delete remaining.verify_hdr_plate_frames;assert.deepEqual(remaining,ordinary);
   await page.locator('#verifyhdrplates').uncheck();
   assert.equal(await page.locator('#verifyhdrplates').isChecked(),false);
   await page.setViewportSize({width:390,height:844});
   await page.screenshot({path:root+'/hdr-proof-mobile.png',fullPage:true});
   const size=await page.evaluate(()=>({scroll:document.documentElement.scrollWidth,client:document.documentElement.clientWidth}));
   assert(size.scroll<=size.client+2,JSON.stringify(size));
   const unexpected=errors.filter(e=>e!=='[openscrub] decode failed (EncodingError; no audio track found)');
   assert.deepEqual(unexpected,[],JSON.stringify(errors));
   fs.writeFileSync(root+'/hdr-proof-browser-result.json',JSON.stringify({ordinary,enabled,errors,viewport:size}));
   console.log('HDR_PROOF_SCAN_SETUP_OK');
  }finally{await context.close()}
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
