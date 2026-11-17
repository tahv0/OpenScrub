const {chromium}=require('/tmp/openscrub-save-as-20261116/node_modules/playwright');
const assert=require('node:assert/strict'),fs=require('fs');
const root='/tmp/openscrub-task71/fix1',url='http://127.0.0.1:18487';
(async()=>{const browser=await chromium.launch({headless:true});const page=await browser.newPage({viewport:{width:1365,height:1000}});
const errors=[],warnings=[],results=[];page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(['error','warning'].includes(m.type()))warnings.push(m.text())});
let version='old',sent=[],renders=0,resume=null,failure='423';
const old=[{t0:0,t1:0.3,mode:'mute'}],fresh=[{t0:0.5,t1:0.6,mode:'mute'}];
await page.route('**/api/jobs/alpha/report',route=>route.fulfill({json:{detections:[],audio_redactions:version==='old'?old:fresh}}));
await page.route('**/api/jobs/alpha/detections',async route=>{if(route.request().method()!=='POST')return route.continue();sent.push(route.request().postDataJSON());
 if(failure==='defer')await new Promise(r=>resume=r);
 if(failure==='network')return route.abort('failed');
 await route.fulfill({status:failure==='ok'?200:423,json:failure==='ok'?{ok:true}:{error:'synthetic busy'}});
});
await page.route('**/api/jobs/*/render',async route=>{renders++;await route.fulfill({json:{ok:true}})});
async function editor(){await page.getByRole('button',{name:/Preview video & edit boxes/}).click();await page.waitForFunction(()=>BE.audioLoaded);}
async function setup(kind){version='old';sent=[];failure='423';resume=null;await page.goto(url);await page.getByRole('link',{name:'synthetic-alpha.mp4',exact:true}).click();await editor();
 await page.evaluate(kind=>{if(kind==='enabled')applyDet(0,false);if(kind==='manual')MAN.push({t_start:0,t_end:1,screen_box:[10,10,40,40]});if(kind==='box')BE.ov[0]=[10,10,40,40];if(kind==='time')BE.times[0]=[0.2,1];if(kind==='editor_manual')BE.adds.push({t0:0,t1:1,tref:0,box:[10,10,40,40]});},kind);
}
async function revisit(){await page.getByRole('link',{name:'synthetic-beta.mp4',exact:true}).click();await page.getByRole('link',{name:'synthetic-alpha.mp4',exact:true}).click();await editor();}
async function addAudio(){await page.locator('#beMute').click();const r=await page.locator('#beTL').boundingBox();await page.mouse.move(r.x+r.width*.7,r.y+60);await page.mouse.down();await page.mouse.move(r.x+r.width*.8,r.y+60);await page.mouse.up();}
async function save(){await page.getByRole('button',{name:'Save changes & re-render',exact:true}).click();await page.getByRole('status').filter({hasText:'Save was not confirmed'}).waitFor();}
for(const kind of ['enabled','manual','box','time','editor_manual']){
 await setup(kind);version='fresh';await revisit();assert.deepEqual(await page.evaluate(()=>BE.audio),fresh);await addAudio();const expected=await page.evaluate(()=>BE.audio);await save();assert.deepEqual(sent[0].audio,expected);assert.deepEqual(sent[0].audio[0],fresh[0]);assert.equal(sent[0].audio.length,2);assert.equal(renders,0);
 if(kind==='enabled')await page.screenshot({path:root+'/fresh-audio-revisit.png',fullPage:true});results.push({case:'fresh audio with pending '+kind,payload:sent[0],passed:true});
}
for(const change of ['add','remove','modify']){
 await setup('enabled');if(change==='add')await addAudio();else await page.evaluate(change=>{if(change==='remove')BE.audio=[];else BE.audio[0].mode='bleep';},change);
 const expected=await page.evaluate(()=>BE.audio);version='fresh';await revisit();assert.deepEqual(await page.evaluate(()=>BE.audio),expected);await save();assert.deepEqual(sent[0].audio,expected);assert.equal(renders,0);results.push({case:'dirty audio '+change+' survives revisit',passed:true});
}
// In-flight non-audio work does not pin clean audio.
await setup('enabled');failure='defer';await page.getByRole('button',{name:'Save changes & re-render',exact:true}).click();await page.waitForFunction(()=>EDITS.busy);while(!resume)await page.waitForTimeout(10);assert.equal('audio' in sent[0],false);version='fresh';await revisit();assert.deepEqual(await page.evaluate(()=>BE.audio),fresh);failure='ok';resume();await page.waitForFunction(()=>!EDITS.busy);assert.equal(renders,0);results.push({case:'in-flight non-audio save refreshes clean audio',passed:true});
// Audio toggle-back is retained across success/rejection/lost acknowledgement.
for(const outcome of ['ok','423','network']){
 await setup('enabled');await addAudio();failure='defer';await page.getByRole('button',{name:'Save changes & re-render',exact:true}).click();await page.waitForFunction(()=>EDITS.busy);while(!resume)await page.waitForTimeout(10);
 await page.evaluate(old=>BE.audio=old,old);version='fresh';await revisit();assert.deepEqual(await page.evaluate(()=>BE.audio),old);failure=outcome;resume();await page.waitForFunction(()=>!EDITS.busy);assert.deepEqual(await page.evaluate(()=>BE.audio),old);failure='423';await save();assert.deepEqual(sent[1].audio,old);assert.equal(renders,0);results.push({case:'audio toggle-back retry after '+outcome,passed:true});
}
const identity={url:page.url(),title:await page.title(),nonblank:(await page.locator('body').innerText()).includes('OpenScrub'),overlays:await page.locator('vite-error-overlay,nextjs-portal').count()};
assert.deepEqual(errors,[]);assert.equal(identity.overlays,0);await page.screenshot({path:root+'/audio-toggleback-retry.png',fullPage:true});fs.writeFileSync(root+'/browser-results.json',JSON.stringify({identity,environment:'Browser plugin unavailable; isolated Playwright Chromium Linux1365x1000',results,errors,warnings},null,2));console.log(JSON.stringify({passed:results.length,identity,errors,warnings},null,2));await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
