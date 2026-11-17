"""Real route transactions with bounded synthetic concurrent work."""
import copy
import json
import queue
import threading
from pathlib import Path

import pytest
import openscrub
import openscrub_web as web
from openscrub_internal import reports
from test_job_lifecycle import store, request, start_call, finish


class ObservedLock:
    def __init__(self):
        self.lock = threading.Lock()
        self.waiting = threading.Event()
    def __enter__(self):
        if self.lock.locked():
            self.waiting.set()
        self.lock.acquire()
        return self
    def __exit__(self, *args):
        self.lock.release()


def two_rows(store):
    doc = copy.deepcopy(store.doc)
    doc['detections'].append(copy.deepcopy(doc['detections'][0]))
    doc['render_state']['bands'] = [[0, 0]] * 30
    doc['audio_transcript'] = [[0, 1, 'synthetic']]
    doc['audio_suggestions'] = [{'t0': 0, 't1': 1, 'future': True}]
    store.path.write_text(json.dumps(doc))
    return doc


def test_overlapping_sparse_saves_preserve_both_choices(store, monkeypatch):
    two_rows(store)
    lock = ObservedLock()
    web.FILES.initialize(store.job).report_lock = lock
    staged, release = threading.Event(), threading.Event()
    real = web.atomic_report
    def publish(path, doc):
        if not staged.is_set():
            staged.set()
            assert release.wait(8)
        return real(path, doc)
    monkeypatch.setattr(web, 'atomic_report', publish)
    first = start_call('post', store.url + '/detections', json={'enabled': {'0': False}})
    second = None
    try:
        assert staged.wait(5)
        second = start_call('post', store.url + '/detections', json={'enabled': {'1': False}})
        assert lock.waiting.wait(2), 'second save never attempted the per-job report lock'
    finally:
        release.set()
        a = finish(first)
        b = finish(second) if second else None
    assert a.status_code == b.status_code == 200
    assert a.json['suggest_allowlist'] == []
    assert b.json['suggest_allowlist'] == ['synthetic']
    assert [d['enabled'] for d in json.loads(store.path.read_text())['detections']] == [False, False]


@pytest.mark.parametrize('phase', ['queued', 'scanning', 'queued_render', 'rendering'])
def test_active_worker_rejects_save_and_tracking(store, phase):
    before = store.path.read_bytes()
    store.job['phase'] = phase
    assert request('post', store.url + '/detections', json={'enabled': {'0': False}}).status_code == 409
    assert request('post', store.url + '/track_object', json={'box': [0,0,8,8], 't_ref': 0, 't0': 0, 't1': 1}).status_code == 409
    assert store.path.read_bytes() == before


def test_missing_report_save_is_404(store):
    store.path.unlink()
    assert request('post', store.url + '/detections', json={}).status_code == 404


def run_worker():
    web.WORK_Q.put(None)
    thread = threading.Thread(target=web.worker)
    thread.start()
    return thread


def join(thread):
    thread.join(8)
    assert not thread.is_alive()


def test_cancel_during_render_compute_rejects_real_final_publication(store, monkeypatch):
    two_rows(store)
    entered, release = threading.Event(), threading.Event()
    callbacks = []
    monkeypatch.setattr(openscrub, 'normalize_vfr', lambda *a: None)
    def render(src, dst, *args, **kwargs):
        callbacks.append(kwargs['cb'])
        entered.set()
        assert release.wait(8)
        Path(dst).write_bytes(b'synthetic encoded output')
    monkeypatch.setattr(openscrub, 'render', render)
    assert request('post', store.url + '/render').status_code == 200
    before = store.path.read_bytes()
    thread = run_worker()
    try:
        assert entered.wait(5)
        assert request('post', store.url + '/cancel').status_code == 200
        assert callbacks[0].cancelled()
        # A reusable Event alone must not revalidate the obsolete operation.
        store.job['cancel'].clear()
    finally:
        release.set()
        join(thread)
    assert store.path.read_bytes() == before, 'cancelled renderer published obsolete provenance'
    assert store.job['phase'] == 'cancelled'


