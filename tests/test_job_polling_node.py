"""Bounded schedules against the actual evaluated APP_JS; Node is optional."""
import json
import shutil
import subprocess

import pytest

from test_review_save_failures import app_js

HARNESS = r"""
const vm=require('node:vm'),assert=require('node:assert/strict');
const elements=new Map(), events={};
// Tree/text semantics only: geometry remains a fixed schedule-test stub.
function el(type=1,data=''){return {nodeType:type,data,dataset:{},childNodes:[],style:{},scrollTop:0,clientTop:0,clientWidth:800,clientHeight:100,scrollHeight:100,
 get textContent(){return this.nodeType===3?this.data:this.childNodes.map(n=>n.textContent).join('')},
 set textContent(value){if(this.nodeType===3)this.data=value;else{this.childNodes=[];if(value)this.appendChild(el(3,value))}},
 get firstChild(){return this.childNodes[0]||null},
 appendChild(node){if(node.nodeType===11){for(const child of [...node.childNodes])this.appendChild(child);node.childNodes=[];return node}
 node.parentNode=this;this.childNodes.push(node);return node},
 contains(node){return node===this||this.childNodes.some(n=>n.contains(node))},
 getBoundingClientRect(){return {top:0,bottom:100,height:100}},
 classList:{toggle(){},remove(){}},addEventListener(){},removeEventListener(){},querySelector(){return null},
 remove(){if(this.parentNode)this.parentNode.childNodes=this.parentNode.childNodes.filter(n=>n!==this);for(const [k,v] of elements)if(v===this)elements.delete(k)},
 insertAdjacentHTML(pos,html){for(const m of html.matchAll(/id="([^"]+)"/g))elements.set(m[1],el());},
 set innerHTML(html){this._html=html;if(this===elements.get('detail')){
 for(const k of [...elements.keys()])if(k!=='detail')elements.delete(k);}
 this.insertAdjacentHTML('',html)}, get innerHTML(){return this._html||''}}}
elements.set('detail',el());
let now=0,seq=0;const timers=new Map();
const listen=(type,fn)=>(events[type]??=[]).push(fn);
const ctx=vm.createContext({console,AbortController,Set,Map,Promise,JSON,Math,Date,
 performance:{now:()=>now},
 document:{hidden:false,getElementById:id=>elements.get(id)||null,querySelectorAll:()=>[],
 addEventListener:listen,createElement:()=>el(),createTextNode:text=>el(3,text),createDocumentFragment:()=>el(11)},window:{addEventListener:listen},detail:elements.get('detail'),
 setTimeout:(fn,ms)=>{const id=++seq;timers.set(id,{fn,at:now+ms});return id},clearTimeout:id=>timers.delete(id),
 setInterval:(fn,ms)=>{const id=++seq;timers.set(id,{fn,at:now+ms,repeat:ms});return id},clearInterval:id=>timers.delete(id),
 confirm:()=>true,alert(){},fetch(){throw Error('unexpected startup fetch')}});
vm.runInContext(SOURCE.slice(0,SOURCE.indexOf('loadPersist();loadCertInfo();loadJobs();setInterval(loadJobs,5000);')).replace(/^refreshModelPanel\(\);renderTiers\(\);$/m,''),ctx);
Object.assign(ctx,{elements,events,timers,assert});
vm.runInContext(`
// Scheduling/layout is covered by its own complete owner suite and browser.
ReviewScheduler.prototype.start=function(){};
loadJobs=()=>{};showPanel=()=>{};initMarquee=()=>{};
var calls=[],queue=[];
fetch=(url,options={})=>{const r={url,options};calls.push(r);return new Promise((resolve,reject)=>{
 Object.assign(r,{resolve,reject});queue.push(r)});};
function response(body,status=200){return {ok:status>=200&&status<300,status,json:async()=>body};}
function job(phase='queued',progress=0.2){return {id:CUR,name:'Job '+CUR,phase,progress,eta:null,error:null,has_output:true};}
function log(lines=['line'],len=lines.length,from=LOGN){return {from,lines,len};}
async function tick(){for(let i=0;i<40;i++)await Promise.resolve();}
async function reply(body,status=200){queue.shift().resolve(response(body,status));await tick();}
async function cycle(phase='queued',lines=[]){await reply(job(phase));await reply(log(lines));}
function emit(type){for(const fn of events[type]||[])fn();}
`,ctx);
ctx.advance=async ms=>{const target=now+ms;while(true){let next;for(const [id,t] of timers){
 if(t.at<=target&&(!next||t.at<next[1].at))next=[id,t];}if(!next)break;
 now=next[1].at;timers.delete(next[0]);if(next[1].repeat)timers.set(next[0],{...next[1],at:now+next[1].repeat});
 next[1].fn();await vm.runInContext('tick()',ctx);}now=target;await vm.runInContext('tick()',ctx)};
const watchdog=setTimeout(()=>{console.error('pending scenario');process.exit(1)},3000);
(async()=>{await vm.runInContext('(async()=>{'+SCENARIO+'})()',ctx);clearTimeout(watchdog)})().catch(e=>{console.error(e);process.exit(1)});
"""


