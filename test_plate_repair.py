"""End-to-end source-bound off-frame detector repair.

A redrawn plate is a new frame-specific shape, not a borrowed JPEG, a
track-wide box transplant, or an automatic trusted training classification.
"""
import json
import re
import shutil
import sqlite3
import subprocess
import threading
import time

import cv2
import numpy as np
import pytest

import finding_previews
import findings_web
import learning_session
import review_journal
import stop_review
import openscrub_web as web
from test_plate_quad_editor import plate_job
from test_review_browser import review_server, browser_instance, load_browser_page


@pytest.fixture
def broken_plate(plate_job, tmp_path, monkeypatch):
    client, jid, report, job_dir = plate_job
    job = web.JOBS[jid]
    sha = learning_session.sha256(job['video'])
    doc = json.loads(report.read_text(encoding='utf-8'))
    doc['provenance']['input_sha256'] = sha
    doc['source_identity'] = dict(input_sha256=sha, width=240, height=160,
                                  fps=10, total_frames=10)
    doc['detections'][0].update(frame_index=2, aoff=[0, 0],
                                t_start=.2, t_end=.2, last_seen=.2,
                                cbox=[-30, 67, 137, 103])
    # Two independent sightings of the same track. The repair must never
    # transplant one frame's perspective geometry into its moving sibling.
    sibling = dict(doc['detections'][0])
    sibling.update(frame_index=3, t_start=.3, t_end=.3, last_seen=.3)
    doc['detections'].append(sibling)
    stop_review.atomic_report(str(report), doc)
    # Most existing fixtures verify a tiny synthetic source up front. Only
    # the dedicated pending-SHA test must exercise asynchronous verification.
    job['_finding_source_verified'] = dict(
        signature=(web._video_identity(job['video']), sha), sha256=sha)
    monkeypatch.setattr(findings_web, 'root', lambda: tmp_path/'archives')
    return client, jid, report, job_dir, job, doc


def view_and_payload(fixture):
    client, jid, _, _, _, _ = fixture
    pre = client.get(f'/api/jobs/{jid}/finding-preview/0?exact=1')
    assert pre.status_code == 200, pre.get_data(as_text=True)[:400]
    before = json.loads(pre.headers['X-Finding-Geometry'])
    assert before['geometry_outside_frame'] is True
    assert before['classification_allowed'] is False
    view = client.get(f'/api/jobs/{jid}/plate-repair/0/frame')
    assert view.status_code == 200, view.get_data(as_text=True)[:400]
    img = cv2.imdecode(np.frombuffer(view.data, np.uint8), cv2.IMREAD_COLOR)
    assert img is not None and img.shape[:2] == (160, 240)
    shown = json.loads(view.headers['X-Repair-Geometry'])
    assert shown['frame'] == before['frame'] == 2
    assert shown['width'] == 240 and shown['height'] == 160
    # The full-frame correction token is source-bound, not keyed to a
    # disposable thumbnail JPEG. The frame source proof stays identical.
    assert shown['preview_token']
    assert shown['frame_source_token'] == before['frame_source_token']
    assert shown['source_verification'] == 'verified'
    return before, shown, dict(edit_id='source-repair-fixture-1',
                               frame=shown['frame'], points=[
                                   [51., 75.], [126., 75.],
                                   [126., 94.], [51., 94.]],
                               preview_token=shown['preview_token'],
                               frame_source_token=shown['frame_source_token'])


