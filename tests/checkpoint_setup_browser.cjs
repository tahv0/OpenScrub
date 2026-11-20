const {chromium}=require(process.env.OPENSCRUB_PLAYWRIGHT_MODULE);
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const [url,root]=process.argv.slice(2);
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.OPENSCRUB_CHROMIUM,args:['--no-sandbox']});
 try{
  const page=await browser.newPage({viewport:{width:1100,height:900}}),errors=[],dialogs=[];
  page.setDefaultTimeout(12000);page.on('pageerror',e=>errors.push(e.message));
  page.on('dialog',d=>{dialogs.push(d.message());d.accept().catch(()=>{});});
  await page.goto(url);assert.equal(await page.title(),'OpenScrub');
  await page.locator('#file').setInputFiles(path.join(root,'runtime','source.mp4'));
  await page.waitForFunction(()=>S.dur>0&&S.wins.length>0);
  await page.locator('details summary').filter({hasText:'Advanced settings'}).click();
  assert.equal(await page.locator('#checkpointreview').isChecked(),false);
  await page.locator('#cats .catrow').filter({has:page.locator('.nm',{hasText:'QR / barcode'})})
   .locator('input[type=checkbox]').check();
  async function submit(){
   const result=page.waitForResponse(r=>r.url().endsWith('/api/jobs')&&r.request().method()==='POST');
   await page.locator('button.start').click();const response=await result;assert.equal(response.status(),200);
   const id=(await response.json()).jobs[0];
   return {id,options:JSON.parse(fs.readFileSync(path.join(root,'runtime','openscrub_jobs',id,'options.json')))};
  }
  await page.locator('#checkpointreview').check();
  // Incompatible category choices are refused before any job is posted.
  await page.locator('#cats .catrow').filter({has:page.locator('.nm',{hasText:'face'})})
   .first().locator('input[type=checkbox]').check();
  const warning=page.waitForEvent('dialog');await page.locator('button.start').click();await warning;
  assert(dialogs.some(d=>/QR|checkpoint/i.test(d)));
  await page.locator('#cats .catrow').filter({has:page.locator('.nm',{hasText:'face'})})
   .first().locator('input[type=checkbox]').uncheck();
  await page.locator('#checkpointreview').uncheck();
  const ordinary=await submit();
  assert(!Object.hasOwn(ordinary.options,'checkpoint_review'));
  assert(Array.isArray(ordinary.options.windows));
  await page.locator('#checkpointreview').check();
  const opted=await submit();
  assert.equal(opted.options.checkpoint_review,true);
  assert.equal(opted.options.categories,'qrcode');
  assert(!Object.hasOwn(opted.options,'windows'));
  const framePath=path.join(root,'runtime','checkpoint-frames');
  for(let i=0;i<100;i++){
   if(fs.existsSync(framePath)&&+fs.readFileSync(framePath,'utf8')>=2)break;
   await page.waitForTimeout(100);
  }
  await page.getByRole('button',{name:'Stop & Review',exact:true}).click();
  await page.waitForFunction(()=>document.getElementById('ph')?.textContent==='paused');
  const status=await (await page.request.get(url+'/api/jobs/'+opted.id)).json();
  const report=await (await page.request.get(url+'/api/jobs/'+opted.id+'/report')).json();
  assert.equal(status.phase,'paused');assert(status.checkpoint_unfinished);
  assert(report.stop_review.next_frame>0&&report.stop_review.next_frame<20);
  assert.deepEqual(errors,[]);
  console.log('CHECKPOINT_SETUP_STOP_OK');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
