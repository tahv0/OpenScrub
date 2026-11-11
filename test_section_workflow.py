"""Saved section revisions, attached rescans and exact-range exports."""
from copy import deepcopy
import json
from pathlib import Path
import threading

import cv2
import numpy as np
import pytest

import openscrub
import openscrub_web as web
import learned_models


@pytest.fixture
def section_job(tmp_path, monkeypatch):
    root = tmp_path / 'jobs'
    folder = root / 'parent'
    folder.mkdir(parents=True)
    video = folder / 'input.mp4'
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*'mp4v'), 10, (96, 64))
    for n in range(40):
        frame = np.full((64, 96, 3), 80+n, np.uint8)
        writer.write(frame)
    writer.release()
    fingerprint = openscrub.sha256_file(str(video))
    doc = dict(provenance=dict(input=str(video), input_sha256=fingerprint, settings={}),
               source_identity=dict(input_sha256=fingerprint, fps=10., total_frames=40),
               render_state=dict(fps=10., cum=[[0,0]]*40, bands=[[0,0]]*40),
               detections=[dict(t_start=n/10, t_end=n/10, last_seen=n/10,
                   frame_index=n, cbox=[10,10,30,25], aoff=[0,0],
                   category='plate', text='SYNTHETIC', confidence=.9,
                   enabled=True, dense=True, track=n, person=-1) for n in [5,15,25]])
    (folder/'report.json').write_text(json.dumps(doc))
    job = dict(id='parent', dir=str(folder), video=str(video), name='Synthetic source',
               options={'categories':'plate'}, phase='review', progress=.5,
               error=None, output=None, log=[], stats={}, created=1,
               cancel=threading.Event(), stop=threading.Event())
    monkeypatch.setattr(web, 'JOBS_DIR', str(root))
    monkeypatch.setattr(web, 'JOBS', {'parent':job})
    monkeypatch.setattr(web, 'TOKEN', None)
    monkeypatch.setattr(web, 'vault_locked', lambda:False)
    queued=[]
    monkeypatch.setattr(web.WORK_Q, 'put', queued.append)
    return web.app.test_client(), job, doc, queued


def create_section(client, start=1, end=2):
    response = client.post('/api/jobs/parent/sections', json={'start':start,'end':end,'name':'Middle'})
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()['section']


def test_approve_range_saves_snapshot_and_export_keeps_exact_bounds(section_job):
    client, job, original, queued = section_job
    section = create_section(client)
    response = client.post('/api/jobs/parent/sections/'+section['id']+'/approve', json={})
    assert response.status_code == 200, response.get_data(as_text=True)
    saved = json.loads((Path(job['dir'])/'report.json').read_text())
    item=saved['video_sections']['items'][0]
    assert item['approved']['revision'] == 1
    snapshot = json.loads((Path(job['dir'])/item['approved']['report']).read_text())
    assert [r['frame_index'] for r in snapshot['detections']] == [15]
    assert saved['detections'] == original['detections']
    exported=client.post('/api/jobs/parent/sections/'+section['id']+'/export', json={})
    assert exported.status_code == 202, exported.get_data(as_text=True)
    export_job=web.JOBS[exported.get_json()['job_id']]
    assert export_job['options']['section_range'] == [10,20]
    assert export_job['video'] == job['video']
    assert queued == [(export_job['id'],'render')]


def test_failed_candidate_keeps_approved_snapshot_and_source(section_job):
    client, job, original, queued = section_job
    section = create_section(client)
    url='/api/jobs/parent/sections/'+section['id']
    assert client.post(url+'/approve', json={}).status_code==200
    approved=(Path(job['dir'])/'report.json').read_bytes()
    response=client.post(url+'/rescan',json={'model_id':''})
    assert response.status_code==202, response.get_data(as_text=True)
    candidate=web.JOBS[response.get_json()['job_id']]
    assert candidate['options']['section_range']==[10,20]
    assert candidate['section']['parent_id']=='parent'
    assert queued==[(candidate['id'],'scan')]
    candidate['phase']='error'
    assert client.post(url+'/approve',json={'candidate_id':candidate['id']}).status_code==409
    current=json.loads((Path(job['dir'])/'report.json').read_text())
    assert current['video_sections']['items'][0]['approved']==json.loads(approved)['video_sections']['items'][0]['approved']
    assert current['detections']==original['detections']
    assert client.delete('/api/jobs/parent').status_code==409
    assert Path(job['video']).exists()


