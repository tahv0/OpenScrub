const {chromium}=require('/tmp/openscrub-save-as-20261116/node_modules/playwright');
const fs=require('fs'),assert=require('assert/strict');const ROOT='/tmp/openscrub-task20',origin='http://127.0.0.1:18520';
(async()=>{const browser=await chromium.launch({headless:true});const errors=[];
async function open(){const p=await browser.newPage({viewport:{width:1365,height:1000}});p.on('pageerror',e=>errors.push(e.message));await p.goto(origin);assert.equal(await p.title(),'OpenScrub');await p.locator('#jobs a').first().click();await p.locator('#bb1').waitFor();return p;}
fs.copyFileSync(ROOT+'/initial-report.json',fs.readFileSync(ROOT+'/report-path.txt','utf8'));
let p=await open();assert.equal(await p.locator('#ds1').innerText(),'Mixed — 2 will be blurred; 1 will stay visible');
await p.locator('#kb1').click();await p.locator('#kb1').click();await p.locator('#bb4').click();await p.locator('#bb4').click();await p.locator('#review details summary').click();await p.locator('#bb8').click();
await p.route('**/api/jobs/qa/render',r=>r.fulfill({status:409,contentType:'application/json',body:JSON.stringify({ok:false,error:'QA gate: reopen before render'})}));
await p.getByRole('button',{name:'Save edits & render',exact:true}).click();await p.waitForFunction(()=>!EDITS.busy);
const reportPath=fs.readFileSync(ROOT+'/report-path.txt','utf8');const before=JSON.parse(fs.readFileSync(ROOT+'/initial-report.json'));const saved=JSON.parse(fs.readFileSync(reportPath));
let expected=before.detections.map(x=>x.enabled);for(const i of [0,1,11])expected[i]=false;for(const i of [4,5,8])expected[i]=true;
assert.deepEqual(saved.detections.map(x=>x.enabled),expected);const strip=d=>{d=structuredClone(d);d.detections.forEach(x=>delete x.enabled);return d};assert.deepEqual(strip(saved),strip(before));
fs.writeFileSync(ROOT+'/saved-before-render.json',JSON.stringify(saved,null,2));await p.close();
p=await open();assert.equal(await p.locator('#ds1').innerText(),'Will stay visible');assert.equal(await p.locator('#ds4').innerText(),'Will be blurred');assert.equal(await p.locator('#ds8').textContent(),'Will be blurred');
assert.deepEqual(await p.evaluate(()=>Object.values(EN)),expected);await p.screenshot({path:ROOT+'/real-reopened.png'});
await p.getByRole('button',{name:'Save edits & render',exact:true}).click();
let job;for(let i=0;i<100;i++){job=await (await p.request.get(origin+'/api/jobs/qa')).json();if(['done','error'].includes(job.phase))break;await p.waitForTimeout(200);}
assert.equal(job.phase,'done',JSON.stringify(job));fs.writeFileSync(ROOT+'/real-result.json',JSON.stringify({beforeRenderFreshReopen:true,nonOutputFieldsUnchanged:true,expected,job,errors},null,2));assert.deepEqual(errors,[]);await browser.close();console.log('real UI save → fresh reopen before render → actual render passed');})().catch(e=>{console.error(e);process.exit(1)});
