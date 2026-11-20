const assert=require('node:assert/strict');
const fs=require('node:fs');
const {chromium}=require(process.env.OPENSCRUB_PLAYWRIGHT_MODULE);
const pageHTML=fs.readFileSync(process.env.OPENSCRUB_PAGE_HTML,'utf8');
const pixel=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+bHBsAAAAASUVORK5CYII=','base64');
const versions=['a','b','c'].map(x=>x.repeat(32));
const row=(i,extra={})=>({i,category:'face <b>& "literal"',text:'literal <strong>'+i+'</strong>',
 enabled:true,track:-1,person:-1,confidence:.5,zone_dropped:false,t_start:i/10,t_end:i/10+1,
 thumbnail_row:i.toString(16).padStart(64,'0'),...extra});
const rows=Array.from({length:120},(_,i)=>row(i,i<2?{track:7,confidence:i===0?.95:.5}:{}));

(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.OPENSCRUB_CHROMIUM,args:['--no-sandbox']});
 try{
  const page=await browser.newPage({viewport:{width:1280,height:1000}});
  const errors=[],images=[],metadata=[];
  page.on('pageerror',e=>errors.push(e.message));
  let generation=0,failMetadata=false,holdRecovery=null,holdInitial=false;
  await page.route('**/*',async route=>{
   const url=new URL(route.request().url()),path=url.pathname;
   if(path==='/')return route.fulfill({contentType:'text/html;charset=utf-8',body:pageHTML});
   if(path==='/api/jobs')return route.fulfill({json:[]});
   if(path==='/api/jobs/A')return route.fulfill({json:{id:'A',name:'Thumbnail review',phase:'queued',progress:1}});
   if(path==='/api/jobs/A/log')return route.fulfill({json:{from:0,len:0,lines:[]}});
   if(path==='/api/jobs/A/detections'){
    metadata.push(route.request().headers()['cache-control']||'');
    if(holdInitial){holdInitial=false;return route.fulfill({status:500,json:{error:'controlled initial error'}});}
    if(holdRecovery)await holdRecovery;
    if(failMetadata)return route.fulfill({status:500,json:{error:'controlled reopen error'}});
    const fresh=rows.map(x=>x.i===1&&generation>0?{...x,thumbnail_row:'f'.repeat(64)}:x);
    return route.fulfill({json:{duration:20,detections:fresh,thumbnail_version:versions[generation]}});
   }
   const image=path.match(/^\/api\/jobs\/A\/(thumb|detframe)\/(\d+)$/);
   if(image){
    const version=url.searchParams.get('v');
    images.push({kind:image[1],id:+image[2],version});
    if(version!==versions[generation])return route.fulfill({status:409,json:{error:'thumbnail_obsolete',refresh:'detections'}});
    return route.fulfill({contentType:'image/png',body:pixel});
   }
   return route.fulfill({json:{}});
  });
  await page.goto('http://openscrub.test/');
  assert.equal(await page.title(),'OpenScrub');
  await page.evaluate(()=>openJob('A'));
  await page.locator('#jobcard').waitFor();
  holdInitial=true;
  await page.evaluate(()=>loadReview());
  await page.locator('[data-review-retry]').waitFor({timeout:1500});
  await page.locator('[data-review-retry]').click();
  await page.locator('#review').waitFor();
  await page.evaluate(()=>scrollTo(0,document.getElementById('detwrap').getBoundingClientRect().top+scrollY-55));
  await page.waitForFunction(()=>document.querySelector('#det0 img')?.naturalWidth>0);
  assert(images.some(x=>x.id===0&&x.version===versions[0]));
  assert.match(await page.locator('#det0').innerText(),/literal <strong>0<\/strong>/);
  assert.equal(await page.locator('#det0 strong').count(),0);
  await page.evaluate(()=>{
   window.firstReview=document.getElementById('review');
   window.firstCard=document.getElementById('det0');
   window.firstButton=firstCard.querySelector('button');
   window.firstDraft=EDITS;
   window.firstEditor=BE;
   window.firstManual=MAN;
   MAN.push({manual_id:'held'});
   BE.audio=[{t0:0,t1:1,mode:'mute'}];
   applyDet(0,false);
   firstButton.focus();
   selSet.add(0);
  });
  generation=1;
  let release;
  holdRecovery=new Promise(resolve=>{release=resolve});
  const before=metadata.length;
  await page.evaluate(()=>{zoomDet(0);});
  await page.waitForFunction(()=>document.querySelector('#lb [data-thumb-status]')?.hidden===false);
  assert.equal(metadata.length,before+1);
  assert(images.some(x=>x.id===0&&x.kind==='detframe'&&x.version===versions[0]));
  release();holdRecovery=null;
  await page.waitForFunction(()=>document.querySelector('#det2 img')?.naturalWidth>0&&document.querySelector('#det0 [data-thumb-reopen]')?.hidden===false);
  assert(images.some(x=>x.id===2&&x.version===versions[1]));
  assert(!images.some(x=>x.id===0&&x.version===versions[1]));
  assert(await page.evaluate(()=>document.getElementById('review')===firstReview&&
   document.getElementById('det0')===firstCard&&document.activeElement===firstButton&&
   EDITS===firstDraft&&BE===firstEditor&&MAN===firstManual&&MAN[0].manual_id==='held'&&
   BE.audio[0].mode==='mute'&&EDITS.enabled[0]===false&&EDITS.enabled[1]===false&&selSet.has(0)));
  await page.evaluate(()=>document.getElementById('lb').click());
  await page.evaluate(()=>scrollTo(0,document.documentElement.scrollHeight));
  await page.waitForFunction(()=>!!document.getElementById('det119'));
  assert(await page.evaluate(()=>document.getElementById('det0')===firstCard));
  await page.waitForFunction(()=>document.querySelector('#det119 img')?.naturalWidth>0);
  assert(images.some(x=>x.id===119&&x.version===versions[1]));
  generation=2;
  await page.evaluate(()=>zoomDet(119));
  await page.waitForFunction(()=>document.querySelector('#lb [data-thumb-status]')?.hidden===false);
  assert.equal(metadata.length,before+1,'a later generation cannot replenish recovery');
  failMetadata=true;
  await page.locator('#lb [data-thumb-reopen]').click();
  await page.locator('[data-review-retry]').waitFor({state:'attached'});
  assert(await page.evaluate(()=>document.getElementById('review')===firstReview&&EDITS===firstDraft&&!!document.getElementById('lb')));
  failMetadata=false;
  await page.locator('#lb [data-thumb-reopen]').click();
  await page.waitForFunction(()=>document.getElementById('review')!==firstReview&&!!document.getElementById('review'));
  assert(await page.evaluate(()=>EDITS===firstDraft&&MAN===firstManual&&BE===firstEditor&&EDITS.enabled[0]===false));
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({metadata:metadata.length,images:images.length,errors,chromium:browser.version()}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
