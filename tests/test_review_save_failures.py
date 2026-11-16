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
const ctx=vm.createContext({elements,console,Set,Map,JSON,Date,Math,Promise,
 document:{getElementById:id=>elements.get(id)||null,querySelector:s=>elements.get(s.slice(1))||null,
 querySelectorAll:()=>[],addEventListener(){},createElement:el},
 detail:elements.get('detail'),window:{},setInterval:()=>1,clearInterval(){},setTimeout(){},
 confirm:()=>false,alert(){},fetch:async()=>({ok:true,json:async()=>({})})});
// Skip startup I/O only; every function under test is evaluated from the Python string.
vm.runInContext(SOURCE.slice(0,SOURCE.indexOf('loadPersist();loadCertInfo();loadJobs();setInterval(loadJobs,5000);')).replace(/^refreshModelPanel\(\);renderTiers\(\);$/m,''),ctx);
vm.runInContext(`
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
    let played=false;const video=elements.get('beVid');Object.assign(video,{readyState:0,play:async()=>{played=true},pause(){}});
    const p=beTogglePlay();openJob('B');video.onloadedmetadata();await p;
    if(played)throw Error('old video started after job switch');""")
