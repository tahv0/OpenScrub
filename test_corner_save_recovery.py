"""Permanent boundary/retry/unsaved-card regression coverage (synthetic data)."""
import json
import os
from pathlib import Path
import subprocess

import numpy as np
import pytest
import confirmed_findings
import openscrub_web as web
from test_plate_quad_editor import plate_job
from test_review_browser import review_server, browser_instance, load_browser_page, drag_corner, plate_points


USER_OLD = [[1024, 1753], [1617, 2072.8881298035867], [1472, 2160], [1024, 2160]]
USER_NEW = [[1617, 1741.2467976088813], [1617, 2113.2228864218614],
            [1546.8569265707797, 2159], [1031.4897804693414, 2159]]


def test_exact_4k_bottom_boundary_saves_and_retries_once(plate_job, monkeypatch):
    client, jid, path, folder = plate_job
    doc = json.loads(path.read_text())
    doc['detections'][0]['cbox'] = [1024, 1753, 1472, 2160]
    path.write_text(json.dumps(doc))
    image = np.zeros((2160, 3840, 3), np.uint8)
    monkeypatch.setattr(web, '_frame_at', lambda *a, **k: image.copy())
    endpoint = '/api/jobs/%s/plate_quad/0' % jid
    meta = client.get(endpoint).get_json()
    body = dict(points=USER_OLD, autosave=True, edit_id='bottom-edge', preview_token=meta['preview_token'])
    r = client.post(endpoint, json=body)
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['preview']['points'][2][1] == 2160
    assert client.post(endpoint, json=body).status_code == 200
    entries = (folder/'plate_annotations/annotations.jsonl').read_text().splitlines()
    assert len(entries) == 1
    # Then save exactly the user's current visible geometry, not the old request.
    body.update(points=USER_NEW, edit_id='current-shape', preview_token=r.get_json()['preview']['preview_token'])
    r = client.post(endpoint, json=body)
    assert r.status_code == 200, r.get_json()
    assert np.allclose(r.get_json()['preview']['points'], USER_NEW, atol=.001)


@pytest.mark.parametrize('side', ['left', 'right', 'top', 'bottom'])
def test_rounded_boundary_roundtrip_and_warm_reedit(plate_job, monkeypatch, side):
    client, jid, path, folder = plate_job
    doc = json.loads(path.read_text())
    doc['detections'][0]['cbox'] = [7, 9, 120, 86]
    path.write_text(json.dumps(doc))
    points = {'left':[[0,30],[50,30],[50,70],[0,70]],
              'right':[[200,30],[240,30],[240,70],[200,70]],
              'top':[[30,0],[80,0],[80,40],[30,40]],
              'bottom':[[30,120],[80,120],[80,160],[30,160]]}[side]
    endpoint = '/api/jobs/%s/plate_quad/0' % jid
    r = client.post(endpoint, json=dict(points=points, autosave=True, edit_id='edge-1'))
    assert r.status_code == 200, r.get_json()
    meta = r.get_json()['preview']
    p = np.array(meta['points'])
    assert (p >= 0).all() and (p <= [240,160]).all(), 'Returned handles must remain in the image'
    monkeypatch.setattr(web, '_frame_at', lambda *a, **k: pytest.fail('Warm border edit must reuse its crop'))
    fresh = client.get(endpoint).get_json()
    assert np.allclose(fresh['points'], p)
    # Leave the boundary points alone; move just one non-boundary coordinate.
    next_points = fresh['points']
    next_points[0][1 if side in ('left','right') else 0] += 1
    r = client.post(endpoint, json=dict(points=next_points, autosave=True, edit_id='edge-2',
                                        preview_token=fresh['preview_token']))
    assert r.status_code == 200, r.get_json()
    assert len((folder/'plate_annotations/annotations.jsonl').read_text().splitlines()) == 1


def test_micro_roundoff_is_accepted_but_real_overflow_names_corners(plate_job):
    client, jid, path, folder = plate_job
    endpoint = '/api/jobs/%s/plate_quad/0' % jid
    p = [[-0.000003,30],[100,30],[100,80],[-0.000003,80]]
    r = client.post(endpoint, json=dict(points=p, autosave=True, edit_id='tiny-roundoff'))
    assert r.status_code == 200, r.get_json()
    before = path.read_bytes()
    manifest = (folder/'plate_annotations/annotations.jsonl').read_bytes()
    r = client.post(endpoint, json={'points':[[10,100],[100,100],[100,161],[10,161]]})
    assert r.status_code == 400
    data = r.get_json()
    assert data['invalid_corners'] == [3,4]
    assert data['frame_size'] == [240,160]
    assert '3' in data['error'] and '4' in data['error'] and '161' in data['error']
    assert path.read_bytes() == before
    assert (folder/'plate_annotations/annotations.jsonl').read_bytes() == manifest


