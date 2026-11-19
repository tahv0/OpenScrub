"""Exact-sample ownership across C01 report and foreign-source owners."""
import json
from pathlib import Path
import threading

import pytest
import openscrub_web as web
from test_exact_samples import exact, sample, precondition, post
from test_job_lifecycle import store, request, start_call, finish


def test_old_report_snapshot_cannot_retire_newer_authoritative_source(exact, monkeypatch):
    sample(exact)
    files = web.FILES.initialize(exact.job)
    entered, release = threading.Event(), threading.Event()
    original = web.json.load
    def held_load(stream, *args, **kwargs):
        doc = original(stream, *args, **kwargs)
        if getattr(stream, 'name', None) == str(exact.path) and threading.current_thread() is not threading.main_thread():
            entered.set()
            assert release.wait(8)
        return doc
    monkeypatch.setattr(web.json, 'load', held_load)
    call = start_call('get', exact.url + '/edit_sample?t=0.2')
    try:
        assert entered.wait(5)
        new = Path(exact.job['dir']) / 'new-input.avi'
        new.write_bytes(Path(exact.job['video']).read_bytes())
        with files.report_lock:
            doc = json.loads(exact.path.read_text())
            doc['provenance']['input'] = str(new)
            web._publish_job_report_locked(exact.job, str(exact.path), doc)
            web._report_committed_locked(exact.job, doc)
            selected = dict(files.current_source, path=str(new), stamp=web._file_stamp(new.stat()), source_ref='new-authority')
            files.current_source = selected
            files.source_status, files.source_retired = 'coherent', False
            exact.job['video'] = str(new)
    finally:
        release.set()
        response = finish(call)
    assert response.status_code == 409
    assert files.current_source is selected and files.source_status == 'coherent' and not files.source_retired


@pytest.mark.parametrize('change', ['publication', 'recovery'])
def test_foreign_owner_change_during_encode_refuses_exact_response(exact, monkeypatch, change):
    source = web.new_job('', {}, 'source.avi')
    foreign = Path(source['dir']) / 'output.avi'
    foreign.write_bytes(Path(exact.job['video']).read_bytes())
    report = Path(source['dir']) / 'report.json'
    report.write_text('{}')
    source.update(video=str(foreign), phase='review')
    exact.job['video'] = str(foreign)
    doc = json.loads(exact.path.read_text()); doc['provenance']['input'] = str(foreign)
    exact.path.write_text(json.dumps(doc))
    before = sample(exact)['sample']['source_ref']
    owner = web.FILES.initialize(source)
    original = web.cv2.imencode
    def change_owner(*args, **kwargs):
        result = original(*args, **kwargs)
        with owner.report_lock:
            if change == 'publication':
                web._publish_job_report_locked(source, str(report), {'updated': True})
            else:
                owner.recovery_required = True
        return result
    monkeypatch.setattr(web.cv2, 'imencode', change_owner)
    response = request('get', exact.url + '/edit_sample?t=0.2')
    assert response.status_code == 409
    assert response.is_json and response.json['error'] == 'sample_conflict'
    monkeypatch.setattr(web.cv2, 'imencode', original)
    with owner.report_lock:
        owner.recovery_required = False
    assert sample(exact)['sample']['source_ref'] == before


def test_strict_identical_replay_keeps_existing_noop_publication_policy(exact):
    pc = precondition(sample(exact))
    edits = {'geometry_preconditions': {'0': pc}, 'box_overrides': {'0': [3, 4, 10, 11]}}
    assert post(exact, **edits).status_code == 200
    state = web.FILES.initialize(exact.job)
    before = (exact.path.read_bytes(), exact.path.stat().st_mtime_ns, state.committed_report_epoch, state.output_epoch)
    replay = post(exact, **edits)
    assert replay.status_code == 200 and '0' in replay.json['geometry_rows']
    assert (exact.path.read_bytes(), exact.path.stat().st_mtime_ns, state.committed_report_epoch, state.output_epoch) == before