def test_accept_candidate_replaces_only_selected_range(section_job):
    client, job, original, queued=section_job
    section=create_section(client)
    url='/api/jobs/parent/sections/'+section['id']
    response=client.post(url+'/rescan',json={'model_id':''})
    assert response.status_code==202, response.get_data(as_text=True)
    candidate=web.JOBS[response.get_json()['job_id']]
    changed=deepcopy(original)
    changed['detections']=[dict(original['detections'][1], cbox=[40,10,60,25], enabled=False, verified_label='not_plate')]
    changed['provenance']['windows']=[{'t0':0,'t1':.75}]
    (Path(candidate['dir'])/'report.json').write_text(json.dumps(changed))
    candidate['phase']='review'
    response=client.post(url+'/approve',json={'candidate_id':candidate['id']})
    assert response.status_code==200, response.get_data(as_text=True)
    merged=json.loads((Path(job['dir'])/'report.json').read_text())
    rows={r['frame_index']:r for r in merged['detections']}
    assert rows[5]==original['detections'][0]
    assert rows[25]==original['detections'][2]
    assert rows[15]['cbox']==[40,10,60,25]
    assert rows[15]['enabled'] is False
    assert rows[15]['verified_label']=='not_plate'


def test_section_approval_rejects_unscanned_tail_and_overlaps(section_job):
    client, job, original, queued=section_job
    original['stop_review']={'state':'paused','next_frame':15,'total_frames':40,'fps':10.}
    (Path(job['dir'])/'report.json').write_text(json.dumps(original))
    job['phase']='paused'
    section=create_section(client)
    assert client.post('/api/jobs/parent/sections/'+section['id']+'/approve',json={}).status_code==409
    assert client.post('/api/jobs/parent/sections',json={'start':1.5,'end':3}).status_code==400
    assert client.post('/api/jobs/parent/sections',json={'start':2,'end':2}).status_code==400


def test_section_render_owns_half_open_frames(tmp_path):
    d=openscrub.Detection(0., 2., (1,1,5,5), 'plate', '', 1.)
    d.owned_start_frame=10; d.owned_end_frame=20
    assert not openscrub._sample_active(d,9,.9)
    assert openscrub._sample_active(d,10,1.)
    assert openscrub._sample_active(d,19,1.9)
    assert not openscrub._sample_active(d,20,2.)


@pytest.fixture
def section_verifier(section_job, tmp_path):
    from test_learned_models import evaluated_candidate

    source, _, candidate_id, _ = evaluated_candidate(tmp_path / 'verifier-source')
    return learned_models.save_candidate(web.learned_models_root(), source,
                                         candidate_id, 'Garage checker')


def test_section_rescan_does_not_inherit_parent_filter_mode(section_job, section_verifier):
    client, parent, _, queued = section_job
    parent['options'].update(learned_plate_model='previous-model',
                             learned_plate_model_mode='filter')
    section = create_section(client)
    response = client.post('/api/jobs/parent/sections/' + section['id'] + '/rescan',
                           json={'model_id': section_verifier['id']})
    assert response.status_code == 202, response.get_data(as_text=True)
    child = web.JOBS[response.get_json()['job_id']]
    assert child['options'].get('learned_plate_model_mode', 'review') == 'review'
    assert learned_models.load_selection(child['dir']) == 'review'
    saved = json.loads((Path(child['dir']) / 'section-job.json').read_text())
    assert saved['options'].get('learned_plate_model_mode', 'review') == 'review'
    assert parent['options']['learned_plate_model_mode'] == 'filter'
    assert queued == [(child['id'], 'scan')]


