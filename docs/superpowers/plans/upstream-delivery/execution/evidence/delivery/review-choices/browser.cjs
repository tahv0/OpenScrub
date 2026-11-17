const { chromium } = require('/tmp/openscrub-save-as-20261116/node_modules/playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ROOT='/tmp/openscrub-task20';
const origin='http://127.0.0.1:18507';
const row=(i,category,enabled,person=-1,track=-1,confidence=.5,zone_dropped=false)=>({
 i,category,enabled,person,track,confidence,zone_dropped,text:'synthetic '+i,
 t_start:i/10,t_end:2+i/10,box:[20+i*12,20,30+i*12,40]});
const initial=[row(0,'face',true,0,10,.4),row(1,'face',false,0,11,.9),
 row(2,'face',true,1,10,.8),row(3,'face',false,-1,10),
 row(4,'face',true,-1,20,.7),row(5,'face',false,-1,20,.2),
 row(6,'plate',true,-1,20,.8),row(7,'email',true),
 row(8,'face',false,0,11,.95,true),row(9,'face',false,-1,-1,.5,true),
 row(10,'face',true),row(11,'face',true,0,11,.3),row(12,'person',true,0,11)];
const copy=x=>JSON.parse(JSON.stringify(x));
fs.writeFileSync(ROOT+'/synthetic-report.json',JSON.stringify({detections:initial.map(({i,box,...d})=>({...d,cbox:box,aoff:[0,0],last_seen:d.t_start})),render_state:{fps:10,cum:Array.from({length:40},()=>[0,0])}},null,2)+'\n');
const results={environment:{browser:'Playwright Chromium, existing install',browserPlugin:'not available',
 viewport:'1365x1000',origin,application:'full unmodified emitted PAGE; synthetic HTTP intercepted by Playwright',
 inference:false,realPersistence:false,realRender:false},scenarios:[],errors:[],console:[],requests:[]};
const record=(name,data)=>{console.log(name);results.scenarios.push({name,...data});};
let browser;
(async()=>{
 browser=await chromium.launch({headless:true});
 async function setup(pin,options={}){
  const page=await browser.newPage({viewport:{width:1365,height:1000},...options});
  const state={rows:copy(initial),posts:[],renders:0,hold:false,release:null};
  page.on('pageerror',e=>results.errors.push(pin+': '+e.message));
  page.on('console',m=>{if(['error','warning'].includes(m.type()))results.console.push(pin+': '+m.text());});
  await page.route(origin+'/**',async route=>{
   const request=route.request(),url=new URL(request.url()),path=url.pathname;
   if(path==='/'+pin+'.html')return route.fulfill({contentType:'text/html',body:fs.readFileSync(ROOT+'/'+pin+'.html','utf8')});
   const json=data=>route.fulfill({contentType:'application/json',body:JSON.stringify(data)});
   if(path.startsWith('/api/'))results.requests.push({pin,method:request.method(),path});
   if(path==='/api/jobs')return json([{id:'qa',name:'Synthetic review choices',phase:'review'}]);
   if(path==='/api/jobs/qa')return json({id:'qa',name:'Synthetic review choices',phase:'review',progress:1,has_output:false});
   if(path==='/api/jobs/qa/log')return json({lines:[],len:0});
   if(path==='/api/jobs/qa/detections'){
    if(request.method()==='POST'){
     const payload=request.postDataJSON();state.posts.push(payload);
     if(state.hold)await new Promise(resolve=>state.release=resolve);
     for(const [i,enabled] of Object.entries(payload.enabled||{}))state.rows[Number(i)].enabled=enabled;
     return json({ok:true,suggest_allowlist:[]});
    }
    return json({detections:state.rows,fps:10,duration:4});
   }
   if(path==='/api/jobs/qa/render'){state.renders++;return json({ok:true});}
   if(path==='/api/jobs/qa/report')return json({detections:state.rows,audio_redactions:[],render_state:{fps:10,cum:Array(40).fill(0)}});
   if(path==='/api/jobs/qa/mediainfo')return json({duration:4,fps:10,width:320,height:180});
   if(path==='/api/jobs/qa/boxes_at')return json({ox:0,oy:0,boxes:state.rows.filter(x=>!x.zone_dropped).map(x=>({...x}))});
   if(/\/(thumb|detframe)\/\d+$|\/frame_at$/.test(path))return route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="320" height="180"><rect width="320" height="180" fill="#233447"/><path d="M40 30h90v100H40z" fill="#abc"/><text x="15" y="160" fill="white">Synthetic original preview</text></svg>'});
   if(path==='/api/custom_cats')return json([]);
   if(path==='/api/allowlist')return json({words:[],path:'synthetic-only'});
   if(path==='/api/certinfo')return json({mode:'synthetic',subject:'local fixture',expires:'n/a'});
   if(path==='/api/vault')return json({enabled:false});
   if(path==='/api/extras')return json({extras:[]});
   if(path==='/api/update_check')return json({current:'synthetic',update_available:false});
   if(path==='/api/quality_tier')return json({tier:'fast',needs:{}});
   if(path.startsWith('/api/models/'))return json({active:true,selected:'',status:'Synthetic fixture',models:[]});
   if(path==='/api/model_status')return json({face:true,plate:true,person:true});
   if(path==='/favicon.ico')return route.fulfill({status:204});
   throw Error('Unexpected HTTP '+request.method()+' '+path);
  });
  await page.goto(origin+'/'+pin+'.html');
  assert.equal(await page.title(),'OpenScrub');
  await page.locator('#jobs a').first().click();
  await page.locator('#bb1').waitFor();
  assert.match(await page.locator('body').innerText(),/Review/);
  return {page,state};
 }

 const {page,state}=await setup('current');
 const flags=()=>page.evaluate(()=>({...EN}));
 const status=async(i,text,b,k)=>{assert.equal(await page.locator('#ds'+i).innerText(),text);
  assert.equal(await page.locator('#bb'+i).getAttribute('aria-pressed'),String(b));
  assert.equal(await page.locator('#kb'+i).getAttribute('aria-pressed'),String(k));};
 await status(1,'Mixed — 2 will be blurred; 1 will stay visible',false,false);
 await status(4,'Mixed — 1 will be blurred; 1 will stay visible',false,false);
 await page.locator('#det1').scrollIntoViewIfNeeded();await page.screenshot({path:ROOT+'/mixed-desktop.png'});
 fs.writeFileSync(ROOT+'/mixed-accessibility.txt',await page.locator('#det1').ariaSnapshot());
 assert.equal(await page.locator('#det1').evaluate(e=>e.classList.contains('off')),false);
 assert.equal(await page.getByRole('group',{name:'face output, appearance 2, 3 appearances',exact:true}).count(),1);
 await page.locator('#bb1').click();await page.locator('#bb1').click();
 await status(1,'Will be blurred',true,false);assert.equal(await page.evaluate(()=>document.activeElement.id),'bb1');
 await page.locator('#kb1').click();await page.locator('#kb1').click();await status(1,'Will stay visible',false,true);
 record('pointer repeated setters and all-member state',{enabled:await flags()});
 await page.locator('button[onclick="setAll(\'face\',false)"]').focus();
 await page.keyboard.press('Tab');assert.equal(await page.evaluate(()=>document.activeElement.id),'bb1');
 await page.keyboard.press('Enter');await page.keyboard.press('Enter');await status(1,'Will be blurred',true,false);
 await page.keyboard.press('Tab');assert.equal(await page.evaluate(()=>document.activeElement.id),'kb1');
 await page.keyboard.press('Space');await page.keyboard.press('Space');await status(1,'Will stay visible',false,true);
 assert.equal(await page.evaluate(()=>document.activeElement.id),'kb1');
 assert.equal(await page.locator('#kb1').evaluate(e=>getComputedStyle(e).outlineStyle),'solid');
 record('Tab Enter Space keep focus and pressed state',{});
 // Existing category, marquee and editor entry points; no replacement handlers.
 await page.locator('button[onclick="setAll(\'face\',true)"]').click();
 await page.locator('button[onclick="setAll(\'face\',true)"]').click();


 let target=page.locator('#det4');await target.scrollIntoViewIfNeeded();
 let b=await target.boundingBox();await page.mouse.move(b.x+3,b.y+3);await page.mouse.down();
 await page.mouse.move(b.x+b.width-3,b.y+b.height-3,{steps:3});await page.mouse.up();
 assert.deepEqual(await page.evaluate(()=>[...selSet]),[4]);
 await page.locator('.selmenu .mkeep').click();
 await status(4,'Will stay visible',false,true);assert.deepEqual(await page.evaluate(()=>[...selSet]),[]);
 b=await target.boundingBox();await page.mouse.move(b.x+3,b.y+3);await page.mouse.down();
 await page.mouse.move(b.x+b.width-3,b.y+b.height-3,{steps:3});await page.mouse.up();
 await page.keyboard.press('Escape');assert.deepEqual(await page.evaluate(()=>[...selSet]),[]);
 record('category and real pointer marquee plus Escape',{});
 await page.locator('#review details summary').click();await page.locator('#bb8').click();
 let f=await flags();assert.equal(f[8],true);assert.equal(f[9],false);assert.equal(f[1],true);
 await page.locator('button[onclick="setAllZd(true)"]').click();
 await status(8,'Will be blurred',true,false);await status(9,'Will be blurred',true,false);
 assert(!((await page.locator('#review details summary').innerText()).includes('NOT blurred')));
 await page.locator('#det8 img').click();await page.locator('#lb img').waitFor();
 assert((await page.locator('#lb img').getAttribute('src')).endsWith('/detframe/8'));
 await page.keyboard.press('Escape');assert.equal(await page.locator('#lb').count(),0);
 record('independent zone controls truthful summary and enlarged preview',{});
 await page.locator('button[onclick="loadBoxEdit(1)"]').click();await page.locator('#beCv').waitFor();
 await page.waitForFunction(()=>BE.boxes?.length>0);
 let cv=await page.locator('#beCv').boundingBox();
 let pos=await page.evaluate(()=>{const q=BE.boxes.find(x=>x.i===0);return {x:(q.box[0]+q.box[2])/2,y:(q.box[1]+q.box[3])/2,w:document.getElementById('beImg').naturalWidth}});
 await page.mouse.click(cv.x+pos.x*cv.width/pos.w,cv.y+pos.y*cv.width/pos.w);
 await page.locator('#beRm').click();await status(1,'Mixed — 2 will be blurred; 1 will stay visible',false,false);
 f=await flags();assert.deepEqual([f[0],f[1],f[11]],[false,true,true]);assert.equal(await page.evaluate(()=>BE.sel),-1);
 record('actual editor nonrepresentative Remove blur stays row-local',{});
 // Close/reopen editor selection at representative row 1, retaining existing fan-out.
 await page.locator('#beCv').scrollIntoViewIfNeeded();cv=await page.locator('#beCv').boundingBox();
 pos=await page.evaluate(()=>{const q=BE.boxes.find(x=>x.i===1);return {x:(q.box[0]+q.box[2])/2,y:(q.box[1]+q.box[3])/2,w:document.getElementById('beImg').naturalWidth}});
 await page.mouse.click(cv.x+pos.x*cv.width/pos.w,cv.y+pos.y*cv.width/pos.w);
 await page.locator('#beRm').click();await status(1,'Will stay visible',false,true);
 record('representative Remove blur retains group fan-out',{});
 await page.waitForTimeout(200);await page.screenshot({path:ROOT+'/desktop.png'});
 await page.setViewportSize({width:390,height:844});
 await page.locator('#bb1').scrollIntoViewIfNeeded();await page.locator('#bb1').click();
 for(const id of ['bb1','kb1']){b=await page.locator('#'+id).boundingBox();assert(b.x>=0&&b.x+b.width<=390);}
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 await page.waitForTimeout(200);await page.screenshot({path:ROOT+'/mobile.png'});
 await page.getByText('Advanced settings ▸',{exact:true}).click();
 const cover=page.locator('label:has(#faceheads)');
 const checkbox=cover.locator('input');const checked=await checkbox.isChecked();await cover.locator('.qm').click();
 assert.equal(await checkbox.isChecked(),checked);assert(await cover.locator('.qm').evaluate(e=>e.classList.contains('open')));
 const q=await cover.locator('.qm').evaluate(e=>({w:e.style.getPropertyValue('--qw'),x:e.style.getPropertyValue('--qx')}));assert(q.w);
 await page.screenshot({path:ROOT+'/mobile-help.png'});record('390px responsive controls and mobile help tap guard',{q});
 const mobile=await setup('current',{viewport:{width:390,height:844},hasTouch:true,isMobile:true});
 await mobile.page.locator('#bb1').scrollIntoViewIfNeeded();await mobile.page.locator('#bb1').tap();
 assert.equal(await mobile.page.locator('#bb1').getAttribute('aria-pressed'),'true');
 const oldScroll=await mobile.page.evaluate(()=>scrollY);const cdp=await mobile.page.context().newCDPSession(mobile.page);
 await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:180,y:450}]});
 for(let y=420;y>=180;y-=30){await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:180,y}]});await mobile.page.waitForTimeout(20);}
 await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
 await mobile.page.waitForTimeout(300);const newScroll=await mobile.page.evaluate(()=>scrollY);console.log({oldScroll,newScroll});assert(newScroll>oldScroll);
 assert.deepEqual(await mobile.page.evaluate(()=>[...selSet]),[]);
 record('native touch action and scrolling without marquee',{oldScroll,newScroll});await mobile.page.close();
 assert.deepEqual(results.errors,[]);assert.deepEqual(results.console,[]);
 fs.writeFileSync(ROOT+'/browser-results.json',JSON.stringify(results,null,2));
 console.log(JSON.stringify({scenarios:results.scenarios.length,errors:results.errors,console:results.console}));
 await browser.close();
})().catch(async e=>{console.error(e);if(browser)await browser.close();process.exit(1)});
