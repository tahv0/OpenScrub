"""Confirmed examples are explicit, durable and reviewed from compact pixels."""
import hashlib
import json
import time
from pathlib import Path

import cv2
import numpy as np
import pytest

import openscrub_web as web
from test_secondary_models_web import synthetic_video, proposal_report


@pytest.fixture
def findings_job(tmp_path, monkeypatch):
    root = tmp_path / 'data'
    root.mkdir()
    monkeypatch.setattr(web, 'JOBS_DIR', str(root))
    monkeypatch.setattr(web, 'JOBS', {})
    monkeypatch.setattr(web, 'TOKEN', None)
    monkeypatch.setattr(web, 'vault_locked', lambda: False)
    video = synthetic_video(tmp_path / 'camera.mp4')
    job = web.new_job(str(video), {'categories': 'plate'}, video.name)
    job['phase'] = 'review'
    doc = proposal_report(video)
    doc['source_identity'] = dict(input_sha256=doc['provenance']['input_sha256'],
                                  fps=10, total_frames=12, width=96, height=64)
    for row in doc['detections']:
        row['verified_label'] = ''
        row['enabled'] = True
    path = Path(job['dir']) / 'report.json'
    path.write_text(json.dumps(doc))
    return web.app.test_client(), job, video, path


def test_archive_starts_empty_and_output_choices_do_not_create_examples(findings_job):
    client, job, _, _ = findings_job
    response = client.get('/api/findings')
    assert response.status_code == 200
    assert response.get_json()['total'] == 0
    saved = client.post(f'/api/jobs/{job["id"]}/detections',
                        json={'enabled': {'0': False}, 'verified_labels': {'0': 'clear'}})
    assert saved.status_code == 200
    assert client.get('/api/findings').get_json()['total'] == 0


def test_explicit_confirmation_uses_cached_pixels_and_survives_job_and_source_removal(findings_job, monkeypatch):
    client, job, video, _ = findings_job
    preview = client.get(f'/api/jobs/{job["id"]}/finding-preview/0')
    assert preview.status_code == 200
    pixels = cv2.imdecode(np.frombuffer(preview.data, np.uint8), cv2.IMREAD_COLOR)
    assert pixels is not None and max(pixels.shape[:2]) <= 640
    monkeypatch.setattr(web, '_frame_at', lambda *a, **k: pytest.fail('Cached confirmation must not reopen video'))
    saved = client.post(f'/api/jobs/{job["id"]}/confirm/0', json={'label': 'negative'})
    assert saved.status_code == 200, saved.get_data(as_text=True)
    entry = saved.get_json()['finding']
    assert entry['label'] == 'negative'
    assert entry['video_id'] == hashlib.sha256(video.read_bytes()).hexdigest()
    assert client.delete(f'/api/jobs/{job["id"]}').status_code == 200
    video.unlink()
    listed = client.get('/api/findings').get_json()
    assert listed['total'] == 1
    assert client.get(f'/api/findings/{entry["id"]}/image').status_code == 200
    assert str(video.parent) not in json.dumps(listed)


@pytest.mark.parametrize('label', ['', 'blur', 'keep', 'maybe', True, None])
def test_archive_requires_an_explicit_classification(findings_job, label):
    client, job, _, path = findings_job
    before = path.read_bytes()
    response = client.post(f'/api/jobs/{job["id"]}/confirm/0', json={'label': label})
    assert response.status_code == 400
    assert path.read_bytes() == before
    assert client.get('/api/findings').get_json()['total'] == 0


def test_corner_draft_is_not_a_positive_training_label(findings_job):
    client, job, _, path = findings_job
    response = client.get(f'/api/jobs/{job["id"]}/finding-preview/0')
    assert response.status_code == 200
    meta = json.loads(response.headers['X-Finding-Geometry'])
    points = [[26, 25], [68, 25], [68, 39], [26, 39]]
    saved = client.post(f'/api/jobs/{job["id"]}/finding-region/0',
                        json={'points': points, 'preview_token': meta['preview_token']})
    assert saved.status_code == 200, saved.get_data(as_text=True)
    row = web._load_job_report(job)['detections'][0]
    assert row.get('plate_quad')
    assert not row.get('verified_label')
    assert client.get('/api/findings').get_json()['total'] == 0


