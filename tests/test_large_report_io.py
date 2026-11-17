"""Report publication regressions. All documents and video paths are synthetic."""
import json
import os
from pathlib import Path
import threading
from types import SimpleNamespace

import pytest

import openscrub
import openscrub_web as web
from openscrub_internal import reports


@pytest.fixture
def review(tmp_path, monkeypatch):
    jobs = tmp_path / 'jobs'
    folder = jobs / 'synthetic'
    folder.mkdir(parents=True)
    video = folder / 'input.avi'
    video.write_bytes(b'synthetic input placeholder')
    doc = {
        'provenance': {'input': str(video), 'settings': {}},
        'render_state': {'fps': 30, 'cum': [[0, 0]] * 30, 'bands': [[0, 0]] * 30},
        'detections': [dict(t_start=0, t_end=1, cbox=[1, 2, 8, 9],
                            category='name', text='synthetic', confidence=.9,
                            aoff=[0, 0], last_seen=.5, enabled=True)] * 2,
        'audio_redactions': [{'t0': .1, 't1': .2, 'mode': 'mute'}],
        'custom_future_field': {'preserved': True},
    }
    path = folder / 'report.json'
    path.write_text(json.dumps(doc, indent=1), encoding='utf-8')
    monkeypatch.setattr(web, 'JOBS', {'synthetic': {'dir': str(folder),
                        'video': str(video), 'log': [],
                        'cancel': threading.Event()}})
    monkeypatch.setattr(web, 'JOBS_DIR', str(jobs))
    monkeypatch.setattr(web, 'TOKEN', None)
    monkeypatch.setattr(web, 'vault_locked', lambda: False)
    monkeypatch.setitem(web.app.config, 'TESTING', False)
    monkeypatch.setitem(web.app.config, 'PROPAGATE_EXCEPTIONS', False)
    return SimpleNamespace(path=path, doc=doc, client=web.app.test_client())


@pytest.mark.parametrize('failure', ['encoding', 'write'])
def test_failed_report_write_preserves_previous_bytes(review, monkeypatch, failure):
    """Opening/truncating the final destination before JSON completes loses work."""
    previous = review.path.read_bytes()
    def fail(doc, stream, **kwargs):
        if failure == 'write':
            stream.write('{"interrupted":')
            raise OSError('injected write failure')
        raise TypeError('injected encoding failure')
    monkeypatch.setattr(reports, 'json', SimpleNamespace(dump=fail, load=json.load))
    response = review.client.post('/api/jobs/synthetic/detections',
                                  json={'enabled': {'0': False}})
    assert response.status_code == 500
    assert review.path.read_bytes() == previous
    assert json.loads(previous) == review.doc
    web.JOBS.clear()
    web.rehydrate_jobs()
    assert web.JOBS['synthetic']['phase'] == 'review'
    assert review.client.get('/api/jobs/synthetic/detections').status_code == 200
    assert not list(review.path.parent.glob('*.tmp'))


@pytest.mark.parametrize('failure', ['flush', 'fsync', 'replace'])
def test_failed_report_sync_or_replace_preserves_previous_bytes(review, monkeypatch, failure):
    previous = review.path.read_bytes()
    def fail(*args, **kwargs):
        raise OSError('injected ' + failure + ' failure')
    if failure == 'flush':
        original = reports.tempfile.NamedTemporaryFile
        def open_temp(*args, **kwargs):
            stream = original(*args, **kwargs)
            monkeypatch.setattr(stream, 'flush', fail)
            return stream
        monkeypatch.setattr(reports.tempfile, 'NamedTemporaryFile', open_temp)
    else:
        monkeypatch.setattr(reports.os, failure, fail)
    response = review.client.post('/api/jobs/synthetic/detections',
                                  json={'enabled': {'0': False}})
    assert response.status_code == 500
    assert review.path.read_bytes() == previous
    assert not list(review.path.parent.glob('*.tmp'))
    # Restart discovery must recover a reviewable, parseable old report.
    web.JOBS.clear()
    web.rehydrate_jobs()
    assert web.JOBS['synthetic']['phase'] == 'review'
    assert review.client.get('/api/jobs/synthetic/detections').status_code == 200


