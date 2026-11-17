"""Bounded job callbacks, atomic cursors and lifecycle ownership."""
import json
from pathlib import Path
import threading

import pytest


def test_actual_callback_overflow_routes_are_bounded_and_coherent(monkeypatch, tmp_path):
    import openscrub_web as web
    monkeypatch.setattr(web, 'JOBS', {})
    monkeypatch.setattr(web, 'JOBS_DIR', str(tmp_path))
    job = web.new_job('', {}, 'synthetic')
    callback = web.WebCallbacks(job)
    for i in range(2005):
        callback.log('entry-' + str(i))
    client = web.app.test_client()
    body = client.get('/api/jobs/' + job['id'] + '/log?from=0').get_json()
    assert len(body['lines']) == 2000
    assert (body['base'], body['from'], body['len'], body['reset'], body['dropped']) == (5, 5, 2005, 'stale', 5)
    assert body['lines'][0] == 'entry-5'
    meta = client.get('/api/jobs/' + job['id']).get_json()
    assert meta['log_tail'] == ['entry-' + str(i) for i in range(1975, 2005)]
    assert meta['log_len'] == body['len']
    assert meta['log_base'] == 5 and meta['log_retained'] == 2000
    assert meta['log_epoch'] == body['epoch']
    assert meta['log_bytes'] == sum(len(s.encode()) for s in body['lines'])
    assert sorted(p.name for p in (tmp_path / job['id']).iterdir()) == ['options.json']


def test_count_bytes_fifo_and_detached_snapshots():
    from openscrub_internal.job_logs import JobLog
    store = JobLog(max_entries=3, max_bytes=128, max_entry_bytes=64)
    for message in ('a' * 64, 'b' * 64):
        store.append(message)
    exact = store.snapshot()
    assert (exact['base'], exact['len'], exact['bytes'], exact['dropped']) == (0, 2, 128, 0)
    store.append('c')
    s = store.snapshot()
    assert (s['base'], s['len'], s['bytes'], s['dropped']) == (1, 3, 65, 1)
    assert s['lines'] == ['b' * 64, 'c']
    s['lines'].clear()
    assert store.snapshot()['lines'] == ['b' * 64, 'c']
    store = JobLog(('a', 'b', 'c'), max_entries=3)
    assert store.snapshot()['dropped'] == 0
    store.append('d')
    assert store.snapshot()['lines'] == ['b', 'c', 'd']
    assert store.snapshot()['dropped'] == 1


def test_entry_normalization_unicode_surrogates_multiline_and_hostile_input():
    from openscrub_internal.job_logs import JobLog, TRUNCATION_SUFFIX
    store = JobLog()
    inputs = ['x' * 8192, 'é' * 4096, 'one\ntwo\nthree', 'a\ud800b', '😀' * 1000000]
    for text in inputs:
        store.append(text)
    s = store.snapshot()
    assert s['len'] == 5 and s['truncated'] == 1
    assert s['lines'][:4] == [inputs[0], inputs[1], 'one\ntwo\nthree', 'a?b']
    assert s['lines'][4].endswith(TRUNCATION_SUFFIX)
    assert len(s['lines'][4].encode()) <= 8192
    class Hostile:
        def __str__(self):
            raise AssertionError('arbitrary conversion')
    class HostileString(str):
        def __getitem__(self, key):
            raise AssertionError('arbitrary slicing')
    for item in (None, 42, Hostile(), HostileString('x')):
        with pytest.raises(TypeError, match='plain string'):
            store.append(item)
    assert store.snapshot()['len'] == 5
    store.append('x' * 8193)
    assert len(store.snapshot()['lines'][-1].encode()) == 8192
    assert store.snapshot()['truncated'] == 2


