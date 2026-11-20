"""Checkpoint publication against the existing web job operation owner."""
import json
import threading
from contextlib import contextmanager

import pytest
import openscrub as core
import openscrub_web as web
from openscrub_internal import checkpoint_runtime as runtime
from openscrub_internal.reports import atomic_report
from test_checkpoint_runtime import Quiet, args_for, movie, owned_scan, stop_after
from test_job_lifecycle import store, request


@pytest.fixture
def checkpoint_job(store):
    video = movie(store.path.parent)
    args = args_for(video)
    args.categories = 'none'
    store.path.unlink()
    initial = owned_scan(runtime, args, str(store.path), cb=Quiet(),
                         stop_requested=stop_after(9))
    initial['detections'].append(dict(
        t_start=0.0, t_end=1.0, last_seen=0.0, cbox=[4, 4, 16, 16],
        aoff=[0.0, 0.0], category='manual', text='reviewed', enabled=False,
        track=21, person=-1, opaque={'preserved': True}))
    initial['audio_redactions'] = [{'t0': .2, 't1': .4, 'mode': 'mute', 'future': True}]
    atomic_report(str(store.path), initial)
    store.job.update(video=str(video), phase='review')
    owner = web._prepare_work(store.job, 'scan')
    files = web.FILES.initialize(store.job)
    with files.report_lock:
        ticket = web._reserve_queue_locked(store.job, 'scan', owner)
        # The real worker removes a claimed ticket before running its lease.
        with web.JOBS_LOCK:
            files.queued.pop(ticket[2], None)
        store.job['phase'] = 'scanning'
    yield store, args, owner, files, ticket[2], owner.operation
    web._finish_operation(store.job, owner)


def commit_for(job, owner, generation, operation, files):
    def commit(staged, path, doc):
        assert files.report_lock.locked()
        return web._publish_checkpoint_locked(job, owner, generation,
                                              operation, staged, path, doc)
    return commit


def test_owned_checkpoint_publish_advances_report_epoch(checkpoint_job):
    store, args, owner, files, generation, operation = checkpoint_job
    assert callable(getattr(web, '_publish_checkpoint_locked', None)), (
        'web checkpoint publication needs the existing operation owner')
    previous = json.loads(store.path.read_text())
    old_epoch, old_output_epoch = files.committed_report_epoch, files.output_epoch
    result = runtime.scan_to_report(
        args, str(store.path), cb=web.WebCallbacks(store.job, operation),
        stop_requested=lambda: False, publication_lock=files.report_lock,
        resume=True,
        _commit_staged=commit_for(store.job, owner, generation, operation, files))
    assert result == json.loads(store.path.read_text())
    assert 'stop_review' not in result
    assert result['detections'] == previous['detections']
    assert result['audio_redactions'] == previous['audio_redactions']
    assert files.committed_report_epoch == old_epoch + 1
    assert files.output_epoch == old_output_epoch + 1
    assert files.source_status == 'pending'
    assert files.source_pair[:3] == (operation, files.committed_report_epoch, str(args.video))
    assert files.source_pair[3] == web._file_stamp(store.path.stat())
    assert store.job['phase'] == 'scanning'  # worker owns subsequent phase/adoption


@pytest.mark.parametrize('cause', ['stale_qgen', 'cancel_ack'])
def test_obsolete_checkpoint_attempt_cannot_publish_after_staging(checkpoint_job, monkeypatch, cause):
    store, args, owner, files, generation, operation = checkpoint_job
    assert callable(getattr(web, '_publish_checkpoint_locked', None)), (
        'web checkpoint publication needs the existing operation owner')
    before = store.path.read_bytes()
    old_epoch, old_output_epoch = files.committed_report_epoch, files.output_epoch
    ready, release = threading.Event(), threading.Event()
    actual_stage = runtime._staged_report
    @contextmanager
    def delayed_stage(*args, **kwargs):
        with actual_stage(*args, **kwargs) as staged:
            ready.set()
            assert release.wait(15)
            yield staged
    monkeypatch.setattr(runtime, '_staged_report', delayed_stage)
    failures = []
    def run():
        try:
            runtime.scan_to_report(
                args, str(store.path), cb=web.WebCallbacks(store.job, operation),
                stop_requested=lambda: False, publication_lock=files.report_lock,
                resume=True,
                _commit_staged=commit_for(store.job, owner, generation, operation, files))
        except BaseException as error:
            failures.append(error)
    thread = threading.Thread(target=run)
    thread.start()
    try:
        assert ready.wait(15)
        if cause == 'stale_qgen':
            with files.report_lock:
                with web.JOBS_LOCK:
                    store.job['qgen'] += 1
        else:
            assert request('post', store.url + '/cancel').status_code == 200
            # Clearing an already acknowledged Event must not resurrect the owner.
            operation.clear()
    finally:
        release.set()
        thread.join(15)
    assert not thread.is_alive()
    assert len(failures) == 1 and isinstance(failures[0], core.PipelineCancelled)
    assert store.path.read_bytes() == before
    assert files.committed_report_epoch == old_epoch
    assert files.output_epoch == old_output_epoch
    assert not list(store.path.parent.glob('.report-*.tmp'))