def test_confirmed_image_can_be_relabelled_and_edited_without_source(findings_job, monkeypatch):
    client, job, video, _ = findings_job
    saved = client.post(f'/api/jobs/{job["id"]}/confirm/0', json={'label': 'positive'})
    assert saved.status_code == 200
    entry = saved.get_json()['finding']
    video.unlink()
    monkeypatch.setattr(web, '_frame_at', lambda *a, **k: pytest.fail('Library editor must use stored pixels'))
    changed = client.post(f'/api/findings/{entry["id"]}', json={
        'label': 'negative', 'expected_revision': entry['revision']})
    assert changed.status_code == 200
    revised = changed.get_json()['finding']
    assert revised['revision'] > entry['revision'] and revised['label'] == 'negative'
    stale = client.post(f'/api/findings/{entry["id"]}', json={
        'label': 'positive', 'expected_revision': entry['revision']})
    assert stale.status_code == 409


def test_confirmed_examples_are_excluded_from_job_retention(findings_job):
    client, job, _, _ = findings_job
    saved = client.post(f'/api/jobs/{job["id"]}/confirm/0', json={'label': 'negative'})
    assert saved.status_code == 200
    web.retention_sweep(-1)
    assert client.get('/api/findings').get_json()['total'] == 1


def test_live_review_queue_does_not_create_training_examples(findings_job):
    import openscrub
    client, job, _, _ = findings_job
    job['phase'] = 'scanning'
    callbacks = web.WebCallbacks(job)
    frame = np.full((64, 96, 3), 130, np.uint8)
    detection = openscrub.Detection(.2, .3, (24, 24, 70, 40), 'plate', 'plate', .3,
                                    (0, 0), track=42, dense=True, frame_index=2)
    assert hasattr(callbacks, 'scan_findings')
    callbacks.scan_findings(frame, 2, 10, [detection])
    response = client.get(f'/api/jobs/{job["id"]}/review-queue')
    assert response.status_code == 200
    assert response.get_json()['total'] >= 1
    assert client.get('/api/findings').get_json()['total'] == 0
    assert job['phase'] == 'scanning'


def test_compact_cache_probe_never_decodes(findings_job, monkeypatch):
    client, job, _, _ = findings_job
    monkeypatch.setattr(web, '_frame_at', lambda *a, **k: pytest.fail('Cache probes cannot decode video'))
    response = client.get(f'/api/jobs/{job["id"]}/finding-preview/0?cache_only=1')
    assert response.status_code == 204


def test_compact_autosave_retry_returns_receipt_without_confirming_label(findings_job):
    client, job, _, path = findings_job
    meta = json.loads(client.get(f'/api/jobs/{job["id"]}/finding-preview/0').headers['X-Finding-Geometry'])
    payload = dict(compact=True, autosave=True, edit_id='crop-edit-1',
                   points=[[26,25],[68,25],[68,39],[26,39]], preview_token=meta['preview_token'])
    url = f'/api/jobs/{job["id"]}/plate_quad/0'
    first = client.post(url, json=payload)
    assert first.status_code == 200
    saved = path.read_bytes()
    retry = client.post(url, json=payload)
    assert retry.status_code == 200, retry.get_data(as_text=True)
    assert path.read_bytes() == saved
    assert retry.get_json()['classification_required']
    assert client.get('/api/findings').get_json()['total'] == 0
    payload['points'][0][0] += 1
    assert client.post(url, json=payload).status_code == 409



