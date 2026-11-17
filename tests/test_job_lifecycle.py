"""Actual-route file lifetimes; bounded schedules and synthetic stores only."""
import json
import os
from pathlib import Path
import queue
import threading
import time
from types import SimpleNamespace

import pytest

import openscrub
import openscrub_web as web
import openscrub_vault as vault
from openscrub_internal import reports


@pytest.fixture
def store(tmp_path, monkeypatch):
    root = tmp_path / 'data'
    root.mkdir()
    jobs = root / 'jobs'
    jobs.mkdir()
    monkeypatch.setattr(web, '_data_root', lambda: str(root))
    monkeypatch.setattr(web, 'JOBS_DIR', str(jobs))
    monkeypatch.setattr(web, 'JOBS', {})
    monkeypatch.setattr(web, 'WORK_Q', queue.Queue())
    monkeypatch.setattr(web, 'WORKER', {'current': None, 'thread': None})
    monkeypatch.setattr(web, 'VAULT', {'key': None})
    # A fresh ownership domain isolates every route schedule, once implemented.
    if hasattr(web, 'FILES'):
        monkeypatch.setattr(web, 'FILES', type(web.FILES)(web.VAULT_LOCK))
    monkeypatch.setattr(web, 'TOKEN', None)
    monkeypatch.setitem(web.app.config, 'TESTING', False)
    monkeypatch.setitem(web.app.config, 'PROPAGATE_EXCEPTIONS', False)
    job = web.new_job('', {}, 'synthetic.avi')
    video = Path(job['dir']) / 'input.avi'
    video.write_bytes(b'synthetic video')
    job.update(video=str(video), phase='review')
    doc = {'provenance': {'input': str(video), 'settings': {}},
           'render_state': {'fps': 30, 'cum': [[0, 0]] * 30},
           'detections': [dict(t_start=0, t_end=1, cbox=[1, 2, 8, 9],
                              category='name', text='synthetic', confidence=.9,
                              aoff=[0, 0], last_seen=.5, enabled=True)],
           'custom': {'preserved': True}}
    path = Path(job['dir']) / 'report.json'
    path.write_text(json.dumps(doc))
    def enable():
        key = vault.create_keystore(str(root), 'synthetic-password')
        web.VAULT['key'] = key
        return key
    result = SimpleNamespace(root=root, jobs=jobs, job=job, path=path,
                             doc=doc, enable=enable,
                             url='/api/jobs/' + job['id'])
    yield result
    if hasattr(web, 'FILES'):
        assert web.FILES.count == 0, 'file ownership leaked'


def request(method, url, **kwargs):
    with web.app.test_client() as client:
        response = getattr(client, method)(url, **kwargs)
        response.get_data()
        response.close()
        return response


def start_call(method, url, **kwargs):
    done, errors, values = threading.Event(), [], []
    def run():
        try:
            values.append(request(method, url, **kwargs))
        except BaseException as error:
            errors.append(error)
        finally:
            done.set()
    thread = threading.Thread(target=run)
    thread.start()
    return thread, done, errors, values


def finish(call):
    thread, done, errors, values = call
    thread.join(8)
    assert not thread.is_alive(), 'route did not finish'
    assert not errors, errors
    return values[0]


def test_save_stage_owns_files_until_publish_and_vault_reopen(store, monkeypatch):
    store.enable()
    staged, release = threading.Event(), threading.Event()
    real_replace = reports.os.replace
    def replace(source, target):
        if Path(source).name.startswith('.report-'):
            staged.set()
            assert release.wait(8)
        return real_replace(source, target)
    monkeypatch.setattr(reports.os, 'replace', replace)
    call = start_call('post', store.url + '/detections', json={'enabled': {'0': False}})
    try:
        assert staged.wait(5)
        assert request('post', '/api/vault/lock').status_code == 409
        assert list(store.path.parent.glob('.report-*.tmp'))
        assert request('delete', store.url).status_code == 409
        # Ordinary work on another job must not wait for this report's I/O.
        assert request('get', '/api/jobs').status_code == 200
    finally:
        release.set()
        response = finish(call)
    assert response.status_code == 200
    committed = store.path.read_bytes()
    assert json.loads(committed)['detections'][0]['enabled'] is False
    assert request('post', '/api/vault/lock').status_code == 200
    assert not store.path.exists()
    assert request('post', store.url + '/detections', json={}).status_code == 423
    assert request('post', '/api/vault/unlock', json={'password': 'synthetic-password'}).status_code == 200
    assert store.path.read_bytes() == committed


