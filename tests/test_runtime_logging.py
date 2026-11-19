"""Privacy and lifecycle checks for opt-in service diagnostics."""
import importlib.util
import json


def test_opt_in_records_sanitized_lifecycle(tmp_path):
    spec = importlib.util.find_spec('openscrub_internal.diagnostics')
    assert spec is not None, 'private diagnostics module must be distributed'
    from openscrub_internal import diagnostics
    sink = diagnostics.Diagnostics(tmp_path, 'http', '1.0.0')
    action = sink.start('scan')
    sink.progress(action, 'scan', 3, 10)
    sink.finish(action, 'review')
    sink.close('normal', 'not_enabled')
    records = [json.loads(line) for line in (tmp_path / 'runtime.jsonl').read_bytes().splitlines()]
    assert [record['kind'] for record in records] == [
        'service_started', 'job_started', 'job_stage', 'job_finished', 'service_stop']
    assert records[1]['action_ref'] == records[3]['action_ref']
    assert not (tmp_path / 'running.json').exists()


def _records(path):
    return [json.loads(line) for line in path.read_bytes().splitlines()]


def test_schema_rejects_sensitive_and_hostile_values(tmp_path):
    from openscrub_internal import diagnostics
    class Hostile:
        def __str__(self):
            raise AssertionError('must not stringify')
    sink = diagnostics.Diagnostics(tmp_path, 'http', '1.0.0', monitor=False)
    assert not sink.emit('unknown', message='TOKEN_SENTINEL')
    assert not sink.emit('worker_restarted', active_action_lost=True, message='OCR_SENTINEL')
    assert not sink.emit('worker_restarted', active_action_lost=Hostile())
    assert not sink.emit('worker_restarted', active_action_lost=1)
    assert not sink.emit('service_stop', reason='normal', active_actions=-1, vault='not_enabled')
    assert not sink.emit('job_heartbeat', action_ref='a' * 32, stage='scan', current=1,
                         total=1, idle_seconds=float('nan'))
    sink.close('normal', 'not_enabled')
    data = (tmp_path / 'runtime.jsonl').read_bytes()
    assert b'SENTINEL' not in data
    assert all(len(line) + 1 <= 1024 for line in data.splitlines())
    assert [r['kind'] for r in _records(tmp_path / 'runtime.jsonl')] == ['service_started', 'service_stop']


def test_heartbeat_throttling_and_stale_handles(tmp_path):
    from openscrub_internal import diagnostics
    now = [0.0]
    sink = diagnostics.Diagnostics(tmp_path, 'http', '1.0.0', clock=lambda: now[0], monitor=False)
    old = sink.start('scan')
    sink.progress(old, 'scan', 1, 3)
    new = sink.start('render')
    sink.finish(old, 'superseded')
    sink.progress(old, 'post', 2, 3)
    sink.finish(old, 'error')
    sink.progress(new, 'render', 2, 9)
    for t in (1, 59, 60, 61, 119, 120):
        now[0] = t
        for _ in range(10):
            sink.heartbeat()
    sink.finish(new, 'done')
    now[0] = 1000
    sink.heartbeat()
    sink.close('normal', 'not_enabled')
    rows = _records(tmp_path / 'runtime.jsonl')
    beats = [r for r in rows if r['kind'] == 'job_heartbeat']
    assert len(beats) == 2
    assert all(r['action_ref'] == new and r['current'] == 2 and r['total'] == 9 for r in beats)
    assert [r['idle_seconds'] for r in beats] == [60, 120]
    assert [r['outcome'] for r in rows if r['kind'] == 'job_finished'] == ['superseded', 'done']


def test_rotation_and_exclusive_writer(tmp_path):
    from openscrub_internal import diagnostics
    first = diagnostics.Diagnostics(tmp_path, 'http', '1.0.0', max_file=450, monitor=False)
    marker = (tmp_path / 'running.json').read_bytes()
    second = diagnostics.Diagnostics(tmp_path, 'http', '1.0.0', max_file=450, monitor=False)
    assert second.start('scan') is None
    second.close('normal', 'not_enabled')
    assert (tmp_path / 'running.json').read_bytes() == marker
    for _ in range(15):
        first.emit('worker_restarted', active_action_lost=False)
    first.close('normal', 'not_enabled')
    files = list(tmp_path.glob('runtime.jsonl*'))
    assert {p.name for p in files} == {'runtime.jsonl', 'runtime.jsonl.1', 'runtime.jsonl.2'}
    assert all(p.stat().st_size <= 450 for p in files)
    assert all(json.loads(line)['schema'] == 1 for p in files for line in p.read_bytes().splitlines())
    third = diagnostics.Diagnostics(tmp_path, 'http', '1.0.0', monitor=False)
    assert third.start('scan') is not None
    third.close('normal', 'not_enabled')