@pytest.mark.parametrize('unapproved_sections', [False, True])
def test_unsectioned_corner_autosave_does_not_deepcopy_huge_report(
        findings_job, monkeypatch, unapproved_sections):
    client, job, _, path = findings_job
    if unapproved_sections:
        doc=json.loads(path.read_text())
        doc['video_sections']={'schema':1,'items':[],'revision':1}
        path.write_text(json.dumps(doc))
    image = client.get(f'/api/jobs/{job["id"]}/finding-preview/0')
    assert image.status_code == 200
    meta = json.loads(image.headers['X-Finding-Geometry'])
    points = [list(p) for p in meta['points']]
    points[0][0] += 1
    monkeypatch.setattr(web.findings_web, 'deepcopy',
                        lambda *_: pytest.fail('Per-corner save deep-copied the entire report'))
    result = client.post(f'/api/jobs/{job["id"]}/plate_quad/0', json=dict(
        compact=True, points=points, preview_token=meta['preview_token'],
        autosave=True, edit_id='efficient-corner-save'))
    assert result.status_code == 200, result.get_data(as_text=True)
    assert web._load_job_report(job)['detections'][0]['human_region_confirmed']

def test_confirm_retry_recovers_archive_after_report_failure(findings_job, monkeypatch):
    client, job, _, path = findings_job
    url = f'/api/jobs/{job["id"]}/confirm/0'
    assert client.post(url, json={'label':'positive'}).status_code == 200
    original = web.findings_web.review_journal.write
    def fail(*args, **kwargs):
        raise OSError('Injected report publication failure')
    monkeypatch.setattr(web.findings_web.review_journal, 'write', fail)
    # Flask may propagate exceptions under the test environment.
    try:
        response = client.post(url, json={'label':'negative'})
        assert response.status_code == 500
    except OSError:
        pass
    monkeypatch.setattr(web.findings_web.review_journal, 'write', original)
    retry = client.post(url, json={'label':'negative'})
    assert retry.status_code == 200, retry.get_data(as_text=True)
    assert web._load_job_report(job)['detections'][0]['verified_label'] == 'not_plate'
    assert client.get('/api/findings').get_json()['items'][0]['label'] == 'negative'


def test_named_training_requires_explicit_selection(findings_job, monkeypatch):
    client, job, _, _ = findings_job
    assert client.post(f'/api/jobs/{job["id"]}/confirm/0', json={'label':'positive'}).status_code == 200
    response = client.post('/api/findings/train', json={'license_accepted':True})
    assert response.status_code == 400
    assert 'select' in response.get_json()['error'].lower()


def test_legacy_learning_accepts_local_parent_without_base_and_preserves_name(findings_job,monkeypatch):
    client,job,_,path=findings_job
    doc=json.loads(path.read_text());doc['learning']={'active':{'model_id':'local-parent'}}
    path.write_text(json.dumps(doc))
    monkeypatch.delenv('OPENSCRUB_TRAIN_WEIGHTS',raising=False)
    monkeypatch.setattr(web.findings_web.training,'training_info',lambda *args:{'trainable':True})
    queued=[];monkeypatch.setattr(web.WORK_Q,'put',queued.append)
    response=client.post(f'/api/jobs/{job["id"]}/learning',json={'license_accepted':True,'name':'Garage revision two'})
    assert response.status_code==200,response.get_data(as_text=True)
    assert job['learning_request']['name']=='Garage revision two'
    assert queued==[(job['id'],'learn')]


def test_legacy_worker_preflights_resolved_parent(findings_job,monkeypatch):
    _,job,_,_=findings_job
    monkeypatch.setattr(web.findings_web.training,'session_parent',lambda *args:{'weights':'retained-parent.pt'})
    calls=[]
    def ready(**kwargs):
        calls.append(kwargs);return {'ready':True,'problems':[]}
    monkeypatch.setattr(web.learning_session,'preflight',ready)
    def retained(*args,**kwargs):
        raise web.learning_session.CoverageRejected('Candidate kept')
    monkeypatch.setattr(web.learning_session,'run_session',retained)
    web.perform_learning(job)
    assert calls==[{'weights':'retained-parent.pt'}]
    assert job['phase']=='review' and job['learning']['stage']=='candidate_ready'


