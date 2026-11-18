"""Exercise the evaluated, shipped review JavaScript with deferred HTTP responses.

Node is optional for Python-only installations; no npm dependency is required.
"""
import ast
import json
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


def app_js():
    tree = ast.parse((ROOT / "openscrub_web.py").read_text())
    return next(ast.literal_eval(n.value) for n in tree.body
                if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "APP_JS" for t in n.targets))


HARNESS = r"""
const vm=require('node:vm'),assert=require('node:assert/strict');
const elements=new Map();
function el(){return {textContent:'',innerHTML:'',style:{},dataset:{},disabled:false,
 classList:{toggle(){},remove(){}},remove(){this.removed=true},
 addEventListener(){},querySelector(){return null},insertAdjacentHTML(){}}}
for(const id of ['detail','beslot','review','reviewSaveStatus'])elements.set(id,el());
const ctx=vm.createContext({elements,el,console,assert,Set,Map,JSON,Date,Math,Promise,crypto:require("node:crypto").webcrypto,
 ResizeObserver:class {observe(){} disconnect(){}},
 document:{getElementById:id=>elements.get(id)||null,querySelector:s=>elements.get(s.slice(1))||null,
 querySelectorAll:()=>[],addEventListener(){},createElement:el},
 detail:elements.get('detail'),window:{},setInterval:()=>1,clearInterval(){},setTimeout(){},
 confirm:()=>false,alert(){},fetch:async()=>({ok:true,json:async()=>({})})});
// Skip startup I/O only; every function under test is evaluated from the Python string.
vm.runInContext(SOURCE.slice(0,SOURCE.indexOf('loadPersist();loadCertInfo();loadJobs();setInterval(loadJobs,5000);')).replace(/^refreshModelPanel\(\);renderTiers\(\);$/m,''),ctx);
vm.runInContext(`
const actualLoadPersist=loadPersist,actualRefresh=refresh;
refresh=()=>{};loadJobs=()=>{};loadPersist=()=>{};
var calls=[],queue=[];
fetch=(url,options={})=>{calls.push({url,body:options.body?JSON.parse(options.body):null});
 return new Promise((resolve,reject)=>queue.push({resolve,reject}));};
function response(body={ok:true},status=200){return {ok:status>=200&&status<300,status,json:async()=>body};}
async function tick(){for(let i=0;i<12;i++)await Promise.resolve();}
async function reply(body={ok:true},status=200){queue.shift().resolve(response(body,status));await tick();}
function setup(){openJob('A');EN[0]=true;EN[1]=true;applyDet(0,false);
 MAN.push({t_start:0,t_end:1,screen_box:[1,2,30,40]});
 BE.adds.push({t0:0,t1:1,tref:0,box:[5,6,30,40]});
 BE.ov[0]=[1,2,3,4];BE.times[0]=[0,1];BE.tlspans=[];
 BE.audio=[{t0:0,t1:1,mode:'mute'}];BE.audioLoaded=true;BE.audioSaved=[];}
`,ctx);
async function run(script){return vm.runInContext('(async()=>{'+script+'})()',ctx)}
const watchdog=setTimeout(()=>{console.error('scenario left a pending request');process.exit(1)},2000);
(async()=>{await run(SCENARIO);clearTimeout(watchdog)})().catch(e=>{console.error(e);process.exit(1)});
"""


def run_js(scenario):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is needed to evaluate the embedded review JavaScript")
    script = "const SOURCE=" + json.dumps(app_js()) + ";const SCENARIO=" + json.dumps(scenario) + ";" + HARNESS
    result = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr


def test_job_switch_during_save_never_renders_new_job():
    run_js("""setup();const p=saveAndRender();openJob('B');MAN.push({newJob:true});
    await reply();await p;
    if(calls.some(c=>c.url.endsWith('/render')))throw Error('stale save rendered a job');
    if(MAN.length!==1||!MAN[0].newJob)throw Error('new job draft cleared');""")


def test_newer_edits_survive_save_ack():
    run_js("""setup();const p=saveAndRender();
    applyDet(0,true);BE.ov[0]=[9,8,7,6];BE.times[0]=[0,2];
    BE.adds.push({t0:1,t1:2,box:[2,3,40,50]});MAN.push({newer:true});
    BE.audio.push({t0:1,t1:2,mode:'bleep'});await reply();await p;
    if(!EN[0]||BE.ov[0][0]!==9||BE.times[0][1]!==2||BE.adds.length!==1||MAN.length!==1||BE.audio.length!==2)
      throw Error('newer draft lost');
    if(calls.length!==1)throw Error('render omits newer edits');""")