def test_repair_uses_verified_full_frame_and_keeps_siblings_untouched(broken_plate):
    client, jid, report, job_dir, _, doc = broken_plate
    old, shown, payload = view_and_payload(broken_plate)
    unchanged_report = report.read_bytes()
    assert not review_journal.has_changes(job_dir)
    fixed = client.post(f'/api/jobs/{jid}/plate-repair/0', json=payload)
    assert fixed.status_code == 200, fixed.get_data(as_text=True)[:400]
    data = fixed.get_json()
    assert data['ok'] is True and data['applied'] == 1
    assert data['needs_confirmation'] is True
    assert data['verified_samples_added'] == 0
    assert data['preview_ready'] is True
    # The corrected exact-frame JPEG is prepared by the Save request itself.
    # No full video SHA or FFmpeg seek should be needed to reopen it.
    immediate = client.get(f'/api/jobs/{jid}/finding-preview/0?cache_only=1')
    assert immediate.status_code == 200
    assert report.read_bytes() == unchanged_report, 'repair must use durable SQLite journal'
    repaired = review_journal.view(job_dir, json.loads(report.read_text()))['detections']
    assert repaired[1]['cbox'] == doc['detections'][1]['cbox']
    assert repaired[1].get('human_region_confirmed') is not True
    one = repaired[0]
    assert one['cbox'][0] >= 0 and one['cbox'][2] <= 240
    assert one['human_region_confirmed'] is True
    assert one['verified_label'] == ''
    assert one['human_confirmation'] is None
    assert one['confirmed_finding_id'] is None
    assert one['enabled'] is True
    assert one['output_choice_explicit'] is False
    assert len(one['plate_quad']) == 4

    # A subsequent ordinary Review picture uses the new EXACT box, NOT a
    # borrowed off-screen crop from the old track/another source frame.
    now = client.get(f'/api/jobs/{jid}/finding-preview/0')
    assert now.status_code == 200, now.get_data(as_text=True)[:400]
    after = json.loads(now.headers['X-Finding-Geometry'])
    assert after['frame'] == after['requested_frame'] == shown['frame']
    assert not after.get('geometry_outside_frame')
    assert after['source_repaired'] is True
    assert after['classification_allowed'] is True
    assert after['box'] == data['box']
    for got, expected in zip(after['points'], payload['points']):
        assert got == pytest.approx(expected, abs=.01)

    second = client.get(f'/api/jobs/{jid}/finding-preview/0?cache_only=1')
    assert second.status_code == 200
    assert second.data == now.data

    # The corrected frame is durable across a restart/report publication.
    assert review_journal.publish(job_dir)
    saved = json.loads(report.read_text())['detections']
    assert saved[0]['cbox'] == one['cbox']
    assert saved[1]['cbox'] == doc['detections'][1]['cbox']



def test_redraw_preserves_previous_track_decisions_on_other_frames(broken_plate):
    client, jid, report, job_dir, job, doc = broken_plate
    review_journal.write(job_dir, doc['detections'][0], 0,
                         dict(enabled=False, verified_label='not_plate',
                              human_confirmation=dict(
                                  label='negative', category='plate',
                                  source='explicit')),
                         dict(confirmed_finding_id='prior-source-only',
                              confirmed_finding_revision=1))
    before = review_journal.view(job_dir, json.loads(report.read_text()))['detections']
    assert before[0]['enabled'] is False and before[1]['enabled'] is False
    _, _, payload = view_and_payload(broken_plate)
    repaired = client.post(f'/api/jobs/{jid}/plate-repair/0', json=payload)
    assert repaired.status_code == 200, repaired.get_data(as_text=True)
    after = review_journal.view(job_dir, json.loads(report.read_text()))['detections']
    assert after[0]['enabled'] is True
    assert after[0]['human_confirmation'] is None
    assert after[0]['confirmed_finding_id'] is None
    assert after[0]['verified_label'] == ''
    assert after[1]['enabled'] is False
    assert after[1]['verified_label'] == 'not_plate'
    assert after[1]['human_confirmation']['label'] == 'negative'
    assert after[1]['cbox'] == doc['detections'][1]['cbox']
    assert review_journal.publish(job_dir)
    published = json.loads(report.read_text())['detections']
    assert published[1]['human_confirmation']['label'] == 'negative'
    assert published[0]['cbox'] == after[0]['cbox']



