"""Coherent thumbnail routes and their observable image representations."""
import json
import os
import threading

import cv2
import numpy as np
import openscrub_web as web
import openscrub
import pytest

from test_exact_samples import exact
from test_exact_adoption import scan
from test_exact_media import retained, install, marker
from test_job_lifecycle import request, store, start_call, finish
from test_report_transactions import join


def test_source_report_bound_only_after_successful_association(exact):
    files = web.FILES.initialize(exact.job)
    prepared, lease = web._prepare_observed_source(exact.job, exact.job['video'])
    try:
        with files.report_lock:
            assert not files.source_report_bound
            selected = web._select_observed_locked(exact.job, prepared, report_bound=False)
            assert not files.source_report_bound
            assert web._select_observed_locked(exact.job, prepared) is selected
            assert files.source_report_bound
            assert web._select_observed_locked(exact.job, prepared, report_bound=False) is selected
            assert files.source_report_bound
    finally:
        lease.release()


def test_legacy_snapshot_cannot_downgrade_a_bound_source(exact):
    doc = json.loads(exact.path.read_text())
    provenance = doc.pop('provenance')
    exact.path.write_text(json.dumps(doc))
    _, source, _, lease = web._thumbnail_snapshot(exact.job)
    lease.release()
    assert not web.FILES.initialize(exact.job).source_report_bound
    doc['provenance'] = provenance
    exact.path.write_text(json.dumps(doc))
    _, same_source, _, lease = web._thumbnail_snapshot(exact.job)
    lease.release()
    assert same_source is source and web.FILES.initialize(exact.job).source_report_bound
    del doc['provenance']
    exact.path.write_text(json.dumps(doc))
    with pytest.raises(web._ThumbnailError) as error:
        web._thumbnail_snapshot(exact.job)
    assert error.value.code == 'thumbnail_source_conflict'
    assert web.FILES.count == 0


@pytest.mark.parametrize('provenance', [None, [], '', {'input': None}, {'input': ''}, {'input': '   '}])
def test_malformed_provenance_cannot_use_legacy_fallback(exact, provenance):
    doc = json.loads(exact.path.read_text())
    doc['provenance'] = provenance
    exact.path.write_text(json.dumps(doc))
    response = request('get', exact.url + '/detections')
    assert response.status_code == 500 and response.json['error'] == 'thumbnail_invalid_report'
    assert not web.FILES.initialize(exact.job).source_report_bound
    del doc['provenance']
    exact.path.write_text(json.dumps(doc))
    assert request('get', exact.url + '/detections').status_code == 200


def test_pending_scan_pair_does_not_use_legacy_fallback(exact):
    doc = json.loads(exact.path.read_text())
    del doc['provenance']
    exact.path.write_text(json.dumps(doc))
    files = web.FILES.initialize(exact.job)
    with files.report_lock:
        files.source_status = 'pending'
    response = request('get', exact.url + '/detections')
    assert response.status_code == 409 and response.json['error'] == 'source_report_pending'
    assert not files.source_report_bound and files.current_source is None


def test_stale_source_association_does_not_set_bound_marker(exact, monkeypatch):
    alternative = exact.path.parent / 'other.avi'
    with open(exact.job['video'], 'rb') as original_file:
        alternative.write_bytes(original_file.read())
    original = web._prepare_observed_source
    def move_after_prepare(job, path):
        prepared = original(job, path)
        job['video'] = str(alternative)
        return prepared
    monkeypatch.setattr(web, '_prepare_observed_source', move_after_prepare)
    response = request('get', exact.url + '/detections')
    assert response.status_code == 409
    files = web.FILES.initialize(exact.job)
    assert not files.source_report_bound and files.current_source is None


def test_metadata_generation_and_obsolete_cached_image(exact):
    metadata = request('get', exact.url + '/detections')
    assert metadata.status_code == 200
    version = metadata.json['thumbnail_version']
    image = request('get', exact.url + '/thumb/0?v=' + version)
    assert image.status_code == 200
    etag = image.headers['ETag']
    assert request('post', exact.url + '/detections', json={'enabled': {'0': False}}).status_code == 200
    stale = request('get', exact.url + '/thumb/0?v=' + version,
                    headers={'If-None-Match': etag})
    assert stale.status_code == 409
    assert stale.json['error'] == 'thumbnail_obsolete'
    newer = request('get', exact.url + '/detections')
    assert newer.json['thumbnail_version'] != version
    assert newer.json['detections'][0]['thumbnail_row'] != metadata.json['detections'][0]['thumbnail_row']


