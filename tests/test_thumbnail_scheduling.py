"""Deterministic ownership/admission tests of the shipped review JavaScript.

Browser primitives are adapters only. Real row geometry and user interactions are
checked with Chromium against the actual Flask page, not this harness.
"""
import json
import shutil
import subprocess

import pytest

from test_review_save_failures import HARNESS, app_js


# Register the shipped page transition listener while evaluating APP_JS. The
# map and tiny DOM below adapt browser primitives only, never reconciliation.
LIFECYCLE_HARNESS = HARNESS.replace(
    'const elements=new Map();', 'const elements=new Map(),windowEvents=new Map();'
).replace('({elements,el,console,', '({elements,el,windowEvents,console,').replace(
    'window:{addEventListener(){}},',
    'window:{addEventListener:(name,fn)=>windowEvents.set(name,fn),'
    'removeEventListener:(name,fn)=>{if(windowEvents.get(name)===fn)windowEvents.delete(name)}},'
)

PRIMITIVES = r"""
const row=(i,enabled=true,category='face',person=-1,track=-1,confidence=.5,zone_dropped=false)=>({
 i,enabled,category,person,track,confidence,zone_dropped,text:'synthetic '+i,t_start:i/10,t_end:2+i/10});
function eq(a,b){if(JSON.stringify(a)!==JSON.stringify(b))throw Error(JSON.stringify(a)+' != '+JSON.stringify(b));}
"""


def run(scenario):
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is needed to evaluate the embedded review JavaScript')
    script = 'const SOURCE=' + json.dumps(app_js()) + ';const SCENARIO=' + json.dumps(PRIMITIVES + scenario) + ';' + LIFECYCLE_HARNESS
    result = subprocess.run([node], input=script, capture_output=True, text=True, timeout=15)
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


def test_scrolling_back_restores_successful_thumbnail_without_second_fetch():
    run(NETWORK + """const s=scheduler(),b=bind(s,1);eligible(s,[1]);
    await headers(tasks[0]);await body(tasks[0],{size:4096,source:'cached'});
    b.img.onload();eq(s.thumbCache.bytes,4096);
    s.retire(b);eq(revoked,['blob:1']);
    bind(s,1);eligible(s,[1]);
    eq(tasks.length,1);eq(created.length,2);
    const returned=s.bindings.get(1);
    if(!returned.img.src||returned.img.src==='blob:1')throw Error('cached remount did not display a fresh local URL');
    returned.img.onload();eq(s.thumbCache.bytes,4096);
    s.retire(returned);bind(s,1);eligible(s,[1]);
    eq(tasks.length,1);
    """)


def test_thumbnail_blob_cache_lru_is_bounded_and_cleared_on_job_exit():
    run(NETWORK + """const s=scheduler(),size=24*1024*1024;
    for(const id of [0,1])s.rememberThumb({id},{size});
    eq(s.thumbCache.bytes,2*size);
    const b=bind(s,0);eligible(s,[0]);eq(tasks.length,0);
    b.img.onload();s.rememberThumb({id:2},{size});
    eq([...s.thumbCache.entries.keys()],[0,2]);
    eq(s.thumbCache.bytes,2*size);
    s.rememberThumb({id:3},{size:70*1024*1024});
    eq(s.thumbCache.entries.has(3),false);
    s.dispose();eq(s.thumbCache.bytes,0);eq(s.thumbCache.entries.size,0);
    eq(revoked,['blob:1']);
    """)


def test_invalid_cached_preview_is_evicted_before_network_retry():
    run(NETWORK + """const s=scheduler(),b=bind(s,4);
    s.rememberThumb(b,{size:4096});eligible(s,[4]);eq(tasks.length,0);
    b.img.onerror();eq(s.thumbCache.entries.has(4),false);
    eq(s.retries.get(4).failures,1);
    advance(600);await tick();eq(tasks.length,1);
    if(!tasks[0].url.includes('r='))throw Error('bad cached image did not recover via network');
    """)