def test_render_cannot_admit_over_active_tracker(store, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    threads = []
    real = web._start_owned_thread
    def start(target, lease):
        thread = real(target, lease)
        threads.append(thread)
        return thread
    monkeypatch.setattr(web, '_start_owned_thread', start)
    def compute(*a, **k):
        entered.set()
        assert release.wait(8)
        return [(0.5, [1,2,8,9], .9)]
    monkeypatch.setattr(openscrub, 'track_manual_region', compute)
    try:
        assert request('post', store.url + '/track_object', json={'box': [0,0,8,8], 't_ref': 0, 't0': 0, 't1': 1}).status_code == 200
        assert entered.wait(5)
        assert request('post', store.url + '/render').status_code == 409
        assert request('post', store.url + '/detections', json={'enabled': {'0': False}, 'manual': [{'t_start': 0, 't_end': 1, 'screen_box': [2,3,4,5]}], 'audio': [{'t0': 0, 't1': .5}]}).status_code == 200
    finally:
        release.set()
        for thread in threads:
            join(thread)
    doc = json.loads(store.path.read_text())
    assert len(doc['detections']) == 3
    assert doc['detections'][0]['enabled'] is False
    assert doc['audio_redactions'] == [{'t0': 0., 't1': .5, 'mode': 'mute'}]
    assert store.job['trackbg']['added'] == 1


@pytest.fixture
def tracker(monkeypatch):
    entered, release = threading.Event(), threading.Event()
    threads, callbacks = [], []
    real = web._start_owned_thread
    def start(target, lease):
        thread = real(target, lease)
        threads.append(thread)
        return thread
    def compute(*args, **kwargs):
        callbacks.append(kwargs['cb'])
        entered.set()
        assert release.wait(8)
        return [(0.5, [1,2,8,9], .9)]
    monkeypatch.setattr(web, '_start_owned_thread', start)
    monkeypatch.setattr(openscrub, 'PersonDetector', lambda *a, **kw: None)
    monkeypatch.setattr(openscrub, 'track_manual_region', compute)
    yield entered, release, threads, callbacks
    release.set()
    for thread in threads:
        join(thread)


def track(store):
    return request('post', store.url + '/track_object', json={
        'box': [0,0,8,8], 't_ref': 0, 't0': 0, 't1': 1})


def test_two_tracker_admissions_and_subsequent_attempt(store, tracker):
    entered, release, threads, callbacks = tracker
    barrier = threading.Barrier(3)
    responses = []
    def post():
        barrier.wait(5)
        responses.append(track(store))
    calls = [threading.Thread(target=post) for _ in range(2)]
    for call in calls:
        call.start()
    barrier.wait(5)
    for call in calls:
        join(call)
    assert entered.wait(5)
    assert sorted(response.status_code for response in responses) == [200, 409]
    assert len(callbacks) == 1
    release.set()
    join(threads[0])
    assert track(store).status_code == 200
    join(threads[1])
    doc = json.loads(store.path.read_text())
    assert [d['track'] for d in doc['detections'][1:]] == [0, 1]
    assert request('get', store.url + '/track_status').json['added'] == 1


def test_tracker_latest_id_and_offsets_survive_save(store, tracker):
    entered, release, threads, _ = tracker
    assert track(store).status_code == 200
    assert entered.wait(5)
    assert request('post', store.url + '/detections', json={
        'enabled': {'0': False}, 'box_overrides': {'0': [3,4,9,10]},
        'time_overrides': {'0': [.1,.8]},
        'manual': [{'t_start': 0, 't_end': 1, 'screen_box': [2,3,4,5]}],
        'audio': [{'t0': .1, 't1': .4, 'mode': 'bleep'}]}).status_code == 200
    # Supplemental publication-boundary control: a legitimate newer synthetic
    # track/FPS generation exists before the computing tracker commits.
    with web.FILES.initialize(store.job).report_lock:
        doc = json.loads(store.path.read_text())
        doc['detections'][-1]['track'] = 42
        doc['render_state']['fps'] = 10
        doc['render_state']['cum'] = [[2,3]] * 30
        web.atomic_report(str(store.path), doc)
    release.set()
    join(threads[0])
    doc = json.loads(store.path.read_text())
    assert len(doc['detections']) == 3
    assert doc['detections'][0]['enabled'] is False
    assert doc['detections'][0]['cbox'] == [3.,4.,9.,10.]
    assert doc['detections'][0]['t_start'] == .1
    assert doc['detections'][-1]['track'] == 43
    assert doc['detections'][-1]['cbox'] == [-1,-1,6,6]
    assert doc['detections'][-1]['aoff'] == [2,3]
    assert doc['detections'][-1]['t_end'] == pytest.approx(.99)
    assert doc['audio_redactions'] == [{'t0': .1, 't1': .4, 'mode': 'bleep'}]
    assert doc['custom'] == {'preserved': True}


def test_tracker_commit_then_waiting_save_merges(store, tracker, monkeypatch):
    entered, release_compute, threads, _ = tracker
    staged, release_publish = threading.Event(), threading.Event()
    lock = ObservedLock()
    web.FILES.initialize(store.job).report_lock = lock
    real = web.atomic_report
    def publish(path, doc):
        if any('track' in d for d in doc['detections']) and not staged.is_set():
            staged.set()
            assert release_publish.wait(8)
        real(path, doc)
    monkeypatch.setattr(web, 'atomic_report', publish)
    assert track(store).status_code == 200
    assert entered.wait(5)
    release_compute.set()
    call = None
    try:
        assert staged.wait(5)
        call = start_call('post', store.url + '/detections', json={'enabled': {'0': False}})
        assert lock.waiting.wait(5)
    finally:
        release_publish.set()
        join(threads[0])
        response = finish(call) if call else None
    assert response.status_code == 200
    doc = json.loads(store.path.read_text())
    assert doc['detections'][0]['enabled'] is False
    assert doc['detections'][-1]['track'] == 0


def test_cancelled_tracker_cannot_publish_or_replace_new_status_after_clear(store, tracker):
    entered, release, threads, callbacks = tracker
    assert track(store).status_code == 200
    assert entered.wait(5)
    before = store.path.read_bytes()
    assert request('post', store.url + '/cancel').status_code == 200
    assert callbacks[0].cancelled()
    acknowledged = request('get', store.url + '/track_status').json
    assert acknowledged['state'] == 'done'
    store.job['cancel'].clear()
    assert track(store).status_code == 409
    release.set()
    join(threads[0])
    assert store.path.read_bytes() == before
    assert request('get', store.url + '/track_status').json == acknowledged
    assert track(store).status_code == 200
    join(threads[1])
    assert json.loads(store.path.read_text())['detections'][-1]['track'] == 0


@pytest.mark.parametrize('failure', ['parse', 'application', 'serialization', 'fsync', 'replace'])
def test_failed_transaction_releases_waiter_and_preserves_previous_json(store, monkeypatch, failure):
    two_rows(store)
    before = store.path.read_bytes()
    entered, release = threading.Event(), threading.Event()
    lock = ObservedLock()
    web.FILES.initialize(store.job).report_lock = lock
    if failure == 'parse':
        target, name = web, '_load_job_report'
    elif failure == 'serialization':
        target, name = reports.json, 'dump'
    elif failure in ('fsync', 'replace'):
        target, name = reports.os, failure
    else:
        target, name = web, '_load_job_report'
    real = getattr(target, name)
    count = [0]
    def fail_once(*args, **kwargs):
        count[0] += 1
        if count[0] == 1:
            entered.set()
            assert release.wait(8)
            if failure == 'application':
                return {'detections': None}
            if failure == 'parse':
                raise ValueError('synthetic parse failure')
            raise OSError('synthetic ' + failure + ' failure')
        return real(*args, **kwargs)
    monkeypatch.setattr(target, name, fail_once)
    first = start_call('post', store.url + '/detections', json={'enabled': {'0': False}})
    second = None
    try:
        assert entered.wait(5)
        second = start_call('post', store.url + '/detections', json={'enabled': {'1': False}})
        assert lock.waiting.wait(5)
        assert store.path.read_bytes() == before
        assert request('delete', store.url).status_code == 409
    finally:
        release.set()
        a = finish(first)
        b = finish(second) if second else None
    assert a.status_code == 500 and b.status_code == 200
    doc = json.loads(store.path.read_text())
    assert [d['enabled'] for d in doc['detections']] == [True, False]
    assert not list(store.path.parent.glob('.report-*.tmp'))


def test_distinct_jobs_commit_independently(store, monkeypatch):
    second = web.new_job(store.job['video'], {}, 'second.avi')
    second['phase'] = 'review'
    path = Path(second['dir']) / 'report.json'
    path.write_bytes(store.path.read_bytes())
    staged, release = threading.Event(), threading.Event()
    real = web.atomic_report
    def publish(target, doc):
        if target == str(store.path):
            staged.set()
            assert release.wait(8)
        real(target, doc)
    monkeypatch.setattr(web, 'atomic_report', publish)
    call = start_call('post', store.url + '/detections', json={'enabled': {'0': False}})
    try:
        assert staged.wait(5)
        assert request('post', '/api/jobs/' + second['id'] + '/detections', json={'enabled': {'0': False}}).status_code == 200
        assert json.loads(path.read_text())['detections'][0]['enabled'] is False
    finally:
        release.set()
        assert finish(call).status_code == 200


def test_overlapping_combined_edits_keep_additive_fields_and_own_responses(store, monkeypatch):
    original = two_rows(store)
    staged, release = threading.Event(), threading.Event()
    lock = ObservedLock()
    web.FILES.initialize(store.job).report_lock = lock
    real = web.atomic_report
    def publish(path, doc):
        if not staged.is_set():
            staged.set()
            assert release.wait(8)
        real(path, doc)
    monkeypatch.setattr(web, 'atomic_report', publish)
    first = start_call('post', store.url + '/detections', json={
        'box_overrides': {'0': [3,4,10,11]}, 'time_overrides': {'0': [.1,.8]},
        'manual': [{'t_start': 0, 't_end': 1, 'screen_box': [2,3,4,5]}]})
    second = None
    try:
        assert staged.wait(5)
        second = start_call('post', store.url + '/detections', json={
            'enabled': {'1': False}, 'audio': [{'t0': .2, 't1': .4}]})
        assert lock.waiting.wait(5)
    finally:
        release.set()
        a = finish(first)
        b = finish(second) if second else None
    assert a.status_code == b.status_code == 200
    assert a.json['total'] == b.json['total'] == 3
    doc = json.loads(store.path.read_text())
    assert doc['detections'][0]['cbox'] == [3.,4.,10.,11.]
    assert doc['detections'][0]['t_start'] == .1
    assert doc['detections'][0]['t_end'] == .8
    assert doc['detections'][1]['enabled'] is False
    assert doc['detections'][2]['category'] == 'manual'
    assert doc['custom'] == original['custom']
    assert doc['audio_suggestions'] == original['audio_suggestions']
    assert doc['audio_transcript'] == original['audio_transcript']
    assert doc['audio_redactions'] == [{'t0': .2, 't1': .4, 'mode': 'mute'}]


def test_save_wins_before_render_admission_and_queued_gate_closes(store, monkeypatch):
    two_rows(store)
    staged, release = threading.Event(), threading.Event()
    lock = ObservedLock()
    web.FILES.initialize(store.job).report_lock = lock
    real = web.atomic_report
    def publish(path, doc):
        if not staged.is_set():
            staged.set()
            assert release.wait(8)
        real(path, doc)
    monkeypatch.setattr(web, 'atomic_report', publish)
    save = start_call('post', store.url + '/detections', json={'enabled': {'0': False}})
    render = None
    try:
        assert staged.wait(5)
        render = start_call('post', store.url + '/render')
        assert lock.waiting.wait(5)
    finally:
        release.set()
        assert finish(save).status_code == 200
        assert finish(render).status_code == 200
    assert request('post', store.url + '/detections', json={'enabled': {'1': False}}).status_code == 409
    assert track(store).status_code == 409
    assert request('post', store.url + '/render').json['note'] == 'render already in progress'
    snapshots = []
    monkeypatch.setattr(openscrub, 'normalize_vfr', lambda *a: None)
    def compute(src, dst, *a, **kw):
        snapshots.append(json.loads(store.path.read_text()))
        Path(dst).write_bytes(b'synthetic output')
    monkeypatch.setattr(openscrub, 'render', compute)
    join(run_worker())
    assert snapshots[0]['detections'][0]['enabled'] is False
    assert [d['enabled'] for d in json.loads(store.path.read_text())['detections']] == [False, True]
    assert store.job['phase'] == 'done'


@pytest.mark.parametrize(('action', 'stage'), [('scan', 'constructed'), ('scan', 'publishing'), ('render', 'constructed'), ('render', 'hashed'), ('render', 'publishing')])
def test_cancel_final_worker_boundary(store, monkeypatch, action, stage):
    two_rows(store)
    before = store.path.read_bytes()
    entered, release = threading.Event(), threading.Event()
    lock = ObservedLock()
    web.FILES.initialize(store.job).report_lock = lock
    callbacks, background = [], []
    real_start = web._start_owned_thread
    def start(*args):
        thread = real_start(*args)
        background.append(thread)
        return thread
    monkeypatch.setattr(web, '_start_owned_thread', start)
    monkeypatch.setattr(openscrub, 'normalize_vfr', lambda *a: None)
    def render(src, dst, *args, **kwargs):
        callbacks.append(kwargs['cb'])
        Path(dst).write_bytes(b'synthetic encoded output')
    monkeypatch.setattr(openscrub, 'render', render)
    def scan(args, cb):
        callbacks.append(cb)
        return dict(fps=30, cum=[[0,0]], bands=[[0,0]], detections=[], stats={})
    monkeypatch.setattr(openscrub, 'run_scan', scan)
    if stage == 'constructed':
        real_write = openscrub.write_report
        def write(path, args, state, output_path=None, publisher=None):
            def pause(target, doc):
                entered.set()
                assert release.wait(8)
                publisher(target, doc)
            return real_write(path, args, state, output_path, publisher=pause)
        monkeypatch.setattr(openscrub, 'write_report', write)
    elif stage == 'hashed':
        real_hash = openscrub.sha256_file
        def sha(path, *args, **kwargs):
            value = real_hash(path, *args, **kwargs)
            if Path(path).name.startswith('output.'):
                entered.set()
                assert release.wait(8)
            return value
        monkeypatch.setattr(openscrub, 'sha256_file', sha)
    else:
        real_replace = reports.os.replace
        def replace(src, dst):
            if str(dst) == str(store.path):
                entered.set()
                assert release.wait(8)
            return real_replace(src, dst)
        monkeypatch.setattr(reports.os, 'replace', replace)
    if action == 'render':
        assert request('post', store.url + '/render').status_code == 200
    else:
        store.job['phase'] = 'error'
        assert request('post', store.url + '/retry').status_code == 200
    thread = run_worker()
    cancel = None
    try:
        assert entered.wait(5)
        lock.waiting.clear()
        cancel = start_call('post', store.url + '/cancel')
        if stage == 'publishing':
            assert lock.waiting.wait(5), 'cancel did not wait for committing publisher'
            assert callbacks[0].cancelled(), 'Event must reach compute before report lock'
            assert not cancel[1].is_set()
        else:
            assert finish(cancel).status_code == 200
            cancel = None
            assert callbacks[0].cancelled()
            store.job['cancel'].clear()
            # Cancelled worker still owns resources and closes mutation gates.
            assert request('post', store.url + '/detections', json={}).status_code == 409
            assert request('post', store.url + '/retry').status_code == 409
    finally:
        release.set()
        if cancel:
            assert finish(cancel).status_code == 200
        join(thread)
        for worker in background:
            join(worker)
    if stage != 'publishing':
        assert store.job['phase'] == 'cancelled'
    else:
        # Terminal publication may legitimately finish before cancel obtains
        # its acknowledgement boundary; cancellation does not undo that commit.
        assert store.job['phase'] in ('cancelled', 'done', 'review')
    if stage == 'publishing':
        assert store.path.read_bytes() != before, 'a valid pre-ack publication is not undone'
        json.loads(store.path.read_text())
    else:
        assert store.path.read_bytes() == before


@pytest.fixture
def socket_api(store, monkeypatch):
    import http.client
    from cheroot import wsgi
    ready = threading.Event()
    servers, errors = [], []
    real = wsgi.Server.prepare
    def prepare(server):
        real(server)
        servers.append(server)
        ready.set()
    monkeypatch.setattr(wsgi.Server, 'prepare', prepare)
    def serve():
        try:
            web._serve('127.0.0.1', 0, None)
        except BaseException as error:
            errors.append(error)
            ready.set()
    thread = threading.Thread(target=serve)
    thread.start()
    try:
        assert ready.wait(8) and not errors, errors
        port = servers[0].socket.getsockname()[1]
        def api(method, path, payload=None):
            connection = http.client.HTTPConnection('127.0.0.1', port, timeout=8)
            try:
                body = json.dumps(payload) if payload is not None else None
                connection.request(method, path, body=body, headers={
                    'Content-Type': 'application/json', 'Connection': 'close'})
                result = connection.getresponse()
                return result.status, dict(result.getheaders()), result.read()
            finally:
                connection.close()
        yield api
    finally:
        for server in servers:
            server.stop()
        join(thread)
        assert not errors


def test_real_socket_overlapping_sparse_saves(store, socket_api, monkeypatch):
    two_rows(store)
    staged, release = threading.Event(), threading.Event()
    lock = ObservedLock()
    web.FILES.initialize(store.job).report_lock = lock
    real = web.atomic_report
    def publish(path, doc):
        if not staged.is_set():
            staged.set()
            assert release.wait(8)
        real(path, doc)
    monkeypatch.setattr(web, 'atomic_report', publish)
    values = []
    def post(index):
        values.append(socket_api('POST', store.url + '/detections', {'enabled': {str(index): False}}))
    first = threading.Thread(target=post, args=(0,))
    second = threading.Thread(target=post, args=(1,))
    first.start()
    try:
        assert staged.wait(5)
        second.start()
        assert lock.waiting.wait(5)
    finally:
        release.set()
        join(first)
        if second.ident:
            join(second)
    assert [v[0] for v in values] == [200, 200]
    assert [d['enabled'] for d in json.loads(store.path.read_text())['detections']] == [False, False]


def test_report_download_stat_open_is_one_generation(store, socket_api, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    lock = ObservedLock()
    web.FILES.initialize(store.job).report_lock = lock
    before = store.path.read_bytes()
    real_send = web.send_file
    def send(*args, **kwargs):
        if str(args[0]) == str(store.path):
            entered.set()
            assert release.wait(8)
        return real_send(*args, **kwargs)
    monkeypatch.setattr(web, 'send_file', send)
    values = []
    thread = threading.Thread(target=lambda: values.append(socket_api('GET', store.url + '/report')))
    thread.start()
    save = None
    try:
        assert entered.wait(5)
        save = start_call('post', store.url + '/detections', json={
            'manual': [{'t_start': 0, 't_end': 1, 'screen_box': [2,3,4,5]}]})
        assert lock.waiting.wait(5), 'download metadata/open did not exclude publication'
    finally:
        release.set()
        join(thread)
        assert finish(save).status_code == 200
    status, headers, body = values[0]
    assert status == 200
    assert int(headers['Content-Length']) == len(body) == len(before)
    assert body == before
    assert len(store.path.read_bytes()) != len(before)


def test_real_socket_save_track_real_render_and_reopen(store, socket_api, tracker):
    import cv2
    import numpy as np
    video = store.job['video']
    writer = cv2.VideoWriter(video, cv2.VideoWriter_fourcc(*'MJPG'), 30, (96,64))
    assert writer.isOpened()
    for i in range(30):
        writer.write(np.full((64,96,3), 180, dtype=np.uint8))
    writer.release()
    two_rows(store)
    store.job['options'].update(encoder='x264', mode='box', pad=0)
    status, _, _ = socket_api('POST', store.url + '/detections', {
        'enabled': {'0': False}, 'audio': [{'t0': .1, 't1': .2, 'mode': 'mute'}]})
    assert status == 200
    entered, release, threads, _ = tracker
    status, _, _ = socket_api('POST', store.url + '/track_object', {
        'box': [1,2,8,9], 't_ref': .5, 't0': 0, 't1': 1})
    assert status == 200 and entered.wait(5)
    release.set()
    join(threads[0])
    assert socket_api('POST', store.url + '/render')[0] == 200
    assert socket_api('POST', store.url + '/detections', {})[0] == 409
    join(run_worker())
    assert store.job['phase'] == 'done', store.job['error']
    status, _, body = socket_api('GET', store.url + '/report')
    doc = json.loads(body)
    assert status == 200 and len(doc['detections']) == 3
    assert doc['detections'][0]['enabled'] is False
    assert doc['detections'][-1]['track'] == 0
    assert doc['custom'] == {'preserved': True}
    assert doc['audio_redactions'] == [{'t0': .1, 't1': .2, 'mode': 'mute'}]
    output = Path(store.job['output'])
    assert doc['provenance']['output_sha256'] == openscrub.sha256_file(str(output))
    cap = cv2.VideoCapture(str(output))
    assert cap.isOpened()
    frames = 0
    while cap.read()[0]:
        frames += 1
    cap.release()
    assert frames == 30
    web.JOBS.clear()
    web.rehydrate_jobs()
    assert socket_api('GET', store.url + '/detections')[0] == 200
    assert json.loads(socket_api('GET', store.url + '/report')[2]) == doc


def test_waiting_transaction_keeps_vault_delete_retention_busy(store, monkeypatch):
    import os
    import time
    store.enable()
    staged, release = threading.Event(), threading.Event()
    lock = ObservedLock()
    web.FILES.initialize(store.job).report_lock = lock
    real = web.atomic_report
    def publish(path, doc):
        if not staged.is_set():
            staged.set()
            assert release.wait(8)
        real(path, doc)
    monkeypatch.setattr(web, 'atomic_report', publish)
    first = start_call('post', store.url + '/detections', json={'enabled': {'0': False}})
    second = None
    try:
        assert staged.wait(5)
        second = start_call('post', store.url + '/detections', json={'audio': []})
        assert lock.waiting.wait(5)
        assert request('post', '/api/vault/lock').status_code == 409
        assert request('delete', store.url).status_code == 409
        old = time.time() - 3 * 86400
        os.utime(store.job['dir'], (old,old))
        web.retention_sweep(1)
        assert store.job['id'] in web.JOBS and store.path.exists()
    finally:
        release.set()
        assert finish(first).status_code == finish(second).status_code == 200
    assert request('post', '/api/vault/lock').status_code == 200
    assert request('post', '/api/vault/unlock', json={'password': 'synthetic-password'}).status_code == 200
    assert json.loads(store.path.read_text())['detections'][0]['enabled'] is False
    assert request('delete', store.url).status_code == 200
    with web.app.test_request_context():
        with pytest.raises(Exception) as error:
            web._own_files(store.job)
        assert error.value.code == 404
    assert not store.path.exists()


def test_late_cancel_of_captured_operation_cannot_cancel_new_retry(store, monkeypatch):
    two_rows(store)
    computing, release_compute = threading.Event(), threading.Event()
    waiting_cancel, release_cancel = threading.Event(), threading.Event()
    lock = ObservedLock()
    class DelayedCancelLock:
        def __enter__(self):
            if threading.current_thread().name == 'captured-old-cancel':
                waiting_cancel.set()
                assert release_cancel.wait(8)
            return lock.__enter__()
        def __exit__(self, *args):
            lock.__exit__(*args)
    web.FILES.initialize(store.job).report_lock = DelayedCancelLock()
    monkeypatch.setattr(openscrub, 'normalize_vfr', lambda *a: None)
    def compute(src, dst, *args, **kwargs):
        computing.set()
        assert release_compute.wait(8)
        if kwargs['cb'].cancelled():
            raise openscrub.PipelineCancelled()
        Path(dst).write_bytes(b'synthetic output')
    monkeypatch.setattr(openscrub, 'render', compute)
    monkeypatch.setattr(openscrub, 'run_scan', lambda *a: dict(
        fps=30, cum=[[0,0]], bands=[[0,0]], detections=[], stats={}))
    background = []
    real = web._start_owned_thread
    def start(*args):
        thread = real(*args)
        background.append(thread)
        return thread
    monkeypatch.setattr(web, '_start_owned_thread', start)
    assert request('post', store.url + '/render').status_code == 200
    worker = run_worker()
    responses = []
    cancel = threading.Thread(name='captured-old-cancel', target=lambda: responses.append(
        request('post', store.url + '/cancel')))
    try:
        assert computing.wait(5)
        cancel.start()
        assert waiting_cancel.wait(5)
        assert store.job['cancel'].is_set()
        release_compute.set()
        join(worker)
        assert request('post', store.url + '/retry').status_code == 200
        assert store.job['phase'] == 'queued'
        operation = web.FILES.initialize(store.job).operation
        assert not store.job['cancel'].is_set()
    finally:
        release_compute.set()
        release_cancel.set()
        if cancel.ident:
            join(cancel)
        join(worker)
    try:
        assert responses[0].status_code == 200
        assert web.FILES.initialize(store.job).operation is operation
        assert store.job['phase'] == 'queued'
        assert not store.job['cancel'].is_set()
    finally:
        join(run_worker())
        for thread in background:
            join(thread)
    assert store.job['phase'] == 'review'


def test_cancelled_deleted_queue_ticket_cleans_up_without_stopping_worker(store):
    assert request('post', store.url + '/render').status_code == 200
    assert request('post', store.url + '/cancel').status_code == 200
    assert request('delete', store.url).status_code == 200
    web.WORK_Q.put(None)
    web.worker()
    assert web.WORK_Q.unfinished_tasks == 0
    assert not store.path.exists()


def test_cancel_signal_during_queue_admission_is_not_cleared(store, monkeypatch):
    entered = threading.Event()
    lock = ObservedLock()
    web.FILES.initialize(store.job).report_lock = lock
    operations = []
    real = web._begin_operation
    def begin(job, owner):
        real(job, owner)
        operations.append(owner.operation)
        entered.set()
        assert lock.waiting.wait(8)
    monkeypatch.setattr(web, '_begin_operation', begin)
    render = start_call('post', store.url + '/render')
    cancel = None
    try:
        assert entered.wait(5)
        cancel = start_call('post', store.url + '/cancel')
    finally:
        assert finish(render).status_code == 200
        if cancel:
            assert finish(cancel).status_code == 200
        join(run_worker())
    assert operations[0].is_set(), 'admission cleared a captured cancellation signal'
    assert store.job['phase'] == 'cancelled'


def test_render_rechecks_prepared_operation_after_intervening_tracker(store, tracker, monkeypatch):
    selected, release = threading.Event(), threading.Event()
    real = web._select_render_input
    def select(job, owner):
        real(job, owner)
        if not selected.is_set():
            selected.set()
            assert release.wait(8)
    monkeypatch.setattr(web, '_select_render_input', select)
    render = start_call('post', store.url + '/render')
    entered, release_tracker, threads, _ = tracker
    try:
        assert selected.wait(5)
        assert track(store).status_code == 200
        assert entered.wait(5)
        release_tracker.set()
        join(threads[0])
    finally:
        release.set()
        response = finish(render)
    try:
        assert response.status_code == 409
    finally:
        if not web.WORK_Q.empty():
            assert request('post', store.url + '/cancel').status_code == 200
            join(run_worker())
    assert request('post', store.url + '/render').status_code == 200
    assert request('post', store.url + '/cancel').status_code == 200
    join(run_worker())
    assert json.loads(store.path.read_text())['detections'][-1]['track'] == 0


def test_tracker_rejects_source_prepared_before_scan_normalization_finishes(store, monkeypatch):
    scanning, finish_scan = threading.Event(), threading.Event()
    prepared, finish_prepare = threading.Event(), threading.Event()
    normalized = Path(store.job['dir']) / 'normalized.avi'
    normalized.write_bytes(b'synthetic normalized video')
    background, responses = [], []
    real_start = web._start_owned_thread
    def start(*args):
        thread = real_start(*args)
        background.append(thread)
        return thread
    monkeypatch.setattr(web, '_start_owned_thread', start)
    def scan(args, cb):
        scanning.set()
        assert finish_scan.wait(8)
        args.original_video, args.video = args.video, str(normalized)
        return dict(fps=10, cum=[[1,2]], bands=[[0,0]], detections=[], stats={})
    monkeypatch.setattr(openscrub, 'run_scan', scan)
    monkeypatch.setattr(openscrub, 'PersonDetector', lambda *a, **kw: None)
    monkeypatch.setattr(openscrub, 'track_manual_region', lambda *a, **kw: [(0, [1,2,8,9], .9)])
    real_own = web._own_files
    def own(job=None, work=False):
        lease = real_own(job, work)
        if work and threading.current_thread().name == 'late-tracker-source':
            prepared.set()
            assert finish_prepare.wait(8)
        return lease
    monkeypatch.setattr(web, '_own_files', own)
    store.job['phase'] = 'error'
    assert request('post', store.url + '/retry').status_code == 200
    worker = run_worker()
    tracker_call = threading.Thread(name='late-tracker-source', target=lambda: responses.append(track(store)))
    try:
        assert scanning.wait(5)
        tracker_call.start()
        assert prepared.wait(5)
        finish_scan.set()
        join(worker)
        for thread in background:
            join(thread)
        assert store.job['video'] == str(normalized)
    finally:
        finish_scan.set()
        finish_prepare.set()
        join(worker)
        if tracker_call.ident:
            join(tracker_call)
        for thread in background:
            join(thread)
    assert responses[0].status_code == 409
    assert json.loads(store.path.read_text())['detections'] == []