def test_rejected_payload_is_replaced_but_ambiguous_retry_keeps_id(tmp_path):
    js = web.APP_JS
    helpers = js[js.index('let QEDIT=null;'):js.index('function initPlateCorners(')]
    script = r'''
const assert=require('node:assert/strict');
const window={removeEventListener(){},addEventListener(){}};
const document={getElementById(){return null}};
let VLBL={},CUR='test',requests=[],ok,no;
function setTimeout(){return 1} function clearTimeout(){}
function reviewRequest(url,opts){requests.push(JSON.parse(opts.body));return new Promise((a,b)=>{ok=a;no=b});}
''' + helpers + r'''
const old=OLD_POINTS,current=NEW_POINTS;
const meta={box:[1024,1753,1472,2160],points:old,crop:[0,0,3840,2160],width:3840,height:2160,track:1,frame:15768,preview_token:'old'};
function make(){return {i:12537,job:'test',meta:{...meta},img:{},points:plateCopy(old),saved:plateCopy(old),
 version:1,dirty:true,pending:null,readyAt:0,failures:0,status:{textContent:'',scrollIntoView(){}},retry:{hidden:true},draw(){}};}
function ack(s){ok({data:{preview:{...s.meta,points:requests.at(-1).points,preview_token:'new'}}});}
function gesture(s){const before=plateCopy(s.points);s.points=plateCopy(current);commitPlateGesture(s,before);s.readyAt=0;}
(async()=>{
 const s=make();PLATE_EDITS.set(s.i,s);
 const a=pumpPlateSaves();no(Object.assign(new Error('Corners must be inside the video frame'),{status:400}));await a;
 assert.equal(s.pending,null,'Definite 400 must not retain an impossible retry');
 const firstId=requests[0].edit_id;gesture(s);
 const b=pumpPlateSaves();assert.deepEqual(requests.at(-1).points,current);assert.notEqual(requests.at(-1).edit_id,firstId);ack(s);await b;assert.ok(!s.dirty);
 // New gesture while the invalid older request is still in flight also proceeds.
 s.points=plateCopy(old);s.dirty=true;s.version++;s.readyAt=0;
 const c=pumpPlateSaves();gesture(s);no(Object.assign(new Error('rejected'),{status:400}));await c;
 assert.ok(s.dirty&&!s.error&&!s.pending,'Old rejection must not block an already corrected gesture');
 const d=pumpPlateSaves();assert.deepEqual(requests.at(-1).points,current);ack(s);await d;
 // A timeout/502 may have committed: retain ID and exact payload for retry.
 for(const status of [undefined,502]){
  s.dirty=true;s.version++;s.readyAt=0;
  const e=pumpPlateSaves();const id=requests.at(-1).edit_id;
  no(Object.assign(new Error('lost response'),{status}));await e;assert.ok(s.pending);
  await retryPlateSave(s);const f=pumpPlateSaves();assert.equal(requests.at(-1).edit_id,id);ack(s);await f;
 }
 console.log('Exact coordinates, 400 recovery, in-flight correction and unknown-write idempotency pass');
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    script = script.replace('OLD_POINTS',json.dumps(USER_OLD)).replace('NEW_POINTS',json.dumps(USER_NEW))
    file = tmp_path/'recovery.js';file.write_text(script)
    r = subprocess.run(['node',str(file)],capture_output=True,text=True,timeout=15)
    assert r.returncode == 0, r.stdout+r.stderr



def test_busy_saved_picture_retries_without_manual_action(tmp_path):
    js=web.APP_JS
    helpers=js[js.index('let QEDIT=null;'):js.index('function initPlateCorners(')]
    script=r'''
const assert=require('node:assert/strict');
const window={removeEventListener(){},addEventListener(){}};
const document={getElementById(){return null}};
let VLBL={},CUR='job',requests=[],resolve,reject;
function setTimeout(){return 1} function clearTimeout(){}
function reviewRequest(url,options){
 requests.push(options);
 return new Promise((ok,no)=>{resolve=ok;reject=no;});
}
''' + helpers + r'''
const corners=[[20,20],[80,20],[80,50],[20,50]];
const meta={box:[20,20,80,50],points:corners,crop:[0,0,100,100],
 width:100,height:100,track:7,frame:42,preview_token:'first',compact:true};
