const {chromium}=require(process.env.OPENSCRUB_PLAYWRIGHT_MODULE);
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const [url,root]=process.argv.slice(2),fixture=JSON.parse(fs.readFileSync(path.join(root,'runtime/fixture.json')));
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.OPENSCRUB_CHROMIUM,args:['--no-sandbox']});
 try{
  for(const [label,width,height] of [['desktop',1365,1000],['mobile',390,844]]){
   const page=await browser.newPage({viewport:{width,height}}),errors=[],warnings=[];
   page.on('pageerror',e=>errors.push(e.message));
   page.on('console',m=>{if(['error','warning'].includes(m.type()))warnings.push(m.text())});
   page.on('dialog',d=>d.accept());
   await page.goto(url);assert.equal(await page.title(),'OpenScrub');
   assert((await page.locator('body').innerText()).includes('OpenScrub'));
   assert.equal(await page.locator('vite-error-overlay,nextjs-portal').count(),0);
   await page.locator('details summary').filter({hasText:'Advanced settings'}).click();
   assert.equal(await page.locator('#plate-policy').count(),1,'Scan Setup needs the optional plate policy control');
   const policy=page.locator('#plate-policy'),cutoff=page.locator('#plate-auto-cutoff');
   assert.equal(await policy.inputValue(),'');
   assert.equal(await cutoff.inputValue(),'');
   assert.equal(await cutoff.isVisible(),false);
   await page.locator('#spath').fill(fixture.video);await page.locator('#spath').press('Enter');
   await page.waitForFunction(()=>document.getElementById('editor').style.display==='block');
   const plate=page.locator('#cats .catrow').filter({has:page.locator('.nm',{hasText:'plate'})});
   await plate.locator('input[type=checkbox]').check();
   const captured=[];
   page.on('request',r=>{if(r.method()==='POST'&&r.url().endsWith('/api/jobs'))captured.push(r)});
   async function submit(){
    const response=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().endsWith('/api/jobs'));
    await page.locator('button.start').click();
    const r=await response;assert.equal(r.status(),200);
    const data=await r.json(),job=data.jobs[0];
    return JSON.parse(fs.readFileSync(path.join(fixture.jobs,job,'options.json')));
   }
   const standard=await submit();
   assert.equal(standard.plate_threshold,.35);
   assert(!Object.hasOwn(standard,'uncertain_policy'));
   assert(!Object.hasOwn(standard,'plate_auto_cutoff'));
   await policy.selectOption('manual_review');
   assert.equal(await cutoff.isVisible(),true);
   assert((await page.locator('#plate-policy-help').innerText()).includes('remain visible'));
   const count=captured.length;
   await page.locator('button.start').click();
   assert((await page.locator('#plate-policy-error').innerText()).includes('cutoff'));
   assert.equal(captured.length,count,'missing cutoff must not create a job');
   await cutoff.fill('.3');await page.locator('button.start').click();
   assert((await page.locator('#plate-policy-error').innerText()).includes('cutoff'));
   assert.equal(captured.length,count,'cutoff below the candidate floor must not create a job');
   await cutoff.fill('.8');
   const review=await submit();
   assert.equal(review.uncertain_policy,'manual_review');assert.equal(review.plate_auto_cutoff,.8);
   await policy.selectOption('blur_candidates');
   assert((await page.locator('#plate-policy-help').innerText()).includes('short'));
   const aggressive=await submit();
   assert.equal(aggressive.uncertain_policy,'blur_candidates');assert.equal(aggressive.plate_auto_cutoff,.8);
   await page.screenshot({path:path.join(root,'setup-'+label+'.png'),fullPage:true});
   assert.deepEqual(errors,[]);assert.deepEqual(warnings,[]);
   await page.close();
  }
  console.log('OPTIONAL_PLATE_SETUP_BROWSER_OK');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