@pytest.mark.parametrize("failure", ["409", "423", "500", "network", "json", "body"])
@pytest.mark.parametrize("entry", ["saveAndRender", "beSave"])
def test_failed_save_keeps_manual_and_audio_drafts(failure, entry):
    run_js("""setup();const p=ENTRY();
    const request=queue.shift();
    if(FAILURE==='network')request.reject(Error('offline'));
    else if(FAILURE==='json')request.resolve({ok:true,status:200,json:async()=>{throw Error('invalid JSON')}});
    else request.resolve(response({error:'busy'},FAILURE==='body'?200:+FAILURE));
    await tick();await p;
    if(MAN.length!==1||BE.adds.length!==1||BE.audio.length!==1||!BE.ov[0]||!BE.times[0])throw Error('failed save cleared drafts');
    if(calls.length!==1)throw Error('render after failed save');
    if(document.getElementById('beslot').innerHTML.includes('rendering with'))throw Error('editor replaced after failure');
    if(!document.getElementById('reviewSaveStatus')?.textContent)throw Error('missing actionable error');
    """.replace("ENTRY", entry).replace("FAILURE", json.dumps(failure)))


def test_enabled_payload_contains_only_deliberate_changes():
    run_js("""setup();const p=saveAndRender();
    if(JSON.stringify(calls[0].body.enabled)!=='{"0":false}')throw Error('stale loaded enabled values submitted');
    await reply();await reply();await p;""")


def test_duplicate_submit_is_guarded_across_both_entry_points():
    run_js("""setup();const p=saveAndRender();const q=beSave();
    if(calls.length!==1)throw Error('duplicate save');await reply();await reply();await p;await q;
    if(calls.length!==2)throw Error('duplicate render');""")


def test_allowlist_await_keeps_job_and_newer_edits():
    run_js("""setup();confirm=()=>true;const p=saveAndRender();await reply({ok:true,suggest_allowlist:['synthetic']});
    if(calls[1].url!=='api/allowlist')throw Error('allowlist behavior lost');
    openJob('B');await reply();await p;
    if(calls.some(c=>c.url.endsWith('/render')))throw Error('render after allowlist job switch');""")


def test_job_switch_away_and_back_is_a_new_view():
    run_js("""setup();const p=saveAndRender();openJob('B');openJob('A');
    await reply();await p;
    if(calls.length!==1)throw Error('old view rendered on revisit');
    if(MAN.length||BE.adds.length)throw Error('acknowledged old draft not reconciled');""")


def test_failed_old_job_draft_is_recoverable_on_revisit():
    run_js("""setup();const p=saveAndRender();openJob('B');await reply({error:'busy'},409);await p;openJob('A');
    if(MAN.length!==1||BE.adds.length!==1||BE.audio.length!==1)throw Error('old job drafts lost');""")


@pytest.mark.parametrize("failure", ["500", "network", "json", "body"])
def test_render_failure_retry_does_not_reappend_committed_manual(failure):
    run_js("""setup();const p=saveAndRender();await reply();const req=queue.shift();
    if(FAILURE==='network')req.reject(Error('offline'));
    else if(FAILURE==='json')req.resolve({ok:true,status:200,json:async()=>{throw Error('invalid JSON')}});
    else req.resolve(response({error:'render failed'},FAILURE==='body'?200:+FAILURE));
    await tick();await p;
    if(MAN.length||BE.adds.length)throw Error('committed manual retained for replay');
    const retry=saveAndRender();
    if(calls.at(-1).body.manual.length)throw Error('retry appends committed manual');
    await reply();await reply();await retry;
    """.replace("FAILURE", json.dumps(failure)))


def test_healthy_save_freezes_every_edit_kind_and_renders_initiating_job():
    run_js("""setup();const p=saveAndRender();const sent=calls[0].body;
    if(sent.manual.length!==2||sent.box_overrides[0][0]!==1||sent.time_overrides[0][1]!==1||sent.audio[0].mode!=='mute')
      throw Error('incomplete save snapshot');
    await reply();await reply();await p;
    if(calls[1].url!=='api/jobs/A/render'||MAN.length||BE.adds.length||Object.keys(BE.ov).length||Object.keys(BE.times).length)
      throw Error('healthy save flow failed');""")


