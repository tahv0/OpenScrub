"""Execute production polling functions when local Chromium is unavailable.

The companion browser tests exercise the full Flask/page interaction in CI.
Here only the browser/transport boundary is replaced, so a stuck promise,
stale completion, or blocked follow-up remains a failure of production code.
"""
import json
import shutil
import subprocess

import pytest

import openscrub_web as web


def script_between(start, end):
    return web.APP_JS[web.APP_JS.index(start):web.APP_JS.index(end)]


def run_node(source):
    if not shutil.which('node'):
        pytest.skip('Node required')
    result = subprocess.run(['node', '-e', source], capture_output=True,
                            text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('stage', ['fetch', 'body'])
def test_request_deadline_settles_even_when_transport_ignores_abort(stage):
    request = script_between('async function reviewRequest(', 'function clearReviewPreviews(')
    run_node("const assert=require('node:assert/strict');\n" + request + "\n" + r"""
const never=new Promise(()=>{});
global.fetch=async()=>STAGE==='fetch'?never:{ok:true,json:()=>never};
(async()=>{
 const result=await Promise.race([
   reviewRequest('/fixture',{timeoutMs:20}).then(()=> 'unexpected success',e=>e.name),
   new Promise(resolve=>setTimeout(()=>resolve('still pending'),150))
 ]);
 assert.equal(result,'TimeoutError','the deadline must release the caller, including body reads');
})().catch(e=>{console.error(e);process.exitCode=1;});
""".replace('STAGE', json.dumps(stage)))


def test_parent_cancellation_settles_an_unresponsive_body():
    request = script_between('async function reviewRequest(', 'function clearReviewPreviews(')
    run_node("const assert=require('node:assert/strict');\n" + request + "\n" + r"""
global.fetch=async()=>({ok:true,json:()=>new Promise(()=>{})});
(async()=>{
 const controller=new AbortController();
 const pending=reviewRequest('/fixture',{signal:controller.signal,timeoutMs:100});
 controller.abort();
 const result=await Promise.race([
   pending.then(()=> 'unexpected success',e=>e.name),
   new Promise(resolve=>setTimeout(()=>resolve('still pending'),150))
 ]);
 assert.equal(result,'AbortError','navigation must not await a body that ignores cancellation');
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


def test_hidden_poll_does_not_leave_a_completed_promise_blocking_future_polls():
    refresh = script_between('async function refresh(){', 'async function refreshJob(')
    run_node(r"""
const assert=require('node:assert/strict');
let CUR='alpha',JOBVIEW=1,REFRESHCTRL=null,REFRESHFLIGHT=null,REFRESHFAILURES=0;
let POLL=null,SHELLPH='rendering',calls=0;
const document={hidden:true,getElementById(){return null}};
function clearTimeout(){};function setTimeout(){return 1};
async function refreshJob(){calls++};
""" + refresh + r"""
(async()=>{
 await refresh();
 assert.equal(calls,0,'hidden polling skips the request');
 document.hidden=false;
 await refresh();
 assert.equal(calls,1,'a hidden cycle must not permanently occupy the polling slot');
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


def test_job_switch_starts_a_new_poll_without_waiting_for_stale_completion():
    open_job = script_between('async function openJob(', 'function shellHtml(')
    refresh = script_between('async function refresh(){', 'async function refreshJob(')
    run_node(r"""
const assert=require('node:assert/strict');
let CUR='alpha',JOBVIEW=1,REFRESHCTRL=null,REFRESHFLIGHT=null,REFRESHFAILURES=0;
let POLL=null,SHELLPH='rendering',EN={},MAN=[],PHIST=[],PHPH='',LOGN=0;
let REVIEW_VERSION=0,REVIEW_SAVED=0;
const document={hidden:false,getElementById(){return null}},detail={innerHTML:''};
function clearReviewPreviews(){};async function flushPlateSaves(){return true};
function closePlateQuad(){return true};function plateUnloadGuard(){};
function clearTimeout(){};function setTimeout(){return 1};
const pending=[],calls=[];
function refreshJob(id){calls.push(id);return new Promise(resolve=>pending.push(resolve))};
""" + open_job + refresh + r"""
(async()=>{
 const stale=refresh();
 for(let n=0;n<20;n++)refresh();
 assert.deepEqual(calls,['alpha'],'one selected-job request at a time');
 await openJob('beta');
 assert.deepEqual(calls,['alpha','beta'],'switching jobs must start beta before alpha settles');
 pending[0]();await stale;
 refresh();
 assert.deepEqual(calls,['alpha','beta'],'late alpha completion must not release beta’s slot');
 pending[1]();await REFRESHFLIGHT;
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


@pytest.mark.parametrize('event', ['visibilitychange', 'focus', 'pageshow', 'online'])
def test_lifecycle_wake_releases_stale_poll_and_backoff(event):
    open_job = script_between('async function openJob(', 'function shellHtml(')
    refresh = script_between('async function refresh(){', 'async function refreshJob(')
    lifecycle = script_between('loadPersist();loadCertInfo();', 'function showView()')
    run_node(r"""
const assert=require('node:assert/strict');
let CUR='alpha',JOBVIEW=1,REFRESHCTRL=null,REFRESHFLIGHT=null,REFRESHFAILURES=3;
let POLL=null,SHELLPH='rendering',EN={},MAN=[],PHIST=[],PHPH='',LOGN=0;
let JOBSFLIGHT=null,JOBSFAILURES=3,JOBSRETRYAT=Date.now()+30000,JOBSJSON='[]';
let REVIEW_VERSION=0,REVIEW_SAVED=0,listCalls=0;
const events={},detail={innerHTML:''};
function listen(name,fn){(events[name]??=[]).push(fn)};
const document={hidden:false,getElementById(){return null},addEventListener:listen};
const window={addEventListener:listen};
function loadPersist(){};function loadCertInfo(){};function refreshLearnedModels(){};
function clearReviewPreviews(){};async function flushPlateSaves(){return true};
function closePlateQuad(){return true};function plateUnloadGuard(){};
function clearTimeout(){};function setTimeout(){return 1};function setInterval(){};
function loadJobs(){listCalls++;return Promise.resolve()};
const pending=[],calls=[];
function refreshJob(id){calls.push(id);return new Promise(resolve=>pending.push(resolve))};
""" + open_job + refresh + lifecycle + r"""
(async()=>{
 const stale=refresh();
 if(EVENT==='visibilitychange'){
   document.hidden=true;for(const fn of events.visibilitychange||[])fn();
   assert.equal(calls.length,1,'a hidden page must not start more polling');
   document.hidden=false;
 }
 for(const fn of events[EVENT]||[])fn();
 await new Promise(setImmediate);
 assert.deepEqual(calls,['alpha','alpha'],'waking must start a fresh poll without waiting for the old one');
 assert.equal(listCalls,2,'waking refreshes the jobs list as well');
 assert.equal(JOBSRETRYAT,0,'a new connection must not inherit the old backoff');
 pending[0]();await stale;
 refresh();assert.equal(calls.length,2,'stale completion must not clear the replacement poll');
 pending[1]();await REFRESHFLIGHT;
})().catch(e=>{console.error(e);process.exitCode=1;});
""".replace('EVENT', json.dumps(event)))


def test_late_jobs_list_response_cannot_overwrite_the_reconnected_list():
    load = script_between('async function loadJobs(){', 'async function retryJob(')
    lifecycle = script_between('loadPersist();loadCertInfo();', 'function showView()')
    run_node(r"""
const assert=require('node:assert/strict');
let JOBSFLIGHT=null,JOBSFAILURES=0,JOBSRETRYAT=0,JOBSJSON='',REFRESHFAILURES=0;
const jobs={innerHTML:''},pending=[];
const document={hidden:false,getElementById(){return null},addEventListener(){}};
const window={addEventListener(){}};
function loadPersist(){};function loadCertInfo(){};function refreshLearnedModels(){};
function stopJobPolling(){};function refresh(){};function setInterval(){};
function reviewRequest(){return new Promise(resolve=>pending.push(resolve))};
""" + script_between('function sectionEscape(', 'function sectionSeconds(') + load + lifecycle + r"""
(async()=>{
 const stale=loadJobs();
 resumeJobPolling();
 const current=loadJobs();
 pending[1]({data:[{id:'alpha',name:'Current fixture',phase:'rendering'}]});await current;
 assert.ok(jobs.innerHTML.includes('Current fixture'));
 pending[0]({data:[{id:'alpha',name:'Stale fixture',phase:'queued'}]});await stale;
 assert.ok(jobs.innerHTML.includes('Current fixture'),'late stale list must not repaint current jobs');
 assert.ok(!jobs.innerHTML.includes('Stale fixture'));
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


def job_view_harness():
    return r"""
const assert=require('node:assert/strict');
let CUR='alpha',JOBVIEW=1,SHELLPH='rendering',PHPH='rendering',PHIST=[],LOGN=0,EXPORT_NAMES={};
const nodes=new Map();
const document={getElementById(id){
 if(!nodes.has(id))nodes.set(id,{textContent:'',innerHTML:'',style:{},dataset:{},value:0,
   removeAttribute(name){delete this[name]},
   scrollTop:100,clientHeight:100,scrollHeight:200});
 return nodes.get(id);
}};
const job={id:'alpha',name:'Synthetic job',phase:'rendering',progress:.4,eta:null,
  error:null,stats:{},has_output:false,download_name:'fixture.mp4',report_name:'fixture.json'};
const signal=new AbortController().signal;
function renderWorkProgress(){};async function loadSectionsPanel(){};
// A pending thumbnail queue, like the jobs list, must not stall job polling.
function refreshPendingFindings(){return new Promise(()=>{})};
function showTrainingResult(j){assert.notEqual(j.kind,'model_training')};
""" + script_between('async function refreshJob(', '\nfunction sectionTime(')


def test_selected_job_poll_does_not_await_jobs_list():
    run_node(job_view_harness() + r"""
function loadJobs(){return new Promise(()=>{})};
async function reviewRequest(url){return {data:url.includes('/log?')?{from:0,len:1,lines:['Progress is moving']}:job}};
(async()=>{
 const result=await Promise.race([
   refreshJob('alpha',1,signal).then(()=> 'finished'),
   new Promise(resolve=>setTimeout(()=>resolve('blocked by list'),100))
 ]);
 assert.equal(document.getElementById('prog').value,.4);
 assert.equal(document.getElementById('log').textContent,'Progress is moving');
 assert.equal(result,'finished','the selected job must schedule its next poll independently of the jobs list');
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


def test_log_tail_stays_bounded_and_rewinds_after_server_reset():
    run_node(job_view_harness() + r"""
function loadJobs(){return Promise.resolve()};
let nextLog={from:0,len:1,lines:['Started']};
async function reviewRequest(url){return {data:url.includes('/log?')?nextLog:job}};
(async()=>{
 await refreshJob('alpha',1,signal);
 nextLog={from:1,len:501,lines:Array.from({length:500},(_,i)=>'Synthetic line '+i)};
 await refreshJob('alpha',1,signal);
 let shown=document.getElementById('log').textContent;
 assert.equal(shown.split('\n').at(-1),'Synthetic line 499');
 assert.ok(shown.split('\n').length<=400,'catchup must not grow the log DOM indefinitely');
 assert.equal(LOGN,501);
 nextLog={from:0,len:0,lines:[]};
 await refreshJob('alpha',1,signal);
 assert.equal(document.getElementById('log').textContent,'','empty reset clears the old run');
 assert.equal(LOGN,0);
 nextLog={from:0,len:1,lines:['Restarted']};
 await refreshJob('alpha',1,signal);
 nextLog={from:1,len:1,lines:[]};
 await refreshJob('alpha',1,signal);
 assert.equal(document.getElementById('log').textContent,'Restarted');
 assert.equal(LOGN,1);
 nextLog={from:1,len:2,lines:['x'.repeat(300000)]};
 await refreshJob('alpha',1,signal);
 assert.ok(document.getElementById('log').textContent.length<=200000,'a huge single line must also stay bounded');
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


def test_cancelled_review_response_cannot_rebuild_the_same_job_view():
    review = script_between('async function loadReview(', 'function detChoices(')
    run_node(r"""
const assert=require('node:assert/strict');
let CUR='alpha',JOBVIEW=1,SHELLPH='review',DUR=0,EN={},TRKMEM={},REVIEW_BASE=null;
let VLBL={},VLBLJOB='alpha',LEARNING_SELECTION_JOB='alpha',LEARNING_SELECTION=null;
let CONFIRM_CHAIN=Promise.resolve();const CONFIRM_FAILED=new Map();
let release,inserted=[];
const panel={};
const document={getElementById(id){return id==='review'&&inserted.length?panel:null}};
const detail={insertAdjacentHTML(position,html){inserted.push(html)}};
async function flushPlateSaves(){return true};function closePlateQuad(){return true};
function clearReviewPreviews(){};async function showPanel(){return true};
function initMarquee(){};function initReviewPreviews(){};
function reviewRequest(){return new Promise(resolve=>{release=resolve})};
const report={detections:[],learning:null,refinement:null,indexed_frames:false,
  frame_count:30,fps:30,duration:1};
""" + review + r"""
(async()=>{
 const controller=new AbortController();
 const pending=loadReview(controller.signal,'review');
 await new Promise(setImmediate);
 controller.abort();SHELLPH='rendering';
 release({data:report});await pending;
 assert.equal(inserted.length,0,'an aborted review response must not rebuild a newer view for the same job');
 assert.equal(DUR,0,'stale review metadata must also be discarded');
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


def test_aborted_review_transition_is_retried_on_the_next_poll():
    run_node(job_view_harness() + r"""
function loadJobs(){return Promise.resolve()};
job.phase='review';
async function reviewRequest(url){return {data:url.includes('/log?')?{from:0,len:0,lines:[]}:job}};
let reviewCalls=0,release;
function loadReview(){
 reviewCalls++;
 return reviewCalls===1?new Promise(resolve=>{release=resolve}):Promise.resolve(true);
};
(async()=>{
 const controller=new AbortController();
 const pending=refreshJob('alpha',1,controller.signal);
 await new Promise(setImmediate);
 controller.abort();release(true);await pending;
 await refreshJob('alpha',1,signal);
 assert.equal(reviewCalls,2,'an interrupted transition must not mark an unloaded review as complete');
 assert.equal(SHELLPH,'review');
})().catch(e=>{console.error(e);process.exitCode=1;});
""")