def test_section_rescan_persists_explicit_verifier_filter_mode(section_job, section_verifier):
    client, parent, _, queued = section_job
    parent['options']['learned_plate_model_mode'] = 'review'
    section = create_section(client)
    response = client.post('/api/jobs/parent/sections/' + section['id'] + '/rescan',
                           json={'model_id': section_verifier['id'],
                                 'learned_plate_model_mode': 'filter'})
    assert response.status_code == 202, response.get_data(as_text=True)
    child = web.JOBS[response.get_json()['job_id']]
    assert child['options'].get('learned_plate_model_mode') == 'filter'
    assert learned_models.load_selection(child['dir']) == 'filter'
    saved = json.loads((Path(child['dir']) / 'section-job.json').read_text())
    assert saved['options']['learned_plate_model_mode'] == 'filter'
    assert queued == [(child['id'], 'scan')]


@pytest.mark.parametrize('mode', ['automatic', False, {}])
def test_section_rescan_rejects_invalid_mode_before_creating_job(section_job, section_verifier, mode):
    client, parent, _, queued = section_job
    section = create_section(client)
    before = (Path(parent['dir']) / 'report.json').read_bytes()
    response = client.post('/api/jobs/parent/sections/' + section['id'] + '/rescan',
                           json={'model_id': section_verifier['id'],
                                 'learned_plate_model_mode': mode})
    assert response.status_code == 400, response.get_data(as_text=True)
    assert list(web.JOBS) == ['parent'] and queued == []
    assert (Path(parent['dir']) / 'report.json').read_bytes() == before


def test_section_export_clears_model_mode_but_keeps_checker_audit(section_job):
    client, parent, source, queued = section_job
    parent['options']['learned_plate_model_mode'] = 'filter'
    source['verification'] = {'name': 'Garage checker', 'mode': 'filter',
                              'model_sha256': 'b' * 64}
    (Path(parent['dir']) / 'report.json').write_text(json.dumps(source))
    section = create_section(client)
    endpoint = '/api/jobs/parent/sections/' + section['id']
    assert client.post(endpoint + '/approve', json={}).status_code == 200
    response = client.post(endpoint + '/export', json={})
    assert response.status_code == 202, response.get_data(as_text=True)
    child = web.JOBS[response.get_json()['job_id']]
    assert not child['options'].get('learned_plate_model')
    assert not child['options'].get('learned_plate_model_mode')
    assert not (Path(child['dir']) / 'plate_model_selection.json').exists()
    saved = json.loads((Path(child['dir']) / 'section-job.json').read_text())
    assert not saved['options'].get('learned_plate_model_mode')
    exported = json.loads((Path(child['dir']) / 'report.json').read_text())
    assert exported['verification'] == source['verification']
    assert queued == [(child['id'], 'render')]


def test_approved_checker_candidate_names_model_and_clears_whole_video_audit(section_job):
    client, parent, source, _ = section_job
    old_audit = {'name': 'Old checker', 'mode': 'review', 'model_sha256': 'a' * 64}
    source['verification'] = old_audit
    parent['verification'] = old_audit
    (Path(parent['dir']) / 'report.json').write_text(json.dumps(source))
    section = create_section(client)
    endpoint = '/api/jobs/parent/sections/' + section['id']
    response = client.post(endpoint + '/rescan', json={})
    assert response.status_code == 202, response.get_data(as_text=True)
    child = web.JOBS[response.get_json()['job_id']]
    candidate = deepcopy(source)
    candidate['verification'] = {'name': 'New checker', 'mode': 'filter',
                                 'model_sha256': 'b' * 64}
    (Path(child['dir']) / 'report.json').write_text(json.dumps(candidate))
    child['phase'] = 'review'
    response = client.post(endpoint + '/approve', json={'candidate_id': child['id']})
    assert response.status_code == 200, response.get_data(as_text=True)
    assert response.get_json()['section']['approved']['model'] == 'New checker'
    merged = json.loads((Path(parent['dir']) / 'report.json').read_text())
    assert 'verification' not in merged and 'verification' not in parent
    assert [record['verification']['name'] for record in merged['range_provenance']] == [
        'Old checker', 'New checker', 'Old checker']
