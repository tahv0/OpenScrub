"""Exact-sample ownership across C01 report and foreign-source owners."""
import json
from pathlib import Path
import threading

import pytest
import openscrub_web as web
from test_exact_samples import exact, sample, precondition, post
from test_exact_adoption import scan
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


def test_strict_save_stale_preparation_does_not_retire_new_scan_authority(scan, monkeypatch):
    import os
    exact, threads = scan
    pc = precondition(sample(exact)); state = web.FILES.initialize(exact.job)
    original = web._prepare_observed_source
    entered, release = threading.Event(), threading.Event()
    def hold_prepared(job, path):
        result = original(job, path)
        if threading.current_thread() is not threading.main_thread():
            entered.set(); assert release.wait(8)
        return result
    monkeypatch.setattr(web, '_prepare_observed_source', hold_prepared)
    call = start_call('post', exact.url + '/detections', json={'geometry_preconditions': {'0':pc}, 'box_overrides': {'0':[3,4,10,11]}})
    try:
        assert entered.wait(5)
        video = Path(exact.job['video']); replacement = video.with_name('replacement.avi')
        replacement.write_bytes(video.read_bytes()); os.replace(replacement, video)
        web._run_job(exact.job, 'scan')
        selected = state.current_source; committed = exact.path.read_bytes()
        assert selected is not None and state.source_status == 'coherent'
    finally:
        release.set(); response = finish(call)
    assert response.status_code == 409
    assert state.current_source is selected and state.source_status == 'coherent' and not state.source_retired
    assert exact.path.read_bytes() == committed
    assert sample(exact)['sample']['source_ref'] == selected['source_ref']


@pytest.mark.parametrize('kind', ['box', 'time'])
def test_strict_index_alias_is_rejected_atomically(exact, kind):
    pc = precondition(sample(exact)); before = exact.path.read_bytes()
    edits = {'geometry_preconditions': {'0':pc}, 'enabled': {'1':True}}
    if kind == 'box': edits['box_overrides'] = {'0':[3,4,10,11], '00':[5,6,12,13]}
    else: edits['time_overrides'] = {'0':[.2,1.8], '00':[.3,1.7]}
    response = post(exact, **edits)
    assert response.status_code == 400 and response.json['error'] == 'invalid_sample_request'
    assert exact.path.read_bytes() == before


def test_legacy_index_alias_still_updates_row(exact):
    response = post(exact, box_overrides={'0':[3,4,10,11], '00':[5,6,12,13]})
    assert response.status_code == 200
    assert json.loads(exact.path.read_text())['detections'][0]['cbox'] == [5.,6.,12.,13.]


@pytest.mark.parametrize('case', ['invalid-id', 'invalid-creation', 'conflict'])
def test_ordinary_manual_errors_remain_actionable(exact, case):
    manual = dict(manual_id='valid:id', t_start=0, t_end=1, t_ref=.2, screen_box=[3,4,10,11])
    if case == 'invalid-id':
        manual['manual_id'] = 'invalid space'; expected = 'Invalid manual_id: expected 1–128 ASCII letters, digits or ._:-'; status = 400
    elif case == 'invalid-creation':
        manual['t_start'] = 'bad'; expected = 'Invalid manual creation: finite times, four coordinates and two offsets required'; status = 400
    else:
        assert post(exact, manual=[manual]).status_code == 200
        manual['screen_box'] = [4,5,11,12]; expected = 'manual_id conflict: creation differs, is missing/invalid, or matches multiple rows'; status = 409
    response = post(exact, manual=[manual])
    assert response.status_code == status and response.json['error'] == expected


def test_strict_save_survives_unrelated_report_publication(exact, monkeypatch):
    pc = precondition(sample(exact)); files = web.FILES.initialize(exact.job); selected = files.current_source
    original = web._prepare_observed_source; entered, release = threading.Event(), threading.Event()
    def hold_prepared(job, path):
        result = original(job, path)
        if threading.current_thread() is not threading.main_thread():
            entered.set(); assert release.wait(8)
        return result
    monkeypatch.setattr(web, '_prepare_observed_source', hold_prepared)
    call = start_call('post', exact.url + '/detections', json={'geometry_preconditions': {'0':pc}, 'box_overrides': {'0':[3,4,10,11]}})
    try:
        assert entered.wait(5)
        assert post(exact, enabled={'1':True}).status_code == 200
    finally:
        release.set(); response = finish(call)
    assert response.status_code == 200 and files.current_source is selected
    doc = json.loads(exact.path.read_text())
    assert doc['detections'][0]['cbox'] == [3.,4.,10.,11.] and doc['detections'][1]['enabled'] is True


