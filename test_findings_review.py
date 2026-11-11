"""Explicit human classification is distinct from the automatic output policy."""
import json
import re
import shutil
import subprocess

import pytest

import openscrub_web as web
from test_review_browser import review_server, browser_instance, load_browser_page, drag_corner


def between(start, end):
    return web.APP_JS.split(start,1)[1].split(end,1)[0].join([start,''])


def choices_script(body):
    source = r'''
const assert=require('node:assert/strict');
let CUR='job',JOBVIEW=1,EN={0:true},VLBL={},FINDING_META={0:{category:'plate'}},OUTPUT_CHOICES={},OUTPUT_VERSION={};
let REVIEW_BASE={job:'job',enabled:{0:true},labels:{},output_choices:{}};
const PLATE_EDITS=new Map(),document={getElementById(){return null}};
let CONFIRM_CHAIN=Promise.resolve(),PLATE_SAVE=null,PLATE_REVIEW_BUSY=false;
const CONFIRM_PENDING=new Set(),CONFIRM_FAILED=new Map();
let changed=0;function markReviewChanged(){changed++}function sectionEscape(s){return String(s)};
function discardRejectedCorners(){}function plateUnloadGuard(){};
const plateCopy=points=>points.map(p=>p.slice());
function syncPlateTrack(){}function plateStatus(){}function schedulePlateSaves(){};
''' + between('function reviewChoiceDelta(){','async function loadReview(') + between('function detChoices(i){','function setAll(')
    result = subprocess.run([shutil.which('node') or 'node','-e',source+'\n'+body],capture_output=True,text=True,timeout=10)
    assert result.returncode == 0, result.stderr


def test_unreviewed_cards_do_not_advertise_default_blur_as_a_choice():
    choices_script('''const html=detChoices(0);assert.ok(html.includes('Not reviewed'));
assert.equal((html.match(/aria-pressed="false"/g)||[]).length,2);assert.ok(!html.includes('aria-pressed="true"'));''')


def test_output_only_choice_keeps_classification_and_records_explicit_default():
    choices_script('''VLBL[0]='plate';REVIEW_BASE.labels[0]='plate';
applyDet(0,true);assert.equal(VLBL[0],'plate');assert.equal(OUTPUT_CHOICES[0],true);
const delta=reviewChoiceDelta();assert.deepEqual(delta.verified_labels,{});
assert.deepEqual(delta.output_choices,{'0':true});assert.equal(delta.enabled[0],true);''')


def test_late_confirmation_keeps_newer_output_choice_in_the_save_delta():
    choices_script(r'''
let acknowledge;
async function reviewRequest(){return await new Promise(resolve=>acknowledge=resolve)}
(async()=>{
 const saving=confirmFinding(0,'negative');await Promise.resolve();
 assert.ok(acknowledge,'Confirmation must be in flight');
 applyDet(0,true);
 acknowledge({data:{finding:{id:'example',revision:1}}});await saving;
 assert.equal(EN[0],true,'The newer explicit Blur action must win');
 assert.equal(REVIEW_BASE.enabled[0],false,'The baseline records the acknowledged server state');
 assert.equal(VLBL[0],'not_plate','Classification remains separate from output');
 assert.deepEqual(reviewChoiceDelta().enabled,{'0':true});
 assert.equal(CONFIRM_FAILED.size,0);
})().catch(error=>{console.error(error);process.exitCode=1});
''')


