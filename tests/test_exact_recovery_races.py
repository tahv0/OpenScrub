"""Recovery authority and selected-source IO races through production routes."""
import os
from pathlib import Path
import threading

import pytest
import openscrub
import openscrub_web as web
from test_exact_adoption import scan
from test_exact_samples import exact, sample
from test_job_lifecycle import store, request, finish


def start_named(name, method, url, **kwargs):
    done, errors, values = threading.Event(), [], []
    def run():
        try:
            values.append(request(method, url, **kwargs))
        except BaseException as error:
            errors.append(error)
        finally:
            done.set()
    thread = threading.Thread(name=name, target=run)
    thread.start()
    return thread, done, errors, values


def recoverable_pair(scan, monkeypatch):
    exact, background = scan
    sample(exact)  # establish the older observed source through the real route
    old_path = Path(exact.job['video'])
    normalized = old_path.with_name('normalized.avi')
    def compute(args, cb):
        args.original_video, args.video = args.video, str(normalized)
        return dict(fps=5, cum=[[0,0]]*10, bands=[[0,0]]*10,
                    detections=[], stats={})
    monkeypatch.setattr(openscrub, 'run_scan', compute)
    web._run_job(exact.job, 'scan')
    files = web.FILES.initialize(exact.job)
    assert files.source_status == 'unavailable' and files.source_pair is not None
    assert not background and web.FILES.count == 0
    normalized.write_bytes(old_path.read_bytes())
    return exact, files, normalized


def record_failures_and_captures(monkeypatch):
    failures, captures = [], []
    real_error, real_capture = web._exact_error, web.cv2.VideoCapture
    def error(value):
        failures.append(value)  # retain tracebacks through cleanup assertions
        return real_error(value)
    class Capture:
        def __init__(self, *args, **kwargs):
            self.cap = real_capture(*args, **kwargs)
            self.released = False
            captures.append(self)
        def __getattr__(self, key):
            return getattr(self.cap, key)
        def release(self):
            self.released = True
            self.cap.release()
    monkeypatch.setattr(web, '_exact_error', error)
    monkeypatch.setattr(web.cv2, 'VideoCapture', Capture)
    return failures, captures


def delay_cancel_lock(files, monkeypatch):
    waiting, release = threading.Event(), threading.Event()
    original = files.report_lock
    class Gate:
        def __enter__(self):
            if threading.current_thread().name == 'held-exact-cancel':
                waiting.set()
                assert release.wait(8)
            return original.__enter__()
        def __exit__(self, *args):
            return original.__exit__(*args)
    monkeypatch.setattr(files, 'report_lock', Gate())
    return waiting, release


def report_before(exact, files):
    return (exact.path.read_bytes(), web._file_stamp(os.stat(exact.path)),
            files.committed_report_epoch)


def assert_report_unchanged(exact, files, before):
    assert report_before(exact, files) == before


def assert_conflict(response):
    assert response.status_code == 409, {
        'status': response.status_code, 'json': response.is_json,
        'fields': sorted(response.json) if response.is_json else None}
    assert response.is_json and response.json['error'] == 'sample_conflict'
    assert response.headers['Cache-Control'] == 'private, no-store'
    assert 'sample' not in response.json and 'image' not in response.json


def test_recovery_rechecks_signalled_cancel_before_authoritative_commit(scan, monkeypatch):
    exact, files, normalized = recoverable_pair(scan, monkeypatch)
    before = report_before(exact, files)
    old_source, old_video = files.current_source, exact.job['video']
    old_epoch, pair = files.source_epoch, files.source_pair
    failures, captures = record_failures_and_captures(monkeypatch)
    prepared, resume = threading.Event(), threading.Event()
    held_leases = []
    original = web._prepare_observed_source
    def prepare(*args):
        value = original(*args)
        held_leases.append(value[1])
        prepared.set()
        assert resume.wait(8)
        return value
    monkeypatch.setattr(web, '_prepare_observed_source', prepare)
    cancel_waiting, cancel_release = delay_cancel_lock(files, monkeypatch)
    recovery = start_named('held-exact-recovery', 'get', exact.url+'/edit_sample?t=0.2')
    cancel = None
    try:
        assert prepared.wait(5)
        cancel = start_named('held-exact-cancel', 'post', exact.url+'/cancel')
        assert cancel_waiting.wait(5) and pair[0].is_set()
        assert files.operation is pair[0] and files.source_pair == pair
        resume.set()
        response = finish(recovery)
        assert_conflict(response)
        assert exact.job['video'] == old_video and files.current_source is old_source
        assert files.source_epoch == old_epoch and files.source_pair == pair
        assert not captures and failures
        assert_report_unchanged(exact, files, before)
    finally:
        resume.set()
        cancel_release.set()
        finish(recovery)
        if cancel is not None:
            assert finish(cancel).status_code == 200
    assert all(lease.released for lease in held_leases)
    assert files.operation is None and files.source_pair is None
    assert web.FILES.count == 0


