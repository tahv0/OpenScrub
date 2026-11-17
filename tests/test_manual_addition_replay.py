"""Replay real ordinary saves through report transactions and HTTP publication."""
import copy
import json
import threading
import os
import subprocess
import sys
from pathlib import Path

import pytest
import openscrub_web as web
from test_job_lifecycle import store, request, start_call, finish
from test_report_transactions import socket_api, ObservedLock, join


def addition(identity="draw:one", **changes):
    value = dict(manual_id=identity, t_start=0, t_end=1, screen_box=[2, 3, 20, 30])
    value.update(changes)
    return value


def saved(store):
    return json.loads(store.path.read_text())


def post(store, manual, **changes):
    return request('post', store.url + '/detections', json=dict(manual=manual, **changes))


def test_committed_http_response_lost_then_identical_retry(store, socket_api):
    payload = {'manual': [addition()]}
    # Deliberately discard a completed HTTP response, as an injected browser
    # response failure would. This is not a real transport-disconnect test.
    assert socket_api('POST', store.url + '/detections', payload)[0] == 200
    assert len(saved(store)['detections']) == 2
    assert socket_api('POST', store.url + '/detections', payload)[0] == 200
    assert len(saved(store)['detections']) == 2
    assert saved(store)['detections'][1]['manual_creation'] == {
        't_start': 0., 't_end': 1., 'cbox': [2, 3, 20, 30], 'aoff': [0, 0]}


def test_replay_preserves_previously_committed_indexed_changes(store):
    assert post(store, [addition()]).status_code == 200
    changes = dict(enabled={'1': False}, box_overrides={'1': [9, 8, 35, 45]},
                   time_overrides={'1': [.2, 2]}, audio=[{'t0': 0, 't1': .5}])
    assert post(store, [], **changes).status_code == 200
    row = copy.deepcopy(saved(store)['detections'][1])
    for _ in range(2):
        assert post(store, [addition()], **changes).status_code == 200
        assert saved(store)['detections'][1] == row
        assert len(saved(store)['detections']) == 2


def test_same_id_concurrent_requests_append_once(store, monkeypatch):
    lock = ObservedLock()
    web.FILES.initialize(store.job).report_lock = lock
    entered, release = threading.Event(), threading.Event()
    real = web.atomic_report
    def publish(path, doc):
        if not entered.is_set():
            entered.set()
            assert release.wait(8)
        real(path, doc)
    monkeypatch.setattr(web, 'atomic_report', publish)
    first = start_call('post', store.url + '/detections', json={'manual': [addition()]})
    second = None
    try:
        assert entered.wait(5)
        second = start_call('post', store.url + '/detections', json={'manual': [addition()]})
        assert lock.waiting.wait(5)
    finally:
        release.set()
        assert finish(first).status_code == 200
        if second:
            assert finish(second).status_code == 200
    assert len(saved(store)['detections']) == 2


def test_duplicate_ids_and_distinct_equal_geometry_and_legacy(store):
    assert post(store, [addition(), addition(), addition('draw:two'), addition('DRAW:ONE')]).status_code == 200
    assert [d.get('manual_id') for d in saved(store)['detections']] == [None, 'draw:one', 'draw:two', 'DRAW:ONE']
    legacy = addition(); del legacy['manual_id']
    assert post(store, [legacy, legacy]).status_code == 200
    assert len(saved(store)['detections']) == 6


@pytest.mark.parametrize('existing', [False, True])
def test_incompatible_id_reuse_atomically_rejects_other_edits(store, existing):
    if existing:
        assert post(store, [addition()]).status_code == 200
    before = store.path.read_bytes()
    response = post(store, [addition(), addition(t_end=3)], enabled={'0': False},
                    audio=[{'t0': 0, 't1': .8}])
    assert response.status_code == 409 and response.json['error']
    assert store.path.read_bytes() == before
    assert post(store, [addition('valid-after-conflict')]).status_code == 200


