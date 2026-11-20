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
function el(){return {isConnected:true,textContent:'',innerHTML:'',style:{},dataset:{},disabled:false,
 classList:{toggle(){},remove(){}},remove(){this.removed=true},
 appendChild(e){(this.children??=[]).push(e);return e},addEventListener(k,f){(this.events??={})[k]=f},setAttribute(){},querySelector(selector){
  if(selector.startsWith('[data-review-heading='))return {querySelector:()=>el(),querySelectorAll:()=>[el(),el()]};
  if(selector.startsWith('[data-review-card='))return {dataset:{},querySelector:()=>el()};
  return null;
 },querySelectorAll(selector){
  if(selector==='[data-review-heading]')return [{querySelector:()=>el(),querySelectorAll:()=>[el(),el()]}];
  if(selector==='[data-review-card]')return [{dataset:{},querySelector:()=>el()}];
  return [];
 },insertAdjacentHTML(){}}}
for(const id of ['detail','beslot','review','reviewSaveStatus'])elements.set(id,el());
const ctx=vm.createContext({elements,el,console,assert,Set,Map,JSON,Date,Math,Promise,crypto:require("node:crypto").webcrypto,
 ResizeObserver:class {observe(){} disconnect(){}},
 document:{getElementById:id=>elements.get(id)||null,querySelector:s=>elements.get(s.slice(1))||null,
 querySelectorAll:()=>[],addEventListener(){},createElement:el},
 detail:elements.get('detail'),window:{addEventListener(){}},setInterval:()=>1,clearInterval(){},clearTimeout(){},setTimeout(){},
 confirm:()=>false,alert(){},fetch:async()=>({ok:true,json:async()=>({})})});