def test_cursor_priority_tail_and_replacement():
    from openscrub_internal.job_logs import JobLog
    store = JobLog(['zero', 'one', 'two'], max_entries=2)
    epoch = store.snapshot()['epoch']
    for cursor, token, start, reason, lines in [
        (0, epoch, 1, 'stale', ['one', 'two']),
        (100, epoch, 1, 'future', ['one', 'two']),
        (100, 'old', 1, 'epoch', ['one', 'two']),
        (2, epoch, 2, None, ['two']),
        (3, epoch, 3, None, []),
        (-1, None, 1, 'stale', ['one', 'two']),
    ]:
        s = store.snapshot(cursor, token)
        assert (s['from'], s['reset'], s['lines']) == (start, reason, lines)
        assert len(s['lines']) == s['len'] - s['from']
    assert store.snapshot(tail=1)['lines'] == ['two']
    replacement = JobLog(['fresh'] * 10)
    assert replacement.snapshot(3, epoch)['reset'] == 'epoch'
    assert len(replacement.snapshot(3, epoch)['lines']) == 10
    empty = JobLog().snapshot()
    assert (empty['base'], empty['from'], empty['len'], empty['lines']) == (0, 0, 0, [])
    assert empty['epoch'] != epoch


@pytest.mark.parametrize('query', ['from=no', 'from=1.5', 'from=' + '9' * 65, 'epoch=' + 'a' * 129])
def test_invalid_cursor_is_bounded_400(monkeypatch, tmp_path, query):
    import openscrub_web as web
    monkeypatch.setattr(web, 'JOBS_DIR', str(tmp_path))
    job = web.new_job('', {}, 'query')
    result = web.app.test_client().get('/api/jobs/' + job['id'] + '/log?' + query)
    assert result.status_code == 400
    assert len(result.data) < 128


def test_negative_cursor_and_retry_keep_store_epoch(monkeypatch, tmp_path):
    import openscrub_web as web
    monkeypatch.setattr(web, 'JOBS_DIR', str(tmp_path))
    monkeypatch.setattr(web, 'enqueue', lambda *_: None)
    job = web.new_job('', {}, 'retry')
    video = Path(job['dir']) / 'input.mp4'
    video.write_bytes(b'')
    job['video'] = str(video)
    web.WebCallbacks(job).log('before')
    client = web.app.test_client()
    before = client.get('/api/jobs/' + job['id'] + '/log?from=-2').get_json()
    assert before['from'] == 0 and before['lines'] == ['before']
    owner = job['log']
    job['phase'] = 'error'
    assert client.post('/api/jobs/' + job['id'] + '/retry').status_code == 200
    after = client.get('/api/jobs/' + job['id'] + '/log?from=1&epoch=' + before['epoch']).get_json()
    assert after['epoch'] == before['epoch'] and job['log'] is owner
    assert after['len'] == 2 and 'retrying scan' in after['lines'][0]
    # Release the deliberately unconsumed queue reservation, like a cancelled
    # real worker; this fixture does not execute the scan.
    files = web.FILES.initialize(job)
    for lease in list(files.queued.values()):
        web._finish_operation(job, lease)
    files.queued.clear()


def test_two_event_controlled_producers_and_http_readers(monkeypatch, tmp_path):
    import openscrub_web as web
    from openscrub_internal.job_logs import JobLog
    monkeypatch.setattr(web, 'JOBS_DIR', str(tmp_path))
    job = web.new_job('', {}, 'concurrent')
    # Construct before publication; small bounds force eviction on every round.
    web.JOBS.pop(job['id'])
    job['log'] = JobLog(max_entries=7, max_bytes=512, max_entry_bytes=64)
    web.JOBS[job['id']] = job
    barrier = threading.Barrier(3)
    failures = []
    def producer(label):
        try:
            cb = web.WebCallbacks(job)
            for i in range(100):
                barrier.wait(timeout=5)
                cb.log(label + str(i))
                barrier.wait(timeout=5)
        except BaseException as exc:
            failures.append(exc)
            barrier.abort()
    threads = [threading.Thread(target=producer, args=(name,)) for name in ('a', 'b')]
    for thread in threads:
        thread.start()
    client = web.app.test_client()
    epoch = job['log'].snapshot()['epoch']
    for _ in range(100):
        barrier.wait(timeout=5)
        s = client.get('/api/jobs/' + job['id'] + '/log?from=0').get_json()
        assert s['base'] <= s['from'] <= s['len']
        assert len(s['lines']) == s['len'] - s['from'] <= 7
        assert s['epoch'] == epoch and s['base'] == s['dropped']
        meta = client.get('/api/jobs/' + job['id']).get_json()
        assert meta['log_retained'] == meta['log_len'] - meta['log_base']
        assert meta['log_bytes'] <= 512
        barrier.wait(timeout=5)
    for thread in threads:
        thread.join(timeout=5)
        assert not thread.is_alive()
    assert not failures
    s = job['log'].snapshot()
    assert (s['len'], s['dropped'], len(s['lines'])) == (200, 193, 7)