def test_tracking_owner_outlives_cancelled_phase_and_cleanup(store, monkeypatch):
    store.enable()
    entered, release, exited = threading.Event(), threading.Event(), threading.Event()
    def compute(*args, **kwargs):
        entered.set()
        assert release.wait(8)
        raise RuntimeError('synthetic compute failure')
    monkeypatch.setattr(openscrub, 'PersonDetector', lambda *a, **k: None)
    monkeypatch.setattr(openscrub, 'track_manual_region', compute)
    real_thread = threading.Thread
    threads = []
    def thread(*args, **kwargs):
        t = real_thread(*args, **kwargs)
        threads.append(t)
        return t
    monkeypatch.setattr(web.threading, 'Thread', thread)
    try:
        assert request('post', store.url + '/track_object', json={'box': [0,0,8,8], 't_ref': 0, 't0': 0, 't1': 1}).status_code == 200
        assert entered.wait(5)
        store.job['phase'] = 'cancelled'
        assert request('post', '/api/vault/lock').status_code == 409
        assert request('delete', store.url).status_code == 409
        old = time.time() - 3 * 86400
        os.utime(store.job['dir'], (old, old))
        web.retention_sweep(1)
        assert store.path.exists() and store.job['id'] in web.JOBS
    finally:
        release.set()
        for t in threads:
            t.join(8)
            assert not t.is_alive()
    assert store.job['trackbg']['state'] == 'done'
    assert request('delete', store.url).status_code == 200
    assert not store.path.exists()


def test_streamed_response_keeps_delete_and_lock_busy(store):
    store.enable()
    payload = bytes(range(256)) * 1024
    output = Path(store.job['dir']) / 'output.mp4'
    output.write_bytes(payload)
    store.job.update(output=str(output), phase='done')
    client = web.app.test_client()
    response = client.get(store.url + '/download', headers={'Range': 'bytes=3-65538'}, buffered=False)
    try:
        assert response.status_code == 206
        assert response.headers['Content-Length'] == '65536'
        assert response.headers['Content-Range'] == 'bytes 3-65538/262144'
        assert request('delete', store.url).status_code == 409
        assert request('post', '/api/vault/lock').status_code == 409
        assert response.get_data() == payload[3:65539]
    finally:
        response.close()
        response.close()
    assert request('delete', store.url).status_code == 200


def test_failed_encrypt_keeps_admissions_closed_until_explicit_recovery(store, monkeypatch):
    store.enable()
    real_encrypt = vault.encrypt_tree
    def fail(key, root):
        # Real partial transform before the injected failure.
        vault.encrypt_file(key, str(store.path))
        raise OSError('synthetic failure with sensitive path')
    monkeypatch.setattr(vault, 'encrypt_tree', fail)
    assert request('post', '/api/vault/lock').status_code == 500
    assert request('post', store.url + '/detections', json={}).status_code == 423
    status = request('get', '/api/vault').get_json()
    assert status['locked'] is True
    monkeypatch.setattr(vault, 'encrypt_tree', real_encrypt)
    assert request('post', '/api/vault/unlock', json={'password': 'synthetic-password'}).status_code == 200
    assert request('post', store.url + '/detections', json={}).status_code == 200


@pytest.mark.parametrize("held", ["VAULT_LOCK", "JOBS_LOCK"])
def test_shutdown_hook_does_not_reacquire_held_lifecycle_mutex(store, capsys, held):
    store.enable()
    done = threading.Event()
    def signal_context():
        with getattr(web, held):
            web._vault_lock_atexit()
        done.set()
    t = threading.Thread(target=signal_context, daemon=True)
    t.start()
    assert done.wait(2), 'shutdown hook self-deadlocked on ' + held
    t.join(2)
    assert store.path.exists() and web.VAULT['key'] is not None
    assert 'NOT locking' in capsys.readouterr().out


def test_intake_owns_new_job_after_cancel_and_before_upload_finishes(store, monkeypatch):
    import io
    from werkzeug.datastructures import FileStorage
    entered, release = threading.Event(), threading.Event()
    real_save = FileStorage.save
    created = []
    def save(upload, destination, *args, **kwargs):
        created.append(next(j for j in web.JOBS.values() if j is not store.job))
        entered.set()
        assert release.wait(8)
        return real_save(upload, destination, *args, **kwargs)
    monkeypatch.setattr(FileStorage, 'save', save)
    call = start_call('post', '/api/jobs', data={'video': (io.BytesIO(b'synthetic intake'), 'intake.avi')})
    try:
        assert entered.wait(5)
        job = created[0]
        url = '/api/jobs/' + job['id']
        assert request('post', url + '/cancel').status_code == 200
        assert request('delete', url).status_code == 409
        assert request('post', url + '/retry').status_code == 409
        assert request('post', url + '/render').status_code == 409
        assert request('post', '/api/vault/setup', json={'password': 'synthetic-password'}).status_code == 409
    finally:
        release.set()
        assert finish(call).status_code == 200
        # Finish/skip every queued ticket with the real worker.
        web.WORK_Q.put(None)
        thread = threading.Thread(target=web.worker)
        thread.start()
        thread.join(8)
        assert not thread.is_alive()
    assert request('delete', url).status_code == 200