def test_full_frame_get_returns_while_source_sha256_runs(broken_plate, monkeypatch):
    """A multi-GB video hash must not occupy the full-image HTTP request."""
    client, jid, report, _, job, doc = broken_plate
    job.pop('_finding_source_verified', None)
    started, release = threading.Event(), threading.Event()
    original_sha = learning_session.sha256

    def delayed_sha(path):
        started.set()
        if not release.wait(15):
            raise TimeoutError('test did not release background hash')
        return original_sha(path)

    monkeypatch.setattr(learning_session, 'sha256', delayed_sha)
    try:
        # An uncached redraw must not inspect/recreate a compact JPEG first.
        with monkeypatch.context() as deny:
            deny.setattr(findings_web, 'preview',
                         lambda *a, **kw: pytest.fail('redraw read a compact JPEG'))
            view = client.get(f'/api/jobs/{jid}/plate-repair/0/frame')
        assert view.status_code == 200, view.get_data(as_text=True)[:300]
        assert started.wait(3)
        shown = json.loads(view.headers['X-Repair-Geometry'])
        assert shown['source_verification'] == 'pending'
        payload = dict(edit_id='slow-hash-but-fast-image',
                       points=[[51., 75.], [126., 75.],
                               [126., 94.], [51., 94.]],
                       frame=shown['frame'],
                       preview_token=shown['preview_token'],
                       frame_source_token=shown['frame_source_token'])
        not_yet = client.post(f'/api/jobs/{jid}/plate-repair/0', json=payload)
        assert not_yet.status_code == 503
        assert 'still running' in not_yet.get_json()['error']
        assert not review_journal.has_changes(job['dir'])
    finally:
        release.set()
    for _ in range(200):
        if job.get('_plate_repair_source_check', {}).get('status') != 'pending':
            break
        time.sleep(.01)
    assert job['_plate_repair_source_check']['status'] == 'verified'
    ready = client.post(f'/api/jobs/{jid}/plate-repair/0', json=payload)
    assert ready.status_code == 200, ready.get_data(as_text=True)[:500]
    assert ready.get_json()['preview_ready'] is True


def test_thumbnail_eviction_during_full_frame_redraw_does_not_conflict(
        broken_plate, monkeypatch):
    client, jid, report, job_dir, job, doc = broken_plate
    # This used to make GET rehash and regenerate the original crop, changing
    # the modal's disposable preview_token while its source frame stayed fixed.
    with monkeypatch.context() as deny:
        deny.setattr(findings_web, 'preview',
                     lambda *a, **kw: pytest.fail('redraw depends on thumbnail key'))
        first = client.get(f'/api/jobs/{jid}/plate-repair/0/frame')
        second = client.get(f'/api/jobs/{jid}/plate-repair/0/frame')
    assert first.status_code == second.status_code == 200
    one = json.loads(first.headers['X-Repair-Geometry'])
    two = json.loads(second.headers['X-Repair-Geometry'])
    assert one['preview_token'] == two['preview_token']
    assert one['frame_source_token'] == two['frame_source_token']
    data = dict(edit_id='after-cache-eviction', frame=one['frame'],
                preview_token=one['preview_token'],
                frame_source_token=one['frame_source_token'],
                points=[[51., 75.], [126., 75.],
                        [126., 94.], [51., 94.]])
    saved = client.post(f'/api/jobs/{jid}/plate-repair/0', json=data)
    assert saved.status_code == 200, saved.get_data(as_text=True)[:500]
    assert saved.get_json()['preview_ready'] is True
    assert client.get(f'/api/jobs/{jid}/finding-preview/0?cache_only=1').status_code == 200


def test_stale_confirmed_preview_can_be_rehydrated_without_losing_repair(
        broken_plate):
    client, jid, report, job_dir, job, doc = broken_plate
    _, _, payload = view_and_payload(broken_plate)
    fixed = client.post(f'/api/jobs/{jid}/plate-repair/0', json=payload)
    assert fixed.status_code == 200
    current = client.get(f'/api/jobs/{jid}/finding-preview/0?cache_only=1')
    assert current.status_code == 200
    first = json.loads(current.headers['X-Finding-Geometry'])
    # Simulate bounded disk-cache eviction after the human has inspected the
    # JPEG but before clicking Is a plate.
    dbpath = job_dir / 'compact_previews' / 'index.sqlite3'
    with sqlite3.connect(dbpath) as db:
        row = db.execute('SELECT length(jpeg),length(CAST(metadata AS BLOB)) '
                         'FROM previews WHERE key=?', (first['key'],)).fetchone()
        assert row
        db.execute('DELETE FROM previews WHERE key=?', (first['key'],))
        db.execute("UPDATE settings SET value=value-1 WHERE key='count'")
        db.execute("UPDATE settings SET value=value-? WHERE key='bytes'",
                   (sum(row),))
    stale = client.post(f'/api/jobs/{jid}/confirm/0', json=dict(
        label='positive', preview_token=first['preview_token'],
        preview_key=first['key']))
    assert stale.status_code == 409
    assert stale.get_json()['conflict'] == 'stale_preview'
    assert client.get(f'/api/jobs/{jid}/finding-preview/0?cache_only=1').status_code == 204

    refreshed = client.get(f'/api/jobs/{jid}/finding-preview/0?exact=1&retry_decode=1')
    assert refreshed.status_code == 200, refreshed.get_data(as_text=True)[:500]
    latest = json.loads(refreshed.headers['X-Finding-Geometry'])
    assert latest['frame_source_token'] == first['frame_source_token']
    assert latest['box'] == first['box']
    assert latest['source_repaired'] is True
    confirmed = client.post(f'/api/jobs/{jid}/confirm/0', json=dict(
        label='positive', preview_token=latest['preview_token'],
        preview_key=latest['key']))
    assert confirmed.status_code == 200, confirmed.get_data(as_text=True)[:500]
    assert confirmed.get_json()['finding']['label'] == 'positive'


