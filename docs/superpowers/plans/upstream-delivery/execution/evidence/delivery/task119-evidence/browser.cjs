process.env.TMPDIR='/tmp/openscrub-task119/tmp';
const {chromium}=require('/tmp/openscrub-save-as-20261116/node_modules/playwright');
const assert=require('node:assert/strict');const fs=require('node:fs');
const root='/tmp/openscrub-task119/evidence';
let ownedBrowser;
(async()=>{
const browser=ownedBrowser=await chromium.launch({headless:true});
const page=await browser.newPage({viewport:{width:1365,height:950},acceptDownloads:true});
const errors=[],warnings=[];page.on('pageerror',e=>errors.push(e.message));
page.on('console',m=>{if(['error','warning'].includes(m.type()))warnings.push(m.text());});
await page.goto('http://127.0.0.1:18489');assert.equal(await page.title(),'OpenScrub');
assert.ok((await page.locator('body').innerText()).includes('OpenScrub'));
const uploadName='Family &amp; friends — café.mp4';
const serverName='Friends\' "summer" & snow ☃ — &quot;.mp4';
const post1=await page.request.post('http://127.0.0.1:18489/api/jobs',{multipart:{video:{name:'folder/'+uploadName,mimeType:'video/mp4',buffer:Buffer.from('synthetic upload input')},options:'{}'}});
assert.equal(post1.status(),200);const first=(await post1.json()).jobs[0];
const post2=await page.request.post('http://127.0.0.1:18489/api/jobs',{form:{server_path:'/tmp/openscrub-task119/runtime/media/'+serverName,options:'{}'}});
assert.equal(post2.status(),200);const second=(await post2.json()).jobs[0];
const accepted=[];for(const [id,name] of [[first,uploadName],[second,serverName]]){
 const j=await(await page.request.get('http://127.0.0.1:18489/api/jobs/'+id)).json();assert.equal(j.name,name);accepted.push(j);
}
await page.evaluate(()=>loadJobs());
for(const name of [uploadName,serverName])assert.equal(await page.locator('#jobs').getByRole('link',{name,exact:true}).count(),1);
const title=()=>page.locator('#jobcard h2');
const titleName=()=>title().evaluate(el=>el.firstChild.textContent.trimEnd());
const structures=[];
for(const [id,name] of [[first,uploadName],[second,serverName],[first,uploadName]]){
 await page.locator('#jobs').getByRole('link',{name,exact:true}).click();
 await page.waitForFunction(expected=>document.querySelector('#jobcard h2')?.firstChild.textContent.trimEnd()===expected,name);
 assert.equal(await titleName(),name);assert.equal(await page.evaluate(()=>CUR),id);
 assert.equal(await page.locator('#jobcard').count(),1);assert.equal(await page.locator('#ph').innerText(),'done');
 const children=await title().evaluate(el=>[...el.children].map(x=>[x.tagName,x.id]));assert.deepEqual(children,[['SPAN','ph'],['SMALL','eta']]);
 assert.equal(await page.locator('#actions a').first().getAttribute('href'),'api/jobs/'+id+'/download');
 structures.push({id,name,children,heading:await title().ariaSnapshot(),list:await page.locator('#jobs').ariaSnapshot()});
}
const downloads=[];
for(const [button,name,expectedBytes] of [
 ['Download redacted video','Family &amp; friends — café_redacted.mkv','synthetic output for literal-name QA'],
 ['Download audit report','Family &amp; friends — café_audit.json','{"synthetic":true}']]){
 const event=page.waitForEvent('download');await page.getByRole('button',{name:button,exact:true}).click();const d=await event;
 assert.equal(d.suggestedFilename(),name);assert.equal(await d.failure(),null);
 assert.equal(fs.readFileSync(await d.path(),'utf8'),expectedBytes);downloads.push({name:d.suggestedFilename()});
}
await page.locator('#jobcard').scrollIntoViewIfNeeded();
const variant=process.env.TASK119_VARIANT||'native';
await page.screenshot({path:root+'/'+variant+'-desktop.png'});
await page.setViewportSize({width:390,height:844});await page.locator('#jobcard').scrollIntoViewIfNeeded();
assert.equal(await titleName(),uploadName);await page.screenshot({path:root+'/'+variant+'-mobile.png'});
assert.deepEqual(errors,[]);assert.deepEqual(warnings,[]);
const result={url:page.url(),title:await page.title(),browser:await browser.version(),viewports:[[1365,950],[390,844]],accepted,structures,downloads,errors,warnings,worker:'controlled done/output fixture; actual intake/list/detail/download routes',browserPlugin:'absent; prepared Playwright fallback'};
fs.writeFileSync(root+'/'+variant+'-browser.json',JSON.stringify(result,null,2));console.log(JSON.stringify(result));await browser.close();
})().catch(async e=>{console.error(e);if(ownedBrowser)await ownedBrowser.close();process.exitCode=1});