def test_cancel_between_render_admission_and_queue_put_cannot_replace_retry(store, monkeypatch):
    store.enable()
    before_put, release = threading.Event(), threading.Event()
    real_put = web.WORK_Q.put
    real_enqueue = web.enqueue
    def enqueue(job, action, *args, **kwargs):
        if action == 'render':
            before_put.set()
            assert release.wait(8)
        return real_enqueue(job, action, *args, **kwargs)
    monkeypatch.setattr(web, 'enqueue', enqueue)
    call = start_call('post', store.url + '/render')
    try:
        assert before_put.wait(5)
        assert request('post', store.url + '/cancel').status_code == 200
        assert request('post', store.url + '/retry').status_code == 200
    finally:
        release.set()
        assert finish(call).status_code == 200
    ran = []
    def build(job, for_render=False):
        ran.append(for_render)
        raise RuntimeError('stop at computation boundary')
    monkeypatch.setattr(web, 'build_args', build)
    real_put(None)
    thread = threading.Thread(target=web.worker)
    thread.start()
    thread.join(8)
    assert not thread.is_alive()
    assert ran == [False], 'obsolete render ticket replaced/executed instead of the retry scan'
    assert web.FILES.count == 0


class ObservedLock:
    """Real locking with an event proving a selected thread tried admission."""
    def __init__(self, lock, name):
        self.lock, self.name = lock, name
        self.attempted = threading.Event()
    def acquire(self, *args, **kwargs):
        if threading.current_thread().name == self.name:
            self.attempted.set()
        return self.lock.acquire(*args, **kwargs)
    def release(self):
        return self.lock.release()
    def __enter__(self):
        self.acquire()
        return self
    def __exit__(self, *args):
        self.release()


def test_waiting_and_previously_captured_requests_recheck_after_encryption(store, monkeypatch):
    store.enable()
    entered, release = threading.Event(), threading.Event()
    real_encrypt = vault.encrypt_tree
    def encrypt(*args):
        entered.set()
        assert release.wait(8)
        return real_encrypt(*args)
    monkeypatch.setattr(vault, 'encrypt_tree', encrypt)
    guard = ObservedLock(web.VAULT_LOCK, 'late-save')
    monkeypatch.setattr(web, 'VAULT_LOCK', guard)
    web.FILES.guard = guard
    locking = start_call('post', '/api/vault/lock')
    waiting, result, errors = [], [], []
    try:
        assert entered.wait(5)
        assert web.vault_locked() is True
        def late_save():
            result.append(request('post', store.url + '/detections', json={'enabled': {'0': False}}))
        thread = threading.Thread(target=late_save, name='late-save')
        thread.start()
        waiting.append(thread)
        assert guard.attempted.wait(5)
        captured = store.job
        def old_capture():
            try:
                with web._own_files(captured):
                    errors.append('admitted stale capture')
            except Exception as error:
                errors.append(error)
        thread = threading.Thread(target=old_capture)
        thread.start()
        waiting.append(thread)
        assert not list(store.path.parent.glob('.report-*.tmp'))
    finally:
        release.set()
        assert finish(locking).status_code == 200
        for thread in waiting:
            thread.join(8)
            assert not thread.is_alive()
    assert result[0].status_code == 423
    assert len(errors) == 1 and getattr(errors[0], 'code', None) == 423
    assert not store.path.exists()
    assert request('post', '/api/jobs', data={'server_path': store.job['video']}).status_code == 423
    assert request('post', store.url + '/render').status_code == 423
    assert request('post', store.url + '/track_object', json={}).status_code == 423


@pytest.mark.parametrize('pause', ['decrypt', 'rehydrate'])
def test_unlock_does_not_admit_mutation_until_decryption_and_registration_finish(store, monkeypatch, pause):
    store.enable()
    assert request('post', '/api/vault/lock').status_code == 200
    web.JOBS.clear()
    reportless = store.jobs / 'reportless'
    reportless.mkdir()
    (reportless / 'input.avi').write_bytes(b'synthetic reportless video')
    entered, release = threading.Event(), threading.Event()
    target = vault if pause == 'decrypt' else web
    name = 'decrypt_tree' if pause == 'decrypt' else '_rehydrate_jobs'
    real = getattr(target, name)
    def transition(*args):
        entered.set()
        assert release.wait(8)
        return real(*args)
    monkeypatch.setattr(target, name, transition)
    guard = ObservedLock(web.VAULT_LOCK, 'waiting-save')
    monkeypatch.setattr(web, 'VAULT_LOCK', guard)
    web.FILES.guard = guard
    unlocking = start_call('post', '/api/vault/unlock', json={'password': 'synthetic-password'})
    values = []
    def save():
        values.append(request('post', store.url + '/detections', json={}))
    thread = threading.Thread(target=save, name='waiting-save')
    try:
        assert entered.wait(5)
        assert web.VAULT['key'] is None and web.vault_locked()
        thread.start()
        assert guard.attempted.wait(5)
        assert not values
    finally:
        release.set()
        assert finish(unlocking).status_code == 200
        thread.join(8)
        assert not thread.is_alive()
    assert values[0].status_code == 200
    assert web.JOBS[store.job['id']]['_files'].count == 0
    assert web.JOBS['reportless']['_files'].count == 0
    assert web.JOBS['reportless']['phase'] == 'error'
    assert request('delete', '/api/jobs/reportless').status_code == 200