@pytest.mark.parametrize('identity', [None, '', 1, [], {}, 'a b', 'å', 'x'*129, 'line\n'])
def test_explicit_invalid_id_is_json_400_and_atomic(store, identity):
    before = store.path.read_bytes()
    response = post(store, [addition(identity)], enabled={'0': False})
    assert response.status_code == 400 and response.json['error']
    assert store.path.read_bytes() == before


@pytest.mark.parametrize('changes', [dict(t_start=float('nan')), dict(t_end=float('inf')),
    dict(t_ref=float('inf')), dict(screen_box=[1,2,3]),
    dict(screen_box=[1,2,3,float('nan')]), dict(screen_box=[1,2,3,'bad'])])
def test_identified_creation_requires_finite_effective_numbers(store, changes):
    before = store.path.read_bytes()
    response = post(store, [addition(**changes)], enabled={'0': False})
    assert response.status_code == 400 and response.json['error']
    assert store.path.read_bytes() == before


@pytest.mark.parametrize('creation', [None, {}, {'t_start': 0, 't_end': 1, 'cbox': [1,2,3], 'aoff': [0,0]},
    {'t_start': 0, 't_end': 1, 'cbox': [2,3,20,30], 'aoff': [float('nan'),0]},
    {'t_start': 0, 't_end': 1, 'cbox': [2,3,20,30], 'aoff': [10**400,0]},
    {'t_start': 0, 't_end': 1, 'cbox': [2.5,3,20,30], 'aoff': [0,0]},
    {'t_start': True, 't_end': 1, 'cbox': [2,3,20,30], 'aoff': [0,0]},
    {'t_start': 0, 't_end': 1, 'cbox': [2,3,20,30], 'aoff': [0,0], 'extra': 1}])
def test_imported_identified_row_without_trustworthy_creation_conflicts_only_on_replay(store, creation):
    doc = saved(store)
    doc['detections'][0]['manual_id'] = 'draw:one'
    if creation is not None:
        doc['detections'][0]['manual_creation'] = creation
    store.path.write_text(json.dumps(doc))
    assert post(store, [], enabled={'0': False}).status_code == 200
    before = store.path.read_bytes()
    response = post(store, [addition()], enabled={'0': True})
    assert response.status_code == 409 and response.json['error']
    assert store.path.read_bytes() == before


def test_multiple_imported_rows_with_same_id_are_conflict(store):
    assert post(store, [addition()]).status_code == 200
    doc = saved(store); doc['detections'].append(copy.deepcopy(doc['detections'][1]))
    store.path.write_text(json.dumps(doc)); before = store.path.read_bytes()
    response = post(store, [addition()])
    assert response.status_code == 409 and response.json['error']
    assert store.path.read_bytes() == before


def test_effective_normalization_reference_default_and_untrusted_creation(store):
    doc = saved(store)
    doc['render_state'] = {'fps': 2, 'cum': [[0,0],[10,20],[10,20]]}
    store.path.write_text(json.dumps(doc))
    first = addition(t_start='.5', t_end='2', screen_box=[12.9,23.8,30.2,50.7], manual_creation={'fake': True})
    assert post(store, [first]).status_code == 200
    assert post(store, [addition(t_start=.5, t_end=2., t_ref=.9, screen_box=[12.1,23.1,30.9,50.1])]).status_code == 200
    row = saved(store)['detections'][1]
    assert row['manual_creation'] == {'t_start': .5, 't_end': 2., 'cbox': [2,3,20,30], 'aoff': [10,20]}
    assert len(saved(store)['detections']) == 2
    assert post(store, [addition(t_start=.5, t_end=2, t_ref=0, screen_box=[2,3,20,30])]).status_code == 409
    assert saved(store)['custom'] == {'preserved': True}


@pytest.mark.parametrize('offset', [[0], [0, float('inf')], ['bad', 0]])
def test_identified_creation_rejects_invalid_report_offset(store, offset):
    doc = saved(store); doc['render_state']['cum'] = [offset]
    store.path.write_text(json.dumps(doc)); before = store.path.read_bytes()
    response = post(store, [addition()])
    assert response.status_code == 400 and response.json['error']
    assert store.path.read_bytes() == before