def test_save_acknowledges_only_after_publish(review, monkeypatch):
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    previous = review.path.read_bytes()
    replace = reports.os.replace
    result = []
    def pause(source, dest):
        # The staged document is complete, private, and closed before replacement.
        with open(source, encoding='utf-8') as stream:
            assert json.load(stream)['detections'][0]['enabled'] is False
        assert Path(source).parent == review.path.parent
        assert str(source).endswith('.tmp')
        if os.name != 'nt':
            assert os.stat(source).st_mode & 0o777 == 0o600
        entered.set()
        assert release.wait(5)
        replace(source, dest)
    monkeypatch.setattr(reports.os, 'replace', pause)
    def save():
        try:
            with web.app.test_client() as client:
                result.append(client.post('/api/jobs/synthetic/detections',
                              json={'enabled': {'0': False, '1': False}}))
        finally:
            finished.set()
    thread = threading.Thread(target=save)
    thread.start()
    try:
        assert entered.wait(5)
        assert not finished.is_set()
        assert review.path.read_bytes() == previous
        release.set()
        assert finished.wait(5)
    finally:
        release.set()
        thread.join(5)
    assert result[0].status_code == 200
    assert result[0].get_json() == {'ok': True, 'total': 2,
                                  'suggest_allowlist': ['synthetic']}
    doc = json.loads(review.path.read_bytes())
    assert [row['enabled'] for row in doc['detections']] == [False, False]
    assert doc['audio_redactions'] == review.doc['audio_redactions']
    assert doc['custom_future_field'] == {'preserved': True}
    assert not list(review.path.parent.glob('*.tmp'))


def test_clean_first_publication_is_private_and_complete(tmp_path):
    path = tmp_path / 'first.json'
    reports.atomic_report(path, {'synthetic': '\u2603', 'rows': [True, None, 1.25]})
    assert json.loads(path.read_bytes()) == {'synthetic': '\u2603', 'rows': [True, None, 1.25]}
    if os.name != 'nt':
        assert path.stat().st_mode & 0o777 == 0o600
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize('failed', [False, True])
def test_engine_report_publication(review, monkeypatch, failed):
    old = review.path.read_bytes()
    parser = openscrub.build_parser()
    args = parser.parse_args([str(review.path.parent / 'input.avi')])
    state = dict(fps=30, cum=[(1.23, 4.56)], bands=[(0, 0)], detections=[],
                 audio_transcript=[{'start': 0, 'end': 1, 'text': 'synthetic'}])
    if failed:
        def fail(*args):
            raise OSError('injected replace failure')
        monkeypatch.setattr(reports.os, 'replace', fail)
        with pytest.raises(OSError, match='injected'):
            openscrub.write_report(review.path, args, state)
        assert review.path.read_bytes() == old
    else:
        openscrub.write_report(review.path, args, state)
        doc = json.loads(review.path.read_bytes())
        assert doc['render_state'] == {'fps': 30, 'cum': [[1.2, 4.6]], 'bands': [[0, 0]]}
        assert doc['detections'] == []
        assert doc['audio_transcript'] == state['audio_transcript']
        assert doc['provenance']['tool'] == 'openscrub'
    assert not list(review.path.parent.glob('*.tmp'))


@pytest.mark.parametrize('failed', [False, True])
def test_background_tracking_publication(review, monkeypatch, failed):
    old = review.path.read_bytes()
    # Model discovery/inference is outside publication; no model files/network.
    monkeypatch.setattr(web, 'load_model_select', lambda: {})
    monkeypatch.setattr(openscrub, 'PersonDetector', lambda *a, **kw: None)
    monkeypatch.setattr(openscrub, 'track_manual_region',
                        lambda *a, **kw: [(0.5, [2, 3, 9, 10], .9)])
    if failed:
        def fail(*args):
            raise OSError('injected tracking replace failure')
        monkeypatch.setattr(reports.os, 'replace', fail)
    # Keep the actual background execution and await its completion deterministically.
    real_thread = threading.Thread
    threads = []
    def thread_factory(*args, **kwargs):
        thread = real_thread(*args, **kwargs)
        threads.append(thread)
        return thread
    monkeypatch.setattr(web.threading, 'Thread', thread_factory)
    response = review.client.post('/api/jobs/synthetic/track_object',
                    json={'box': [2, 3, 9, 10], 't_ref': .5, 't0': 0, 't1': 1})
    assert response.status_code == 200  # existing asynchronous acceptance semantics
    for thread in threads:
        thread.join(5)
        assert not thread.is_alive()
    status = review.client.get('/api/jobs/synthetic/track_status').get_json()
    assert status['state'] == 'done'
    if failed:
        assert status['added'] == 0
        assert 'injected' in status['error']
        assert review.path.read_bytes() == old
    else:
        assert status['added'] == 1 and status['error'] is None
        doc = json.loads(review.path.read_bytes())
        assert len(doc['detections']) == 3
        assert doc['detections'][-1]['track'] == 0
        assert doc['detections'][-1]['dense'] is True
        assert doc['custom_future_field'] == {'preserved': True}
    assert not list(review.path.parent.glob('*.tmp'))


