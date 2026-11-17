"""Actual render-selected inputs and shared-tree allowlist ownership."""
import builtins
import copy
import json
import os
from pathlib import Path
import threading
import time

import pytest

import openscrub
import openscrub_web as web
import openscrub_vault as vault
from test_job_lifecycle import store, request, start_call, finish, ObservedLock
from test_report_roundtrip import review as media_review, assert_review_preserved


def destination(store, original):
    job = web.new_job('', {}, 'normalized-synthetic.avi')
    normalized = Path(job['dir']) / 'input.cfr.mp4'
    normalized.write_bytes(b'synthetic normalized input')
    job.update(video=str(normalized), phase='review')
    doc = copy.deepcopy(store.doc)
    doc['provenance'].update(input=str(normalized), original_input=str(original),
                             vfr_normalized=True)
    doc['render_state']['bands'] = [[0, 0]] * 30
    report = Path(job['dir']) / 'report.json'
    report.write_text(json.dumps(doc))
    return job, report, doc


def run_queued():
    web.WORK_Q.put(None)
    thread = threading.Thread(target=web.worker)
    thread.start()
    return thread


def join(thread):
    thread.join(8)
    assert not thread.is_alive(), 'render worker did not finish'


@pytest.mark.parametrize('method', ['get', 'post'])
def test_locked_allowlist_cannot_read_or_recreate_plaintext(store, method):
    store.enable()
    assert request('post', '/api/allowlist', json={'words': ['synthetic-person']}).status_code == 200
    assert request('post', '/api/vault/lock').status_code == 200
    response = request(method, '/api/allowlist', **({'json': {'words': ['late-name']}} if method == 'post' else {}))
    assert response.status_code == 423
    assert not (store.jobs / 'allowlist.txt').exists()


def test_allowlist_write_owns_tree_until_close_then_encrypts_and_reopens(store, monkeypatch):
    store.enable()
    path = store.jobs / 'allowlist.txt'
    entered, release = threading.Event(), threading.Event()
    real_open = builtins.open
    class Writer:
        def __init__(self, file):
            self.file = file
        def __enter__(self):
            return self
        def __exit__(self, *args):
            self.file.close()
        def write(self, content):
            entered.set()
            assert release.wait(8)
            return self.file.write(content)
    def opening(name, mode='r', *args, **kwargs):
        file = real_open(name, mode, *args, **kwargs)
        return Writer(file) if str(name) == str(path) and mode == 'w' else file
    monkeypatch.setattr(builtins, 'open', opening)
    call = start_call('post', '/api/allowlist', json={'words': [' synthetic-one ', 'synthetic-two', 'synthetic-one']})
    try:
        assert entered.wait(5)
        assert request('post', '/api/vault/lock').status_code == 409
        assert web.FILES.count == 1
    finally:
        release.set()
        response = finish(call)
    assert response.status_code == 200 and response.get_json() == {'ok': True, 'count': 2}
    committed = path.read_bytes()
    assert committed == b'synthetic-one\nsynthetic-two\n'
    assert request('post', '/api/vault/lock').status_code == 200
    assert not path.exists()
    assert request('post', '/api/vault/unlock', json={'password': 'synthetic-password'}).status_code == 200
    assert path.read_bytes() == committed
    result = request('get', '/api/allowlist').get_json()
    assert result == {'words': ['synthetic-one', 'synthetic-two'], 'path': str(path)}
    assert request('post', '/api/allowlist', json={'remove': ['synthetic-one']}).get_json()['count'] == 1
    assert request('post', '/api/allowlist', json={'clear': True}).get_json()['count'] == 0


@pytest.mark.parametrize('method', ['get', 'post'])
def test_allowlist_waiter_rechecks_after_vault_transition(store, monkeypatch, method):
    store.enable()
    entered, release = threading.Event(), threading.Event()
    real_encrypt = vault.encrypt_tree
    def encrypt(*args):
        entered.set()
        assert release.wait(8)
        return real_encrypt(*args)
    monkeypatch.setattr(vault, 'encrypt_tree', encrypt)
    guard = ObservedLock(web.VAULT_LOCK, 'late-allowlist')
    monkeypatch.setattr(web, 'VAULT_LOCK', guard)
    web.FILES.guard = guard
    locking = start_call('post', '/api/vault/lock')
    responses = []
    thread = threading.Thread(target=lambda: responses.append(request(method, '/api/allowlist',
        **({'json': {'words': ['late-name']}} if method == 'post' else {}))), name='late-allowlist')
    try:
        assert entered.wait(5)
        thread.start()
        assert guard.attempted.wait(5)
        assert not responses
    finally:
        release.set()
        assert finish(locking).status_code == 200
        if thread.ident is not None:
            join(thread)
    assert responses[0].status_code == 423
    assert not (store.jobs / 'allowlist.txt').exists()


