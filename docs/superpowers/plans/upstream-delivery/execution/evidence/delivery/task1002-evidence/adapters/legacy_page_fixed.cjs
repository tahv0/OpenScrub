const fs=require('fs');
const assert=require('assert');
const {chromium}=require(process.env.OPENSCRUB_PLAYWRIGHT_MODULE);
const [base,jid,out]=process.argv.slice(2);
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.OPENSCRUB_CHROMIUM,headless:true});
 try{
  const context=await browser.newContext({viewport:{width:1280,height:900}});
  await context.route('**/*',route=>new URL(route.request().url()).origin===base?route.continue():route.abort());
  const page=await context.newPage(),errors=[],warnings=[],responses=[];
  page.on('pageerror',e=>errors.push(e.stack||String(e)));
  page.on('console',m=>{if(m.type()==='error')errors.push(m.text());if(m.type()==='warning')warnings.push(m.text());});
  page.on('response',async r=>{
   if(r.url().endsWith('/track_status'))responses.push(await r.json());
  });
  await page.goto(base,{waitUntil:'domcontentloaded'});
  assert((await page.title()).includes('OpenScrub'));
  assert((await page.locator('body').innerText()).includes('OpenScrub'));
  assert.strictEqual(await page.locator('vite-error-overlay,nextjs-portal').count(),0);
  await page.evaluate(id=>openJob(id),jid);
  await page.waitForSelector('#review');
  await page.evaluate(()=>loadBoxEdit(true));
  await page.waitForFunction(()=>document.querySelector('#beImg')?.complete&&BE.scale>0);
  assert(await page.locator('#beTrk').isEnabled());
  await page.evaluate(()=>{const slider=document.querySelector('#beT');slider.value='1.9';slider.dispatchEvent(new Event('input',{bubbles:true}));});
  await page.waitForFunction(()=>BE.t===1.9&&document.querySelector('#beImg').complete);
  const draft=await page.evaluate(()=>{
   BE.ov={'0':[22,32,52,62]};BE.dis={'1':true};BE.times={'0':[.2,1.8]};
   BE.adds=[{manual_id:'pending:legacy',box:[70,30,90,60],t0:0,t1:2,tref:.2}];
   BE.audio=[{t0:.1,t1:.4,mode:'mute'}];beDraw();
   return JSON.stringify({ov:BE.ov,dis:BE.dis,times:BE.times,adds:BE.adds,audio:BE.audio});
  });
  await page.locator('#beTrk').click();
  await page.locator('#beCv').scrollIntoViewIfNeeded();
  const position=await page.evaluate(()=>{const r=document.querySelector('#beCv').getBoundingClientRect();return{x:r.x,y:r.y,scale:BE.scale};});
  await page.screenshot({path:out+'/legacy-before.png'});
  await page.mouse.click(position.x+12*position.scale,position.y+12*position.scale);
  await page.mouse.click(position.x+44*position.scale,position.y+44*position.scale);
  await page.waitForFunction(()=>document.querySelector('#beTrkSt')?.textContent.includes('deterministic legacy tracking failure'),null,{timeout:12000});
  const retained=await page.evaluate(()=>JSON.stringify({ov:BE.ov,dis:BE.dis,times:BE.times,adds:BE.adds,audio:BE.audio}));
  assert.strictEqual(retained,draft);
  assert(responses.some(r=>r.state==='running'));
  assert(responses.some(r=>r.state==='done'&&r.added===0));
  assert.deepStrictEqual(errors,[]);
  assert.deepStrictEqual(warnings,[]);
  await page.screenshot({path:out+'/legacy-failure.png'});
  const evidence={url:page.url(),title:await page.title(),viewport:{width:1280,height:900},
   meaningfulBody:true,frameworkOverlay:false,errors,warnings,responses,draftsRetained:true,
   failureText:await page.locator('#beTrkSt').innerText()};
  fs.writeFileSync(out+'/legacy-dom.json',JSON.stringify(evidence,null,2)+'\n');
  console.log(JSON.stringify(evidence));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