def test_unclean_marker_validated_and_clean_close_idempotent(tmp_path):
    from openscrub_internal import diagnostics
    marker = tmp_path / 'running.json'
    marker.write_bytes(b'{"schema":1,"active":true,"stage":"scan","secret":"TOKEN_SENTINEL"}')
    sink = diagnostics.Diagnostics(tmp_path, 'https', '1.0.0', monitor=False)
    assert not any(r['kind'] == 'previous_run_unclean' for r in _records(tmp_path / 'runtime.jsonl'))
    assert marker.stat().st_size <= 1024
    sink.close('normal', 'busy')
    sink.close('normal', 'busy')
    assert not marker.exists()
    marker.write_bytes(b'{"schema":1,"active":true,"stage":"post"}')
    sink = diagnostics.Diagnostics(tmp_path, 'https', '1.0.0', monitor=False)
    sink.close('normal', 'failed')
    records = _records(tmp_path / 'runtime.jsonl')
    prior = [r for r in records if r['kind'] == 'previous_run_unclean']
    assert len(prior) == 1 and prior[0]['previous_active'] is True and prior[0]['stage'] == 'post'
    assert b'TOKEN_SENTINEL' not in (tmp_path / 'runtime.jsonl').read_bytes()


def test_storage_failure_preserves_marker_and_never_escapes(tmp_path, monkeypatch):
    from openscrub_internal import diagnostics
    sink = diagnostics.Diagnostics(tmp_path, 'http', '1.0.0', monitor=False)
    def fail(*args, **kwargs):
        raise OSError('sensitive path')
    monkeypatch.setattr(sink, '_marker', fail)
    assert sink.start('scan') is None
    sink.progress(None, 'scan', 1, 1)
    sink.heartbeat()
    sink.close('normal', 'not_enabled')
    assert (tmp_path / 'running.json').exists()
    assert b'sensitive path' not in (tmp_path / 'runtime.jsonl').read_bytes()


def test_worker_failure_stays_alive_and_persists_only_classification(tmp_path, monkeypatch):
    import queue
    import threading
    import openscrub_web as web
    from openscrub_internal import diagnostics
    jobs = tmp_path / 'jobs'
    jobs.mkdir()
    monkeypatch.setattr(web, 'JOBS_DIR', str(jobs))
    monkeypatch.setattr(web, 'JOBS', {})
    monkeypatch.setattr(web, 'WORK_Q', queue.Queue())
    monkeypatch.setattr(web, 'WORKER', {'current': None, 'thread': None})
    monkeypatch.setattr(web, 'FILES', type(web.FILES)(web.VAULT_LOCK))
    sink = diagnostics.Diagnostics(tmp_path / 'logs', 'http', '1.0.0', monitor=False)
    monkeypatch.setattr(web, 'DIAGNOSTICS', sink)
    seen = []
    def fail(job, for_render=False):
        seen.append(job['id'])
        raise OSError(5, 'PATH_TOKEN_OCR_SENTINEL')
    monkeypatch.setattr(web, 'build_args', fail)
    for _ in range(2):
        job = web.new_job('', {}, 'synthetic.mp4')
        web.enqueue(job, 'scan')
    web.WORK_Q.put(None)
    worker = threading.Thread(target=web.worker)
    worker.start()
    worker.join(10)
    assert not worker.is_alive() and len(seen) == 2
    assert web.FILES.count == 0
    sink.close('normal', 'not_enabled')
    data = (tmp_path / 'logs' / 'runtime.jsonl').read_bytes()
    rows = [json.loads(line) for line in data.splitlines()]
    finished = [r for r in rows if r['kind'] == 'job_finished']
    assert len(finished) == 2 and all(r['outcome'] == 'error' and r['error'] == 'os_error' and r['errno'] == 5 for r in finished)
    assert all(jid.encode() not in data for jid in seen)
    assert b'PATH_TOKEN_OCR_SENTINEL' not in data


def test_no_default_diagnostics_or_logging_hook(tmp_path):
    import logging
    import openscrub_web as web
    from openscrub_internal import diagnostics
    before = list(logging.getLogger().handlers)
    assert web.DIAGNOSTICS is None
    assert list(logging.getLogger().handlers) == before
    assert not list(tmp_path.iterdir())