def test_repair_is_revision_safe_and_idempotent(broken_plate):
    client, jid, report, _, job, _ = broken_plate
    before = report.read_bytes()
    pre = client.get(f'/api/jobs/{jid}/finding-preview/0?exact=1')
    meta = json.loads(pre.headers['X-Finding-Geometry'])
    data = dict(edit_id='attempt-1', frame=meta['frame'],
                points=[[51, 75], [126, 75], [126, 94], [51, 94]],
                preview_token=meta['preview_token'],
                frame_source_token=meta['frame_source_token'])
    no_view = client.post(f'/api/jobs/{jid}/plate-repair/0', json=data)
    assert no_view.status_code == 409, no_view.get_data(as_text=True)
    assert report.read_bytes() == before

    _, _, original = view_and_payload(broken_plate)
    altered = dict(original, frame_source_token='wrong')
    stale = client.post(f'/api/jobs/{jid}/plate-repair/0', json=altered)
    assert stale.status_code == 409
    outside = dict(original, points=[[51, 75], [126, 75], [126, 500], [51, 94]])
    denied = client.post(f'/api/jobs/{jid}/plate-repair/0', json=outside)
    assert denied.status_code == 400
    assert not review_journal.has_changes(job['dir'])

    result = client.post(f'/api/jobs/{jid}/plate-repair/0', json=original)
    assert result.status_code == 200, result.get_data(as_text=True)
    again = client.post(f'/api/jobs/{jid}/plate-repair/0', json=original)
    assert again.status_code == 200 and again.get_json()['box'] == result.get_json()['box']
    conflict = client.post(f'/api/jobs/{jid}/plate-repair/0',
                           json=dict(original, points=[[53, 75], [126, 75],
                                                       [126, 94], [51, 94]]))
    assert conflict.status_code == 409


def test_source_file_substitution_after_verified_view_is_rejected(broken_plate):
    client, jid, report, job_dir, job, _ = broken_plate
    _, _, payload = view_and_payload(broken_plate)
    with open(job['video'], 'ab') as stream:
        stream.write(b'altered-source')
    rejected = client.post(f'/api/jobs/{jid}/plate-repair/0', json=payload)
    assert rejected.status_code == 409
    assert not review_journal.has_changes(job_dir)


def test_repaired_plate_is_training_only_after_explicit_confirmation(broken_plate):
    client, jid, report, _, job, _ = broken_plate
    _, _, payload = view_and_payload(broken_plate)
    fixed = client.post(f'/api/jobs/{jid}/plate-repair/0', json=payload)
    assert fixed.status_code == 200
    row = review_journal.view(job['dir'], json.loads(report.read_text()))['detections'][0]
    assert not row.get('confirmed_finding_id')
    image = client.get(f'/api/jobs/{jid}/finding-preview/0?exact=1')
    assert image.status_code == 200
    meta = json.loads(image.headers['X-Finding-Geometry'])
    confirmed = client.post(f'/api/jobs/{jid}/confirm/0',
                            json={'label': 'positive', 'preview_token': meta['preview_token'],
                                  'preview_key': meta['key']})
    assert confirmed.status_code == 200, confirmed.get_data(as_text=True)[:800]
    archive = confirmed.get_json()['finding']
    assert archive['label'] == 'positive'
    assert archive['frame'] == 2
    assert archive['box'] == fixed.get_json()['box']
    # After a fresh human label, the frame-specific anchor supersedes the
    # temporary unconfirmed override; other track members keep their geometry.
    updated = review_journal.view(job['dir'], json.loads(report.read_text()))['detections']
    assert updated[0]['human_confirmation']['label'] == 'positive'
    assert updated[0]['confirmed_finding_id'] == archive['id']
    assert updated[1]['cbox'] == [-30, 67, 137, 103]