def test_keep_visible_on_model_filtered_row_preserves_requested_output(findings_job):
    client,job,_,path=findings_job
    doc=json.loads(path.read_text())
    doc['detections'][0].update(enabled=False,plate_verification={'applied':True,'previous_enabled':True})
    path.write_text(json.dumps(doc))
    response=client.post(f'/api/jobs/{job["id"]}/detections',json={'enabled':{'0':False},'output_choices':{'0':True}})
    assert response.status_code==200
    row=json.loads(path.read_text())['detections'][0]
    assert row['enabled'] is False and row['output_choice_explicit'] is True
    assert not row.get('plate_verification')
    assert client.get('/api/findings').get_json()['total']==0


def test_cold_preview_rejects_changed_source_before_decoding(findings_job,monkeypatch):
    client,job,video,_=findings_job
    video.write_bytes(video.read_bytes()+b'changed source bytes')
    monkeypatch.setattr(web,'_frame_at',lambda *a,**k:pytest.fail('Changed source was decoded'))
    response=client.get(f'/api/jobs/{job["id"]}/finding-preview/0')
    assert response.status_code==409
    assert client.get('/api/findings').get_json()['total']==0


@pytest.mark.parametrize('forget',[False,True])
def test_stale_confirmation_returns_current_revision_for_explicit_retry(findings_job,forget):
    client,job,_,_=findings_job
    url=f'/api/jobs/{job["id"]}/confirm/0'
    entry=client.post(url,json={'label':'positive'}).get_json()['finding']
    library=f'/api/findings/{entry["id"]}'
    if forget:client.delete(library,json={'expected_revision':1})
    else:client.post(library,json={'expected_revision':1,'label':'negative'})
    stale=client.post(url,json={'label':'positive','expected_revision':1})
    assert stale.status_code==409
    current=stale.get_json()['current_archive']
    assert current['revision']==2 and current['revoked']==forget
    assert client.post(url,json={'label':'positive','expected_revision':current['revision']}).status_code==200


@pytest.mark.parametrize('resource', ['list', 'image'])
def test_vault_lock_refuses_saved_findings_even_if_plaintext_remains(findings_job, monkeypatch, resource):
    client, job, _, _ = findings_job
    entry = client.post(f'/api/jobs/{job["id"]}/confirm/0', json={'label': 'positive'}).get_json()['finding']
    url = '/api/findings' if resource == 'list' else f'/api/findings/{entry["id"]}/image'
    monkeypatch.setattr(web, 'vault_locked', lambda: True)
    assert client.get(url).status_code == 423


def test_locked_findings_request_does_not_recreate_encrypted_database(findings_job, monkeypatch):
    client, job, _, _ = findings_job
    assert client.post(f'/api/jobs/{job["id"]}/confirm/0', json={'label': 'positive'}).status_code == 200
    monkeypatch.setitem(web.VAULT, 'key', b'v' * 32)
    monkeypatch.setattr(web, 'vault_locked', lambda: web.VAULT['key'] is None)
    assert web._vault_lock_now() > 0
    database = Path(web.JOBS_DIR) / 'confirmed_findings' / 'findings.sqlite3'
    assert not database.exists()
    assert client.get('/api/findings').status_code == 423
    assert not database.exists(), 'A read while locked must not create a new plaintext archive'


@pytest.mark.parametrize('resource', ['list', 'image', 'queue', 'queue_image', 'preview'])
def test_findings_reads_refuse_io_while_vault_exclusive_gate_is_held(findings_job, monkeypatch, resource):
    client, job, _, path = findings_job
    entry = client.post(f'/api/jobs/{job["id"]}/confirm/0', json={'label': 'positive'}).get_json()['finding']
    key = client.get(f'/api/jobs/{job["id"]}/review-queue').get_json()['items'][0]['key']
    urls = dict(list='/api/findings', image=f'/api/findings/{entry["id"]}/image',
                queue=f'/api/jobs/{job["id"]}/review-queue',
                queue_image=f'/api/jobs/{job["id"]}/review-queue/{key}/image',
                preview=f'/api/jobs/{job["id"]}/finding-preview/0?cache_only=1')
    # Pause after the report read so this checks the compact SQLite read itself.
    doc = json.loads(path.read_text())
    monkeypatch.setattr(web, '_load_preview_report', lambda job: doc)
    # Only actual vault encryption should delay concurrent picture reads.
    with web._REVIEW_PICTURE_GATE.writer():
        assert client.get(urls[resource]).status_code == 503


