"""Checkpoint edits retain raw choices and require inspected-source authority."""
import copy
from contextlib import contextmanager
import json
import os
from pathlib import Path
import threading

import pytest
import openscrub_web as web
from test_checkpoint_bounded_review_web import recovered
from test_checkpoint_restart_web import paused_job
from test_exact_samples import precondition
from test_job_lifecycle import finish, request, start_call, store
from openscrub_internal.reports import atomic_report


def test_checkpoint_save_ack_preserves_unknown_rows_audio_and_noop_bytes(recovered):
    store, report = recovered
    report['detections'][0]['opaque'] = {'keep': [1, 2]}
    report['audio_redactions'] = [{'t0': .2, 't1': .7, 'mode': 'mute', 'future': True}]
    report['extra'] = {'keep': True}
    store.path.write_text(json.dumps(report))
    changed = request('post', store.url + '/detections', json={'enabled': {'0': False}})
    assert changed.status_code == 200, changed.get_data(as_text=True)
    token = changed.get_json()['resume_token']
    assert isinstance(token, str) and token
    saved = json.loads(store.path.read_text())
    expected = copy.deepcopy(report)
    expected['detections'][0]['enabled'] = False
    assert saved == expected
    before = store.path.read_bytes()
    replay = request('post', store.url + '/detections', json={'enabled': {'0': False}})
    assert replay.status_code == 200
    assert replay.get_json()['resume_token'] == token
    assert store.path.read_bytes() == before


def test_checkpoint_save_fails_after_source_changes_even_for_enabled_only(recovered):
    store, _ = recovered
    assert request('post', store.url + '/detections', json={'enabled': {'0': False}}).status_code == 200
    before = store.path.read_bytes()
    with Path(web.JOBS[store.job['id']]['video']).open('ab') as stream:
        stream.write(b'changed source')
    assert request('post', store.url + '/detections', json={'enabled': {'0': True}}).status_code == 409
    assert store.path.read_bytes() == before


@pytest.mark.skipif(not hasattr(os, 'symlink'), reason='symlinks required')
def test_checkpoint_save_refuses_symlink_report_without_replacing_it(recovered):
    store, _ = recovered
    backup = store.path.with_name('partial-backup.json')
    backup.write_bytes(store.path.read_bytes())
    store.path.unlink()
    store.path.symlink_to(backup)
    before = backup.read_bytes()
    assert request('post', store.url + '/detections', json={'enabled': {'0': False}}).status_code == 409
    assert store.path.is_symlink()
    assert backup.read_bytes() == before


def test_checkpoint_save_does_not_replace_report_changed_during_staging(recovered, monkeypatch):
    store, report = recovered
    staged, release = threading.Event(), threading.Event()
    actual = web._staged_report
    @contextmanager
    def delay(*args, **kwargs):
        with actual(*args, **kwargs) as path:
            staged.set()
            assert release.wait(10)
            yield path
    monkeypatch.setattr(web, '_staged_report', delay)
    call = start_call('post', store.url + '/detections', json={'enabled': {'0': False}})
    try:
        assert staged.wait(10)
        report['external_choice'] = {'keep': True}
        atomic_report(str(store.path), report)
        latest = store.path.read_bytes()
    finally:
        release.set()
        response = finish(call)
    assert response.status_code == 409
    assert store.path.read_bytes() == latest


def test_checkpoint_save_does_not_publish_when_source_changes_during_staging(recovered, monkeypatch):
    store, _ = recovered
    before = store.path.read_bytes()
    staged, release = threading.Event(), threading.Event()
    actual = web._staged_report
    @contextmanager
    def delay(*args, **kwargs):
        with actual(*args, **kwargs) as path:
            staged.set()
            assert release.wait(10)
            yield path
    monkeypatch.setattr(web, '_staged_report', delay)
    call = start_call('post', store.url + '/detections', json={'enabled': {'0': False}})
    try:
        assert staged.wait(10)
        with Path(web.JOBS[store.job['id']]['video']).open('ab') as stream:
            stream.write(b'source changed during staging')
    finally:
        release.set()
        response = finish(call)
    assert response.status_code == 409
    assert store.path.read_bytes() == before


