"""Thumbnail generation behavior on the composed virtual review scheduler.

The standalone thumbnail owner used eager img URLs, thumbRetry and REVIEW_IMAGES.
The composed scheduler fetches blobs in four shared slots, so its image and
lightbox lifetimes are exercised here through their current owner. Page-level
reopen, labels, editing, and detached saves are exercised separately by the
C01 page and save-owner tests.
"""
import json

import pytest
from test_thumbnail_scheduling import NETWORK, run
from test_review_save_failures import run_js


GENERATION = """
function versioned(s,rows){
 const sections=reviewDescriptors(rows);s.meta.sections=sections;
 s.meta.byId=new Map(sections.flatMap(d=>d.cards.map(c=>[c.id,c])));
 s.meta.thumbnails={version:'a'.repeat(32),rows:new Map(rows.map(x=>[x.i,x.thumbnail_row])),attempted:false,incompatible:new Set()};
}
const hashed=(i,extra={})=>({...row(i),thumbnail_row:String(i).repeat(64),...extra});
"""

LIGHTBOX = """
document.body={appendChild(node){node.isConnected=true;node.img.isConnected=true}};
document.createElement=()=>{
 const img={isConnected:true,hidden:false,removeAttribute(){this.src=''}};
 const status={hidden:true},button={};
 return {img,status,button,style:{},isConnected:true,
  querySelector(q){return q==='img'?img:q==='[data-thumb-status]'?status:button},
  contains(n){return n===img&&this.isConnected},remove(){this.isConnected=false;img.isConnected=false}};
};
function card(s,id){const b=bind(s,id);b.reopen={hidden:true};b.card.querySelector=()=>b.reopen;return b;}
"""


def test_legacy_unversioned_url_and_toggle_do_not_trigger_recovery():
    run(NETWORK + """
    const s=scheduler(),b=bind(s,0);eligible(s,[0]);
    if(tasks[0].url.includes('v='))throw Error('legacy request included a version');
    EN[0]=true;applyDet(0,false);eq(EN[0],false);eq(tasks.length,1);
    tasks[0].reject(Error('network'));await tick();
    for(const delay of [600,1200,1800]){advance(delay);tasks.at(-1).reject(Error('network'));await tick();}
    eq(tasks.filter(t=>t.url.endsWith('/detections')).length,0);
    """)


@pytest.mark.parametrize('failure', ['http', 'same', 'malformed', 'network'])
def test_failed_recovery_spends_budget_and_keeps_old_generation(failure):
    run(NETWORK + GENERATION + """
    const s=scheduler(),rows=[hashed(0)];versioned(s,rows);bind(s,0);eligible(s,[0]);
    tasks[0].resolve({ok:false,status:409,json:async()=>({error:'thumbnail_obsolete'})});await tick();
    const meta=tasks[1];
    if(FAIL==='network')meta.reject(Error('offline'));
    else if(FAIL==='http')meta.resolve({ok:false,status:404});
    else if(FAIL==='same')meta.resolve({ok:true,json:async()=>({duration:10,detections:rows,thumbnail_version:'a'.repeat(32)})});
    else meta.resolve({ok:true,json:async()=>({thumbnail_version:'invalid'})});
    await tick();s.recoverThumbnails();await tick();
    eq(tasks.length,2);eq(s.meta.thumbnails.attempted,true);eq(s.meta.thumbnails.version,'a'.repeat(32));
    eq(s.retries.get(0).failures,4);
    """.replace('FAIL', json.dumps(failure)))


def test_replaced_lightbox_cannot_be_mutated_by_old_response():
    run(NETWORK + GENERATION + LIGHTBOX + """
    const s=scheduler(),rows=[hashed(0),hashed(1)];versioned(s,rows);
    const a=card(s,0),b=card(s,1);eligible(s,[0,1]);
    s.openLightbox(0);const old=s.lightbox,oldTask=tasks[2];
    s.openLightbox(1);const current=s.lightbox,currentTask=tasks[3];
    if(!oldTask.options.signal.aborted||old.overlay.isConnected)throw Error('old lightbox not retired');
    await headers(oldTask);await body(oldTask);eq(created.length,0);
    await headers(currentTask);await body(currentTask);eq(created.length,1);
    if(s.lightbox!==current||!current.overlay.isConnected||!current.img.src)throw Error('replacement lost');
    s.dispose();eq(current.overlay.isConnected,false);eq(revoked,['blob:1']);
    """)


def test_lightbox_failure_survives_card_success_until_new_lightbox_succeeds():
    run(NETWORK + GENERATION + LIGHTBOX + """
    const s=scheduler(),rows=[hashed(0)];versioned(s,rows);const a=card(s,0);eligible(s,[0]);
    s.openLightbox(0);const first=s.lightbox;
    tasks[1].resolve({ok:false,status:409,json:async()=>({error:'thumbnail_obsolete'})});await tick();
    tasks[2].resolve({ok:false,status:503});await tick();
    eq(a.reopen.hidden,false);s.closeLightbox();
    await headers(tasks[0]);await body(tasks[0]);eq(a.reopen.hidden,false);
    s.openLightbox(0);const second=s.lightbox;
    await headers(tasks[3]);await body(tasks[3]);second.img.onload();
    eq(a.reopen.hidden,true);eq(second.status.hidden,true);
    """)


def test_competing_review_loads_publish_only_newest():
    run_js("""openJob('A');const first=loadReview(),second=loadReview();
    const row=i=>({i,enabled:true,category:'name',t_start:0,t_end:1});
    const newer=queue.splice(1,1)[0];newer.resolve(response({duration:10,detections:[row(1)]}));await tick();await second;
    const owner=REVIEW_SCHED,meta=REVIEW_META;await reply({duration:10,detections:[row(0)]});await first;
    if(REVIEW_SCHED!==owner||REVIEW_META!==meta||!meta.byId.has(1)||meta.byId.has(0))throw Error('older review replaced newest');
    """)


