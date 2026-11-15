"""End-to-end source-bound off-frame detector repair.

A redrawn plate is a new frame-specific shape, not a borrowed JPEG, a
track-wide box transplant, or an automatic trusted training classification.
"""
import json
import shutil
import subprocess

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
    assert shown['preview_token'] == before['preview_token']
    assert shown['frame_source_token'] == before['frame_source_token']
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