def test_checkpoint_noop_does_not_acknowledge_a_newer_report(recovered, monkeypatch):
    store, _ = recovered
    actual = web._checkpoint_resume_token_locked
    def replaced(job):
        latest = json.loads(store.path.read_text())
        latest['external_choice'] = True
        atomic_report(str(store.path), latest)
        return actual(job)
    monkeypatch.setattr(web, '_checkpoint_resume_token_locked', replaced)
    response = request('post', store.url + '/detections', json={})
    assert response.status_code == 409
    assert json.loads(store.path.read_text())['external_choice'] is True


def test_checkpoint_noop_does_not_acknowledge_a_changed_source(recovered, monkeypatch):
    store, _ = recovered
    before = store.path.read_bytes()
    actual = web._checkpoint_resume_token_locked
    def changed(job):
        with Path(job['video']).open('ab') as stream:
            stream.write(b'source changed before ACK')
        return actual(job)
    monkeypatch.setattr(web, '_checkpoint_resume_token_locked', changed)
    response = request('post', store.url + '/detections', json={})
    assert response.status_code == 409
    assert store.path.read_bytes() == before


def test_changed_checkpoint_save_reports_uncertain_ack_if_report_is_replaced(recovered, monkeypatch):
    store, _ = recovered
    actual = web._checkpoint_resume_token_locked
    def replaced(job):
        latest = json.loads(store.path.read_text())
        latest['external_choice'] = True
        atomic_report(str(store.path), latest)
        return actual(job)
    monkeypatch.setattr(web, '_checkpoint_resume_token_locked', replaced)
    response = request('post', store.url + '/detections', json={'enabled': {'0': False}})
    assert response.status_code >= 500
    latest = json.loads(store.path.read_text())
    assert latest['external_choice'] is True
    assert latest['detections'][0]['enabled'] is False


def test_checkpoint_audio_edit_keeps_unknown_fields_on_unchanged_spans(recovered):
    store, report = recovered
    kept = {'t0': 0.2, 't1': 0.7, 'mode': 'mute', 'future': {'keep': True}}
    tail = {'t0': 2.0, 't1': 3.0, 'mode': 'bleep', 'future': {'preserve': True}}
    report['audio_redactions'] = [kept, tail]
    store.path.write_text(json.dumps(report))
    edits = {'audio': [{'t0': 0.2, 't1': 0.7, 'mode': 'mute'},
                       {'t0': 0.9, 't1': 1.0, 'mode': 'bleep'}]}
    response = request('post', store.url + '/detections', json=edits)
    assert response.status_code == 200, response.get_data(as_text=True)
    saved = json.loads(store.path.read_text())
    assert saved['audio_redactions'] == [kept, {'t0': 0.9, 't1': 1.0, 'mode': 'bleep'}, tail]
    before = store.path.read_bytes()
    future = request('post', store.url + '/detections', json={'audio': [{'t0': 1.0, 't1': 2.0, 'mode': 'mute'}]})
    assert future.status_code == 400
    assert store.path.read_bytes() == before


def test_checkpoint_strict_manual_replay_and_future_rejection(recovered):
    store, _ = recovered
    response = request('get', store.url + '/edit_sample?t=0')
    assert response.status_code == 200
    pc = precondition(response.get_json(), None)
    manual = {'manual_id': 'checkpoint:one', 't_start': 0.0, 't_end': 1.0,
              't_ref': 0.0, 'screen_box': [20, 20, 50, 50], 'sample_precondition': pc}
    result = request('post', store.url + '/detections', json={'manual': [manual]})
    assert result.status_code == 200, result.get_data(as_text=True)
    first = store.path.read_bytes()
    saved = json.loads(first)
    manual_rows = [row for row in saved['detections'] if row.get('manual_id') == 'checkpoint:one']
    assert len(manual_rows) == 1 and manual_rows[0]['t_end'] == 1.0
    assert 'scan_frame_start' not in manual_rows[0]
    assert request('post', store.url + '/detections', json={'manual': [manual]}).status_code == 200
    assert store.path.read_bytes() == first
    future = dict(manual, manual_id='checkpoint:future', t_end=2.0)
    assert request('post', store.url + '/detections', json={'manual': [future]}).status_code == 400
    assert store.path.read_bytes() == first


