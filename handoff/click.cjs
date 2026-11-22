const {chromium}=require(process.env.OPENSCRUB_PLAYWRIGHT_MODULE||'playwright');
(async()=>{
 const b=await chromium.launch({executablePath:process.env.OPENSCRUB_CHROMIUM||undefined,args:['--no-sandbox']});
 const p=await b.newPage();p.setDefaultTimeout(240000);
 p.on('pageerror',e=>console.log('pageerror',e.message));p.on('dialog',d=>{console.log('dialog',d.message().slice(0,150));d.accept()});
 await p.goto('http://127.0.0.1:18391/');await p.waitForSelector('text=input.mp4');
 await p.evaluate(()=>openJob('aaaaaaaaaaaa'));
 await p.waitForSelector('#reviewOutput');
 const labels=async s=>console.log(s,JSON.stringify(await p.locator('#reviewOutput option').allTextContents()));
 await labels('before');
 await p.selectOption('#reviewOutput','blur');
 console.log('filtered',await p.textContent('#reviewFilterStatus'));
 let t=Date.now();
 await p.locator('#review section button',{hasText:/^Blur all$/}).first().click();
 await p.evaluate(()=>0);console.log('click s',(Date.now()-t)/1000);
 await labels('after click');t=Date.now();
 const r=p.waitForResponse(r=>r.url().endsWith('/detections')&&r.request().method()==='POST');
 await p.locator('[data-save-edits]').click();
 console.log('save',(await r).status(),(Date.now()-t)/1000);
 const r2=await p.waitForResponse(r=>r.url().includes('/render')&&r.request().method()==='POST');
 console.log('render',r2.status());
 for(let i=0;i<170;i++){const j=await (await p.request.get('http://127.0.0.1:18391/api/jobs/aaaaaaaaaaaa')).json();
  if(['done','error','cancelled'].includes(j.phase)){console.log('phase',j.phase,j.error||'',j.output||'');break}
  await new Promise(r=>setTimeout(r,2000));}
 await b.close();
})().catch(e=>{console.log('FAIL',e.message.slice(0,700));process.exit(1)});
