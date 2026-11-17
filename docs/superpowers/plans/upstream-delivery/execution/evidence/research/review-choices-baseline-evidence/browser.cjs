const { chromium } = require('/tmp/openscrub-save-as-20261116/node_modules/playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ROOT='/tmp/openscrub-review-choices-20261117';
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
const record=(name,data)=>results.scenarios.push({name,...data});
let browser;
(async()=>{
 browser=await chromium.launch({headless:true});
 async function setup(pin){
  const page=await browser.newPage({viewport:{width:1365,height:1000}});
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
 const {page,state}=await setup('austin');
 const snapshot=()=>page.evaluate(()=>({enabled:{...EN},members:TRKMEM,
  cards:[...document.querySelectorAll('#detwrap .det')].map(e=>({id:e.id,category:e.dataset.cat,
   text:e.querySelector('.blurbtn')?.textContent,pressed:e.querySelector('.blurbtn')?.getAttribute('aria-pressed'),off:e.classList.contains('off')}))}));
 let before=await snapshot();
 assert.deepEqual(before.members['1'],[0,1,11]);
 assert.deepEqual(before.members['2'],[2]);
 assert.deepEqual(before.members['3'],[3]);
 assert.deepEqual(before.members['4'],[4,5]);
 assert.deepEqual(before.members['6'],[6]);
 assert.deepEqual(before.members['12'],[12]);
 assert.equal(before.cards.find(x=>x.id==='det1').text,'Keep');
 assert.equal(before.cards.find(x=>x.id==='det4').text,'Blur');
 record('mixed/person-track/category construction',{before});
 await page.locator('#det1').scrollIntoViewIfNeeded();
 await page.screenshot({path:ROOT+'/baseline-mixed.png'});
 await page.locator('#bb1').click();
 let once=await snapshot();assert.deepEqual([0,1,11].map(i=>once.enabled[i]),[true,true,true]);
 await page.locator('#bb1').click();
 let twice=await snapshot();assert.deepEqual([0,1,11].map(i=>twice.enabled[i]),[false,false,false]);
 for(const i of [2,3,4,5,6,7,8,9,10,12])assert.equal(twice.enabled[i],before.enabled[i]);
 record('repeated click toggles and isolates group',{once,twice});
 await page.locator('button[onclick="setAll(\'face\',false)"]').focus();
 await page.keyboard.press('Tab');assert.equal(await page.evaluate(()=>document.activeElement.id),'bb1');
 record('Tab reaches first card action after category controls',{focused:'bb1'});
 await page.locator('#bb4').focus();
 await page.keyboard.press('Enter');
 let enter=await snapshot();assert.equal(enter.enabled[4],false);assert.equal(enter.enabled[5],false);
 await page.keyboard.press('Space');
 let space=await snapshot();assert.equal(space.enabled[4],true);assert.equal(space.enabled[5],true);
 record('native keyboard Enter and Space toggle',{focus:await page.evaluate(()=>document.activeElement.id),enter,space});
 await page.locator('button[onclick="setAll(\'face\',false)"]').click();
 let category=await snapshot();
 for(const i of [0,1,2,3,4,5,10,11])assert.equal(category.enabled[i],false);
 for(const i of [6,7,8,9,12])assert.equal(category.enabled[i],before.enabled[i]);
 await page.locator('button[onclick="setAll(\'face\',false)"]').click();
 assert.deepEqual((await snapshot()).enabled,category.enabled);
 record('category explicit setter is idempotent, excludes zones and other categories',{category});
 // Real desktop marquee: intersect just the chosen card; invoke emitted menu.
 const target=page.locator('#det4');await target.scrollIntoViewIfNeeded();
 let box=await target.boundingBox();
 await page.mouse.move(box.x+3,box.y+3);await page.mouse.down();
 await page.mouse.move(box.x+box.width-3,box.y+box.height-3,{steps:5});await page.mouse.up();
 assert.deepEqual(await page.evaluate(()=>[...selSet]),[4]);
 await page.locator('.selmenu .mblur').click();
 const bulk=await snapshot();
 assert.equal(bulk.enabled[4],true);assert.equal(bulk.enabled[5],true);
 for(const i of [0,1,2,3,6,7,8,9,10,11,12])assert.equal(bulk.enabled[i],category.enabled[i]);
 assert.equal(await page.locator('.selmenu').count(),0);
 record('desktop marquee bulk explicit choice',{selected:[4],bulk});
 // Escape clears the ordinary menu/selection; no custom output shortcuts.
 box=await target.boundingBox();await page.mouse.move(box.x+3,box.y+3);await page.mouse.down();
 await page.mouse.move(box.x+box.width-3,box.y+box.height-3,{steps:3});await page.mouse.up();
 await page.keyboard.press('Escape');assert.deepEqual(await page.evaluate(()=>[...selSet]),[]);
 record('Escape clears marquee selection',{selection:await page.evaluate(()=>[...selSet])});
 await page.locator('#review details summary').click();
 await page.locator('#bb8').click();
 let zone=await snapshot();assert.equal(zone.enabled[8],true);assert.equal(zone.enabled[1],false);assert.equal(zone.enabled[9],false);
 await page.locator('button[onclick="setAllZd(true)"]').click();
 zone=await snapshot();assert.equal(zone.enabled[8],true);assert.equal(zone.enabled[9],true);
 assert.equal(zone.enabled[1],false);
 const summary=await page.locator('#review details summary').innerText();assert.match(summary,/NOT blurred/);
 record('zone rows stay independent; summary is static even after enabling',{zone,summary});
 await page.locator('#det8 img').click();await page.locator('#lb img').waitFor();
 const zoom=await page.locator('#lb img').getAttribute('src');assert.match(zoom,/detframe\/8$/);
 await page.keyboard.press('Escape');assert.equal(await page.locator('#lb').count(),0);
 record('enlarged original preview and Escape',{zoom});
 // Restore fetched baseline; use actual emitted editor and ordinary Remove blur.
 await page.evaluate(()=>loadReview());
 await page.getByRole('button',{name:/Preview video & edit boxes/}).click();
 await page.waitForFunction(()=>BE.boxes.length>0&&BE.scale>0);
 await page.locator('#beCv').scrollIntoViewIfNeeded();
 let cv=await page.locator('#beCv').boundingBox();
 let scale=await page.evaluate(()=>BE.scale);
 await page.mouse.click(cv.x+25*scale,cv.y+30*scale);
 assert.equal(await page.evaluate(()=>BE.sel),0);
 await page.locator('#beRm').click();
 let editor=await snapshot();assert.equal(editor.enabled[0],false);assert.equal(editor.enabled[1],false);assert.equal(editor.enabled[11],true);
 assert.equal(await page.evaluate(()=>BE.sel),-1);
 record('editor non-representative Remove blur is row-local',{editor,remainingEditorRows:await page.evaluate(()=>BE.boxes.map(x=>x.i))});
 // Editor representative removal operates over existing card membership.
 await page.evaluate(()=>loadReview());
 await page.locator('button[onclick="setAll(\'face\',true)"]').click();
 await page.getByRole('button',{name:/Preview video & edit boxes/}).click();
 await page.waitForFunction(()=>BE.boxes.length>0&&BE.scale>0);
 await page.locator('#beCv').scrollIntoViewIfNeeded();cv=await page.locator('#beCv').boundingBox();scale=await page.evaluate(()=>BE.scale);
 await page.mouse.click(cv.x+37*scale,cv.y+30*scale);
 assert.equal(await page.evaluate(()=>BE.sel),1);
 await page.locator('#beRm').click();editor=await snapshot();
 assert.deepEqual([0,1,11].map(i=>editor.enabled[i]),[false,false,false]);
 record('editor representative Remove blur propagates to card group',{editor});
 // Controlled round trip: server persistence/render are fixture acknowledgements.
 await page.locator('button[onclick="setAll(\'face\',false)"]').click();
 await page.getByRole('button',{name:'Save edits & render',exact:true}).click();
 await page.waitForFunction(()=>!document.getElementById('review'));
 assert.equal(state.posts.length,1);assert.equal(state.renders,1);
 await page.evaluate(()=>loadReview());
 const reopened=await snapshot();for(const i of [0,1,2,3,4,5,10,11])assert.equal(reopened.enabled[i],false);
 record('controlled HTTP save and reopen; render acknowledged only',{post:state.posts[0],renders:state.renders,reopened});
 // Mobile help uses full existing page and its delegated tap handler.
 await page.setViewportSize({width:390,height:844});
 await page.getByText('Advanced settings ▸',{exact:true}).click();
 const tip=page.locator('label:has(#faceheads) .qm');await tip.scrollIntoViewIfNeeded();
 const checkedBefore=await tip.evaluate(e=>{const c=e.closest('label').querySelector('input[type=checkbox]');return c?c.checked:null;});
 await tip.click();
 const help=await tip.evaluate(e=>({open:e.classList.contains('open'),below:e.classList.contains('below'),
  width:e.style.getPropertyValue('--qw'),offset:e.style.getPropertyValue('--qx'),
  checked:e.closest('label').querySelector('input[type=checkbox]')?.checked??null}));
 assert.equal(help.open,true);assert.equal(help.checked,checkedBefore);assert.equal(help.width,'250px');
 record('mobile tooltip guard and placement',{checkedBefore,help});
 await page.screenshot({path:ROOT+'/baseline-mobile-help.png'});
 await page.close();
 // Existing draft pin only: preserve deliberate same-value intent and owner ACK.
 const draft=await setup('draft');const p=draft.page;
 const untouched=await p.evaluate(()=>({...EDITS.enabled}));assert.deepEqual(untouched,{});
 await p.evaluate(()=>applyDet(4,true));
 const sameValue=await p.evaluate(()=>({...EDITS.enabled}));assert.deepEqual(sameValue,{'4':true,'5':true});
 draft.state.hold=true;
 await p.getByRole('button',{name:'Save edits & render',exact:true}).click();
 while(!draft.state.release)await p.waitForTimeout(10);
 await p.locator('#bb4').click();
 const pending=await p.evaluate(()=>({...EDITS.enabled}));assert.deepEqual(pending,{'4':false,'5':false});
 draft.state.release();
 await p.waitForFunction(()=>!EDITS.busy);
 const afterAck=await p.evaluate(()=>({enabled:{...EDITS.enabled},status:EDITS.status}));
 assert.deepEqual(afterAck.enabled,pending);assert.equal(draft.state.renders,0);
 record('draft same-value explicit setter and newer opposite choice survives ACK',{untouched,sameValue,pending,afterAck,post:draft.state.posts[0],renders:draft.state.renders});
 assert.deepEqual(results.errors,[]);assert.deepEqual(results.console,[]);
 await p.close();
 fs.writeFileSync(ROOT+'/browser-results.json',JSON.stringify(results,null,2)+'\n');
 console.log(JSON.stringify({status:'passed',scenarios:results.scenarios.length,errors:results.errors,console:results.console}));
 await browser.close();
})().catch(async e=>{
 results.failure=e.stack;fs.writeFileSync(ROOT+'/browser-results.json',JSON.stringify(results,null,2)+'\n');
 console.error(e);if(browser)await browser.close();process.exit(1);
});