def test_same_failed_operation_retry_preserves_submitted_payload():
    run_js("""setup();const first=saveAndRender();const snapshot=JSON.stringify(calls[0].body);
    await reply({error:'busy'},423);await first;const retry=saveAndRender();
    if(JSON.stringify(calls[1].body)!==snapshot)throw Error('retry changed operation');
    await reply();await reply();await retry;""")


def test_allowlist_await_preserves_newer_edits_and_does_not_render():
    run_js("""setup();confirm=()=>true;const p=saveAndRender();await reply({ok:true,suggest_allowlist:['synthetic']});
    applyDet(0,true);await reply();await p;
    if(calls.length!==2||!EDITS.enabled[0])throw Error('newer allowlist-await choice lost');""")


def test_edits_during_render_request_remain_visible():
    run_js("""setup();const p=saveAndRender();await reply();applyDet(0,true);
    MAN.push({newer:true});await reply();await p;
    if(document.getElementById('review').removed||MAN.length!==1||!EDITS.enabled[0])throw Error('render hid newer edits');
    if(!document.getElementById('reviewSaveStatus').textContent.includes('Newer edits'))throw Error('render omitted pending notice');""")


def test_plain_review_does_not_send_unloaded_audio():
    run_js("""setup();BE.audioLoaded=false;BE.audio=[];BE.audioSaved=[];const p=saveAndRender();
    if('audio' in calls[0].body)throw Error('plain review overwrites audio');
    await reply();await reply();await p;""")


def test_unchanged_loaded_audio_is_not_reasserted():
    run_js("""setup();BE.audioSaved=copyEdit(BE.audio);const p=saveAndRender();
    if('audio' in calls[0].body)throw Error('unchanged audio reasserted');
    await reply();await reply();await p;""")


def test_identical_new_manual_addition_survives_ack():
    run_js("""setup();const p=saveAndRender();BE.adds.push(copyEdit(BE.adds[0]));
    await reply();await p;if(BE.adds.length!==1||calls.length!==1)throw Error('legitimate identical new addition lost');""")


def test_stale_review_load_cannot_publish_into_new_view():
    run_js("""setup();const p=loadReview();openJob('B');await reply({duration:99,detections:[{i:99,enabled:false}]});await p;
    if(99 in EN||DUR===99)throw Error('old review published in new job');""")


def test_stale_audio_load_cannot_publish_into_revisited_view():
    run_js("""setup();beTLDraw=()=>{};const p=tlInit();openJob('B');openJob('A');
    await reply({detections:[],audio_redactions:[{t0:9,t1:10}]});await p;
    if(BE.audio[0].t0!==0)throw Error('old audio load published after revisit');""")


def test_audio_added_while_initial_report_load_is_pending_survives():
    run_js("""openJob('A');beTLDraw=()=>{};const p=tlInit();
    BE.audio.push({t0:2,t1:3,mode:'bleep'});
    await reply({detections:[],audio_redactions:[{t0:0,t1:1,mode:'mute'}]});await p;
    if(BE.audio.length!==2||BE.audio[1].mode!=='bleep'||!hasReviewEdits(EDITS))throw Error('initial report load lost audio draft');""")


def test_editor_reopen_preserves_existing_drafts():
    run_js("""setup();beHook=()=>{};tlHook=()=>{};beTLDraw=()=>{};beScrub=()=>{};
    for(const id of ['beImg','beVid']){const e=document.createElement('div');elements.set(id,e);}
    const p=loadBoxEdit(1);await reply({duration:2});await reply({detections:[],audio_redactions:[]});await p;
    if(BE.adds.length!==1||!BE.ov[0]||!BE.times[0]||BE.audio.length!==1)throw Error('editor reopen reset drafts');""")


def test_explicit_equal_loaded_choice_submits_once_then_is_acknowledged():
    run_js("""setup();applyDet(1,true);const p=saveAndRender();
    if(calls[0].body.enabled[1]!==true)throw Error('explicit choice omitted');
    await reply();await reply();await p;
    if(Object.keys(EDITS.enabled).length)throw Error('acknowledged enabled choice remains pending');""")


