"""Exercise the composed checkpoint lifecycle through actual loopback requests."""

import json
from pathlib import Path

import cv2

import openscrub_web as web
from test_checkpoint_web_worker import checkpoint_web, hold_after_frames
from test_exact_samples import precondition
from test_job_lifecycle import store
from test_report_transactions import join, run_worker, socket_api


def test_pause_restart_save_resume_and_render_native_source(checkpoint_web, socket_api, monkeypatch):
    state, _ = checkpoint_web
    state.job['options']['encoder'] = 'x264'
    (state.path.parent / web.OPTIONS_FILE).write_text(json.dumps(state.job['options']))
    entered, release = hold_after_frames(monkeypatch)
    web.enqueue(state.job, 'scan')
    worker = run_worker()
    try:
        assert entered.wait(12), state.job.get('error')
        assert socket_api('POST', state.url + '/stop')[0] == 202
        assert not state.path.exists()
    finally:
        release.set()
        join(worker)

    web.JOBS.clear()
    web._rehydrate_jobs()
    status = json.loads(socket_api('GET', state.url)[2])
    assert status['phase'] == 'paused' and not status['has_output']
    metadata = json.loads(socket_api('GET', state.url + '/detections')[2])
    assert (metadata['processed_frames'], metadata['total_frames']) == (7, 24)
    assert socket_api('GET', state.url + '/edit_sample?t=2')[0] == 400
    sample_code, _, sample = socket_api('GET', state.url + '/edit_sample?t=0')
    assert sample_code == 200, sample
    manual = {'manual_id': 'checkpoint-web:chosen', 't_start': 0.0, 't_end': 1.0,
              't_ref': 0.0, 'screen_box': [12, 12, 48, 48],
              'sample_precondition': precondition(json.loads(sample), None)}
    audio = {'t0': .2, 't1': .7, 'mode': 'mute'}
    code, _, body = socket_api('POST', state.url + '/detections', {
        'enabled': {'0': False}, 'manual': [manual], 'audio': [audio],
    })
    assert code == 200, body
    token = json.loads(body)['resume_token']
    before = json.loads(state.path.read_text())
    assert before['detections'][0]['enabled'] is False
    assert before['audio_redactions'] == [audio]
    assert any(row.get('manual_id') == manual['manual_id'] for row in before['detections'])

    code, _, body = socket_api('POST', state.url + '/resume', {'resume_token': token})
    assert code in (200, 202), body
    join(run_worker())
    done = json.loads(state.path.read_text())
    assert 'stop_review' not in done
    assert len(done['render_state']['cum']) == 24
    assert done['detections'][0]['enabled'] is False
    assert done['audio_redactions'] == [audio]
    assert any(row.get('manual_id') == manual['manual_id'] for row in done['detections'])
    assert json.loads(socket_api('GET', state.url)[2])['phase'] == 'review'
    code, _, body = socket_api('POST', state.url + '/render')
    assert code in (200, 202), body
    join(run_worker())
    assert json.loads(socket_api('GET', state.url)[2])['phase'] == 'done'
    output = Path(web.JOBS[state.job['id']]['output'])
    capture = cv2.VideoCapture(str(output))
    try:
        frames = 0
        while capture.grab():
            frames += 1
    finally:
        capture.release()
    assert frames == 24