def test_failed_checkpoint_replace_preserves_report_and_epochs(checkpoint_job, monkeypatch):
    store, args, owner, files, generation, operation = checkpoint_job
    before = store.path.read_bytes()
    state_before = (files.committed_report_epoch, files.output_epoch,
                    files.source_status, files.source_pair)
    def fail_replace(source, target):
        raise OSError('synthetic report replacement failure')
    monkeypatch.setattr(web.os, 'replace', fail_replace)
    with pytest.raises(OSError, match='replacement failure'):
        runtime.scan_to_report(
            args, str(store.path), cb=web.WebCallbacks(store.job, operation),
            stop_requested=lambda: False, publication_lock=files.report_lock,
            resume=True,
            _commit_staged=commit_for(store.job, owner, generation, operation, files))
    assert store.path.read_bytes() == before
    assert (files.committed_report_epoch, files.output_epoch,
            files.source_status, files.source_pair) == state_before
    assert not list(store.path.parent.glob('.report-*.tmp'))


def test_checkpoint_notification_preparation_failure_preserves_report(checkpoint_job, monkeypatch):
    store, args, owner, files, generation, operation = checkpoint_job
    before = store.path.read_bytes()
    state_before = (files.committed_report_epoch, files.output_epoch,
                    files.source_status, files.source_pair)
    def fail_invalidation(*args, **kwargs):
        raise OSError('synthetic thumbnail invalidation failure')
    monkeypatch.setattr(web.thumbs, 'invalidate_locked', fail_invalidation)
    with pytest.raises(OSError, match='invalidation failure'):
        runtime.scan_to_report(
            args, str(store.path), cb=web.WebCallbacks(store.job, operation),
            stop_requested=lambda: False, publication_lock=files.report_lock,
            resume=True,
            _commit_staged=commit_for(store.job, owner, generation, operation, files))
    assert store.path.read_bytes() == before
    assert (files.committed_report_epoch, files.output_epoch,
            files.source_status, files.source_pair) == state_before
    assert not list(store.path.parent.glob('.report-*.tmp'))


def test_unsupported_platform_rejects_before_checkpoint_replacement(checkpoint_job, monkeypatch):
    store, args, owner, files, generation, operation = checkpoint_job
    before = store.path.read_bytes()
    state_before = (files.committed_report_epoch, files.output_epoch,
                    files.source_status, files.source_pair)
    monkeypatch.setattr(web, '_CHECKPOINT_FD_PUBLICATION', False, raising=False)
    with pytest.raises(ValueError, match='POSIX|platform'):
        runtime.scan_to_report(
            args, str(store.path), cb=web.WebCallbacks(store.job, operation),
            stop_requested=lambda: False, publication_lock=files.report_lock,
            resume=True,
            _commit_staged=commit_for(store.job, owner, generation, operation, files))
    assert store.path.read_bytes() == before
    assert (files.committed_report_epoch, files.output_epoch,
            files.source_status, files.source_pair) == state_before


def test_post_replace_failure_reports_committed_and_blocks_job(checkpoint_job, monkeypatch):
    store, args, owner, files, generation, operation = checkpoint_job
    before = store.path.read_bytes()
    old_output_epoch = files.output_epoch
    real_replace, real_fstat = web.os.replace, web.os.fstat
    replaced = threading.Event()
    def replace(source, target):
        result = real_replace(source, target)
        if str(target) == str(store.path):
            replaced.set()
        return result
    def fail_after_replace(fd):
        if replaced.is_set():
            raise OSError('synthetic post-replace stat failure')
        return real_fstat(fd)
    monkeypatch.setattr(web.os, 'replace', replace)
    monkeypatch.setattr(web.os, 'fstat', fail_after_replace)
    with pytest.raises(Exception) as caught:
        runtime.scan_to_report(
            args, str(store.path), cb=web.WebCallbacks(store.job, operation),
            stop_requested=lambda: False, publication_lock=files.report_lock,
            resume=True,
            _commit_staged=commit_for(store.job, owner, generation, operation, files))
    assert replaced.is_set() and store.path.read_bytes() != before
    assert getattr(caught.value, 'committed', False) is True
    assert files.output_epoch == old_output_epoch + 1
    assert files.recovery_required is True
    assert store.job['phase'] == 'error'
    assert 'checkpoint' in store.job['error'].lower()
    assert isinstance(caught.value.__cause__, OSError)
    committed = json.loads(store.path.read_text())
    assert committed['detections'][0]['opaque'] == {'preserved': True}
    assert committed['audio_redactions'][0]['future'] is True
    from werkzeug.exceptions import Conflict
    with pytest.raises(Conflict):
        web._recovery_gate(store.job)
    assert not list(store.path.parent.glob('.report-*.tmp'))