def test_revisited_clean_job_uses_fresh_server_choices():
    run_js("""setup();EDITS.enabled={};EDITS.manual.length=0;BE.adds=[];BE.ov={};BE.times={};BE.audioSaved=copyEdit(BE.audio);
    openJob('B');const inactive=REVIEW_DRAFTS.get('A');
    if(Object.keys(inactive.en).length||inactive.editor.audio.length)throw Error('clean inactive view retains display data');
    openJob('A');const p=loadReview();await reply({duration:2,detections:[{i:0,enabled:false,category:'name',t_start:0,t_end:1}]});await p;
    if(EN[0]!==false)throw Error('cached enabled display masked server change');""")


def test_playback_box_response_cannot_publish_after_job_switch():
    run_js("""setup();var frames=[];requestAnimationFrame=f=>frames.push(f);performance={now:()=>200};
    for(const id of ['beVid','beImg','beCv','bePlay','beT','beL'])elements.set(id,document.createElement('div'));
    const video=elements.get('beVid');Object.assign(video,{readyState:1,currentTime:0,play:async()=>{},pause(){}});
    beDraw=()=>{};beTLDraw=()=>{};const p=beTogglePlay();await p;frames.shift()();
    openJob('B');BE.playing=true;await reply({ox:9,oy:9,boxes:[{i:99,enabled:true}]});
    if(BE.raw||BE.ox===9)throw Error('old playback boxes published in new job');""")


def test_pending_playback_metadata_cannot_start_after_switch():
    run_js("""setup();requestAnimationFrame=()=>{};
    for(const id of ['beVid','beImg','beCv','bePlay'])elements.set(id,document.createElement('div'));
    let played=false;const video=elements.get('beVid');Object.assign(video,{readyState:0,load(){},play:async()=>{played=true},pause(){}});
    const p=beTogglePlay();openJob('B');video.onloadedmetadata();await p;
    if(played)throw Error('old video started after job switch');""")


PENDING_AUDIO_SETUP = """
setup();EDITS.enabled={};MAN.length=0;BE.adds=[];BE.ov={};BE.times={};
BE.audioSaved=copyEdit(BE.audio);beTLDraw=()=>{};
const kind=KIND;
if(kind==='enabled')applyDet(1,false);
if(kind==='manual')MAN.push({t_start:0,t_end:1,screen_box:[1,2,30,40]});
if(kind==='box')BE.ov[1]=[5,6,30,40];
if(kind==='time')BE.times[1]=[0.2,1];
if(kind==='editor_manual')BE.adds.push({t0:0,t1:1,tref:0,box:[5,6,30,40]});
"""


@pytest.mark.parametrize("kind", ["enabled", "manual", "box", "time", "editor_manual"])
def test_revisit_refreshes_clean_audio_with_non_audio_draft_pending(kind):
    run_js(PENDING_AUDIO_SETUP.replace("KIND", json.dumps(kind)) + """
    openJob('B');openJob('A');const load=tlInit();
    await reply({detections:[],audio_redactions:[{t0:5,t1:6,mode:'mute'}]});await load;
    BE.audio.push({t0:7,t1:8,mode:'bleep'});const save=saveAndRender();
    if(JSON.stringify(calls.at(-1).body.audio)!==JSON.stringify([
      {t0:5,t1:6,mode:'mute'},{t0:7,t1:8,mode:'bleep'}]))throw Error('revisited audio used stale clean cache');
    const sent=calls.at(-1).body;
    if(kind==='enabled'&&sent.enabled[1]!==false)throw Error('pending enabled choice lost');
    if((kind==='manual'||kind==='editor_manual')&&sent.manual.length!==1)throw Error('pending manual lost');
    if(kind==='box'&&!sent.box_overrides[1])throw Error('pending box lost');
    if(kind==='time'&&!sent.time_overrides[1])throw Error('pending time lost');
    await reply();await reply();await save;
    """)