@pytest.mark.parametrize('save_only', [False, True])
def test_new_confirmation_waits_for_inflight_review_save_before_changing_output(save_only):
    choices_script(r'''
let MAN=[],BE={adds:[],ov:{},times:{}},REVIEW_VERSION=1,REVIEW_SAVED=0,SHELLPH='review';
function reviewChoicesPending(){return REVIEW_VERSION!==REVIEW_SAVED||CONFIRM_PENDING.size>0||CONFIRM_FAILED.size>0;}
function reviewSaveStatus(){}function alert(){}function closePlateQuad(){}function clearReviewPreviews(){};
async function flushPlateSaves(){return true;}
const note={textContent:''};document.getElementById=id=>id==='vlabel0'?note:null;
let serverEnabled=true,commitEarlierSave=null,renderedEnabled=null,confirmationRequests=0;
async function reviewRequest(url,options){
 if(url.endsWith('/detections')){
  const payload=JSON.parse(options.body);
  return await new Promise(resolve=>commitEarlierSave=()=>{
   serverEnabled=payload.enabled['0'];resolve({data:{ok:true}});
  });
 }
 if(url.includes('/confirm/')){
  confirmationRequests++;serverEnabled=JSON.parse(options.body).label==='positive';
  return {data:{ok:true,finding:{id:'example',revision:1},applied:1,label:'plate'}};
 }
 if(url.endsWith('/render')){renderedEnabled=serverEnabled;return {data:{ok:true}};}
 throw Error('Unexpected request '+url);
}
''' + between('async function saveAndRender(', 'async function loadPersist(') + r'''
(async()=>{
 EN[0]=false;OUTPUT_CHOICES[0]=true;
 const saving=saveAndRender(SAVE_ONLY);
 for(let n=0;n<10&&!commitEarlierSave;n++)await Promise.resolve();
 assert.ok(commitEarlierSave,'The older output save must be in flight');
 assert.equal(PLATE_REVIEW_BUSY,true);
 await confirmFinding(0,'positive');
 assert.equal(confirmationRequests,0,'A new classification cannot overtake the older output save');
 assert.equal(EN[0],false);assert.equal(VLBL[0],undefined);
 assert.equal(CONFIRM_PENDING.size,0);assert.equal(CONFIRM_FAILED.size,0);
 assert.match(note.textContent,/Review is being saved.*choose Is \/ Not after it finishes/i);
 commitEarlierSave();assert.equal(await saving,true);
 assert.equal(serverEnabled,false);assert.equal(EN[0],false);
 assert.equal(renderedEnabled,SAVE_ONLY?null:false);
 assert.equal(reviewChoicesPending(),false);assert.equal(PLATE_REVIEW_BUSY,false);
 if(SAVE_ONLY){
  await confirmFinding(0,'positive');
  assert.equal(confirmationRequests,1,'The same classification can be retried after saving');
  assert.equal(serverEnabled,true);assert.equal(EN[0],true);assert.equal(VLBL[0],'plate');
  assert.equal(CONFIRM_PENDING.size,0);assert.equal(CONFIRM_FAILED.size,0);
 }
})().catch(error=>{console.error(error);process.exitCode=1});
'''.replace('SAVE_ONLY',json.dumps(save_only)))


@pytest.mark.parametrize('revoked',[False,True])
def test_archive_conflict_requires_explicit_reconfirmation_with_current_revision(revoked):
    choices_script(r'''
FINDING_META[0].confirmed_finding_id='example';FINDING_META[0].confirmed_finding_revision=1;
const payloads=[];
async function reviewRequest(url,options){
 const body=JSON.parse(options.body);payloads.push(body);
 if(payloads.length===1)throw Object.assign(new Error('Saved example changed'),{status:409,
  details:{current_archive:{id:'example',revision:2,revoked:REVOKED,label:REVOKED?null:'negative'}}});
 return {data:{finding:{id:'example',revision:3}}};
}
(async()=>{
 await confirmFinding(0,'positive');
 assert.equal(payloads.length,1,'Conflicts must not retry automatically');
 assert.equal(FINDING_META[0].confirmed_finding_revision,2);
 assert.equal(CONFIRM_FAILED.size,1);assert.equal(VLBL[0],undefined);
 await confirmFinding(0,'positive');
 assert.equal(payloads[1].expected_revision,2);
 assert.equal(CONFIRM_FAILED.size,0);assert.equal(VLBL[0],'plate');
 assert.equal(FINDING_META[0].confirmed_finding_revision,3);
})().catch(error=>{console.error(error);process.exitCode=1});
'''.replace('REVOKED',json.dumps(revoked)))