@pytest.mark.parametrize('violation', ['foreign_source', 'different_source', 'different_report'])
def test_checkpoint_rejects_unowned_source_or_report(checkpoint_job, violation):
    store, args, owner, files, generation, operation = checkpoint_job
    before = store.path.read_bytes()
    state_before = (files.committed_report_epoch, files.output_epoch,
                    files.source_status, files.source_pair)
    document = json.loads(before)
    if violation == 'foreign_source':
        owner.source_state = object()
    elif violation == 'different_source':
        document['provenance']['input'] = str(store.path.parent / 'different.mp4')
    target = str(store.path.parent / 'different-report.json') if violation == 'different_report' else str(store.path)
    with runtime._staged_report(str(store.path), document) as staged:
        with files.report_lock:
            with pytest.raises(ValueError, match='source|report'):
                web._publish_checkpoint_locked(store.job, owner, generation,
                                               operation, staged, target, document)
    assert store.path.read_bytes() == before
    assert (files.committed_report_epoch, files.output_epoch,
            files.source_status, files.source_pair) == state_before


def test_checkpoint_requires_the_current_active_owner(checkpoint_job):
    store, args, owner, files, generation, operation = checkpoint_job
    before = store.path.read_bytes()
    document = json.loads(before)
    with runtime._staged_report(str(store.path), document) as staged:
        with files.report_lock:
            files.active = None
            with pytest.raises(core.PipelineCancelled):
                web._publish_checkpoint_locked(store.job, owner, generation,
                                               operation, staged, str(store.path), document)
    assert store.path.read_bytes() == before


def test_stage_descriptor_is_closed_if_wrapping_fails(checkpoint_job, monkeypatch):
    store, args, owner, files, generation, operation = checkpoint_job
    before = store.path.read_bytes()
    document = json.loads(before)
    actual_open = web.os.open
    descriptors = []
    with runtime._staged_report(str(store.path), document) as staged:
        def observe(path, *args, **kwargs):
            fd = actual_open(path, *args, **kwargs)
            if str(path) == str(staged):
                descriptors.append(fd)
            return fd
        def fail_fdopen(*args, **kwargs):
            raise OSError('synthetic stage descriptor wrapping failure')
        monkeypatch.setattr(web.os, 'open', observe)
        monkeypatch.setattr(web.os, 'fdopen', fail_fdopen)
        try:
            with files.report_lock:
                with pytest.raises(OSError, match='wrapping failure'):
                    web._publish_checkpoint_locked(store.job, owner, generation,
                                                   operation, staged, str(store.path), document)
            assert len(descriptors) == 1
            with pytest.raises(OSError):
                web.os.fstat(descriptors[0])
        finally:
            for fd in descriptors:
                try:
                    web.os.close(fd)
                except OSError:
                    pass
    assert store.path.read_bytes() == before


@pytest.mark.skipif(not hasattr(web.os, 'mkfifo'), reason='POSIX FIFO required')
def test_nonregular_checkpoint_stage_cannot_block_report_lock(checkpoint_job):
    import os
    import time
    store, args, owner, files, generation, operation = checkpoint_job
    before = store.path.read_bytes()
    document = json.loads(before)
    stage = store.path.parent / 'hostile-stage'
    os.mkfifo(stage)
    finished, errors = threading.Event(), []
    def publish():
        try:
            with files.report_lock:
                web._publish_checkpoint_locked(store.job, owner, generation,
                                               operation, str(stage), str(store.path), document)
        except BaseException as error:
            errors.append(error)
        finally:
            finished.set()
    thread = threading.Thread(target=publish)
    thread.start()
    try:
        completed_promptly = finished.wait(.7)
    finally:
        if not finished.is_set():
            # Unblock the pre-fix FIFO open so the regression never hangs pytest.
            writer = os.open(stage, os.O_WRONLY | os.O_NONBLOCK)
            os.close(writer)
        thread.join(4)
        stage.unlink()
    assert not thread.is_alive()
    assert completed_promptly, 'nonregular stage blocked the stable report lock'
    assert len(errors) == 1 and isinstance(errors[0], (OSError, ValueError))
    assert store.path.read_bytes() == before