def test_repaired_corners_remain_frame_only_on_later_drags(broken_plate):
    client, jid, report, _, job, _ = broken_plate
    _, _, payload = view_and_payload(broken_plate)
    assert client.post(f'/api/jobs/{jid}/plate-repair/0', json=payload).status_code == 200
    loaded = client.get(f'/api/jobs/{jid}/finding-preview/0?exact=1')
    meta = json.loads(loaded.headers['X-Finding-Geometry'])
    changed = [[52., 76.], [125., 76.], [125., 93.], [52., 93.]]
    result = client.post(f'/api/jobs/{jid}/finding-region/0', json=dict(
        points=changed, preview_token=meta['preview_token'],
        preview_key=meta['key'], edit_id='drag-1', autosave=True))
    assert result.status_code == 200, result.get_data(as_text=True)[:400]
    assert result.get_json()['applied'] == 1
    rows = review_journal.view(job['dir'], json.loads(report.read_text()))['detections']
    assert rows[1]['cbox'] == [-30, 67, 137, 103]
    assert not rows[1].get('human_region_confirmed')




def test_refresh_picture_keep_corners_recovers_409_in_production_js():
    """Execute the actual Review retry helper with source-safe metadata."""
    if not shutil.which('node'):
        pytest.skip('Node not installed')
    js = web.APP_JS
    helper = js[js.index('async function refreshPlateDraft(s){'):
                js.index('function pumpPlateSaves(){')]
    script = r"""
const assert=require('node:assert/strict');
const CUR='job',PLATE_EDITS=new Map(),CONFIRM_FAILED=new Map();
let refreshes=0,retryScheduled=0,statusTexts=[],cleared=0;
const plateCopy=points=>points.map(p=>p.slice());
const plateSamePreviewSource=(a,b)=>a.frame_source_token===b.frame_source_token;
const plateSameSourceFrame=(a,b)=>a.frame_source_token===b.frame_source_token;
const plateCornersInsideCrop=(p,c)=>p.every(v=>v[0]>=c[0]&&v[0]<=c[2]&&v[1]>=c[1]&&v[1]<=c[3]);
function plateStatus(s,msg){statusTexts.push(msg);}
function schedulePlateSaves(){retryScheduled++;}
function updateConfirmationIssues(){cleared++;}
function plateUnloadGuard(){}
const original={frame:2,box:[40,60,140,120],width:240,height:160,
 crop:[30,50,160,130],frame_source_token:'same-source',source_repaired:true,
 points:[[50,75],[125,75],[125,94],[50,94]]};
const latest={...original,preview_token:'new-key',key:'new-thumbnail'};
let shouldLoad=true;
async function queueReviewPreview(img,priority){
 assert(priority);refreshes++;
 if(!shouldLoad)return false;
 img._plateMeta=latest;
 return true;
}
""" + helper + r"""
(async()=>{
 const img={_plateMeta:original,_forceExactPreview:false,_previewLongRetry:false};
 const s={i:4,job:'job',img,meta:original,
  points:[[52,76],[125,75],[125,93],[52,94]],
  pending:{edit_id:'rejected'},dirty:true,error:{status:409},conflict:true,
  displayCrop:original.crop,refreshBusy:false,drag:null,draw(){}};
 PLATE_EDITS.set(4,s);
 CONFIRM_FAILED.set(4,{status:409,details:{conflict:'stale_preview'}});
 const originalDraft=JSON.stringify(s.points);
 await refreshPlateDraft(s);
 assert.equal(refreshes,1);
 assert.equal(JSON.stringify(s.points),originalDraft,'corners were lost');
 assert.equal(s.meta,latest);
 assert.equal(s.pending,null);
 assert.equal(s.error,null);
 assert.equal(s.conflict,false);
 assert.equal(s.dirty,true);
 assert.equal(s.refreshBusy,false);
 assert(img._forceExactPreview && img._previewLongRetry);
 assert(retryScheduled>=1);
 assert(!CONFIRM_FAILED.has(4));
 assert(cleared>=1);
 shouldLoad=false;
 s.error={status:409};s.conflict=true;s.pending={edit_id:'uncertain'};
 const preserved=JSON.stringify(s.points);
 await refreshPlateDraft(s);
 assert.equal(JSON.stringify(s.points),preserved,'failed reload discarded corners');
 assert.equal(s.meta,latest,'failed reload changed source metadata');
 assert.equal(s.img._plateMeta,latest);
 assert(s.error&&s.conflict);
 assert(s.dirty);
 assert(!s.refreshBusy);
})().catch(error=>{console.error(error);process.exitCode=1});
"""
    result = subprocess.run(['node', '-e', script], capture_output=True,
                            text=True, timeout=15)
    assert result.returncode == 0, result.stderr