def test_succeeded_thumbnail_clears_retry_budget_before_virtual_remount():
    run(NETWORK + """const s=scheduler(),b=bind(s,1);eligible(s,[1]);
    tasks[0].reject(Error('temporary network failure'));await tick();
    eq(s.retries.get(1).failures,1);
    advance(600);await tick();eq(tasks.length,2);
    if(!tasks[1].url.includes('r='))throw Error('retry did not bypass failed cached request');
    await headers(tasks[1]);await body(tasks[1],{good:true});
    b.img.onload();eq(s.retries.get(1).failures,0);
    eq(s.retries.get(1).readyAt,0);
    s.retire(b);bind(s,1);eligible(s,[1]);eq(tasks.length,3);
    if(tasks[2].url.includes('r='))throw Error('successful preview kept adding retry cache busters');
    """)


def test_pending_generation_retries_slowly_without_spending_error_budget():
    run(NETWORK + """const s=scheduler(),b=bind(s,0);eligible(s,[0]);
    for(let i=0;i<3;i++){
     const t=tasks.at(-1);
     t.resolve({status:409,ok:false,json:async()=>({error:'thumbnail_pending'})});await tick();
     eq(s.retries.get(0).failures,0);eq(s.retries.get(0).pending,i+1);
     const delay=1000*2**i;
     eq([...timers.values()].map(t=>t.ms),[delay]);
     advance(delay);await tick();
    }
    eq(tasks.length,4);
    if(tasks.some(t=>t.url.includes('r=')))throw Error('pending state incorrectly spent failure budget');
    await headers(tasks[3]);await body(tasks[3],{good:true});
    b.img.onload();
    eq(s.retries.get(0).pending,0);eq(s.retries.get(0).failures,0);
    """)


