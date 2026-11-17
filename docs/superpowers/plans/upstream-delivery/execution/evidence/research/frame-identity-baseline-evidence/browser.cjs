const {chromium}=require('/tmp/openscrub-save-as-20261116/node_modules/playwright');
const fs=require('node:fs'),assert=require('node:assert/strict');
const evid='/home/tahv0/src/OpenScrub/.superpowers/sdd/README/frame-identity-baseline-evidence';
(async()=>{let browser;const results={environment:{browserPlugin:'Browser plugin not available; task permits existing isolated Playwright fallback',playwright:require('/tmp/openscrub-save-as-20261116/node_modules/playwright/package.json').version,node:process.version,viewport:{width:1100,height:900}},states:[]};
try{
 browser=await chromium.launch({headless:true,executablePath:'/tmp/openscrub-save-as-20261116/browsers/chromium-1255/chrome-linux64/chrome'});results.environment.browser=browser.version();
 const ctx=await browser.newContext({viewport:results.environment.viewport});
 await ctx.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
 const page=await ctx.newPage(),errors=[],warnings=[],requests=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(['warning','error'].includes(m.type()))warnings.push(m.text())});page.on('request',r=>requests.push({method:r.method(),url:r.url()}));
 for(const [label,time] of [['cfr24',.2],['cfr5',1.9],['normalized',.5]]){
  await page.goto('http://127.0.0.1:18571');
  await page.getByRole('link',{name:'synthetic-'+label+'.mp4',exact:true}).click();
  await page.getByRole('button',{name:/Preview video & edit boxes/}).click();
  await page.waitForFunction(()=>document.getElementById('beImg')?.naturalWidth===320&&BE.boxes.length===1);
  await page.locator('#beT').fill(String(time));await page.locator('#beT').dispatchEvent('input');
  await page.waitForFunction(t=>BE.t===t&&document.getElementById('beImg').complete&&document.getElementById('beImg').naturalWidth===320&&BE.ox===BE.boxes[0].box[0]-50,time);
  // Decode the exact rendered image pixels in a separate inspection canvas.
  const state=await page.evaluate(()=>{const img=document.getElementById('beImg'),cv=document.createElement('canvas');cv.width=img.naturalWidth;cv.height=img.naturalHeight;const x=cv.getContext('2d');x.drawImage(img,0,0);let marker=0;for(let k=0;k<6;k++)if(x.getImageData(14+12*k,14,1,1).data[0]>128)marker|=1<<k;return{url:location.href,title:document.title,nonblank:document.body.innerText.includes('OpenScrub'),overlays:document.querySelectorAll('vite-error-overlay,nextjs-portal').length,slider:{min:beT.min,max:beT.max,step:beT.step,value:beT.value},label:beL.textContent,BE:{t:BE.t,dur:BE.dur,ox:BE.ox,oy:BE.oy,boxes:BE.boxes,scale:BE.scale},image:{src:img.src,width:img.naturalWidth,height:img.naturalHeight,marker},pointerEvents:getComputedStyle(document.getElementById('beCv')).pointerEvents}});
  state.job=label;
  await page.screenshot({path:evid+'/'+label+'-editor.png',fullPage:true});
  // Actual pointer edit proves the shown sample remains editable with its
  // requested-time geometry. Keep drafts local and never press Save.
  await page.locator('#beCv').click({position:{x:(state.BE.boxes[0].box[0]+10)*state.BE.scale,y:90*state.BE.scale}});
  state.selected=await page.evaluate(()=>BE.sel);
  const box=await page.locator('#beCv').boundingBox();
  await page.mouse.move(box.x+(state.BE.boxes[0].box[0]+20)*state.BE.scale,box.y+90*state.BE.scale);await page.mouse.down();await page.mouse.move(box.x+(state.BE.boxes[0].box[0]+25)*state.BE.scale,box.y+90*state.BE.scale);await page.mouse.up();
  state.localDraft=await page.evaluate(()=>({ov:BE.ov,t:BE.t,ox:BE.ox}));
  assert.equal(state.selected,0);assert.equal(state.pointerEvents,'auto');assert.equal(state.slider.value,String(time));assert.equal(state.overlays,0);assert(state.nonblank);assert(state.localDraft.ov['0']);
  results.states.push(state);
 }
 results.compare={entry:'source route/caller inspection only; review-phase synthetic job has no compare container or rendered output'};
 results.errors=errors;results.warnings=warnings;results.requests=requests;results.mutations=requests.filter(r=>r.method!=='GET');assert.equal(results.mutations.length,0);assert.equal(errors.length,0);
 fs.writeFileSync(evid+'/browser-results.json',JSON.stringify(results,null,2));console.log(JSON.stringify({states:results.states.map(s=>({job:s.job,t:s.BE.t,marker:s.image.marker,ox:s.BE.ox,slider:s.slider,selected:s.selected,draft:s.localDraft})),errors,mutations:results.mutations},null,2));
}finally{if(browser)await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