def test_foreign_owner_change_during_source_preparation_is_refused(exact, monkeypatch):
    source = web.new_job('', {}, 'source.avi')
    foreign = Path(source['dir']) / 'output.avi'
    foreign.write_bytes(Path(exact.job['video']).read_bytes())
    report = Path(source['dir']) / 'report.json'; report.write_text('{}')
    source.update(video=str(foreign), phase='review')
    exact.job['video'] = str(foreign)
    doc = json.loads(exact.path.read_text()); doc['provenance']['input'] = str(foreign)
    exact.path.write_text(json.dumps(doc))
    owner = web.FILES.initialize(source)
    original = web._probe_exact_source
    def change_owner(path):
        facts = original(path)
        with owner.report_lock:
            web._publish_job_report_locked(source, str(report), {'updated': True})
        return facts
    monkeypatch.setattr(web, '_probe_exact_source', change_owner)
    response = request('get', exact.url + '/edit_sample?t=0.2')
    assert response.status_code == 409
    assert response.is_json and response.json['error'] == 'sample_conflict'
    assert web.FILES.initialize(exact.job).current_source is None


def test_report_path_mismatch_cannot_retire_newer_adopted_source(exact, monkeypatch):
    sample(exact)
    files = web.FILES.initialize(exact.job)
    old_path = str(Path(exact.job['video']).resolve())
    entered, release = threading.Event(), threading.Event()
    local = threading.local()
    original_load, original_realpath = web.json.load, web.os.path.realpath
    def loaded(stream, *args, **kwargs):
        doc = original_load(stream, *args, **kwargs)
        if getattr(stream, 'name', None) == str(exact.path):
            local.after_load = True
        return doc
    def held_realpath(path, *args, **kwargs):
        value = original_realpath(path, *args, **kwargs)
        if getattr(local, 'after_load', False) and str(path) == old_path:
            local.after_load = False
            entered.set(); assert release.wait(8)
        return value
    monkeypatch.setattr(web.json, 'load', loaded)
    monkeypatch.setattr(web.os.path, 'realpath', held_realpath)
    call = start_call('get', exact.url + '/edit_sample?t=0.2')
    try:
        assert entered.wait(5)
        new = Path(exact.job['dir']) / 'new-input.avi'; new.write_bytes(Path(old_path).read_bytes())
        with files.report_lock:
            doc = json.loads(exact.path.read_text()); doc['provenance']['input'] = str(new)
            web._publish_job_report_locked(exact.job, str(exact.path), doc)
            web._report_committed_locked(exact.job, doc)
            selected = dict(files.current_source, path=str(new), stamp=web._file_stamp(new.stat()), source_ref='new-authority')
            files.current_source = selected; files.source_status, files.source_retired = 'coherent', False
            exact.job['video'] = str(new)
    finally:
        release.set(); response = finish(call)
    assert response.status_code == 409
    assert files.current_source is selected and files.source_status == 'coherent' and not files.source_retired


@pytest.mark.parametrize('fail_publication', [False, True])
def test_render_report_epoch_advances_only_after_pair_commit(store, monkeypatch, fail_publication):
    import os
    import openscrub
    store.doc['render_state']['bands'] = [[0, 0]] * 30
    store.path.write_text(json.dumps(store.doc))
    old_report = store.path.read_bytes()
    output = Path(store.job['dir']) / 'output.mp4'; output.write_bytes(b'old video')
    store.job['output'] = str(output)
    state = web.FILES.initialize(store.job)
    monkeypatch.setattr(openscrub, 'normalize_vfr', lambda *args: None)
    monkeypatch.setattr(openscrub, '_render_into', lambda src, dst, *args, **kwargs: Path(dst).write_bytes(b'new video'))
    real_replace = os.replace
    def replace(src, dst):
        if fail_publication and Path(src).name.startswith('.report-') and Path(dst) == store.path:
            raise OSError('injected report publication failure')
        return real_replace(src, dst)
    monkeypatch.setattr(os, 'replace', replace)
    web._run_job(store.job, 'render')
    if fail_publication:
        assert state.committed_report_epoch == 0
        assert store.path.read_bytes() == old_report and output.read_bytes() == b'old video'
    else:
        assert state.committed_report_epoch == 1
        assert output.read_bytes() == b'new video' and store.job['phase'] == 'done'
    assert state.output_epoch > 0


def test_existing_file_owner_lookup_does_not_allocate_again(monkeypatch):
    import openscrub_internal.lifetimes as lifetimes
    job = {}
    first = web.FILES.initialize(job)
    def forbidden():
        raise AssertionError('existing owner must not construct another state')
    monkeypatch.setattr(lifetimes, '_JobFiles', forbidden)
    assert web.FILES.initialize(job) is first
