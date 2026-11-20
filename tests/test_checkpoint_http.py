"""Loopback HTTP exercises real checkpoint source and operation ownership."""
from contextlib import contextmanager
import json
from pathlib import Path
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from werkzeug.serving import make_server

import openscrub as core
import openscrub_web as web
from openscrub_internal import checkpoint_runtime as runtime
from test_checkpoint_bounded_review_web import recovered
from test_checkpoint_restart_web import paused_job
from test_checkpoint_web_owner import checkpoint_job, commit_for
from test_job_lifecycle import store


@contextmanager
def serving():
    server = make_server('127.0.0.1', 0, web.app, threaded=True)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        yield 'http://127.0.0.1:%d' % server.server_port
    finally:
        server.shutdown()
        thread.join(10)
        server.server_close()
        assert not thread.is_alive()


def http(url, method='GET'):
    try:
        with urlopen(Request(url, method=method), timeout=15) as response:
            return response.status, response.read()
    except HTTPError as error:
        return error.code, error.read()


def test_real_http_prefix_sample_and_changed_source(recovered):
    store, _ = recovered
    with serving() as base:
        status, body = http(base + store.url + '/detections')
        assert status == 200
        assert (json.loads(body)['duration'], json.loads(body)['processed_frames']) == (4.0, 9)
        status, body = http(base + store.url + '/edit_sample?t=' + str(8 / 6))
        assert status == 200 and json.loads(body)['sample']['index'] == 8
        assert http(base + store.url + '/edit_sample?t=1.5')[0] == 400
        with Path(web.JOBS[store.job['id']]['video']).open('ab') as stream:
            stream.write(b'changed after checkpoint')
        assert http(base + store.url + '/detections')[0] == 409


@pytest.mark.parametrize('cause', ['cancel', 'stale_generation'])
def test_real_http_cancel_or_stale_generation_fences_staged_report(checkpoint_job, monkeypatch, cause):
    store, args, owner, files, generation, operation = checkpoint_job
    before = store.path.read_bytes()
    ready, release = threading.Event(), threading.Event()
    actual_stage = runtime._staged_report
    @contextmanager
    def delayed_stage(*args, **kwargs):
        with actual_stage(*args, **kwargs) as staged:
            ready.set()
            assert release.wait(15)
            yield staged
    monkeypatch.setattr(runtime, '_staged_report', delayed_stage)
    errors = []
    def scan():
        try:
            runtime.scan_to_report(args, str(store.path),
                cb=web.WebCallbacks(store.job, operation), stop_requested=lambda: False,
                publication_lock=files.report_lock, resume=True,
                _commit_staged=commit_for(store.job, owner, generation, operation, files))
        except BaseException as error:
            errors.append(error)
    with serving() as base:
        worker = threading.Thread(target=scan)
        worker.start()
        try:
            assert ready.wait(15)
            if cause == 'cancel':
                status, body = http(base + store.url + '/cancel', method='POST')
                assert status == 200 and json.loads(body)['ok'] is True
                operation.clear()
            else:
                with files.report_lock:
                    with web.JOBS_LOCK:
                        store.job['qgen'] += 1
        finally:
            release.set()
            worker.join(15)
        assert not worker.is_alive()
    assert len(errors) == 1 and isinstance(errors[0], core.PipelineCancelled)
    assert store.path.read_bytes() == before
