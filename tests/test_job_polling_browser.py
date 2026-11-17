"""Full emitted PAGE acceptance, including real HTTP held-body responses.

Optional existing Playwright/Chromium only. Set NODE_PATH and
PLAYWRIGHT_BROWSERS_PATH for an isolated installation; no install is attempted.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import pytest


@pytest.fixture
def polling_http(monkeypatch, tmp_path):
    import openscrub_web as web

    monkeypatch.setattr(web, 'JOBS', {})
    monkeypatch.setattr(web, 'JOBS_DIR', str(tmp_path))
    for jid in ('A', 'B'):
        job = web.new_job('', {}, 'synthetic job ' + jid)
        web.JOBS.pop(job['id'])
        folder = tmp_path / jid
        folder.mkdir()
        job.update(id=jid, dir=str(folder), phase='queued', progress=.2, log=web.JobLog(['log-' + jid]))
        web.JOBS[jid] = job
    monkeypatch.setattr(web, 'enqueue', lambda *_: None)
    gate = threading.Event()
    state = {'kind': None, 'entered': 0, 'released': 0}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            action = data.get('action')
            jid = data.get('id', 'A')
            if action in ('seed', 'replace', 'recover'):
                old = web.JOBS[jid]
                if action == 'recover':
                    folder = Path(old['dir'])
                    (folder / 'input.mp4').write_bytes(b'')
                    web.JOBS.pop(jid)
                    web.rehydrate_jobs()
                    job = web.JOBS[jid]
                else:
                    job = web.new_job('', {}, 'synthetic job ' + jid)
                    web.JOBS.pop(job['id'])
                    folder = tmp_path / jid
                    folder.mkdir(exist_ok=True)
                    job.update(id=jid, dir=str(folder), phase='queued', name='synthetic job ' + jid)
                    web.JOBS[jid] = job
                if action == 'replace':
                    web.WebCallbacks(old).log('obsolete callback must stay old')
                # Recovery starts with its real recovery message.
                count = data.get('count', 0)
                for i in range(count):
                    web.WebCallbacks(job).log(data.get('prefix', 'L') + str(i))
            elif action == 'append':
                callback = web.WebCallbacks(web.JOBS[jid])
                for message in data['lines']:
                    callback.log(message)
            elif action == 'cancel':
                with web.app.test_client() as client:
                    assert client.post('/api/jobs/' + jid + '/cancel').status_code == 200
            elif action == 'retry':
                job = web.JOBS[jid]
                video = Path(job['dir']) / 'input.mp4'
                video.write_bytes(b'')
                job.update(video=str(video), phase='error')
                with web.app.test_client() as client:
                    assert client.post('/api/jobs/' + jid + '/retry').status_code == 200
            if data.get('release'):
                gate.set()
            if data.get('kind'):
                gate.clear()
                state['kind'] = data['kind']
            payload = json.dumps(state).encode()
            self.send_response(200)
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_DELETE(self):
            with web.app.test_client() as client:
                result = client.delete(self.path)
            self.send_response(result.status_code)
            self.send_header('Content-Type', result.content_type)
            self.send_header('Content-Length', str(len(result.data)))
            self.end_headers()
            self.wfile.write(result.data)

        def do_GET(self):
            path = urlsplit(self.path).path
            if path == '/':
                payload = web.PAGE.replace('%%VERSION%%', web.openscrub.VERSION).encode()
                content_type = 'text/html'
            elif path == '/__qa__/state':
                payload = json.dumps(state).encode()
                content_type = 'application/json'
            else:
                # The real production metadata/log routes supply the JSON body.
                with web.app.test_client() as client:
                    result = client.get(self.path)
                payload = result.data
                content_type = result.content_type
            kind = 'log' if path.endswith('/log') else 'meta'
            held = path.startswith('/api/jobs/A') and state['kind'] == kind
            if held:
                state['kind'] = None
                state['entered'] += 1
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(payload)))
            if held:
                self.send_header('X-QA-Body-Gate', kind)
            self.end_headers()
            try:
                if held:
                    self.wfile.write(payload[:1])
                    self.wfile.flush()
                    gate.wait(15)
                    state['released'] += 1
                    self.wfile.write(payload[1:])
                else:
                    self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError):
                pass  # Expected when the shipped deadline requests actual abort.

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield 'http://127.0.0.1:' + str(server.server_port)
    finally:
        gate.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


BROWSER = r"""
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
const base=process.env.POLLING_BASE,results=[];
const pause=ms=>new Promise(r=>setTimeout(r,ms));
async function wait(fn){for(let i=0;i<150;i++){if(await fn())return;await pause(20)}throw Error('bounded condition expired')}
const meta=(id,phase='queued',progress=.2)=>({id,name:'synthetic job '+id,phase,progress,eta:null,error:null,has_output:true});
const tiny=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=','base64');
(async()=>{
const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
async function setup(name){
 const page=await browser.newPage({viewport:{width:1280,height:950}});
 const q={name,page,events:[],held:[],plans:[],errors:[],console:[],injected:[],phase:'queued',progress:.2,logs:{A:['log-A'],B:['log-B']}};
 page.on('pageerror',e=>q.errors.push(e.message));page.on('console',m=>{if(['error','warning'].includes(m.type()))q.console.push({text:m.text(),url:m.location().url})});
 page.on('dialog',d=>d.accept());await page.clock.install();
 await page.route('**/api/**',async route=>{
  const req=route.request(),u=new URL(req.url()),m=u.pathname.match(/^\/api\/jobs\/([^/]+)(?:\/(.*))?$/);
  if(!m){let body={};if(u.pathname==='/api/jobs')body=[];
   if(u.pathname==='/api/quality_tier')body={tiers:[],current:'fast'};
   if(u.pathname==='/api/persist')body={enabled:false,count:0};
   return route.fulfill({json:body})}
  const [,id,tail]=m,kind=tail||'meta';q.events.push({id,kind,query:u.search,method:req.method()});
  if((q.pass===kind||q.pass==='both'&&['meta','log'].includes(kind))&&req.method()==='GET')return route.continue();
  if(/thumb|detframe|frame_at|preview.jpg/.test(kind))return route.fulfill({contentType:'image/png',body:tiny});
  let body=kind==='meta'?meta(id,q.phase,q.progress):kind==='log'?{from:+u.searchParams.get('from'),lines:q.logs[id].slice(+u.searchParams.get('from')),len:q.logs[id].length}:
   kind==='detections'?{duration:10,detections:[{i:0,category:'mrn',text:'review-'+id,enabled:true,t_start:0,t_end:1,track:-1,person:-1}]}:
   kind==='mediainfo'?{duration:10,width:320,height:180}:kind==='report'?{detections:[],audio_redactions:[{t0:1,t1:2,mode:'mute'}]}:{ok:true};
  const plan=q.plans.find(p=>!p.used&&p.kind===kind&&(!p.id||p.id===id));
  if(plan){plan.used=true;if(plan.body)body=plan.body;if(plan.abort){q.injected.push({kind:'network',url:req.url()});return route.abort('failed');}
   if(plan.hold)await new Promise(resolve=>q.held.push({id,kind,release:resolve}));}
  if(plan?.status===503)q.injected.push({kind:'503',url:req.url()});
  await route.fulfill({status:plan?.status||200,contentType:'application/json',body:plan?.raw??JSON.stringify(body)}).catch(()=>{});
 });
 await page.goto(base);await page.clock.pauseAt(await page.evaluate(()=>Date.now()+100));assert.equal(await page.title(),'OpenScrub');assert.match(await page.locator('body').innerText(),/OpenScrub/);
 return q;
}
const status=q=>q.page.locator('#pollStatus').innerText();
async function opened(q,id='A'){await q.page.evaluate(id=>openJob(id),id);await wait(async()=>await q.page.locator('#log').count()&&(await q.page.locator('#log').innerText())==='log-'+id)}
async function advance(q,ms=900){await q.page.clock.runFor(ms);await pause(60)}
async function finish(q){for(const h of q.held)h.release();await pause(30);
 assert.deepEqual(q.errors,[],'no unhandled page errors');
 assert.ok(q.events.every(e=>e.method==='GET'||e.method==='DELETE'),'wake/recovery never submit mutations');
 // Each diagnostic must consume an actual injection in this scenario and URL.
 const remaining=[...q.injected];
 for(const diagnostic of q.console){
  const kind=diagnostic.text.includes('net::ERR_FAILED')?'network':diagnostic.text.includes('503')?'503':null;
  const index=remaining.findIndex(i=>i.kind===kind&&i.url===diagnostic.url);
  assert.ok(index>=0,JSON.stringify({scenario:q.name,unexpected:diagnostic,injections:q.injected}));
  remaining.splice(index,1);
 }
 results.push({name:q.name,events:q.events,injections:q.injected,controlledConsole:q.console,pageErrors:q.errors});await q.page.close();}
try{
 {
 const q=await setup('overlap-progress-log');q.plans.push({kind:'meta',hold:true,body:meta('A','queued',.8)});
 await q.page.evaluate(()=>openJob('A'));await wait(()=>q.held.length===1);await advance(q,1800);await q.page.evaluate(()=>{refresh();refresh()});
 assert.equal(q.events.length,1);q.held[0].release();await wait(async()=>await q.page.locator('#log').count()&&(await q.page.locator('#log').innerText())==='log-A');
 assert.equal(await q.page.locator('#prog').evaluate(e=>e.value),.8);q.plans.push({kind:'log',hold:true});await advance(q);await wait(()=>q.held.length===2);
 await advance(q,1800);assert.equal(q.events.filter(e=>e.kind==='log').length,2);q.held[1].release();await pause(60);assert.equal(await q.page.locator('#log').innerText(),'log-A');await finish(q);
 }
 for(const kind of ['meta','log']){
 const q=await setup('real-HTTP-'+kind+'-held-body-deadline');q.pass=kind;
 await q.page.request.post(base+'/__qa__/control',{data:{kind}});
 let headers=0; q.page.on('response',r=>{if(r.headers()['x-qa-body-gate']===kind)headers++});
 await q.page.evaluate(()=>openJob('A'));await wait(()=>headers===1);
 assert.equal((await q.page.request.get(base+'/__qa__/state').then(r=>r.json())).kind,null);
 await advance(q,14999);assert.equal(await status(q),'');assert.equal(q.events.filter(e=>e.kind===kind).length,1);
 await advance(q,1);await wait(async()=>/retrying/.test(await status(q)));
 await advance(q);await wait(async()=>await q.page.locator('#log').count()&&(await q.page.locator('#log').innerText())==='log-A');
 await q.page.request.post(base+'/__qa__/control',{data:{release:true}});await wait(async()=>(await q.page.request.get(base+'/__qa__/state').then(r=>r.json())).released>=(kind==='meta'?1:2));
 assert.equal(await status(q),'');await finish(q);
 }
 for(const kind of ['meta','log']){
 const q=await setup('real-HTTP-'+kind+'-body-switch');q.pass=kind;
 await q.page.request.post(base+'/__qa__/control',{data:{kind}});let headers=0;
 q.page.on('response',r=>{if(r.headers()['x-qa-body-gate']===kind)headers++});
 await q.page.evaluate(()=>openJob('A'));await wait(()=>headers===1);await opened(q,'B');
 await q.page.request.post(base+'/__qa__/control',{data:{release:true}});await pause(60);
 assert.equal(await q.page.locator('#log').innerText(),'log-B');await finish(q);
 }
 for(const failure of ['network','json','503']){
 const q=await setup('initial-'+failure+'-recovery');q.plans.push({kind:'meta',abort:failure==='network',raw:failure==='json'?'{':undefined,status:failure==='503'?503:200});
 await q.page.evaluate(()=>openJob('A'));await wait(async()=>/retrying/.test(await status(q)));
 assert.equal(await q.page.locator('#jobcard').count(),0);await advance(q);await wait(async()=>await status(q)==='');
 assert.match(await q.page.locator('#jobcard h2').innerText(),/job A/);await finish(q);
 }
 for(const mode of ['same','aba','delete']){
 const q=await setup('obsolete-'+mode);q.plans.push({kind:'meta',id:'A',hold:true,body:meta('A','done',1)});
 await q.page.evaluate(()=>openJob('A'));await wait(()=>q.held.length===1);
 if(mode==='delete'){await q.page.evaluate(()=>delJob('A'));await wait(async()=>await q.page.evaluate(()=>CUR===null));}
 else{if(mode==='aba')await opened(q,'B');await opened(q,'A');}
 q.held[0].release();await pause(60);if(mode==='delete'){const n=q.events.length;await advance(q,20000);assert.equal(q.events.length,n)}
 else assert.equal(await q.page.locator('#prog').evaluate(e=>e.value),.2);await finish(q);
 }
 {
 const q=await setup('cursor-tail-scroll-reset');q.logs.A=Array.from({length:405},(_,i)=>'L'+i);
 await q.page.evaluate(()=>openJob('A'));await wait(async()=>await q.page.evaluate(()=>LOGN===405));
 assert.equal((await q.page.locator('#log').innerText()).split('\n').length,400);assert.match(await q.page.locator('#log').innerText(),/^L5\n/);
 await q.page.locator('#log').evaluate(e=>e.scrollTop=0);q.logs.A=['new'];await advance(q);await wait(async()=>await q.page.evaluate(()=>LOGN===1));
 assert.equal(await q.page.locator('#log').innerText(),'new');assert.ok(q.events.filter(e=>e.kind==='log').at(-1).query==='?from=0');
 q.logs.A=[];await advance(q);await wait(async()=>await q.page.evaluate(()=>LOGN===0));assert.equal(await q.page.locator('#log').innerText(),'');await finish(q);
 }
 for(const mode of ['done','return','same','failure','manual']){
 const q=await setup('automatic-review-'+mode);q.phase='review';q.plans.push({kind:'detections',hold:true,abort:false});
 await opened(q);await wait(()=>q.held.length===1);
 if(mode==='failure'){q.held[0].release();await pause(50);await q.page.evaluate(()=>{document.getElementById('review')?.remove()});
 // A separate initialization failure on a new view must retry without a phase change.
 q.plans.push({kind:'detections',abort:true});await q.page.evaluate(()=>openJob('A'));await wait(async()=>/could not load/.test(await status(q)));
 await advance(q);await wait(async()=>await q.page.locator('#review').count()===1);await finish(q);continue;}
 q.phase=mode==='same'?'review':'done';await advance(q);await wait(async()=>(await q.page.locator('#ph').innerText())===q.phase);
 if(mode==='return'){q.phase='review';q.plans.push({kind:'detections',hold:true});await advance(q);await wait(()=>q.held.length===2)}
 if(mode==='manual'){await q.page.getByRole('button',{name:'Re-open review',exact:true}).click();await wait(async()=>await q.page.locator('#review').count()===1);}
 q.held[0].release();await pause(60);assert.equal(await q.page.locator('#review').count(),['same','manual'].includes(mode)?1:0);await finish(q);
 }
 {
 const q=await setup('lifecycle-wake-and-Austin-help-preview');await opened(q);
 await q.page.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,get:()=>true});document.dispatchEvent(new Event('visibilitychange'))});
 const n=q.events.length;await advance(q,20000);assert.equal(q.events.length,n);
 await q.page.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,get:()=>false});document.dispatchEvent(new Event('visibilitychange'));for(const e of ['focus','pageshow','online'])window.dispatchEvent(new Event(e))});
 await advance(q,0);await wait(()=>q.events.length===n+2);
 assert.ok(await q.page.locator('.qm').count()>0);await q.page.locator('summary').filter({hasText:'Advanced settings'}).click();await q.page.locator('.qm:visible').first().click();
 assert.ok(await q.page.locator('.qm.open').count()>0);
 q.phase='review';await advance(q);await wait(async()=>await q.page.locator('#review').count()===1);
 await q.page.locator('#det0 img').click();await wait(async()=>await q.page.locator('#lb img').evaluate(e=>e.naturalWidth>0));await q.page.locator('#lb').click();
 await q.page.getByRole('button',{name:'▶ Preview video & edit boxes (before rendering)'}).click();await wait(async()=>await q.page.locator('#beCv').count()===1);
 assert.ok(await q.page.locator('#beCv').evaluate(e=>e.width>0));
 if(process.env.POLLING_ARTIFACTS)await q.page.screenshot({path:process.env.POLLING_ARTIFACTS+'/polling-review-preview.png'});
 await finish(q);
 }
}finally{await browser.close()}
if(process.env.POLLING_ARTIFACTS)fs.writeFileSync(process.env.POLLING_ARTIFACTS+'/browser-results.json',JSON.stringify(results,null,2));
console.log(JSON.stringify(results.map(q=>({name:q.name,requests:q.events.length,pageErrors:q.pageErrors,controlledConsole:q.controlledConsole})),null,2));
})().catch(e=>{console.error(e);process.exit(1)});
"""


def test_emitted_page_polling_acceptance(polling_http):
    node = shutil.which('node')
    if not node:
        pytest.skip('Node needed for optional Playwright acceptance')
    available = subprocess.run([node, '-e', "require('playwright')"], capture_output=True)
    if available.returncode:
        pytest.skip('Existing Playwright required; no frontend dependencies installed')
    env = dict(os.environ, POLLING_BASE=polling_http)
    result = subprocess.run([node, '-e', BROWSER], capture_output=True, text=True, env=env, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    if os.environ.get('POLLING_ARTIFACTS'):
        Path(os.environ['POLLING_ARTIFACTS'], 'browser-summary.log').write_text(result.stdout)


BOUNDED_BROWSER = r"""
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
const base=process.env.POLLING_BASE,results=[];
const pause=ms=>new Promise(r=>setTimeout(r,ms));
async function wait(fn){for(let i=0;i<200;i++){if(await fn())return;await pause(20)}throw Error('bounded condition expired')}
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 const page=await browser.newPage({viewport:{width:1280,height:950}}),errors=[],consoleErrors=[],requests=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(['error','warning'].includes(m.type()))consoleErrors.push(m.text())});
 await page.clock.install();
 await page.route('**/api/**',async route=>{
  const u=new URL(route.request().url());
  if(/^\/api\/jobs\/[AB](\/log)?$/.test(u.pathname)){requests.push(u.pathname+u.search);return route.continue()}
  let body={};if(u.pathname==='/api/jobs')body=[];
  if(u.pathname==='/api/quality_tier')body={tiers:[],current:'fast'};
  if(u.pathname==='/api/persist')body={enabled:false,count:0};
  return route.fulfill({json:body});
 });
 const control=async data=>{const r=await page.request.post(base+'/__qa__/control',{data});assert.equal(r.status(),200)};
 const cursor=()=>page.evaluate(()=>LOGN);
 const text=()=>page.locator('#log').textContent();
 const note=()=>page.locator('#logStatus').textContent();
 const epoch=()=>page.evaluate(()=>LOGE);
 async function poll(){const n=requests.length;await page.clock.runFor(900);await wait(()=>requests.length>=n+2);await wait(async()=>await page.evaluate(()=>POLL_CYCLE===null))}
 try{
  await control({action:'seed',count:2100});
  await page.goto(base);await page.clock.pauseAt(await page.evaluate(()=>Date.now()+100));
  assert.equal(await page.title(),'OpenScrub');assert.match(await page.locator('body').innerText(),/OpenScrub/);
  await page.evaluate(()=>openJob('A'));await wait(async()=>await cursor()===2100);
  assert.equal(await text(),Array.from({length:400},(_,i)=>'L'+(1700+i)).join('\n'));
  assert.match(await note(),/omitted/);const firstEpoch=await epoch();
  results.push('overflow initial400 through both production routes');
  await control({action:'append',lines:['normal-one','normal-two']});await poll();
  assert.equal(await cursor(),2102);assert.ok((await text()).endsWith('L2099\nnormal-one\nnormal-two'));
  const before=await text();await poll();assert.equal(await text(),before);results.push('normal increments exactly once');
  // A stale cursor must replay retained history; reset display still uses400.
  await control({action:'append',lines:Array.from({length:2100},(_,i)=>'gap-'+i)});await poll();
  assert.equal(await cursor(),4202);assert.equal(await text(),Array.from({length:400},(_,i)=>'gap-'+(1700+i)).join('\n'));
  assert.match(await note(),/omitted/);results.push('stale recovery replaces transcript');
  await page.evaluate(()=>LOGN=999999);await poll();assert.equal(await cursor(),4202);assert.match(await note(),/replaced/);
  results.push('future recovery');
  await control({action:'append',lines:['😀'.repeat(10000)]});await poll();assert.match(await note(),/truncated/);
  assert.ok((await text()).endsWith('... [message truncated]'));results.push('fixed truncation status');
  await control({action:'retry'});await page.evaluate(()=>openJob('A'));await wait(async()=>await cursor()===4204);
  assert.equal(await epoch(),firstEpoch);assert.match(await text(),/retrying scan/);results.push('append-only retry same epoch');
  await control({action:'replace',count:4500,prefix:'replacement-'});await poll();
  assert.equal(await cursor(),4500);assert.notEqual(await epoch(),firstEpoch);
  assert.equal(await text(),Array.from({length:400},(_,i)=>'replacement-'+(4100+i)).join('\n'));
  assert.match(await note(),/replaced/);results.push('actual server job replacement larger than old cursor');
  const replacedEpoch=await epoch();await control({action:'recover',count:4600,prefix:'recovered-'});await poll();
  assert.equal(await cursor(),4601);assert.notEqual(await epoch(),replacedEpoch);
  assert.equal(await text(),Array.from({length:400},(_,i)=>'recovered-'+(4200+i)).join('\n'));
  results.push('actual incomplete recovery replacement larger than old cursor');
  // Hold real old bodies across A→B→A and recovery, then release them late.
  for(const kind of ['meta','log']){
   await control({kind});let headers=0;const listener=r=>{if(r.headers()['x-qa-body-gate']===kind)headers++};page.on('response',listener);
   await page.clock.runFor(900);await wait(()=>headers===1);
   await page.evaluate(()=>openJob('B'));await wait(async()=>await cursor()===1);
   assert.equal(await text(),'log-B');
   await control({action:'replace',count:4700,prefix:'fresh-'+kind+'-'});
   await page.evaluate(()=>openJob('A'));await wait(async()=>await cursor()===4700);
   const accepted=await epoch();await control({release:true});await pause(80);
   assert.equal(await epoch(),accepted);assert.equal(await cursor(),4700);
   assert.ok((await text()).startsWith('fresh-'+kind+'-4300\n'));
   page.off('response',listener);results.push('held '+kind+' body across A→B→A and job replacement');
  }
  // A real pending body from before Retry cannot overwrite the reopened view.
  await control({kind:'log'});let held=0;page.on('response',r=>{if(r.headers()['x-qa-body-gate']==='log')held++});
  await page.clock.runFor(900);await wait(()=>held===1);const retryEpoch=await epoch();
  await control({action:'retry'});await page.evaluate(()=>openJob('A'));await wait(async()=>await cursor()===4701);
  await control({release:true});await pause(80);assert.equal(await cursor(),4701);assert.equal(await epoch(),retryEpoch);
  assert.match(await text(),/retrying scan/);results.push('held body across append-only retry');
  assert.deepEqual(errors,[]);assert.deepEqual(consoleErrors,[]);
  if(process.env.POLLING_ARTIFACTS){
  await page.screenshot({path:process.env.POLLING_ARTIFACTS+'/bounded-logs-desktop.png'});
  await page.setViewportSize({width:390,height:844});await page.screenshot({path:process.env.POLLING_ARTIFACTS+'/bounded-logs-mobile.png'});
  fs.writeFileSync(process.env.POLLING_ARTIFACTS+'/bounded-browser.json',JSON.stringify({results,requests,errors,consoleErrors,url:page.url(),title:await page.title()},null,2));
  }
  console.log(JSON.stringify({results,requests:requests.length,errors,consoleErrors}));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
"""


def test_bounded_history_through_actual_page_and_backend(polling_http):
    node = shutil.which('node')
    if not node:
        pytest.skip('Node needed for optional Playwright acceptance')
    available = subprocess.run([node, '-e', "require('playwright')"], capture_output=True)
    if available.returncode:
        pytest.skip('Existing Playwright required; no dependencies installed')
    env = dict(os.environ, POLLING_BASE=polling_http)
    result = subprocess.run([node, '-e', BOUNDED_BROWSER], capture_output=True, text=True, env=env, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
