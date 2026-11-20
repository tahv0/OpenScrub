"""Actual web ownership around an opt-in native checkpoint producer."""

from contextlib import contextmanager
import json
import os
import shutil
import stat
import threading

import pytest

import openscrub_web as web
from openscrub_internal import checkpoint_media, checkpoint_runtime
from test_checkpoint_web_owner import checkpoint_job
from test_checkpoint_runtime import movie
from test_job_lifecycle import store
from test_report_transactions import join, run_worker, socket_api


@pytest.fixture
def checkpoint_web(store):
    video = movie(store.path.parent)
    store.path.unlink()
    output = store.path.parent / 'output.mp4'
    output.write_bytes(b'older output must remain intact')
    store.job.update(video=str(video), phase='error', output=str(output),
                     options={'checkpoint_review': True, 'categories': 'qrcode',
                              'use_zones': False})
    (store.path.parent / web.OPTIONS_FILE).write_text(json.dumps(store.job['options']))
    return store, output


def hold_after_frames(monkeypatch, count=7):
    entered, release = threading.Event(), threading.Event()
    actual = checkpoint_media.FrameStream.read
    held = [False]
    def read(stream):
        value = actual(stream)
        if value is not None and stream.next_frame == count and not held[0]:
            held[0] = True
            entered.set()
            assert release.wait(12)
        return value
    monkeypatch.setattr(checkpoint_media.FrameStream, 'read', read)
    return entered, release


@pytest.fixture
def paused_web(checkpoint_web, socket_api, monkeypatch):
    store, output = checkpoint_web
    entered, release = hold_after_frames(monkeypatch)
    web.enqueue(store.job, 'scan')
    worker = run_worker()
    try:
        assert entered.wait(12), store.job.get('error')
        assert socket_api('POST', store.url + '/stop')[0] == 202
    finally:
        release.set()
        join(worker)
    assert store.job['phase'] == 'paused'
    return store, output


def resume_token(store):
    with web.FILES.initialize(store.job).report_lock:
        return web._checkpoint_resume_token_locked(store.job)


def test_real_stop_waits_for_frame_boundary_and_hides_old_output(checkpoint_web, socket_api, monkeypatch):
    store, output = checkpoint_web
    entered, release = hold_after_frames(monkeypatch)
    web.enqueue(store.job, 'scan')
    worker = run_worker()
    try:
        assert entered.wait(12), store.job.get('error')
        assert socket_api('POST', store.url + '/stop')[0] == 202
        assert not store.path.exists()
        assert store.job['phase'] == 'scanning'
    finally:
        release.set()
        join(worker)
    doc = json.loads(store.path.read_text())
    assert doc['stop_review']['next_frame'] == 7
    assert len(doc['render_state']['cum']) == len(doc['render_state']['bands']) == 7
    status = json.loads(socket_api('GET', store.url)[2])
    assert status['phase'] == 'paused' and status['checkpoint_unfinished']
    assert not status['has_output'] and store.job['output'] is None
    assert output.read_bytes() == b'older output must remain intact'
    assert socket_api('POST', store.url + '/render')[0] == 409
    assert not (store.path.parent / web._CHECKPOINT_RECOVERY_NAME).exists()


def test_natural_eof_publishes_verified_complete_review(checkpoint_web, socket_api):
    store, output = checkpoint_web
    web.enqueue(store.job, 'scan')
    join(run_worker())
    doc = json.loads(store.path.read_text())
    assert 'stop_review' not in doc
    assert doc['provenance']['checkpoint_identity']['timeline']['count_verified'] is True
    assert len(doc['render_state']['cum']) == 24
    assert all(row['scan_frame_start'] == 0 and row['scan_frame_end'] == 24
               for row in doc['detections'])
    status = json.loads(socket_api('GET', store.url)[2])
    assert status['phase'] == 'review' and not status['checkpoint_unfinished']
    assert not status['has_output'] and store.job['output'] is None
    assert output.read_bytes() == b'older output must remain intact'