def test_old_cached_image_never_bypasses_invalid_report(exact):
    assert request('get', exact.url + '/thumb/0').status_code == 200
    exact.path.write_text(json.dumps([]))
    response = request('get', exact.url + '/thumb/0')
    assert response.status_code == 500
    assert response.json['error'] == 'thumbnail_invalid_report'


def test_current_image_uses_last_clamped_ordinal_and_its_offset(exact):
    doc = json.loads(exact.path.read_text())
    doc['detections'][0].update(t_start=2, t_end=2, last_seen=2, cbox=[10, 10, 20, 20])
    exact.path.write_text(json.dumps(doc))
    metadata = request('get', exact.url + '/detections').json
    response = request('get', exact.url + '/detframe/0?v=' + metadata['thumbnail_version'])
    assert response.status_code == 200
    frame = cv2.imdecode(np.frombuffer(response.data, np.uint8), 1)
    assert abs(float(frame[40, 50].mean()) - 180) < 5
    assert frame[1, 15, 2] > frame[1, 15, 0] + 40  # offset [9, -9] and outline


def test_coherent_reads_are_allowed_during_active_work(exact):
    owner = web._prepare_work(exact.job, 'scan')
    try:
        with web.FILES.initialize(exact.job).report_lock:
            web._begin_operation(exact.job, owner)
        metadata = request('get', exact.url + '/detections')
        assert metadata.status_code == 200
        assert request('get', exact.url + '/thumb/0?v=' + metadata.json['thumbnail_version']).status_code == 200
    finally:
        web._finish_operation(exact.job, owner)


def test_observed_source_replacement_refuses_old_image(exact):
    metadata = request('get', exact.url + '/detections').json
    version = metadata['thumbnail_version']
    assert request('get', exact.url + '/thumb/0?v=' + version).status_code == 200
    source = exact.job['video']
    replacement = source + '.replacement'
    with open(source, 'rb') as original, open(replacement, 'wb') as output:
        output.write(original.read())
    os.replace(replacement, source)
    response = request('get', exact.url + '/thumb/0?v=' + version)
    assert response.status_code == 409
    assert response.json['error'] in ('thumbnail_obsolete', 'thumbnail_source_conflict')


def test_scan_pregen_uses_generation_cache(scan, monkeypatch):
    fixture, threads = scan
    writer = cv2.VideoWriter(fixture.job['video'], cv2.VideoWriter_fourcc(*'MJPG'), 5, (160, 120))
    assert writer.isOpened()
    for index in range(10):
        frame = np.zeros((120, 160, 3), np.uint8)
        frame[:, ::8] = (20, 180, 230)
        writer.write(frame)
    writer.release()
    doc = json.loads(fixture.path.read_text())
    for row in doc['detections']:
        row['cbox'] = [55, 45, 105, 75]
    real_load, real_validate = web.json.load, web._thumbnail_validate_report
    counts = {'parse': 0, 'validate': 0}
    def count_load(stream, *args, **kwargs):
        if getattr(stream, 'name', None) == str(fixture.path): counts['parse'] += 1
        return real_load(stream, *args, **kwargs)
    def count_validate(value):
        counts['validate'] += 1
        return real_validate(value)
    monkeypatch.setattr(web.json, 'load', count_load)
    monkeypatch.setattr(web, '_thumbnail_validate_report', count_validate)
    def compute(args, cb):
        return dict(source_report=doc, stats={})
    monkeypatch.setattr(openscrub, 'run_scan', compute)
    web._run_job(fixture.job, 'scan')
    assert len(threads) == 1
    join(threads[0])
    assert not list(fixture.path.parent.glob('thumb2_*.jpg'))
    state = web.FILES.initialize(fixture.job).thumbnail
    assert state.current is not None and ('crop', 0) in state.entries
    assert counts == {'parse': 1, 'validate': 2}


