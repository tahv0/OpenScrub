"""A recovered checkpoint can review only its source-proven frame prefix."""
import json
import math
import os
import shutil
import subprocess
from pathlib import Path

import pytest

import openscrub_web as web
from openscrub_internal import checkpoint_runtime as runtime
from test_checkpoint_restart_web import paused_job
from test_checkpoint_runtime import Quiet, args_for, owned_scan, stop_after
from test_job_lifecycle import request, store


@pytest.fixture
def recovered(paused_job):
    store, report, _, _ = paused_job
    web.JOBS.clear()
    web._rehydrate_jobs()
    return store, report


def test_partial_review_reports_full_duration_and_rejects_uninspected_samples(recovered):
    store, _ = recovered
    result = request('get', store.url + '/detections')
    assert result.status_code == 200, result.get_data(as_text=True)
    metadata = result.get_json()
    assert metadata['duration'] == 4.0
    assert metadata['processed_duration'] == 1.5
    assert metadata['processed_frames'] == 9
    assert metadata['total_frames'] == 24
    last = request('get', store.url + '/edit_sample?t=' + str(8 / 6))
    assert last.status_code == 200, last.get_data(as_text=True)
    assert last.get_json()['sample']['index'] == 8
    assert request('get', store.url + '/edit_sample?t=1.5').status_code == 400
    assert request('get', store.url + '/edit_sample?t=3').status_code == 400


def test_changed_source_rejects_checkpoint_review_before_serving_frames(recovered):
    store, _ = recovered
    assert request('get', store.url + '/detections').status_code == 200
    source = Path(web.JOBS[store.job['id']]['video'])
    with source.open('ab') as stream:
        stream.write(b'changed after checkpoint')
    response = request('get', store.url + '/detections')
    assert response.status_code in (409, 422)
    assert request('get', store.url + '/edit_sample?t=0').status_code in (409, 422)


@pytest.mark.skipif(not hasattr(os, 'symlink'), reason='symlinks required')
def test_checkpoint_report_symlink_cannot_bypass_output_guard(paused_job):
    store, _, _, _ = paused_job
    target = store.path.with_name('checkpoint-backup.json')
    target.write_bytes(store.path.read_bytes())
    store.path.unlink()
    store.path.symlink_to(target)
    assert request('get', store.url + '/download').status_code == 409


@pytest.mark.parametrize('field,value', [('normalization', 'transcoded'), ('categories', 'face')])
def test_checkpoint_outside_native_scope_cannot_use_exact_review(recovered, field, value):
    store, report = recovered
    for identity in (report['stop_review']['options'], report['provenance']['checkpoint_identity']):
        if field == 'normalization':
            identity['normalization']['mode'] = value
        else:
            identity['effective_settings']['categories'] = value
    store.path.write_text(json.dumps(report))
    assert request('get', store.url + '/detections').status_code in (409, 422)
    assert request('get', store.url + '/edit_sample?t=0').status_code in (409, 422)


def test_sample_and_thumbnail_respect_each_rows_exclusive_frame_bounds(recovered, monkeypatch):
    store, report = recovered
    row = report['detections'][0]
    row.update(t_start=0, t_end=3, last_seen=0)
    second = dict(row, text='later authority', scan_frame_start=6, scan_frame_end=9)
    second_index = len(report['detections'])
    report['detections'].append(second)
    store.path.write_text(json.dumps(report))
    sample = request('get', store.url + '/edit_sample?t=' + str(2 / 6))
    assert sample.status_code == 200, sample.get_data(as_text=True)
    assert 0 in [box['i'] for box in sample.get_json()['boxes']]
    assert second_index not in [box['i'] for box in sample.get_json()['boxes']]
    sought = []
    original = web.thumbs.read_ordinal_capture
    def read(cap, index, **kwargs):
        sought.append(index)
        return original(cap, index, **kwargs)
    monkeypatch.setattr(web.thumbs, 'read_ordinal_capture', read)
    image = request('get', store.url + '/thumb/' + str(second_index))
    assert image.status_code == 200, image.get_data(as_text=True)
    assert sought and all(6 <= index < 9 for index in sought)


def test_future_manual_geometry_is_refused_with_row_and_span(recovered):
    store, report = recovered
    row = dict(report['detections'][0], category='manual', t_start=1.0, t_end=2.0)
    row.pop('scan_frame_start')
    row.pop('scan_frame_end')
    index = len(report['detections'])
    report['detections'].append(row)
    store.path.write_text(json.dumps(report))
    response = request('get', store.url + '/detections')
    assert response.status_code in (409, 422)
    detail = response.get_json()['detail']
    assert str(index) in detail and '1.0' in detail and '2.0' in detail


def test_unbounded_row_outside_prefix_has_no_extrapolated_thumbnail(recovered):
    store, report = recovered
    row = dict(report['detections'][0], t_start=2.0, t_end=3.0, last_seen=2.0)
    row.pop('scan_frame_start')
    row.pop('scan_frame_end')
    index = len(report['detections'])
    report['detections'].append(row)
    store.path.write_text(json.dumps(report))
    assert request('get', store.url + '/detections').status_code == 200
    response = request('get', store.url + '/thumb/' + str(index))
    assert response.status_code == 404


def test_high_rate_boundary_uses_exclusive_inspected_frame_index(store):
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        pytest.skip('stock ffmpeg and ffprobe required')
    video = Path(store.job['dir']) / 'fast.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                    'testsrc2=size=64x48:rate=120', '-frames:v', '240',
                    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-bf', '2',
                    '-y', str(video)], check=True)
    args = args_for(video)
    args.categories = 'none'
    store.path.unlink()
    paused = owned_scan(runtime, args, str(store.path), cb=Quiet(),
                        stop_requested=stop_after(200))
    assert paused['stop_review']['next_frame'] == 200
    (store.path.parent / web.OPTIONS_FILE).write_text(json.dumps({'categories': 'none'}))
    web.JOBS.clear()
    web._rehydrate_jobs()
    meta = request('get', store.url + '/detections').get_json()
    assert meta['duration'] == 2.0
    assert meta['processed_frames'] == 200
    for index in (119, 120, 123, 199):
        response = request('get', store.url + '/edit_sample?t=' + str(index / 120))
        assert response.status_code == 200, response.get_data(as_text=True)
        assert response.get_json()['sample']['index'] == index
    before_grid = math.nextafter(123 / 120, 0.0)
    assert request('get', store.url + '/edit_sample?t=' + str(before_grid)).get_json()['sample']['index'] == 122
    assert request('get', store.url + '/edit_sample?t=' + str(200 / 120)).status_code == 400