def test_checkpoint_time_edit_relinquishes_only_that_row_and_replays(recovered):
    store, report = recovered
    response = request('get', store.url + '/edit_sample?t=0')
    assert response.status_code == 200
    data = response.get_json()
    row = next(item for item in data['boxes'] if item['i'] == 0)
    pc = precondition(data)
    pc['scan_frame_bounds'] = row['scan_frame_bounds']
    edits = {'geometry_preconditions': {'0': pc}, 'time_overrides': {'0': [0.0, 1.0]}}
    result = request('post', store.url + '/detections', json=edits)
    assert result.status_code == 200, result.get_data(as_text=True)
    ack = result.get_json()['geometry_rows']['0']
    assert ack['scan_frame_bounds'] is None
    assert ack['row_context_eq'] != pc['row_context_eq']
    assert ack['base']['span'][:2] == [0.0, 1.0]
    saved = json.loads(store.path.read_text())
    assert 'scan_frame_start' not in saved['detections'][0]
    assert 'scan_frame_end' not in saved['detections'][0]
    assert saved['detections'][1:] == report['detections'][1:]
    first = store.path.read_bytes()
    replay = request('post', store.url + '/detections', json=edits)
    assert replay.status_code == 200, replay.get_data(as_text=True)
    assert store.path.read_bytes() == first
    saved['detections'][0]['text'] = 'concurrent change'
    store.path.write_text(json.dumps(saved))
    newer = store.path.read_bytes()
    assert request('post', store.url + '/detections', json=edits).status_code == 409
    assert store.path.read_bytes() == newer


def test_checkpoint_box_edit_and_replay_keep_original_frame_bounds(recovered):
    store, _ = recovered
    data = request('get', store.url + '/edit_sample?t=0').get_json()
    row = next(item for item in data['boxes'] if item['i'] == 0)
    pc = precondition(data)
    pc['scan_frame_bounds'] = row['scan_frame_bounds']
    box = list(pc['base']['cbox'])
    box[0] += 1
    edits = {'geometry_preconditions': {'0': pc}, 'box_overrides': {'0': box},
             'enabled': {'0': False}}
    response = request('post', store.url + '/detections', json=edits)
    assert response.status_code == 200, response.get_data(as_text=True)
    saved = json.loads(store.path.read_text())
    assert [saved['detections'][0]['scan_frame_start'],
            saved['detections'][0]['scan_frame_end']] == pc['scan_frame_bounds']
    first = store.path.read_bytes()
    assert request('post', store.url + '/detections', json=edits).status_code == 200
    assert store.path.read_bytes() == first


def test_checkpoint_unchanged_time_replay_retains_frame_bounds(recovered):
    store, _ = recovered
    data = request('get', store.url + '/edit_sample?t=0').get_json()
    row = next(item for item in data['boxes'] if item['i'] == 0)
    pc = precondition(data)
    pc['scan_frame_bounds'] = row['scan_frame_bounds']
    span = pc['base']['span'][:2]
    assert span[1] > span[0]
    before = store.path.read_bytes()
    edits = {'geometry_preconditions': {'0': pc}, 'time_overrides': {'0': span}}
    assert request('post', store.url + '/detections', json=edits).status_code == 200
    assert store.path.read_bytes() == before


def test_checkpoint_geometry_rejects_changed_frame_authority(recovered):
    store, report = recovered
    data = request('get', store.url + '/edit_sample?t=0').get_json()
    row = next(item for item in data['boxes'] if item['i'] == 0)
    pc = precondition(data)
    pc['scan_frame_bounds'] = row['scan_frame_bounds']
    report['detections'][0]['scan_frame_start'] = 1
    store.path.write_text(json.dumps(report))
    before = store.path.read_bytes()
    edits = {'geometry_preconditions': {'0': pc}, 'time_overrides': {'0': [0.0, 1.0]}}
    assert request('post', store.url + '/detections', json=edits).status_code == 409
    assert store.path.read_bytes() == before


def test_checkpoint_rejects_legacy_or_future_geometry_without_mutation(recovered):
    store, _ = recovered
    before = store.path.read_bytes()
    response = request('post', store.url + '/detections', json={'time_overrides': {'0': [0.0, 1.0]}})
    assert response.status_code == 400
    assert store.path.read_bytes() == before
    sample = request('get', store.url + '/edit_sample?t=0').get_json()
    pc = precondition(sample)
    pc['scan_frame_bounds'] = sample['boxes'][0]['scan_frame_bounds']
    response = request('post', store.url + '/detections', json={
        'geometry_preconditions': {'0': pc}, 'time_overrides': {'0': [0.0, 2.0]}})
    assert response.status_code == 400
    assert store.path.read_bytes() == before
