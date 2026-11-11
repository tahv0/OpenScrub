"""Immutable section exports and approval preservation through worker resume."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import openscrub_web as web
import stop_review
import video_sections
from test_section_workflow import section_job, create_section


def approved_export(client):
    section = create_section(client)
    endpoint = '/api/jobs/parent/sections/' + section['id']
    approved = client.post(endpoint + '/approve', json={})
    assert approved.status_code == 200, approved.get_data(as_text=True)
    exported = client.post(endpoint + '/export', json={})
    assert exported.status_code == 202, exported.get_data(as_text=True)
    return web.JOBS[exported.get_json()['job_id']]


def test_approved_export_retry_cannot_replace_snapshot_with_fresh_scan(section_job):
    client, _, _, queued = section_job
    export = approved_export(client)
    export['phase'] = 'error'
    snapshot = (Path(export['dir']) / 'report.json').read_bytes()
    pending = list(queued)
    response = client.post('/api/jobs/' + export['id'] + '/retry')
    assert response.status_code == 409, response.get_data(as_text=True)
    assert queued == pending
    assert export['phase'] == 'error'
    assert (Path(export['dir']) / 'report.json').read_bytes() == snapshot


def test_approved_export_learning_cannot_replace_approved_geometry(section_job, monkeypatch, tmp_path):
    client, _, _, queued = section_job
    export = approved_export(client)
    export['phase'] = 'review'
    weights = tmp_path / 'training.pt'
    weights.write_bytes(b'route preflight only; no training runs in this test')
    monkeypatch.setenv('OPENSCRUB_TRAIN_WEIGHTS', str(weights))
    pending = list(queued)
    response = client.post('/api/jobs/' + export['id'] + '/learning',
                           json={'license_accepted': True})
    assert response.status_code == 409, response.get_data(as_text=True)
    assert queued == pending
    assert export['phase'] == 'review'


def test_successful_resume_retains_locked_approval_and_range_provenance(section_job, monkeypatch):
    client, job, source, _ = section_job
    source['render_state']['cum'] = source['render_state']['cum'][:30]
    source['render_state']['bands'] = source['render_state']['bands'][:30]
    paused = stop_review.with_checkpoint(source, 30, 40, {'categories': 'plate'})
    paused['range_provenance'] = [{
        'start_frame': 0, 'end_frame': 40,
        'source_identity': deepcopy(source['source_identity']),
        'provenance': deepcopy(source['provenance']),
    }]
    report = Path(job['dir']) / 'report.json'
    stop_review.atomic_report(report, paused)
    job['phase'] = 'paused'
    section = create_section(client)
    response = client.post('/api/jobs/parent/sections/' + section['id'] + '/approve', json={})
    assert response.status_code == 200, response.get_data(as_text=True)
    before = json.loads(report.read_text())

    class OneJobQueue:
        def __init__(self):
            self.pending = []
            self.finished = 0

        def put(self, item):
            self.pending.append(item)

        def get(self):
            if not self.pending:
                raise StopIteration
            return self.pending.pop(0)

        def task_done(self):
            self.finished += 1

    queue = OneJobQueue()
    monkeypatch.setattr(web, 'WORK_Q', queue)

    def scanned_suffix(args, callback):
        return {
            'fps': 10., 'cum': [(0., 0.)] * 40, 'bands': [(0., 0.)] * 40,
            'detections': [], 'zdropped': [], 'stop_at_frame': None,
            'total_frames': 40, 'input_sha256': source['source_identity']['input_sha256'],
            'stats': {},
        }

    monkeypatch.setattr(web.openscrub, 'run_scan', scanned_suffix)
    thread_factory = web.threading.Thread
    background = []

    def tracked_thread(*args, **kwargs):
        thread = thread_factory(*args, **kwargs)
        background.append(thread)
        return thread

    monkeypatch.setattr(web.threading, 'Thread', tracked_thread)
    response = client.post('/api/jobs/parent/resume')
    assert response.status_code == 200, response.get_data(as_text=True)
    try:
        with pytest.raises(StopIteration):
            web.worker()
    finally:
        for thread in background:
            thread.join(timeout=5)
    assert queue.finished == 1
    assert job['phase'] == 'review', job.get('error')
    resumed = json.loads(report.read_text())
    assert 'stop_review' not in resumed
    assert resumed.get('video_sections') == before['video_sections']
    assert resumed.get('source_identity') == before['source_identity']
    assert resumed.get('range_provenance') == before['range_provenance']
    # Approval must still block a reviewer edit after the continuation commits.
    changed = client.post('/api/jobs/parent/detections', json={'enabled': {'1': False}})
    assert changed.status_code == 409, changed.get_data(as_text=True)


def test_accepting_new_masks_keeps_old_output_unavailable_after_restart(section_job, monkeypatch):
    client, job, source, _ = section_job
    output = Path(job['dir']) / 'output.mp4'
    output.write_bytes(b'previous video: does not contain the newly approved masks')
    job.update(output=str(output), phase='done')
    section = create_section(client)
    endpoint = '/api/jobs/parent/sections/' + section['id']
    rescan = client.post(endpoint + '/rescan', json={'model_id': ''})
    assert rescan.status_code == 202, rescan.get_data(as_text=True)
    candidate = web.JOBS[rescan.get_json()['job_id']]
    changed = deepcopy(source)
    changed['detections'][1]['cbox'] = [40, 10, 60, 25]
    stop_review.atomic_report(Path(candidate['dir']) / 'report.json', changed)
    candidate['phase'] = 'review'
    approved = client.post(endpoint + '/approve', json={'candidate_id': candidate['id']})
    assert approved.status_code == 200, approved.get_data(as_text=True)
    assert job['output'] is None

    monkeypatch.setattr(web, 'JOBS', {})
    web.rehydrate_jobs()
    recovered = web.JOBS['parent']
    assert recovered['output'] is None, 'Restart must not revive the superseded video'
    assert recovered['phase'] == 'review'
    response = client.get('/api/jobs/parent/download')
    assert response.status_code == 409, response.get_data(as_text=True)


def test_tracking_grace_frames_cannot_change_an_adjacent_approved_section(section_job, monkeypatch):
    client, job, _, _ = section_job
    section = create_section(client)
    response = client.post('/api/jobs/parent/sections/' + section['id'] + '/approve', json={})
    assert response.status_code == 200, response.get_data(as_text=True)
    report = Path(job['dir']) / 'report.json'
    locked = video_sections.slice_report(json.loads(report.read_text()), 10, 20)
    # Detector execution is outside this workflow test. The tracker's returned
    # sightings are just before the lock; publication adds hold/grace frames.
    monkeypatch.setattr(web.openscrub, 'PersonDetector',
                        lambda *args, **kwargs: SimpleNamespace(net=None, ort=None))
    monkeypatch.setattr(web.openscrub, 'track_manual_region',
                        lambda *args, **kwargs: [(.8, [10, 10, 30, 25], .9),
                                                (.9, [11, 10, 31, 25], .9)])
    thread_factory = web.threading.Thread
    background = []

    def tracked_thread(*args, **kwargs):
        thread = thread_factory(*args, **kwargs)
        background.append(thread)
        return thread

    monkeypatch.setattr(web.threading, 'Thread', tracked_thread)
    try:
        response = client.post('/api/jobs/parent/track_object',
                               json={'box': [10, 10, 30, 25], 't_ref': .8,
                                     't0': .7, 't1': .9})
        assert response.status_code in (200, 409), response.get_data(as_text=True)
    finally:
        for thread in background:
            thread.join(timeout=5)
    current = video_sections.slice_report(json.loads(report.read_text()), 10, 20)
    assert current['detections'] == locked['detections']
    assert current.get('audio_redactions') == locked.get('audio_redactions')


@pytest.mark.parametrize('payload', [['invalid'], 'invalid', 7])
@pytest.mark.parametrize('action', ['', '/rescan', '/approve'])
def test_section_actions_reject_non_object_payloads(section_job, payload, action):
    client, _, _, queued = section_job
    section = create_section(client)
    endpoint = '/api/jobs/parent/sections'
    if action:
        endpoint += '/' + section['id'] + action
    response = client.post(endpoint, json=payload)
    assert response.status_code == 400
    assert response.is_json
    assert not queued


@pytest.mark.parametrize('candidate_id', [[], {}, 12, True])
def test_approval_rejects_invalid_candidate_ids(section_job, candidate_id):
    client, _, _, _ = section_job
    section = create_section(client)
    response = client.post('/api/jobs/parent/sections/' + section['id'] + '/approve',
                           json={'candidate_id': candidate_id})
    assert response.status_code == 400


def test_rescan_rejects_unscanned_tail_before_queueing_work(section_job):
    client, job, original, queued = section_job
    original['stop_review'] = {'state': 'paused', 'next_frame': 15,
                              'total_frames': 40, 'fps': 10.}
    stop_review.atomic_report(Path(job['dir']) / 'report.json', original)
    job['phase'] = 'paused'
    section = create_section(client)
    response = client.post('/api/jobs/parent/sections/' + section['id'] + '/rescan', json={})
    assert response.status_code == 409
    assert not queued
    assert list(web.JOBS) == ['parent']


@pytest.mark.parametrize('recover_child', [True, False])
def test_retention_keeps_source_for_persisted_section_dependency(section_job, monkeypatch, recover_child):
    import os
    client, job, _, _ = section_job
    child = approved_export(client)
    parent_path = Path(job['dir'])
    child_path = Path(child['dir'])
    # Neither an unreadable parent report nor an unrecovered child lets
    # background retention delete the source of an approved export.
    (parent_path / 'report.json').write_text('{broken')
    monkeypatch.setattr(web, 'JOBS', {child['id']: child} if recover_child else {})
    for folder in (parent_path, child_path):
        os.utime(folder, (1, 1))
    web.retention_sweep(1)
    assert Path(job['video']).is_file()
    assert (child_path / 'section-job.json').is_file()


def test_retention_waits_until_encrypted_dependencies_can_be_read(section_job, monkeypatch):
    import os
    _, job, _, _ = section_job
    monkeypatch.setattr(web, 'JOBS', {})
    monkeypatch.setattr(web, 'vault_locked', lambda: True)
    os.utime(job['dir'], (1, 1))
    web.retention_sweep(1)
    assert Path(job['video']).is_file()


def test_accepted_candidate_invalidates_row_indexed_previews(section_job):
    client, job, source, _ = section_job
    section = create_section(client)
    endpoint = '/api/jobs/parent/sections/' + section['id']
    rescan = client.post(endpoint + '/rescan', json={})
    candidate = web.JOBS[rescan.get_json()['job_id']]
    changed = deepcopy(source)
    changed['detections'] = [dict(source['detections'][1], cbox=[40, 10, 60, 25])]
    stop_review.atomic_report(Path(candidate['dir']) / 'report.json', changed)
    candidate['phase'] = 'review'
    caches = [Path(job['dir']) / 'thumb2_1.jpg', Path(job['dir']) / 'plate_preview_1.npz']
    for path in caches:
        path.write_bytes(b'preview for a superseded report row')
    response = client.post(endpoint + '/approve', json={'candidate_id': candidate['id']})
    assert response.status_code == 200, response.get_data(as_text=True)
    assert all(not path.exists() for path in caches)


def test_late_preview_from_previous_report_cannot_poison_accepted_section(section_job):
    client, job, source, _ = section_job
    source['detections'][1]['category'] = 'face'
    stop_review.atomic_report(Path(job['dir']) / 'report.json', source)
    section = create_section(client)
    endpoint = '/api/jobs/parent/sections/' + section['id']
    rescan = client.post(endpoint + '/rescan', json={})
    candidate = web.JOBS[rescan.get_json()['job_id']]
    changed = deepcopy(source)
    changed['detections'][1]['cbox'] = [40, 10, 60, 25]
    stop_review.atomic_report(Path(candidate['dir']) / 'report.json', changed)
    candidate['phase'] = 'review'
    assert client.post(endpoint + '/approve', json={'candidate_id': candidate['id']}).status_code == 200
    # An old reader/prewarmer may finish after the approval's invalidation.
    accepted = web._load_job_report(job)
    index = next(i for i, row in enumerate(accepted['detections']) if row['category'] == 'face')
    (Path(job['dir']) / ('thumb2_%d.jpg' % index)).write_bytes(b'old crop')
    response = client.get('/api/jobs/parent/thumb/%d?cache_only=1' % index)
    assert response.status_code == 204


def test_approval_waits_for_candidate_tracking(section_job):
    client, _, source, _ = section_job
    section = create_section(client)
    endpoint = '/api/jobs/parent/sections/' + section['id']
    rescan = client.post(endpoint + '/rescan', json={})
    candidate = web.JOBS[rescan.get_json()['job_id']]
    stop_review.atomic_report(Path(candidate['dir']) / 'report.json', source)
    candidate.update(phase='review', trackbg={'state': 'running'})
    response = client.post(endpoint + '/approve', json={'candidate_id': candidate['id']})
    assert response.status_code == 409


def test_approving_unchanged_results_keeps_existing_export(section_job):
    client, job, _, _ = section_job
    output = Path(job['dir']) / 'output.mp4'
    output.write_bytes(b'existing reviewed render')
    job.update(phase='done', output=str(output))
    section = create_section(client)
    response = client.post('/api/jobs/parent/sections/' + section['id'] + '/approve', json={})
    assert response.status_code == 200, response.get_data(as_text=True)
    assert job['phase'] == 'done'
    assert job['output'] == str(output)
    assert not web._load_job_report(job).get('render_required')