@pytest.mark.parametrize('skip_review', [False, True])
def test_signalled_cancel_prevents_scan_handoff_before_ack(scan, monkeypatch, skip_review):
    from test_exact_recovery_races import delay_cancel_lock, start_named
    exact, threads = scan; exact.job['options']['skip_review'] = skip_review
    files = web.FILES.initialize(exact.job); original = web._adopt_scan_source
    entered, release = threading.Event(), threading.Event()
    def held_adoption(job, owner):
        result = original(job, owner); entered.set(); assert release.wait(8); return result
    monkeypatch.setattr(web, '_adopt_scan_source', held_adoption)
    worker = threading.Thread(target=web._run_job, args=(exact.job, 'scan')); worker.start()
    cancel = None
    try:
        assert entered.wait(5)
        cancel_waiting, cancel_release = delay_cancel_lock(files, monkeypatch)
        cancel = start_named('held-exact-cancel', 'post', exact.url+'/cancel')
        assert cancel_waiting.wait(5) and files.operation.is_set()
        release.set(); worker.join(8); assert not worker.is_alive()
        assert exact.job['phase'] not in ('review', 'queued_render') and web.WORK_Q.empty()
    finally:
        release.set()
        if cancel is not None:
            cancel_release.set(); cancel[0].join(8); assert not cancel[0].is_alive()
            request('post', exact.url+'/cancel')
        worker.join(8)


@pytest.mark.parametrize('change', ['recovery', 'publication'])
def test_foreign_source_change_during_pregen_never_writes_thumbnail(exact, monkeypatch, change):
    import cv2
    import numpy as np
    source = web.new_job('', {}, 'foreign.avi'); foreign = Path(source['dir'])/'output.avi'
    writer = cv2.VideoWriter(str(foreign), cv2.VideoWriter_fourcc(*'MJPG'), 5, (128,96)); assert writer.isOpened()
    try:
        for _ in range(3): writer.write(np.random.default_rng(2).integers(0,256,(96,128,3),dtype=np.uint8))
    finally: writer.release()
    source.update(video=str(foreign), phase='review'); exact.job['video'] = str(foreign)
    doc = json.loads(exact.path.read_text())
    doc['provenance']['input'] = str(foreign)
    doc['render_state'] = {'fps': 5, 'cum': [[0, 0]] * 3}
    doc['detections'] = [dict(doc['detections'][0], last_seen=0, t_start=0,
                              t_end=.4, cbox=[50, 40, 70, 60])]
    def scan(args, cb):
        return dict(source_report=doc, stats={})
    monkeypatch.setattr(web.openscrub, 'run_scan', scan)
    deferred = []
    monkeypatch.setattr(web, '_start_owned_thread', lambda target, lease: deferred.append((target,lease)))
    web._run_job(exact.job, 'scan'); assert len(deferred) == 1
    native = cv2.VideoCapture(str(foreign)); owner = web.FILES.initialize(source)
    source_report = Path(source['dir'])/'report.json'; source_report.write_text('{}')
    reads = []
    class Capture:
        def __getattr__(self, attribute):
            return getattr(native, attribute)
        def read(self):
            result = native.read()
            reads.append(result[0])
            with owner.report_lock:
                if change == 'recovery': owner.recovery_required = True
                else: web._publish_job_report_locked(source, str(source_report), {'updated':True})
            return result
        def set(self,*args): return native.set(*args)
        def release(self): native.release()
    monkeypatch.setattr(web.cv2, 'VideoCapture', lambda path: Capture())
    target, lease = deferred.pop()
    try: target()
    finally:
        lease.release()
        with owner.report_lock: owner.recovery_required = False
    assert reads == [True]
    assert not web.FILES.initialize(exact.job).thumbnail.entries
    assert web.FILES.count == 0