def test_abrupt_process_and_fresh_process_recovery(tmp_path):
    import os
    import subprocess
    import sys
    script = '''
import os, sys
from openscrub_internal.diagnostics import Diagnostics
sink = Diagnostics(sys.argv[1], "http", "1.0.0", monitor=False)
ref = sink.start("scan")
sink.progress(ref, "post", 4, 8)
os._exit(17)
'''
    child = subprocess.run([sys.executable, '-B', '-c', script, str(tmp_path)],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    assert child.returncode == 17, child.stderr
    marker = json.loads((tmp_path / 'running.json').read_text())
    assert marker == {'schema': 1, 'active': True, 'stage': 'post'}
    from openscrub_internal import diagnostics
    sink = diagnostics.Diagnostics(tmp_path, 'http', '1.0.0', monitor=False)
    sink.close('normal', 'not_enabled')
    rows = _records(tmp_path / 'runtime.jsonl')
    prior = [r for r in rows if r['kind'] == 'previous_run_unclean']
    assert len(prior) == 1 and prior[0]['previous_active'] and prior[0]['stage'] == 'post'
    assert not (tmp_path / 'running.json').exists()


def test_write_flush_rollover_and_monitor_failures_are_nonfatal(tmp_path, monkeypatch, capsys):
    from openscrub_internal import diagnostics
    class BrokenStream:
        def __init__(self, wrapped, method):
            self.wrapped, self.method = wrapped, method
        def tell(self):
            return self.wrapped.tell()
        def write(self, data):
            if self.method == 'write':
                raise OSError('sensitive write')
            return self.wrapped.write(data)
        def flush(self):
            if self.method == 'flush':
                raise OSError('sensitive flush')
            return self.wrapped.flush()
        def close(self):
            return self.wrapped.close()
    for method in ('write', 'flush'):
        path = tmp_path / method
        sink = diagnostics.Diagnostics(path, 'http', '1.0.0', monitor=False)
        sink._stream = BrokenStream(sink._stream, method)
        assert not sink.emit('worker_restarted', active_action_lost=False)
        sink.close('normal', 'not_enabled')
        assert (path / 'running.json').exists()
        assert b'sensitive' not in (path / 'runtime.jsonl').read_bytes()
    path = tmp_path / 'rotate'
    sink = diagnostics.Diagnostics(path, 'http', '1.0.0', max_file=220, monitor=False)
    def fail(*args):
        raise OSError('sensitive rotation')
    with monkeypatch.context() as context:
        context.setattr(diagnostics.os, 'replace', fail)
        assert not sink.emit('worker_restarted', active_action_lost=False)
    sink.close('normal', 'not_enabled')
    assert (path / 'running.json').exists()
    path = tmp_path / 'monitor'
    sink = diagnostics.Diagnostics(path, 'http', '1.0.0', monitor=False)
    class BrokenWait:
        def wait(self, timeout):
            raise RuntimeError('sensitive monitor')
        def set(self):
            pass
    sink._stop = BrokenWait()
    sink._monitor()
    sink.close('normal', 'not_enabled')
    assert (path / 'running.json').exists()
    assert 'sensitive' not in capsys.readouterr().out


def test_open_failure_does_not_raise(tmp_path, monkeypatch, capsys):
    from openscrub_internal import diagnostics
    def fail(*args, **kwargs):
        raise PermissionError('sensitive path')
    monkeypatch.setattr(diagnostics.Diagnostics, '_open_private', fail)
    sink = diagnostics.Diagnostics(tmp_path, 'http', '1.0.0', monitor=False)
    assert sink.start('scan') is None
    sink.close('normal', 'not_enabled')
    assert capsys.readouterr().out == '[web] diagnostics unavailable\n'


def test_cancelled_operation_and_late_callback_cannot_touch_new_action(tmp_path, monkeypatch):
    import queue
    import threading
    import openscrub
    import openscrub_web as web
    from openscrub_internal import diagnostics
    jobs = tmp_path / 'jobs'; jobs.mkdir()
    monkeypatch.setattr(web, 'JOBS_DIR', str(jobs))
    monkeypatch.setattr(web, 'JOBS', {})
    monkeypatch.setattr(web, 'WORK_Q', queue.Queue())
    monkeypatch.setattr(web, 'WORKER', {'current': None, 'thread': None})
    monkeypatch.setattr(web, 'FILES', type(web.FILES)(web.VAULT_LOCK))
    sink = diagnostics.Diagnostics(tmp_path / 'logs', 'http', '1.0.0', monitor=False)
    monkeypatch.setattr(web, 'DIAGNOSTICS', sink)
    callbacks = []
    monkeypatch.setattr(web, 'build_args', lambda *a, **k: None)
    def cancelled(args, cb):
        callbacks.append(cb)
        cb.progress('scan', 1, 5)
        raise openscrub.PipelineCancelled()
    monkeypatch.setattr(openscrub, 'run_scan', cancelled)
    job = web.new_job('', {}, 'synthetic.mp4')
    web.enqueue(job, 'scan'); web.WORK_Q.put(None)
    worker = threading.Thread(target=web.worker); worker.start(); worker.join(10)
    assert not worker.is_alive() and job['phase'] == 'cancelled'
    assert web.FILES.count == 0
    newer = sink.start('render')
    callbacks[0].progress('post', 2, 5)
    sink.progress(newer, 'render', 3, 5)
    sink.finish(newer, 'done')
    sink.close('normal', 'not_enabled')
    rows = _records(tmp_path / 'logs' / 'runtime.jsonl')
    finishes = [r for r in rows if r['kind'] == 'job_finished']
    assert [r['outcome'] for r in finishes] == ['cancelled', 'done']
    assert not any(r.get('stage') == 'post' for r in rows)
    assert [r['stage'] for r in rows if r['kind'] == 'job_stage'] == ['scan', 'render']


def test_vault_busy_and_failure_release_ownership_with_diagnostics(tmp_path, monkeypatch):
    import openscrub_web as web
    import openscrub_vault as vault
    from openscrub_internal import diagnostics
    root = tmp_path / 'app'; root.mkdir()
    jobs = root / 'jobs'; jobs.mkdir()
    monkeypatch.setattr(web, '_data_root', lambda: str(root))
    monkeypatch.setattr(web, 'JOBS_DIR', str(jobs))
    monkeypatch.setattr(web, 'JOBS', {})
    monkeypatch.setattr(web, 'FILES', type(web.FILES)(web.VAULT_LOCK))
    key = vault.create_keystore(str(root), 'synthetic-password')
    monkeypatch.setattr(web, 'VAULT', {'key': key})
    job = web.new_job('', {}, 'synthetic.mp4')
    job['phase'] = 'review'
    lease = web._own_files(job, work=True)
    try:
        busy = web._vault_lock_atexit()
        assert busy == 'busy' and web.FILES.count == 1
    finally:
        lease.release()
    assert web.FILES.count == 0
    def fail(*args):
        raise OSError('private-path-sentinel')
    monkeypatch.setattr(vault, 'encrypt_tree', fail)
    failed = web._vault_lock_atexit()
    assert failed == 'failed' and web.FILES.count == 0
    for result in (busy, failed):
        sink = diagnostics.Diagnostics(root / 'logs', 'http', '1.0.0', monitor=False)
        sink.close('normal', result)
    rows = _records(root / 'logs' / 'runtime.jsonl')
    assert [r['vault'] for r in rows if r['kind'] == 'service_stop'] == ['busy', 'failed']
    assert b'private-path-sentinel' not in (root / 'logs' / 'runtime.jsonl').read_bytes()


def test_live_process_keeps_exclusive_writer_until_exit(tmp_path):
    import subprocess
    import sys
    from openscrub_internal import diagnostics
    script = '''
import sys
from openscrub_internal.diagnostics import Diagnostics
sink = Diagnostics(sys.argv[1], 'http', '1.0.0', monitor=False)
sink.start('scan')
print('OWNER_READY', flush=True)
sys.stdin.readline()
sink.close('normal', 'not_enabled')
'''
    proc = subprocess.Popen([sys.executable, '-B', '-c', script, str(tmp_path)],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        while True:
            line = proc.stdout.readline()
            assert line, 'owner exited before ready'
            if line.strip() == 'OWNER_READY':
                break
        before = (tmp_path / 'running.json').read_bytes()
        second = diagnostics.Diagnostics(tmp_path, 'https', '1.0.0', monitor=False)
        assert second.start('render') is None
        second.close('normal', 'not_enabled')
        assert (tmp_path / 'running.json').read_bytes() == before
    finally:
        proc.stdin.write('\n'); proc.stdin.flush()
        _, err = proc.communicate(timeout=15)
        assert proc.returncode == 0, err
    assert not (tmp_path / 'running.json').exists()
    assert [r['kind'] for r in _records(tmp_path / 'runtime.jsonl')] == ['service_started', 'job_started', 'service_stop']


def test_watchdog_discards_lost_action_without_fabricating_finish(tmp_path, monkeypatch):
    import threading
    import openscrub_web as web
    from openscrub_internal import diagnostics
    jobs = tmp_path / 'jobs'; jobs.mkdir()
    monkeypatch.setattr(web, 'JOBS_DIR', str(jobs))
    monkeypatch.setattr(web, 'JOBS', {})
    monkeypatch.setattr(web, 'FILES', type(web.FILES)(web.VAULT_LOCK))
    monkeypatch.setattr(web, 'start_worker', lambda: None)
    dead = threading.Thread(target=lambda: None); dead.start(); dead.join()
    job = web.new_job('', {}, 'synthetic.mp4'); job['phase'] = 'scanning'
    monkeypatch.setattr(web, 'WORKER', {'current': job['id'], 'thread': dead})
    sink = diagnostics.Diagnostics(tmp_path / 'logs', 'http', '1.0.0', monitor=False)
    monkeypatch.setattr(web, 'DIAGNOSTICS', sink)
    lost = sink.start('scan')
    web.WORKER['diagnostic_ref'] = lost
    assert web.check_worker()
    sink.progress(lost, 'scan', 1, 10)
    assert not sink._actions
    sink.close('normal', 'not_enabled')
    rows = _records(tmp_path / 'logs' / 'runtime.jsonl')
    assert [r['active_action_lost'] for r in rows if r['kind'] == 'worker_restarted'] == [True]
    assert not any(r['kind'] in ('job_finished', 'job_stage') for r in rows)
    assert rows[-1]['active_actions'] == 0


def test_real_cancel_route_records_cancelled_after_operation_invalidation(tmp_path, monkeypatch):
    import queue
    import threading
    import openscrub
    import openscrub_web as web
    from openscrub_internal import diagnostics
    jobs = tmp_path / 'jobs'; jobs.mkdir()
    monkeypatch.setattr(web, 'JOBS_DIR', str(jobs))
    monkeypatch.setattr(web, 'JOBS', {})
    monkeypatch.setattr(web, 'WORK_Q', queue.Queue())
    monkeypatch.setattr(web, 'WORKER', {'current': None, 'thread': None})
    monkeypatch.setattr(web, 'FILES', type(web.FILES)(web.VAULT_LOCK))
    monkeypatch.setattr(web, 'TOKEN', None)
    sink = diagnostics.Diagnostics(tmp_path / 'logs', 'http', '1.0.0', monitor=False)
    monkeypatch.setattr(web, 'DIAGNOSTICS', sink)
    entered, release = threading.Event(), threading.Event()
    monkeypatch.setattr(web, 'build_args', lambda *args, **kwargs: None)
    def scanning(args, cb):
        entered.set()
        assert release.wait(10)
        assert cb.cancelled()
        raise openscrub.PipelineCancelled()
    monkeypatch.setattr(openscrub, 'run_scan', scanning)
    job = web.new_job('', {}, 'synthetic.mp4')
    web.enqueue(job, 'scan'); web.WORK_Q.put(None)
    thread = threading.Thread(target=web.worker); thread.start()
    try:
        assert entered.wait(10)
        with web.app.test_client() as client:
            assert client.post('/api/jobs/' + job['id'] + '/cancel').status_code == 200
        assert job['phase'] == 'cancelled'
    finally:
        release.set(); thread.join(10)
    assert not thread.is_alive() and web.FILES.count == 0
    sink.close('normal', 'not_enabled')
    rows = _records(tmp_path / 'logs' / 'runtime.jsonl')
    assert [r['outcome'] for r in rows if r['kind'] == 'job_finished'] == ['cancelled']


def test_watchdog_identifies_cancelled_but_still_active_action(tmp_path, monkeypatch):
    import threading
    import openscrub_web as web
    from openscrub_internal import diagnostics
    jobs = tmp_path / 'jobs'; jobs.mkdir()
    monkeypatch.setattr(web, 'JOBS_DIR', str(jobs)); monkeypatch.setattr(web, 'JOBS', {})
    monkeypatch.setattr(web, 'FILES', type(web.FILES)(web.VAULT_LOCK))
    monkeypatch.setattr(web, 'start_worker', lambda: None)
    dead = threading.Thread(target=lambda: None); dead.start(); dead.join()
    job = web.new_job('', {}, 'synthetic.mp4'); job['phase'] = 'cancelled'
    sink = diagnostics.Diagnostics(tmp_path / 'logs', 'http', '1.0.0', monitor=False)
    ref = sink.start('scan')
    monkeypatch.setattr(web, 'WORKER', {'current': job['id'], 'thread': dead, 'diagnostic_ref': ref})
    monkeypatch.setattr(web, 'DIAGNOSTICS', sink)
    assert web.check_worker() and not sink._actions
    sink.close('normal', 'not_enabled')
    rows = _records(tmp_path / 'logs' / 'runtime.jsonl')
    assert [r['active_action_lost'] for r in rows if r['kind'] == 'worker_restarted'] == [True]