def test_real_browser_can_drag_new_box_on_bad_plate_and_confirm(review_server):
    """Real Flask + Chromium: offscreen source box -> full-frame drag -> save."""
    sync_api = pytest.importorskip('playwright.sync_api')
    url, report = review_server
    doc = json.loads(report.read_text())
    doc['detections'][0]['cbox'] = [-50, 120, 420, 220]
    stop_review.atomic_report(str(report), doc)
    with sync_api.sync_playwright() as pw:
        browser = browser_instance(pw)
        page = browser.new_page(viewport={'width': 1360, 'height': 920})
        page.set_default_timeout(30000)
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        requests, posts = [], []
        load_browser_page(page, url, requests, posts)
        page.get_by_role('link', name='Synthetic review fixture', exact=True).click()
        card = page.locator('#det0')
        card.scroll_into_view_if_needed()
        redraw = card.get_by_role('button', name='Redraw plate area')
        redraw.wait_for(state='visible', timeout=90000)
        assert not card.get_by_role('button', name=re.compile(r'Is .*plate')).is_enabled()
        redraw.click()
        modal = page.get_by_role('dialog', name='Redraw plate area on exact original frame')
        modal.wait_for(timeout=90000)
        canvas = modal.locator('canvas')
        bounds = canvas.bounding_box()
        assert bounds and bounds['width'] > 100 and bounds['height'] > 100
        page.mouse.move(bounds['x']+180/640*bounds['width'],
                        bounds['y']+120/360*bounds['height'])
        page.mouse.down()
        page.mouse.move(bounds['x']+420/640*bounds['width'],
                        bounds['y']+220/360*bounds['height'], steps=6)
        page.mouse.up()
        submit = modal.get_by_role('button', name='Save replacement · this frame only')
        assert submit.is_enabled()
        submit.click()
        modal.wait_for(state='detached', timeout=90000)
        page.wait_for_function(
            "document.querySelector('#det0 img')._plateMeta?.source_repaired===true",
            timeout=90000)
        now = card.locator('img').evaluate('(img)=>img._plateMeta')
        assert now['classification_allowed'] is True
        assert now['exact_frame'] is True and now['frame'] == 300
        assert now['box'][0] >= 0
        assert now['box'][2] <= 640
        assert now['box'][1] >= 0 and now['box'][3] <= 360
        assert not redraw.is_visible()
        assert card.get_by_role('button', name=re.compile(r'Is .*plate')).is_enabled()
        # A polygon repair is durable but NOT automatically trusted training.
        with web.app.test_client() as client:
            assert client.get('/api/findings').get_json()['total'] == 0
        assert review_journal.has_changes(web.JOBS['inline-fixture']['dir'])
        assert not errors, errors
        browser.close()


def test_ui_has_full_frame_redraw_and_reenables_confirmation():
    if not shutil.which('node'):
        pytest.skip('Node not installed')
    js = web.APP_JS
    assert 'plate-repair-button' in js
    assert 'openPlateRepair(this)' in js
    assert 'Save replacement · this frame only' in js
    assert 'photo.style.width=Math.round(baseWidth*zoom)' in js
    assert 'FINDING_META[meta.i].classification_allowed=meta.classification_allowed!==false' in js
    helper = js[js.index('function validPlateRepair('):js.index('async function openPlateRepair(')]
    script = ("""
const assert=require('node:assert/strict');
function plateQuadValid(p){
 if(p.length!==4)return false;
 const a=p.reduce((sum,v,i)=>{const w=p[(i+1)%4];return sum+v[0]*w[1]-w[0]*v[1]},0);
 return Math.abs(a)>16;
}
""" + helper + """
assert(validPlateRepair([[2,2],[20,2],[20,15],[2,15]],{width:24,height:20}));
assert(!validPlateRepair([[-1,2],[20,2],[20,15],[2,15]],{width:24,height:20}));
assert(!validPlateRepair([[2,2],[20,2]],{width:24,height:20}));
""")
    result = subprocess.run(['node','-e',script],capture_output=True,text=True,timeout=15)
    assert result.returncode == 0, result.stderr