def test_concurrent_saved_images_do_not_wait_for_another_slow_reader(findings_job, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor, TimeoutError
    import threading
    client, job, _, _ = findings_job
    entry = client.post(f'/api/jobs/{job["id"]}/confirm/0', json={'label': 'positive'}).get_json()['finding']
    url = f'/api/findings/{entry["id"]}/image'
    entered, release = threading.Event(), threading.Event()
    original = web.findings_web.library.image_path
    def paused_image(*args):
        if not entered.is_set():
            entered.set()
            assert release.wait(3)
        return original(*args)
    monkeypatch.setattr(web.findings_web.library, 'image_path', paused_image)
    def request_image():
        with web.app.test_client() as reader:
            return reader.get(url).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(request_image)
        assert entered.wait(3)
        second = pool.submit(request_image)
        try:
            assert second.result(timeout=2) == 200, (
                'A cached JPEG must not wait behind an unrelated slow reader')
        finally:
            release.set()
        assert first.result(timeout=3) == 200



def test_saved_picture_reader_blocks_vault_encryption_until_complete(findings_job, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor, TimeoutError
    import threading
    client, job, _, _ = findings_job
    entry = client.post(f'/api/jobs/{job["id"]}/confirm/0',
                        json={'label': 'positive'}).get_json()['finding']
    entered, release = threading.Event(), threading.Event()
    original = web.findings_web.library.image_path
    def blocked_image(*args):
        entered.set()
        assert release.wait(3)
        return original(*args)
    monkeypatch.setattr(web.findings_web.library, 'image_path', blocked_image)
    monkeypatch.setitem(web.VAULT, 'key', b'fake-test-key')
    encrypted = []
    def encrypt(*args):
        encrypted.append(True)
        return 0
    monkeypatch.setattr(web.vault, 'encrypt_tree', encrypt)
    def read():
        with web.app.test_client() as reader:
            return reader.get(f'/api/findings/{entry["id"]}/image').status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        reading = pool.submit(read)
        assert entered.wait(2)
        locking = pool.submit(web._vault_lock_now)
        try:
            with pytest.raises(TimeoutError):
                locking.result(timeout=.1)
            assert not encrypted, 'Vault encrypted plaintext while a reader was open'
        finally:
            release.set()
        assert reading.result(timeout=3) == 200
        assert locking.result(timeout=3) == 0
        assert encrypted and web.VAULT['key'] is None

def test_exact_warm_preview_can_confirm_after_source_removal(findings_job, monkeypatch):
    client, job, video, _ = findings_job
    url = f'/api/jobs/{job["id"]}/finding-preview/0'
    assert client.get(url).status_code == 200
    video.unlink()
    monkeypatch.setattr(web, '_frame_at', lambda *a, **k: pytest.fail('Warm preview reopened the source'))
    response = client.post(f'/api/jobs/{job["id"]}/confirm/0', json={'label': 'positive'})
    assert response.status_code == 200
    assert response.get_json()['finding']['frame'] == 2


@pytest.fixture
def legacy_vfr_job(findings_job):
    import subprocess
    client, job, original, path = findings_job
    video = original.with_name('legacy-vfr.mp4')
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(original),
                    '-vf', r"select='not(mod(n\,3))'", '-fps_mode', 'vfr', str(video)], check=True)
    job['video'] = str(video)
    fingerprint = hashlib.sha256(video.read_bytes()).hexdigest()
    doc = json.loads(path.read_text())
    doc['provenance'].update(input=str(video), input_sha256=fingerprint)
    doc['render_state'] = dict(fps=4., cum=[[0, 0]] * 4, bands=[[0, 0]] * 4)
    doc['source_identity'].update(input_sha256=fingerprint, fps=4., total_frames=4)
    doc['detections'] = [dict(doc['detections'][0], frame_index=-1, t_start=.1, t_end=.7, last_seen=.2)]
    path.write_text(json.dumps(doc))
    return client, job, video, path


