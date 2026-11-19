"""Exercise the shipped review JavaScript and its image ownership protocol."""
import ast
import json
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


def app_js():
    tree = ast.parse((ROOT / 'openscrub_web.py').read_text())
    return next(ast.literal_eval(n.value) for n in tree.body
                if isinstance(n, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == 'APP_JS' for t in n.targets))


HARNESS = r'''
const vm=require('node:vm'),assert=require('node:assert/strict');
const elements=new Map();
function element(id='') {return {id, textContent:'', innerHTML:'', style:{},dataset:{},
 disabled:false,isConnected:true, classList:{toggle(){},remove(){}},
 remove(){this.isConnected=false;if(this.child)this.child.isConnected=false; if(elements.get(this.id)===this)elements.delete(this.id)},
 addEventListener(){},querySelector(selector){if(selector==='img'&&this.id==='lb'){if(!this.child){this.child=element();this.child.root=this;}return this.child;}return null},querySelectorAll(){return []},
 contains(node){return node.isConnected && node.root===this},setAttribute(k,v){this[k]=String(v)},
 removeAttribute(k){delete this[k]}};}
const detail=element('detail'); elements.set('detail',detail);
detail.insertAdjacentHTML=function(_,html){
 const old=elements.get('review');if(old)old.remove();
 const root=element('review');elements.set('review',root);root.root=root;
 for(const match of html.matchAll(/<div class="det [\s\S]*?id="det(\d+)"[\s\S]*?<img ([\s\S]*?)>/g)){
  const i=+match[1], attrs=match[2], img=element('img'+i); img.root=root;
  const src=attrs.match(/src="([^"]*)"/);img.src=src?src[1]:'';
  img.dataset.thumbIndex=String(i);img.onerror=()=>vm.runInContext('thumbRetry(elements.get(\"img'+i+'\"))',ctx);const button=element('reopen'+i),status=element('status'+i);button.hidden=true;status.hidden=true;const parent={querySelector:s=>s==='[data-thumb-reopen]'?button:s==='[data-thumb-status]'?status:img};elements.set('status'+i,status);button.parentElement=parent;img.parentElement=parent;elements.set('reopen'+i,button);elements.set('img'+i,img);elements.set('thumb'+i,img);
 }
};
for(const id of ['beslot','reviewSaveStatus'])elements.set(id,element(id));
const document={getElementById:id=>elements.get(id)||null,querySelector:s=>elements.get(s.slice(1))||null,
 querySelectorAll:()=>[],addEventListener(){},createElement:()=>element(),body:{appendChild(node){elements.set(node.id,node)}}};
const ctx=vm.createContext({elements,console,assert,Set,Map,JSON,Date,Math,Promise,URL,
 location:{href:'http://localhost/'},document,detail,window:{location:{href:'http://localhost/'}},
 setInterval:()=>1,clearInterval(){},setTimeout(){},confirm:()=>false,alert(){},
 crypto:require('node:crypto').webcrypto,fetch:async()=>({ok:true,json:async()=>({})})});
vm.runInContext(SOURCE.slice(0,SOURCE.indexOf('loadPersist();loadCertInfo();loadJobs();setInterval(loadJobs,5000);')).replace(/^refreshModelPanel\(\);renderTiers\(\);$/m,''),ctx);
vm.runInContext(`
refresh=()=>{};loadJobs=()=>{};initMarquee=()=>{};
var calls=[],queue=[];
fetch=(url,options={})=>{calls.push({url:String(url),options});return new Promise((resolve,reject)=>queue.push({resolve,reject}));};
function response(body,status=200){return {ok:status>=200&&status<300,status,json:async()=>body};}
async function tick(){for(let i=0;i<20;i++)await Promise.resolve();}
async function reply(body,status=200){queue.shift().resolve(response(body,status));await tick();}
function row(i,extra={}) {return {i,category:'name',text:'row'+i,t_start:i,t_end:i+1,enabled:true,track:-1,person:-1,confidence:0,thumbnail_row:String(i).padStart(64,'0'),...extra};}
function metadata(rows,version='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'){return {duration:10,detections:rows,thumbnail_version:version};}
async function mount(rows){openJob('A');const p=loadReview();await reply(metadata(rows));await p;return elements.get('review');}
`,ctx);
async function run(script){return vm.runInContext('(async()=>{'+script+'})()',ctx)}
const watchdog=setTimeout(()=>{console.error('scenario left pending');process.exit(1)},3000);
(async()=>{await run(SCENARIO);clearTimeout(watchdog)})().catch(e=>{console.error(e);process.exit(1)});
'''


