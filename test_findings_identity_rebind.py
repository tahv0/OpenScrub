"""Regression coverage: changing a confirmed finding's source-frame/box
must preserve the original training archive while saving the new review area.
"""
import json
import subprocess
import shutil

import pytest

import openscrub_web as web
import review_journal
from test_findings_web import findings_job


def _confirm(client, job, label):
    response = client.post(f"/api/jobs/{job['id']}/confirm/0", json={'label': label})
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()['finding']


def _move_box(report):
    # Other report publishers must first make committed SQLite corrections
    # part of the authoritative snapshot. Moving a source box while the
    # journal still targets the previous version must fail closed.
    review_journal.publish(report.parent)
    data = json.loads(report.read_text())
    data['detections'][0]['cbox'] = [26, 24, 72, 40]
    report.write_text(json.dumps(data))


def _preview(client, job):
    response = client.get(f"/api/jobs/{job['id']}/finding-preview/0")
    assert response.status_code == 200, response.get_data(as_text=True)
    return json.loads(response.headers['X-Finding-Geometry'])


@pytest.mark.parametrize('original_label', ['positive', 'negative'])
def test_relocalized_confirmed_corners_save_as_protected_draft(
        findings_job, original_label):
    client, job, _, report = findings_job
    original = _confirm(client, job, original_label)
    original_id, original_revision = original['id'], original['revision']
    _move_box(report)
    meta = _preview(client, job)
    points = [list(p) for p in meta['points']]
    points[0][0] += 1
    payload = {'compact': True, 'autosave': True, 'edit_id': 'moved-frame-draft',
               'points': points, 'preview_token': meta['preview_token']}
    uri = f"/api/jobs/{job['id']}/plate_quad/0"
    response = client.post(uri, json=payload)
    assert response.status_code == 200, response.get_data(as_text=True)
    result = response.get_json()
    assert result['reconfirmation_required'] is True
    assert result['classification_required'] is True
    assert result['cleared_indices'] == [0]
    saved_bytes = report.read_bytes()
    row = json.loads(saved_bytes)['detections'][0]
    assert len(row['plate_quad']) == 4 and row['human_region_confirmed']
    assert row['enabled'] is True, 'An old negative must not expose a changed source image'
    assert row['verified_label'] == ''
    assert not row['output_choice_explicit']
    assert not row.get('human_confirmation')
    assert not row.get('confirmed_finding_id')

    # Retransmission after a lost HTTP acknowledgement is idempotent and
    # returns the same re-confirmation instruction without a report rewrite.
    again = client.post(uri, json=payload)
    assert again.status_code == 200, again.get_data(as_text=True)
    assert again.get_json()['reconfirmation_required'] is True
    assert report.read_bytes() == saved_bytes

    archived = client.get(f"/api/findings/{original_id}").get_json()['finding']
    assert archived['id'] == original_id
    assert archived['revision'] == original_revision
    assert archived['label'] == original_label
    assert archived['box'] != result['preview']['box']
    assert client.get('/api/findings').get_json()['total'] == 1

    new_meta = _preview(client, job)
    new_response = client.post(f"/api/jobs/{job['id']}/confirm/0", json={
        'label': 'positive', 'preview_token': new_meta['preview_token']})
    assert new_response.status_code == 200, new_response.get_data(as_text=True)
    newer = new_response.get_json()['finding']
    assert newer['id'] != original_id
    assert newer['frame'] == original['frame']
    assert newer['box'] == result['preview']['box']
    assert client.get('/api/findings').get_json()['total'] == 2



def test_moved_negative_group_restores_default_protection_for_all_members(
        findings_job):
    client, job, _, report = findings_job
    original_doc = json.loads(report.read_text())
    original_doc['detections'][1]['track'] = original_doc['detections'][0]['track']
    report.write_text(json.dumps(original_doc))
    previous = _confirm(client, job, 'negative')
    verified = web._load_job_report(job)['detections']
    assert all(not verified[i]['enabled'] and
               verified[i]['verified_label'] == 'not_plate'
               for i in (0, 1))
    assert verified[1]['human_confirmation']['propagated'] is True
    _move_box(report)
    meta = _preview(client, job)
    points = [list(p) for p in meta['points']]
    points[0][0] += 1
    result = client.post(f"/api/jobs/{job['id']}/plate_quad/0", json={
        'compact': True, 'points': points,
        'preview_token': meta['preview_token']})
    assert result.status_code == 200, result.get_data(as_text=True)
    assert result.get_json()['cleared_indices'] == [0, 1]
    after = json.loads(report.read_text())['detections']
    for i in (0, 1):
        assert after[i]['enabled'] is True
        assert after[i]['verified_label'] == ''
        assert not after[i]['output_choice_explicit']
        assert not after[i].get('human_confirmation')
    assert client.get(f"/api/findings/{previous['id']}").status_code == 200