@pytest.mark.parametrize('timing', ['admission', 'worker'])
def test_foreign_recovery_before_optional_pregen_keeps_scan_in_review(exact, monkeypatch, timing):
    source = web.new_job('', {}, 'foreign.avi')
    foreign = Path(source['dir']) / 'output.avi'
    foreign.write_bytes(Path(exact.job['video']).read_bytes())
    source.update(video=str(foreign), phase='review')
    exact.job['video'] = str(foreign)
    monkeypatch.setattr(web.openscrub, 'run_scan', lambda args, cb: dict(
        fps=5, cum=[[0, 0]]*10, bands=[[0, 0]]*10, detections=[], stats={}))
    owner = web.FILES.initialize(source)
    original = web._adopt_scan_source
    def recover_after_adoption(job, operation):
        result = original(job, operation)
        if timing == 'admission': owner.recovery_required = True
        return result
    monkeypatch.setattr(web, '_adopt_scan_source', recover_after_adoption)
    deferred = []
    monkeypatch.setattr(web, '_start_owned_thread', lambda target, lease: deferred.append((target, lease)))
    try:
        web._run_job(exact.job, 'scan')
        assert exact.job['phase'] == 'review'
        if timing == 'worker':
            owner.recovery_required = True
            target, lease = deferred.pop()
            try: target()
            finally: lease.release()
        assert not deferred
    finally:
        owner.recovery_required = False


@pytest.mark.parametrize('failure', [PermissionError('admission denied'), web._ThumbnailArtifactPending()])
@pytest.mark.parametrize('skip_review', [False, True])
def test_optional_pregen_admission_refusal_preserves_scan_handoff(exact, monkeypatch, failure, skip_review):
    exact.job['options']['skip_review'] = skip_review
    queued = []
    monkeypatch.setattr(web, 'enqueue', lambda job, action, ticket: queued.append(ticket))
    monkeypatch.setattr(web.openscrub, 'run_scan', lambda args, cb: dict(
        fps=5, cum=[[0, 0]]*10, bands=[[0, 0]]*10, detections=[], stats={}))
    original_adopt = web._adopt_scan_source
    original_resolve = web._thumbnail_resolve_admission
    adopted = False
    def adopt(job, operation):
        nonlocal adopted
        coherent = original_adopt(job, operation)
        adopted = True
        return coherent
    def resolve(lease, path):
        nonlocal failure
        if adopted and failure is not None:
            refusal, failure = failure, None
            raise refusal
        return original_resolve(lease, path)
    monkeypatch.setattr(web, '_adopt_scan_source', adopt)
    monkeypatch.setattr(web, '_thumbnail_resolve_admission', resolve)
    web._run_job(exact.job, 'scan')
    assert adopted
    assert exact.job['phase'] == ('queued_render' if skip_review else 'review')
    assert exact.path.exists()
    if skip_review:
        assert len(queued) == 1
        ticket = queued.pop()
        web.FILES.initialize(exact.job).queued.pop(ticket[2])
        web._finish_operation(exact.job, ticket[3])
    else:
        assert not queued
    assert web.FILES.count == 0


def test_unexpected_optional_pregen_admission_error_is_not_hidden(exact, monkeypatch):
    monkeypatch.setattr(web.openscrub, 'run_scan', lambda args, cb: dict(
        fps=5, cum=[[0, 0]]*10, bands=[[0, 0]]*10, detections=[], stats={}))
    original_adopt = web._adopt_scan_source
    original_resolve = web._thumbnail_resolve_admission
    adopted = False
    def adopt(job, operation):
        nonlocal adopted
        coherent = original_adopt(job, operation)
        adopted = True
        return coherent
    def resolve(lease, path):
        if adopted:
            raise RuntimeError('unexpected admission failure')
        return original_resolve(lease, path)
    monkeypatch.setattr(web, '_adopt_scan_source', adopt)
    monkeypatch.setattr(web, '_thumbnail_resolve_admission', resolve)
    web._run_job(exact.job, 'scan')
    assert exact.job['phase'] == 'error'
    assert exact.job['error'] == 'unexpected admission failure'
    assert web.FILES.count == 0
