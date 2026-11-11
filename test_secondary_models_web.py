"""Retained trained candidates can check proposals without training again."""
import copy
import hashlib
import io
import json
from pathlib import Path
import shutil

import cv2
import numpy as np
import pytest

import openscrub
import openscrub_web as web
import learned_models
import learning_session
import stop_review
from test_learning_candidates import candidate_job, candidates, CANDIDATE_ID
from test_plate_verifier import brightness_onnx_bytes


def synthetic_video(path):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'mp4v'), 10, (96, 64))
    assert writer.isOpened()
    for frame in range(12):
        writer.write(np.full((64, 96, 3), 0 if frame < 6 else 255, np.uint8))
    writer.release()
    return path


def proposal_report(video):
    rows = []
    for frame, label, enabled in [(2, '', True), (8, '', True),
                                   (3, 'plate', True), (4, 'not_plate', False)]:
        rows.append({'t_start': frame / 10, 't_end': (frame + 1) / 10,
                     'last_seen': frame / 10, 'frame_index': frame,
                     'cbox': [24, 24, 70, 40], 'aoff': [0, 0], 'category': 'plate',
                     'text': 'synthetic proposal', 'confidence': .9,
                     'track': len(rows), 'dense': True, 'enabled': enabled,
                     'verified_label': label})
    return {'provenance': {'input': str(video), 'input_sha256': openscrub.sha256_file(str(video))},
            'render_state': {'fps': 10., 'cum': [[0, 0]] * 12, 'bands': [[0, 0]] * 12},
            'detections': rows}


@pytest.fixture
def checker_job(tmp_path, monkeypatch):
    root = tmp_path / 'application' / 'jobs'
    root.mkdir(parents=True)
    monkeypatch.setattr(web, 'JOBS_DIR', str(root))
    monkeypatch.setattr(web, 'JOBS', {})
    monkeypatch.setattr(web, 'TOKEN', None)
    monkeypatch.setattr(web, 'vault_locked', lambda: False)
    monkeypatch.delenv('OPENSCRUB_TRAIN_WEIGHTS', raising=False)
    monkeypatch.setattr(learning_session, 'preflight',
                        lambda: pytest.fail('Candidate checking must not require training setup'))
    video = synthetic_video(tmp_path / 'unrelated-layout.mp4')
    job = web.new_job(str(video), {'categories': 'plate'}, video.name)
    job['phase'] = 'review'
    original, folder = candidate_job(tmp_path / 'seed')
    # Use a crop-associated box at the runtime aspect ratio as well as the
    # square validation crops. A neighboring/oversized box must not confirm it.
    payload = brightness_onnx_bytes()
    (folder / 'model.onnx').write_bytes(payload)
    manifest = json.loads((folder / 'manifest.json').read_text())
    manifest['artifacts']['model.onnx'] = hashlib.sha256(payload).hexdigest()
    (folder / 'manifest.json').write_text(json.dumps(manifest))
    shutil.copytree(original / 'learning', Path(job['dir']) / 'learning')
    report = Path(job['dir']) / 'report.json'
    report.write_text(json.dumps(proposal_report(video)), encoding='utf-8')
    queued = []
    monkeypatch.setattr(web.WORK_Q, 'put', queued.append)
    return web.app.test_client(), job, report, queued


def queue_check(client, job, mode='review'):
    return client.post('/api/jobs/%s/plate-verifier' % job['id'],
                       json={'candidate_id': CANDIDATE_ID, 'mode': mode})


def run_check(client, job, mode='review'):
    response = queue_check(client, job, mode)
    assert response.status_code == 200, response.get_data(as_text=True)
    assert hasattr(web, 'perform_verification'), 'Candidate checker worker is missing'
    web.perform_verification(job)


def test_retained_candidate_is_visible_without_mask_acceptance(checker_job):
    client, job, path, _ = checker_job
    before = path.read_bytes()
    response = client.get('/api/jobs/%s/detections' % job['id'])
    assert response.status_code == 200
    found = response.get_json().get('learning_candidates')
    assert found and found[0]['id'] == CANDIDATE_ID
    assert found[0]['assessment'] is None
    assert str(Path(job['dir'])) not in json.dumps(found)
    assert path.read_bytes() == before