@pytest.mark.parametrize('first', ['pregen', 'demand'])
def test_pregen_and_demand_share_first_fill(scan, monkeypatch, first):
    fixture, threads = scan
    writer = cv2.VideoWriter(fixture.job['video'], cv2.VideoWriter_fourcc(*'MJPG'), 5, (160, 120))
    assert writer.isOpened()
    try:
        for _ in range(10):
            frame = np.zeros((120, 160, 3), np.uint8)
            frame[:, ::8] = (20, 180, 230)
            writer.write(frame)
    finally:
        writer.release()
    doc = json.loads(fixture.path.read_text())
    for row in doc['detections']: row['cbox'] = [55, 45, 105, 75]
    monkeypatch.setattr(openscrub, 'run_scan', lambda args, cb: dict(source_report=doc, stats={}))
    staged, resume, start_pregen = threading.Event(), threading.Event(), threading.Event()
    if first == 'demand':
        real_start = web._start_owned_thread
        def delayed_start(target, lease):
            def delayed():
                assert start_pregen.wait(8)
                target()
            return real_start(delayed, lease)
        monkeypatch.setattr(web, '_start_owned_thread', delayed_start)
    real_stage = web.thumbs.stage_jpeg
    def held_stage(job_dir, ticket, jpeg):
        result = real_stage(job_dir, ticket, jpeg)
        if ticket.index == 0 and not staged.is_set():
            staged.set()
            assert resume.wait(8)
        return result
    monkeypatch.setattr(web.thumbs, 'stage_jpeg', held_stage)
    demand = None
    try:
        web._run_job(fixture.job, 'scan')
        assert len(threads) == 1
        if first == 'pregen':
            assert staged.wait(5)
        version = request('get', fixture.url + '/detections').json['thumbnail_version']
        url = fixture.url + '/thumb/0?v=' + version
        if first == 'pregen':
            pending = request('get', url)
            assert pending.status_code == 409 and pending.json['error'] == 'thumbnail_pending'
            resume.set()
            join(threads[0])
            first_image = request('get', url)
        else:
            demand = start_call('get', url)
            assert staged.wait(5)
            start_pregen.set()
            join(threads[0])
            resume.set()
            first_image = finish(demand)
        assert first_image.status_code == 200
        assert request('get', url).data == first_image.data
    finally:
        start_pregen.set()
        resume.set()
        if demand is not None: finish(demand)
        for thread in threads: join(thread)


def test_conditional_get_and_missing_cached_body(exact):
    version = request('get', exact.url + '/detections').json['thumbnail_version']
    url = exact.url + '/thumb/0?v=' + version
    first = request('get', url)
    assert first.status_code == 200
    assert first.headers['Cache-Control'] == 'private, no-cache, max-age=0, must-revalidate'
    cached = request('get', url, headers={'If-None-Match': first.headers['ETag']})
    assert cached.status_code == 304 and not cached.data
    entry = web.FILES.initialize(exact.job).thumbnail.entries[('crop', 0)]
    os.unlink(entry.path)
    missing = request('get', url, headers={'If-None-Match': first.headers['ETag']})
    assert missing.status_code == 409 and missing.json['error'] == 'thumbnail_obsolete'
    assert missing.headers['Cache-Control'] == 'private, no-store'


def test_changed_cached_bytes_are_not_revalidated_as_current(exact):
    version = request('get', exact.url + '/detections').json['thumbnail_version']
    url = exact.url + '/thumb/0?v=' + version
    first = request('get', url)
    assert first.status_code == 200
    entry = web.FILES.initialize(exact.job).thumbnail.entries[('crop', 0)]
    before = os.stat(entry.path)
    with open(entry.path, 'r+b') as file:
        body = bytearray(file.read())
        body[-10] ^= 1
        file.seek(0)
        file.write(body)
    os.utime(entry.path, ns=(before.st_atime_ns, before.st_mtime_ns))
    response = request('get', url, headers={'If-None-Match': first.headers['ETag']})
    assert response.status_code == 409 and response.json['error'] == 'thumbnail_obsolete'


def test_invalid_encoded_bytes_are_not_accepted(exact, monkeypatch):
    version = request('get', exact.url + '/detections').json['thumbnail_version']
    monkeypatch.setattr(web.thumbs, 'encode_jpeg', lambda image, quality: b'not jpeg')
    response = request('get', exact.url + '/thumb/0?v=' + version)
    assert response.status_code == 500 and response.json['error'] == 'thumbnail_encode_failed'
    state = web.FILES.initialize(exact.job).thumbnail
    assert not state.entries and not state.fills