@pytest.mark.parametrize('category', ['qrcode', 'none'])
def test_checkpoint_scan_with_permanent_name_allowlist(checkpoint_web, category):
    store, _ = checkpoint_web
    (store.jobs / 'allowlist.txt').write_text('Alice Example\n')
    store.job['options']['categories'] = category
    web.enqueue(store.job, 'scan')
    join(run_worker())
    assert store.job['phase'] == 'review', store.job['error']
    doc = json.loads(store.path.read_text())
    assert doc['provenance']['checkpoint_identity']['timeline']['count_verified'] is True


def test_ordinary_scan_keeps_permanent_name_allowlist(checkpoint_web):
    store, _ = checkpoint_web
    (store.jobs / 'allowlist.txt').write_text('Alice Example\n')
    store.job['options'].update(checkpoint_review=False, categories='name')
    args = web.build_args(store.job)
    with open(args.allow_names, encoding='utf-8') as stream:
        assert stream.read().strip() == 'Alice Example'


def test_cancel_acknowledged_before_staged_commit_wins(checkpoint_web, socket_api, monkeypatch):
    store, output = checkpoint_web
    ready, release = threading.Event(), threading.Event()
    original = checkpoint_runtime._staged_report
    @contextmanager
    def held_stage(*args, **kwargs):
        with original(*args, **kwargs) as stage:
            ready.set()
            assert release.wait(12)
            yield stage
    monkeypatch.setattr(checkpoint_runtime, '_staged_report', held_stage)
    web.enqueue(store.job, 'scan')
    worker = run_worker()
    try:
        assert ready.wait(12), store.job.get('error')
        assert socket_api('POST', store.url + '/cancel')[0] == 200
    finally:
        release.set()
        join(worker)
    assert not store.path.exists()
    assert store.job['phase'] == 'cancelled'
    assert output.read_bytes() == b'older output must remain intact'
    assert not (store.path.parent / web._CHECKPOINT_RECOVERY_NAME).exists()


@pytest.mark.parametrize('change', ['cleared', 'replaced'])
def test_partial_commit_requires_its_captured_stop_event(checkpoint_web, socket_api, monkeypatch, change):
    store, output = checkpoint_web
    entered, release_frame = hold_after_frames(monkeypatch)
    staged, release_stage = threading.Event(), threading.Event()
    original = checkpoint_runtime._staged_report
    @contextmanager
    def held_stage(*args, **kwargs):
        with original(*args, **kwargs) as stage:
            staged.set()
            assert release_stage.wait(12)
            yield stage
    monkeypatch.setattr(checkpoint_runtime, '_staged_report', held_stage)
    web.enqueue(store.job, 'scan')
    worker = run_worker()
    try:
        assert entered.wait(12)
        assert socket_api('POST', store.url + '/stop')[0] == 202
        release_frame.set()
        assert staged.wait(12)
        files = web.FILES.initialize(store.job)
        with files.report_lock:
            if change == 'cleared':
                files.active.checkpoint_stop.clear()
            else:
                files.active.checkpoint_stop = threading.Event()
    finally:
        release_frame.set()
        release_stage.set()
        join(worker)
    assert not store.path.exists()
    assert output.read_bytes() == b'older output must remain intact'
    assert not (store.path.parent / web._CHECKPOINT_RECOVERY_NAME).exists()