def test_allowlist_failed_encryption_remains_closed_until_recovery(store, monkeypatch):
    store.enable()
    path = store.jobs / 'allowlist.txt'
    request('post', '/api/allowlist', json={'words': ['synthetic-name']})
    def partial(key, root):
        vault.encrypt_file(key, str(path))
        raise OSError('synthetic partial encryption failure')
    monkeypatch.setattr(vault, 'encrypt_tree', partial)
    assert request('post', '/api/vault/lock').status_code == 500
    assert request('get', '/api/allowlist').status_code == 423
    assert request('post', '/api/allowlist', json={'clear': True}).status_code == 423
    assert not path.exists()
    assert request('post', '/api/vault/unlock', json={'password': 'synthetic-password'}).status_code == 200
    assert request('get', '/api/allowlist').get_json()['words'] == ['synthetic-name']


@pytest.mark.parametrize('alias', [False, True])
def test_render_original_source_owned_from_queue_through_normalization_cleanup(store, monkeypatch, alias):
    store.enable()
    original = Path(store.job['video'])
    if alias:
        original = store.root / 'original-alias.avi'
        original.symlink_to(store.job['video'])
    job, report, doc = destination(store, original)
    entered, release, sources, probes = threading.Event(), threading.Event(), [], []
    real_exists = os.path.exists
    def exists(path):
        if str(path) == store.job['video']:
            probes.append(store.job['_files'].count)
        return real_exists(path)
    monkeypatch.setattr(web.os.path, 'exists', exists)
    def normalize(args, cb):
        sources.append(args.video)
        entered.set()
        assert release.wait(8)
        raise RuntimeError('stop at real pipeline normalization boundary')
    monkeypatch.setattr(openscrub, 'normalize_vfr', normalize)
    thread = None
    try:
        assert request('post', '/api/jobs/' + job['id'] + '/render').status_code == 200
        assert store.job['_files'].count == 1, 'queued render did not own actual original source'
        assert job['_files'].count == 1
        assert request('delete', store.url).status_code == 409
        old = time.time() - 3 * 86400
        os.utime(store.job['dir'], (old, old))
        web.retention_sweep(1)
        assert Path(store.job['video']).exists()
        thread = run_queued()
        assert entered.wait(5)
        assert sources == [store.job['video']]
        assert probes and min(probes) > 0, 'source stat preceded admission'
        job['phase'] = 'cancelled'
        assert request('delete', store.url).status_code == 409
        assert request('post', '/api/vault/lock').status_code == 409
        web.retention_sweep(1)
        assert Path(store.job['video']).exists()
    finally:
        release.set()
        if thread is None:
            request('post', '/api/jobs/' + job['id'] + '/cancel')
            thread = run_queued()
        join(thread)
    assert web.FILES.count == 0
    web.retention_sweep(1)
    assert not Path(store.job['video']).exists()


@pytest.mark.parametrize('original', ['self', 'self_alias', 'missing_live', 'missing_unregistered', 'external', 'external_missing'])
def test_render_source_selection_preserves_self_alias_and_missing_fallback(store, monkeypatch, original):
    job, report, doc = destination(store, store.job['video'])
    expected = job['video']
    if original == 'self':
        source = job['video']
    elif original == 'self_alias':
        source = store.root / 'self-alias.avi'
        source.symlink_to(job['video'])
    elif original == 'missing_live':
        source = Path(store.job['dir']) / 'missing-original.avi'
    elif original == 'missing_unregistered':
        source = store.jobs / 'removed-source' / 'input.avi'
    else:
        source = store.root / 'external.avi'
        if original == 'external':
            source.write_bytes(b'synthetic external original')
            expected = str(source)
    doc['provenance']['original_input'] = str(source)
    report.write_text(json.dumps(doc))
    sources = []
    def normalize(args, cb):
        sources.append(args.video)
        raise RuntimeError('selected source verified')
    monkeypatch.setattr(openscrub, 'normalize_vfr', normalize)
    assert request('post', '/api/jobs/' + job['id'] + '/render').status_code == 200
    assert job['_files'].count == 1 and not job['_files'].queued[job['qgen']].related
    assert store.job['_files'].count == 0
    join(run_queued())
    assert sources == [expected]
    assert web.FILES.count == 0


@pytest.mark.parametrize('state,code', [('unregistered', 404), ('deleting', 409)])
def test_render_rejects_extant_unregistered_or_deleting_original_without_read(store, monkeypatch, state, code):
    job, report, doc = destination(store, store.job['video'])
    if state == 'unregistered':
        web.JOBS.pop(store.job['id'])
    else:
        store.job['_files'].closed = True
    opened = []
    real_open = builtins.open
    def opening(path, *args, **kwargs):
        if str(path) == store.job['video']:
            opened.append(str(path))
        return real_open(path, *args, **kwargs)
    monkeypatch.setattr(builtins, 'open', opening)
    response = request('post', '/api/jobs/' + job['id'] + '/render')
    try:
        assert response.status_code == code
        assert job['phase'] == 'review' and web.WORK_Q.empty()
        assert not opened
    finally:
        if not web.WORK_Q.empty():
            request('post', '/api/jobs/' + job['id'] + '/cancel')
            join(run_queued())


