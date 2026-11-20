"""Restart must preserve a partial checkpoint instead of treating it as output."""
import json
from pathlib import Path

import pytest

import openscrub_web as web
from openscrub_internal import checkpoint_runtime as runtime
from test_checkpoint_runtime import Quiet, args_for, movie, owned_scan, stop_after
from test_job_lifecycle import request, store


@pytest.fixture
def paused_job(store):
    video = movie(store.path.parent)
    store.path.unlink()
    report = owned_scan(runtime, args_for(video), str(store.path), cb=Quiet(),
                        stop_requested=stop_after(9))
    options = {'categories': 'qrcode', 'checkpoint_review': True,
               'skip_review': True, 'unknown': {'keep': 1}}
    (store.path.parent / web.OPTIONS_FILE).write_text(json.dumps(options))
    output = store.path.parent / 'output.mp4'
    output.write_bytes(b'previous rendered video')
    store.job.update(video=str(video), options=options, phase='review', output=str(output))
    return store, report, options, output


def test_restart_recognizes_partial_checkpoint_before_older_output(paused_job):
    store, report, options, output = paused_job
    before = store.path.read_bytes()
    web.JOBS.clear()
    web._rehydrate_jobs()
    job = web.JOBS[store.job['id']]
    assert job['phase'] == 'paused'
    assert job['output'] is None
    assert job['options'] == options
    status = request('get', store.url).get_json()
    assert status['phase'] == 'paused' and status['has_output'] is False
    assert request('post', store.url + '/render').status_code == 409
    assert request('post', store.url + '/retry').status_code == 409
    assert store.path.read_bytes() == before
    assert output.read_bytes() == b'previous rendered video'


@pytest.mark.parametrize('marker', [None, {'schema': 1, 'state': 'paused'}])
def test_malformed_checkpoint_never_becomes_done_or_admits_render_or_retry(paused_job, marker):
    store, report, options, output = paused_job
    report['stop_review'] = marker
    store.path.write_text(json.dumps(report))
    before = store.path.read_bytes()
    web.JOBS.clear()
    web._rehydrate_jobs()
    job = web.JOBS[store.job['id']]
    assert job['phase'] == 'error'
    assert job['output'] is None
    assert job['options'] == options
    assert 'checkpoint' in job['error'].lower()
    assert request('post', store.url + '/render').status_code == 409
    assert request('post', store.url + '/retry').status_code == 409
    assert store.path.read_bytes() == before
    assert output.read_bytes() == b'previous rendered video'


def test_live_partial_report_blocks_ordinary_render_and_retry(paused_job):
    store, report, options, output = paused_job
    before = store.path.read_bytes()
    assert request('post', store.url + '/render').status_code == 409
    store.job['phase'] = 'error'
    assert request('post', store.url + '/retry').status_code == 409
    assert store.path.read_bytes() == before


def test_live_partial_report_does_not_expose_older_output(paused_job):
    store, _, _, _ = paused_job
    assert request('get', store.url + '/download').status_code == 409
    assert request('get', store.url + '/frame_at?src=output&t=0').status_code == 409


def test_recovered_checkpoint_cannot_use_unbounded_review_api(paused_job):
    store, _, _, _ = paused_job
    before = store.path.read_bytes()
    web.JOBS.clear()
    web._rehydrate_jobs()
    assert request('post', store.url + '/detections', json={'time_overrides': {'0': [0, 3]}}).status_code == 409
    assert request('get', store.url + '/boxes_at?t=3').status_code == 409
    assert store.path.read_bytes() == before


def test_recovered_checkpoint_stays_fenced_if_report_marker_disappears(paused_job):
    store, report, _, _ = paused_job
    web.JOBS.clear()
    web._rehydrate_jobs()
    report.pop('stop_review')
    store.path.write_text(json.dumps(report))
    assert request('post', store.url + '/render').status_code == 409


def test_completed_checkpoint_without_render_does_not_adopt_older_output(paused_job):
    store, _, _, output = paused_job
    args = args_for(store.job['video'])
    completed = owned_scan(runtime, args, str(store.path), cb=Quiet(),
                           stop_requested=lambda: False, resume=True)
    assert 'stop_review' not in completed
    assert 'output' not in completed['provenance']
    web.JOBS.clear()
    web._rehydrate_jobs()
    job = web.JOBS[store.job['id']]
    assert job['phase'] == 'review'
    assert job['output'] is None
    assert request('get', store.url).get_json()['has_output'] is False
    assert output.read_bytes() == b'previous rendered video'


def test_restart_keeps_checkpoint_visible_when_source_is_missing(paused_job):
    store, _, _, _ = paused_job
    before = store.path.read_bytes()
    Path(store.job['video']).unlink()
    web.JOBS.clear()
    web._rehydrate_jobs()
    job = web.JOBS[store.job['id']]
    assert job['phase'] == 'error'
    assert job['output'] is None
    assert 'source' in job['error'].lower()
    assert request('post', store.url + '/retry').status_code == 409
    assert store.path.read_bytes() == before


def test_restart_keeps_checkpoint_with_invalid_provenance_visible(paused_job):
    store, report, _, _ = paused_job
    report['provenance'] = None
    store.path.write_text(json.dumps(report))
    before = store.path.read_bytes()
    web.JOBS.clear()
    web._rehydrate_jobs()
    job = web.JOBS[store.job['id']]
    assert job['phase'] == 'error'
    assert job['output'] is None
    assert request('get', store.url + '/report').status_code == 200
    assert store.path.read_bytes() == before


def test_output_guard_reuses_report_observation_but_not_after_replacement(paused_job, monkeypatch):
    store, report, _, _ = paused_job
    ordinary = dict(report)
    ordinary.pop('stop_review')
    store.path.write_text(json.dumps(ordinary))
    loads = []
    original = web.json.load
    def observe(stream, *args, **kwargs):
        if getattr(stream, 'name', None) == str(store.path):
            loads.append(1)
        return original(stream, *args, **kwargs)
    monkeypatch.setattr(web.json, 'load', observe)
    assert request('get', store.url + '/download').status_code == 200
    assert request('get', store.url + '/download').status_code == 200
    assert len(loads) == 1
    store.path.write_text(json.dumps(report))
    assert request('get', store.url + '/download').status_code == 409
    assert len(loads) == 2