def test_confirm_can_commit_conflicted_area_with_a_new_explicit_classification():
    choices_script(r'''
const points=[[1,1],[10,1],[10,8],[1,8]];
const edit={i:0,job:CUR,dirty:true,archiveConflict:true,error:{status:409},version:4,
 points,saved:[[0,0],[10,0],[10,8],[0,8]],meta:{preview_token:'same-frame'},img:{},draw(){}};
PLATE_EDITS.set(0,edit);FINDING_META[0].confirmed_finding_revision=2;
async function reviewRequest(url,options){
 const body=JSON.parse(options.body);
 assert.deepEqual(body.points,points);assert.equal(body.expected_revision,2);
 return {data:{finding:{id:'example',revision:3},preview:{points,preview_token:'new'}}};
}
(async()=>{
 await confirmFinding(0,'positive');
 assert.equal(CONFIRM_FAILED.size,0);assert.equal(edit.dirty,false);
 assert.equal(edit.archiveConflict,false);assert.equal(edit.error,null);
 assert.equal(edit.meta.preview_token,'new');assert.deepEqual(edit.saved,points);
})().catch(error=>{console.error(error);process.exitCode=1});
''')


def test_dismissing_one_conflict_preserves_other_drafts_and_review_choices():
    choices_script(r'''
const saved=[[0,0],[10,0],[10,8],[0,8]];
const edit={i:0,job:CUR,dirty:true,archiveConflict:true,error:{status:409},version:4,
 points:[[1,1],[10,1],[10,8],[1,8]],saved,meta:{},draw(){}};
const other={dirty:true,points:[[2,2]],error:{message:'Other draft'}};
PLATE_EDITS.set(0,edit);PLATE_EDITS.set(1,other);EN[0]=false;VLBL[0]='not_plate';
CONFIRM_FAILED.set(0,{status:409});CONFIRM_FAILED.set(1,{status:409});
dismissFindingConfirmation(0);
assert.equal(CONFIRM_FAILED.has(0),false);assert.equal(CONFIRM_FAILED.has(1),true);
assert.equal(edit.dirty,false);assert.deepEqual(edit.points,saved);
assert.equal(other.dirty,true);assert.equal(other.error.message,'Other draft');
assert.equal(EN[0],false);assert.equal(VLBL[0],'not_plate');
''')


def test_conflict_found_while_flushing_corners_waits_for_another_explicit_click():
    choices_script(r'''
const points=[[1,1],[10,1],[10,8],[1,8]];
const edit={i:0,job:CUR,dirty:true,error:null,version:1,points,saved:points,
 meta:{preview_token:'old'},img:{},draw(){}};
PLATE_EDITS.set(0,edit);
FINDING_META[0].confirmed_finding_id='example';FINDING_META[0].confirmed_finding_revision=1;
let requests=0;
async function pumpPlateSaves(){
 edit.archiveConflict=true;
 edit.error=Object.assign(new Error('Saved example changed'),{status:409,
  details:{current_archive:{id:'example',revision:2,label:'negative',revoked:false}}});
 rememberFindingConflict(0,edit.error.details.current_archive);
}
async function reviewRequest(){requests++;return {data:{finding:{id:'example',revision:3},preview:{points}}}}
(async()=>{
 await confirmFinding(0,'positive');
 assert.equal(requests,0,'A conflict discovered during flushing must not overwrite the newer archive decision');
 assert.equal(CONFIRM_FAILED.size,1);
 await confirmFinding(0,'positive');assert.equal(requests,1);assert.equal(CONFIRM_FAILED.size,0);
})().catch(error=>{console.error(error);process.exitCode=1});
''')


