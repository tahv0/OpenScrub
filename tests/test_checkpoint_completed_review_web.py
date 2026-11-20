"""A completed native checkpoint retains exact editing after verified EOF."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

import openscrub_web as web
from openscrub_internal import checkpoint_runtime as runtime
from test_checkpoint_restart_web import paused_job
from test_checkpoint_runtime import Quiet, args_for, owned_scan, stop_after
from test_exact_samples import precondition
from test_job_lifecycle import request, store


@pytest.fixture
def completed(paused_job):
    store, _, _, _ = paused_job
    result = owned_scan(runtime, args_for(store.job['video']), str(store.path),
                        cb=Quiet(), stop_requested=lambda: False, resume=True)
    assert 'stop_review' not in result
    assert result['provenance']['checkpoint_identity']['timeline']['count_verified'] is True
    web.JOBS.clear()
    web._rehydrate_jobs()
    return store, result


def test_completed_checkpoint_supports_exact_sample_and_source_change_is_rejected(completed):
    store, _ = completed
    response = request('get', store.url + '/edit_sample?t=' + str(8 / 6))
    assert response.status_code == 200, response.get_data(as_text=True)
    assert response.get_json()['sample']['index'] == 8
    with Path(web.JOBS[store.job['id']]['video']).open('ab') as stream:
        stream.write(b'changed after verified scan')
    assert request('get', store.url + '/edit_sample?t=0').status_code in (409, 422)


@pytest.mark.parametrize('mutation', ['unverified_count', 'wrong_normalization', 'wrong_count'])
def test_completed_checkpoint_rejects_identity_that_does_not_prove_source(completed, mutation):
    store, report = completed
    assert request('get', store.url + '/edit_sample?t=0').status_code == 200
    identity = report['provenance']['checkpoint_identity']
    if mutation == 'unverified_count':
        identity['timeline']['count_verified'] = False
    elif mutation == 'wrong_normalization':
        identity['normalization']['mode'] = 'transcoded'
    else:
        identity['timeline']['total_frames'] += 1
    store.path.write_text(json.dumps(report))
    assert request('get', store.url + '/edit_sample?t=0').status_code in (409, 422)


def test_completed_checkpoint_time_edit_releases_row_bounds_and_replays(completed):
    store, report = completed
    response = request('get', store.url + '/edit_sample?t=0')
    assert response.status_code == 200
    data = response.get_json()
    row = next(item for item in data['boxes'] if item['i'] == 0)
    pc = precondition(data)
    pc['scan_frame_bounds'] = row['scan_frame_bounds']
    edits = {'geometry_preconditions': {'0': pc}, 'time_overrides': {'0': [0.0, 1.5]}}
    result = request('post', store.url + '/detections', json=edits)
    assert result.status_code == 200, result.get_data(as_text=True)
    after = json.loads(store.path.read_text())
    assert 'scan_frame_start' not in after['detections'][0]
    assert 'scan_frame_end' not in after['detections'][0]
    assert after['detections'][1:] == report['detections'][1:]
    first = store.path.read_bytes()
    replay = request('post', store.url + '/detections', json=edits)
    assert replay.status_code == 200, replay.get_data(as_text=True)
    assert store.path.read_bytes() == first


def test_completed_zero_detection_120fps_preserves_canonical_sample(store):
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
    owned_scan(runtime, args, str(store.path), cb=Quiet(), stop_requested=stop_after(200))
    result = owned_scan(runtime, args, str(store.path), cb=Quiet(),
                        stop_requested=lambda: False, resume=True)
    assert result['detections'] == []
    assert result['provenance']['checkpoint_identity']['timeline']['count_verified'] is True
    web.JOBS.clear()
    web._rehydrate_jobs()
    response = request('get', store.url + '/edit_sample?t=' + str(123 / 120))
    assert response.status_code == 200, response.get_data(as_text=True)
    assert response.get_json()['sample']['index'] == 123
    with video.open('ab') as stream:
        stream.write(b'changed zero-detection source')
    assert request('get', store.url + '/edit_sample?t=0').status_code in (409, 422)