def test_recovery_constructors_get_fresh_epochs_without_log_files(monkeypatch, tmp_path):
    import openscrub_web as web
    monkeypatch.setattr(web, 'JOBS', {})
    monkeypatch.setattr(web, 'JOBS_DIR', str(tmp_path))
    for jid in ('incomplete', 'review', 'done'):
        folder = tmp_path / jid
        folder.mkdir()
        video = folder / 'input.mp4'
        video.write_bytes(b'')
        if jid != 'incomplete':
            (folder / 'report.json').write_text(json.dumps({'provenance': {'input': str(video)}}))
        if jid == 'done':
            (folder / 'output.mp4').write_bytes(b'')
    before = sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob('*'))
    web.rehydrate_jobs()
    epochs = {jid: job['log'].snapshot()['epoch'] for jid, job in web.JOBS.items()}
    assert len(set(epochs.values())) == 3
    assert {job['phase'] for job in web.JOBS.values()} == {'error', 'review', 'done'}
    old_jobs = dict(web.JOBS)
    monkeypatch.setattr(web, 'JOBS', {})
    web.rehydrate_jobs()
    for jid, old in old_jobs.items():
        assert web.JOBS[jid]['log'].snapshot()['epoch'] != epochs[jid]
        web.WebCallbacks(old).log('old callback')
        assert web.JOBS[jid]['log'].snapshot()['len'] == 1
    assert sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob('*')) == before


def test_thumbnail_and_tracking_callbacks_stay_with_their_job(monkeypatch, tmp_path):
    import openscrub_web as web
    monkeypatch.setattr(web, 'JOBS', {})
    monkeypatch.setattr(web, 'JOBS_DIR', str(tmp_path))
    old = web.new_job('', {}, 'old')
    deferred = []
    class DeferredThread:
        def __init__(self, target, **kwargs):
            self.target = target
        def start(self):
            deferred.append(self.target)
    monkeypatch.setattr(web.threading, 'Thread', DeferredThread)
    monkeypatch.setattr(web, 'build_args', lambda *_: object())
    monkeypatch.setattr(web.openscrub, 'run_scan', lambda *_: {'stats': {}})
    monkeypatch.setattr(web.openscrub, 'write_report', lambda *_, **kwargs: None)
    monkeypatch.setattr(web, '_load_job_report', lambda *_: {'render_state': {'fps': 1, 'cum': [[0, 0]]}, 'detections': []})
    class Capture:
        def release(self):
            pass
    sources = []
    monkeypatch.setattr(web.cv2, 'VideoCapture', lambda source: (sources.append(source), Capture())[1])
    web._run_job(old, 'scan')
    replacement = web.new_job('', {}, 'replacement')
    web.JOBS[old['id']] = replacement
    selected = old['video']
    old['video'] = 'late source must not replace lease'
    deferred.pop(0)()
    assert sources == [selected or None]
    assert any('thumbnails pre-generated' in s for s in old['log'].snapshot()['lines'])
    assert replacement['log'].snapshot()['lines'] == []
    # Actual manual-tracking route creates its ordinary engine callback.
    def detector(cb, **kwargs):
        cb.log('tracking detector')
        raise RuntimeError('no model needed')
    def track(*args, cb, **kwargs):
        cb.log('tracking samples')
        return [(0., [0, 0, 4, 4], .9)]
    monkeypatch.setattr(web.openscrub, 'PersonDetector', detector)
    monkeypatch.setattr(web.openscrub, 'track_manual_region', track)
    result = web.app.test_client().post('/api/jobs/' + old['id'] + '/track_object', json={'box': [0, 0, 4, 4], 't_ref': 0, 't0': 0, 't1': 1})
    assert result.status_code == 200
    deferred.pop(0)()
    lines = replacement['log'].snapshot()['lines']
    assert lines[:2] == ['tracking detector', 'tracking samples']
    assert 'tracked object: 1 position(s)' in lines[2]
    assert replacement['trackbg']['state'] == 'done'