def test_approximate_legacy_picture_does_not_send_training_confirmation():
    choices_script(r'''
FINDING_META[0].classification_allowed=false;
FINDING_META[0].classification_note='Rescan for exact training examples';
async function reviewRequest(){throw new Error('Approximate picture must not create training evidence')}
(async()=>{
 await confirmFinding(0,'positive');
 assert.equal(CONFIRM_PENDING.size,0);assert.equal(CONFIRM_FAILED.size,0);
 assert.equal(VLBL[0],undefined);
 applyDet(0,false);assert.equal(reviewChoiceDelta().enabled[0],false);
})().catch(error=>{console.error(error);process.exitCode=1});
''')


def test_embedded_modules_do_not_override_each_others_global_handlers():
    script='\n'.join(re.findall(r'<script>(.*?)</script>',web.PAGE,re.S))
    names=re.findall(r'^(?:async )?function ([A-Za-z_$][\w$]*)\(',script,re.M)
    assert len(names)==len(set(names)), 'A later embedded module overrides an earlier UI handler'


@pytest.mark.parametrize('width',[1440,390])
def test_explicit_compact_review_saved_without_video(review_server,monkeypatch,width):
    url,report = review_server
    api = pytest.importorskip('playwright.sync_api')
    # Warm each exact representative once, then forbid reopening the source.
    client=web.app.test_client()
    doc=json.loads(report.read_text())
    for i in range(len(doc['detections'])):
        assert client.get(f'/api/jobs/inline-fixture/finding-preview/{i}').status_code==200
    monkeypatch.setattr(web,'_frame_at',lambda *a,**k:pytest.fail('Compact review reopened video'))
    with api.sync_playwright() as pw:
        browser=browser_instance(pw)
        page=browser.new_page(viewport={'width':width,'height':1000 if width>400 else 844})
        errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
        requests=[];page.on('request',lambda request:requests.append(request.url))
        load_browser_page(page,url,[],[])
        page.get_by_role('link',name='Synthetic review fixture',exact=True).click()
        card=page.locator('#det0');card.wait_for()
        assert card.locator('.det-status').inner_text()=='Not reviewed'
        assert card.locator('.det-choice[aria-pressed=true]').count()==0
        page.wait_for_function('!!document.querySelector("#det0 img")._quadEdit')
        drag_corner(page,card)
        page.wait_for_function('!plateEditsPending()')
        assert client.get('/api/findings').get_json()['total']==0
        assert not json.loads(report.read_text())['detections'][0].get('verified_label')
        card.get_by_role('button',name='✓ Is a plate',exact=True).click()
        page.wait_for_function('document.getElementById("vlabel0").textContent.includes("Saved")')
        stored=client.get('/api/findings').get_json()
        assert stored['total']==1 and stored['items'][0]['shape_confirmed']
        assert stored['items'][0]['label']=='positive'
        card.get_by_role('button',name='✕ Not a plate',exact=True).click()
        page.wait_for_function('document.getElementById("vlabel0").textContent.includes("Not a plate")')
        assert client.get('/api/findings').get_json()['items'][0]['label']=='negative'
        assert not any('/video_stream' in item or '/detframe/' in item for item in requests)
        assert not errors,errors
        browser.close()