def test_candidate_filter_uses_real_onnx_and_preserves_human_decisions(checker_job):
    client, job, path, queued = checker_job
    run_check(client, job, 'filter')
    assert queued == [(job['id'], 'verify')]
    assert job['phase'] == 'review' and job['error'] is None, job.get('error')
    doc = json.loads(path.read_text())
    rows = doc['detections']
    assert rows[0]['enabled'] is False
    assert rows[0]['verified_label'] == ''
    assert rows[0]['plate_verification']['applied'] is True
    assert rows[1]['enabled'] is True
    assert rows[2]['enabled'] is True and rows[2]['verified_label'] == 'plate'
    assert rows[3]['enabled'] is False and rows[3]['verified_label'] == 'not_plate'
    assert doc['verification']['mode'] == 'filter'
    assert doc['verification']['assessment']['status'] == 'validated'
    assert doc['verification']['inference']['suppressed'] == 1
    assert doc['render_required'] is True
    assert 'learning' not in doc
    assert not (Path(job['dir']) / 'learning' / 'active.json').exists()


def test_switching_checker_back_to_suggestions_restores_machine_only_suppression(checker_job):
    client, job, path, _ = checker_job
    run_check(client, job, 'filter')
    run_check(client, job, 'review')
    assert job['error'] is None, job.get('error')
    rows = json.loads(path.read_text())['detections']
    assert rows[0]['enabled'] is True
    assert rows[0]['plate_verification']['applied'] is False
    assert rows[3]['enabled'] is False


@pytest.mark.parametrize('payload', [None, [], {'candidate_id': '../outside', 'mode': 'filter'},
                                     {'candidate_id': CANDIDATE_ID, 'mode': 'primary'}])
def test_checker_rejects_invalid_selection_before_queueing(checker_job, payload):
    client, job, path, queued = checker_job
    before = path.read_bytes()
    response = client.post('/api/jobs/%s/plate-verifier' % job['id'], json=payload)
    assert response.status_code == 400
    assert queued == [] and job['phase'] == 'review'
    assert path.read_bytes() == before


def test_checker_cancel_keeps_previous_report(checker_job):
    client, job, path, _ = checker_job
    before = path.read_bytes()
    assert queue_check(client, job).status_code == 200
    job['cancel'].set()
    assert hasattr(web, 'perform_verification')
    web.perform_verification(job)
    assert path.read_bytes() == before
    assert job['phase'] == 'review'


def test_failed_secondary_separation_does_not_filter_or_replace_review(checker_job, tmp_path):
    client, job, path, _ = checker_job
    original, _ = candidate_job(tmp_path / 'inseparable', separable=False)
    shutil.rmtree(Path(job['dir']) / 'learning')
    shutil.copytree(original / 'learning', Path(job['dir']) / 'learning')
    before = path.read_bytes()
    run_check(client, job, 'filter')
    assert path.read_bytes() == before and job['phase'] == 'review'
    assert 'suggest' in job['error'].lower() or 'review' in job['error'].lower()
    run_check(client, job, 'review')
    assert job['error'] is None
    assert json.loads(path.read_text())['verification']['assessment']['status'] == 'review_only'


def test_evaluated_candidate_can_be_saved_transferred_and_pinned_in_filter_mode(checker_job, tmp_path):
    client, job, _, _ = checker_job
    run_check(client, job, 'review')
    response = client.post('/api/jobs/%s/learned-models' % job['id'], json={
        'candidate_id': CANDIDATE_ID, 'name': 'Garage false-positive checker', 'description': 'Synthetic'})
    assert response.status_code == 200, response.get_data(as_text=True)
    saved = response.get_json()['model']
    assert saved['schema'] == 2 and saved['kind'] == 'openscrub-plate-verifier'
    exported = client.get('/api/jobs/learned-models/%s/export' % saved['id'])
    assert exported.status_code == 200
    imported = client.post('/api/jobs/learned-models/import',
        data={'model': (io.BytesIO(exported.data), 'checker.openscrub-model')},
        content_type='multipart/form-data')
    assert imported.status_code == 200
    new_job = web.new_job(job['video'], {'categories': 'plate', 'learned_plate_model': saved['id'],
                                        'learned_plate_model_mode': 'filter'}, 'Another clip')
    assert learned_models.load_selection(new_job['dir']) == 'filter'
    learned_models.delete_model(web.learned_models_root(), saved['id'])
    doc = web.apply_selected_plate_model(new_job, proposal_report(Path(job['video'])))
    assert doc['detections'][0]['enabled'] is False
    assert doc['verification']['mode'] == 'filter'
    # Restart before a report exists must retain mode as well as model ID.
    uploaded = Path(new_job['dir']) / 'input.mp4'
    uploaded.write_bytes(Path(job['video']).read_bytes())
    web.JOBS.clear()
    web.rehydrate_jobs()
    recovered = web.JOBS[new_job['id']]
    assert recovered['options']['learned_plate_model_mode'] == 'filter'
    assert web.build_args(recovered).plate_learning_exact is True


