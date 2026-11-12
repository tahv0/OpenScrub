"""Secondary model UI preserves explicit choices, selection modes, and job views."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading

import pytest
from werkzeug.serving import make_server

import openscrub_web as web
from test_secondary_models_web import checker_job, CANDIDATE_ID
from test_review_browser import browser_instance, load_browser_page


def page_between(start, end):
    script = '\n'.join(re.findall(r'<script>(.*?)</script>', web.PAGE, re.S))
    assert start in script, 'Secondary model UI handler is missing: ' + start
    return script[script.index(start):script.index(end)]


def run_node(source):
    if not shutil.which('node'):
        pytest.skip('Node required')
    result = subprocess.run(['node', '-e', source], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr


def choice_harness():
    return r'''
const assert=require('node:assert/strict');
let CUR='one',JOBVIEW=1,EN={0:false},VLBL={0:'clear'},OUTPUT_CHOICES={};
let REVIEW_BASE={job:'one',enabled:{0:false},labels:{}},REVIEW_VERSION=1,REVIEW_SAVED=0;
let BE={adds:[],ov:{},times:{}},MAN=[],SHELLPH='review',release,posts=[];
const document={getElementById(){return null}};
function plateUnloadGuard(){};function reviewSaveStatus(){};
function reviewChoicesPending(){const d=reviewChoiceDelta();return Object.keys(d.enabled).length+Object.keys(d.verified_labels).length>0};
async function reviewRequest(url,options){posts.push(JSON.parse(options.body));return new Promise(resolve=>{release=()=>resolve({data:{ok:true}})})};
''' + page_between('function reviewChoiceDelta(', 'async function loadReview(') + page_between(
        'async function persistReview(', 'async function loadPersist(')


def test_same_value_keep_sends_an_explicit_clear_and_enabled_choice():
    run_node(choice_harness() + r'''
const delta=reviewChoiceDelta();
assert.deepEqual(delta,{enabled:{0:false},verified_labels:{0:'clear'}});
(async()=>{const pending=persistReview(true,'one',1,true);release();assert.equal(await pending,true);
assert.equal(VLBL[0],'');assert.deepEqual(reviewChoiceDelta(),{enabled:{},verified_labels:{}});
})().catch(e=>{console.error(e);process.exitCode=1});
''')


@pytest.mark.parametrize('new_choice', ["EN[0]=true;VLBL[0]='clear';", "EN[0]=true;VLBL[0]='plate';"])
def test_acknowledgement_does_not_clear_a_newer_human_choice(new_choice):
    run_node(choice_harness() + r'''
(async()=>{const pending=persistReview(true,'one',1,true);
CHANGE
release();await pending;assert.equal(EN[0],true);assert.notEqual(VLBL[0],'');
assert.ok(Object.keys(reviewChoiceDelta().enabled).length);
})().catch(e=>{console.error(e);process.exitCode=1});
'''.replace('CHANGE', new_choice))


@pytest.mark.parametrize('changed', ["CUR='other';", 'JOBVIEW++;'])
def test_candidate_check_never_posts_after_navigation_during_save(changed):
    source = r'''
const assert=require('node:assert/strict');
let CUR='one',JOBVIEW=1,release,posts=[];
const nodes={plateVerifierCandidate:{value:'candidate'},plateVerifierMode:{value:'review'},
plateVerifierStatus:{textContent:''},plateVerifierButton:{disabled:false,isConnected:true}};
const document={getElementById:id=>nodes[id]||null};
function saveAndRender(){return new Promise(resolve=>{release=resolve})};
async function reviewRequest(url,options){posts.push(url);return {data:{ok:true}}};
async function openJob(){};
''' + page_between('async function checkPlateDetections(', 'function reviewChoiceDelta(') + r'''
(async()=>{const pending=checkPlateDetections();CHANGE release(true);await pending;
assert.deepEqual(posts,[]);assert.equal(nodes.plateVerifierButton.disabled,false);
})().catch(e=>{console.error(e);process.exitCode=1});
'''.replace('CHANGE', changed)
    run_node(source)


def test_candidate_check_snapshots_mode_and_candidate_before_saving():
    run_node(r'''
const assert=require('node:assert/strict');
let CUR='one',JOBVIEW=1,release,posts=[],opened=[];
const nodes={plateVerifierCandidate:{value:'first-candidate'},plateVerifierMode:{value:'filter'},
plateVerifierStatus:{textContent:''},plateVerifierButton:{disabled:false,isConnected:true}};
const document={getElementById:id=>nodes[id]||null};
function saveAndRender(){return new Promise(resolve=>{release=resolve})};
async function reviewRequest(url,options){posts.push({url,body:JSON.parse(options.body)});return {data:{ok:true}}};
async function openJob(id){opened.push(id)};
''' + page_between('async function checkPlateDetections(', 'function reviewChoiceDelta(') + r'''
(async()=>{const pending=checkPlateDetections();
nodes.plateVerifierCandidate.value='later';nodes.plateVerifierMode.value='review';release(true);await pending;
assert.deepEqual(posts,[{url:'api/jobs/one/plate-verifier',body:{candidate_id:'first-candidate',mode:'filter'}}]);
assert.deepEqual(opened,['one']);
})().catch(e=>{console.error(e);process.exitCode=1});
''')


def test_library_modes_preserve_explicit_filter_but_default_new_verifiers_to_review():
    run_node(r'''
const assert=require('node:assert/strict');
const LEARNED_MODEL_LIST=[{id:'mask',name:'Mask',kind:'openscrub-plate-mask-refiner'},
{id:'valid',name:'Garage <checker>',kind:'openscrub-plate-verifier',validation:{status:'validated'}},
{id:'review',name:'Review only',kind:'openscrub-plate-verifier',validation:{status:'review_only'}}];
class Select{constructor(){this.value='';this.dataset={};this.options=[]}
replaceChildren(...options){this.options=options;this.value=options[0]?.value||''}
add(option){this.options.push(option)}};
function Option(text,value){this.text=text;this.value=value};
const nodes={learnedPlateModel:new Select(),learnedPlateModelMode:new Select(),learnedPlateModelHint:{},
sectionModel:new Select(),sectionModelMode:new Select()};
const document={getElementById:id=>nodes[id]};
''' + page_between('function refreshLearnedModelMode(', 'async function refreshLearnedModels(') + r'''
nodes.learnedPlateModel.value='valid';refreshLearnedModelMode();
assert.equal(nodes.learnedPlateModelMode.value,'review');
assert.equal(nodes.learnedPlateModelMode.options.find(o=>o.value==='filter').disabled,false);
nodes.learnedPlateModelMode.value='filter';refreshLearnedModelMode();
assert.equal(nodes.learnedPlateModelMode.value,'filter');
nodes.learnedPlateModel.value='review';refreshLearnedModelMode();
assert.equal(nodes.learnedPlateModelMode.value,'review');
assert.equal(nodes.learnedPlateModelMode.options.find(o=>o.value==='filter').disabled,true);
nodes.learnedPlateModel.value='mask';refreshLearnedModelMode();
assert.equal(nodes.learnedPlateModelMode.value,'refine');
nodes.sectionModel.value='valid';refreshLearnedModelMode('sectionModel','sectionModelMode');
assert.equal(nodes.sectionModelMode.value,'review');
''')


def test_section_rescan_submits_the_clicked_mode_without_resetting_it_during_save():
    run_node(r'''
const assert=require('node:assert/strict');
let CUR='one',JOBVIEW=1,JOBSJSON='',release,posts=[];
const nodes={sectionModel:{value:'checker'},sectionModelMode:{value:'filter'}};
const document={getElementById:id=>nodes[id]};
function saveSectionReview(){return new Promise(resolve=>{release=resolve})};
async function reviewRequest(url,options){posts.push(JSON.parse(options.body));return {data:{job_id:'candidate'}}};
async function openJob(){};function alert(error){throw error};
''' + page_between('async function sectionAction(', '\nlet BE=') + r'''
(async()=>{const pending=sectionAction('one','section','rescan','',{disabled:false});
nodes.sectionModelMode.value='review';release(true);await pending;
assert.deepEqual(posts,[{model_id:'checker',learned_plate_model_mode:'filter'}]);
})().catch(e=>{console.error(e);process.exitCode=1});
''')


def test_save_evaluated_candidate_posts_its_identity_and_preserves_selection_during_save():
    run_node(r'''
const assert=require('node:assert/strict');
let CUR='one',JOBVIEW=1,release,posts=[];
const nodes={learnedModelName:{value:'Garage'},learnedModelDescription:{value:'Daylight'},
learnedModelSource:{value:'candidate-before-save'},saveLearnedModelStatus:{textContent:''},
saveLearnedModelButton:{disabled:false,isConnected:true}};
const document={getElementById:id=>nodes[id]};
function saveAndRender(){return new Promise(resolve=>{release=resolve})};
async function refreshLearnedModels(){};
async function reviewRequest(url,options){posts.push(JSON.parse(options.body));return {data:{model:{name:'Garage'}}}};
''' + page_between('async function saveLearnedModel(', '\nloadPersist();') + r'''
(async()=>{const pending=saveLearnedModel();nodes.learnedModelSource.value='later';release(true);await pending;
assert.deepEqual(posts,[{name:'Garage',description:'Daylight',candidate_id:'candidate-before-save'}]);
assert.ok(nodes.saveLearnedModelStatus.textContent.includes('Saved'));
})().catch(e=>{console.error(e);process.exitCode=1});
''')


def test_scan_setup_serializes_the_explicit_secondary_model_mode():
    run_node(r'''
const assert=require('node:assert/strict');
const nodes={plateMargin:{value:'0'},spath:{value:'/local/video.mp4'},learnedPlateModel:{value:'checker'},
learnedPlateModelMode:{value:'filter'},summary:{}};
function $(id){return nodes[id]||{value:'',checked:false}};
const S={dur:2,file:null,wins:[],audio:[],mm:{},cin:0,cout:2,ignore:[]};
const MAXUP=0,FREEDISK=0;let MS={},sent;
function unionCats(){return ['plate']};function confirm(){return true};function alert(error){throw error};
const document={querySelectorAll(){return []}};
async function fetch(){return {json:async()=>({plate:true,plate_autofetch:true})}};
class FormData{constructor(){this.values={}}append(key,value){this.values[key]=value}};
class XMLHttpRequest{constructor(){this.upload={}}open(){}send(data){sent=JSON.parse(data.values.options)}};
''' + page_between('async function startScan(', '\nsetMode("play");') + r'''
(async()=>{await startScan();assert.equal(sent.learned_plate_model,'checker');
assert.equal(sent.learned_plate_model_mode,'filter');
})().catch(e=>{console.error(e);process.exitCode=1});
''')


@pytest.fixture
def secondary_ui_server(checker_job, monkeypatch):
    client, job, report, queued = checker_job
    monkeypatch.setattr(web, 'openscrub_update', None)
    job['name'] = 'Secondary checker fixture'
    server = make_server('127.0.0.1', 0, web.app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield 'http://127.0.0.1:%d' % server.server_port, job, report, queued
    server.shutdown()
    thread.join(timeout=5)


@pytest.mark.parametrize('width,height', [(1440, 1000), (390, 844)])
def test_candidate_check_save_and_explicit_library_mode_in_browser(secondary_ui_server, tmp_path, width, height):
    sync = pytest.importorskip('playwright.sync_api')
    url, job, report, queued = secondary_ui_server
    errors = []
    with sync.sync_playwright() as pw:
        browser = browser_instance(pw)
        page = browser.new_page(viewport={'width': width, 'height': height})
        page.set_default_timeout(12000)
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('dialog', lambda dialog: dialog.accept())
        load_browser_page(page, url, [], [])
        assert page.title() == 'OpenScrub'
        page.get_by_role('link', name='Secondary checker fixture', exact=True).click()
        page.locator('#review').wait_for()
        sync.expect(page.locator('#plateVerifierCandidate')).to_have_value(CANDIDATE_ID)
        assert page.locator('#plateVerifierMode').input_value() == 'review'
        page.get_by_role('button', name='Check detections', exact=True).click()
        sync.expect(page.get_by_role('button', name='Cancel learning pass', exact=True)).to_be_visible(timeout=12000)
        assert queued == [(job['id'], 'verify')]
        assert job['verification_request']['mode'] == 'review'
        web.perform_verification(job)
        page.evaluate("SHELLPH='';refresh()")
        page.locator('#plateVerifierCandidate').wait_for()
        sync.expect(page.locator('#plateVerifierStatus')).to_contain_text('0 rejected plates')
        sync.expect(page.locator('#review .plate-verification-badge').first).to_contain_text('review')
        page.locator('#saveLearnedModelPanel summary').click()
        page.locator('#learnedModelName').fill('Garage <secondary>')
        page.get_by_role('button', name='Save model', exact=True).click()
        sync.expect(page.locator('#saveLearnedModelStatus')).to_contain_text('Saved')
        page.evaluate("location.hash='#settings'")
        entry = page.locator('#learnedModelLibrary .learned-model').first
        sync.expect(entry).to_contain_text('Secondary verifier')
        sync.expect(entry).to_contain_text('validated')
        assert entry.locator('secondary').count() == 0
        entry.get_by_role('button', name='Use for next scan', exact=True).click()
        assert page.locator('#learnedPlateModelMode').input_value() == 'review'
        page.locator('#learnedPlateModelMode').select_option('filter')
        assert page.locator('#learnedPlateModelMode').input_value() == 'filter'
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        assert not errors, errors
        evidence = Path(os.environ.get('REVIEW_EVIDENCE_DIR', str(tmp_path)))
        evidence.mkdir(parents=True, exist_ok=True)
        page.locator('#learnedPlateModelControls').screenshot(path=str(evidence / ('secondary-mode-%d.png' % width)))
        browser.close()