@pytest.mark.parametrize('width',[1440,390])
def test_archive_revision_conflict_and_corner_reconfirmation_use_real_api(
        review_server,monkeypatch,width):
    """External archive edits require a fresh Is click and retain corner drafts."""
    url,report=review_server
    api=pytest.importorskip('playwright.sync_api')
    client=web.app.test_client()
    # Pin the exact JPEG before the browser starts. All subsequent operations
    # must work from saved pixels, including the conflicted region request.
    assert client.get('/api/jobs/inline-fixture/finding-preview/0').status_code==200
    monkeypatch.setattr(web,'_frame_at',lambda *a,**k:pytest.fail('Conflict recovery reopened the video'))
    with api.sync_playwright() as pw:
        browser=browser_instance(pw)
        try:
            page=browser.new_page(viewport={'width':width,'height':1000 if width>400 else 844})
            page.set_default_timeout(15000)
            errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            load_browser_page(page,url,[],[])
            page.get_by_role('link',name='Synthetic review fixture',exact=True).click()
            card=page.locator('#det0')
            card.scroll_into_view_if_needed()
            page.wait_for_function('!!document.querySelector("#det0 img")._quadEdit')
            positive=card.get_by_role('button',name='✓ Is a plate',exact=True)
            positive.click()
            page.evaluate('CONFIRM_CHAIN')
            page.wait_for_function('document.getElementById("vlabel0").textContent.includes("Saved")')
            saved=client.get('/api/findings').get_json()['items'][0]
            assert saved['label']=='positive' and saved['revision']==1
            identity=saved['id']

            def external_negative(expected_revision):
                response=client.post('/api/findings/'+identity,json={
                    'label':'negative','expected_revision':expected_revision})
                assert response.status_code==200,response.get_data(as_text=True)
                return response.get_json()['finding']

            newer=external_negative(saved['revision'])
            positive.click()
            page.evaluate('CONFIRM_CHAIN')
            note=card.locator('#vlabel0')
            assert 'Not saved' in note.inner_text()
            assert 'now says Not a plate' in note.inner_text()
            assert card.get_by_role('button',name='Keep current review choice',exact=True).is_visible()
            assert page.evaluate('CONFIRM_FAILED.has(0)') is True
            assert page.evaluate('FINDING_META[0].confirmed_finding_revision')==newer['revision']
            # A rejected click must neither replace newer evidence nor retry
            # automatically. Only the following explicit click may replace it.
            current=client.get('/api/findings/'+identity).get_json()['finding']
            assert current['label']=='negative' and current['revision']==2
            positive.click()
            page.evaluate('CONFIRM_CHAIN')
            restored=client.get('/api/findings/'+identity).get_json()['finding']
            assert restored['label']=='positive' and restored['revision']==3
            assert page.evaluate('CONFIRM_FAILED.has(0)') is False
            assert card.locator('#findingDismiss0').is_hidden()
            assert 'Saved' in note.inner_text()

            # A saved-confirmation region edit is another archive write. Make
            # that revision stale, then ensure the real conflict preserves the
            # visible draft and offers an explicit way to confirm its corners.
            external_negative(restored['revision'])
            before=card.locator('img').evaluate('img=>img._quadEdit.points.map(p=>p.slice())')
            drag_corner(page,card,dx=8,dy=4)
            page.wait_for_function('document.querySelector("#det0 img")._quadEdit.archiveConflict===true')
            draft=card.locator('img').evaluate('img=>img._quadEdit.points.map(p=>p.slice())')
            assert draft[0]!=before[0] and draft[1:]==before[1:]
            assert 'Saved example changed' in card.locator('.quad-status').inner_text()
            assert card.locator('#findingDismiss0').inner_text()=='Discard this unsaved adjustment'
            assert card.locator('#findingDismiss0').is_visible()
            rejected=client.get('/api/findings/'+identity).get_json()['finding']
            assert rejected['revision']==4 and rejected['label']=='negative'
            assert rejected['points'] is None,'A conflicted region must not be advertised as stored'
            positive.click()
            page.evaluate('CONFIRM_CHAIN')
            final=client.get('/api/findings/'+identity).get_json()['finding']
            assert final['revision']==5 and final['label']=='positive' and final['shape_confirmed']
            assert max(abs(a-b) for p,q in zip(final['points'],draft) for a,b in zip(p,q))<.001
            edit=card.locator('img').evaluate('img=>({dirty:img._quadEdit.dirty,conflict:img._quadEdit.archiveConflict,error:!!img._quadEdit.error})')
            assert edit=={'dirty':False,'conflict':False,'error':False}
            assert page.evaluate('CONFIRM_FAILED.has(0)') is False
            assert 'confirmation stored' in card.locator('.quad-status').inner_text()
            row=json.loads(report.read_text())['detections'][0]
            assert row['confirmed_finding_revision']==5 and row['verified_label']=='plate'
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            assert not errors,errors
        finally:
            browser.close()