def test_human_same_value_keep_is_persisted_without_creating_negative_label(checker_job):
    client, job, path, _ = checker_job
    doc = json.loads(path.read_text())
    row = doc['detections'][0]
    row.update(enabled=False, plate_verification={'applied': True, 'previous_enabled': True,
                                                  'decision': 'suppress'})
    path.write_text(json.dumps(doc))
    response = client.post('/api/jobs/%s/detections' % job['id'],
                           json={'enabled': {'0': False}, 'verified_labels': {'0': 'clear'}})
    assert response.status_code == 200 and response.get_json()['changed'] is True
    stored = json.loads(path.read_text())['detections'][0]
    assert stored['enabled'] is False and stored['verified_label'] == ''
    assert stored.get('plate_verification_override') is True
    assert 'plate_verification' not in stored


def test_legacy_unchanged_full_choice_save_does_not_promote_machine_decisions(checker_job):
    client, job, path, _ = checker_job
    doc = json.loads(path.read_text())
    doc['detections'][0].update(enabled=False, plate_verification={
        'applied': True, 'previous_enabled': True, 'decision': 'suppress'})
    path.write_text(json.dumps(doc))
    response = client.post('/api/jobs/%s/detections' % job['id'],
                           json={'enabled': {str(i): row['enabled'] for i, row in enumerate(doc['detections'])}})
    assert response.status_code == 200
    row = json.loads(path.read_text())['detections'][0]
    assert row['plate_verification']['applied'] is True
    assert not row.get('plate_verification_override')


def test_render_preserves_secondary_model_audit(checker_job):
    _, _, path, _ = checker_job
    before = json.loads(path.read_text())
    before['verification'] = {'mode': 'review', 'model_sha256': 'b' * 64, 'inference': {'suggested': 1}}
    rendered = copy.deepcopy(before)
    rendered.pop('verification')
    assert learning_session.preserve_render_review(before, rendered).get('verification') == before['verification']


def test_checker_api_obeys_vault_lock(checker_job, monkeypatch):
    client, job, _, queued = checker_job
    monkeypatch.setattr(web, 'vault_locked', lambda: True)
    assert queue_check(client, job).status_code == 423
    assert queued == []


def saved_checker(client, job):
    run_check(client, job, 'review')
    response = client.post('/api/jobs/%s/learned-models' % job['id'], json={
        'candidate_id': CANDIDATE_ID, 'name': 'Secondary checker'})
    assert response.status_code == 200
    return response.get_json()['model']


@pytest.mark.parametrize('damage', ['missing', 'null'])
def test_corrupt_saved_filter_mode_survives_recovery_as_a_visible_error(checker_job, damage):
    client, training, _, _ = checker_job
    saved = saved_checker(client, training)
    job = web.new_job(training['video'], {'categories': 'plate', 'learned_plate_model': saved['id'],
                                         'learned_plate_model_mode': 'filter'}, 'Pinned filter')
    result = web.apply_selected_plate_model(job, proposal_report(Path(job['video'])))
    path = Path(job['dir']) / 'report.json'
    path.write_text(json.dumps(result))
    selection = Path(job['dir']) / 'plate_model_selection.json'
    if damage == 'missing':
        selection.unlink()
    else:
        value = json.loads(selection.read_text())
        value['mode'] = None
        selection.write_text(json.dumps(value))
    web.JOBS.clear()
    web.rehydrate_jobs()
    recovered = web.JOBS[job['id']]
    assert recovered['phase'] == 'error' and 'selection' in recovered['error']
    assert recovered['options']['learned_plate_model']
    with pytest.raises(learned_models.ModelError):
        web.build_args(recovered)
    assert json.loads(path.read_text()) == result


