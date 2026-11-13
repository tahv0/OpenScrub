"""Isolated OCR worker tests: no child publication, bounded failure recovery."""
import hashlib
import io
import json
from pathlib import Path

import pytest

import openscrub_web as web
import plate_text_web as search
import plate_text_subprocess as worker
from test_plate_text_web import search_job, queue


def _result(path, video, *, count=0, additions=None, updates=None):
    return dict(report_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        fingerprint=hashlib.sha256(video.read_bytes()).hexdigest(),
        original_count=count, additions=additions or [], updates=updates or {},
        stats=dict(added=len(additions or []), matched_existing=len(updates or {}),
                   decoded_frames=2, sampled_frames=[0, 11]))


def _plate_row():
    return dict(t_start=0., t_end=0., last_seen=0., frame_index=0,
        cbox=[24,20,70,44], aoff=[0,0], category='plate', track=-1,
        text='Known-text plate candidate', verified_label='',
        enabled=True, plate_text_evidence={'match_kind':'exact'})


def test_child_stages_delta_without_touching_report(search_job, tmp_path, monkeypatch):
    _, job, video, path, _ = search_job
    stage = tmp_path / 'private'
    stage.mkdir()
    original = path.read_bytes()
    def fake_scan(child_job, doc, settings, stats):
        assert child_job['_ocr_progress'] is not None
        child_job['_ocr_progress'](dict(state='running', done=1,total=1,source_frame=0))
        doc['detections'].append(_plate_row())
        stats.update(added=1, decoded_frames=1, sampled_frames=[0])
    monkeypatch.setattr(search, '_scan', fake_scan)
    request = dict(stage=str(stage), directory=job['dir'], video=str(video),
                   settings=dict(plate_texts=['ABC123'], max_frames=1))
    monkeypatch.setattr(worker.sys, 'stdin', io.StringIO(json.dumps(request)))
    assert worker._child_process() == 0
    assert path.read_bytes() == original
    staged = json.loads((stage / 'result.json').read_text())
    assert staged['original_count'] == 0
    assert staged['additions'][0]['category'] == 'plate'
    assert staged['updates'] == {}
    assert json.loads((stage / 'progress.json').read_text())['done'] == 1


def test_parent_merges_sparse_ocr_without_changing_human_choices(search_job, monkeypatch):
    client, job, video, path, _ = search_job
    doc = json.loads(path.read_text())
    person = _plate_row()
    person.update(verified_label='not_plate', enabled=False,
                  human_confirmation={'label':'negative', 'source':'explicit'},
                  output_choice_explicit=True)
    doc['detections'] = [person]
    path.write_text(json.dumps(doc))
    assert queue(client, job).status_code == 200
    result = _result(path, video, count=1,
        additions=[_plate_row()],
        updates={'0': {'match_kind':'partial','review_status':'unreviewed'}})
    monkeypatch.setattr(worker, '_run_child', lambda *a, **k: (result, 1234567))
    worker.perform(job, web)
    assert job['phase'] == 'review' and job['error'] is None
    updated = json.loads(path.read_text())
    row = updated['detections'][0]
    assert len(updated['detections']) == 2
    assert row['verified_label'] == 'not_plate'
    assert row['enabled'] is False
    assert row['human_confirmation']['label'] == 'negative'
    assert row['plate_text_evidence']['match_kind'] == 'partial'
    assert updated['render_required'] is True


def test_child_failure_does_not_replace_review_report(search_job, monkeypatch):
    client, job, _, path, _ = search_job
    assert queue(client, job).status_code == 200
    original = path.read_bytes()
    def failed(*args, **kwargs):
        raise MemoryError('OCR worker exceeded its resident memory budget')
    monkeypatch.setattr(worker, '_run_child', failed)
    worker.perform(job, web)
    assert job['phase'] == 'review'
    assert job['plate_text_search']['state'] == 'failed'
    assert path.read_bytes() == original


def test_report_changed_while_child_runs_is_never_overwritten(search_job, monkeypatch):
    client, job, video, path, _ = search_job
    assert queue(client, job).status_code == 200
    candidate = _result(path, video, additions=[_plate_row()])
    def changed(*args, **kwargs):
        doc = json.loads(path.read_text())
        doc['detections'].append(dict(_plate_row(), text='User correction'))
        path.write_text(json.dumps(doc))
        return candidate, 10000
    monkeypatch.setattr(worker, '_run_child', changed)
    worker.perform(job, web)
    assert job['plate_text_search']['state'] == 'failed'
    assert json.loads(path.read_text())['detections'][0]['text'] == 'User correction'


def test_cancel_does_not_publish(search_job, monkeypatch):
    client, job, _, path, _ = search_job
    assert queue(client, job).status_code == 200
    original = path.read_bytes()
    monkeypatch.setattr(worker, '_run_child',
                        lambda *a, **k: (_ for _ in ()).throw(InterruptedError()))
    worker.perform(job, web)
    assert job['plate_text_search']['state'] == 'cancelled'
    assert job['phase'] == 'review'
    assert path.read_bytes() == original


def test_isolated_crop_keeps_rotated_plate_envelope(monkeypatch):
    box = [40., 30., 120., 65.]
    corners = [[24.,55.],[89.,10.],[141.,42.],[78.,99.]]
    monkeypatch.setattr(search, '_web', None)
    assert search._editor_crop(box,corners,160,120) == web._plate_editor_crop(box,corners,160,120)


def test_default_worker_memory_budget_is_bounded(monkeypatch):
    monkeypatch.setenv('OPENSCRUB_OCR_MAX_RSS_MB', '999999')
    assert worker._rss_limit_mb() == 4096
    monkeypatch.setenv('OPENSCRUB_OCR_MAX_RSS_MB', '-1')
    assert worker._rss_limit_mb() == 512