def test_legacy_vfr_timestamp_preview_is_available_without_claiming_exact_geometry(legacy_vfr_job):
    client, job, video, _ = legacy_vfr_job
    response = client.get(f'/api/jobs/{job["id"]}/finding-preview/0')
    assert response.status_code == 200, response.get_data(as_text=True)
    meta = json.loads(response.headers['X-Finding-Geometry'])
    assert meta['exact_frame'] is False and meta['frame_index'] == -1
    assert meta['classification_allowed'] is False and 'rescan' in meta['classification_note'].lower()
    assert meta['t'] == .2
    assert meta['source']['sha256'] == hashlib.sha256(video.read_bytes()).hexdigest()
    assert cv2.imdecode(np.frombuffer(response.data, np.uint8), cv2.IMREAD_COLOR) is not None


def test_legacy_vfr_last_timestamp_stays_inside_its_available_timeline(legacy_vfr_job):
    client, job, _, path = legacy_vfr_job
    doc = json.loads(path.read_text())
    doc['detections'][0].update(t_start=.7, t_end=1., last_seen=.9)
    path.write_text(json.dumps(doc))
    response = client.get(f'/api/jobs/{job["id"]}/finding-preview/0')
    assert response.status_code == 200, response.get_data(as_text=True)
    meta = json.loads(response.headers['X-Finding-Geometry'])
    assert meta['t'] == .9 and meta['classification_allowed'] is False
    assert meta['frame'] == 3 and meta['frame_index'] == -1


def test_legacy_vfr_cached_picture_supports_offline_drafts_but_not_training(legacy_vfr_job, monkeypatch):
    client, job, video, path = legacy_vfr_job
    url = f'/api/jobs/{job["id"]}/finding-preview/0'
    first = client.get(url)
    assert first.status_code == 200
    video.unlink()
    monkeypatch.setattr(web, '_frame_at', lambda *a, **k: pytest.fail('Warm legacy preview reopened the source'))
    second = client.get(url)
    assert second.status_code == 200 and second.data == first.data
    meta = json.loads(second.headers['X-Finding-Geometry'])
    assert meta['classification_allowed'] is False
    before = path.read_bytes()
    rejected = client.post(f'/api/jobs/{job["id"]}/confirm/0', json={'label': 'positive'})
    assert rejected.status_code == 409 and 'rescan' in rejected.get_json()['error'].lower()
    assert path.read_bytes() == before
    drafted = client.post(f'/api/jobs/{job["id"]}/finding-region/0', json={
        'points': [[26, 25], [68, 25], [68, 39], [26, 39]], 'preview_token': meta['preview_token']})
    assert drafted.status_code == 200, drafted.get_data(as_text=True)
    row = web._load_job_report(job)['detections'][0]
    assert row['plate_quad'] and not row.get('verified_label') and not row.get('confirmed_finding_id')
    assert client.get('/api/findings').get_json()['total'] == 0


def test_indexed_vfr_preview_does_not_fall_back_to_approximate_time(legacy_vfr_job):
    client, job, _, path = legacy_vfr_job
    doc = json.loads(path.read_text())
    doc['detections'][0]['frame_index'] = 1
    path.write_text(json.dumps(doc))
    assert client.get(f'/api/jobs/{job["id"]}/finding-preview/0').status_code == 422


@pytest.mark.parametrize('field', ['fps', 'width'])
def test_cold_preview_refuses_report_timeline_that_differs_from_verified_video(findings_job, field):
    client, job, _, path = findings_job
    doc = json.loads(path.read_text())
    if field == 'fps':
        doc['render_state']['fps'] = 20.
    else:
        doc['source_identity']['width'] = 192
    path.write_text(json.dumps(doc))
    response = client.get(f'/api/jobs/{job["id"]}/finding-preview/0')
    assert response.status_code == 409
    assert client.get('/api/findings').get_json()['total'] == 0