def run_js(scenario):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node needed for emitted polling JavaScript")
    script = "const SOURCE=" + json.dumps(app_js()) + ";const SCENARIO=" + json.dumps(scenario) + ";" + HARNESS
    result = subprocess.run([node], input=script, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr


def test_same_view_single_cycle_and_completion_delay():
    run_js("""openJob('A');refresh();refresh();await advance(1800);
    assert.equal(calls.length,1,'pending metadata must coalesce');
    await reply(job('scanning',0.8));refresh();await advance(900);
    assert.equal(calls.length,2,'pending log must coalesce');
    await reply(log(['one']));assert.equal(elements.get('log').textContent,'one');
    await advance(899);assert.equal(calls.length,2);await advance(1);assert.equal(calls.length,3);
    await reply(job('scanning'));await reply(log([],1));assert.equal(elements.get('prog').value,0.2);
    assert.equal(elements.get('log').textContent,'one');""")


@pytest.mark.parametrize('kind', ['headers', 'body'])
def test_whole_operation_deadline_releases_ignore_abort(kind):
    run_js("""openJob('A');const old=queue.shift();let release;
    if(KIND==='body'){old.resolve({ok:true,json:()=>new Promise(r=>release=r)});await tick();}
    await advance(14999);assert.equal(calls.length,1);await advance(1);
    assert.equal(old.options.signal.aborted,true);assert.match(elements.get('pollStatus').textContent,/retry/i);
    await advance(900);assert.equal(calls.length,2);await cycle();
    if(release)release(job('queued',0.9));else old.resolve(response(job('queued',0.9)));
    await tick();assert.equal(elements.get('prog').value,0.2);assert.equal(elements.get('pollStatus').textContent,'');
    assert.equal(timers.size,1,'losing operation must not retain timers');""".replace('KIND', json.dumps(kind)))


@pytest.mark.parametrize('stage', ['metadata', 'log'])
@pytest.mark.parametrize('kind', ['network', 'json', '503'])
def test_failures_retain_valid_dom_then_recover(stage, kind):
    run_js("""openJob('A');await cycle('queued',['kept']);await advance(900);
    if(STAGE==='log')await reply(job('queued',0.4));
    const req=queue.shift();if(KIND==='network')req.reject(Error('offline'));
    else if(KIND==='json')req.resolve({ok:true,json:async()=>{throw Error('invalid')}});
    else req.resolve(response({error:'unavailable'},503));await tick();
    assert.equal(elements.get('log').textContent,'kept');assert.match(elements.get('pollStatus').textContent,/retry/i);
    assert.ok(!elements.get('detail').innerHTML.includes('undefined'));
    await advance(900);await cycle();assert.equal(elements.get('pollStatus').textContent,'');
    assert.ok(calls.every(c=>!c.options.method),'recovery must never mutate jobs');
    """.replace('STAGE', json.dumps(stage)).replace('KIND', json.dumps(kind)))


def test_initial_failure_and_bounded_backoff_reset():
    run_js("""openJob('A');for(const delay of [900,1800,3600,7200,10000,10000]){
    queue.shift().reject(Error('offline'));await tick();assert.match(elements.get('pollStatus').textContent,/retry/i);
    const n=calls.length;await advance(delay-1);assert.equal(calls.length,n);await advance(1);assert.equal(calls.length,n+1);}
    await cycle();await advance(900);assert.equal(calls.length,9);""")


@pytest.mark.parametrize('mode', ['reopen', 'aba', 'delete'])
def test_obsolete_finally_cannot_control_new_view(mode):
    run_js("""openJob('A');const old=queue.shift();
    if(MODE==='delete'){const p=delJob('A');await reply({ok:true});await p;old.resolve(response(job()));await tick();
      await advance(20000);assert.equal(CUR,null);assert.equal(timers.size,0);assert.equal(calls.length,2);return;}
    if(MODE==='aba'){openJob('B');queue.shift();}openJob('A');await tick();
    assert.equal(old.options.signal.aborted,true);const current=queue[0];
    old.resolve(response(job('done',1)));await tick();refresh();assert.equal(queue[0],current);assert.equal(queue.length,1);
    await cycle();assert.equal(elements.get('prog').value,0.2);assert.equal(timers.size,1);
    """.replace('MODE', json.dumps(mode)))


def test_authoritative_empty_shrunk_cursor_initial_tail_and_scroll():
    run_js("""openJob('A');await reply(job());await reply(log(Array.from({length:405},(_,i)=>'L'+i),405,0));
    const lg=elements.get('log');assert.equal(lg.textContent.split('\\n').length,400);assert.ok(lg.textContent.startsWith('L5\\n'));
    assert.equal(LOGN,405);assert.equal(lg.scrollTop,100);lg.scrollTop=0;lg.scrollHeight=1000;
    await advance(900);await reply(job());await reply(log([],1,405));
    assert.ok(lg.textContent.startsWith('L5\\n'));assert.equal(LOGN,405);assert.ok(queue[0].url.endsWith('from=0'));
    await reply(log(['new'],1,0));assert.equal(lg.textContent,'new');assert.equal(LOGN,1);assert.equal(lg.scrollTop,1000,'accepted reset goes to recent bottom');
    await advance(900);await cycle();assert.equal(LOGN,0,'empty len=0 is authoritative');""")


@pytest.mark.parametrize('transition', ['done', 'return', 'same', 'manual', 'failure'])
def test_automatic_review_eligibility_and_retry(transition):
    run_js("""openJob('A');await cycle('review');const detections=queue.shift();
    assert.ok(detections.url.endsWith('/detections'));await advance(900);assert.ok(queue[0].url==='api/jobs/A');
    if(TRANSITION==='failure'){detections.reject(Error('offline'));await tick();await cycle('review');
      assert.ok(queue[0].url.endsWith('/detections'));await reply({duration:3,detections:[]});assert.equal(DUR,3);return;}
    await cycle(TRANSITION==='same'?'review':'done');
    if(TRANSITION==='return'){await advance(900);await cycle('review');}
    if(TRANSITION==='manual'){const p=loadReview();await reply({duration:3,detections:[]});await p;}
    detections.resolve(response({duration:99,detections:[]}));await tick();
    assert.equal(DUR,TRANSITION==='same'?99:TRANSITION==='manual'?3:0);
    """.replace('TRANSITION', json.dumps(transition)))


def test_hide_wake_bursts_cancel_and_coalesce():
    run_js("""openJob('A');const old=queue.shift();document.hidden=true;emit('visibilitychange');await tick();
    assert.equal(old.options.signal.aborted,true);await advance(20000);assert.equal(calls.length,1);
    document.hidden=false;emit('visibilitychange');emit('focus');emit('pageshow');emit('online');await advance(0);
    assert.equal(calls.length,2);old.resolve(response(job('done',1)));await tick();await cycle();
    emit('focus');emit('online');await advance(0);assert.equal(calls.length,4);refresh();assert.equal(calls.length,4);
    assert.ok(calls.every(c=>!c.options.method));""")


def test_online_wake_replaces_pending_work_once():
    run_js("""openJob('A');const old=queue.shift();emit('online');emit('focus');emit('pageshow');
    await advance(0);assert.equal(old.options.signal.aborted,true);assert.equal(calls.length,2);
    old.reject(Error('late failure'));await tick();await cycle();assert.equal(timers.size,1);""")


def test_new_contract_stale_clamp_replaces_and_advances():
    run_js("""openJob('A');await reply(job());
    await reply({from:5,base:5,len:7,epoch:'E1',reset:'stale',dropped:5,truncated:0,lines:['six','seven']});
    assert.equal(elements.get('log').textContent,'six\\nseven');
    assert.equal(LOGN,7);assert.equal(LOGE,'E1');
    assert.match(elements.get('logStatus').textContent,/omitted/);
    await advance(900);await reply(job());assert.ok(queue[0].url.includes('epoch=E1'));
    await reply({from:7,base:5,len:8,epoch:'E1',reset:null,dropped:5,truncated:0,lines:['eight']});
    assert.equal(elements.get('log').textContent,'six\\nseven\\neight');""")


@pytest.mark.parametrize('change', [
    "delete bad.base", "bad.len=9", "bad.from=0", "bad.base=3", "bad.reset='future'",
    "bad.epoch='E2'", "bad.dropped=-1", "bad.truncated=1.5", "bad.epoch='x'.repeat(129)",
    "bad.lines=[3]", "bad.len=Number.MAX_SAFE_INTEGER+1",
])
def test_invalid_new_snapshot_cannot_publish_or_advance(change):
    run_js("""openJob('A');await reply(job());
    await reply({from:0,base:0,len:1,epoch:'E1',reset:null,dropped:0,truncated:0,lines:['kept']});
    await advance(900);await reply({...job(),log_epoch:'ADVISORY',log_len:999});
    const bad={from:1,base:0,len:2,epoch:'E1',reset:null,dropped:0,truncated:0,lines:['bad']};CHANGE;
    await reply(bad);assert.equal(LOGN,1);assert.equal(LOGE,'E1');assert.equal(elements.get('log').textContent,'kept');
    assert.match(elements.get('pollStatus').textContent,/retrying/);""".replace('CHANGE', change))


def test_epoch_replacement_future_and_authoritative_empty():
    run_js("""openJob('A');await reply(job());
    await reply({from:0,base:0,len:1,epoch:'E1',reset:null,dropped:0,truncated:0,lines:['old']});
    await advance(900);await reply(job());
    await reply({from:0,base:0,len:2,epoch:'E2',reset:'epoch',dropped:0,truncated:0,lines:['fresh','history']});
    assert.equal(elements.get('log').textContent,'fresh\\nhistory');assert.equal(LOGN,2);assert.equal(LOGE,'E2');
    await advance(900);await reply(job());
    await reply({from:0,base:0,len:0,epoch:'E3',reset:'epoch',dropped:0,truncated:0,lines:[]});
    assert.equal(elements.get('log').textContent,'');assert.equal(LOGN,0);assert.equal(LOGE,'E3');""")


def test_phase_actions_replacement_releases_only_removed_editor_owner():
    run_js("""openJob('A');await cycle('done');
    const actions=elements.get('actions'),cv=document.createElement('canvas');actions.appendChild(cv);
    let disconnected=0,paused=0;BE.drag={kind:'move'};
    const video={paused:false,pause(){paused++;this.paused=true}};
    BE_VIEW={cv,vid:video,editor:BE,observer:{disconnect(){disconnected++}}};
    await advance(900);await cycle('rendering');
    assert.equal(BE_VIEW,null);assert.equal(BE.drag,null);
    assert.equal(disconnected,1);assert.equal(paused,1);
    """)


def test_manual_review_retry_owns_inflight_request_against_polling():
    run_js("""openJob('A');await cycle('review');const initial=queue.shift();
    initial.reject(Error('offline'));await tick();
    const manual=loadReview(),request=queue.shift();assert.ok(request.url.endsWith('/detections'));
    await advance(900);await cycle('review');
    assert.equal(queue.filter(r=>r.url.endsWith('/detections')).length,0,'poll replaced manual retry');
    request.resolve(response({duration:7,detections:[]}));await tick();await manual;
    assert.equal(DUR,7);await advance(900);await cycle('review');
    assert.equal(queue.filter(r=>r.url.endsWith('/detections')).length,0);
    """)


def test_failed_manual_review_retry_restores_automatic_eligibility():
    run_js("""openJob('A');await cycle('review');queue.shift().reject(Error('offline'));await tick();
    const manual=loadReview(),request=queue.shift();request.reject(Error('offline'));await tick();await manual;
    await advance(900);await cycle('review');assert.ok(queue[0].url.endsWith('/detections'));
    await reply({duration:9,detections:[]});assert.equal(DUR,9);
    """)


def test_newer_manual_retry_retains_claim_when_older_manual_fails():
    run_js("""openJob('A');await cycle('review');queue.shift().reject(Error('offline'));await tick();
    const first=loadReview(),old=queue.shift(),second=loadReview(),current=queue.shift();
    old.reject(Error('late failure'));await tick();await first;
    await advance(900);await cycle('review');
    assert.equal(queue.filter(r=>r.url.endsWith('/detections')).length,0,'old failure released newer claim');
    current.resolve(response({duration:8,detections:[]}));await tick();await second;assert.equal(DUR,8);
    """)


def test_failed_auto_completion_cannot_release_manual_retry_claim():
    run_js("""openJob('A');await cycle('review');const initial=queue.shift();let manual,request;
    reviewLoadFailure=()=>{Promise.resolve().then(()=>{manual=loadReview();request=queue.shift()})};
    initial.reject(Error('offline'));await tick();
    await advance(900);await cycle('review');
    assert.equal(queue.filter(r=>r.url.endsWith('/detections')).length,0,'old auto completion released manual claim');
    request.resolve(response({duration:11,detections:[]}));await tick();await manual;assert.equal(DUR,11);
    """)