def test_failed_decryption_stays_closed_then_recovers(store, monkeypatch):
    store.enable()
    assert request('post', '/api/vault/lock').status_code == 200
    real = vault.decrypt_tree
    def fail(key, root):
        vault.decrypt_file(key, str(store.path) + '.enc')
        raise OSError('synthetic decrypt failure')
    monkeypatch.setattr(vault, 'decrypt_tree', fail)
    assert request('post', '/api/vault/unlock', json={'password': 'synthetic-password'}).status_code == 500
    assert web.VAULT['key'] is None
    assert request('post', store.url + '/detections', json={}).status_code == 423
    state = request('get', '/api/vault').get_json()
    assert state['locked'] and state['error'] and str(store.root) not in state['error']
    monkeypatch.setattr(vault, 'decrypt_tree', real)
    assert request('post', '/api/vault/unlock', json={'password': 'synthetic-password'}).status_code == 200
    assert request('post', store.url + '/detections', json={}).status_code == 200


def test_worker_pickup_cancel_and_cleanup_share_ticket_lifetime(store, monkeypatch):
    store.enable()
    entered, release = threading.Event(), threading.Event()
    def compute(args, cb):
        entered.set()
        assert release.wait(8)
        raise openscrub.PipelineCancelled()
    monkeypatch.setattr(openscrub, 'run_scan', compute)
    monkeypatch.setattr(openscrub, 'PersonDetector', lambda *a, **k: None)
    monkeypatch.setattr(openscrub, 'track_manual_region', lambda *a, **k: [])
    store.job['phase'] = 'error'
    assert request('post', store.url + '/retry').status_code == 200
    assert request('post', '/api/vault/lock').status_code == 409
    web.WORK_Q.put(None)
    thread = threading.Thread(target=web.worker)
    thread.start()
    try:
        assert entered.wait(5)
        assert request('post', store.url + '/cancel').status_code == 200
        assert store.job['cancel'].is_set()
        # Even a prematurely terminal public phase cannot release resources.
        store.job['phase'] = 'cancelled'
        assert request('post', store.url + '/retry').status_code == 409
        assert request('post', store.url + '/render').status_code == 409
        assert request('post', store.url + '/track_object', json={'box':[0,0,8,8], 't_ref':0, 't0':0, 't1':1}).status_code == 409
        assert store.job['cancel'].is_set()
        assert request('delete', store.url).status_code == 409
        assert request('post', '/api/vault/lock').status_code == 409
    finally:
        release.set()
        thread.join(8)
        assert not thread.is_alive()
    assert web.FILES.count == 0
    assert request('post', '/api/vault/lock').status_code == 200


@pytest.mark.parametrize('which', ['tracking', 'thumbnail'])
def test_background_start_failure_releases_reservation_once(store, monkeypatch, which):
    def fail(*args, **kwargs):
        raise RuntimeError('synthetic thread start failure')
    monkeypatch.setattr(web.threading.Thread, 'start', fail)
    if which == 'tracking':
        response = request('post', store.url + '/track_object', json={'box': [0,0,8,8], 't_ref': 0, 't0': 0, 't1': 1})
        assert response.status_code == 500
        assert store.job['trackbg']['state'] == 'done'
    else:
        state = dict(fps=30, cum=[[0,0]], bands=[[0,0]], detections=[], stats={})
        monkeypatch.setattr(openscrub, 'run_scan', lambda *a: state)
        store.job['phase'] = 'queued'
        web.enqueue(store.job, 'scan')
        web.WORK_Q.put(None)
        web.worker()
        assert store.job['phase'] == 'error'
        assert 'thread start failure' in store.job['error']
    assert web.FILES.count == 0
    assert request('delete', store.url).status_code == 200