def test_version_validation_and_unversioned_cache_policy(exact):
    invalid = request('get', exact.url + '/thumb/0?v=bad')
    assert invalid.status_code == 400 and invalid.json['error'] == 'thumbnail_invalid_version'
    assert invalid.headers['Cache-Control'] == 'private, no-store'
    unversioned = request('get', exact.url + '/thumb/0?r=123')
    assert unversioned.status_code == 200 and unversioned.headers['Cache-Control'] == 'private, no-store'
    legacy = exact.path.parent / 'thumb2_999.jpg'
    legacy.write_bytes(unversioned.data)
    assert request('get', exact.url + '/thumb/999').status_code == 404


def test_warm_image_does_not_parse_report_or_decode_source(exact, monkeypatch):
    version = request('get', exact.url + '/detections').json['thumbnail_version']
    url = exact.url + '/thumb/0?v=' + version
    first = request('get', url)
    assert first.status_code == 200
    def forbidden(*args, **kwargs): raise AssertionError('warm image performed cold work')
    monkeypatch.setattr(web, '_thumbnail_snapshot', forbidden)
    monkeypatch.setattr(web, '_load_job_report', forbidden)
    monkeypatch.setattr(web, '_read_thumbnail_ordinal', forbidden)
    monkeypatch.setattr(web.thumbs, 'raw_row_fingerprint', forbidden)
    monkeypatch.setattr(web.cv2, 'imdecode', forbidden)
    monkeypatch.setattr(openscrub, 'sha256_file', forbidden)
    for _ in range(3):
        warm = request('get', url)
        assert warm.status_code == 200 and warm.data == first.data


def test_reader_pin_blocks_new_generation_fill_until_closed(exact, monkeypatch):
    version = request('get', exact.url + '/detections').json['thumbnail_version']
    old_url = exact.url + '/thumb/0?v=' + version
    assert request('get', old_url).status_code == 200
    state = web.FILES.initialize(exact.job).thumbnail
    entry = state.entries[('crop', 0)]
    original_open = open
    entered, resume = threading.Event(), threading.Event()
    class HeldReader:
        def __init__(self, file): self.file = file
        def __getattr__(self, name): return getattr(self.file, name)
        def __enter__(self): return self
        def __exit__(self, *args): self.file.close()
        def read(self):
            entered.set()
            assert resume.wait(8)
            return self.file.read()
    def held_open(path, *args, **kwargs):
        file = original_open(path, *args, **kwargs)
        return HeldReader(file) if path == entry.path else file
    monkeypatch.setattr(web, 'open', held_open, raising=False)
    call = start_call('get', old_url)
    try:
        assert entered.wait(5)
        assert request('post', exact.url + '/detections', json={'enabled': {'0': False}}).status_code == 200
        new_version = request('get', exact.url + '/detections').json['thumbnail_version']
        pending = request('get', exact.url + '/thumb/0?v=' + new_version)
        assert pending.status_code == 409 and pending.json['error'] == 'thumbnail_pending'
        assert os.path.exists(entry.path)
    finally:
        resume.set()
        stale = finish(call)
    assert stale.status_code == 409 and stale.json['error'] == 'thumbnail_obsolete'
    assert request('get', exact.url + '/thumb/0?v=' + new_version).status_code == 200
    assert not os.path.exists(entry.path)


def test_cached_reader_failure_retires_generation(exact, monkeypatch):
    version = request('get', exact.url + '/detections').json['thumbnail_version']
    url = exact.url + '/thumb/0?v=' + version
    assert request('get', url).status_code == 200
    state = web.FILES.initialize(exact.job).thumbnail
    entry = state.entries[('crop', 0)]
    original_open = open
    class BrokenReader:
        def __init__(self, file): self.file = file
        def __getattr__(self, name): return getattr(self.file, name)
        def __enter__(self): return self
        def __exit__(self, *args): self.file.close()
        def read(self): raise OSError('injected read failure')
    def broken_open(path, *args, **kwargs):
        file = original_open(path, *args, **kwargs)
        return BrokenReader(file) if path == entry.path else file
    monkeypatch.setattr(web, 'open', broken_open, raising=False)
    response = request('get', url)
    assert response.status_code == 409 and response.json['error'] == 'thumbnail_obsolete'
    assert state.current is None and not state.readers