@pytest.mark.parametrize('replace_source', [False, True])
def test_completed_recovery_pair_cannot_authorize_a_second_request(scan, monkeypatch, replace_source):
    exact, files, normalized = recoverable_pair(scan, monkeypatch)
    before = report_before(exact, files)
    failures, captures = record_failures_and_captures(monkeypatch)
    entered, resume = threading.Event(), threading.Event()
    held_leases = []
    original = web._prepare_observed_source
    def prepare(*args):
        if threading.current_thread().name == 'stale-exact-recovery':
            entered.set()  # early recovery check passed; source not opened yet
            assert resume.wait(8)
        value = original(*args)
        held_leases.append(value[1])
        return value
    monkeypatch.setattr(web, '_prepare_observed_source', prepare)
    stale = start_named('stale-exact-recovery', 'get', exact.url+'/edit_sample?t=0.2')
    try:
        assert entered.wait(5)
        first = request('get', exact.url+'/edit_sample?t=0.2')
        assert first.status_code == 200 and files.source_pair is None
        selected, epoch = files.current_source, files.source_epoch
        if replace_source:
            replacement = normalized.with_name('replacement.avi')
            replacement.write_bytes(normalized.read_bytes())
            replacement.replace(normalized)
            assert web._file_stamp(os.stat(normalized)) != selected['stamp']
        resume.set()
        response = finish(stale)
        if replace_source or response.status_code == 409:
            assert_conflict(response)
            assert failures and len(captures) == 1  # only request A decoded
        else:
            # Identical-descriptor non-authoritative convergence is allowed.
            assert response.status_code == 200
            assert response.json['sample']['source_ref'] == first.json['sample']['source_ref']
        assert files.current_source is selected and files.source_epoch == epoch
        assert exact.job['video'] == str(normalized) and files.source_pair is None
        assert_report_unchanged(exact, files, before)
    finally:
        resume.set()
        finish(stale)
    assert all(lease.released for lease in held_leases)
    assert all(cap.released for cap in captures) and web.FILES.count == 0
    if replace_source:
        assert request('get', exact.url+'/edit_sample?t=0.2').status_code == 422
        assert files.source_retired


def test_final_sample_acceptance_rechecks_signalled_operation(scan, monkeypatch):
    exact, files, normalized = recoverable_pair(scan, monkeypatch)
    before = report_before(exact, files)
    operation = files.source_pair[0]
    failures, captures = record_failures_and_captures(monkeypatch)
    decoded, resume = threading.Event(), threading.Event()
    original = web.exact.read_indexed_capture
    def read(*args, **kwargs):
        value = original(*args, **kwargs)
        decoded.set()
        assert resume.wait(8)
        return value
    monkeypatch.setattr(web.exact, 'read_indexed_capture', read)
    cancel_waiting, cancel_release = delay_cancel_lock(files, monkeypatch)
    recovery = start_named('decoding-exact-recovery', 'get', exact.url+'/edit_sample?t=0.2')
    cancel = None
    try:
        assert decoded.wait(5)
        assert files.source_pair is None and exact.job['video'] == str(normalized)
        cancel = start_named('held-exact-cancel', 'post', exact.url+'/cancel')
        assert cancel_waiting.wait(5) and operation.is_set()
        resume.set()
        assert_conflict(finish(recovery))
        assert failures and len(captures) == 1 and captures[0].released
        assert_report_unchanged(exact, files, before)
    finally:
        resume.set()
        cancel_release.set()
        finish(recovery)
        if cancel is not None:
            assert finish(cancel).status_code == 200
    assert files.operation is None and web.FILES.count == 0


def test_selected_source_disappearance_before_open_is_json_conflict(exact, monkeypatch):
    files = web.FILES.initialize(exact.job)
    before = report_before(exact, files)
    failures, captures = record_failures_and_captures(monkeypatch)
    selected, resume = threading.Event(), threading.Event()
    snapshots = []
    original = web._exact_snapshot
    def snapshot(*args):
        value = original(*args)
        snapshots.append(value)  # retain the released lease on the failure path
        selected.set()
        assert resume.wait(8)
        return value
    monkeypatch.setattr(web, '_exact_snapshot', snapshot)
    call = start_named('selected-exact-source', 'get', exact.url+'/edit_sample?t=0.2')
    try:
        assert selected.wait(5)
        Path(exact.job['video']).unlink()
        resume.set()
        assert_conflict(finish(call))
        assert failures and not captures
        assert_report_unchanged(exact, files, before)
    finally:
        resume.set()
        finish(call)
    assert snapshots[0][3].released and web.FILES.count == 0


def test_never_selected_missing_source_retains_json_404(exact, monkeypatch):
    files = web.FILES.initialize(exact.job)
    before = report_before(exact, files)
    failures, captures = record_failures_and_captures(monkeypatch)
    Path(exact.job['video']).unlink()
    response = request('get', exact.url+'/edit_sample?t=0.2')
    assert response.status_code == 404 and response.json['error'] == 'missing_source'
    assert response.headers['Cache-Control'] == 'private, no-store'
    assert 'sample' not in response.json and 'image' not in response.json
    assert failures and not captures and files.current_source is None
    assert_report_unchanged(exact, files, before)
    assert web.FILES.count == 0
