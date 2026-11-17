"""Deterministic ownership/admission tests of the shipped review JavaScript.

Browser primitives are adapters only. Real row geometry and user interactions are
checked with Chromium against the actual Flask page, not this harness.
"""
import json
import shutil
import subprocess

import pytest

from test_review_save_failures import HARNESS, app_js


PRIMITIVES = r"""
const row=(i,enabled=true,category='face',person=-1,track=-1,confidence=.5,zone_dropped=false)=>({
 i,enabled,category,person,track,confidence,zone_dropped,text:'synthetic '+i,t_start:i/10,t_end:2+i/10});
function eq(a,b){if(JSON.stringify(a)!==JSON.stringify(b))throw Error(JSON.stringify(a)+' != '+JSON.stringify(b));}
"""


def run(scenario):
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is needed to evaluate the embedded review JavaScript')
    script = 'const SOURCE=' + json.dumps(app_js()) + ';const SCENARIO=' + json.dumps(PRIMITIVES + scenario) + ';' + HARNESS
    result = subprocess.run([node, '-e', script], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr


def test_paging_preserves_hidden_group_choices():
    run("""openJob('A');
    const rows=[row(0,true,'face',0,2,.4),row(1,false,'face',0,3,.9),
      ...Array.from({length:180},(_,j)=>row(j+2)),row(182,false,'face',0,2,.99,true)];
    const sections=reviewDescriptors(rows);eq(TRKMEM[1],[0,1]);eq(ROWCARD[0],1);
    eq(sections.map(s=>s.ids.length),[1,181]);
    REVIEW_META={sections,byId:new Map(sections.flatMap(s=>s.cards.map(c=>[c.id,c])))};
    setAll('face',false);eq([EN[0],EN[1],EN[181],EN[182]],[false,false,false,false]);
    setAllZd(true);eq([EN[0],EN[182]],[false,true]);
    applyDet(0,true);eq([EN[0],EN[1]],[true,false]);
    selSet.add(1);selSet.add(181);bulkSet(true);eq([EN[0],EN[1],EN[181],EN[182]],[true,true,true,true]);
    eq([...selSet],[]);
    """)


NETWORK = r"""
var tasks=[],timers=new Map(),clock=0,serial=0,created=[],revoked=[];
Date.now=()=>clock;setTimeout=(fn,ms)=>{const i=++serial;timers.set(i,{fn,at:clock+ms,ms});return i};clearTimeout=i=>timers.delete(i);
requestAnimationFrame=()=>1;cancelAnimationFrame=()=>{};
AbortController=class{constructor(){this.signal={aborted:false}}abort(){this.signal.aborted=true}};
URL=class{constructor(path){this.href='http://localhost/'+path;this.searchParams={set:(k,v)=>{this.href+='&'+k+'='+v}}}
 static createObjectURL(blob){created.push(blob);return 'blob:'+created.length}static revokeObjectURL(url){revoked.push(url)}};
fetch=(url,options)=>new Promise((resolve,reject)=>tasks.push({url,options,resolve,reject}));
function scheduler(job='A'){
 if(CUR!==job)openJob(job);
 const root={isConnected:true};elements.set('review',root);
 const s=new ReviewScheduler(CUR,VIEW_GEN,root,{sections:[],byId:new Map()});REVIEW_SCHED=s;
 return s;
}
function bind(s,id){
 const img={isConnected:true,removeAttribute(){this.src=''},parentElement:{classList:{add(){},remove(){}}}};
 const b={id,img,card:{isConnected:true},token:{},url:null};s.bindings.set(id,b);return b;
}
function eligible(s,ids){s.eligible=new Map(ids.map((id,i)=>[id,{rank:0,order:i}]));s.updateQueue();}
async function headers(task){task.resolve({ok:true,blob:()=>new Promise((resolve,reject)=>{task.body={resolve,reject}})});await tick();}
async function body(task,value={}){task.body.resolve(value);await tick();}
function advance(ms){clock+=ms;for(const [i,t]of [...timers])if(t.at<=clock){timers.delete(i);t.fn()}}
"""


def test_scroll_jump_prioritizes_current_view_and_body_slots():
    run(NETWORK + """const s=scheduler();for(let i=0;i<12;i++)bind(s,i);
    eligible(s,[0,1,2,3,4,5]);eq(tasks.length,4);eq(THUMB_FLIGHTS.size,4);
    await headers(tasks[0]);eq(tasks.length,4);eq(THUMB_FLIGHTS.size,4);
    eligible(s,[8,9,10,11]);eq(tasks.length,4);
    if(!tasks.slice(0,4).every(t=>t.options.signal.aborted))throw Error('obsolete work not aborted');
    await body(tasks[0]);eq(tasks.length,5);if(!tasks[4].url.includes('/8'))throw Error('jump did not reprioritize');
    eq(created.length,0);eq(THUMB_FLIGHTS.size,4);
    tasks[1].reject(Error('aborted'));tasks[2].reject(Error('aborted'));tasks[3].reject(Error('aborted'));await tick();
    eq(tasks.length,8);eq(THUMB_FLIGHTS.size,4);
    """)


def test_switch_job_discards_old_thumbnail_results_and_drains():
    run(NETWORK + """const a=scheduler();for(let i=0;i<4;i++)bind(a,i);eligible(a,[0,1,2,3]);
    await headers(tasks[0]);a.dispose();const b=scheduler();bind(b,20);eligible(b,[20]);eq(tasks.length,4);
    await body(tasks[0]);eq(created.length,0);eq(tasks.length,5);
    await headers(tasks[4]);await body(tasks[4],{newView:true});eq(created.length,1);
    const oldLoad=b.bindings.get(20).img.onload;b.dispose();oldLoad();eq(revoked,['blob:1']);
    eq(timers.size,0);
    """)


def test_retry_budget_survives_unmount_and_stale_timers_are_fenced():
    run(NETWORK + """const s=scheduler();bind(s,1);eligible(s,[1]);
    for(const delay of [600,1200,1800]){
      tasks.at(-1).reject(Error('network'));await tick();eq([...timers.values()].map(t=>t.ms),[delay]);
      eligible(s,[]);s.retire(s.bindings.get(1));bind(s,1);eligible(s,[1]);
      eq(timers.size,1);advance(delay);await tick();
    }
    tasks.at(-1).reject(Error('network'));await tick();eq(tasks.length,4);eq(timers.size,0);
    eligible(s,[]);s.retire(s.bindings.get(1));bind(s,1);eligible(s,[1]);eq(tasks.length,4);
    eq(s.retries.get(1).failures,4);
    """)


def test_same_job_root_and_a_b_a_reject_stale_blob_and_image_error():
    run(NETWORK + """const first=scheduler();bind(first,1);eligible(first,[1]);await headers(tasks[0]);
    const second=scheduler();bind(second,1);eligible(second,[1]);
    await body(tasks[0],{stale:true});eq(created,[]);first.dispose();
    await headers(tasks[1]);await body(tasks[1],{good:true});const error=second.bindings.get(1).img.onerror;
    second.retire(second.bindings.get(1));bind(second,1);eligible(second,[1]);error();eq(second.retries.get(1).failures,0);
    openJob('B');openJob('A');await headers(tasks[2]);await body(tasks[2],{staleABA:true});eq(created.length,1);
    eq(revoked,['blob:1']);
    """)


def test_http_error_consumes_body_and_retry_does_not_bypass_slots():
    run(NETWORK + """const s=scheduler();for(let i=0;i<6;i++)bind(s,i);eligible(s,[0,1,2,3,4,5]);
    tasks[0].resolve({ok:false,status:503,blob:()=>new Promise(resolve=>tasks[0].body={resolve})});await tick();
    eq(tasks.length,4);eq(THUMB_FLIGHTS.size,4);await body(tasks[0]);eq(tasks.length,5);eq(created.length,0);
    advance(600);eq(tasks.length,5);eq(THUMB_FLIGHTS.size,4);
    await headers(tasks[1]);await body(tasks[1]);eq(tasks.length,6);
    if(!tasks[5].url.includes('/5'))throw Error('retry displaced fresh visible work');
    """)


def test_disposal_clears_observers_listeners_urls_and_retry_continuations():
    run(NETWORK + """const s=scheduler();let disconnected=0,removed=0,gesture=0;
    s.observer={disconnect(){disconnected++}};s.listeners=[()=>removed++,()=>removed++];s.selectionCleanup=()=>gesture++;
    bind(s,1);bind(s,2);eligible(s,[1,2]);await headers(tasks[0]);await body(tasks[0]);
    tasks[1].reject(Error('failure'));await tick();const stale=[...timers.values()][0].fn;
    s.dispose();s.dispose();eq([disconnected,removed,gesture],[1,2,1]);eq(timers.size,0);eq(revoked,['blob:1']);
    stale();advance(4000);eq(tasks.length,2);eq(s.bindings.size,0);eq(s.queue.length,0);
    """)


def test_complete_group_order_and_once_per_bulk_editor_refresh():
    run("""openJob('A');const sections=reviewDescriptors([row(0,true,'face',-1,2),row(1,false,'face',1,3),
     row(2,true,'face',-1,2,.9),row(3,false,'plate',1,2),row(4,false,'face',1,3,.99,true)]);
    eq(sections.map(s=>s.ids),[[4],[1,2],[3]]);eq(TRKMEM[2],[0,2]);eq(ROWCARD[0],2);
    REVIEW_META={sections,byId:new Map(sections.flatMap(s=>s.cards.map(c=>[c.id,c])))};
    let filter=0,draw=0;elements.set('beCv',{});beFilter=()=>filter++;beDraw=()=>draw++;
    setAll('face',false);eq([filter,draw],[1,1]);eq([EN[0],EN[1],EN[2],EN[3],EN[4]],[false,false,false,false,false]);
    """)