def test_signalled_operation_cannot_revive_a_warm_generation(exact, monkeypatch):
    owner = web._prepare_work(exact.job, 'scan')
    files = web.FILES.initialize(exact.job)
    with files.report_lock:
        web._begin_operation(exact.job, owner)
    try:
        version = request('get', exact.url + '/detections').json['thumbnail_version']
        url = exact.url + '/thumb/0?v=' + version
        assert request('get', url).status_code == 200
        entry = files.thumbnail.entries[('crop', 0)]
        entered, resume = threading.Event(), threading.Event()
        real_open = open
        class HeldReader:
            def __init__(self, file): self.file = file
            def __getattr__(self, name): return getattr(self.file, name)
            def __enter__(self): return self
            def __exit__(self, *args): self.file.close()
            def read(self):
                entered.set()
                assert resume.wait(8)
                return self.file.read()
        def held_open(path, *args, **kwargs):
            file = real_open(path, *args, **kwargs)
            return HeldReader(file) if path == entry.path else file
        monkeypatch.setattr(web, 'open', held_open, raising=False)
        call = start_call('get', url)
        try:
            assert entered.wait(5)
            owner.operation.set()
        finally:
            resume.set()
            response = finish(call)
        assert response.status_code == 409
        owner.operation.clear()
        assert request('get', url).status_code == 409
    finally:
        web._finish_operation(exact.job, owner)


def test_cold_discovery_waits_for_one_inflight_owner(exact, monkeypatch):
    first_entered, second_entered, resume = threading.Event(), threading.Event(), threading.Event()
    lock, count = threading.Lock(), [0]
    original = web._thumbnail_snapshot
    def held_snapshot(*args, **kwargs):
        with lock:
            count[0] += 1
            number = count[0]
        if number == 1:
            first_entered.set()
            assert resume.wait(8)
        else:
            second_entered.set()
        return original(*args, **kwargs)
    monkeypatch.setattr(web, '_thumbnail_snapshot', held_snapshot)
    first = start_call('get', exact.url + '/thumb/0')
    second = None
    try:
        assert first_entered.wait(5)
        second = start_call('get', exact.url + '/thumb/1')
        assert not second_entered.wait(.15)
    finally:
        resume.set()
        first_result = finish(first)
        if second is not None:
            second_result = finish(second)
    assert first_result.status_code == 200 and second_result.status_code == 200


@pytest.mark.skipif(not hasattr(os, 'mkfifo'), reason='FIFO control requires POSIX')
def test_nonregular_source_is_rejected_without_waiting_on_open(exact, monkeypatch):
    fifo = exact.path.parent / 'unexpected.fifo'
    os.mkfifo(fifo)
    exact.job['video'] = str(fifo)
    doc = json.loads(exact.path.read_text())
    doc['provenance']['input'] = str(fifo)
    exact.path.write_text(json.dumps(doc))
    def no_probe(_path): raise web.exact.ExactError('not media')
    monkeypatch.setattr(web, '_probe_exact_source', no_probe)
    call = start_call('get', exact.url + '/detections')
    timely = call[1].wait(1)
    unblock = None
    try:
        if not timely:
            unblock = os.open(fifo, os.O_RDWR | os.O_NONBLOCK)
        response = finish(call)
    finally:
        if unblock is not None:
            os.close(unblock)
    assert timely and response.status_code == 409
    assert response.json['error'] == 'thumbnail_source_conflict'


def test_report_commit_during_decode_rejects_stale_stage(exact, monkeypatch):
    version = request('get', exact.url + '/detections').json['thumbnail_version']
    entered, resume = threading.Event(), threading.Event()
    original = web._read_thumbnail_ordinal
    def held_decode(*args, **kwargs):
        frame = original(*args, **kwargs)
        entered.set()
        assert resume.wait(8)
        return frame
    monkeypatch.setattr(web, '_read_thumbnail_ordinal', held_decode)
    call = start_call('get', exact.url + '/thumb/0?v=' + version)
    try:
        assert entered.wait(5)
        assert request('post', exact.url + '/detections', json={'enabled': {'0': False}}).status_code == 200
    finally:
        resume.set()
        response = finish(call)
    assert response.status_code == 409 and response.json['error'] == 'thumbnail_obsolete'
    state = web.FILES.initialize(exact.job).thumbnail
    assert not state.fills and not state.readers
    assert not list(exact.path.parent.glob('.thumb3-stage-*'))


def test_missing_previously_selected_source_is_conflict(exact):
    metadata = request('get', exact.url + '/detections')
    assert metadata.status_code == 200
    os.unlink(exact.job['video'])
    response = request('get', exact.url + '/thumb/0?v=' + metadata.json['thumbnail_version'])
    assert response.status_code == 409 and response.json['error'] == 'thumbnail_source_conflict'
    files = web.FILES.initialize(exact.job)
    assert files.source_retired and files.current_source is None