def test_marker_and_directory_are_synced_before_report_replace(checkpoint_web, monkeypatch):
    store, _ = checkpoint_web
    marker = store.path.parent / web._CHECKPOINT_RECOVERY_NAME
    original_sync, original_replace = os.fsync, os.replace
    observed = set()
    def sync(fd):
        info = os.fstat(fd)
        if stat.S_ISDIR(info.st_mode):
            observed.add('directory')
        if marker.exists():
            target = marker.stat()
            if (info.st_dev, info.st_ino) == (target.st_dev, target.st_ino):
                observed.add('marker')
        return original_sync(fd)
    def replace(source, target):
        if str(target) == str(store.path):
            assert marker.is_file() and {'marker', 'directory'} <= observed
            observed.add('report')
        return original_replace(source, target)
    monkeypatch.setattr(os, 'fsync', sync)
    monkeypatch.setattr(os, 'replace', replace)
    web.enqueue(store.job, 'scan')
    join(run_worker())
    assert 'report' in observed and not marker.exists()
    assert store.job['phase'] == 'review'


def test_failure_before_replace_removes_marker_without_recovery(checkpoint_web, monkeypatch):
    store, output = checkpoint_web
    def fail(*args, **kwargs):
        raise OSError('controlled pre-replace failure')
    monkeypatch.setattr(web, '_publish_checkpoint_locked', fail)
    web.enqueue(store.job, 'scan')
    join(run_worker())
    assert not store.path.exists()
    assert not (store.path.parent / web._CHECKPOINT_RECOVERY_NAME).exists()
    assert not web.FILES.initialize(store.job).recovery_required
    assert store.job['phase'] == 'error'
    assert output.read_bytes() == b'older output must remain intact'


def test_marker_sync_failure_never_replaces_report(checkpoint_web, monkeypatch):
    store, output = checkpoint_web
    marker = store.path.parent / web._CHECKPOINT_RECOVERY_NAME
    real_sync = os.fsync
    def fail_marker(fd):
        info = os.fstat(fd)
        if marker.exists():
            named = marker.stat()
            if (info.st_dev, info.st_ino) == (named.st_dev, named.st_ino):
                raise OSError('controlled marker sync failure')
        return real_sync(fd)
    monkeypatch.setattr(os, 'fsync', fail_marker)
    web.enqueue(store.job, 'scan')
    join(run_worker())
    assert not store.path.exists() and not marker.exists()
    assert store.job['phase'] == 'error'
    assert output.read_bytes() == b'older output must remain intact'


def test_marker_descriptor_closed_if_wrapper_creation_fails(checkpoint_job, monkeypatch):
    store, _, owner, files, generation, operation = checkpoint_job
    before = store.path.read_bytes()
    doc = json.loads(before)
    marker = store.path.parent / web._CHECKPOINT_RECOVERY_NAME
    actual_open, actual_fdopen = os.open, os.fdopen
    descriptors = []
    with checkpoint_runtime._staged_report(str(store.path), doc) as staged:
        def observe(path, *args, **kwargs):
            fd = actual_open(path, *args, **kwargs)
            if str(path) == str(marker):
                descriptors.append(fd)
            return fd
        def fail_marker(fd, *args, **kwargs):
            if descriptors and fd == descriptors[-1]:
                raise OSError('controlled wrapper failure')
            return actual_fdopen(fd, *args, **kwargs)
        monkeypatch.setattr(os, 'open', observe)
        monkeypatch.setattr(os, 'fdopen', fail_marker)
        with files.report_lock, pytest.raises(OSError, match='wrapper failure'):
            web._publish_checkpoint_job_locked(store.job, owner, generation, operation,
                                               staged, str(store.path), doc)
        assert len(descriptors) == 1
        with pytest.raises(OSError):
            os.fstat(descriptors[0])
    assert store.path.read_bytes() == before and not marker.exists()


def test_stop_before_first_frame_preserves_prior_output(checkpoint_web, socket_api, monkeypatch):
    store, output = checkpoint_web
    ready, release = threading.Event(), threading.Event()
    original = checkpoint_runtime.scan_to_report
    def held(*args, **kwargs):
        ready.set()
        assert release.wait(12)
        return original(*args, **kwargs)
    monkeypatch.setattr(checkpoint_runtime, 'scan_to_report', held)
    web.enqueue(store.job, 'scan')
    worker = run_worker()
    try:
        assert ready.wait(12)
        assert socket_api('POST', store.url + '/stop')[0] == 202
    finally:
        release.set()
        join(worker)
    assert not store.path.exists() and store.job['phase'] == 'error'
    assert output.read_bytes() == b'older output must remain intact'
    assert not (store.path.parent / web._CHECKPOINT_RECOVERY_NAME).exists()


