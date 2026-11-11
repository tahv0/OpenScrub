"""Section UI races and frame boundaries using functions from the served PAGE."""
import json
import re
import shutil
import subprocess

import pytest

import openscrub_web as web
import video_sections


PAGE_JS = '\n'.join(re.findall(r'<script>(.*?)</script>', web.PAGE, re.S))


def page_between(start, end):
    return PAGE_JS[PAGE_JS.index(start):PAGE_JS.index(end)]


def run_page(source):
    if not shutil.which('node'):
        pytest.skip('Node required')
    result = subprocess.run(['node', '-e', source], capture_output=True,
                            text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def creation_harness():
    return r"""
const assert=require('node:assert/strict');
let CUR='parent',JOBVIEW=1,release,posts=[];
const fields={sectionName:{value:'Original interval'},sectionStart:{value:'1'},
 sectionEnd:{value:'2'},sectionsPanel:{dataset:{}}};
const document={getElementById:id=>fields[id]};
const button={disabled:false};
function saveSectionReview(){return new Promise(resolve=>{release=resolve})};
async function reviewRequest(url,options){posts.push({url,body:JSON.parse(options.body)});return {data:{}}};
function refresh(){};function alert(error){throw new Error(error)};
""" + page_between('function sectionSeconds(', 'async function loadSectionsPanel(') + page_between(
        'async function createSection(', 'async function sectionAction(')


@pytest.mark.parametrize('navigate', ["CUR='other';JOBVIEW++;", 'JOBVIEW++;'])
def test_create_section_abandons_a_view_changed_while_saving(navigate):
    run_page(creation_harness() + "\n(async()=>{\nconst pending=createSection(button);\n" + navigate + r"""
 fields.sectionName.value='New view interval';
 release(true);await pending;
 assert.deepEqual(posts,[],'a pending section action must never target a newly opened view');
 assert.equal(button.disabled,false);
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


def test_create_section_snapshots_the_clicked_range_before_saving():
    run_page(creation_harness() + r"""
(async()=>{
 const pending=createSection(button);
 fields.sectionName.value='Later edit';fields.sectionStart.value='2';fields.sectionEnd.value='3';
 release(true);await pending;
 assert.deepEqual(posts,[{url:'api/jobs/parent/sections',body:{name:'Original interval',start:1,end:2}}]);
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


@pytest.mark.parametrize('with_review', [False, True])
def test_section_action_saves_manual_boxes_and_audio_without_card_changes(with_review):
    run_page(r"""
const assert=require('node:assert/strict');
let CUR='parent',JOBVIEW=1,JOBSJSON='',SHELLPH='done',PLATE_REVIEW_BUSY=false;
let REVIEW_VERSION=0,REVIEW_SAVED=0,REVIEW_BASE=null,MAN=[];
const PLATE_EDITS=new Map(),posts=[];
let BE={adds:[{t0:1,t1:2,tref:1,box:[10,10,20,20]}],ov:{},times:{},
 audio:[{t0:1,t1:2,mode:'mute'}],tlspans:[],pending:false,drag:null};
const document={getElementById(id){return id==='beCv'||(HAS_REVIEW&&id==='review')?{}:null}};
async function flushPlateSaves(){return true};async function beRefresh(){return true};
function reviewChoicesPending(){return false};function reviewChoiceDelta(){return {enabled:{},verified_labels:{}}};
function reviewSaveStatus(){};function plateUnloadGuard(){};function alert(error){throw new Error(error)};
async function openJob(){};
async function reviewRequest(url,options){posts.push({url,body:JSON.parse(options.body)});return {data:{ok:true}}};
""".replace('HAS_REVIEW', json.dumps(with_review)) + page_between(
        'async function saveAndRender(', 'async function loadPersist(') + page_between(
        'async function saveSectionReview(', '\nlet BE=') + r"""
(async()=>{
 await sectionAction('parent','middle','approve','',{disabled:false});
 assert.deepEqual(posts.map(p=>p.url),['api/jobs/parent/detections','api/jobs/parent/sections/middle/approve']);
 assert.deepEqual(posts[0].body.manual,[{t_start:1,t_end:2,t_ref:1,screen_box:[10,10,20,20]}]);
 assert.deepEqual(posts[0].body.audio,[{t0:1,t1:2,mode:'mute'}]);
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


def test_section_save_does_not_save_an_editor_opened_during_corner_flush():
    run_page(r"""
const assert=require('node:assert/strict');
let CUR='parent',JOBVIEW=1,release,saves=0;
const document={getElementById(){return {}}};
function flushPlateSaves(){return new Promise(resolve=>{release=resolve})};
function reviewChoicesPending(){return true};async function saveAndRender(){saves++;return true};
""" + page_between('async function saveSectionReview(', 'async function createSection(') + r"""
(async()=>{
 const pending=saveSectionReview();CUR='other';JOBVIEW++;release(true);
 assert.equal(await pending,false);assert.equal(saves,0,'the new editor must not be saved by the old action');
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


def view_harness(phase='error', role='export'):
    job = dict(id='export', name='Synthetic section export', phase=phase, progress=.4,
               eta=None, error=None, stats={}, has_output=True,
               download_name='fixture.mp4', report_name='fixture.json',
               section=dict(role=role, parent_id='parent', section_id='middle'))
    return r"""
const assert=require('node:assert/strict');
let CUR='export',JOBVIEW=1,SHELLPH='old',PHPH='old',PHIST=[],LOGN=0,EXPORT_NAMES={};
let JOBSFLIGHT=null,JOBSFAILURES=0,JOBSRETRYAT=0,JOBSJSON='';
const CAN_SAVE_AS=false,opened=[],posts=[],jobs={innerHTML:''},nodes=new Map();
const document={hidden:false,getElementById(id){
 if(!nodes.has(id))nodes.set(id,{textContent:'',innerHTML:'',style:{},dataset:{},value:0,
 removeAttribute(name){delete this[name]},scrollTop:0,clientHeight:100,scrollHeight:100});
 return nodes.get(id);
}};
const signal=new AbortController().signal;
function renderWorkProgress(){};async function loadSectionsPanel(){};
function alert(error){throw new Error(error)};async function openJob(id){opened.push(id)};
async function answer(url,options={}){
 if(options.method==='POST'){posts.push({url,body:options.body?JSON.parse(options.body):null});return {ok:true}};
 return url==='api/jobs'?[job]:url.includes('/log?')?{from:0,len:0,lines:[]}:job;
}
async function reviewRequest(url,options){return {data:await answer(url,options)}};
async function fetch(url,options){return {ok:true,json:async()=>answer(url,options)}};
""" + 'const job=' + json.dumps(job) + ';\n' + page_between(
        'async function loadJobs(){', 'async function delJob(') + page_between(
        'async function refreshJob(', '\nfunction sectionTime(')


@pytest.mark.parametrize('surface', ['sidebar', 'detail'])
@pytest.mark.parametrize('phase', ['error', 'cancelled'])
def test_export_retry_controls_render_the_saved_approval(surface, phase):
    run_page(view_harness(phase) + r"""
(async()=>{
 await refreshJob('export',1,signal);await loadJobs();
 const html=SURFACE==='sidebar'?jobs.innerHTML:document.getElementById('actions').innerHTML;
 assert.ok(html.includes('Retry section export'),'exports need a render retry, not a scan retry');
 const handler=html.match(/onclick="(retryJob\([^"]+)"/)[1].replace(';return false','');
 await eval(handler);
 assert.deepEqual(posts,[{url:'api/jobs/export/render',body:{}}]);
 assert.deepEqual(opened,['export']);
})().catch(e=>{console.error(e);process.exitCode=1;});
""".replace('SURFACE', json.dumps(surface)))


def test_retry_completion_does_not_navigate_away_from_a_newer_view():
    run_page(view_harness() + r"""
let release;
reviewRequest=(url,options)=>new Promise(resolve=>{release=()=>resolve({data:{ok:true}})});
fetch=(url,options)=>new Promise(resolve=>{release=()=>resolve({ok:true,json:async()=>({ok:true})})});
(async()=>{
 const pending=retryJob('export',true);CUR='other';JOBVIEW++;release();await pending;
 assert.deepEqual(opened,[],'a completed retry must not pull the user back from another job');
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


@pytest.mark.parametrize('role,compare', [('export', False), ('candidate', True)])
def test_completed_section_export_omits_misaligned_full_source_compare(role, compare):
    run_page(view_harness('done', role) + r"""
(async()=>{
 await refreshJob('export',1,signal);
 assert.equal(document.getElementById('actions').innerHTML.includes('Compare before/after'),EXPECTED);
})().catch(e=>{console.error(e);process.exitCode=1;});
""".replace('EXPECTED', json.dumps(compare)))


def panel_harness(manifest):
    return r"""
const assert=require('node:assert/strict');
let CUR='parent',JOBVIEW=1,LEARNED_MODEL_LIST=[{id:'old',name:'Original model'}],LEARNED_MODEL_REFRESH=0;
let newModels=LEARNED_MODEL_LIST;
class Select{
 constructor(){this.options=[];this.value='';this.dataset={};}
 replaceChildren(...options){this.options=options;this.value=options[0]?.value||'';}
 add(option){this.options.push(option)};
}
function Option(text,value){this.text=text;this.value=value};
const nodes={learnedPlateModel:new Select(),learnedModelLibrary:{replaceChildren(){},appendChild(){}},
 learnedModelStatus:{},learnedPlateModelHint:{}};
const panel={dataset:{},isConnected:true,html:'',
 get innerHTML(){return this.html},set innerHTML(html){
  this.html=html;
  for(const match of html.matchAll(/<input id="([^"]+)" value="([^"]*)"/g))nodes[match[1]]={value:match[2]};
  const select=html.match(/<select id="sectionModel"[^>]*>([\s\S]*?)<\/select>/);
  if(select){nodes.sectionModel=new Select();for(const match of select[1].matchAll(/<option value="([^"]*)">([^<]*)<\/option>/g))
   nodes.sectionModel.add(new Option(match[2],match[1]));}
 }};
const document={getElementById:id=>id==='sectionsPanel'?panel:nodes[id]||null,
 createElement(){return {style:{},appendChild(){},append(){},setAttribute(){}}}};
let manifestReads=0;
async function reviewRequest(url){
 if(url==='api/jobs/learned-models')return {data:{models:newModels}};
 manifestReads++;return {data:manifest};
};
const job={phase:'review',sections_revision:1};
""" + 'const manifest=' + json.dumps(manifest) + ';\n' + page_between(
        'function sectionTime(', 'async function saveSectionReview(')


@pytest.mark.parametrize('fps,total,previous_end', [(30., 95, 31), (30., 90, 31), (30000/1001, 95, 31)])
def test_default_section_inputs_roundtrip_to_exact_source_frames(fps, total, previous_end):
    manifest = dict(identity=dict(fps=fps, total_frames=total),
                    items=[dict(id='first', name='First', start_frame=0, end_frame=previous_end)])
    output = run_page(panel_harness(manifest) + r"""
(async()=>{
 await loadSectionsPanel(job,'parent',1);
 console.log(JSON.stringify([sectionSeconds(nodes.sectionStart.value),sectionSeconds(nodes.sectionEnd.value)]));
})().catch(e=>{console.error(e);process.exitCode=1;});
""")
    times = json.loads(output)
    doc = {'render_state': {'fps': fps, 'total_frames': total}}
    assert video_sections.bounds(doc, *times) == (previous_end, total)


def test_model_refresh_updates_cached_section_options_without_resetting_draft():
    manifest = dict(identity=dict(fps=30., total_frames=95), items=[])
    run_page(panel_harness(manifest) + page_between(
        'function clearLearnedModels(', 'async function importLearnedModel(') + r"""
(async()=>{
 await loadSectionsPanel(job,'parent',1);
 nodes.sectionModel.value='old';nodes.sectionName.value='My draft';nodes.sectionStart.value='1.25';nodes.sectionEnd.value='2.7';
 newModels=[{id:'old',name:'Original model',model_size:1},{id:'new',name:'New model',model_size:1}];
 assert.equal(await refreshLearnedModels(),true);
 assert.deepEqual(nodes.sectionModel.options.map(o=>o.value),['','old','new']);
 assert.equal(nodes.sectionModel.value,'old');
 assert.equal(nodes.sectionName.value,'My draft');assert.equal(nodes.sectionStart.value,'1.25');assert.equal(nodes.sectionEnd.value,'2.7');
 assert.equal(manifestReads,1,'model refresh must not rebuild the section form');
 newModels=[newModels[1]];await refreshLearnedModels();assert.equal(nodes.sectionModel.value,'');
})().catch(e=>{console.error(e);process.exitCode=1;});
""")