def test_thumbnail_decoder_cleanup_remains_owned_after_review_phase(store, monkeypatch, capsys):
    import numpy as np
    store.enable()
    cleaning, release = threading.Event(), threading.Event()
    class Decoder:
        def read(self):
            return True, np.zeros((48, 48, 3), dtype=np.uint8)
        def set(self, *args):
            pass
        def release(self):
            cleaning.set()
            assert release.wait(8)
    monkeypatch.setattr(web.cv2, 'VideoCapture', lambda *a: Decoder())
    det = openscrub.Detection(t_start=0, t_end=1, cbox=(1,2,8,9),
                             category='name', text='synthetic', confidence=.9,
                             aoff=(0,0), last_seen=0)
    state = dict(fps=30, cum=[[0,0]], bands=[[0,0]], detections=[det], stats={})
    monkeypatch.setattr(openscrub, 'run_scan', lambda *a: state)
    threads = []
    real_start = web._start_owned_thread
    def start(*args):
        thread = real_start(*args)
        threads.append(thread)
        return thread
    monkeypatch.setattr(web, '_start_owned_thread', start)
    web.enqueue(store.job, 'scan')
    web.WORK_Q.put(None)
    worker = threading.Thread(target=web.worker)
    worker.start()
    try:
        assert cleaning.wait(5)
        worker.join(5)
        assert not worker.is_alive() and store.job['phase'] == 'review'
        assert request('post', '/api/vault/lock').status_code == 409
        assert request('delete', store.url).status_code == 409
        web._vault_lock_atexit()
        assert 'NOT locking' in capsys.readouterr().out
        with pytest.raises(web.FilesBusy):
            web._vault_lock_now()  # exact single-step auto-lock decision
        old = time.time() - 3 * 86400
        os.utime(store.job['dir'], (old, old))
        web.retention_sweep(1)
        assert store.path.exists()
    finally:
        release.set()
        worker.join(8)
        for thread in threads:
            thread.join(8)
            assert not thread.is_alive()
    web.retention_sweep(1)
    assert not store.path.exists() and store.job['id'] not in web.JOBS
    with pytest.raises(Exception) as stale:
        web._own_files(store.job)
    assert stale.value.code == 404


def test_first_reap_failure_marker_retry_and_fresh_rehydration(store, monkeypatch):
    first, retry, release = threading.Event(), threading.Event(), threading.Event()
    real_reap, real_sleep = web._reap_job_dir, time.sleep
    attempts, threads = [], []
    real_thread = threading.Thread
    def reap(*args, **kwargs):
        attempts.append(args[0])
        if len(attempts) == 1:
            return False
        return real_reap(*args, **kwargs)
    def sleep(seconds):
        if seconds == 30:
            retry.set()
            assert release.wait(8)
        else:
            real_sleep(seconds)
    def start(*args, **kwargs):
        t = real_thread(*args, **kwargs)
        threads.append(t)
        return t
    monkeypatch.setattr(web, '_reap_job_dir', reap)
    monkeypatch.setattr(web.time, 'sleep', sleep)
    monkeypatch.setattr(web.threading, 'Thread', start)
    try:
        response = request('delete', store.url)
        assert response.status_code == 200 and response.get_json()['pending']
        assert retry.wait(5)
        assert (store.path.parent / web.DELETE_MARKER).exists()
        assert store.job['id'] not in web.JOBS
        with pytest.raises(Exception) as stale:
            web._own_files(store.job)
        assert stale.value.code == 404
        # Startup/unlock registration reaps a condemned folder instead of reviving it.
        web.rehydrate_jobs()
        assert store.job['id'] not in web.JOBS and not store.path.exists()
    finally:
        release.set()
        for thread in threads:
            thread.join(8)
            assert not thread.is_alive()
    assert web.FILES.count == 0


@pytest.mark.parametrize('endpoint', ['mediainfo', 'frame_at', 'detframe/0', 'thumb/0'])
def test_web_decoder_exception_closes_handle_before_owner_release(store, monkeypatch, endpoint):
    handles = []
    class Decoder:
        def __init__(self):
            self.closed = False
            handles.append(self)
        def get(self, *args):
            raise OSError('synthetic property read failure')
        def set(self, *args):
            pass
        def read(self):
            raise OSError('synthetic decode failure')
        def release(self):
            assert web.FILES.count > 0
            assert web.VAULT_LOCK.acquire(blocking=False), 'cleanup held global guard'
            web.VAULT_LOCK.release()
            self.closed = True
    monkeypatch.setattr(web.cv2, 'VideoCapture', lambda *a: Decoder())
    assert request('get', store.url + '/' + endpoint).status_code == 500
    assert handles and all(handle.closed for handle in handles)
    assert web.FILES.count == 0


def test_tracking_receives_prompt_cancel_signal_through_existing_callback(store, monkeypatch):
    entered, checked = threading.Event(), threading.Event()
    observed, threads = [], []
    def compute(*args, **kwargs):
        entered.set()
        assert store.job['cancel'].wait(8)
        observed.append(kwargs['cb'].cancelled())
        checked.set()
        return []
    monkeypatch.setattr(openscrub, 'PersonDetector', lambda *a, **k: None)
    monkeypatch.setattr(openscrub, 'track_manual_region', compute)
    real_start = web._start_owned_thread
    def start(*args):
        thread = real_start(*args)
        threads.append(thread)
        return thread
    monkeypatch.setattr(web, '_start_owned_thread', start)
    try:
        assert request('post', store.url + '/track_object', json={'box':[0,0,8,8], 't_ref':0, 't0':0, 't1':1}).status_code == 200
        assert entered.wait(5)
        assert request('post', store.url + '/cancel').status_code == 200
        assert checked.wait(5)
    finally:
        store.job['cancel'].set()
        for thread in threads:
            thread.join(8)
            assert not thread.is_alive()
    assert observed == [True]