def test_source_io_error_is_structured_and_safe(exact, monkeypatch):
    def fail(*args, **kwargs): raise PermissionError('/private/secret/source.avi')
    monkeypatch.setattr(web, '_prepare_observed_source', fail)
    response = request('get', exact.url + '/detections')
    assert response.status_code == 409 and response.json['error'] == 'thumbnail_source_conflict'
    assert b'/private/secret' not in response.data
    assert response.headers['Cache-Control'] == 'private, no-store'


def test_decode_lease_blocks_vault_and_delete(exact, monkeypatch):
    exact.enable()
    version = request('get', exact.url + '/detections').json['thumbnail_version']
    entered, resume = threading.Event(), threading.Event()
    original = web._read_thumbnail_ordinal
    def held_decode(*args, **kwargs):
        entered.set()
        assert resume.wait(8)
        return original(*args, **kwargs)
    monkeypatch.setattr(web, '_read_thumbnail_ordinal', held_decode)
    call = start_call('get', exact.url + '/thumb/0?v=' + version)
    try:
        assert entered.wait(5)
        assert request('post', '/api/vault/lock').status_code == 409
        assert request('delete', exact.url).status_code == 409
    finally:
        resume.set()
        result = finish(call)
    assert result.status_code == 200
    assert web.FILES.count == 0
    assert request('post', '/api/vault/lock').status_code == 200


@pytest.mark.parametrize('failure', [openscrub.PipelineCancelled(), KeyboardInterrupt(),
                                     web.thumbs.ThumbnailDecodeError('unavailable'), OSError('native')])
@pytest.mark.parametrize('borrowed', [False, True])
def test_ordinal_adapter_preserves_primary_exception_and_capture_ownership(monkeypatch, failure, borrowed):
    class Capture:
        released = False
        def isOpened(self): raise failure
        def release(self):
            self.released = True
            raise OSError('close')
    capture = Capture()
    monkeypatch.setattr(web.cv2, 'VideoCapture', lambda path: capture)
    expected = web.thumbs.ThumbnailDecodeError if isinstance(failure, OSError) else type(failure)
    with pytest.raises(expected) as caught:
        web._read_thumbnail_ordinal({'path': 'unused'}, 0, count=1,
                                    capture=capture if borrowed else None)
    if not isinstance(failure, OSError):
        assert caught.value is failure
    else:
        assert caught.value.__cause__ is failure
    assert capture.released is not borrowed


def test_vault_transition_evicts_generation_for_registered_job(exact):
    exact.enable()
    version = request('get', exact.url + '/detections').json['thumbnail_version']
    assert request('get', exact.url + '/thumb/0?v=' + version).status_code == 200
    state = web.FILES.initialize(exact.job).thumbnail
    assert request('post', '/api/vault/lock').status_code == 200
    assert state.current is None
    assert request('post', '/api/vault/unlock', json={'password': 'synthetic-password'}).status_code == 200
    assert request('get', exact.url + '/thumb/0?v=' + version).status_code == 409
    new_version = request('get', exact.url + '/detections').json['thumbnail_version']
    assert new_version != version
    assert request('get', exact.url + '/thumb/0?v=' + new_version).status_code == 200


def test_detframe_end_ordinal_matches_sequential_oracle_and_offset(exact):
    writer = cv2.VideoWriter(exact.job['video'], cv2.VideoWriter_fourcc(*'MJPG'), 5, (160, 120))
    assert writer.isOpened()
    try:
        for index in range(4):
            frame = np.full((120, 160, 3), (25 + 40 * index, 50 + 20 * index, 180 - 30 * index), np.uint8)
            frame[45:75, 60:100] = (220, 30 + 30 * index, 20)
            writer.write(frame)
    finally:
        writer.release()
    decoder = cv2.VideoCapture(exact.job['video'])
    sequential = []
    try:
        while True:
            ok, frame = decoder.read()
            if not ok: break
            sequential.append(frame)
    finally:
        decoder.release()
    assert len(sequential) == 4
    doc = json.loads(exact.path.read_text())
    doc['render_state'] = {'fps': 5, 'cum': [[0, 0], [2, 1], [4, 2], [13, -7]]}
    doc['detections'][0].update(t_start=.8, t_end=.8, last_seen=.8, cbox=[50, 40, 100, 80])
    exact.path.write_text(json.dumps(doc))
    version = request('get', exact.url + '/detections').json['thumbnail_version']
    response = request('get', exact.url + '/detframe/0?v=' + version)
    assert response.status_code == 200
    actual = cv2.imdecode(np.frombuffer(response.data, np.uint8), cv2.IMREAD_COLOR)
    assert np.max(np.abs(actual[100, 140].astype(int) - sequential[3][100, 140].astype(int))) < 12
    assert actual[29, 80, 2] > actual[29, 80, 0] + 50