def test_post_replace_failure_stays_fenced_after_restart(checkpoint_web, monkeypatch):
    store, output = checkpoint_web
    def fail_after_replace(*args, **kwargs):
        raise OSError('controlled post-replace notification failure')
    monkeypatch.setattr(web, '_report_committed_locked', fail_after_replace)
    web.enqueue(store.job, 'scan')
    join(run_worker())
    marker = store.path.parent / web._CHECKPOINT_RECOVERY_NAME
    assert store.path.exists() and marker.exists()
    assert web.FILES.initialize(store.job).recovery_required
    web.JOBS.clear()
    web._rehydrate_jobs()
    recovered = web.JOBS[store.job['id']]
    assert recovered['phase'] == 'error' and recovered['output'] is None
    assert web.FILES.initialize(recovered).recovery_required
    assert output.read_bytes() == b'older output must remain intact'


def test_resume_requires_current_saved_report_token_and_completes(paused_web, socket_api):
    store, output = paused_web
    before = store.path.read_bytes()
    token = resume_token(store)
    assert socket_api('POST', store.url + '/resume', {})[0] == 400
    store.path.write_bytes(before + b' ')
    changed = store.path.read_bytes()
    assert socket_api('POST', store.url + '/resume', {'resume_token': token})[0] == 409
    assert store.path.read_bytes() == changed and web.WORK_Q.empty()
    token = resume_token(store)
    status, _, body = socket_api('POST', store.url + '/resume', {'resume_token': token})
    assert status == 202 and json.loads(body) == {'ok': True, 'state': 'queued'}
    join(run_worker())
    doc = json.loads(store.path.read_text())
    assert 'stop_review' not in doc
    assert doc['provenance']['checkpoint_identity']['timeline']['count_verified'] is True
    assert len(doc['render_state']['cum']) == 24
    assert store.job['phase'] == 'review' and not store.job['_checkpoint_unfinished']
    assert store.job['output'] is None and output.read_bytes() == b'older output must remain intact'


def test_cancel_ack_before_resume_commit_preserves_paused_bytes(paused_web, socket_api, monkeypatch):
    store, _ = paused_web
    before = store.path.read_bytes()
    original_token = resume_token(store)
    ready, release = threading.Event(), threading.Event()
    original = checkpoint_runtime._staged_report
    @contextmanager
    def held_stage(*args, **kwargs):
        with original(*args, **kwargs) as staged:
            ready.set()
            assert release.wait(12)
            yield staged
    monkeypatch.setattr(checkpoint_runtime, '_staged_report', held_stage)
    assert socket_api('POST', store.url + '/resume', {'resume_token': original_token})[0] == 202
    worker = run_worker()
    try:
        assert ready.wait(12), store.job.get('error')
        assert socket_api('POST', store.url + '/cancel')[0] == 200
        assert socket_api('POST', store.url + '/resume', {'resume_token': original_token})[0] == 409
    finally:
        release.set()
        join(worker)
    assert store.path.read_bytes() == before
    assert store.job['phase'] == 'paused' and store.job['_checkpoint_unfinished']
    assert store.job['output'] is None and resume_token(store) == original_token
    assert socket_api('POST', store.url + '/retry')[0] == 409