def test_explicit_reconfirmation_rebinds_to_new_identity_without_reusing_old_revision(
        findings_job):
    client, job, _, report = findings_job
    previous = _confirm(client, job, 'negative')
    _move_box(report)
    meta = _preview(client, job)
    response = client.post(f"/api/jobs/{job['id']}/confirm/0", json={
        'label': 'positive', 'preview_token': meta['preview_token'],
        'expected_revision': previous['revision']})
    assert response.status_code == 200, response.get_data(as_text=True)
    new = response.get_json()['finding']
    assert new['id'] != previous['id']
    assert new['revision'] == 1
    assert new['label'] == 'positive'
    assert client.get(f"/api/findings/{previous['id']}").get_json()['finding']['label'] == 'negative'


def test_changed_original_video_identity_must_not_migrate_confirmation(
        findings_job):
    client, job, _, report = findings_job
    previous = _confirm(client, job, 'negative')
    review_journal.publish(report.parent)
    data = json.loads(report.read_text())
    data['provenance']['original_input_sha256'] = 'f' * 64
    report.write_text(json.dumps(data))
    before = report.read_bytes()
    meta = _preview(client, job)
    result = client.post(f"/api/jobs/{job['id']}/plate_quad/0", json={
        'compact': True, 'points': meta['points'],
        'preview_token': meta['preview_token']})
    assert result.status_code == 409, result.get_data(as_text=True)
    assert 'different source or timeline' in result.get_json()['error']
    assert report.read_bytes() == before
    assert client.get(f"/api/findings/{previous['id']}").status_code == 200


def test_area_only_updates_of_same_archive_identity_remain_versioned(
        findings_job):
    client, job, _, report = findings_job
    original = _confirm(client, job, 'positive')
    meta = _preview(client, job)
    points = [list(p) for p in meta['points']]
    points[0][0] += 1
    result = client.post(f"/api/jobs/{job['id']}/plate_quad/0", json={
        'compact': True, 'points': points, 'preview_token': meta['preview_token']})
    assert result.status_code == 200, result.get_data(as_text=True)
    data = result.get_json()
    assert not data['reconfirmation_required']
    assert data['finding']['id'] == original['id']
    assert data['finding']['revision'] == original['revision'] + 1
    assert client.get('/api/findings').get_json()['total'] == 1


def test_browser_rebound_state_protects_cleared_confirmations():
    if not shutil.which('node'):
        pytest.skip('node is needed for Review browser regression')
    js=web.APP_JS
    begin=js.index('function applyReboundFindingState(')
    end=js.index('function pumpPlateSaves(', begin)
    script=r"""
const assert=require('node:assert/strict');
const FINDING_META={0:{human_confirmation:{label:'negative'},confirmed_finding_id:'old',verified_label:'not_plate'},
                   1:{human_confirmation:{label:'negative',propagated:true},verified_label:'not_plate'}};
const EN={0:false,1:false},VLBL={0:'not_plate',1:'not_plate'};
const OUTPUT_CHOICES={0:true,1:true},OUTPUT_VERSION={};
const REVIEW_BASE={job:'current',enabled:{0:false,1:false},labels:{0:'not_plate',1:'not_plate'},output_choices:{0:true,1:true}};
const nodes={};const document={getElementById(id){return nodes[id]||null}};
for(const i of [0,1]){
 nodes['det'+i]={classList:{remove(){}}};nodes['bb'+i]={innerHTML:''};
 nodes['vlabel'+i]={textContent:''};
}
function detChoices(i){return EN[i]?'blur':'keep'};
function redrawReviewOverlay(){}
"""+js[begin:end]+r"""
applyReboundFindingState({i:0,job:'current'}, {reconfirmation_required:true,cleared_indices:[0,1]});
assert.equal(EN[0],true);assert.equal(EN[1],true);
assert.equal(VLBL[0],'');assert.equal(VLBL[1],'');
assert.equal(FINDING_META[0].confirmed_finding_id,undefined);
assert.equal(REVIEW_BASE.enabled[0],true);
assert.equal(REVIEW_BASE.labels[0],undefined);
assert.equal(OUTPUT_CHOICES[0],undefined);
assert.ok(nodes.vlabel0.textContent.includes('confirm Is / Not again'));
console.log('Updated source identity clears old negative and restores protective output');
"""
    result=subprocess.run(['node','-e',script],capture_output=True,text=True,timeout=5)
    assert result.returncode==0,result.stdout+result.stderr