def test_normalized_retained_source_uses_sequential_last_ordinal(store, retained):
    path = retained['normalized']['path']
    decoder = cv2.VideoCapture(path)
    frames = []
    try:
        while True:
            ok, frame = decoder.read()
            if not ok: break
            frames.append(frame)
            assert len(frames) <= 60
    finally:
        decoder.release()
    assert len(frames) > 1
    install(store, path, 13, len(frames), normalized=True)
    doc = json.loads(store.path.read_text())
    end = len(frames) / 13
    doc['detections'][0].update(t_start=end, t_end=end, last_seen=end, cbox=[4, 1, 10, 4])
    store.path.write_text(json.dumps(doc))
    version = request('get', store.url + '/detections').json['thumbnail_version']
    response = request('get', store.url + '/detframe/0?v=' + version)
    assert response.status_code == 200
    actual = cv2.imdecode(np.frombuffer(response.data, np.uint8), cv2.IMREAD_COLOR)
    assert marker(actual) == marker(frames[-1])


def test_sequential_oracle_detects_wrong_ordinal_mutation(exact, monkeypatch):
    decoder = cv2.VideoCapture(exact.job['video'])
    frames = []
    try:
        while True:
            ok, frame = decoder.read()
            if not ok: break
            frames.append(frame)
    finally:
        decoder.release()
    doc = json.loads(exact.path.read_text())
    doc['detections'][0].update(t_start=2, t_end=2, last_seen=2, cbox=[10, 10, 20, 20])
    exact.path.write_text(json.dumps(doc))
    version = request('get', exact.url + '/detections').json['thumbnail_version']
    real = web._read_thumbnail_ordinal
    def wrong_index(selected, index, *, count, capture=None):
        return real(selected, index - 1, count=count, capture=capture)
    monkeypatch.setattr(web, '_read_thumbnail_ordinal', wrong_index)
    response = request('get', exact.url + '/detframe/0?v=' + version)
    assert response.status_code == 200
    actual = cv2.imdecode(np.frombuffer(response.data, np.uint8), cv2.IMREAD_COLOR)
    assert abs(float(actual[40, 50].mean()) - float(frames[-1][40, 50].mean())) > 10


@pytest.mark.parametrize('stage', ['encode', 'fsync'])
def test_failed_producer_releases_fill_stage_and_source(exact, monkeypatch, stage):
    version = request('get', exact.url + '/detections').json['thumbnail_version']
    def fail(*args, **kwargs): raise OSError('injected failure')
    if stage == 'encode': monkeypatch.setattr(web.thumbs, 'encode_jpeg', fail)
    else: monkeypatch.setattr(web.thumbs.os, 'fsync', fail)
    response = request('get', exact.url + '/thumb/0?v=' + version)
    assert response.status_code == 500
    assert response.json['error'] == ('thumbnail_encode_failed' if stage == 'encode' else 'thumbnail_io_failed')
    state = web.FILES.initialize(exact.job).thumbnail
    assert not state.fills and not state.readers and state.retirement is None
    assert web.FILES.count == 0 and not list(exact.path.parent.glob('.thumb3-stage-*'))


def test_ordinary_images_do_not_require_exact_timing_policy(exact):
    doc = json.loads(exact.path.read_text())
    doc['provenance']['settings']['no_vfr_fix'] = True
    exact.path.write_text(json.dumps(doc))
    metadata = request('get', exact.url + '/detections')
    assert metadata.status_code == 200
    version = metadata.json['thumbnail_version']
    assert request('get', exact.url + '/thumb/0?v=' + version).status_code == 200
    assert request('get', exact.url + '/detframe/0?v=' + version).status_code == 200
    assert request('get', exact.url + '/edit_sample?t=0.2').status_code != 200