def test_perpetually_pending_thumbnail_expires_bounded_budget():
    run(NETWORK + """const s=scheduler();bind(s,0);eligible(s,[0]);
    for(let i=0;i<6;i++){
     tasks.at(-1).resolve({status:409,ok:false,json:async()=>({error:'thumbnail_pending'})});
     await tick();
     if(i<5){advance(Math.min(8000,1000*2**i));await tick();}
    }
    eq(tasks.length,6);eq(s.retries.get(0).pending,6);
    eq(s.retries.get(0).failures,4);eq(timers.size,0);
    eligible(s,[0]);eq(tasks.length,6);
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


STRUCTURE = r"""
var gridTop=-3000,gridWidth=200;
class PrimitiveNode{
 constructor(type='div'){
  this.type=type;this.children=[];this.style={};this.dataset={};this.isConnected=true;
  this.classList={toggle(){},add(){},remove(){}};
 }
 get clientWidth(){return gridWidth}
 get nextElementSibling(){if(!this.parentElement)return null;const siblings=this.parentElement.children;return siblings[siblings.indexOf(this)+1]||null}
 contains(node){for(let n=node;n;n=n.parentElement)if(n===this)return true;return false}
 insertBefore(node,next){
  if(node===next)return node;
  if(node.parentElement){
   if(node.contains(document.activeElement))document.activeElement=null;
   const siblings=node.parentElement.children;siblings.splice(siblings.indexOf(node),1);
  }
  const index=next?this.children.indexOf(next):this.children.length;
  if(index<0)throw Error('reference node outside parent');
  this.children.splice(index,0,node);node.parentElement=this;node.connect(true);return node;
 }
 appendChild(node){return this.insertBefore(node,null)}
 connect(on){this.isConnected=on;this.children.forEach(n=>n.connect(on))}
 remove(){if(this.parentElement){const siblings=this.parentElement.children;siblings.splice(siblings.indexOf(this),1);this.parentElement=null}this.connect(false)}
 setAttribute(){}removeAttribute(){}addEventListener(){}removeEventListener(){}
 getBoundingClientRect(){const top=this.type==='grid'?gridTop:this.type==='card'?this.parentElement.getBoundingClientRect().top:gridTop+(parseFloat(this.style.top)||0);return{top,bottom:top+260,width:gridWidth,height:260}}
 closest(selector){if(selector==='.det')return this.type==='card'?this:this.parentElement?.closest(selector);return null}
 focus(){document.activeElement=this}
 querySelector(selector){return selector==='img'?this.img:selector==='button'?this.button:null}
 set innerHTML(html){
  const card=new PrimitiveNode('card');card.id='det'+html.match(/id="det(\d+)"/)[1];
  card.img=new PrimitiveNode('img');card.button=new PrimitiveNode('button');
  card.appendChild(card.img);card.appendChild(card.button);this.firstElementChild=card;
 }
}
var grid,root;
getComputedStyle=()=>({gridTemplateColumns:gridWidth===200?'200px':'195px 195px'});
ResizeObserver=class{observe(){}unobserve(){}disconnect(){}};
requestAnimationFrame=()=>1;cancelAnimationFrame=()=>{};
Object.assign(window,{innerHeight:800,scrollY:0,scrollBy(){},scrollTo(){}});
function structure(count=30){
 if(!CUR)openJob('A');
 grid=new PrimitiveNode('grid');root=new PrimitiveNode('root');
 const status=new PrimitiveNode(),prev=new PrimitiveNode(),next=new PrimitiveNode();
 root.querySelector=selector=>selector.startsWith('[data-review-section')?grid:selector==='[data-review-range]'?status:selector==='[data-review-prev]'?prev:selector==='[data-review-next]'?next:null;
 root.appendChild(grid);elements.set('review',root);document.createElement=()=>new PrimitiveNode();
 const sections=reviewDescriptors(Array.from({length:count},(_,n)=>row(n+1)));
 const meta={sections,byId:new Map(sections.flatMap(s=>s.cards.map(c=>[c.id,c])))};
 REVIEW_SCHED=new ReviewScheduler(CUR,VIEW_GEN,root,meta);REVIEW_SCHED.start();return REVIEW_SCHED;
}
function domIds(){return grid.children.filter(n=>n.className==='grid3 reviewrow').flatMap(n=>n.children.map(c=>+c.id.slice(3)))}
function structureCounts(){return{rows:grid.children.filter(n=>n.className==='grid3 reviewrow').length,spacers:grid.children.filter(n=>n.className==='reviewspacer').length,cards:domIds().length}}
"""


def test_upward_rows_and_width_repartition_keep_dom_order_and_focused_control():
    run(STRUCTURE + """ReviewScheduler.prototype.updateQueue=function(){};
    const s=structure();eq(domIds(),[12,13,14,15,16,17]);
    gridTop=-2000;s.layout();eq(domIds(),[8,9,10,11,12,13]);
    const control=s.bindings.get(12).button||s.bindings.get(12).card.button;
    control.focus();gridWidth=400;s.layout();
    eq(domIds(),[...domIds()].sort((a,b)=>a-b));
    if(document.activeElement!==control||!control.isConnected)throw Error('repartition replaced/lost focused control');
    gridWidth=200;s.layout();eq(domIds(),[...domIds()].sort((a,b)=>a-b));
    if(document.activeElement!==control)throw Error('focused row reorder lost focus');
    """)


def test_pagehide_pageshow_releases_all_owned_rows_and_spacers():
    run(STRUCTURE + """ReviewScheduler.prototype.updateQueue=function(){};gridTop=100;structure(1);
    eq(structureCounts(),{rows:1,spacers:2,cards:1});
    for(let n=0;n<3;n++){
     const old=REVIEW_SCHED;windowEvents.get('pagehide')();
     eq(structureCounts(),{rows:0,spacers:0,cards:0});
     eq([old.sections[0].rows.size,old.sections[0].spacers.length,old.bindings.size,old.listeners.length],[0,0,0,0]);
     windowEvents.get('pageshow')();eq(structureCounts(),{rows:1,spacers:2,cards:1});
    }
    """)


def test_back_forward_cache_restores_thumbnail_blobs_without_network():
    run(NETWORK + STRUCTURE + """gridTop=100;const s=structure(1),b=s.bindings.get(1);
    await headers(tasks[0]);await body(tasks[0],{size:2048});
    b.img.onload();eq(s.thumbCache.bytes,2048);
    windowEvents.get('pagehide')();
    eq(s.thumbCache.bytes,2048);
    windowEvents.get('pageshow')();
    const restored=REVIEW_SCHED;
    eq(restored.thumbCache,s.thumbCache);
    eq(tasks.length,1);
    restored.bindings.get(1).img.onload();
    disposeReview();eq(s.thumbCache.entries.size,0);eq(s.thumbCache.bytes,0);
    """)


def test_pagehide_pageshow_preserves_exhausted_view_budget_without_old_bindings():
    run(NETWORK + STRUCTURE + """gridTop=100;const s=structure(1);
    for(const delay of [600,1200,1800]){tasks.at(-1).reject(Error('network'));await tick();advance(delay);await tick();}
    tasks.at(-1).reject(Error('network'));await tick();eq(tasks.length,4);eq(s.retries.get(1).failures,4);
    for(let n=0;n<3;n++){
     const old=REVIEW_SCHED,oldBinding=old.bindings.get(1);windowEvents.get('pagehide')();
     eq(old.retries.get(1).failures,4);eq(old.bindings.size,0);eq(timers.size,0);
     windowEvents.get('pageshow')();eq(REVIEW_SCHED.retries.get(1).failures,4);eq(tasks.length,4);
     if(REVIEW_SCHED.bindings.get(1)===oldBinding)throw Error('old binding retained on restore');
    }
    disposeReview();structure(1);eq(REVIEW_SCHED.retries.get(1).failures,0);eq(tasks.length,5);
    """)


def test_pagehide_pageshow_preserves_retry_deadline_and_recreates_only_live_timer():
    run(NETWORK + STRUCTURE + """gridTop=100;structure(1);tasks[0].reject(Error('network'));await tick();
    const stale=[...timers.values()][0].fn;advance(200);windowEvents.get('pagehide')();eq(timers.size,0);
    windowEvents.get('pageshow')();eq(REVIEW_SCHED.retries.get(1).readyAt,600);eq(timers.size,1);
    stale();eq(tasks.length,1);advance(399);eq(tasks.length,1);advance(1);await tick();eq(tasks.length,2);
    """)


def test_lightbox_failure_survives_virtual_card_remount_and_page_restore():
    structure = STRUCTURE.replace(
        "querySelector(selector){return selector==='img'?this.img:selector==='button'?this.button:null}",
        "querySelector(selector){return selector==='img'?this.img:selector==='button'?this.button:selector==='[data-thumb-reopen]'?this.reopen:null}"
    ).replace(
        "card.img=new PrimitiveNode('img');card.button=new PrimitiveNode('button');",
        "card.img=new PrimitiveNode('img');card.button=new PrimitiveNode('button');card.reopen={hidden:true};"
    )
    run(NETWORK + structure + """gridTop=100;const s=structure(1),first=s.bindings.get(1);
    s.meta.thumbnails={version:'a'.repeat(32),attempted:true,incompatible:new Set()};
    const failed={id:1,source:first,overlay:{},status:{hidden:true},img:{hidden:false}};
    s.previewStatus(failed,true);eq(first.card.reopen.hidden,false);
    s.matching.clear();s.layout();eq(s.bindings.has(1),false);
    s.matching.add(1);s.layout();let current=s.bindings.get(1);
    if(current===first)throw Error('card was not remounted');eq(current.card.reopen.hidden,false);
    windowEvents.get('pagehide')();windowEvents.get('pageshow')();
    current=REVIEW_SCHED.bindings.get(1);eq(current.card.reopen.hidden,false);
    eq(REVIEW_SCHED.meta.thumbnails.attempted,true);
    """)