def test_held_save_and_newer_drafts_survive_failed_reopen():
    run_js("""setup();const editor=BE,draft=EDITS,manual=MAN,audio=BE.audio;
    const save=saveAndRender();applyDet(0,true);MAN.push({manual_id:'newer'});BE.audio.push({t0:2,t1:3,mode:'mute'});
    const reopen=loadReview(),req=queue.splice(1,1)[0];req.resolve(response({error:'busy'},503));await tick();await reopen;
    await reply({ok:true});await save;
    if(BE!==editor||EDITS!==draft||MAN!==manual||BE.audio!==audio||MAN.at(-1).manual_id!=='newer'||BE.audio.length!==2||!EN[0])throw Error('newer draft lost');
    if(calls.some(c=>c.url.endsWith('/render')))throw Error('newer draft rendered');
    """)


def test_failed_reopen_keeps_loaded_lightbox_and_recovery_budget():
    run(NETWORK + GENERATION + LIGHTBOX + """
    const s=scheduler(),rows=[hashed(0)];versioned(s,rows);card(s,0);eligible(s,[0]);
    s.openLightbox(0);await headers(tasks[1]);await body(tasks[1]);
    const light=s.lightbox,draft=EDITS,editor=BE;s.meta.thumbnails.attempted=true;
    const create=document.createElement;
    document.createElement=tag=>{const n=create(tag);n.appendChild=()=>{};n.setAttribute=()=>{};n.dataset={};return n};
    detail.appendChild=()=>{};
    const reopen=loadReview();tasks[2].resolve({ok:false,status:503});await tick();await reopen;
    if(REVIEW_SCHED!==s||s.lightbox!==light||!light.overlay.isConnected||!light.img.src)throw Error('failed reopen retired live lightbox');
    eq(s.meta.thumbnails.attempted,true);if(EDITS!==draft||BE!==editor)throw Error('draft owner changed');
    """)


def test_successful_lightbox_does_not_clear_exhausted_card_failure():
    run(NETWORK + GENERATION + LIGHTBOX + """
    const s=scheduler(),rows=[hashed(0)];versioned(s,rows);const a=card(s,0);eligible(s,[0]);
    tasks[0].resolve({ok:false,status:409,json:async()=>({error:'thumbnail_obsolete'})});await tick();
    tasks[1].resolve({ok:false,status:503});await tick();eq(a.reopen.hidden,false);
    s.openLightbox(0);await headers(tasks[2]);await body(tasks[2]);
    eq(a.reopen.hidden,false);eq(s.lightbox.status.hidden,true);
    """)


def test_overlay_retry_keeps_failed_lightbox_until_review_replacement_succeeds():
    run(NETWORK + GENERATION + LIGHTBOX + """
    const s=scheduler(),rows=[hashed(0)];versioned(s,rows);card(s,0);eligible(s,[0]);s.openLightbox(0);
    const light=s.lightbox;tasks[1].resolve({ok:false,status:409,json:async()=>({error:'thumbnail_obsolete'})});await tick();
    tasks[2].resolve({ok:false,status:503});await tick();
    const create=document.createElement;document.createElement=tag=>{const n=create(tag);n.appendChild=()=>{};n.setAttribute=()=>{};n.dataset={};return n};detail.appendChild=()=>{};
    light.overlay.button.onclick({stopPropagation(){}});
    if(s.lightbox!==light||!light.overlay.isConnected)throw Error('retry removed existing lightbox before replacement');
    tasks[3].resolve({ok:false,status:503});await tick();
    if(s.lightbox!==light||!light.overlay.isConnected||light.status.hidden)throw Error('failed retry lost lightbox');
    """)


def test_closed_failed_lightbox_survives_card_only_generation_recovery():
    run(NETWORK + GENERATION + LIGHTBOX + """
    const s=scheduler(),rows=[hashed(0)];versioned(s,rows);const a=card(s,0);eligible(s,[0]);s.openLightbox(0);
    tasks[1].resolve({ok:false,status:409,json:async()=>({error:'thumbnail_obsolete'})});await tick();
    s.closeLightbox();eq(a.reopen.hidden,false);
    tasks[2].resolve({ok:true,json:async()=>({duration:10,detections:rows,thumbnail_version:'b'.repeat(32)})});await tick();
    tasks[0].reject(Error('aborted'));await tick();const replacement=tasks.find(t=>t.url.includes('/thumb/0')&&t.url.includes('v='+('b'.repeat(32))));
    await headers(replacement);await body(replacement);if(a.img.onload)a.img.onload();
    eq(a.reopen.hidden,false);eq(a.lightFailed,true);
    """)


def test_lightbox_failure_clears_only_after_current_image_decodes():
    run(NETWORK + GENERATION + LIGHTBOX + """
    const s=scheduler(),rows=[hashed(0)];versioned(s,rows);const a=card(s,0);eligible(s,[0]);
    s.openLightbox(0);tasks[1].resolve({ok:false,status:409,json:async()=>({error:'thumbnail_obsolete'})});await tick();
    tasks[2].resolve({ok:false,status:503});await tick();s.closeLightbox();s.openLightbox(0);
    const replacement=s.lightbox;await headers(tasks[3]);await body(tasks[3]);eq(a.reopen.hidden,false);
    replacement.img.onload();eq(a.reopen.hidden,true);
    """)