def test_queue_submission_failure_releases_reserved_work(store, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError('synthetic queue submission failure')
    monkeypatch.setattr(web.WORK_Q, 'put', fail)
    assert request('post', store.url + '/render').status_code == 500
    assert store.job['phase'] == 'error'
    assert web.FILES.count == 0
    assert request('delete', store.url).status_code == 200


def test_legacy_queue_entry_never_recursively_acquires_jobs_mutex(store, monkeypatch):
    class StrictMutex:
        def __init__(self):
            self.lock = threading.Lock()
            self.owner = None
        def __enter__(self):
            if self.owner == threading.get_ident():
                raise RuntimeError('recursive JOBS_LOCK acquire')
            self.lock.acquire()
            self.owner = threading.get_ident()
            return self
        def __exit__(self, *args):
            self.owner = None
            self.lock.release()
    monkeypatch.setattr(web, 'JOBS_LOCK', StrictMutex())
    reached = []
    def build(*args, **kwargs):
        reached.append(True)
        raise RuntimeError('synthetic computation boundary')
    monkeypatch.setattr(web, 'build_args', build)
    web.WORK_Q.put((store.job['id'], 'scan'))
    web.WORK_Q.put(None)
    web.worker()
    assert reached == [True]
    assert web.FILES.count == 0


def test_real_tracker_cancellation_releases_capture_before_background_owner(store, monkeypatch):
    import cv2
    import numpy as np
    video = store.job['video']
    writer = cv2.VideoWriter(video, cv2.VideoWriter_fourcc(*'MJPG'), 30, (48, 48))
    assert writer.isOpened()
    for i in range(15):
        writer.write(np.random.default_rng(i).integers(0, 255, (48,48,3), dtype=np.uint8))
    writer.release()
    entered, release = threading.Event(), threading.Event()
    real_capture, captures, threads = cv2.VideoCapture, [], []
    class Capture:
        def __init__(self, *args):
            self.real = real_capture(*args)
            self.releases = 0
            captures.append(self)
        def __getattr__(self, name):
            return getattr(self.real, name)
        def release(self):
            assert web.FILES.count > 0, 'decoder closed after lifetime ended'
            self.releases += 1
            self.real.release()
    class Vit:
        def init(self, *args):
            pass
    def factory(log):
        entered.set()
        assert release.wait(8)
        return Vit
    monkeypatch.setattr(openscrub.cv2, 'VideoCapture', Capture)
    monkeypatch.setattr(openscrub, '_vittrack_factory', factory)
    monkeypatch.setattr(openscrub, 'PersonDetector', lambda *a, **k: None)
    real_start = web._start_owned_thread
    def start(*args):
        thread = real_start(*args)
        threads.append(thread)
        return thread
    monkeypatch.setattr(web, '_start_owned_thread', start)
    try:
        assert request('post', store.url + '/track_object', json={'box':[4,4,40,40], 't_ref':.1, 't0':0, 't1':.4}).status_code == 200
        assert entered.wait(5)
        assert request('post', store.url + '/cancel').status_code == 200
    finally:
        release.set()
        for thread in threads:
            thread.join(8)
            assert not thread.is_alive()
    try:
        assert captures and all(c.releases == 1 and not c.isOpened() for c in captures)
    finally:
        for capture in captures:
            capture.real.release()  # diagnostic retained references must not leak on RED


def test_tracker_failed_open_explicitly_releases_capture(store, monkeypatch):
    import cv2
    real_capture, captures = cv2.VideoCapture, []
    class Capture:
        def __init__(self, *args):
            self.real = real_capture(*args)
            self.releases = 0
            captures.append(self)
        def __getattr__(self, name):
            return getattr(self.real, name)
        def release(self):
            self.releases += 1
            self.real.release()
    monkeypatch.setattr(openscrub.cv2, 'VideoCapture', Capture)
    assert openscrub.track_manual_region(store.job['video'], (4,4,40,40), 0, 0, 1) == []
    assert len(captures) == 1 and captures[0].releases == 1


def test_single_tracker_reservation_outlives_terminal_status_until_cleanup(store, monkeypatch):
    cleaning, release, threads = threading.Event(), threading.Event(), []
    monkeypatch.setattr(openscrub, 'PersonDetector', lambda *a, **k: None)
    monkeypatch.setattr(openscrub, 'track_manual_region', lambda *a, **k: [])
    real_start = web._start_owned_thread
    def start(target, lease):
        real_release = lease.release
        def cleanup():
            cleaning.set()
            assert release.wait(8)
            real_release()
        lease.release = cleanup
        thread = real_start(target, lease)
        threads.append(thread)
        return thread
    monkeypatch.setattr(web, '_start_owned_thread', start)
    payload = {'box':[0,0,8,8], 't_ref':0, 't0':0, 't1':1}
    try:
        assert request('post', store.url + '/track_object', json=payload).status_code == 200
        assert cleaning.wait(5)
        assert request('get', store.url + '/track_status').get_json()['state'] == 'done'
        assert request('post', store.url + '/track_object', json=payload).status_code == 409
    finally:
        release.set()
        for thread in threads:
            thread.join(8)
            assert not thread.is_alive()
    assert web.FILES.count == 0


def test_next_tracker_gets_fresh_event_only_after_cancelled_owner_cleanup(store, monkeypatch):
    entered, observed, threads = threading.Event(), [], []
    def compute(*args, **kwargs):
        if not observed:
            entered.set()
            assert store.job['cancel'].wait(8)
        observed.append(kwargs['cb'].cancelled())
        return []
    monkeypatch.setattr(openscrub, 'PersonDetector', lambda *a, **k: None)
    monkeypatch.setattr(openscrub, 'track_manual_region', compute)
    real_start = web._start_owned_thread
    def start(*args):
        thread = real_start(*args)
        threads.append(thread)
        return thread
    monkeypatch.setattr(web, '_start_owned_thread', start)
    payload = {'box':[0,0,8,8], 't_ref':0, 't0':0, 't1':1}
    try:
        assert request('post', store.url + '/track_object', json=payload).status_code == 200
        assert entered.wait(5)
        assert request('post', store.url + '/cancel').status_code == 200
        threads[0].join(8)
        assert not threads[0].is_alive()
        assert request('post', store.url + '/track_object', json=payload).status_code == 200
        threads[-1].join(8)
        assert not threads[-1].is_alive()
    finally:
        store.job['cancel'].set()
        for thread in threads:
            thread.join(8)
            assert not thread.is_alive()
    assert observed == [True, False]


@pytest.mark.parametrize('alias', [False, True])
def test_server_preview_job_path_and_symlink_hold_stream_ownership(store, alias):
    store.enable()
    path = Path(store.job['video'])
    if alias:
        path = store.root / 'source-alias.avi'
        path.symlink_to(store.job['video'])
    client = web.app.test_client()
    response = client.get('/api/server_video', query_string={'path': str(path)}, buffered=False)
    try:
        assert response.status_code == 200
        assert request('delete', store.url).status_code == 409
        assert request('post', '/api/vault/lock').status_code == 409
        assert response.get_data() == b'synthetic video'
    finally:
        response.close()
    assert request('post', '/api/vault/lock').status_code == 200
    assert client.get('/api/server_video', query_string={'path': str(path)}).status_code == 423


@pytest.mark.parametrize('alias', [False, True])
def test_waveform_job_path_owns_canonical_source_until_compute_finishes(store, monkeypatch, alias):
    import subprocess
    store.enable()
    path = Path(store.job['video'])
    if alias:
        path = store.root / 'audio-source-alias.avi'
        path.symlink_to(store.job['video'])
    entered, release, sources = threading.Event(), threading.Event(), []
    def compute(argv, **kwargs):
        sources.append(argv[argv.index('-i') + 1])
        entered.set()
        assert release.wait(8)
        return SimpleNamespace(stdout=b'\x00\x00\x01\x00')
    monkeypatch.setattr(subprocess, 'run', compute)
    call = start_call('get', '/api/waveform', query_string={'path': str(path)})
    try:
        assert entered.wait(5)
        assert request('delete', store.url).status_code == 409
        assert request('post', '/api/vault/lock').status_code == 409
    finally:
        release.set()
        assert finish(call).status_code == 200
    assert sources == [store.job['video']]
    assert request('post', '/api/vault/lock').status_code == 200
    assert request('get', '/api/waveform', query_string={'path': str(path)}).status_code == 423


@pytest.mark.parametrize('alias', [False, True])
def test_intake_source_job_remains_owned_through_queue_and_cancelled_worker(store, monkeypatch, alias):
    source = Path(store.job['video'])
    if alias:
        source = store.root / 'intake-alias.avi'
        source.symlink_to(store.job['video'])
    response = request('post', '/api/jobs', data={'server_path': str(source)})
    assert response.status_code == 200
    jid = response.get_json()['jobs'][0]
    url = '/api/jobs/' + jid
    entered, release = threading.Event(), threading.Event()
    def compute(args, cb):
        assert args.video == store.job['video']
        entered.set()
        assert release.wait(8)
        raise openscrub.PipelineCancelled()
    monkeypatch.setattr(openscrub, 'run_scan', compute)
    thread = None
    try:
        assert request('delete', store.url).status_code == 409
        web.WORK_Q.put(None)
        thread = threading.Thread(target=web.worker)
        thread.start()
        assert entered.wait(5)
        old = time.time() - 3 * 86400
        os.utime(store.job['dir'], (old, old))
        web.retention_sweep(1)
        assert store.path.exists() and store.job['id'] in web.JOBS
        assert request('post', url + '/cancel').status_code == 200
        assert request('delete', store.url).status_code == 409
    finally:
        release.set()
        if thread is None:
            request('post', url + '/cancel')
            web.WORK_Q.put(None)
            web.worker()
        else:
            thread.join(8)
            assert not thread.is_alive()
    assert request('delete', store.url).status_code == 200
    assert request('delete', url).status_code == 200


def test_allowed_external_sources_keep_existing_preview_and_waveform_behavior(store, monkeypatch):
    import subprocess
    store.enable()
    external = store.root / 'external.avi'
    external.write_bytes(b'external synthetic video')
    assert request('post', '/api/vault/lock').status_code == 200
    response = request('get', '/api/server_video', query_string={'path': str(external)})
    assert response.status_code == 200 and response.data == external.read_bytes()
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: SimpleNamespace(stdout=b'\0\0\1\0'))
    response = request('get', '/api/waveform', query_string={'path': str(external)})
    assert response.status_code == 200 and response.get_json()['peaks']
    monkeypatch.setenv('OPENSCRUB_MEDIA_ROOT', str(store.jobs))
    assert request('get', '/api/server_video', query_string={'path': str(external)}).status_code == 400