@pytest.mark.parametrize('exists', [False, True])
def test_real_encoding_failure_cleans_staging_file(tmp_path, exists):
    path = tmp_path / 'report.json'
    if exists:
        path.write_bytes(b'{"previous": true}')
    with pytest.raises(TypeError):
        reports.atomic_report(path, {'invalid': object()})
    if exists:
        assert path.read_bytes() == b'{"previous": true}'
    else:
        assert not path.exists()
    assert not list(tmp_path.glob('*.tmp'))


@pytest.fixture
def report_work(monkeypatch):
    """Count report operations; encoder_chunks counts encoder pieces."""
    counts = dict(parse=0, dump=0, stage=0, fsync=0, replace=0, encoder_chunks=0)
    load, encoder = web._load_job_report, json.JSONEncoder
    def parse(job):
        counts['parse'] += 1
        return load(job)
    def encode(**kwargs):
        counts['dump'] += 1
        instance = encoder(**kwargs)
        original = instance.iterencode
        def chunks(doc):
            for value in original(doc):
                counts['encoder_chunks'] += 1  # Encoder pieces, not OS syscalls.
                yield value
        instance.iterencode = chunks
        return instance
    monkeypatch.setattr(web, '_load_job_report', parse)
    monkeypatch.setattr(reports, 'json', SimpleNamespace(JSONEncoder=encode))
    for owner, name, key in [(reports.tempfile, 'NamedTemporaryFile', 'stage'),
                             (reports.os, 'fsync', 'fsync'),
                             (reports.os, 'replace', 'replace')]:
        original = getattr(owner, name)
        def count(*args, _original=original, _key=key, **kwargs):
            counts[_key] += 1
            return _original(*args, **kwargs)
        monkeypatch.setattr(owner, name, count)
    return counts


def file_snapshot(path):
    stat = path.stat()
    return (path.read_bytes(), stat.st_dev, stat.st_ino, stat.st_mtime_ns,
            stat.st_ctime_ns, stat.st_mode)


def finite_review(review):
    doc = json.loads(review.path.read_bytes())
    for row in doc['detections']:
        row.update(t_start=0., t_end=1., cbox=[1., 2., 8., 9.])
    return doc


@pytest.mark.parametrize('canonical', [False, True])
@pytest.mark.parametrize('edits', [
    {}, {'enabled': {'0': 'false', '1': True}},
    {'box_overrides': {'0': ['1', 2, 8., 9]}},
    {'time_overrides': {'0': ['0', 1]}},
    {'audio': [{'t0': '.1', 't1': '.2', 'mode': 'unsupported', 'ignored': True}]},
    {'enabled': {'00': False, '-1': False, '999': False},
     'box_overrides': {'999': None, '0': [1]},
     'time_overrides': {'-1': None, '0': [1, 0]}},
    {'box_overrides': {'0': [4, 5, 6, 7], '00': [1, 2, 8, 9]},
     'time_overrides': {'0': [.1, .9], '00': [0, 1]}},
])
def test_unchanged_save_preserves_exact_file_and_skips_publication(review, report_work, canonical, edits):
    # Unconditional publication loses metadata even for byte-identical JSON.
    doc = finite_review(review)
    review.path.write_text(json.dumps(doc, indent=1 if canonical else None))
    if os.name != 'nt':
        review.path.chmod(0o640)
    os.utime(review.path, ns=(1000000000, 2000000000))
    before = file_snapshot(review.path)
    response = review.client.post('/api/jobs/synthetic/detections', json=edits)
    assert response.status_code == 200
    assert response.json == {'ok': True, 'total': 2, 'suggest_allowlist': []}
    assert file_snapshot(review.path) == before
    assert report_work == dict(parse=1, dump=0, stage=0, fsync=0, replace=0, encoder_chunks=0)
    assert web.FILES.count == 0


