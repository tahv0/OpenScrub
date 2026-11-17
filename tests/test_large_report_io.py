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