def test_resume_recovers_pinned_mode_after_checkpoint_options_replace_runtime(checker_job):
    client, training, _, queued = checker_job
    saved = saved_checker(client, training)
    job = web.new_job(training['video'], {'categories': 'plate', 'learned_plate_model': saved['id'],
                                         'learned_plate_model_mode': 'filter'}, 'Pinned filter')
    doc = proposal_report(Path(job['video']))
    doc['render_state']['cum'] = doc['render_state']['cum'][:6]
    doc['render_state']['bands'] = doc['render_state']['bands'][:6]
    doc['detections'] = [row for row in doc['detections'] if row['frame_index'] < 6]
    doc = stop_review.with_checkpoint(doc, 6, 12, {'categories': 'plate'})
    (Path(job['dir']) / 'report.json').write_text(json.dumps(doc))
    job['phase'] = 'paused'
    response = client.post('/api/jobs/%s/resume' % job['id'])
    assert response.status_code == 200, response.get_data(as_text=True)
    assert job['options']['learned_plate_model'] == saved['id']
    assert job['options']['learned_plate_model_mode'] == 'filter'
    assert queued[-1] == (job['id'], 'resume')


@pytest.mark.parametrize('failure', ['source', 'publish'])
def test_checker_failure_keeps_review_and_prior_output(checker_job, monkeypatch, failure):
    client, job, path, _ = checker_job
    output = Path(job['dir']) / 'output.mp4'
    output.write_bytes(b'existing output')
    job.update(output=str(output), phase='done')
    before = path.read_bytes()
    if failure == 'source':
        doc = json.loads(before)
        doc['provenance']['input_sha256'] = '0' * 64
        path.write_text(json.dumps(doc))
        before = path.read_bytes()
    else:
        def fail(*args, **kwargs):
            raise OSError('Simulated disk error')
        monkeypatch.setattr(stop_review, 'atomic_report', fail)
    run_check(client, job, 'filter')
    assert job['phase'] == 'done' and job['error']
    assert job['output'] == str(output) and output.read_bytes() == b'existing output'
    assert path.read_bytes() == before


def test_paused_candidate_check_stays_within_scanned_frames(checker_job):
    client, job, path, _ = checker_job
    doc = json.loads(path.read_text())
    doc['render_state']['cum'] = doc['render_state']['cum'][:6]
    doc['render_state']['bands'] = doc['render_state']['bands'][:6]
    doc['detections'] = [row for row in doc['detections'] if row['frame_index'] < 6]
    doc = stop_review.with_checkpoint(doc, 6, 12, job['options'])
    path.write_text(json.dumps(doc))
    job['phase'] = 'paused'
    run_check(client, job, 'filter')
    result = json.loads(path.read_text())
    assert job['phase'] == 'paused' and job['error'] is None
    assert result['stop_review'] == doc['stop_review']
    assert result['verification']['inference']['decoded_frames'] == 6
    assert result['detections'][0]['enabled'] is False


@pytest.mark.parametrize('edit', [
    {'enabled': {'0': True}},
    {'verified_labels': {'0': 'plate'}},
    {'box_overrides': {'0': [23, 24, 70, 40]}},
    {'time_overrides': {'0': [.2, .4]}},
])
def test_human_positive_or_geometry_edit_restores_machine_suppression(checker_job, edit):
    client, job, path, _ = checker_job
    run_check(client, job, 'filter')
    response = client.post('/api/jobs/%s/detections' % job['id'], json=edit)
    assert response.status_code == 200 and response.get_json()['changed']
    row = json.loads(path.read_text())['detections'][0]
    assert row['enabled'] is True and row['plate_verification_override'] is True
    assert 'plate_verification' not in row
    run_check(client, job, 'filter')
    row = json.loads(path.read_text())['detections'][0]
    assert row['enabled'] is True and 'plate_verification' not in row