def test_render_pins_selected_original_when_report_provenance_later_changes(store, monkeypatch):
    job, report, doc = destination(store, store.job['video'])
    other = web.new_job('', {}, 'later-original.avi')
    other_video = Path(other['dir']) / 'input.avi'
    other_video.write_bytes(b'synthetic later source')
    other.update(video=str(other_video), phase='review')
    sources = []
    def normalize(args, cb):
        sources.append(args.video)
        raise RuntimeError('selected source verified')
    monkeypatch.setattr(openscrub, 'normalize_vfr', normalize)
    assert request('post', '/api/jobs/' + job['id'] + '/render').status_code == 200
    doc['provenance']['original_input'] = str(other_video)
    report.write_text(json.dumps(doc))
    join(run_queued())
    assert sources == [store.job['video']], 'engine followed later unowned provenance'
    assert other['_files'].count == 0
    assert request('delete', '/api/jobs/' + other['id']).status_code == 200


def test_real_web_render_keeps_document_and_private_source_pin_out_of_json(store, media_review):
    Path(store.job['video']).write_bytes(media_review.video.read_bytes())
    job, report, doc = destination(store, store.job['video'])
    Path(job['video']).write_bytes(media_review.video.read_bytes())
    doc = copy.deepcopy(media_review.doc)
    doc['provenance'].update(input=job['video'], original_input=store.job['video'], vfr_normalized=True)
    report.write_text(json.dumps(doc))
    job['options'].update(encoder='x264', mode='box', pad=0)
    assert request('post', '/api/jobs/' + job['id'] + '/render').status_code == 200
    thread = run_queued()
    thread.join(30)
    assert not thread.is_alive()
    assert job['phase'] == 'done', job.get('error')
    saved = json.loads(report.read_text())
    assert_review_preserved(doc, saved)
    assert '_report_input' not in json.dumps(saved)
    assert '_report_input' not in (Path(job['dir']) / web.OPTIONS_FILE).read_text()
    assert '_report_input' not in json.dumps(request('get', '/api/jobs/' + job['id']).get_json())


def test_skip_review_normalized_scan_hands_original_owner_to_render_queue(store, monkeypatch):
    job, report, doc = destination(store, store.job['video'])
    normalized = job['video']
    job.update(video=store.job['video'], phase='queued')
    job['options']['skip_review'] = True
    def scan(args, cb):
        args.original_video = args.video
        args.video = normalized
        return dict(fps=30, cum=[[0,0]] * 30, bands=[[0,0]] * 30,
                    detections=[], stats={})
    monkeypatch.setattr(openscrub, 'run_scan', scan)
    background, real_start = [], web._start_owned_thread
    def start(*args):
        thread = real_start(*args)
        background.append(thread)
        return thread
    monkeypatch.setattr(web, '_start_owned_thread', start)
    web.enqueue(job, 'scan')
    join(run_queued())  # stop marker precedes the internally enqueued render
    for thread in background:
        join(thread)
    try:
        assert job['video'] == normalized and job['phase'] == 'queued_render'
        assert store.job['_files'].count == 1
        assert request('delete', store.url).status_code == 409
    finally:
        request('post', '/api/jobs/' + job['id'] + '/cancel')
        join(run_queued())
    assert web.FILES.count == 0


@pytest.mark.parametrize('source', ['original', 'alias', 'missing'])
def test_unpinned_engine_keeps_default_original_selection(store, monkeypatch, source):
    original = Path(store.job['video'])
    if source == 'alias':
        original = store.root / 'cli-original-alias.avi'
        original.symlink_to(store.job['video'])
    elif source == 'missing':
        original = store.jobs / 'absent' / 'input.avi'
    job, report, doc = destination(store, original)
    args = web.build_args(job, for_render=True)
    assert not hasattr(args, '_report_input')
    sources = []
    def normalize(args, cb):
        sources.append(args.video)
        raise RuntimeError('ordinary engine source selected')
    monkeypatch.setattr(openscrub, 'normalize_vfr', normalize)
    with pytest.raises(RuntimeError, match='ordinary engine source selected'):
        openscrub.run_pipeline(args)
    assert sources == [job['video'] if source == 'missing' else str(original)]


@pytest.mark.parametrize('report_state', ['missing', 'invalid'])
def test_missing_or_invalid_report_keeps_async_render_error_behavior(store, report_state):
    job, report, doc = destination(store, store.job['video'])
    if report_state == 'missing':
        report.unlink()
    else:
        report.write_text('{invalid synthetic report')
    job['phase'] = 'error'
    assert request('post', '/api/jobs/' + job['id'] + '/render').status_code == 200
    join(run_queued())
    assert job['phase'] == 'error' and job['error']
    assert web.FILES.count == 0