@pytest.mark.parametrize("kind", ["enabled", "manual", "box", "time", "editor_manual"])
@pytest.mark.parametrize("change", ["add", "remove", "modify"])
def test_revisit_preserves_dirty_audio_with_non_audio_draft_pending(kind, change):
    run_js(PENDING_AUDIO_SETUP.replace("KIND", json.dumps(kind)) + """
    const change=CHANGE;
    if(change==='add')BE.audio.push({t0:2,t1:3,mode:'bleep'});
    if(change==='remove')BE.audio.splice(0,1);
    if(change==='modify')BE.audio[0].t1=2;
    const draft=JSON.stringify(BE.audio);openJob('B');openJob('A');const load=tlInit();
    await reply({detections:[],audio_redactions:[{t0:5,t1:6,mode:'mute'}]});await load;
    if(JSON.stringify(BE.audio)!==draft)throw Error('revisit overwrote dirty audio');
    const save=saveAndRender();if(JSON.stringify(calls.at(-1).body.audio)!==draft)throw Error('dirty audio not submitted');
    await reply();await reply();await save;
    """.replace("CHANGE", json.dumps(change)))


def test_revisit_refreshes_clean_audio_during_non_audio_save():
    run_js(PENDING_AUDIO_SETUP.replace("KIND", json.dumps("enabled")) + """
    const save=saveAndRender();openJob('B');openJob('A');const load=tlInit();
    const saving=queue.shift();await reply({detections:[],audio_redactions:[{t0:5,t1:6,mode:'mute'}]});await load;
    if(BE.audio[0].t0!==5)throw Error('non-audio save retained stale clean audio');
    saving.resolve(response());await tick();await save;
    if(calls.some(c=>c.url.endsWith('/render')))throw Error('revisited view rendered');
    """)


def test_audio_toggle_back_during_save_survives_revisit_and_ack():
    run_js(PENDING_AUDIO_SETUP.replace("KIND", json.dumps("enabled")) + """
    const baseline=copyEdit(BE.audio);BE.audio.push({t0:2,t1:3,mode:'bleep'});
    const save=saveAndRender();BE.audio=copyEdit(baseline);openJob('B');openJob('A');
    const load=tlInit();const saving=queue.shift();
    await reply({detections:[],audio_redactions:[{t0:5,t1:6,mode:'mute'}]});await load;
    saving.resolve(response());await tick();await save;
    if(!sameEdit(BE.audio,baseline)||!hasReviewEdits(EDITS))throw Error('audio toggle-back lost during acknowledgement');
    const retry=saveAndRender();if(!sameEdit(calls.at(-1).body.audio,baseline))throw Error('audio toggle-back not submitted');
    await reply();await reply();await retry;
    """)


@pytest.mark.parametrize("failure", ["network", "423"])
def test_audio_toggle_back_survives_unacknowledged_save_and_revisit(failure):
    run_js(PENDING_AUDIO_SETUP.replace("KIND", json.dumps("enabled")) + """
    const baseline=copyEdit(BE.audio);BE.audio.push({t0:2,t1:3,mode:'bleep'});
    const save=saveAndRender();BE.audio=copyEdit(baseline);openJob('B');
    if(FAILURE==='network')queue.shift().reject(Error('offline'));
    else await reply({error:'busy'},423);
    await tick();await save;openJob('A');
    const load=tlInit();await reply({detections:[],audio_redactions:[{t0:5,t1:6,mode:'mute'}]});await load;
    if(!sameEdit(BE.audio,baseline))throw Error('unacknowledged audio toggle-back lost');
    const retry=saveAndRender();if(!sameEdit(calls.at(-1).body.audio,baseline))throw Error('unacknowledged audio toggle-back omitted');
    await reply();await reply();await retry;
    """.replace("FAILURE", json.dumps(failure)))


@pytest.mark.parametrize('action', ["delJob('A')", "retryJob('A')", 'vaultDoLock()'])
@pytest.mark.parametrize('status', [409, 423])
def test_lifecycle_rejections_keep_current_review_and_drafts(action, status):
    run_js("""setup();confirm=()=>true;
    let alerts=[];alert=message=>alerts.push(String(message));vaultStatus=()=>{};
    const draft=EDITS,view=VIEW_GEN,html=detail.innerHTML;
    const p=ACTION;const pending=queue.shift();
    pending.resolve({ok:false,status:STATUS,json:async()=>({error:'busy or locked'}),
      text:async()=>'busy or locked'});
    await tick();await p;
    if(CUR!=='A'||VIEW_GEN!==view||EDITS!==draft||REVIEW_DRAFTS.get('A')!==draft)
      throw Error('rejected lifecycle request cleared or switched review');
    if(detail.innerHTML!==html||MAN.length!==1||BE.adds.length!==1||BE.audio.length!==1)
      throw Error('rejected lifecycle request cleared draft/view');
    if(alerts.length!==1||!alerts[0].includes('busy or locked')||alerts[0].startsWith('Locked'))
      throw Error('lifecycle rejection claimed success or omitted failure');
    if(calls.length!==1)throw Error('rejected lifecycle request started another action');
    """.replace('ACTION', action).replace('STATUS', str(status)))