def test_unlinked_archive_after_report_failure_requires_explicit_different_retry(findings_job, monkeypatch):
    client, job, _, path = findings_job
    url = f'/api/jobs/{job["id"]}/confirm/0'
    before = path.read_bytes()
    def fail(*args, **kwargs):
        raise OSError('Injected initial report publication failure')
    with monkeypatch.context() as failure:
        failure.setattr(web.findings_web.review_journal, 'write', fail)
        try:
            assert client.post(url, json={'label': 'positive'}).status_code == 500
        except OSError:
            pass
    assert path.read_bytes() == before
    original = client.get('/api/findings').get_json()['items'][0]
    conflict = client.post(url, json={'label': 'negative'})
    assert conflict.status_code == 409
    assert conflict.get_json()['current_archive'] == dict(
        id=original['id'], revision=1, revoked=False, label='positive')
    assert client.get('/api/findings').get_json()['items'][0]['label'] == 'positive'
    retry = client.post(url, json={'label': 'negative', 'expected_revision': 1})
    assert retry.status_code == 200
    assert retry.get_json()['finding']['revision'] == 2
    row = web._load_job_report(job)['detections'][0]
    assert row['confirmed_finding_id'] == original['id'] and row['verified_label'] == 'not_plate'


def test_final_track_uses_cached_scan_representative_without_video_decode(findings_job, monkeypatch):
    client, job, video, path = findings_job
    doc = json.loads(path.read_text())
    base = dict(doc['detections'][0])
    # The scan cached the real detector hit at frame 2 before final tracking.
    cap = cv2.VideoCapture(str(video))
    cap.set(cv2.CAP_PROP_POS_FRAMES, 2)
    ok, pixels = cap.read()
    cap.release()
    assert ok
    raw = dict(base, frame_index=2, t_start=.2, t_end=.2, last_seen=.2, track=-1)
    assert web.finding_previews.capture(job['dir'], pixels, 2, 10., [raw])['added'] == 1

    # Post-processing inserted an earlier synthetic continuity row and assigned
    # both rows to the same final track. Review chooses the earlier row.
    synthetic = dict(base, frame_index=1, t_start=.1, t_end=.1, last_seen=.1,
                     track=9, fallback_reason='interpolated_sample')
    real = dict(base, frame_index=2, t_start=.2, t_end=.2, last_seen=.2, track=9)
    doc['detections'] = [synthetic, real]
    path.write_text(json.dumps(doc))

    monkeypatch.setattr(web, '_frame_at',
        lambda *a, **k: pytest.fail('reconciled cached preview reopened source video'))
    # Legacy track relinking must occur without blocking the detections GET.
    # While it runs, cache-only previews may briefly return 204. They must
    # eventually find the same verified real scan frame, without video decode.
    started = time.monotonic()
    assert client.get(f'/api/jobs/{job["id"]}/detections').status_code == 200
    assert time.monotonic() - started < 2.0
    deadline = time.monotonic() + 5.0
    while True:
        preview = client.get(f'/api/jobs/{job["id"]}/finding-preview/0?cache_only=1')
        if preview.status_code == 200 or time.monotonic() >= deadline:
            break
        assert preview.status_code in (204, 503), preview.get_data(as_text=True)
        time.sleep(0.05)
    assert preview.status_code == 200, preview.get_data(as_text=True)
    meta = json.loads(preview.headers['X-Finding-Geometry'])
    assert meta['match'] == 'representative'
    assert meta['requested_frame'] == 1 and meta['frame'] == 2

    saved = client.post(f'/api/jobs/{job["id"]}/confirm/0', json={'label':'positive'})
    assert saved.status_code == 200, saved.get_data(as_text=True)
    entry = saved.get_json()['finding']
    assert entry['frame'] == 2
    stored = web._load_job_report(job)['detections']
    assert all(r['verified_label'] == 'plate' for r in stored)