const s={i:1,job:'job',meta,img:{},points:plateCopy(corners),saved:plateCopy(corners),
 version:1,dirty:true,pending:null,readyAt:0,failures:0,draw(){},
 status:{textContent:''},retry:{hidden:true},card:null};
(async()=>{
 PLATE_EDITS.set(s.i,s);
 const first=pumpPlateSaves();
 assert.equal(requests[0].timeoutMs,120000,'Corner save was stopped by the 15-second thumbnail deadline');
 const refusedId=JSON.parse(requests[0].body).edit_id;
 reject(Object.assign(new Error('Saved pictures are temporarily busy. Retry shortly.'),{status:503}));
 await first;
 assert.equal(s.pending,null,'A definite 503 should not reuse a rejected edit ID');
 assert.equal(s.error,undefined,'Busy preview must not require manual Retry save');
 assert.equal(s.retry.hidden,true);
 assert.ok(s.status.textContent.includes('retrying save'));
 s.readyAt=0;
 const next=pumpPlateSaves();
 assert.notEqual(JSON.parse(requests[1].body).edit_id,refusedId);
 resolve({data:{preview:{...meta,points:corners,preview_token:'second'},
  applied:1,classification_required:true}});
 await next;
 assert.equal(s.dirty,false);
 assert.equal(s.retry.hidden,true);
 assert.equal(s.pending,null);
 console.log('Automatic 503 retry, durable save deadline, and idempotency pass');
})().catch(error=>{console.error(error);process.exitCode=1});
'''
    result=subprocess.run(['node','-e',script],capture_output=True,text=True,timeout=8)
    assert result.returncode==0,result.stdout+result.stderr

@pytest.mark.parametrize('width',[1440,390])
def test_hidden_failed_card_can_be_found_corrected_and_saved(review_server, monkeypatch, width, tmp_path):
    from flask import jsonify, request
    url, path = review_server
    original = web.app.view_functions['job_plate_quad']
    received = []
    def reject_first(*a, **k):
        if request.method=='POST':
            received.append(request.get_json())
            if len(received)==1:
                return jsonify(error='Corner 3 outside video frame: y=361 exceeds 360',invalid_corners=[3],frame_size=[640,360]),400
        return original(*a, **k)
    monkeypatch.setitem(web.app.view_functions,'job_plate_quad',reject_first)
    api=pytest.importorskip('playwright.sync_api')
    with api.sync_playwright() as pw:
        browser=browser_instance(pw);page=browser.new_page(viewport={'width':width,'height':1000 if width>400 else 844})
        page.set_default_timeout(12000);errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('dialog',lambda d:d.accept())
        load_browser_page(page,url,[],[])
        assert page.title()=='OpenScrub'
        page.get_by_role('link',name='Synthetic review fixture',exact=True).click()
        card=page.locator('#det1');card.scroll_into_view_if_needed()
        page.wait_for_function('!!document.querySelector("#det1 img")._quadEdit')
        page.evaluate('window.originalCard=document.getElementById("det1")')
        drag_corner(page,card)
        page.wait_for_function('!!PLATE_EDITS.get(1).error')
        page.get_by_role('button',name='Review 10% of plate groups',exact=True).click()
        assert card.is_hidden(), 'Frame 1 is not in the temporal 10% sample'
        page.get_by_role('button',name='Show finding #1',exact=True).click()
        assert card.is_visible()
        assert page.evaluate('document.getElementById("det1")===originalCard')
        assert 'frame 300' in page.locator('#plateSaveIssues').inner_text()
        assert card.evaluate('(el)=>el.classList.contains("corner-save-error")')
        assert page.evaluate('document.activeElement===PLATE_EDITS.get(1).cv')
        evidence=Path(os.environ.get('REVIEW_EVIDENCE_DIR',str(tmp_path)));evidence.mkdir(parents=True,exist_ok=True)
        page.screenshot(path=str(evidence/('corner-save-issue-%s.png'%width)))
        # Correct by an actual new drag; no console repair or Reload required.
        drag_corner(page,card,index=2,dx=-5,dy=-3)
        latest=plate_points(card)
        page.wait_for_function('!PLATE_EDITS.get(1).dirty&&!PLATE_EDITS.get(1).pending')
        assert len(received)==2
        assert received[0]['edit_id']!=received[1]['edit_id']
        assert received[1]['points']==latest
        assert page.locator('#plateSaveIssues').is_hidden()
        assert page.evaluate('saveAndRender(true)') is True
        assert 'saved to disk' in page.locator('#reviewSaveStatus').inner_text()
        page.evaluate('loadReview()')
        card=page.locator('#det1');card.scroll_into_view_if_needed()
        page.wait_for_function('!!document.querySelector("#det1 img")._quadEdit')
        assert np.allclose(plate_points(card),latest,atol=.001)
        assert not errors,errors
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        browser.close()


def test_boundary_preview_drag_preserves_edge_without_handle_jump(review_server, tmp_path):
    url,path=review_server
    doc=json.loads(path.read_text());doc['detections']=doc['detections'][:1]
    doc['detections'][0]['cbox']=[180,240,420,360]
    path.write_text(json.dumps(doc))
    api=pytest.importorskip('playwright.sync_api')
    with api.sync_playwright() as pw:
        browser=browser_instance(pw);page=browser.new_page(viewport={'width':1440,'height':1000})
        page.set_default_timeout(12000);errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        load_browser_page(page,url,[],[])
        page.get_by_role('link',name='Synthetic review fixture',exact=True).click()
        card=page.locator('#det0');card.scroll_into_view_if_needed()
        page.wait_for_function('!!document.querySelector("#det0 img")._quadEdit')
        # A border-touching detector guess is not an implicitly verified sample.
        assert not (path.parent/'plate_annotations').exists()
        card.locator('canvas').focus();page.keyboard.press('3');page.keyboard.press('ArrowLeft')
        page.wait_for_function('document.querySelector("#det0 .quad-status").textContent.startsWith("Saved")')
        before=plate_points(card)
        assert before[2][1]==360 and before[3][1]==360
        handle=page.evaluate('''()=>{const s=PLATE_EDITS.get(0),c=s.displayCrop,r=s.cv.getBoundingClientRect(),p=s.points[2];
         return {x:r.left+Math.max(9,Math.min(r.width-9,(p[0]-c[0])*r.width/(c[2]-c[0]))),
          y:r.top+Math.max(9,Math.min(r.height-9,(p[1]-c[1])*r.height/(c[3]-c[1]))),scale:(c[2]-c[0])/r.width};}''')
        page.mouse.move(handle['x'],handle['y']);page.mouse.down()
        page.mouse.move(handle['x']-2,handle['y'],steps=3);page.mouse.up()
        page.wait_for_function('!PLATE_EDITS.get(0).dirty&&!PLATE_EDITS.get(0).pending')
        after=plate_points(card)
        assert after[2][1]==360, 'An inset handle must not pull a valid edge inward on a horizontal drag'
        assert after[2][0]==pytest.approx(before[2][0]-2*handle['scale'],abs=.001)
        archive=path.parent.parent/'confirmed_findings'
        assert confirmed_findings.list_findings(archive)['total']==0, 'Area-only edits are drafts'
        assert not (path.parent/'plate_annotations').exists()
        card.get_by_role('button',name='✓ Is a plate',exact=True).click()
        page.evaluate('CONFIRM_CHAIN')
        assert page.evaluate('CONFIRM_PENDING.size===0&&CONFIRM_FAILED.size===0')
        saved=confirmed_findings.list_findings(archive)
        assert saved['total']==1
        entry=saved['items'][0]
        assert entry['label']=='positive' and entry['shape_confirmed']
        assert np.allclose(entry['points'],after,atol=.001)
        assert confirmed_findings.image_path(archive,entry['id']).is_file()
        assert not errors,errors
        browser.close()


def test_boundary_saved_example_is_usable_by_feedback_collector(plate_job):
    import learning_session as ls
    import openscrub
    client,jid,path,folder=plate_job
    r=client.post('/api/jobs/%s/plate_quad/0'%jid,json={
        'points':[[0,120],[90,120],[90,160],[0,160]],'autosave':True,'edit_id':'edge-training'})
    assert r.status_code==200,r.get_json()
    doc=json.loads(path.read_text());job=web.JOBS[jid]
    doc['provenance']['input_sha256']=openscrub.sha256_file(job['video'])
    feedback=ls.collect_feedback(job,doc,lambda i:web._read_exact_frame(job['video'],i))
    assert len(feedback['samples'])==1
    sample=next(iter(feedback['samples'].values()))
    assert sample['quality']=='human_quad'
    assert np.all(np.asarray(sample['points'])>=0) and np.all(np.asarray(sample['points'])<=1)