@pytest.mark.parametrize('action', ['loadPersist()', 'rmPersist("synthetic-one")', 'clearPersist()'])
@pytest.mark.parametrize('failure', ['locked', 'recovery', 'network'])
def test_allowlist_refusal_preserves_display_and_reports_error(action, failure):
    run_js("""loadPersist=actualLoadPersist;confirm=()=>true;
    for(const id of ['persistlist','persistnote','clearpersist'])
      elements.set(id,document.createElement('div'));
    const list=elements.get('persistlist'),note=elements.get('persistnote');
    list.innerHTML='existing safe words';note.textContent='existing note';
    const p=ACTION;const pending=queue.shift();
    if(FAILURE==='network')pending.reject(Error('offline'));
    else pending.resolve({ok:false,status:423,json:async()=>{throw Error('HTML refusal')}});
    let escaped=null;try{await p}catch(e){escaped=e}
    if(escaped)throw Error('allowlist refusal escaped as unhandled rejection');
    if(list.innerHTML!=='existing safe words')throw Error('failed allowlist request cleared display');
    if(note.style.display!=='block'||note.textContent==='existing note'||!note.textContent)
      throw Error('allowlist refusal was not shown in existing note');
    if(calls.length!==1)throw Error('rejected mutation started an unconfirmed reload');
    """.replace('ACTION', action).replace('FAILURE', json.dumps(failure)))


@pytest.mark.parametrize('action', ['loadPersist()', 'rmPersist("synthetic-one")', 'clearPersist()'])
def test_allowlist_ready_success_updates_display_after_acknowledgement(action):
    run_js("""loadPersist=actualLoadPersist;confirm=()=>true;
    for(const id of ['persistlist','persistnote','clearpersist'])
      elements.set(id,document.createElement('div'));
    elements.get('persistlist').innerHTML='old display';
    const p=ACTION;
    if(!IS_READ){await reply({ok:true,count:1});}
    if(calls.length!==(IS_READ?1:2))throw Error('ready mutation did not reload after ack');
    await reply({words:['synthetic-two'],path:'/synthetic/allowlist.txt'});await p;
    if(!elements.get('persistlist').innerHTML.includes('synthetic-two'))
      throw Error('ready allowlist response was not displayed');
    if(elements.get('clearpersist').style.display!=='inline-block')throw Error('ready controls hidden');
    """.replace('ACTION', action).replace('IS_READ', 'true' if action == 'loadPersist()' else 'false'))


@pytest.mark.parametrize("fallback", [False, True])
def test_manual_id_is_generated_once_retained_and_serialized_on_retry(fallback):
    run_js("""setup();if(FALLBACK)crypto={getRandomValues:crypto.getRandomValues.bind(crypto)};
    const p=saveAndRender();const ids=calls[0].body.manual.map(m=>m.manual_id);
    assert(ids.every(id=>/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(id)));
    assert.notEqual(ids[0],ids[1]);await reply({error:'lost response'},500);await p;
    openJob('B');openJob('A');const q=saveAndRender();
    assert.deepEqual(calls[1].body.manual.map(m=>m.manual_id),ids);
    await reply();await reply();await q;""".replace('FALLBACK', str(fallback).lower()))


def test_missing_secure_randomness_retains_drafts_and_reports_error():
    run_js("""setup();crypto={};const p=saveAndRender();await p;
    assert.equal(calls.length,0);assert.equal(BE.adds.length,1);assert.equal(MAN.length,1);
    assert(document.getElementById('reviewSaveStatus').textContent.includes('random'));
    assert(!EDITS.busy);""")