@pytest.mark.parametrize('case', [
    'missing_enabled', 'numeric_enabled', 'integer_box', 'integer_time',
    'negative_zero_box', 'negative_zero_time', 'missing_last_seen', 'clamped_last_seen',
    'missing_audio', 'audio_extra', 'audio_bool', 'audio_int', 'audio_negative_zero',
    'nonfinite_box', 'nonfinite_audio', 'sparse', 'combined', 'legacy_manual',
])
def test_effective_changes_publish_once_with_raw_fields_preserved(review, report_work, case):
    doc = finite_review(review)
    row = doc['detections'][0]
    edits = {}
    if case == 'missing_enabled':
        del row['enabled']; edits = {'enabled': {'0': True}}
    elif case == 'numeric_enabled':
        row['enabled'] = 1; edits = {'enabled': {'0': True}}
    elif case == 'integer_box':
        row['cbox'] = [1, 2, 8, 9]; edits = {'box_overrides': {'0': [1, 2, 8, 9]}}
    elif case == 'integer_time':
        row.update(t_start=0, t_end=1); edits = {'time_overrides': {'0': [0, 1]}}
    elif case == 'negative_zero_box':
        row['cbox'][0] = -0.; edits = {'box_overrides': {'0': [0., 2., 8., 9.]}}
    elif case == 'negative_zero_time':
        row['t_start'] = -0.; edits = {'time_overrides': {'0': [0., 1.]}}
    elif case in ('missing_last_seen', 'clamped_last_seen'):
        if case == 'missing_last_seen': del row['last_seen']
        else: row['last_seen'] = 2.
        edits = {'time_overrides': {'0': [0., 1.]}}
    elif case == 'missing_audio':
        del doc['audio_redactions']; edits = {'audio': []}
    elif case == 'audio_extra':
        doc['audio_redactions'][0]['future'] = {'nested': [True, 1, 1.]}
        edits = {'audio': [{'t0': .1, 't1': .2}]}
    elif case in ('audio_bool', 'audio_int', 'audio_negative_zero'):
        value = {'audio_bool': False, 'audio_int': 0, 'audio_negative_zero': -0.}[case]
        doc['audio_redactions'] = [{'t0': value, 't1': 1., 'mode': 'mute'}]
        edits = {'audio': [{'t0': 0., 't1': 1.}]}
    elif case == 'nonfinite_box':
        row['cbox'][0] = float('inf'); edits = {'box_overrides': {'0': [float('inf'), 2, 8, 9]}}
    elif case == 'nonfinite_audio':
        doc['audio_redactions'][0]['t1'] = float('inf')
        edits = {'audio': doc['audio_redactions']}
    elif case == 'sparse': edits = {'enabled': {'0': False}}
    elif case == 'combined':
        edits = {'enabled': {'0': False, '1': False}, 'box_overrides': {'0': [2,3,9,10]},
                 'time_overrides': {'0': [.2, 2]}, 'audio': []}
    elif case == 'legacy_manual':
        edits = {'manual': [{'t_start': 0, 't_end': 1, 'screen_box': [1,2,8,9]}]}
    doc['unknown'] = {'ordered': [None, True, 1, 1., {'motion': [[1,2],[3,4]]}]}
    doc['audio_transcript'] = [{'text': 'raw synthetic', 'future': [0,False]}]
    review.path.write_text(json.dumps(doc, indent=1))
    before = review.path.read_bytes()
    response = review.client.post('/api/jobs/synthetic/detections', json=edits)
    assert response.status_code == 200
    after = json.loads(review.path.read_bytes())
    assert report_work['parse'] == report_work['dump'] == report_work['stage'] == report_work['fsync'] == report_work['replace'] == 1
    assert report_work['encoder_chunks'] > 0  # Encoder chunks, not Python writes or syscalls.
    assert after['unknown'] == doc['unknown']
    assert after['audio_transcript'] == doc['audio_transcript']
    assert after['render_state'] == doc['render_state']
    assert review.path.read_bytes() == json.dumps(after, indent=1).encode()
    if not case.startswith('nonfinite'):
        assert review.path.read_bytes() != before
    if case == 'combined':
        assert after['detections'][0]['cbox'] == [2.,3.,9.,10.]
        assert after['detections'][0]['last_seen'] == .5
        assert after['audio_redactions'] == []
        assert response.json['suggest_allowlist'] == ['synthetic']
    if case == 'audio_extra': assert set(after['audio_redactions'][0]) == {'t0','t1','mode'}
    assert web.FILES.count == 0


def test_replay_only_skips_but_replay_edit_publishes_and_conflict_rejects(review, report_work):
    manual = {'manual_id': 'draw:one', 't_start': 0, 't_end': 1, 'screen_box': [2,3,8,9]}
    url = '/api/jobs/synthetic/detections'
    assert review.client.post(url, json={'manual': [manual]}).status_code == 200
    before = file_snapshot(review.path)
    for key in report_work: report_work[key] = 0
    assert review.client.post(url, json={'manual': [manual, manual]}).json['total'] == 3
    assert file_snapshot(review.path) == before
    assert report_work['parse'] == 1 and report_work['replace'] == report_work['dump'] == 0
    assert review.client.post(url, json={'manual': [manual], 'enabled': {'2': False}}).status_code == 200
    assert report_work['replace'] == 1
    current = file_snapshot(review.path)
    assert review.client.post(url, json={'manual': [dict(manual, t_end=2)], 'enabled': {'0': False}}).status_code == 409
    assert file_snapshot(review.path) == current
    assert report_work['replace'] == 1
    assert review.client.post(url, json={'manual': [dict(manual, manual_id='draw:two')]}).json['total'] == 4
    assert report_work['replace'] == 2