// Skip startup I/O only; every function under test is evaluated from the Python string.
vm.runInContext(SOURCE.slice(0,SOURCE.indexOf('loadPersist();loadCertInfo();loadJobs();setInterval(loadJobs,5000);')).replace(/^refreshModelPanel\(\);renderTiers\(\);$/m,''),ctx);
vm.runInContext(`
const actualLoadPersist=loadPersist;
refresh=()=>{};loadJobs=()=>{};loadPersist=()=>{};
var calls=[],queue=[];
fetch=(url,options={})=>{calls.push({url,body:options.body?JSON.parse(options.body):null});
 return new Promise((resolve,reject)=>queue.push({resolve,reject}));};
function response(body={ok:true},status=200){return {ok:status>=200&&status<300,status,json:async()=>body,text:async()=>JSON.stringify(body)};}
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
    script = "const SOURCE=" + json.dumps(app_js()) + ";const SCENARIO=" + json.dumps("ReviewScheduler.prototype.start=function(){};" + scenario) + ";" + HARNESS
    result = subprocess.run([node], input=script, capture_output=True, text=True, timeout=15)
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
    const retry=saveAndRender();if(calls.at(-1).body.audio.length!==2)throw Error('uncertain payload changed before acknowledgement');
    await reply();await retry;if(!hasReviewEdits(EDITS))throw Error('newer audio toggle-back lost after retry ACK');
    const final=saveAndRender();if(!sameEdit(calls.at(-1).body.audio,baseline))throw Error('audio toggle-back omitted after retry ACK');
    await reply();await reply();await final;
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


def test_old_mount_callbacks_cannot_touch_replacement():
    run_js(MOUNT + r"""openJob('A');const old=mountIn('beslot');
    showPanel('compare');const replacement=mountIn('beslot_done');
    const before=replacement.paint.value;old.view.sync();
    assert.equal(BE_VIEW,replacement.view);assert.equal(replacement.paint.value,before);
    assert.equal(old.view.observer.disconnected,true);
    """)


@pytest.mark.parametrize('retained', [False, True], ids=['removed', 'retained'])
def test_pending_playback_metadata_retirement_and_same_draft_remount(retained):
    run_js(MOUNT + r"""openJob('A');requestAnimationFrame=()=>{};
    const old=mountIn('beslot');elements.set('bePlay',el());let played=false;
    Object.assign(old.vid,{readyState:0,paused:true,load(){},
      play:async()=>{played=true;old.vid.paused=false}});
    const pending=beTogglePlay();assert.equal(BE.playing,true);assert.equal(old.vid.paused,true);
    if(RETAINED){
      showPanel('boxedit_rev');assert.equal(BE_VIEW,old.view);
      assert.equal(BE.playing,true);assert.equal(old.view.observer.disconnected,false);
      Object.assign(old.vid,{readyState:1,videoWidth:640,videoHeight:360});
      old.vid.onloadedmetadata();await pending;assert.equal(played,true);
      assert.equal(BE_VIEW,old.view);showPanel('compare');return;
    }
    showPanel('compare');const replacement=mountIn('beslot_done');
    assert.equal(BE.playing,false,'removed pending Play leaked into the same draft remount');
    assert(replacement.view.sync(),'replacement still image has no transform');
    const pixels=replacement.paint.value;
    old.vid.onloadedmetadata();await pending;
    assert.equal(played,false,'late old metadata started outgoing video');
    assert.equal(BE_VIEW,replacement.view);assert.equal(replacement.paint.value,pixels);
    """.replace('RETAINED', str(retained).lower()))


# Exact-sample fixtures model DOM/media I/O only: shipped handlers remain intact.
EXACT = MOUNT + r"""
assert.deepEqual=(a,b)=>assert.equal(JSON.stringify(a),JSON.stringify(b));
var candidates=[],liveURLs=new Set(),revoked=[],urlNumber=0;
Blob=class {};atob=s=>s;
URL={createObjectURL(){const u='blob:sample-'+(++urlNumber);liveURLs.add(u);return u},
 revokeObjectURL(u){liveURLs.delete(u);revoked.push(u)}};
Image=class {constructor(){this.complete=true;this.naturalWidth=640;this.naturalHeight=360;}
 decode(){return new Promise((resolve,reject)=>candidates.push({image:this,resolve,reject}));}};
function sample(t=0,extra={}){return {version:1,sample:{source_ref:'incarnation:7',timeline_eq:'a'.repeat(64),
 policy:'opencv-ffmpeg-zero-cfr-v1',index:4,requested_s:t,canonical_s:4/24,observed_s:4/24,
 width:640,height:360,stream:0,origin:[0,0],offset:[8,-4],...extra},
 image:{mime:'image/jpeg',base64:'/9j/AA=='},boxes:[{i:0,category:'name',text:'synthetic',enabled:true,
 t_start:0,t_end:2,box:[128,76,328,216],row_context_eq:'b'.repeat(64),
 base:{cbox:[120,80,320,220],span:[0,2,0]}}]};}
function exactMount(){const m=mountIn('beslot');BE.dur=3;BE.win=[0,3];
 for(const id of ['beT','beL','beRm','beTimes','beT0','beT1','beAdd','beTrk','beMute','beTrkSt','bePlay','reviewResolveActions'])elements.set(id,el());
 elements.get('beT').value=0;BE.tlspans=[];
 m.cv.getContext=()=>new Proxy({},{get:()=>()=>{}});
 m.cv.setPointerCapture=()=>{};m.cv.getBoundingClientRect=()=>({left:0,top:0,width:319.5,height:179.71875});
 elements.get('detail').contains=m.root.contains;
 m.img.decode=async()=>{};m.img.currentSrc='';beHook();return m;}
async function inspected(m,t=0){const p=beScrub();await reply(sample(t));
 assert.equal(candidates.length,1,'exact sample must await detached decode');
 candidates.shift().resolve();await tick();await p;
 assert(beReady(m.view),'decoded displayed sample should be ready');}
function strictDraft(){openJob('A');const m=exactMount();return m;}
function ack(payload,base={cbox:[130,85,330,225],span:[0,2,.4]}){
 const rows={};for(const [key,pc] of Object.entries(payload.geometry_preconditions||{}))rows[key]={...pc,base};
 return {ok:true,geometry_rows:rows};}
"""


def test_exact_scrubs_coalesce_fetch_and_body_across_mounts():
    run_js(EXACT + r"""openJob('A');const a=exactMount();beScrub();
    let bodyResolve;const req=queue.shift();req.resolve({ok:true,status:200,json:()=>new Promise(r=>bodyResolve=r)});await tick();
    elements.get('beT').value=.2;beScrub();openJob('B');exactMount();beScrub();
    openJob('A');const a3=exactMount();elements.get('beT').value=.7;beScrub();
    assert.equal(calls.length,1,'fetch/body cycle released early');bodyResolve(sample());await tick();
    assert.equal(candidates.length,0,'stale body decoded');assert.equal(calls.length,2);
    assert(calls[1].url.endsWith('A/edit_sample?t=0.7'));
    await reply(sample(.7));assert.equal(candidates.length,1);
    elements.get('beT').value=.8;beScrub();assert.equal(calls.length,2,'decode released slot early');
    candidates.shift().resolve();await tick();assert.equal(calls.length,3);assert.equal(liveURLs.size,0);
    await reply(sample(.8));candidates.shift().resolve();await tick();assert(beReady(a3.view));
    assert.equal(liveURLs.size,1);beUnmount();assert.equal(liveURLs.size,0);""")


@pytest.mark.parametrize('bad', ['dimensions','zero','hidden'])
def test_exact_sample_waits_for_display_decode_and_transform(bad):
    run_js(EXACT + r"""const m=strictDraft();beScrub();await reply(sample());assert.equal(beReady(m.view),false);
    if(BAD==='dimensions')m.img.naturalWidth=1;
    else if(BAD==='zero')m.img.getBoundingClientRect=()=>({width:0,height:0});
    else m.cv.getBoundingClientRect=()=>({left:0,top:0,width:0,height:0});
    candidates.shift().resolve();await tick();assert.equal(beReady(m.view),false);
    assert.equal(Object.keys(BE.ov).length,0);""".replace('BAD',json.dumps(bad)))


def test_exact_old_load_error_and_same_be_remount_are_inert():
    run_js(EXACT+r"""const old=strictDraft();beScrub();await reply(sample());
    const next=exactMount();beScrub();candidates.shift().reject(Error('old decode'));await tick();
    assert.equal(BE_VIEW,next.view);assert.equal(next.view.readySample,null);
    await reply(sample());candidates.shift().resolve();await tick();assert(beReady(next.view));
    assert.equal(liveURLs.size,1);assert.equal(revoked.length,1);""")


def test_same_be_open_intent_before_metadata_cannot_replace_newer_mount():
    run_js(EXACT+r"""const old=strictDraft();const p=loadBoxEdit(1);
    const q=loadBoxEdit(1);const first=queue.shift(),second=queue.shift();
    // Same draft, newer mounted content appears before older metadata.
    second.resolve(response({duration:3}));await tick();const newer=BE_VIEW;
    first.resolve(response({duration:99}));await tick();assert.equal(BE_VIEW,newer);
    assert.equal(BE.dur,3);await reply({detections:[]});await q;await p;
    assert.equal(BE_VIEW,newer);""")


def test_exact_geometry_handlers_share_ready_sample():
    run_js(EXACT+r"""const m=strictDraft();const down=(x,y)=>m.cv.events.pointerdown({clientX:x,clientY:y,pointerId:1});
    down(100,60);assert.equal(BE.sel,-1);beAddMode();assert.equal(BE.add,false);
    beTrackMode();assert.equal(!!BE.trk,false);BE.sel=0;elements.get('beT0').value=0;elements.get('beT1').value=1;
    beApplyTimes();assert.equal(Object.keys(BE.times).length,0);
    await inspected(m);down(100,60);assert.equal(BE.sel,0);down(100,60);
    m.cv.events.pointermove({clientX:110,clientY:65,pointerId:1});
    assert(BE.ov[0]);assert.equal(BE.geometry[0].precondition.source_ref,'incarnation:7');
    assert.deepEqual(BE.geometry[0].precondition.base.span,[0,2,0]);
    assert.deepEqual(BE.geometry[0].precondition.offset,[8,-4]);""")


def test_exact_scrub_cancels_gesture_keeps_pending_baseline():
    run_js(EXACT+r"""const m=strictDraft();await inspected(m);
    BE.sel=0;elements.get('beT0').value=.1;elements.get('beT1').value=1;beApplyTimes();
    const owner=BE.geometry[0],before=JSON.stringify(BE.times);BE.drag={kind:'move'};BE.addAnchor=[1,2];
    BE.audio.push({t0:0,t1:1});applyDet(2,false);beScrub();
    assert.equal(BE.drag,null);assert.equal(BE.addAnchor,null);assert.equal(BE.sel,-1);
    assert.equal(BE.geometry[0],owner);assert.equal(JSON.stringify(BE.times),before);
    assert.equal(BE.audio.length,1);assert.equal(EDITS.enabled[2],false);""")


@pytest.mark.parametrize('change',['window','scrub','good'])
def test_exact_add_captures_canonical_creation_after_prompts(change):
    run_js(EXACT+r"""const m=strictDraft();await inspected(m);beAddMode();let prompts=0;
    prompt=()=>{prompts++;if(CHANGE==='scrub'&&prompts===2)beScrub();return prompts===1?(CHANGE==='window'?'1':'0'):'2'};
    const down=(x,y)=>m.cv.events.pointerdown({clientX:x,clientY:y,pointerId:1});down(10,10);down(50,50);
    if(CHANGE!=='good'){assert.equal(BE.adds.length,0);return;}
    assert.equal(BE.adds.length,1);assert.equal(BE.adds[0].tref,4/24);
    assert.equal(Object.keys(BE.adds[0].sample_precondition).length,8);assert(BE.adds[0].manual_id);""".replace('CHANGE',json.dumps(change)))


@pytest.mark.parametrize('kind',['box-span','span-box','both','away-back'])
def test_geometry_ack_retains_newer_kind_and_advances_owned_complete_base(kind):
    run_js(EXACT+r"""const m=strictDraft();await inspected(m);beCaptureGeometry(m.view,BE.raw[0]);
    if(KIND==='span-box')BE.times[0]=[.1,1];else BE.ov[0]=[130,85,330,225];
    if(KIND==='both')BE.times[0]=[.1,1];const p=saveAndRender(),sent=calls.at(-1).body;
    if(KIND==='box-span')BE.times[0]=[.2,1.5];else BE.ov[0]=[140,90,340,230];
    if(KIND==='away-back')BE.ov[0]=[130,85,330,225];
    const base={cbox:sent.box_overrides[0]||[120,80,320,220],span:sent.time_overrides[0]?[...sent.time_overrides[0],.4]:[0,2,.4]};
    await reply(ack(sent,base));if(KIND==='away-back')await reply();await p;
    if(KIND!=='away-back'){assert.equal(calls.filter(c=>c.url.endsWith('/render')).length,0);
    assert.deepEqual(BE.geometry[0].precondition.base,base);assert(BE.ov[0]||BE.times[0]);}
    """.replace('KIND',json.dumps(kind)))


def test_geometry_ack_does_not_transplant_reinspected_family():
    run_js(EXACT+r"""const m=strictDraft();await inspected(m);beCaptureGeometry(m.view,BE.raw[0]);BE.ov[0]=[130,85,330,225];
    const p=saveAndRender(),sent=calls.at(-1).body;BE.geometry[0]={precondition:{...BE.geometry[0].precondition,source_ref:'other:1'}};
    await reply(ack(sent));await p;assert(BE.ov[0]);assert.equal(BE.geometry[0].precondition.source_ref,'other:1');""")


@pytest.mark.parametrize('failure',['network','json','body','409','423','500'])
def test_lost_ack_retries_identical_payload_before_newer_geometry(failure):
    run_js(EXACT+r"""const m=strictDraft();await inspected(m);beCaptureGeometry(m.view,BE.raw[0]);BE.ov[0]=[130,85,330,225];
    const p=saveAndRender(),sent=copyEdit(calls.at(-1).body),req=queue.shift();
    if(FAILURE==='network')req.reject(Error('lost ACK'));
    else if(FAILURE==='json')req.resolve({ok:true,status:200,json:async()=>{throw Error('bad JSON')}});
    else req.resolve(response({error:'busy'},FAILURE==='body'?200:+FAILURE));await tick();await p;
    BE.times[0]=[.2,1.5];BE.audioLoaded=true;BE.audio.push({t0:0,t1:1});applyDet(1,false);
    const retry=saveAndRender();assert.deepEqual(calls.at(-1).body,sent);await reply(ack(sent));await retry;
    assert(BE.times[0]);assert.equal(calls.filter(c=>c.url.endsWith('/render')).length,0);
    assert.equal(EDITS.submitted,null);""".replace('FAILURE',json.dumps(failure)))


@pytest.mark.parametrize('uncertain',[False,True])
def test_geometry_conflict_authority_and_abandon_preserve_drafts(uncertain):
    run_js(EXACT+r"""const m=strictDraft();await inspected(m);beCaptureGeometry(m.view,BE.raw[0]);BE.ov[0]=[130,85,330,225];
    let p=saveAndRender();if(UNCERTAIN){queue.shift().reject(Error('lost'));await tick();await p;p=saveAndRender();}
    await reply({ok:false,error:'geometry_conflict'},409);await p;
    assert.equal(!!EDITS.submitted,UNCERTAIN);const before=JSON.stringify(BE.ov),n=calls.length;
    if(UNCERTAIN){confirm=()=>false;reviewAbandon();assert(EDITS.submitted);confirm=()=>true;reviewAbandon();assert.equal(EDITS.submitted,null);}
    assert.equal(JSON.stringify(BE.ov),before);assert.equal(calls.length,n);""".replace('UNCERTAIN',str(uncertain).lower()))


@pytest.mark.parametrize('changed',[False,True])
def test_discard_geometry_and_inspect_is_selected_and_confirmed(changed):
    run_js(EXACT+r"""const m=strictDraft();await inspected(m);beCaptureGeometry(m.view,BE.raw[0]);BE.ov[0]=[130,85,330,225];BE.times[99]=[0,1];
    BE.adds.push({manual_id:'keep',box:[1,2,3,4]});MAN.push({manual_id:'separate'});BE.audio.push({t0:0,t1:1});applyDet(1,false);
    confirm=()=>{if(CHANGED)BE.ov[0]=[140,85,340,225];return true};await reviewDiscard('row:0');
    assert.equal(!!BE.ov[0],CHANGED);assert(BE.times[99]);assert.equal(BE.adds.length,1);assert.equal(MAN.length,1);
    assert.equal(BE.audio.length,1);assert.equal(EDITS.enabled[1],false);
    assert.equal(calls.filter(c=>c.url.endsWith('/detections')||c.url.endsWith('/render')).length,0);
    """.replace('CHANGED',str(changed).lower()))


def test_ack_clear_next_edit_uses_confirmed_display_baseline():
    run_js(EXACT+r"""const m=strictDraft();await inspected(m);beCaptureGeometry(m.view,BE.raw[0]);BE.ov[0]=[130,85,330,225];
    const p=saveAndRender(),sent=calls.at(-1).body;applyDet(1,false);await reply(ack(sent));await p;
    assert.deepEqual(BE.raw[0].base.cbox,[130,85,330,225]);assert.deepEqual(BE.boxes[0].box,[138,81,338,221]);
    beCaptureGeometry(m.view,BE.raw[0]);assert.deepEqual(BE.geometry[0].precondition.base.span,[0,2,.4]);""")


def test_track_captures_seed_window_and_job_before_await():
    run_js(EXACT+r"""const m=strictDraft();await inspected(m);const st=elements.get('beTrkSt');
    const p=beTrackGo([10,20,40,60]);const sent=calls.at(-1);assert(sent.url.endsWith('A/track_object'));
    assert.equal(sent.body.t_ref,4/24);assert.deepEqual(sent.body.box,[10,20,40,60]);
    assert.equal(Object.keys(sent.body.seed).length,8);assert.deepEqual([sent.body.t0,sent.body.t1],[0,3]);
    BE.win=[1,2];openJob('B');await reply({ok:true});await p;assert.equal(BE_VIEW,null);""")


def test_track_late_status_cannot_refresh_reopened_mount():
    run_js(EXACT+r"""const m=strictDraft();await inspected(m);var timers=[];setTimeout=f=>{timers.push(f);return 1};
    const p=beTrackGo([10,20,40,60]);await reply();await p;const poll=timers.pop();poll();
    const next=exactMount();await reply({state:'done',added:2});assert.equal(BE_VIEW,next.view);
    assert.equal(calls.filter(c=>c.url.endsWith('/report')).length,0);""")


def test_playback_response_after_pause_cannot_replace_exact_sample():
    run_js(EXACT+r"""const m=strictDraft();await inspected(m);var frames=[];requestAnimationFrame=f=>frames.push(f);performance={now:()=>200};
    Object.assign(m.vid,{readyState:1,currentTime:.2,videoWidth:640,videoHeight:360,play:async()=>{}});
    await beTogglePlay();m.vid.currentTime=.2;frames.shift()();const old=queue.shift();bePlayStop();
    await reply(sample(.2));candidates.shift().resolve();await tick();const before=JSON.stringify(BE.raw);
    old.resolve(response({ox:99,oy:99,boxes:[]}));await tick();assert.equal(JSON.stringify(BE.raw),before);assert(beReady(m.view));""")



def test_exact_existing_outside_frame_rows_remain_inspectable():
    run_js(EXACT+r"""const m=strictDraft();beScrub();const data=sample();data.boxes[0].base={cbox:[-20,-10,700,400],span:[0,2,3]};
    data.boxes[0].box=[-12,-14,708,396];await reply(data);assert.equal(candidates.length,1);
    candidates.shift().resolve();await tick();assert(beReady(m.view));assert.equal(BE.boxes[0].box[0],-12);""")


def test_ack_span_inactive_and_other_mount_cannot_patch_current_row():
    run_js(EXACT+r"""const m=strictDraft();await inspected(m);beCaptureGeometry(m.view,BE.raw[0]);BE.times[0]=[1,2];
    const p=saveAndRender(),sent=calls.at(-1).body;applyDet(2,false);await reply(ack(sent,{cbox:[120,80,320,220],span:[1,2,1]}));await p;
    assert.equal(BE.boxes.length,0,'ACK span left an inactive row editable');
    beCaptureGeometry(m.view,BE.raw[0]);BE.ov[0]=[130,85,330,225];const q=saveAndRender(),sent2=calls.at(-1).body;
    const next=exactMount();applyDet(2,true);await reply(ack(sent2,{cbox:[130,85,330,225],span:[1,2,1]}));await q;
    assert.equal(next.view.readySample,null);assert(calls.at(-1).url.includes('/edit_sample'));
    assert.equal(BE_VIEW,next.view);""")


@pytest.mark.parametrize('kind',['missing','wrongbase','wrongsource'])
def test_malformed_geometry_ack_keeps_all_submitted_state_uncertain(kind):
    run_js(EXACT+r"""const m=strictDraft();await inspected(m);beCaptureGeometry(m.view,BE.raw[0]);BE.ov[0]=[130,85,330,225];applyDet(1,false);
    BE.adds.push({manual_id:'new',box:[1,2,3,4],t0:0,t1:1,tref:0});
    const p=saveAndRender(),sent=calls.at(-1).body,result=ack(sent);
    if(KIND==='missing')delete result.geometry_rows;
    else if(KIND==='wrongbase')result.geometry_rows[0].base.cbox=[0,0,1,1];else result.geometry_rows[0].source_ref='other';
    await reply(result);await p;assert(BE.ov[0]);assert.equal(BE.adds.length,1);assert.equal(EDITS.enabled[1],false);
    assert(EDITS.submitted.everUncertain);assert.equal(calls.filter(c=>c.url.endsWith('/render')).length,0);""".replace('KIND',json.dumps(kind)))


@pytest.mark.parametrize('case',['busy','unresolved','changed','good'])
def test_discard_addition_preserves_other_additions_and_manual(case):
    run_js(EXACT+r"""const m=strictDraft();await inspected(m);const first={manual_id:'first',box:[1,2,30,40],t0:0,t1:1,tref:0};
    BE.adds.push(first,{manual_id:'second',box:[1,2,3,4]});MAN.push({manual_id:'manual'});
    if(CASE==='busy')EDITS.busy=true;if(CASE==='unresolved')EDITS.submitted={everUncertain:true};
    confirm=()=>{if(CASE==='changed')first.t1=2;return true};await reviewDiscard('add:first');
    assert.equal(BE.adds.length,CASE==='good'?1:2);assert.equal(BE.adds.at(-1).manual_id,'second');assert.equal(MAN.length,1);
    assert.equal(calls.filter(c=>c.url.endsWith('/detections')||c.url.endsWith('/render')).length,0);""".replace('CASE',json.dumps(case)))


def test_playback_restart_serial_fences_metadata_and_raf():
    run_js(EXACT+r"""const m=strictDraft();await inspected(m);var frames=[];requestAnimationFrame=f=>frames.push(f);
    Object.assign(m.vid,{readyState:0,paused:true,load(){},play:async()=>{m.vid.playCount=(m.vid.playCount||0)+1}});
    const first=beTogglePlay(),metadata=m.vid.onloadedmetadata;bePlayStop();const second=beTogglePlay();
    metadata();await first;assert.equal(m.vid.playCount,undefined,'old metadata played a restarted session');
    Object.assign(m.vid,{readyState:1,videoWidth:640,videoHeight:360});m.vid.onloadedmetadata();await second;
    assert.equal(m.vid.playCount,1);assert.equal(BE.playing,true);""")


def test_old_review_continuation_cannot_retire_same_be_reinspection():
    run_js(EXACT+r"""const m=strictDraft();const p=loadReview();showPanel('boxedit_rev');const next=exactMount();
    elements.get('review').contains=next.root.contains;await reply({duration:3,detections:[]});await p;
    assert.equal(BE_VIEW,next.view,'old review retired a newer editor intention');""")


def test_authoritative_geometry_rejection_preserves_audio_baseline():
    run_js(EXACT+r"""const m=strictDraft();await inspected(m);beCaptureGeometry(m.view,BE.raw[0]);BE.ov[0]=[130,85,330,225];
    BE.audioLoaded=true;BE.audio.push({t0:0,t1:1,mode:'mute'});const before=copyEdit(BE.audioSaved);
    const p=saveAndRender();await reply({error:'geometry_conflict'},409);await p;
    assert.equal(EDITS.submitted,null);assert.deepEqual(BE.audioSaved,before);assert.equal(BE.audio.length,1);""")


def test_discard_geometry_refuses_changed_baseline_family_during_confirmation():
    run_js(EXACT+r"""const m=strictDraft();await inspected(m);beCaptureGeometry(m.view,BE.raw[0]);BE.ov[0]=[130,85,330,225];
    confirm=()=>{BE.geometry[0].precondition.base.span[2]=.5;return true};await reviewDiscard('row:0');
    assert(BE.ov[0],'changed baseline family was discarded');assert.equal(BE.geometry[0].precondition.base.span[2],.5);""")



def test_exact_wrong_policy_is_blocked_before_decode():
    run_js(EXACT+r"""const m=strictDraft();beScrub();await reply(sample(0,{policy:'cfr-index-v1'}));
    assert.equal(candidates.length,0);assert.equal(beReady(m.view),false);assert.equal(liveURLs.size,0);""")


def test_hidden_canvas_cancels_incomplete_pointer_gesture():
    run_js(EXACT+r"""const m=strictDraft();await inspected(m);BE.drag={kind:'move',serial:m.view.serial};BE.addAnchor=[1,2];
    m.cv.getBoundingClientRect=()=>({width:0,height:0,left:0,top:0});m.cv.events.pointermove({clientX:10,clientY:10,pointerId:1});
    assert.equal(BE.drag,null);assert.equal(BE.addAnchor,null);""")


def test_owned_track_success_replaces_prior_refusal_status():
    run_js(EXACT+r"""const m=strictDraft();await inspected(m);elements.delete('review');
    BE.win=[1,2];await beTrackGo([10,20,40,60]);assert(EDITS.status.includes('requires'));
    var timers=[];setTimeout=f=>{timers.push(f);return 1};BE.win=[0,3];
    const p=beTrackGo([10,20,40,60]);await reply();await p;const poll=timers.shift()();
    await reply({state:'done',added:1});await reply({detections:[],audio_redactions:[]});await poll;
    assert(!EDITS.status.includes('requires'),'successful owned Track still reports prior refusal');""")


@pytest.mark.parametrize('replace',['mount','job'])
def test_detached_timeline_callbacks_cannot_edit_new_mount(replace):
    run_js(EXACT+r"""const m=strictDraft(),timeline=el();Object.assign(timeline,{clientWidth:300,
    getBoundingClientRect:()=>({left:0,top:0,width:300,height:72}),setPointerCapture(){},releasePointerCapture(){this.released=true}});
    elements.set('beTL',timeline);elements.set('beWinL',el());timeline.getContext=m.cv.getContext;tlHook();
    timeline.events.pointerdown({clientX:0,clientY:10,pointerId:7});assert(BE.tlDrag);
    if(REPLACE==='job')openJob('B');const next=exactMount();BE.win=[.5,2.5];BE.tlDrag={k:'w0'};
    timeline.events.pointermove({clientX:150,clientY:10,pointerId:7});timeline.events.pointerup({pointerId:7});
    assert.deepEqual(BE.win,[.5,2.5]);assert.equal(BE.tlDrag.k,'w0');assert.equal(timeline.released,true);""".replace('REPLACE',json.dumps(replace)))


def test_timeline_audio_remains_usable_while_exact_sample_loads():
    run_js(EXACT+r"""const m=strictDraft(),timeline=el();Object.assign(timeline,{clientWidth:300,
    getBoundingClientRect:()=>({left:0,top:0,width:300,height:72}),setPointerCapture(){},releasePointerCapture(){}});
    elements.set('beTL',timeline);timeline.getContext=m.cv.getContext;elements.set('beWinL',el());
    elements.set('beAMode',{value:'mute'});elements.set('beARm',el());tlHook();BE.muteArm=true;beScrub();
    timeline.events.pointerdown({clientX:100,clientY:60,pointerId:7});timeline.events.pointermove({clientX:200,clientY:60,pointerId:7});timeline.events.pointerup({pointerId:7});
    assert.equal(beReady(m.view),false);assert.deepEqual(BE.audio,[{t0:1,t1:2,mode:'mute'}]);""")


def test_timeline_release_cannot_clear_replaced_gesture_family():
    run_js(EXACT+r"""const m=strictDraft(),timeline=el();Object.assign(timeline,{clientWidth:300,
    getBoundingClientRect:()=>({left:0,top:0,width:300,height:72}),setPointerCapture(){},releasePointerCapture(){}});
    elements.set('beTL',timeline);timeline.getContext=m.cv.getContext;elements.set('beWinL',el());tlHook();
    timeline.events.pointerdown({clientX:0,clientY:10,pointerId:7});const replacement={k:'w1'};BE.tlDrag=replacement;
    timeline.events.pointerup({pointerId:7});assert.equal(BE.tlDrag,replacement);""")


def test_geometry_pointer_continuation_owns_selected_raw_row_and_pointer():
    run_js(EXACT+r"""const m=strictDraft();await inspected(m);const down=(id,x,y)=>m.cv.events.pointerdown({clientX:x,clientY:y,pointerId:id});
    down(1,100,60);m.cv.events.pointerup({pointerId:1});down(1,100,60);
    m.cv.events.pointermove({clientX:120,clientY:60,pointerId:2});assert.equal(Object.keys(BE.ov).length,0,'another pointer moved the selected row');
    m.cv.events.pointerup({pointerId:2});assert(BE.drag,'another pointer ended current drag');
    m.cv.events.pointermove({clientX:110,clientY:65,pointerId:1});assert(BE.ov[0]);""")



@pytest.mark.parametrize('status', [409, 423, 500])
@pytest.mark.parametrize('read_failure', [False, True], ids=['body-exhausted', 'body-read-failed'])
def test_exact_error_body_retains_slot_across_mounts(status, read_failure):
    run_js(EXACT+r"""const old=strictDraft();const first=beScrub();
    elements.get('beT').value=.2;beScrub();
    let exhausted,failed,bodyReads=0,jsonReads=0;
    queue.shift().resolve({ok:false,status:STATUS,
      text(){bodyReads++;return new Promise((resolve,reject)=>{exhausted=resolve;failed=reject})},
      json(){jsonReads++;throw Error('non-JSON middleware refusal must not be parsed')}});
    await tick();
    assert.equal(calls.length,1,'non-success headers released the slot before its delayed body settled');
    assert.equal(EDIT_SAMPLE_IO.active.view,old.view);
    openJob('B');exactMount();elements.get('beT').value=.4;beScrub();
    openJob('A');const latest=exactMount();elements.get('beT').value=.7;beScrub();
    elements.get('beT').value=.8;beScrub();const statusBefore=elements.get('beL').textContent;
    assert.equal(calls.length,1);assert.equal(bodyReads,1);assert.equal(jsonReads,0);
    assert.equal(candidates.length,0);assert.equal(liveURLs.size,0);assert.equal(beReady(latest.view),false);
    if(READ_FAILURE)failed(Error('error response stream failed'));
    else exhausted('<html>non-JSON middleware refusal</html>');
    await tick();await first;
    assert.equal(calls.length,2);assert(calls[1].url.endsWith('A/edit_sample?t=0.8'));
    assert.equal(elements.get('beL').textContent,statusBefore,'stale error changed the latest mount status');
    assert.equal(candidates.length,0);assert.equal(liveURLs.size,0);
    await reply(sample(.8));assert.equal(candidates.length,1);candidates.shift().resolve();await tick();
    assert(beReady(latest.view));assert.equal(latest.view.readySample.sample.requested_s,.8);
    beUnmount();assert.equal(liveURLs.size,0);
    """.replace('STATUS',str(status)).replace('READ_FAILURE',str(read_failure).lower()))


@pytest.mark.parametrize('status', [409, 423, 500])
@pytest.mark.parametrize('read_failure', [False, True], ids=['body-exhausted', 'body-read-failed'])
def test_exact_current_error_body_settlement_keeps_http_status(status, read_failure):
    run_js(EXACT+r"""const current=strictDraft();const pending=beScrub();let exhausted,failed;
    queue.shift().resolve({ok:false,status:STATUS,
      text:()=>new Promise((resolve,reject)=>{exhausted=resolve;failed=reject}),
      json:()=>{throw Error('non-JSON middleware refusal must not be parsed')}});
    await tick();assert(EDIT_SAMPLE_IO.active,'current error released the slot before its body settled');
    assert.equal(calls.length,1);assert.equal(candidates.length,0);assert.equal(liveURLs.size,0);
    assert.equal(beReady(current.view),false);
    if(READ_FAILURE)failed(Error('error response stream failed'));
    else exhausted('<html>non-JSON middleware refusal</html>');
    await tick();await pending;
    assert.equal(EDIT_SAMPLE_IO.active,null);assert.equal(EDIT_SAMPLE_IO.wanted,null);
    assert.equal(calls.length,1);assert.equal(candidates.length,0);assert.equal(liveURLs.size,0);
    assert.equal(beReady(current.view),false);
    assert(elements.get('beL').textContent.includes('HTTP '+STATUS));
    assert(elements.get('beL').textContent.includes('Inspect again to retry'));
    """.replace('STATUS',str(status)).replace('READ_FAILURE',str(read_failure).lower()))


@pytest.mark.parametrize('held', ['save_ack', 'render_ack'])
def test_older_save_completion_keeps_newer_same_job_editor_mount(held):
    run_js(MOUNT + r"""openJob('A');const old=mountIn('review');
    const pending=saveAndRender();
    if(HELD==='render_ack')await reply();
    showPanel('boxedit_rev');const newer=mountIn('review');
    if(HELD==='save_ack')await reply();
    await reply();await pending;
    assert.equal(BE_VIEW,newer.view,'older save completion retired the newer editor');
    assert.equal(newer.view.observer.disconnected,false);
    assert.equal(newer.vid.paused,false);
    assert.equal(newer.root.detached,undefined);
    """.replace('HELD',json.dumps(held)))


@pytest.mark.parametrize('newer', ['editor_metadata', 'manual_review'])
def test_older_track_status_cannot_preempt_newer_pending_intent(newer):
    run_js(EXACT + r"""const old=strictDraft();await inspected(old);
    var timers=[];setTimeout=f=>{timers.push(f);return 1};
    const start=beTrackGo([10,20,40,60]);await reply();await start;
    const poll=timers.shift()(),status=queue.shift();
    const pending=NEWER==='editor_metadata'?loadBoxEdit(1):loadReview();
    const newer=queue.shift();
    assert.equal(old.view.trackLaunch,null,'newer intent did not retire the old Track control immediately');
    status.resolve(response({state:'done',added:1}));await tick();
    assert.equal(queue.length,0,'older Track status started a competing report or review request');
    assert.equal(BE_VIEW,old.view,'older Track status retired the editor before newer intent settled');
    if(NEWER==='editor_metadata'){
      newer.resolve(response({duration:3}));await tick();assert(calls.at(-1).url.endsWith('/report'));
      await reply({detections:[],audio_redactions:[]});await pending;
      assert.notEqual(BE_VIEW,old.view,'newer editor failed to mount');
    }else{
      newer.resolve(response({duration:3,detections:[]}));await tick();await pending;
      assert.equal(DUR,3,'newer manual review failed to publish');
    }
    await poll;
    """.replace('NEWER',json.dumps(newer)))


@pytest.mark.parametrize('navigation', ['remount', 'away-return'])
@pytest.mark.parametrize('result', ['success', 'failure'])
@pytest.mark.parametrize('timing', ['timer', 'body'])
def test_admitted_track_survives_view_change_and_offers_current_report(navigation, result, timing):
    run_js(EXACT + r"""const old=strictDraft();await inspected(old);const owner=EDITS;
    owner.enabled[17]=false;MAN.push({manual_id:'keep'});
    const trackStatus=el(),trackActions=el();elements.set('reviewTrackStatus',trackStatus);elements.set('reviewTrackActions',trackActions);
    var timers=new Map(),timerId=0;setTimeout=f=>{const n=++timerId;timers.set(n,f);return n};clearTimeout=n=>timers.delete(n);
    const start=beTrackGo([10,20,40,60]);await reply();await start;
    assert.equal(timers.size,1,'admitted Track did not schedule status');
    let poll,otherStatus;
    if(TIMING==='body'){poll=[...timers.values()][0]();timers.clear();}
    if(NAV==='remount'){showPanel('boxedit_rev');exactMount();}
    else {openJob('B');otherStatus=trackStatus.textContent;}
    if(TIMING==='timer'){
      assert.equal(timers.size,1,'view retirement cancelled the only admitted Track status poll');
      poll=[...timers.values()][0]();timers.clear();
    }
    await reply(RESULT==='success'?{state:'done',added:2}:{state:'done',added:0,error:'synthetic tracking failure'});await poll;
    if(NAV==='away-return'){assert.equal(CUR,'B');assert.equal(trackStatus.textContent,otherStatus,'Track result changed another job UI');openJob('A');exactMount();}
    assert.equal(EDITS,owner);assert.equal(EDITS.enabled[17],false);assert.equal(MAN[0].manual_id,'keep');
    assert(trackStatus.textContent.includes(RESULT==='success'?'2':'synthetic tracking failure'),trackStatus.textContent);
    if(RESULT==='success'){
      const button=trackActions.children.findLast(x=>x.textContent==='Review tracked positions');
      assert(button,'missing deliberate tracked-result review');
      const review=button.onclick();await reply({duration:3,detections:[{i:7,category:'manual',text:'tracked object',
       enabled:true,t_start:0,t_end:2,person:-1,track:-1}]});await review;
      assert(REVIEW_META.byId.has(7),'current tracked row missing from refreshed report');
      assert.equal(EDITS.enabled[17],false);assert.equal(MAN[0].manual_id,'keep');
    }
    """.replace('NAV',json.dumps(navigation)).replace('RESULT',json.dumps(result)).replace('TIMING',json.dumps(timing)))


def test_track_admission_ack_after_newer_view_still_monitors_status():
    run_js(EXACT + r"""const old=strictDraft();await inspected(old);
    const trackStatus=el();elements.set('reviewTrackStatus',trackStatus);elements.set('reviewTrackActions',el());
    var timers=new Map(),timerId=0;setTimeout=f=>{const n=++timerId;timers.set(n,f);return n};clearTimeout=n=>timers.delete(n);
    const start=beTrackGo([10,20,40,60]);showPanel('boxedit_rev');const newer=exactMount();
    await reply();await start;assert.equal(BE_VIEW,newer.view);
    assert.equal(timers.size,1,'late admission ACK lost the job-owned status poll');
    const poll=[...timers.values()][0]();timers.clear();await reply({state:'done',added:1});await poll;
    assert.equal(BE_VIEW,newer.view);assert(trackStatus.textContent.includes('1'));
    """)



def test_detached_track_status_failure_can_be_checked_again_without_new_track():
    run_js(EXACT+r"""const old=strictDraft();await inspected(old);
    const status=el(),actions=el();elements.set('reviewTrackStatus',status);elements.set('reviewTrackActions',actions);
    var timers=new Map(),timerId=0;setTimeout=f=>{const n=++timerId;timers.set(n,f);return n};clearTimeout=n=>timers.delete(n);
    const started=beTrackGo([10,20,40,60]);await reply();await started;
    showPanel('boxedit_rev');const newer=exactMount();
    const first=[...timers.values()][0]();timers.clear();queue.shift().reject(Error('offline'));await tick();await first;
    assert(status.textContent.includes('offline'));assert.equal(BE_VIEW,newer.view);
    const check=actions.children.findLast(x=>x.textContent==='Check tracking status');assert(check);
    const retry=check.onclick();await reply({state:'running',added:0});await retry;
    assert.equal(timers.size,1);const final=[...timers.values()][0]();timers.clear();await reply({state:'done',added:3});await final;
    assert(status.textContent.includes('3'));assert.equal(calls.filter(c=>c.url.endsWith('/track_object')).length,1);
    assert(actions.children.some(x=>x.textContent==='Review tracked positions'));
    """)


def test_deleted_job_cannot_publish_late_track_status_into_reopened_job():
    run_js(EXACT+r"""const old=strictDraft();await inspected(old);
    const status=el();elements.set('reviewTrackStatus',status);elements.set('reviewTrackActions',el());
    var timers=new Map(),timerId=0;setTimeout=f=>{const n=++timerId;timers.set(n,f);return n};clearTimeout=n=>timers.delete(n);
    const started=beTrackGo([10,20,40,60]);await reply();await started;
    const polling=[...timers.values()][0]();timers.clear();const oldStatus=queue.shift();
    confirm=()=>true;const deleting=delJob('A');await reply();await deleting;
    openJob('A');const fresh=EDITS;oldStatus.resolve(response({state:'done',added:9}));await tick();await polling;
    assert.equal(EDITS,fresh);assert(!status.textContent.includes('9'));assert.equal(fresh.track,undefined);
    """)


def test_uncertain_track_ack_exposes_status_check_and_preserves_job_drafts():
    run_js(EXACT+r"""const old=strictDraft();await inspected(old);const owner=EDITS;
    const status=el(),actions=el();elements.set('reviewTrackStatus',status);elements.set('reviewTrackActions',actions);
    owner.enabled[2]=false;MAN.push({manual_id:'kept'});
    var timers=new Map(),timerId=0;setTimeout=f=>{const n=++timerId;timers.set(n,f);return n};clearTimeout=n=>timers.delete(n);
    const start=beTrackGo([10,20,40,60]);showPanel('boxedit_rev');const next=exactMount();
    queue.shift().reject(Error('lost acknowledgement'));await tick();await start;
    assert(status.textContent.includes('may have started'));assert.equal(BE_VIEW,next.view);
    const check=actions.children.findLast(x=>x.textContent==='Check tracking status');assert(check);
    const retry=check.onclick();await reply({state:'running',added:0});await retry;
    const poll=[...timers.values()][0]();timers.clear();await reply({state:'done',added:1});await poll;
    assert(status.textContent.includes('1'));assert.equal(EDITS,owner);assert.equal(EDITS.enabled[2],false);assert.equal(MAN[0].manual_id,'kept');
    assert.equal(calls.filter(c=>c.url.endsWith('/track_object')).length,1);
    """)


def test_review_while_track_status_uncertain_does_not_lose_status_owner():
    run_js(EXACT+r"""const old=strictDraft();await inspected(old);const owner=EDITS;
    const status=el(),actions=el();elements.set('reviewTrackStatus',status);elements.set('reviewTrackActions',actions);
    const start=beTrackGo([10,20,40,60]);showPanel('boxedit_rev');exactMount();
    queue.shift().reject(Error('lost acknowledgement'));await tick();await start;
    const button=actions.children.findLast(x=>x.textContent==='Review tracked positions');assert(button);
    const review=button.onclick();await reply({duration:3,detections:[]});await review;
    assert.equal(EDITS,owner);assert(owner.track,'reviewing before Track settled discarded its status owner');
    assert(status.textContent.includes('may have started'));
    """)


def test_stale_tracking_action_cannot_discard_restarted_status_check():
    run_js(EXACT+r"""const old=strictDraft();await inspected(old);const owner=EDITS;
    const actions=el();elements.set('reviewTrackStatus',el());elements.set('reviewTrackActions',actions);
    var timers=new Map(),timerId=0;setTimeout=f=>{const n=++timerId;timers.set(n,f);return n};clearTimeout=n=>timers.delete(n);
    const started=beTrackGo([10,20,40,60]);await reply();await started;showPanel('boxedit_rev');exactMount();
    const first=[...timers.values()][0]();timers.clear();queue.shift().reject(Error('offline'));await tick();await first;
    const check=actions.children.findLast(x=>x.textContent==='Check tracking status');
    const dismiss=actions.children.findLast(x=>x.textContent==='Dismiss tracking notice');assert(check&&dismiss);
    const retry=check.onclick();dismiss.onclick();assert(owner.track,'stale dismiss dropped an active status check');
    await reply({state:'running',added:0});await retry;const finish=[...timers.values()][0]();timers.clear();
    await reply({state:'done',added:2});await finish;const count=calls.length;await check.onclick();
    assert.equal(calls.length,count,'stale check replaced completed Track result');
    """)


@pytest.mark.parametrize('status', [500, 503])
def test_track_server_error_after_detachment_remains_unconfirmed_and_checkable(status):
    run_js(EXACT+r"""const old=strictDraft();await inspected(old);const owner=EDITS;
    const status=el(),actions=el();elements.set('reviewTrackStatus',status);elements.set('reviewTrackActions',actions);
    const start=beTrackGo([10,20,40,60]);showPanel('boxedit_rev');const next=exactMount();
    await reply({error:'server failed after admission'},STATUS);await start;
    assert.equal(BE_VIEW,next.view);assert.equal(EDITS,owner);
    assert(status.textContent.includes('may have started'),'server error was treated as proof the operation did not start');
    assert(actions.children.some(x=>x.textContent==='Check tracking status'));
    assert(actions.children.some(x=>x.textContent==='Review tracked positions'));
    """.replace('STATUS',str(status)))



def test_track_authoritative_client_refusal_reports_failure_without_polling():
    run_js(EXACT+r"""const old=strictDraft();await inspected(old);
    const status=el(),actions=el();elements.set('reviewTrackStatus',status);elements.set('reviewTrackActions',actions);
    const start=beTrackGo([10,20,40,60]);await reply({error:'sample_conflict'},409);await start;
    assert(status.textContent.includes('sample_conflict'));
    assert(!actions.children.some(x=>x.textContent==='Check tracking status'));
    assert(actions.children.some(x=>x.textContent==='Dismiss tracking notice'));
    assert.equal(calls.filter(c=>c.url.endsWith('/track_status')).length,0);
    """)