# These fixtures model containment/removal ordering while executing shipped
# showPanel/refresh/saveAndRender, never a surrogate teardown.
MOUNT = r"""
function mountIn(rootId){
 const root=elements.get(rootId)||el();elements.set(rootId,root);
 const img=el(),vid=el(),cv=el(),paint={value:'original'};
 Object.assign(img,{complete:true,naturalWidth:640,naturalHeight:360,
  getBoundingClientRect:()=>({width:319.5,height:179.71875})});
 Object.assign(vid,{paused:false,pause(){this.paused=true;this.pausedBeforeDetach=!root.detached;},
  getBoundingClientRect:img.getBoundingClientRect});
 Object.assign(cv,{releasePointerCapture(){},getContext:()=>({setTransform(){},clearRect(){paint.value='cleared'}})});
 elements.set('beImg',img);elements.set('beVid',vid);elements.set('beCv',cv);
 root.contains=node=>node===cv||node===img||node===vid;
 let html='';Object.defineProperty(root,'innerHTML',{configurable:true,get:()=>html,set:value=>{
  root.retiredBeforeDetach=BE_VIEW===null&&vid.paused;root.detached=true;html=value;
 }});
 root.remove=()=>{root.retiredBeforeDetach=BE_VIEW===null&&vid.paused;root.detached=true;};
 const view=beMount(img,vid,cv,CUR,VIEW_GEN,BE);view.observer.disconnected=false;
 view.observer.disconnect=()=>{view.observer.disconnected=true};
 view.transform={media:img,sw:640,sh:360,width:319.5,height:179.71875,sx:319.5/640,sy:179.71875/360};
 return {root,img,vid,cv,view,paint};
}
"""


def test_retained_editor_keeps_mount_on_panel_reentry():
    run_js(MOUNT + r"""openJob('A');const m=mountIn('beslot');
    BE.ov[0]=[11,12,33,44];BE.drag={kind:'move'};const applied=JSON.stringify(BE.ov);
    showPanel('boxedit_rev');
    assert.equal(BE_VIEW,m.view,'retained panel lost its mount');
    assert.equal(document.getElementById('beCv'),m.cv);
    assert.equal(m.view.observer.disconnected,false);assert.equal(m.vid.paused,false);
    assert.equal(BE.drag.kind,'move');assert.equal(JSON.stringify(BE.ov),applied);
    // Removing an unrelated comparison subtree must preserve this owner too.
    elements.set('compare',el());showPanel('boxedit_rev');assert.equal(BE_VIEW,m.view);
    """)


@pytest.mark.parametrize('path', ['panel', 'save'])
def test_removed_editor_subtree_releases_before_removal(path):
    run_js(MOUNT + r"""openJob('A');const m=mountIn('beslot');
    if(PATH==='panel')showPanel('compare');
    if(PATH==='save'){
      const p=saveAndRender();await reply();await reply();await p;
      // The review is the actual ancestor removed by a save acknowledgement.
    }
    assert.equal(m.view.observer.disconnected,true,'removed mount observer still active');
    assert.equal(m.vid.paused,true,'outgoing video not paused');
    assert.equal(m.vid.pausedBeforeDetach,true,'video paused only after detach');
    """.replace('PATH', json.dumps(path)).replace("const m=mountIn('beslot');", "const m=mountIn(PATH==='save'?'review':'beslot');".replace('PATH',json.dumps(path))))


def test_phase_actions_replacement_retires_editor():
    run_js(MOUNT + r"""openJob('A');const m=mountIn('actions');
    for(const name of ['ph','eta','prog','log','pimg','warnbox'])elements.set(name,el());
    SHELLPH='done';const p=actualRefresh();
    await reply({phase:'rendering',progress:.25});await reply({lines:[],len:0});await p;
    assert.equal(m.view.observer.disconnected,true,'phase replacement retained observer');
    assert.equal(m.root.retiredBeforeDetach,true,'phase replacement detached before retirement');
    assert.equal(m.vid.pausedBeforeDetach,true);
    """)


def test_old_mount_callbacks_cannot_touch_replacement():
    run_js(MOUNT + r"""openJob('A');const old=mountIn('beslot');
    showPanel('compare');const replacement=mountIn('beslot_done');
    const before=replacement.paint.value;old.view.sync();
    assert.equal(BE_VIEW,replacement.view);assert.equal(replacement.paint.value,before);
    assert.equal(old.view.observer.disconnected,true);
    """)
