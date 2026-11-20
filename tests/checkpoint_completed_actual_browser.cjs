const {chromium}=require(process.env.OPENSCRUB_PLAYWRIGHT_MODULE);
const assert=require('node:assert/strict');const [url]=process.argv.slice(2);
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.OPENSCRUB_CHROMIUM,args:['--no-sandbox']});
 try{
  const page=await browser.newPage({viewport:{width:1100,height:900}}),errors=[],saves=[],acks=[];
  page.setDefaultTimeout(15000);page.on('pageerror',e=>errors.push(e.message));
  page.on('console',m=>{if(m.type()==='error'&&!m.text().includes('409'))errors.push(m.text())});
  page.on('request',r=>{if(r.method()==='POST'&&r.url().endsWith('/completed/detections'))saves.push(r.postDataJSON());});
  page.on('response',r=>{if(r.request().method()==='POST'&&r.url().endsWith('/completed/detections'))acks.push(r.json());});
  await page.route('**/api/jobs/completed/render',route=>route.fulfill({status:409,json:{error:'test_render_refusal'}}));
  await page.goto(url);await page.getByRole('link',{name:'completed-checkpoint.mp4',exact:true}).click();
  await page.getByRole('button',{name:/Preview video & edit boxes/}).click();
  await page.waitForFunction(()=>beReady()&&BE.boxes.length>0);await page.evaluate(()=>stopPolling());
  const row=await page.evaluate(()=>BE.raw.find(r=>r.i===BE.boxes[0].i));
  assert(Array.isArray(row.scan_frame_bounds));assert(row.scan_frame_bounds[0]===0&&row.scan_frame_bounds[1]>0);
  await page.locator('#beCv').scrollIntoViewIfNeeded();
  const point=await page.locator('#beCv').evaluate((cv,b)=>{const r=cv.getBoundingClientRect(),im=document.getElementById('beImg');return {x:r.x+(b[0]+b[2])/2*r.width/im.naturalWidth,y:r.y+(b[1]+b[3])/2*r.height/im.naturalHeight}},row.box);
  await page.mouse.click(point.x,point.y);assert.equal(await page.evaluate(()=>BE.sel),row.i);
  await page.locator('#beT0').fill(String(row.t_start));await page.locator('#beT1').fill('2');
  await page.getByRole('button',{name:'Apply times'}).click();
  assert.deepEqual(await page.evaluate(i=>BE.geometry[i].precondition.scan_frame_bounds,row.i),row.scan_frame_bounds);
  await page.getByRole('button',{name:'Save changes & re-render'}).click();
  await page.waitForFunction(()=>!EDITS.busy&&EDITS.status.includes('render was not confirmed'));
  assert.deepEqual(saves[0].geometry_preconditions[row.i].scan_frame_bounds,row.scan_frame_bounds);
  const ack=(await acks[0]).geometry_rows[row.i];assert.equal(ack.scan_frame_bounds,null);
  assert.notEqual(ack.row_context_eq,row.row_context_eq);
  await page.waitForFunction(i=>beReady()&&BE_VIEW.readySample.rows.find(r=>r.i===i)?.scan_frame_bounds===null,row.i);
  const report=await(await page.request.get(url+'/api/jobs/completed/report')).json();
  assert.equal(report.detections[row.i].t_end,2);
  assert(!('scan_frame_start' in report.detections[row.i])&&!('scan_frame_end' in report.detections[row.i]));
  assert.deepEqual(errors,[],JSON.stringify(errors));console.log('CHECKPOINT_COMPLETED_ACTUAL_PAGE_OK');await page.close();
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
