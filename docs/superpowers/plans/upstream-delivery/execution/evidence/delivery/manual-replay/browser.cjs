const {chromium}=require('/tmp/openscrub-save-as-20261116/node_modules/playwright');
const assert=require('node:assert/strict'),fs=require('node:fs');
(async()=>{
 const browser=await chromium.launch({headless:true});
 const results=[],ids=JSON.parse(fs.readFileSync('/tmp/openscrub-task72/browser-jobs.json'));
 for(const mode of ['ack','lost']){
  const page=await browser.newPage({viewport:{width:1280,height:1000}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  page.on('dialog',d=>d.accept(d.message().includes('FROM')?'0':'4'));
  await page.addInitScript(()=>{
   window.qa={requests:[],held:[],commits:0,hold:true};const real=window.fetch.bind(window);
   window.fetch=async(url,options={})=>{
    if(String(url).endsWith('/detections')&&options.method==='POST'){
     qa.requests.push(JSON.parse(options.body));
     const result=await real(url,options);qa.commits++;
     if(qa.hold){await new Promise((resolve,reject)=>qa.held.push({resolve,reject}));}
     return result;
    }return real(url,options);
   };
  });
  await page.goto('http://127.0.0.1:18472');
  await page.evaluate(id=>openJob(id),ids[mode]);
  await page.waitForFunction(()=>!!document.getElementById('review'));
  await page.evaluate(()=>loadBoxEdit(1));
  await page.waitForFunction(()=>!!document.getElementById('beCv')&&BE.raw!==undefined);
  await page.waitForFunction(()=>document.getElementById('beCv').width===160&&document.getElementById('beCv').height===120);await page.locator('#beCv').scrollIntoViewIfNeeded();
  const point=async(x,y)=>page.evaluate(([x,y])=>{const r=document.getElementById('beCv').getBoundingClientRect();return {x:r.left+x*BE.scale,y:r.top+y*BE.scale}},[x,y]);
  const click=async(x,y)=>{const p=await point(x,y);await page.mouse.click(p.x,p.y)};
  const drag=async(x,y,a,b)=>{const p=await point(x,y),q=await point(a,b);await page.mouse.move(p.x,p.y);await page.mouse.down();await page.mouse.move(q.x,q.y,{steps:4});await page.mouse.up()};
  await page.evaluate(()=>beAddMode());await click(20,20);await click(60,60);await page.evaluate(()=>beAddMode());
  const creation=await page.evaluate(()=>copyEdit(BE.adds[0]));assert.match(creation.manual_id,/^[0-9a-f-]{36}$/);
  await page.evaluate(()=>{window.firstSave=saveAndRender()});await page.waitForFunction(()=>qa.commits===1);
  await page.evaluate(async()=>{document.getElementById('beT').value='1';await beScrub()});
  assert.equal(await page.evaluate(()=>BE.boxes.length),1);
  await click(40,40);await drag(40,40,50,50);await drag(70,70,80,90);
  await page.evaluate(()=>{document.getElementById('beT0').value='.5';document.getElementById('beT1').value='5';beApplyTimes();beRemove()});
  assert.deepEqual(await page.evaluate(()=>BE.ov[0]),[30,30,80,90]);
  assert.deepEqual(await page.evaluate(()=>BE.times[0]),[.5,5]);
  assert.equal(await page.evaluate(()=>EDITS.enabled[0]),false);
  assert.deepEqual(await page.evaluate(()=>BE.adds[0]),creation);
  if(mode==='ack')await page.evaluate(()=>qa.held.shift().resolve());
  else await page.evaluate(()=>qa.held.shift().reject(Error('injected browser response loss after commit')));
  await page.evaluate(()=>firstSave);
  assert.equal(await page.evaluate(()=>BE.adds.length),mode==='ack'?0:1);
  assert.deepEqual(await page.evaluate(()=>BE.ov[0]),[30,30,80,90]);
  // A distinct equal-geometry addition is completed through the actual producer.
  await page.evaluate(()=>beAddMode());await click(20,20);await click(60,60);await page.evaluate(()=>beAddMode());
  const second=await page.evaluate(()=>BE.adds.at(-1).manual_id);assert.notEqual(second,creation.manual_id);
  await page.evaluate(()=>{window.retry=saveAndRender()});await page.waitForFunction(()=>qa.commits===2);
  // Lose the retry's acknowledgement after its indexed patches really commit.
  await page.evaluate(()=>qa.held.shift().reject(Error('second injected response loss')));await page.evaluate(()=>retry);
  let doc=await page.evaluate(async()=>await (await fetch(`api/jobs/${CUR}/report`)).json());
  assert.equal(doc.detections.length,2);assert.deepEqual(doc.detections[0].cbox,[30,30,80,90]);assert.equal(doc.detections[0].enabled,false);
  assert.equal(doc.detections[0].t_start,.5);assert.equal(doc.detections[0].t_end,5);
  assert.deepEqual(doc.detections[0].manual_creation,{t_start:0,t_end:4,cbox:[20,20,60,60],aoff:[0,0]});
  // Revisit retains the original IDs. A subsequent committed retry must not
  // reset the edited row or append either pending creation again.
  await page.evaluate(([id,other])=>{openJob(other);openJob(id);window.finalSave=saveAndRender()},[ids[mode],ids[mode==='ack'?'lost':'ack']]);
  await page.waitForFunction(()=>qa.commits===3);
  await page.evaluate(()=>{applyDet(0,true);qa.held.shift().resolve()});await page.evaluate(()=>finalSave);
  assert.equal(await page.evaluate(()=>BE.adds.length),0);assert.equal(await page.evaluate(()=>EDITS.enabled[0]),true);
  const after=await page.evaluate(async()=>await (await fetch(`api/jobs/${CUR}/report`)).json());assert.deepEqual(after,doc);
  const requests=await page.evaluate(()=>qa.requests);assert.deepEqual(requests[1],requests[2]);
  assert.deepEqual(errors,[]);
  results.push({mode,creation,second,requests,current:doc.detections,errors});await page.close();
 }
 fs.writeFileSync('/tmp/openscrub-task72/browser-results.json',JSON.stringify(results,null,2));console.log('actual Chromium delayed ACK/lost ACK/retry loss/job revisit/newer distinct creation/newer choice: passed (2 schedules)');
 await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
