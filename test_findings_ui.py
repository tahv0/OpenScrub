"""Saved JPEG library UI: selection, revisions, escaping, and live queue races.

Node checks run without Chromium; the real Flask/browser tests run in browser CI
at desktop and mobile widths, using the existing review server fixture.
"""
import json
import shutil
import subprocess

import cv2
import numpy as np
import pytest

import confirmed_findings
import findings_ui
import openscrub_web as web
from test_review_browser import review_server, browser_instance, load_browser_page


def run_ui(body, setup=''):
    if not shutil.which('node'):
        pytest.skip('Node required')
    source = r"""
const assert=require('node:assert/strict');
const nodes=new Map();
function node(id){if(!nodes.has(id))nodes.set(id,{id,value:'',checked:false,disabled:false,hidden:false,innerHTML:'',textContent:'',style:{},dataset:{},options:[],
 classList:{toggle(){}},replaceChildren(...items){this.options=items;this.children=items;this.value=items[0]?.value||''},add(o){this.options.push(o)},append(o){(this.children??=[]).push(o)},
 querySelectorAll(){return []},scrollIntoView(){},remove(){nodes.delete(id)}});return nodes.get(id)}
const document={getElementById:node,createElement:tag=>({tag,style:{},dataset:{},textContent:'',append(){},replaceChildren(){}})};
function Option(text,value){this.text=text;this.value=value}
let location={hash:'#findings'},CUR='job-a',JOBVIEW=1;
let calls=[],opened=[],refreshed=0;
async function reviewRequest(url,options={}){calls.push({url,options});return {data:{items:[],videos:[],total:0,models:[]}}}
function confirm(){return true};async function openJob(id){opened.push(id)};async function refreshLearnedModels(){refreshed++}
""" + findings_ui.SCRIPT + '\n' + setup + '\n(async()=>{\n' + body + r"""
})().catch(error=>{console.error(error);process.exitCode=1});
"""
    result = subprocess.run(['node', '-e', source], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def test_script_syntax_and_initial_neutral_state():
    run_ui("assert.equal(FINDINGS.selected.size,0);assert.equal(FINDINGS.editor,null)")
    assert 'id="findingsview" style="display:none"' in findings_ui.HTML
    assert '<video' not in findings_ui.HTML + findings_ui.SCRIPT
    assert 'license_accepted:true' in findings_ui.SCRIPT
    assert 'id="findingsLicense" type="checkbox"' in findings_ui.HTML
    assert 'id="findingsLicense" type="checkbox" checked' not in findings_ui.HTML


def test_cards_escape_source_names_labels_and_ids_without_inline_script():
    run_ui(r"""
const html=findingCard({id:'x" onclick="attack()',category:'<script>alert(1)</script>',label:'positive',video:{name:'<img src=x onerror=attack()>'},frame:4,time:1.25});
assert.ok(html.includes('&lt;img src=x onerror=attack()&gt;'));
assert.ok(!html.includes('<script>'));assert.ok(!html.includes(' onclick="attack()'));
assert.ok(html.includes('Frame 4 · 1.25 s'));
assert.ok(html.includes('Confirmed &lt;script&gt;'));assert.ok(!html.includes('Blur'));
assert.equal(findingEscape("a\"b'c&<>"),'a&quot;b&#39;c&amp;&lt;&gt;');
""")


def test_selection_is_explicit_and_survives_pages_and_video_filters():
    run_ui(r"""
bindConfirmedFindings();
const a={id:'a',category:'plate',label:'positive',video_id:'one'},b={id:'b',category:'plate',label:'negative',video_id:'two'},face={id:'f',category:'face'};
FINDINGS.items=[a,face];FINDINGS.total=3;renderConfirmedFindings();assert.equal(FINDINGS.selected.size,0);
node('findingsSelectPage').onclick();assert.deepEqual([...FINDINGS.selected.keys()],['a']);
FINDINGS.items=[b];renderConfirmedFindings();assert.deepEqual([...FINDINGS.selected.keys()],['a']);
node('findingsSelectPage').onclick();assert.deepEqual([...FINDINGS.selected.keys()],['a','b']);
assert.ok(node('findingsSelection').textContent.includes('2 videos'));
location.hash='';openFindingsForVideo('three');assert.equal(node('findingsVideo').value,'three');
assert.deepEqual([...FINDINGS.selected.keys()],['a','b']);assert.equal(location.hash,'#findings');
node('findingsClear').onclick();assert.equal(FINDINGS.selected.size,0);
""")


def test_parent_dropdown_excludes_imported_inference_only_models_and_keeps_choice():
    run_ui(r"""
reviewRequest=async()=>({data:{models:[{id:'local',name:'Local <plate>',training:{trainable:true}},{id:'import',name:'Imported',training:{trainable:false}},{id:'legacy',name:'Legacy'}]}});
node('findingsParent').value='local';await loadFindingsParents();
assert.deepEqual(node('findingsParent').options.map(o=>o.value),['','local']);assert.equal(node('findingsParent').value,'local');
""")


def test_training_sends_selected_ids_name_parent_and_explicit_license_only():
    run_ui(r"""
FINDINGS.selected.set('a',{id:'a',video_id:'one',category:'plate',label:'positive'});
await trainConfirmedFindings();assert.equal(calls.length,0);assert.ok(node('findingsTrainStatus').textContent.includes('acknowledge'));
node('findingsLicense').checked=true;node('findingsModelName').value=' Evening ';node('findingsParent').value='parent';
reviewRequest=async(url,options)=>{calls.push({url,options});return {data:{id:'training-job',name:'Evening'}}};
await trainConfirmedFindings();
assert.equal(calls.length,1);assert.equal(calls[0].url,'api/findings/train');
assert.deepEqual(JSON.parse(calls[0].options.body),{example_ids:['a'],name:'Evening',parent_model_id:'parent',license_accepted:true});
assert.deepEqual(opened,['training-job']);assert.equal(refreshed,1);
""")


def test_editor_save_uses_expected_revision_and_preserves_conflicted_draft():
    run_ui(r"""
const state={item:{id:'example',revision:7},points:[[20,20],[50,20],[50,40],[20,40]],shapeDirty:true,busy:false};
FINDINGS.editor=state;node('findingEditorLabel').value='negative';
reviewRequest=async(url,options)=>{calls.push({url,options});throw Object.assign(new Error('changed'),{status:409})};
await saveFindingEditor(state);
assert.equal(calls[0].url,'api/findings/example');
assert.deepEqual(JSON.parse(calls[0].options.body),{expected_revision:7,label:'negative',points:state.points});
assert.equal(FINDINGS.editor,state);assert.equal(state.busy,false);
assert.ok(node('findingEditorStatus').textContent.includes('Revision conflict'));assert.ok(node('findingEditorStatus').textContent.includes('draft is kept'));
assert.equal(calls.length,1,'editing never reads a source video');
""")


def test_forgetting_requires_explicit_confirmation_and_expected_revision():
    run_ui(r"""
const state={item:{id:'example',revision:4},busy:false};FINDINGS.editor=state;
confirm=()=>false;await forgetFindingEditor(state);assert.equal(calls.length,0);
confirm=()=>true;reviewRequest=async(url,options)=>{calls.push({url,options});throw Object.assign(new Error('changed'),{status:409})};
await forgetFindingEditor(state);assert.equal(calls[0].options.method,'DELETE');
assert.deepEqual(JSON.parse(calls[0].options.body),{expected_revision:4});
assert.ok(node('findingEditorStatus').textContent.includes('Revision conflict'));
""")


def test_source_mapping_clamps_coordinates_and_rejects_crossed_corners():
    run_ui(r"""
const c=[100,50,500,250],r={left:10,top:20,width:200,height:100};
assert.deepEqual(findingSourcePoint(c,r,110,70),[300,150]);
assert.deepEqual(findingSourcePoint(c,r,-100,400),[100,250]);
assert.ok(findingValidPoints([[100,50],[500,50],[500,250],[100,250]],c));
assert.ok(!findingValidPoints([[100,50],[500,250],[500,50],[100,250]],c));
""")


def test_pending_queue_returns_immediately_throttles_and_discards_stopped_scan_response():
    run_ui(r"""
let release;reviewRequest=(url)=>{calls.push({url});return new Promise(resolve=>release=resolve)};
const job={phase:'scanning'};
assert.equal(refreshPendingFindings(job,'job-a',1),undefined);
refreshPendingFindings(job,'job-a',1);assert.equal(calls.length,1);
refreshPendingFindings({phase:'paused'},'job-a',1);
release({data:{items:[],total:9}});await Promise.resolve();await Promise.resolve();
assert.ok(!nodes.has('pendingFindings'),'late response must not remount after the scan stops');
""", "document.getElementById=id=>id==='pendingFindings'?(nodes.get(id)||null):node(id);")


def test_findings_list_ignores_an_old_response_and_keeps_latest_scope():
    run_ui(r"""
let releases=[];loadFindingsParents=()=>{};
reviewRequest=(url)=>new Promise(resolve=>releases.push(resolve));
node('findingsVideo').value='first';const a=loadConfirmedFindings();
node('findingsVideo').value='second';const b=loadConfirmedFindings();
releases[1]({data:{items:[{id:'b',video:{name:'second'},category:'plate',label:'negative',frame:1,time:.5}],videos:[{id:'second',name:'second',count:1}],total:1}});await b;
releases[0]({data:{items:[],videos:[],total:0}});await a;
assert.equal(FINDINGS.items[0].id,'b');assert.equal(node('findingsVideo').value,'second');
""")


def seed_examples(root):
    ok, jpeg = cv2.imencode('.jpg', np.full((80, 160, 3), 150, np.uint8))
    assert ok
    entries = []
    for i, category, label in [(1, 'plate', 'positive'), (2, 'plate', 'negative'), (3, 'face', 'positive')]:
        video = dict(sha256=str(i)*64, variant_sha256=str(i)*64,
                     name='Garage <daylight>' if i == 1 else 'Other camera',
                     fps=10, width=640, height=360, total_frames=100)
        entry = confirmed_findings.record(root, video, dict(explicit=True, category=category,
            label=label, frame=12, box=[200, 120, 320, 180], crop=[160, 100, 400, 220]), jpeg.tobytes())
        entries.append(entry)
    return entries


@pytest.mark.parametrize('viewport', [(1440, 1000), (390, 844)])
def test_saved_jpeg_browse_edit_and_explicit_selection_without_video(
        review_server, monkeypatch, tmp_path, viewport):
    sync = pytest.importorskip('playwright.sync_api')
    url, _ = review_server
    root = tmp_path / 'library-data'
    root.mkdir()
    monkeypatch.setattr(web, 'JOBS_DIR', str(root))
    monkeypatch.setattr(web, 'vault_locked', lambda: False)
    entries = seed_examples(root / 'confirmed_findings')
    monkeypatch.setattr(web, '_frame_at', lambda *a, **k: pytest.fail('Library editor reopened a video'))
    with sync.sync_playwright() as pw:
        browser = browser_instance(pw)
        try:
            page = browser.new_page(viewport={'width':viewport[0], 'height':viewport[1]})
            page.set_default_timeout(15000)
            errors, requests = [], []
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.on('request', lambda r: requests.append(r.url))
            page.on('dialog', lambda d: d.accept())
            load_browser_page(page, url, requests, [])
            page.evaluate("location.hash='#findings'")
            page.locator('#findingsList .finding-card').first.wait_for()
            assert page.locator('#findingsList .finding-card').count() == 3
            assert 'Garage <daylight>' in page.locator('#findingsList').inner_text()
            assert page.locator('#findingsList daylight').count() == 0
            assert page.locator('#findingsList input:checked').count() == 0
            assert page.locator('#findingsTrain').is_disabled()
            # Pick only the current video's examples, then explicitly add another.
            page.locator('#findingsVideo').select_option(entries[0]['video_id'])
            page.wait_for_function("document.querySelectorAll('#findingsList .finding-card').length===1")
            page.locator('#findingsSelectPage').click()
            assert page.evaluate('FINDINGS.selected.size') == 1
            page.locator('#findingsVideo').select_option(entries[1]['video_id'])
            page.wait_for_function("document.querySelector('#findingsList .finding-card').dataset.finding===%s" % json.dumps(entries[1]['id']))
            assert page.locator('#findingsList input:checked').count() == 0
            page.locator('#findingsList input[type=checkbox]').check()
            assert page.evaluate('FINDINGS.selected.size') == 2
            page.locator('#findingsList button').click()
            page.locator('#findingEditorImage').wait_for(state='visible')
            assert page.locator('#findingEditor video').count() == 0
            page.wait_for_function("document.querySelector('#findingEditorImage').naturalWidth>0")
            page.get_by_label('Corner 1 x', exact=True).fill('210')
            page.get_by_label('Corner 1 x', exact=True).press('Tab')
            page.locator('#findingEditorLabel').select_option('positive')
            page.locator('#findingEditorSave').click()
            page.wait_for_function("document.querySelector('#findingEditorStatus').textContent.includes('Saved confirmation')")
            saved = confirmed_findings.get_finding(root / 'confirmed_findings', entries[1]['id'])
            assert saved['revision'] == 2 and saved['label'] == 'positive'
            assert saved['points'][0][0] == 210
            assert not any('/video' in u or '/finding-preview/' in u or '/plate_quad/' in u for u in requests)
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            assert not errors, errors
        finally:
            browser.close()