@pytest.mark.parametrize('broken,edits,status', [
    ('missing', {}, 404), ('malformed', {}, 500), ('no_render_state', {}, 500),
    ('no_detections', {}, 500), (None, {'enabled': None}, 500),
    (None, {'box_overrides': {'bad': [1,2,8,9]}}, 500),
    (None, {'time_overrides': {'0': ['bad',1]}}, 500),
    (None, {'manual': [{'manual_id': None}]}, 400),
])
def test_noop_candidates_still_parse_and_validate(review, report_work, broken, edits, status):
    if broken == 'missing': review.path.unlink()
    elif broken == 'malformed': review.path.write_bytes(b'{')
    elif broken:
        doc = finite_review(review); del doc[broken[3:]]
        review.path.write_text(json.dumps(doc))
    before = review.path.read_bytes() if review.path.exists() else None
    assert review.client.post('/api/jobs/synthetic/detections', json=edits).status_code == status
    assert report_work['parse'] == 1 and report_work['replace'] == report_work['dump'] == 0
    assert (review.path.read_bytes() if review.path.exists() else None) == before
    assert web.FILES.count == 0


def test_failed_change_releases_waiting_noop_to_fresh_snapshot(review, monkeypatch, report_work):
    from test_report_transactions import ObservedLock
    from test_job_lifecycle import start_call, finish
    lock = ObservedLock()
    web.FILES.initialize(web.JOBS['synthetic']).report_lock = lock
    entered, release = threading.Event(), threading.Event()
    def fail(*args):
        entered.set()
        assert release.wait(5)
        raise OSError('injected replacement failure')
    monkeypatch.setattr(reports.os, 'replace', fail)
    before = file_snapshot(review.path)
    first = start_call('post', '/api/jobs/synthetic/detections', json={'enabled': {'0': False}})
    second = None
    try:
        assert entered.wait(5)
        second = start_call('post', '/api/jobs/synthetic/detections', json={})
        assert lock.waiting.wait(5)
    finally:
        release.set()
        assert finish(first).status_code == 500
        if second: assert finish(second).status_code == 200
    assert report_work['parse'] == 2 and report_work['dump'] == 1
    assert file_snapshot(review.path) == before
    assert web.FILES.count == 0


@pytest.mark.parametrize('present', [False, True])
def test_omitted_audio_stays_absent_or_empty_and_explicit_empty_is_acknowledged(review, report_work, present):
    doc = finite_review(review)
    if present: doc['audio_redactions'] = []
    else: del doc['audio_redactions']
    review.path.write_text(json.dumps(doc))
    before = file_snapshot(review.path)
    assert review.client.post('/api/jobs/synthetic/detections', json={}).status_code == 200
    assert file_snapshot(review.path) == before
    if present:
        assert review.client.post('/api/jobs/synthetic/detections', json={'audio': [{'t0': 1, 't1': 0}]}).status_code == 200
        assert file_snapshot(review.path) == before
    assert report_work['dump'] == 0


def test_alias_time_restoration_still_publishes_effective_last_seen_clamp(review, report_work):
    doc = finite_review(review)
    review.path.write_text(json.dumps(doc))
    response = review.client.post('/api/jobs/synthetic/detections', json={
        'time_overrides': {'0': [.7,.9], '00': [0.,1.]}})
    assert response.status_code == 200
    assert json.loads(review.path.read_bytes())['detections'][0]['last_seen'] == .7
    assert report_work['replace'] == 1


def test_noop_response_uses_each_fresh_report(review, report_work):
    url = '/api/jobs/synthetic/detections'
    assert review.client.post(url, json={}).json['suggest_allowlist'] == []
    doc = finite_review(review)
    for row in doc['detections']: row['enabled'] = False
    doc['future'] = {'unusual_but_untouched': float('nan')}
    review.path.write_text(json.dumps(doc, separators=(',', ':')))
    before = file_snapshot(review.path)
    assert review.client.post(url, json={}).json['suggest_allowlist'] == ['synthetic']
    assert file_snapshot(review.path) == before
    assert report_work['parse'] == 2 and report_work['dump'] == 0
