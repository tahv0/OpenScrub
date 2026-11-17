const {chromium}=require('playwright');
(async()=>{
 const b=await chromium.launch({headless:true});const p=await b.newPage({viewport:{width:1365,height:950}});
 const errors=[];p.on('pageerror',e=>errors.push(e.message));
 await p.addInitScript(()=>{window.showSaveFilePicker=async()=>({createWritable:async()=>new WritableStream({write:()=>new Promise(r=>setTimeout(r,40))})});});
 await p.goto('http://127.0.0.1:18484');await p.evaluate(()=>openJob('alpha'));
 await p.getByRole('button',{name:'Save redacted video as…'}).click();await p.waitForTimeout(1800);
 const btn=p.getByRole('button',{name:'Saving…'});await btn.scrollIntoViewIfNeeded();
 await p.screenshot({path:'/tmp/openscrub-save-as-20261116/donor-static-saving.png'});
 console.log(JSON.stringify({url:p.url(),title:await p.title(),button:await btn.textContent(),disabled:await btn.isDisabled(),exportProgressBars:await p.locator('#actions progress').count(),errors}));
 for(const route of ['download','report']){const r=await p.request.get('http://127.0.0.1:18484/api/jobs/alpha/'+route);console.log(route,r.status(),r.headers()['content-length']);await r.dispose();}
 await b.close();
})().catch(e=>{console.error(e);process.exit(1)});