def test_real_render_and_fresh_server_process_preserve_creation_and_current_choices(store, socket_api):
    import cv2
    import numpy as np
    from test_report_transactions import run_worker
    video = store.job['video']
    writer = cv2.VideoWriter(video, cv2.VideoWriter_fourcc(*'MJPG'), 30, (96,64))
    assert writer.isOpened()
    for _ in range(30):
        writer.write(np.full((64,96,3), 180, dtype=np.uint8))
    writer.release()
    doc = saved(store); doc['render_state']['bands'] = [[0,0]]*30
    doc['detections'][0]['future'] = {'preserved': [1,2]}
    store.path.write_text(json.dumps(doc))
    payload = {'manual': [addition(), addition('kept:row')]}
    assert socket_api('POST', store.url + '/detections', payload)[0] == 200
    changes = {'enabled': {'0': False, '2': False},
               'box_overrides': {'1': [40,10,65,35]}, 'time_overrides': {'1': [0,.8]}}
    assert socket_api('POST', store.url + '/detections', changes)[0] == 200
    rows = saved(store)['detections']
    store.job['options'].update(encoder='x264', mode='box', pad=0)
    assert socket_api('POST', store.url + '/render')[0] == 200
    join(run_worker())
    assert store.job['phase'] == 'done', store.job.get('error')
    rendered = saved(store)
    assert rendered['detections'] == rows
    assert rendered['custom'] == {'preserved': True}
    cap = cv2.VideoCapture(store.job['output']); ok, frame = cap.read(); cap.release()
    assert ok and frame[20,50].mean() < 20 and frame[20,10].mean() > 150
    # A new interpreter opens the persisted job/report and serves a real HTTP
    # replay; no identity registry or live parent job objects cross processes.
    code = r"""
import json, os, threading, urllib.request
import openscrub_web as web
from cheroot import wsgi
assert web.__file__ == os.environ['REPLAY_SOURCE']
web._data_root = lambda: os.environ['REPLAY_ROOT']
web.JOBS_DIR = os.environ['REPLAY_JOBS']
web.TOKEN = None
web.rehydrate_jobs()
ready = threading.Event(); servers = []; errors = []
original = wsgi.Server.prepare
def prepare(server):
    original(server); servers.append(server); ready.set()
wsgi.Server.prepare = prepare
def serve():
    try: web._serve('127.0.0.1', 0, None)
    except BaseException as error: errors.append(str(error)); ready.set()
thread = threading.Thread(target=serve); thread.start()
try:
    assert ready.wait(8) and not errors, errors
    port = servers[0].socket.getsockname()[1]
    request = urllib.request.Request('http://127.0.0.1:'+str(port)+os.environ['REPLAY_URL']+'/detections',
        data=os.environ['REPLAY_PAYLOAD'].encode(), headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(request, timeout=8) as response:
        assert response.status == 200
        assert json.load(response)['total'] == 3
finally:
    for server in servers: server.stop()
    thread.join(8)
    assert not thread.is_alive()
print('fresh HTTP server replay: passed')
"""
    env = dict(os.environ, REPLAY_ROOT=str(store.root), REPLAY_JOBS=str(store.jobs),
               REPLAY_SOURCE=str(Path(web.__file__).resolve()), REPLAY_URL=store.url,
               REPLAY_PAYLOAD=json.dumps(payload))
    result = subprocess.run([sys.executable, '-c', code], env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert saved(store) == rendered


@pytest.mark.parametrize('identity', ['a', 'A0._:-'+'x'*122])
def test_valid_id_boundaries_and_report_local_scope(store, identity):
    assert post(store, [addition(identity)]).status_code == 200
    other = web.new_job('', {}, 'other.avi'); other['phase'] = 'review'
    (Path(other['dir'])/'report.json').write_text(json.dumps(store.doc))
    response = request('post', '/api/jobs/'+other['id']+'/detections', json={
        'manual': [addition(identity, t_end=3)]})
    assert response.status_code == 200
    assert saved(store)['detections'][1]['t_end'] == 1
    assert json.loads((Path(other['dir'])/'report.json').read_text())['detections'][1]['t_end'] == 3