def run_js(scenario):
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is needed to evaluate the shipped JavaScript')
    script = 'const SOURCE=' + json.dumps(app_js()) + ';const SCENARIO=' + json.dumps(scenario) + ';' + HARNESS
    result = subprocess.run([node, '-e', script], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr


def test_thumbnail_browser_one_refresh_per_mount():
    run_js("""await mount([row(0),row(1)]);
    const a=elements.get('img0'),b=elements.get('img1');
    assert.match(a.src,/\\?v=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa$/,'initial image must bind generation');
    thumbRetry(a);thumbRetry(b);await tick();
    assert.equal(calls.length,2,'parallel errors share one metadata request');
    assert.equal(calls[1].options.cache,'no-store');
    await reply(metadata([row(0),row(1)],'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'));
    assert.match(a.src,/\\?v=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb$/);
    thumbRetry(a);await tick();assert.equal(calls.length,2,'patched failure must not retry');
    """)


def test_thumbnail_browser_patches_only_equal_raw_index_and_complete_group():
    run_js("""const a=row(0,{track:7,confidence:0.9}),b=row(1,{track:7}),c=row(2);
    await mount([a,b,c]);const group=elements.get('img0'),single=elements.get('img2');
    thumbRetry(group);await tick();
    await reply(metadata([a,b,c,row(3,{track:7})],'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'));
    assert.match(group.src,/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa$/,'added group member must prevent patch');
    assert.match(group.alt,/reopen review/);
    assert.match(single.src,/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb$/,'unchanged singleton can patch');
    """)


def test_thumbnail_browser_changed_raw_rows_do_not_patch():
    run_js("""const a=row(0),b=row(1);await mount([a,b]);const one=elements.get('img0'),two=elements.get('img1');
    thumbRetry(two);await tick();await reply(metadata([{...a,thumbnail_row:'f'.repeat(64),enabled:false},b], 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'));
    assert.match(one.src,/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa$/);assert.match(one.alt,/reopen review/);
    assert.equal(one.style.visibility,'hidden','unequal loaded image must be unavailable');assert.equal(elements.get('status0').hidden,false);
    assert.match(two.src,/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb$/);
    assert.equal(two.style.visibility,'hidden');const loaded=two.onload;two.currentSrc=two.src;two.complete=true;two.naturalWidth=20;loaded();
    assert.equal(two.style.visibility,'');
    """)


def test_thumbnail_browser_late_result_and_draft_ownership():
    run_js("""await mount([row(0)]);const old=elements.get('img0'),editor=BE,draft=EDITS,en=EN,manual=MAN,root=elements.get('review');
    BE.sel=3;BE.playing=true;BE.audio=[{t0:1}];BE.audioSaved=[];BE.audioLoaded=true;BE.audioInFlight=true;MAN.push({manual_id:'new'});
    const audio=BE.audio;thumbRetry(old);await tick();openJob('B');openJob('A');
    await reply(metadata([row(0)],'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'));
    assert.match(old.src,/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa$/,'old callback must not patch on A-B-A');
    assert.equal(REVIEW_DRAFTS.get('A'),draft);assert.equal(draft.editor,editor);
    assert.equal(editor.audio,audio);assert.equal(manual[0].manual_id,'new');
    """)


def test_thumbnail_local_enabled_toggle_does_not_fetch_or_spend_budget():
    run_js("""await mount([row(0)]);const owner=REVIEW_IMAGES;toggleDet(0);
    assert.equal(calls.length,1);assert.equal(owner.attempted,false);
    """)


def test_thumbnail_lightbox_shares_recovery_and_current_version():
    run_js(r"""await mount([row(0)]);zoomDet(0);const o=REVIEW_IMAGES,light=o.lightbox;
    assert.match(light.node.src,/detframe\/0\?v=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa$/);
    light.node.onerror();await tick();await reply(metadata([row(0)],'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'));
    assert.match(light.node.src,/detframe\/0\?v=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb$/);
    assert.match(elements.get('img0').src,/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb$/);
    """)


def test_thumbnail_legacy_metadata_uses_unversioned_image_without_retry():
    run_js("""openJob('A');const p=loadReview();const data=metadata([row(0)]);delete data.thumbnail_version;await reply(data);await p;
    const image=elements.get('img0');assert.equal(image.src,'api/jobs/A/thumb/0');thumbRetry(image);await tick();
    assert.equal(calls.length,1);assert.equal(REVIEW_IMAGES.attempted,false);
    """)


@pytest.mark.parametrize('failure', ['404', 'same', 'malformed', 'network'])
def test_thumbnail_failed_recovery_spends_budget(failure):
    run_js("""await mount([row(0)]);const image=elements.get('img0');thumbRetry(image);await tick();
    if(FAIL==='network'){queue.shift().reject(Error('offline'));await tick();}
    else if(FAIL==='404')await reply({error:'pending'},404);
    else if(FAIL==='same')await reply(metadata([row(0)]));
    else await reply({thumbnail_version:'bad'});
    thumbRetry(image);await tick();assert.equal(calls.length,2);assert.match(image.alt,/reopen review/);
    """.replace('FAIL',json.dumps(failure)))


def test_thumbnail_own_enabled_save_retains_newer_drafts_and_refuses_changed_row():
    run_js("""await mount([row(0),row(1)]);const o=REVIEW_IMAGES,image=elements.get('img0'),other=elements.get('img1');
    toggleDet(0);BE.audio=[{t0:1,t1:2,mode:'mute'}];BE.audioLoaded=true;
    const draft=EDITS,editor=BE,audio=BE.audio;const save=saveAndRender();
    toggleDet(0);BE.ov[0]=[1,2,3,4];MAN.push({manual_id:'newer'});BE.audio.push({t0:2,t1:3,mode:'bleep'});
    thumbRetry(image);await tick();assert.equal(calls.length,3);
    const metadataRequest=queue.splice(1,1)[0];metadataRequest.resolve(response(metadata([
     {...row(0),enabled:false,thumbnail_row:'f'.repeat(64)},row(1)],'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb')));await tick();
    assert.match(image.src,/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa$/);assert.match(image.alt,/reopen review/);
    assert.match(other.src,/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb$/);
    await reply({ok:true,total:2});await save;
    assert.equal(EDITS,draft);assert.equal(BE,editor);assert.equal(BE.audio,audio);
    assert.equal(BE.audio.length,2);assert.equal(MAN[0].manual_id,'newer');assert.deepEqual(BE.ov[0],[1,2,3,4]);
    assert.equal(EN[0],true);assert.equal(o.attempted,true);assert.equal(calls.length,3);
    """)


def test_thumbnail_same_job_remount_and_disconnected_image_reject_late_reply():
    run_js("""await mount([row(0)]);const old=elements.get('img0');thumbRetry(old);await tick();
    const mounting=loadReview();await reply(metadata([row(0)],'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'));
    await reply(metadata([row(0)],'cccccccccccccccccccccccccccccccc'));await mounting;
    assert.match(old.src,/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb$/,'still-mounted owner remains active until replacement succeeds');assert.match(elements.get('img0').src,/cccccccccccccccccccccccccccccccc$/);
    const current=elements.get('img0');thumbRetry(current);await tick();current.isConnected=false;
    await reply(metadata([row(0)],'dddddddddddddddddddddddddddddddd'));assert.match(current.src,/cccccccccccccccccccccccccccccccc$/);
    """)


def test_thumbnail_new_review_gets_new_budget_after_failure():
    run_js("""await mount([row(0)]);thumbRetry(elements.get('img0'));await reply({error:'busy'},409);
    const p=loadReview();await reply(metadata([row(0)]));await p;
    assert.equal(REVIEW_IMAGES.attempted,false);thumbRetry(elements.get('img0'));await tick();assert.equal(calls.length,4);
    await reply({error:'busy'},409);
    """)


def test_thumbnail_explicit_reopen_preserves_pending_draft_and_gets_new_budget():
    run_js("""await mount([row(0)]);const image=elements.get('img0'),button=elements.get('reopen0');
    const editor=BE,draft=EDITS,manual=MAN;BE.ov[0]=[1,2,3,4];MAN.push({manual_id:'pending'});
    BE.audio=[{t0:1,t1:2,mode:'mute'}];BE.audioLoaded=true;const audio=BE.audio;
    thumbRetry(image);await reply({error:'busy'},409);assert.equal(button.hidden,false);
    reopenThumbnailReview({currentTarget:button,stopPropagation(){}});await tick();
    assert.equal(calls.length,3);await reply(metadata([row(0)],'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'));
    assert.equal(REVIEW_IMAGES.attempted,false);assert.equal(BE,editor);assert.equal(EDITS,draft);
    assert.equal(MAN,manual);assert.equal(MAN[0].manual_id,'pending');assert.equal(BE.audio,audio);
    assert.deepEqual(BE.ov[0],[1,2,3,4]);
    """)


def test_thumbnail_reopen_during_lost_save_ack_keeps_newer_drafts():
    run_js("""await mount([row(0)]);toggleDet(0);BE.audio=[{t0:1,t1:2,mode:'mute'}];BE.audioLoaded=true;
    const editor=BE,draft=EDITS,manual=MAN,audio=BE.audio;const save=saveAndRender();
    toggleDet(0);BE.ov[0]=[4,3,2,1];MAN.push({manual_id:'newer'});BE.audio.push({t0:2,t1:3,mode:'bleep'});
    const image=elements.get('img0'),button=elements.get('reopen0');thumbRetry(image);
    const meta=queue.splice(1,1)[0];meta.resolve(response({error:'pending'},409));await tick();
    reopenThumbnailReview({currentTarget:button,stopPropagation(){}});const mountRequest=queue.splice(1,1)[0];
    mountRequest.resolve(response(metadata([row(0)])));await tick();
    queue.shift().reject(Error('lost acknowledgement'));await tick();await save;
    assert.equal(BE,editor);assert.equal(EDITS,draft);assert.equal(MAN,manual);assert.equal(BE.audio,audio);
    assert.equal(BE.audioSaved,null);assert.equal(BE.audio.length,2);assert.equal(EN[0],true);
    assert.equal(MAN[0].manual_id,'newer');assert.deepEqual(BE.ov[0],[4,3,2,1]);assert.equal(REVIEW_IMAGES.attempted,false);
    assert.equal(calls.filter(c=>c.url.endsWith('/render')).length,0);
    """)


def test_thumbnail_late_load_cannot_reveal_disconnected_image():
    run_js("""await mount([row(0)]);const image=elements.get('img0');thumbRetry(image);
    await reply(metadata([row(0)],'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'));const load=image.onload;
    image.currentSrc=image.src;image.complete=true;image.naturalWidth=20;openJob('B');openJob('A');
    load();assert.equal(image.style.visibility,'hidden');
    """)


@pytest.mark.parametrize('error_order', ['before', 'after'])
def test_thumbnail_replacement_lightbox_error_survives_card_refresh(error_order):
    run_js("""await mount([row(0),row(1)]);const o=REVIEW_IMAGES;
    const editor=BE,draft=EDITS,manual=MAN,audio=BE.audio,review=elements.get('review');
    zoomDet(0);const old=o.lightbox,oldError=old.node.onerror;oldError();await tick();
    assert.equal(calls.length,2);assert.equal(calls[1].options.cache,'no-store');
    old.overlay.remove();zoomDet(1);const replacement=o.lightbox;
    assert.notEqual(replacement.node,old.node);const replacementSrc=replacement.node.src;
    if(ORDER==='before')replacement.node.onerror();
    await reply(metadata([row(0),row(1)],'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'));
    const card=replacement.card.node;assert.match(card.src,/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb$/);
    card.currentSrc=card.src;card.complete=true;card.naturalWidth=20;card.onload();
    if(ORDER==='after')replacement.node.onerror();
    oldError();await tick();
    assert.equal(replacement.node.src,replacementSrc,'late response must not rebind replacement');
    assert.equal(replacement.node.style.visibility,'hidden','actual failed replacement is unavailable');
    assert.equal(elements.get('reopen1').hidden,false,'card load cannot hide lightbox failure');
    assert.equal(elements.get('status1').hidden,false);assert.equal(calls.length,2);
    assert.equal(BE,editor);assert.equal(EDITS,draft);assert.equal(MAN,manual);assert.equal(BE.audio,audio);
    assert.equal(elements.get('review'),review);
    """.replace('ORDER',json.dumps(error_order)))


def test_thumbnail_replaced_captured_card_rejects_pending_result():
    run_js("""await mount([row(0),row(1)]);const o=REVIEW_IMAGES,old=elements.get('img0');
    const editor=BE,draft=EDITS,manual=MAN,audio=BE.audio,review=elements.get('review');
    thumbRetry(old);await tick();old.isConnected=false;
    const replacement={...old,isConnected:true,style:{visibility:'visible'},src:'data:image/gif;base64,replacement'};
    elements.set('img0',replacement);elements.set('thumb0',replacement);
    await reply(metadata([row(0),row(1)],'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'));
    thumbRetry(old);await tick();
    assert.equal(replacement.src,'data:image/gif;base64,replacement');assert.equal(replacement.style.visibility,'visible');
    assert.match(elements.get('img1').src,/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb$/);assert.equal(calls.length,2);
    assert.equal(BE,editor);assert.equal(EDITS,draft);assert.equal(MAN,manual);assert.equal(BE.audio,audio);
    assert.equal(elements.get('review'),review);
    """)


def test_thumbnail_closing_failed_lightbox_keeps_reopen_action():
    run_js("""await mount([row(0)]);zoomDet(0);const light=REVIEW_IMAGES.lightbox;
    light.node.onerror();await reply({error:'unavailable'},409);
    assert.equal(elements.get('reopen0').hidden,false);light.overlay.onclick();
    assert.equal(elements.get('reopen0').hidden,false,'closing failed lightbox must retain reopen action');
    assert.equal(elements.get('status0').hidden,false);assert.equal(calls.length,2);
    """)


def test_thumbnail_new_lightbox_success_clears_closed_lightbox_status():
    run_js("""await mount([row(0)]);zoomDet(0);const first=REVIEW_IMAGES.lightbox;
    first.node.onerror();await reply({error:'unavailable'},409);first.overlay.onclick();
    zoomDet(0);const second=REVIEW_IMAGES.lightbox;
    assert.equal(elements.get('status0').hidden,false,'unresolved failure stays visible');
    second.node.currentSrc=second.node.src;second.node.complete=true;second.node.naturalWidth=20;second.node.onload();
    assert.equal(elements.get('status0').hidden,true,'current successful replacement resolves lightbox status');
    assert.equal(elements.get('reopen0').hidden,true);assert.equal(calls.length,2);
    """)


def test_thumbnail_new_lightbox_failure_preserves_closed_lightbox_status():
    run_js("""await mount([row(0)]);zoomDet(0);const first=REVIEW_IMAGES.lightbox;
    first.node.onerror();await reply({error:'unavailable'},409);first.overlay.onclick();
    zoomDet(0);const second=REVIEW_IMAGES.lightbox;second.node.onerror();await tick();
    assert.equal(second.node.style.visibility,'hidden');assert.equal(elements.get('status0').hidden,false);
    assert.equal(elements.get('reopen0').hidden,false);assert.equal(calls.length,2);
    """)


@pytest.mark.parametrize('failure', ['network', '409', '503'])
def test_fix1_failed_reopen_keeps_group_owner_and_allows_retry(failure):
    run_js("""const rows=[row(0,{track:7,confidence:.9}),row(1,{track:7})];await mount(rows);
    const owner=REVIEW_IMAGES,root=elements.get('review'),editor=BE,draft=EDITS,manual=MAN,audio=BE.audio,groups=TRKMEM;
    BE.ov[0]=[1,2,3,4];MAN.push({manual_id:'pending'});EDITS.audioInFlight=true;BE.audioSaved=null;
    const p=loadReview();if(FAIL==='network')queue.shift().reject(Error('offline'));else await reply({error:'pending'},+FAIL);
    await p;assert.equal(REVIEW_IMAGES,owner,'failed reopen must keep owner');
    assert.equal(elements.get('review'),root);assert.equal(TRKMEM,groups);toggleDet(0);
    assert.equal(EN[0],false);assert.equal(EN[1],false,'group toggle keeps every member');
    assert.equal(BE,editor);assert.equal(EDITS,draft);assert.equal(MAN,manual);assert.equal(BE.audio,audio);
    assert.equal(BE.audioSaved,null);assert.equal(EDITS.audioInFlight,true);
    const q=loadReview();await reply(metadata(rows,'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'));await q;
    assert.notEqual(REVIEW_IMAGES,owner);assert.equal(REVIEW_IMAGES.attempted,false);
    """.replace('FAIL',json.dumps(failure)))


def test_fix1_initial_callbacks_cannot_hide_new_version():
    run_js("""await mount([row(0)]);const card=elements.get('img0'),oldCard=card.onerror;
    zoomDet(0);const light=REVIEW_IMAGES.lightbox,oldLight=light.node.onerror;oldLight();
    await reply(metadata([row(0)],'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'));
    for(const node of [card,light.node]){node.currentSrc=node.src;node.complete=true;node.naturalWidth=20;node.onload();}
    oldCard();oldLight();await tick();assert.equal(card.style.visibility,'');assert.equal(light.node.style.visibility,'');
    assert.equal(elements.get('reopen0').hidden,true);assert.equal(calls.length,2);
    """)


def test_fix1_late_card_load_cannot_clear_closed_lightbox_failure():
    run_js("""await mount([row(0),row(1)]);zoomDet(0);const old=REVIEW_IMAGES.lightbox;old.node.onerror();
    old.overlay.remove();zoomDet(1);const light=REVIEW_IMAGES.lightbox;light.node.onerror();
    await reply(metadata([row(0),row(1)],'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'));
    const card=light.card.node;light.overlay.onclick();assert.equal(elements.get('reopen1').hidden,false);
    card.currentSrc=card.src;card.complete=true;card.naturalWidth=20;card.onload();
    assert.equal(elements.get('reopen1').hidden,false,'card load cannot clear closed lightbox latch');
    zoomDet(1);const replacement=REVIEW_IMAGES.lightbox;replacement.node.currentSrc=replacement.node.src;
    replacement.node.complete=true;replacement.node.naturalWidth=20;replacement.node.onload();
    assert.equal(elements.get('reopen1').hidden,true);
    """)


@pytest.mark.parametrize('exit_kind',['job','panel'])
def test_fix1_teardown_retires_owner_before_stale_metadata(exit_kind):
    run_js("""await mount([row(0)]);const owner=REVIEW_IMAGES,image=elements.get('img0');thumbRetry(image);await tick();
    if(KIND==='job')openJob('B');else showPanel('compare');const current=REVIEW_IMAGES;let parsed=0;
    queue.shift().resolve({ok:true,status:200,json:async()=>{parsed++;return metadata([row(0)],'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb')}});
    await owner.refresh;assert.equal(current,null,'detached review must release global owner');
    assert.equal(parsed,0,'obsolete response must stop before parsing/indexing');
    assert.equal(owner.version,'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa');
    """.replace('KIND',json.dumps(exit_kind)))


def test_fix1_competing_review_mounts_only_publish_latest():
    run_js("""await mount([row(0)]);const first=loadReview(),second=loadReview();
    const newer=queue.splice(1,1)[0];newer.resolve(response(metadata([row(1)],'cccccccccccccccccccccccccccccccc')));await tick();await second;
    const owner=REVIEW_IMAGES,root=elements.get('review');await reply(metadata([row(0)],'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'));await first;
    assert.equal(REVIEW_IMAGES,owner);assert.equal(elements.get('review'),root);
    assert.match(elements.get('img1').src,/cccccccccccccccccccccccccccccccc$/);
    """)


def test_fix2_failed_reopen_keeps_exact_loaded_lightbox():
    run_js("""await mount([row(0)]);zoomDet(0);const owner=REVIEW_IMAGES,light=owner.lightbox,root=elements.get('review');
    const editor=BE,draft=EDITS,p=loadReview();await reply({error:'pending'},409);await p;
    assert.equal(REVIEW_IMAGES,owner);assert.equal(elements.get('review'),root);assert.equal(elements.get('lb'),light.overlay);
    assert.equal(light.overlay.isConnected,true);assert.equal(light.node.isConnected,true);assert.equal(BE,editor);assert.equal(EDITS,draft);
    """)


@pytest.mark.parametrize('exit_kind',['job','panel','replacement'])
def test_fix2_retirement_disconnects_only_owned_lightbox(exit_kind):
    run_js("""await mount([row(0)]);zoomDet(0);const owner=REVIEW_IMAGES,light=owner.lightbox;
    const oldError=light.node.onerror,oldLoad=light.node.onload;light.node.currentSrc=light.node.src;light.node.complete=true;light.node.naturalWidth=20;oldLoad();
    if(KIND==='job'){openJob('B');assert.equal(light.overlay.isConnected,false);openJob('A');}
    if(KIND==='panel'){showPanel('compare');assert.equal(light.overlay.isConnected,false);}
    if(KIND==='replacement'){const p=loadReview();await reply(metadata([row(0)],'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'));await p;}
    else {const p=loadReview();await reply(metadata([row(0)]));await p;}
    assert.equal(light.overlay.isConnected,false,'retired owned overlay must be removed');
    assert.equal(light.node.isConnected,false);zoomDet(0);const current=REVIEW_IMAGES.lightbox,src=current.node.src;
    MAN.push({manual_id:'current'});const editor=BE,draft=EDITS,manual=MAN;oldError();oldLoad();await tick();
    assert.notEqual(current.overlay,light.overlay);assert.equal(current.overlay.isConnected,true);assert.equal(current.node.src,src);
    assert.equal(BE,editor);assert.equal(EDITS,draft);assert.equal(MAN,manual);assert.equal(MAN[0].manual_id,'current');
    """.replace('KIND',json.dumps(exit_kind)))