@pytest.mark.parametrize('action', ['scan', 'render'])
def test_routes_read_coherent_report_during_held_pipeline(scan, monkeypatch, action):
    fixture, _threads = scan
    assert request('get', fixture.url + '/detections').status_code == 200
    doc = json.loads(fixture.path.read_text())
    entered, resume = threading.Event(), threading.Event()
    def compute(args, cb):
        entered.set()
        assert resume.wait(8)
        if action == 'scan': return dict(source_report=doc, stats={})
        return {'output': str(fixture.path.parent / 'output.mp4')}
    monkeypatch.setattr(openscrub, 'run_scan' if action == 'scan' else 'run_pipeline', compute)
    worker = threading.Thread(target=web._run_job, args=(fixture.job, action))
    worker.start()
    try:
        assert entered.wait(5)
        metadata = request('get', fixture.url + '/detections')
        assert metadata.status_code == 200
        version = metadata.json['thumbnail_version']
        assert request('get', fixture.url + '/thumb/0?v=' + version).status_code == 200
        assert request('get', fixture.url + '/detframe/0?v=' + version).status_code == 200
    finally:
        resume.set()
        join(worker)


def test_active_render_may_own_cross_job_original_while_images_use_preview(exact, monkeypatch):
    other = web.new_job('', {}, 'original.avi')
    original_path = os.path.join(other['dir'], 'input.avi')
    with open(original_path, 'wb') as file:
        file.write(b'original source held by render')
    other['video'] = original_path
    doc = json.loads(exact.path.read_text())
    doc['provenance']['original_input'] = original_path
    exact.path.write_text(json.dumps(doc))
    entered, resume = threading.Event(), threading.Event()
    def render(args, cb):
        assert args.video == original_path
        entered.set()
        assert resume.wait(8)
        return {'output': str(exact.path.parent / 'output.mp4')}
    monkeypatch.setattr(openscrub, 'run_pipeline', render)
    worker = threading.Thread(target=web._run_job, args=(exact.job, 'render'))
    worker.start()
    try:
        assert entered.wait(5)
        assert request('delete', '/api/jobs/' + other['id']).status_code == 409
        metadata = request('get', exact.url + '/detections')
        assert metadata.status_code == 200
        image = request('get', exact.url + '/thumb/0?v=' + metadata.json['thumbnail_version'])
        assert image.status_code == 200
    finally:
        resume.set()
        join(worker)
    assert web.FILES.count == 0


def test_rehydrate_sweeps_only_owned_derivatives(exact):
    root = exact.path.parent
    owned = [root / 'thumb2_12.jpg', root / ('thumb3_' + 'a' * 32 + '_crop_2.jpg'),
             root / '.thumb3-stage-owned']
    unrelated = [root / 'thumb2_bad.jpg', root / ('thumb3_' + 'b' * 32 + '_other_2.jpg'),
                 root / 'unrelated.jpg']
    for path in owned + unrelated:
        path.write_bytes(b'not media')
    original_report = exact.path.read_bytes()
    with web.JOBS_LOCK:
        web.JOBS.pop(exact.job['id'])
    web.rehydrate_jobs()
    assert exact.job['id'] in web.JOBS
    assert request('get', exact.url + '/detections').status_code == 200
    assert all(not path.exists() for path in owned)
    assert all(path.read_bytes() == b'not media' for path in unrelated)
    assert exact.path.read_bytes() == original_report


def test_rehydrate_failed_sweep_blocks_until_later_owned_request(exact, monkeypatch):
    orphan = exact.path.parent / 'thumb2_0.jpg'
    orphan.write_bytes(b'orphan')
    with web.JOBS_LOCK:
        web.JOBS.pop(exact.job['id'])
    web.rehydrate_jobs()
    real_unlink = os.unlink
    attempts = []
    def fail_owned(path, *args, **kwargs):
        if os.fspath(path) == str(orphan):
            attempts.append(path)
            raise PermissionError('held artifact')
        return real_unlink(path, *args, **kwargs)
    monkeypatch.setattr(web.os, 'unlink', fail_owned)
    response = request('get', exact.url + '/detections')
    assert response.status_code == 409 and response.json['error'] == 'thumbnail_pending'
    assert len(attempts) == 3 and orphan.exists()
    monkeypatch.setattr(web.os, 'unlink', real_unlink)
    assert request('get', exact.url + '/detections').status_code == 200
    assert not orphan.exists()