def test_failed_setup_remains_closed_until_explicit_setup_recovery(store, monkeypatch):
    real = vault.create_keystore
    def fail(*args):
        raise OSError('synthetic setup failure')
    monkeypatch.setattr(vault, 'create_keystore', fail)
    assert request('post', '/api/vault/setup', json={'password': 'synthetic-password'}).status_code == 500
    assert request('post', store.url + '/detections', json={}).status_code == 423
    monkeypatch.setattr(vault, 'create_keystore', real)
    assert request('post', '/api/vault/setup', json={'password': 'synthetic-password'}).status_code == 200
    assert request('post', store.url + '/detections', json={}).status_code == 200


def test_failed_rehydration_keeps_unlock_closed_until_explicit_recovery(store, monkeypatch):
    store.enable()
    assert request('post', '/api/vault/lock').status_code == 200
    real = web._rehydrate_jobs
    def fail():
        real()
        raise OSError('synthetic registration failure')
    monkeypatch.setattr(web, '_rehydrate_jobs', fail)
    assert request('post', '/api/vault/unlock', json={'password': 'synthetic-password'}).status_code == 500
    assert request('post', store.url + '/detections', json={}).status_code == 423
    monkeypatch.setattr(web, '_rehydrate_jobs', real)
    assert request('post', '/api/vault/unlock', json={'password': 'synthetic-password'}).status_code == 200
    assert request('post', store.url + '/detections', json={}).status_code == 200