def test_stop_before_resume_progress_preserves_bytes_and_returns_to_paused(paused_web, socket_api, monkeypatch):
    store, _ = paused_web
    before = store.path.read_bytes()
    ready, release = threading.Event(), threading.Event()
    original = checkpoint_runtime.scan_to_report
    def held(*args, **kwargs):
        ready.set()
        assert release.wait(12)
        return original(*args, **kwargs)
    monkeypatch.setattr(checkpoint_runtime, 'scan_to_report', held)
    assert socket_api('POST', store.url + '/resume', {'resume_token': resume_token(store)})[0] == 202
    worker = run_worker()
    try:
        assert ready.wait(12)
        assert socket_api('POST', store.url + '/stop')[0] == 202
    finally:
        release.set()
        join(worker)
    assert store.path.read_bytes() == before
    assert store.job['phase'] == 'paused' and store.job['_checkpoint_unfinished']
    assert not (store.path.parent / web._CHECKPOINT_RECOVERY_NAME).exists()


def test_ordinary_scan_arguments_and_stop_route_remain_unchanged(store):
    args = web.build_args(store.job)
    assert not args.no_vfr_fix and not args.no_backtrack and args.scroll_track == 'auto'
    assert 'checkpoint_enabled' not in web.job_public(store.job)
    with web.app.test_client() as client:
        assert client.post(store.url + '/stop').status_code == 409


def test_qr_checkpoint_does_not_attach_unrelated_selected_models(checkpoint_web, monkeypatch):
    store, _ = checkpoint_web
    monkeypatch.setattr(web, 'load_model_select', lambda: {'face': 'face', 'plate': 'plate', 'person': 'person'})
    monkeypatch.setattr(web, 'find_model_file', lambda name: '/unused/' + name)
    args = web.build_args(store.job)
    assert args.no_vfr_fix and args.no_backtrack and args.scroll_track == 'off'
    assert not args.face_model and not args.plate_model and not args.person_model


def test_unsupported_source_is_rejected_before_frame_decoder(checkpoint_web, monkeypatch):
    import cv2
    import numpy as np
    store, output = checkpoint_web
    unsupported = store.path.parent / 'unsupported.avi'
    writer = cv2.VideoWriter(str(unsupported), cv2.VideoWriter_fourcc(*'MJPG'), 5, (64, 48))
    assert writer.isOpened()
    writer.write(np.zeros((48, 64, 3), np.uint8))
    writer.release()
    store.job['video'] = str(unsupported)
    monkeypatch.setattr(checkpoint_media.FrameStream, '__enter__',
                        lambda self: pytest.fail('unsupported source reached frame decode'))
    web.enqueue(store.job, 'scan')
    join(run_worker())
    assert store.job['phase'] == 'error' and not store.path.exists()
    assert output.read_bytes() == b'older output must remain intact'


def test_foreign_job_source_is_rejected_before_frame_decoder(checkpoint_web, monkeypatch):
    store, output = checkpoint_web
    other = web.new_job('', {}, 'other.mp4')
    foreign = os.path.join(other['dir'], 'input.mp4')
    shutil.copyfile(store.job['video'], foreign)
    other['video'] = foreign
    store.job['video'] = foreign
    monkeypatch.setattr(checkpoint_media.FrameStream, '__enter__',
                        lambda self: pytest.fail('foreign source reached frame decode'))
    web.enqueue(store.job, 'scan')
    join(run_worker())
    assert store.job['phase'] == 'error' and not store.path.exists()
    assert output.read_bytes() == b'older output must remain intact'


@pytest.mark.parametrize('options', [
    {'checkpoint_review': 'yes', 'categories': 'qrcode'},
    {'checkpoint_review': True, 'categories': 'face'},
    {'checkpoint_review': True, 'categories': 'qrcode', 'windows': [{'t0': 0, 't1': 1}]},
    {'checkpoint_review': True, 'categories': 'qrcode', 'skip_review': True},
])
def test_unsupported_checkpoint_options_fail_before_job_allocation(store, options):
    with web.app.test_client() as client:
        response = client.post('/api/jobs', data={'server_path': store.job['video'],
                                                  'options': json.dumps(options)})
    assert response.status_code == 400
    assert len(web.JOBS) == 1 and web.WORK_Q.empty()