def test_media_uses_admitted_source_snapshot_when_live_job_source_changes(store, monkeypatch):
    response = request('post', '/api/jobs', data={'server_path': store.job['video']})
    jid = response.get_json()['jobs'][0]
    url = '/api/jobs/' + jid
    assert request('post', url + '/cancel').status_code == 200
    web.WORK_Q.put(None)
    web.worker()  # drain the cancelled queue ticket before the read schedule
    other = web.new_job('', {}, 'other.avi')
    other_video = Path(other['dir']) / 'input.avi'
    other_video.write_bytes(b'new source must not be followed')
    other.update(phase='review', video=str(other_video))
    entered, release = threading.Event(), threading.Event()
    real_view = web.app.view_functions['job_video_stream']
    def view(jid):
        entered.set()
        assert release.wait(8)
        return real_view(jid)
    monkeypatch.setitem(web.app.view_functions, 'job_video_stream', view)
    call = start_call('get', url + '/video')
    try:
        assert entered.wait(5)
        web.JOBS[jid]['video'] = str(other_video)
        assert request('delete', store.url).status_code == 409
        assert request('delete', '/api/jobs/' + other['id']).status_code == 200
    finally:
        release.set()
        response = finish(call)
    assert response.status_code == 200 and response.data == b'synthetic video'
    assert request('delete', url).status_code == 200


def test_idle_source_reference_does_not_pin_retention_or_hide_job_status(store):
    response = request('post', '/api/jobs', data={'server_path': store.job['video']})
    jid = response.get_json()['jobs'][0]
    url = '/api/jobs/' + jid
    assert request('post', url + '/cancel').status_code == 200
    web.WORK_Q.put(None)
    web.worker()
    assert request('delete', store.url).status_code == 200
    assert request('get', url).status_code == 200
    assert request('get', url + '/log').status_code == 200
    assert request('get', url + '/video').status_code == 404
    assert request('delete', url).status_code == 200
