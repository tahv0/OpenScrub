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
from test_strict_tracking_routes import tracking, launch, joined


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


def test_successful_bound_association_survives_later_decode_failure(exact, monkeypatch):
    def unavailable(*args, **kwargs): raise web.thumbs.ThumbnailDecodeError('unavailable')
    monkeypatch.setattr(web, '_read_thumbnail_ordinal', unavailable)
    response = request('get', exact.url + '/thumb/0')
    assert response.status_code == 404 and response.json['error'] == 'thumbnail_unavailable'
    assert web.FILES.initialize(exact.job).source_report_bound
    doc = json.loads(exact.path.read_text())
    del doc['provenance']
    exact.path.write_text(json.dumps(doc))
    stale = request('get', exact.url + '/detections')
    assert stale.status_code == 409 and stale.json['error'] == 'thumbnail_source_conflict'


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


def test_native_drawing_error_is_structured_and_safe(exact, monkeypatch):
    version = request('get', exact.url + '/detections').json['thumbnail_version']
    def fail(*args, **kwargs): raise cv2.error('/private/source')
    monkeypatch.setattr(web.cv2, 'rectangle', fail)
    response = request('get', exact.url + '/detframe/0?v=' + version)
    assert response.status_code == 500 and response.json['error'] == 'thumbnail_encode_failed'
    assert b'/private/source' not in response.data
    assert web.FILES.count == 0 and not web.FILES.initialize(exact.job).thumbnail.fills


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
    original_open = web._thumbnail_open
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
    monkeypatch.setattr(web, '_thumbnail_open', held_open, raising=False)
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
    original_open = web._thumbnail_open
    class BrokenReader:
        def __init__(self, file): self.file = file
        def __getattr__(self, name): return getattr(self.file, name)
        def __enter__(self): return self
        def __exit__(self, *args): self.file.close()
        def read(self): raise OSError('injected read failure')
    def broken_open(path, *args, **kwargs):
        file = original_open(path, *args, **kwargs)
        return BrokenReader(file) if path == entry.path else file
    monkeypatch.setattr(web, '_thumbnail_open', broken_open, raising=False)
    response = request('get', url)
    assert response.status_code == 409 and response.json['error'] == 'thumbnail_obsolete'
    assert state.current is None and not state.readers


@pytest.mark.parametrize('failure', [openscrub.PipelineCancelled(), KeyboardInterrupt()])
def test_cached_reader_close_failure_preserves_primary_exception(exact, monkeypatch, failure):
    version = request('get', exact.url + '/detections').json['thumbnail_version']
    assert request('get', exact.url + '/thumb/0?v=' + version).status_code == 200
    files = web.FILES.initialize(exact.job)
    entry = files.thumbnail.entries[('crop', 0)]
    real_open = web._thumbnail_open
    class FailedReader:
        def __init__(self, file): self.file = file
        def __getattr__(self, name): return getattr(self.file, name)
        def __enter__(self): return self
        def __exit__(self, *args): self.close()
        def read(self): raise failure
        def close(self):
            self.file.close()
            raise OSError('injected close failure')
    def failed_open(path, *args, **kwargs):
        file = real_open(path, *args, **kwargs)
        return FailedReader(file) if path == entry.path else file
    monkeypatch.setattr(web, '_thumbnail_open', failed_open, raising=False)
    with pytest.raises(type(failure)) as caught:
        web._thumbnail_image(exact.job, 0, 'crop', version)
    assert caught.value is failure
    assert not files.thumbnail.readers and web.FILES.count == 0


def test_unclosed_cached_reader_retains_lease_until_later_cleanup(exact, monkeypatch):
    version = request('get', exact.url + '/detections').json['thumbnail_version']
    url = exact.url + '/thumb/0?v=' + version
    assert request('get', url).status_code == 200
    files = web.FILES.initialize(exact.job)
    entry = files.thumbnail.entries[('crop', 0)]
    failure = openscrub.PipelineCancelled()
    real_open, opened = web._thumbnail_open, []
    class RetryCloseReader:
        def __init__(self, file): self.file, self.attempts = file, 0
        def __getattr__(self, name): return getattr(self.file, name)
        def read(self): raise failure
        def close(self):
            self.attempts += 1
            if self.attempts == 1: raise OSError('injected close failure')
            self.file.close()
    def failed_open(path, *args, **kwargs):
        file = real_open(path, *args, **kwargs)
        if path == entry.path:
            file = RetryCloseReader(file)
            opened.append(file)
        return file
    monkeypatch.setattr(web, '_thumbnail_open', failed_open, raising=False)
    with pytest.raises(openscrub.PipelineCancelled) as caught:
        web._thumbnail_image(exact.job, 0, 'crop', version)
    assert caught.value is failure and web.FILES.count == 1
    assert files.thumbnail.retirement is not None and not opened[0].closed
    assert request('get', url).status_code == 409
    assert opened[0].closed and web.FILES.count == 0 and not files.thumbnail.readers


@pytest.mark.parametrize('transition', ['vault', 'delete'])
def test_lifecycle_retries_deferred_reader_without_thumbnail_request(exact, monkeypatch, transition):
    if transition == 'vault': exact.enable()
    version = request('get', exact.url + '/detections').json['thumbnail_version']
    url = exact.url + '/thumb/0?v=' + version
    assert request('get', url).status_code == 200
    entry = web.FILES.initialize(exact.job).thumbnail.entries[('crop', 0)]
    real_open, opened = web._thumbnail_open, []
    class RetryCloseReader:
        def __init__(self, file): self.file, self.attempts = file, 0
        def __getattr__(self, name): return getattr(self.file, name)
        def read(self): raise openscrub.PipelineCancelled()
        def close(self):
            self.attempts += 1
            if self.attempts == 1: raise OSError('injected close failure')
            self.file.close()
    def failed_open(path, *args, **kwargs):
        file = real_open(path, *args, **kwargs)
        if path == entry.path:
            file = RetryCloseReader(file)
            opened.append(file)
        return file
    monkeypatch.setattr(web, '_thumbnail_open', failed_open, raising=False)
    with pytest.raises(openscrub.PipelineCancelled):
        web._thumbnail_image(exact.job, 0, 'crop', version)
    assert web.FILES.count == 1 and not opened[0].closed
    result = (request('post', '/api/vault/lock') if transition == 'vault'
              else request('delete', exact.url))
    assert result.status_code == 200
    assert opened[0].closed and web.FILES.count == 0


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
        real_open = web._thumbnail_open
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
        monkeypatch.setattr(web, '_thumbnail_open', held_open, raising=False)
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
    original = request('get', exact.url + '/thumb/0?v=' + version)
    assert original.status_code == 200
    state = web.FILES.initialize(exact.job).thumbnail
    assert request('post', '/api/vault/lock').status_code == 200
    assert state.current is None
    assert request('post', '/api/vault/unlock', json={'password': 'synthetic-password'}).status_code == 200
    old = request('get', exact.url + '/thumb/0?v=' + version,
                  headers={'If-None-Match': original.headers['ETag']})
    assert old.status_code == 409 and old.json['error'] == 'thumbnail_obsolete'
    new_version = request('get', exact.url + '/detections').json['thumbnail_version']
    assert new_version != version
    current = request('get', exact.url + '/thumb/0?v=' + new_version)
    assert current.status_code == 200
    before = cv2.imdecode(np.frombuffer(original.data, np.uint8), cv2.IMREAD_COLOR)
    after = cv2.imdecode(np.frombuffer(current.data, np.uint8), cv2.IMREAD_COLOR)
    assert np.array_equal(before, after)


def test_nonblocking_vault_lock_does_not_wait_for_thumbnail_report_lock(exact):
    exact.enable()
    assert request('get', exact.url + '/detections').status_code == 200
    files = web.FILES.initialize(exact.job)
    done, errors = threading.Event(), []
    def lock_vault():
        try:
            web._vault_lock_now(blocking=False)
        except BaseException as error:
            errors.append(error)
        finally:
            done.set()
    with files.report_lock:
        worker = threading.Thread(target=lock_vault)
        worker.start()
        timely = done.wait(.5)
    join(worker)
    assert timely and len(errors) == 1 and isinstance(errors[0], web.FilesBusy)
    assert not web.vault_locked()


@pytest.mark.parametrize('transition', ['vault', 'delete'])
def test_active_cleanup_is_busy_before_retrying_deferred_reader(exact, monkeypatch, transition):
    exact.enable()
    version = request('get', exact.url + '/detections').json['thumbnail_version']
    assert request('get', exact.url + '/thumb/0?v=' + version).status_code == 200
    files = web.FILES.initialize(exact.job)
    entry = files.thumbnail.entries[('crop', 0)]
    real_open, readers = web._thumbnail_open, []
    class RetryCloseReader:
        def __init__(self, file): self.file, self.attempts = file, 0
        def __getattr__(self, name): return getattr(self.file, name)
        def read(self): raise openscrub.PipelineCancelled()
        def close(self):
            self.attempts += 1
            if self.attempts == 1: raise OSError('injected close failure')
            self.file.close()
    def held_open(path, *args, **kwargs):
        file = real_open(path, *args, **kwargs)
        if path == entry.path:
            file = RetryCloseReader(file)
            readers.append(file)
        return file
    monkeypatch.setattr(web, '_thumbnail_open', held_open, raising=False)
    with pytest.raises(openscrub.PipelineCancelled):
        web._thumbnail_image(exact.job, 0, 'crop', version)
    owner = web._prepare_work(exact.job, 'scan')
    with files.report_lock:
        web._begin_operation(exact.job, owner)
    exact.job['phase'] = 'review'
    real_lock = files.report_lock
    entered, resume, admission_locks = threading.Event(), threading.Event(), []
    errors = []
    class FinishGate:
        def __enter__(self):
            if threading.current_thread() is worker:
                entered.set()
                assert resume.wait(8)
            else:
                admission_locks.append(True)
            return real_lock.__enter__()
        def __exit__(self, *args): return real_lock.__exit__(*args)
    def finish_owner():
        try: web._finish_operation(exact.job, owner)
        except BaseException as error: errors.append(error)
    worker = threading.Thread(target=finish_owner)
    files.report_lock = FinishGate()
    worker.start()
    checked_busy = False
    try:
        assert entered.wait(5) and owner.released and files.active is owner
        assert request('post', '/api/vault/lock').status_code == 409
        assert not admission_locks and readers[0].attempts == 1 and not readers[0].closed
        checked_busy = True
    finally:
        resume.set()
        join(worker)
        files.report_lock = real_lock
        assert not errors
        if not checked_busy:
            web._thumbnail_lifecycle_cleanup(exact.job)
    response = (request('post', '/api/vault/lock') if transition == 'vault'
                else request('delete', exact.url))
    assert response.status_code == 200
    assert readers[0].closed and web.FILES.count == 0


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


def test_rehydrate_preserves_unverified_matching_files(exact):
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
    assert all(path.read_bytes() == b'not media' for path in owned + unrelated)
    assert exact.path.read_bytes() == original_report


def test_rehydrate_never_unlinks_an_unverified_matching_path(exact, monkeypatch):
    orphan = exact.path.parent / 'thumb2_0.jpg'
    orphan.write_bytes(b'orphan')
    with web.JOBS_LOCK:
        web.JOBS.pop(exact.job['id'])
    web.rehydrate_jobs()
    real_unlink, attempts = os.unlink, []
    def observed_unlink(path, *args, **kwargs):
        if os.fspath(path) == str(orphan): attempts.append(path)
        return real_unlink(path, *args, **kwargs)
    monkeypatch.setattr(web.os, 'unlink', observed_unlink)
    assert request('get', exact.url + '/detections').status_code == 200
    assert not attempts and orphan.read_bytes() == b'orphan'


def test_rehydration_never_sweeps_its_selected_matching_media(exact):
    selected = exact.path.parent / 'thumb2_71.jpg'
    selected.write_bytes(open(exact.job['video'], 'rb').read())
    original = selected.read_bytes()
    identity = (selected.stat().st_dev, selected.stat().st_ino)
    doc = json.loads(exact.path.read_text())
    doc['provenance']['input'] = str(selected)
    exact.path.write_text(json.dumps(doc))
    with web.JOBS_LOCK:
        web.JOBS.pop(exact.job['id'])
    web.rehydrate_jobs()
    response = request('get', exact.url + '/detections')
    assert response.status_code == 200
    assert selected.read_bytes() == original
    assert (selected.stat().st_dev, selected.stat().st_ino) == identity


@pytest.mark.parametrize('missing', ['category', 'text'])
@pytest.mark.parametrize('route', ['/detections', '/thumb/0', '/detframe/0'])
def test_required_projection_fields_rejected_consistently(exact, missing, route):
    doc = json.loads(exact.path.read_text())
    del doc['detections'][0][missing]
    exact.path.write_text(json.dumps(doc))
    response = request('get', exact.url + route)
    assert response.status_code == 500
    assert response.json['error'] == 'thumbnail_invalid_report'
    assert web.FILES.initialize(exact.job).thumbnail.current is None


def test_competing_discovery_after_generation_retirement_is_pending(exact, monkeypatch):
    assert request('get', exact.url + '/detections').status_code == 200
    files = web.FILES.initialize(exact.job)
    state = files.thumbnail
    competing = []
    def retire_after_observation(job):
        with files.report_lock:
            current = state.current
            web.thumbs.invalidate_locked(state, 'injected race')
            competing.append(web.thumbs.begin_discovery_locked(state))
        return current, None
    monkeypatch.setattr(web, '_thumbnail_reserve_discovery', retire_after_observation)
    try:
        response = request('get', exact.url + '/detections')
        assert response.status_code == 409
        assert response.json['error'] == 'thumbnail_pending'
    finally:
        with files.report_lock:
            if competing:
                web.thumbs.finish_discovery_locked(state, competing[0])


def test_interrupted_retry_leaves_other_deferred_reader_recoverable(exact):
    version = request('get', exact.url + '/detections').json['thumbnail_version']
    for route in ('thumb', 'detframe'):
        assert request('get', exact.url + '/' + route + '/0?v=' + version).status_code == 200
    files = web.FILES.initialize(exact.job)
    state = files.thumbnail
    readers = []
    class FailingClose:
        def __init__(self, file): self.file, self.attempts = file, 0
        def __getattr__(self, name): return getattr(self.file, name)
        def close(self):
            self.attempts += 1
            if self.attempts == 1: raise OSError('first close')
            if self.attempts == 2: raise KeyboardInterrupt('retry interrupted')
            self.file.close()
    try:
        for entry in list(state.entries.values()):
            lease = web._own_files(exact.job)
            opened = FailingClose(open(entry.path, 'rb'))
            with files.report_lock:
                reader = web.thumbs.begin_reader_locked(state, state.current, entry, opened)
                web.thumbs.defer_resource_locked(state, reader, lease)
            readers.append(reader)
            with pytest.raises(OSError): opened.close()
        with files.report_lock: web.thumbs.invalidate_locked(state, 'deferred test')
        with pytest.raises(KeyboardInterrupt): web._thumbnail_cleanup(exact.job)
        assert all(not getattr(reader, '_close_claimed', False) for reader in state.readers)
        for _ in range(4):
            if not state.readers: break
            try: web._thumbnail_cleanup(exact.job)
            except KeyboardInterrupt: pass
        assert not state.readers and all(reader.file.closed for reader in readers)
        assert web.FILES.count == 0
    finally:
        for reader in readers:
            if not reader.file.closed: reader.file.file.close()
            if reader in state.readers:
                with files.report_lock:
                    if reader in state.deferred:
                        discarded = web.thumbs.remove_deferred_locked(state, reader)
                    web.thumbs.end_reader_locked(state, reader)
                    lease, reader._deferred_lease = reader._deferred_lease, None
                discarded = None
                if lease is not None: lease.release()


def test_stale_report_read_cannot_retire_managed_scan_adoption(scan, monkeypatch):
    fixture, threads = scan
    files = web.FILES.initialize(fixture.job)
    assert request('get', fixture.url + '/detections').status_code == 200
    old_path = fixture.job['video']
    new_path = str(fixture.path.parent / 'normalized.avi')
    with open(old_path, 'rb') as src, open(new_path, 'wb') as dst:
        dst.write(src.read())
    entered, resume = threading.Event(), threading.Event()
    local = threading.local()
    real_load, real_path = web.json.load, os.path.realpath
    def load(*args, **kwargs):
        result = real_load(*args, **kwargs)
        if threading.current_thread().name == 'held-old-report': local.read_report = True
        return result
    def realpath(path, *args, **kwargs):
        if (threading.current_thread().name == 'held-old-report'
                and getattr(local, 'read_report', False) and path == old_path):
            local.read_report = False
            entered.set()
            assert resume.wait(8)
        return real_path(path, *args, **kwargs)
    def compute(args, cb):
        args.original_video, args.video = args.video, new_path
        return dict(fps=5, cum=[[0, 0]] * 10, bands=[[0, 0]] * 10,
                    detections=[], stats={})
    monkeypatch.setattr(web.json, 'load', load)
    monkeypatch.setattr(web.os.path, 'realpath', realpath)
    monkeypatch.setattr(openscrub, 'run_scan', compute)
    result, errors = [], []
    def read_old():
        try: result.append(request('get', fixture.url + '/detections'))
        except BaseException as exc: errors.append(exc)
    worker = threading.Thread(name='held-old-report', target=read_old)
    worker.start()
    try:
        assert entered.wait(5)
        web._run_job(fixture.job, 'scan')
        selected = files.current_source
        assert selected is not None and selected['path'] == new_path
        ref = selected['source_ref']
    finally:
        resume.set()
        join(worker)
    assert not errors and result[0].status_code == 409
    assert files.current_source is selected and files.current_source['source_ref'] == ref
    assert request('get', fixture.url + '/detections').status_code == 200


@pytest.mark.skipif(not hasattr(os, 'mkfifo'), reason='named pipes unavailable')
@pytest.mark.parametrize('target', ['report', 'jpeg'])
def test_fifo_inputs_return_prompt_structured_error_without_leases(exact, target):
    version = request('get', exact.url + '/detections').json['thumbnail_version']
    if target == 'jpeg':
        assert request('get', exact.url + '/thumb/0?v=' + version).status_code == 200
        path = web.FILES.initialize(exact.job).thumbnail.entries[('crop', 0)].path
        url = exact.url + '/thumb/0?v=' + version
    else:
        path, url = str(exact.path), exact.url + '/detections'
    backup = path + '.backup-test'
    os.rename(path, backup)
    os.mkfifo(path)
    done, responses, errors = threading.Event(), [], []
    def run():
        try: responses.append(request('get', url))
        except BaseException as exc: errors.append(exc)
        finally: done.set()
    worker = threading.Thread(target=run)
    worker.start()
    try:
        prompt = done.wait(1)
        if not prompt:
            fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)
            try: os.write(fd, b'not-json')
            finally: os.close(fd)
        join(worker)
        assert prompt
        assert not errors and responses[0].is_json
        assert responses[0].json['error'] == ('thumbnail_invalid_report' if target == 'report' else 'thumbnail_obsolete')
        assert responses[0].status_code == (500 if target == 'report' else 409)
        assert web.FILES.count == 0
    finally:
        if worker.is_alive():
            fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)
            try: os.write(fd, b'rescue')
            finally: os.close(fd)
            join(worker)
        if os.path.lexists(path): os.unlink(path)
        os.rename(backup, path)


def test_deleting_source_job_drains_another_jobs_deferred_reader(exact, monkeypatch):
    other = web.new_job('', {}, 'source.avi')
    source = os.path.join(other['dir'], 'source.avi')
    with open(exact.job['video'], 'rb') as src, open(source, 'wb') as dst:
        dst.write(src.read())
    other['video'] = source
    other['phase'] = 'review'
    exact.job['video'] = source
    doc = json.loads(exact.path.read_text())
    doc['provenance']['input'] = source
    exact.path.write_text(json.dumps(doc))
    version = request('get', exact.url + '/detections').json['thumbnail_version']
    assert request('get', exact.url + '/thumb/0?v=' + version).status_code == 200
    files = web.FILES.initialize(exact.job)
    entry = files.thumbnail.entries[('crop', 0)]
    real_open, opened_files = web._thumbnail_open, []
    class DelayedClose:
        def __init__(self, file): self.file, self.attempts = file, 0
        def __getattr__(self, name): return getattr(self.file, name)
        def read(self): raise openscrub.PipelineCancelled()
        def close(self):
            self.attempts += 1
            if self.attempts == 1: raise OSError('transient close')
            self.file.close()
    def wrapped(path, *args, **kwargs):
        f = real_open(path, *args, **kwargs)
        if path == entry.path:
            f = DelayedClose(f)
            opened_files.append(f)
        return f
    monkeypatch.setattr(web, '_thumbnail_open', wrapped, raising=False)
    try:
        with pytest.raises(openscrub.PipelineCancelled):
            web._thumbnail_image(exact.job, 0, 'crop', version)
        assert files.thumbnail.readers and not opened_files[0].closed
        assert request('delete', '/api/jobs/' + other['id']).status_code == 200
        assert opened_files[0].closed and not files.thumbnail.readers
        assert web.FILES.count == 0
        assert exact.job['id'] in web.JOBS
    finally:
        web._thumbnail_lifecycle_cleanup(exact.job)


def test_rehydration_preserves_media_referenced_by_another_live_job(exact):
    owned_dir = exact.path.parent
    referenced = owned_dir / ('thumb3_' + 'a' * 32 + '_crop_7.jpg')
    referenced.write_bytes(b'other job source data')
    identity = (referenced.stat().st_dev, referenced.stat().st_ino)
    other = web.new_job('', {}, 'other source')
    alias = os.path.join(other['dir'], 'other-source.avi')
    os.link(referenced, alias)
    other['video'] = alias
    other['phase'] = 'review'
    with web.JOBS_LOCK: web.JOBS.pop(exact.job['id'])
    web.rehydrate_jobs()
    assert request('get', exact.url + '/detections').status_code == 200
    assert referenced.read_bytes() == b'other job source data'
    assert (referenced.stat().st_dev, referenced.stat().st_ino) == identity
    assert os.stat(alias).st_ino == identity[1]


def test_rehydrated_unknown_files_do_not_block_unrelated_admission(exact):
    orphan = exact.path.parent / 'thumb2_141.jpg'
    orphan.write_bytes(b'unknown')
    with web.JOBS_LOCK: web.JOBS.pop(exact.job['id'])
    web.rehydrate_jobs()
    assert request('get', exact.url + '/detections').status_code == 200
    assert request('get', '/api/jobs').status_code == 200
    assert orphan.read_bytes() == b'unknown' and web.FILES.count == 0


def test_failed_stage_writer_close_retains_owner_until_lifecycle_retry(exact, monkeypatch):
    version = request('get', exact.url + '/detections').json['thumbnail_version']
    files = web.FILES.initialize(exact.job)
    real_wrap, writers = web.thumbs._stage_wrap, []
    prepare, observed_leases = web._prepare_observed_source, []
    def tracked_prepare(*args):
        result = prepare(*args)
        observed_leases.append(result[1])
        return result
    monkeypatch.setattr(web, '_prepare_observed_source', tracked_prepare)
    primary = openscrub.PipelineCancelled()
    class FailingWriter:
        def __init__(self, file): self.file, self.attempts = file, 0
        def __getattr__(self, name): return getattr(self.file, name)
        def __enter__(self): return self
        def __exit__(self, *args): self.close()
        def write(self, data): raise primary
        def close(self):
            self.attempts += 1
            if self.attempts == 1: raise OSError('transient writer close')
            self.file.close()
    def wrap(raw, ticket):
        file = FailingWriter(real_wrap(raw, ticket))
        writers.append(file)
        return file
    monkeypatch.setattr(web.thumbs, '_stage_wrap', wrap)
    try:
        with pytest.raises(openscrub.PipelineCancelled) as caught:
            web._thumbnail_image(exact.job, 0, 'crop', version)
        assert caught.value is primary
        assert len(writers) == 1 and not writers[0].closed
        assert len(files.thumbnail.fills) == 1 and web.FILES.count > 0
        web._thumbnail_lifecycle_cleanup(exact.job)
        assert writers[0].closed and not files.thumbnail.fills
        assert web.FILES.count == 0
        assert not list(exact.path.parent.glob('.thumb3-stage-*'))
    finally:
        for writer in writers:
            if not writer.closed: writer.file.close()
        for fill in list(files.thumbnail.fills):
            if not fill.stage_closed:
                fill.stage_closed = True
            with files.report_lock: web.thumbs.finish_fill_locked(files.thumbnail, fill)
            lease = getattr(fill, '_deferred_lease', None)
            if lease is not None: lease.release()
        for lease in observed_leases: lease.release()


def test_opened_cache_handle_is_pinned_before_retirement(exact, monkeypatch):
    version = request('get', exact.url + '/detections').json['thumbnail_version']
    assert request('get', exact.url + '/thumb/0?v=' + version).status_code == 200
    files = web.FILES.initialize(exact.job)
    path = files.thumbnail.entries[('crop', 0)].path
    real_open = web._thumbnail_open
    entered, resume, saved = threading.Event(), threading.Event(), threading.Event()
    results, errors = [], []
    def held_open(name, *args, **kwargs):
        file = real_open(name, *args, **kwargs)
        if name == path and threading.current_thread().name == 'held-cache-open':
            entered.set()
            assert resume.wait(8)
        return file
    monkeypatch.setattr(web, '_thumbnail_open', held_open, raising=False)
    def read():
        try: results.append(request('get', exact.url + '/thumb/0?v=' + version))
        except BaseException as error: errors.append(error)
    def save():
        try: request('post', exact.url + '/detections', json={'enabled': {'0': False}})
        except BaseException as error: errors.append(error)
        finally: saved.set()
    reader = threading.Thread(name='held-cache-open', target=read)
    writer = threading.Thread(target=save)
    reader.start()
    try:
        assert entered.wait(5)
        writer.start()
        save_early = saved.wait(.3)
        if save_early:
            web._thumbnail_cleanup(exact.job)
        protected = os.path.exists(path)
    finally:
        resume.set()
        join(reader)
        if writer.ident is not None: join(writer)
    assert not errors and protected
    assert results[0].status_code in (200, 409)
    assert web.FILES.count == 0


def test_rejected_cache_reader_close_failure_keeps_lease_until_retry(exact, monkeypatch):
    version = request('get', exact.url + '/detections').json['thumbnail_version']
    assert request('get', exact.url + '/thumb/0?v=' + version).status_code == 200
    files = web.FILES.initialize(exact.job)
    path = files.thumbnail.entries[('crop', 0)].path
    real_open, opened = web._thumbnail_open, []
    class BadStat:
        def __init__(self, file): self.file, self.attempts = file, 0
        def __getattr__(self, name): return getattr(self.file, name)
        def fileno(self): raise OSError('injected descriptor rejection')
        def close(self):
            self.attempts += 1
            if self.attempts == 1: raise OSError('injected close failure')
            self.file.close()
    def wrapped(name, *args, **kwargs):
        file = real_open(name, *args, **kwargs)
        if name == path:
            file = BadStat(file)
            opened.append(file)
        return file
    monkeypatch.setattr(web, '_thumbnail_open', wrapped, raising=False)
    try:
        with pytest.raises(web._ThumbnailError) as error:
            web._thumbnail_image(exact.job, 0, 'crop', version)
        assert error.value.code == 'thumbnail_obsolete'
        assert len(files.thumbnail.readers) == 1 and web.FILES.count > 0
        assert not opened[0].closed
        web._thumbnail_lifecycle_cleanup(exact.job)
        assert opened[0].closed and not files.thumbnail.readers and web.FILES.count == 0
    finally:
        for file in opened:
            if not file.closed: file.file.close()
        for reader in list(files.thumbnail.readers):
            if reader.file.closed:
                with files.report_lock:
                    if reader in files.thumbnail.deferred:
                        discarded = web.thumbs.remove_deferred_locked(files.thumbnail, reader)
                    web.thumbs.end_reader_locked(files.thumbnail, reader)
                    owner, reader._deferred_lease = getattr(reader, '_deferred_lease', None), None
                discarded = None
                if owner is not None: owner.release()


def test_open_wrapper_construction_failure_retains_real_handle(exact, monkeypatch):
    version = request('get', exact.url + '/detections').json['thumbnail_version']
    assert request('get', exact.url + '/thumb/0?v=' + version).status_code == 200
    files = web.FILES.initialize(exact.job)
    original = web._thumbnail_open
    primary = openscrub.PipelineCancelled()
    opened = []
    class RetryClose:
        def __init__(self, file): self.file, self.attempts = file, 0
        def __getattr__(self, name): return getattr(self.file, name)
        def close(self):
            self.attempts += 1
            if self.attempts == 1: raise OSError('transient close')
            self.file.close()
    def fail_after_open(path, reader):
        file = RetryClose(original(path, reader))
        opened.append(file)
        reader.file = file
        raise primary
    monkeypatch.setattr(web, '_thumbnail_open', fail_after_open)
    try:
        with pytest.raises(openscrub.PipelineCancelled) as caught:
            web._thumbnail_image(exact.job, 0, 'crop', version)
        assert caught.value is primary
        assert len(files.thumbnail.readers) == 1 and web.FILES.count > 0
        assert not opened[0].closed
        web._thumbnail_lifecycle_cleanup(exact.job)
        assert opened[0].closed and not files.thumbnail.readers and web.FILES.count == 0
    finally:
        for file in opened:
            if not file.closed: file.file.close()
        for reader in list(files.thumbnail.readers):
            if reader.file is None or reader.file.closed:
                with files.report_lock:
                    if reader in files.thumbnail.deferred:
                        discarded = web.thumbs.remove_deferred_locked(files.thumbnail, reader)
                    web.thumbs.end_reader_locked(files.thumbnail, reader)
                    owner, reader._deferred_lease = getattr(reader, '_deferred_lease', None), None
                discarded = None
                if owner is not None: owner.release()


def test_failed_managed_save_keeps_current_version_and_jpeg(exact, monkeypatch):
    metadata = request('get', exact.url + '/detections').json
    version = metadata['thumbnail_version']
    url = exact.url + '/thumb/0?v=' + version
    before = request('get', url)
    assert before.status_code == 200
    report = exact.path.read_bytes()
    def fail(*args, **kwargs): raise OSError('failed managed publication')
    monkeypatch.setattr(web, 'atomic_report', fail)
    response = request('post', exact.url + '/detections', json={'enabled': {'0': False}})
    assert response.status_code == 500
    assert exact.path.read_bytes() == report
    after = request('get', url)
    assert after.status_code == 200 and after.data == before.data
    assert after.headers['ETag'] == before.headers['ETag']
    assert request('get', exact.url + '/detections').json['thumbnail_version'] == version


def test_late_pregeneration_stage_cannot_publish_after_save(scan, monkeypatch):
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
    for row in doc['detections']:
        row['cbox'] = [55, 45, 105, 75]
    entered, resume = threading.Event(), threading.Event()
    real_stage = web.thumbs.stage_jpeg
    def stage(job_dir, ticket, jpeg):
        result = real_stage(job_dir, ticket, jpeg)
        if ticket.index == 0:
            entered.set()
            assert resume.wait(8)
        return result
    monkeypatch.setattr(web.thumbs, 'stage_jpeg', stage)
    monkeypatch.setattr(openscrub, 'run_scan', lambda args, cb: dict(source_report=doc, stats={}))
    web._run_job(fixture.job, 'scan')
    try:
        assert entered.wait(5)
        old = request('get', fixture.url + '/detections').json['thumbnail_version']
        assert request('post', fixture.url + '/detections', json={'enabled': {'0': False}}).status_code == 200
    finally:
        resume.set()
        for thread in threads: join(thread)
    fresh = request('get', fixture.url + '/detections').json['thumbnail_version']
    assert fresh != old
    assert request('get', fixture.url + '/thumb/0?v=' + old).status_code == 409
    assert request('get', fixture.url + '/thumb/0?v=' + fresh).status_code == 200
    entries = web.FILES.initialize(fixture.job).thumbnail.entries
    assert {str(path) for path in fixture.path.parent.glob('.thumb3-stage-*')} == {
        entry.path for entry in entries.values()}


def test_successful_track_append_retires_current_thumbnail(tracking):
    exact = tracking.exact
    before = request('get', exact.url + '/detections').json
    old = before['thumbnail_version']
    assert request('get', exact.url + '/thumb/0?v=' + old).status_code == 200
    launch(tracking)
    status = joined(tracking)
    assert status['state'] == 'done' and status['added'] == 1 and status['error'] is None
    stale = request('get', exact.url + '/thumb/0?v=' + old)
    assert stale.status_code == 409 and stale.json['error'] == 'thumbnail_obsolete'
    after = request('get', exact.url + '/detections').json
    assert after['thumbnail_version'] != old
    assert len(after['detections']) == len(before['detections']) + 1
    assert request('get', exact.url + '/thumb/0?v=' + after['thumbnail_version']).status_code == 200


@pytest.mark.parametrize('change', ['box', 'timing', 'last', 'fps', 'cum', 'reorder', 'source'])
def test_managed_scan_changes_actual_thumbnail_pixels(scan, monkeypatch, change):
    fixture, threads = scan
    doc = json.loads(fixture.path.read_text())
    for row in doc['detections']:
        row.update(t_start=0, t_end=1, last_seen=.2, cbox=[10, 10, 20, 20])
    doc['render_state']['cum'] = [[0, 0] for _ in range(10)]
    fixture.path.write_text(json.dumps(doc))
    old = request('get', fixture.url + '/detections').json['thumbnail_version']
    old_image = request('get', fixture.url + '/detframe/0?v=' + old)
    assert old_image.status_code == 200
    before = cv2.imdecode(np.frombuffer(old_image.data, np.uint8), 1)
    assert abs(float(before[40, 50].mean()) - 20) < 6
    if change == 'box': doc['detections'][0]['cbox'] = [30, 10, 40, 20]
    elif change == 'timing': doc['detections'][0].update(t_start=.6, t_end=.8, last_seen=.6)
    elif change == 'last': doc['detections'][0]['last_seen'] = .8
    elif change == 'fps': doc['render_state']['fps'] = 10
    elif change == 'cum': doc['render_state']['cum'][1] = [10, 0]
    elif change == 'reorder':
        doc['detections'][1]['last_seen'] = .8
        doc['detections'].reverse()
    new_path = str(fixture.path.parent / 'new-source.avi')
    if change == 'source':
        writer = cv2.VideoWriter(new_path, cv2.VideoWriter_fourcc(*'MJPG'), 5, (64, 48))
        assert writer.isOpened()
        try:
            for _ in range(10): writer.write(np.full((48, 64, 3), 150, np.uint8))
        finally: writer.release()
    def compute(args, cb):
        if change == 'source': args.original_video, args.video = args.video, new_path
        return dict(source_report=doc, stats={})
    monkeypatch.setattr(openscrub, 'run_scan', compute)
    web._run_job(fixture.job, 'scan')
    for thread in threads: join(thread)
    assert request('get', fixture.url + '/detframe/0?v=' + old,
                   headers={'If-None-Match': old_image.headers['ETag']}).status_code == 409
    newer = request('get', fixture.url + '/detections').json['thumbnail_version']
    assert newer != old
    image = request('get', fixture.url + '/detframe/0?v=' + newer)
    assert image.status_code == 200
    after = cv2.imdecode(np.frombuffer(image.data, np.uint8), 1)
    if change in ('box', 'cum'):
        new_x = 26 if change == 'box' else 16
        assert int(before[6, 6, 2]) > int(before[6, 6, 0]) + 40
        assert int(after[6, new_x, 2]) > int(after[6, new_x, 0]) + 40
        assert int(after[6, 6, 2]) < int(after[6, 6, 0]) + 40
    else:
        expected = {'timing': 60, 'last': 80, 'fps': 40, 'reorder': 80, 'source': 150}[change]
        assert abs(float(after[40, 50].mean()) - expected) < 7


def test_raw_thumbnail_descriptor_is_closed_once(exact, monkeypatch):
    version = request('get', exact.url + '/detections').json['thumbnail_version']
    url = exact.url + '/thumb/0?v=' + version
    assert request('get', url).status_code == 200
    real_open, real_close, descriptors, closed = web._thumbnail_open, os.close, [], []
    def tracked_open(path, reader):
        handle = real_open(path, reader)
        descriptors.append(handle.fileno())
        return handle
    def tracked_close(fd):
        if fd in descriptors: closed.append(fd)
        return real_close(fd)
    monkeypatch.setattr(web, '_thumbnail_open', tracked_open)
    monkeypatch.setattr(web.os, 'close', tracked_close)
    assert request('get', url).status_code == 200
    assert len(descriptors) == 1 and closed == descriptors
    assert web.FILES.count == 0


def test_deleting_containing_job_retries_deferred_writer(exact, monkeypatch):
    other = web.new_job('', {}, 'source.avi')
    source = os.path.join(other['dir'], 'source.avi')
    with open(exact.job['video'], 'rb') as src, open(source, 'wb') as dst:
        dst.write(src.read())
    other['video'], other['phase'] = source, 'review'
    exact.job['video'] = source
    doc = json.loads(exact.path.read_text())
    doc['provenance']['input'] = source
    exact.path.write_text(json.dumps(doc))
    version = request('get', exact.url + '/detections').json['thumbnail_version']
    real_wrap, writers = web.thumbs._stage_wrap, []
    class FailingWriter:
        def __init__(self, file): self.file, self.attempts = file, 0
        def __getattr__(self, name): return getattr(self.file, name)
        def write(self, data): raise openscrub.PipelineCancelled()
        def close(self):
            self.attempts += 1
            if self.attempts == 1: raise OSError('transient close')
            self.file.close()
    def wrap(raw, ticket):
        file = FailingWriter(real_wrap(raw, ticket))
        writers.append(file)
        return file
    monkeypatch.setattr(web.thumbs, '_stage_wrap', wrap)
    files = web.FILES.initialize(exact.job)
    try:
        with pytest.raises(openscrub.PipelineCancelled):
            web._thumbnail_image(exact.job, 0, 'crop', version)
        assert len(files.thumbnail.fills) == 1 and not writers[0].closed
        assert request('delete', '/api/jobs/' + other['id']).status_code == 200
        assert writers[0].closed and not files.thumbnail.fills and web.FILES.count == 0
    finally:
        web._thumbnail_lifecycle_cleanup(exact.job)


def test_retired_entry_collection_is_disposed_outside_report_lock(exact):
    version = request('get', exact.url + '/detections').json['thumbnail_version']
    assert request('get', exact.url + '/thumb/0?v=' + version).status_code == 200
    files = web.FILES.initialize(exact.job)
    disposal = []
    class TrackedEntries(dict):
        def __del__(self): disposal.append(files.report_lock.locked())
    files.thumbnail.entries = TrackedEntries(files.thumbnail.entries)
    assert request('post', exact.url + '/detections', json={'enabled': {'0': False}}).status_code == 200
    assert request('get', exact.url + '/detections').status_code == 200
    assert disposal == [False]


def test_stage_wrapper_construction_failure_preserves_primary_and_owner(exact, monkeypatch):
    version = request('get', exact.url + '/detections').json['thumbnail_version']
    files = web.FILES.initialize(exact.job)
    real_wrap, real_close = web.thumbs._stage_wrap, os.close
    primary = openscrub.PipelineCancelled()
    owned, descriptors = [], []
    class CloseOnceFailure:
        def __init__(self, file): self.file, self.attempts = file, 0
        def __getattr__(self, name): return getattr(self.file, name)
        def close(self):
            self.attempts += 1
            if self.attempts == 1: raise OSError('wrapper close failure')
            self.file.close()
    def fail_wrapper(raw, ticket):
        file = real_wrap(raw, ticket)
        wrapper = CloseOnceFailure(file)
        ticket.stage_writer = wrapper
        owned.append(wrapper)
        descriptors.append(file.fileno())
        raise primary
    def fail_close(fd):
        if fd in descriptors and owned[0].attempts == 0:
            raise OSError('construction cleanup failed')
        return real_close(fd)
    monkeypatch.setattr(web.thumbs, '_stage_wrap', fail_wrapper)
    monkeypatch.setattr(web.thumbs.os, 'close', fail_close)
    try:
        with pytest.raises(openscrub.PipelineCancelled) as caught:
            web._thumbnail_image(exact.job, 0, 'crop', version)
        assert caught.value is primary and len(files.thumbnail.fills) == 1
        assert not owned[0].closed and web.FILES.count > 0
        web._thumbnail_lifecycle_cleanup(exact.job)
        assert owned[0].closed and not files.thumbnail.fills and web.FILES.count == 0
    finally:
        for file in owned:
            if not file.closed: file.file.close()
        for fill in list(files.thumbnail.fills):
            fill.stage_closed = True
            with files.report_lock: web.thumbs.finish_fill_locked(files.thumbnail, fill)
            owner = getattr(fill, '_deferred_lease', None)
            if owner is not None: owner.release()


@pytest.mark.parametrize('kind', ['thumb', 'detframe'])
@pytest.mark.parametrize('containing_job', [False, True])
def test_first_rehydrated_unversioned_image_can_finish_sweep(exact, kind, containing_job):
    if containing_job:
        other = web.new_job('', {}, 'source.avi')
        source = os.path.join(other['dir'], 'source.avi')
        with open(exact.job['video'], 'rb') as src, open(source, 'wb') as dst:
            dst.write(src.read())
        other['video'], other['phase'] = source, 'review'
        exact.job['video'] = source
        doc = json.loads(exact.path.read_text())
        doc['provenance']['input'] = source
        exact.path.write_text(json.dumps(doc))
    orphan = exact.path.parent / 'thumb2_44.jpg'
    orphan.write_bytes(b'obsolete')
    with web.JOBS_LOCK: web.JOBS.pop(exact.job['id'])
    web.rehydrate_jobs()
    response = request('get', exact.url + '/' + kind + '/0')
    assert response.status_code == 200
    assert orphan.read_bytes() == b'obsolete' and web.FILES.count == 0


@pytest.mark.parametrize('factory', [web._ThumbnailHandle, web.thumbs._StageHandle])
def test_ambiguous_os_close_is_never_retried_as_a_raw_integer(tmp_path, monkeypatch, factory):
    file = tmp_path / 'descriptor'
    file.write_bytes(b'data')
    handle = factory()
    handle.fd = os.open(file, os.O_RDONLY)
    target, real_close, calls = handle.fd, os.close, []
    def consumed_then_error(fd):
        if fd == target:
            calls.append(fd)
            real_close(fd)
            raise OSError('ambiguous close')
        return real_close(fd)
    monkeypatch.setattr(os, 'close', consumed_then_error)
    with pytest.raises(OSError): handle.close()
    assert handle.close_uncertain and not handle.closed
    with pytest.raises(OSError): handle.close()
    assert calls == [target]


@pytest.mark.parametrize('owner', ['thumbnail', 'exact'])
def test_stale_report_fence_precedes_source_retirement(exact, owner):
    doc, selected, fence, lease = web._thumbnail_snapshot(exact.job)
    files = web.FILES.initialize(exact.job)
    try:
        exact.path.write_text(json.dumps(dict(doc, future='report changed')))
        source = exact.job['video']
        replacement = source + '.new'
        with open(source, 'rb') as src, open(replacement, 'wb') as dst:
            dst.write(src.read())
        os.replace(replacement, source)
        with files.report_lock:
            if owner == 'thumbnail':
                with pytest.raises(web._ThumbnailError) as error:
                    web._thumbnail_current_locked(exact.job, selected, fence)
                assert error.value.code == 'thumbnail_obsolete'
            else:
                with pytest.raises(web.exact.ExactError) as error:
                    web._exact_current_locked(exact.job, selected, fence)
                assert error.value.code == 'sample_conflict'
            assert files.current_source is selected and not files.source_retired
    finally:
        lease.release()


def test_sweep_preserves_original_and_output_matching_names(exact):
    root = exact.path.parent
    original = root / 'thumb2_101.jpg'
    output = root / '.thumb3-stage-output'
    original.write_bytes(b'original media')
    output.write_bytes(b'render output')
    doc = json.loads(exact.path.read_text())
    doc['provenance'].update(original_input=str(original), output=str(output))
    exact.path.write_text(json.dumps(doc))
    with web.JOBS_LOCK: web.JOBS.pop(exact.job['id'])
    web.rehydrate_jobs()
    assert request('get', exact.url + '/detections').status_code == 200
    assert original.read_bytes() == b'original media'
    assert output.read_bytes() == b'render output'


def test_sweep_with_unknown_other_report_preserves_all_candidates(exact):
    orphan = exact.path.parent / 'thumb2_90.jpg'
    orphan.write_bytes(b'could be media')
    other = web.new_job('', {}, 'unknown report')
    other['phase'] = 'review'
    with open(os.path.join(other['dir'], 'report.json'), 'w') as file:
        file.write('{bad json')
    with web.JOBS_LOCK: web.JOBS.pop(exact.job['id'])
    web.rehydrate_jobs()
    response = request('get', exact.url + '/detections')
    assert response.status_code == 200
    assert orphan.read_bytes() == b'could be media'


def test_cleanup_interrupt_does_not_mask_primary_decode_cancel(exact, monkeypatch):
    version = request('get', exact.url + '/detections').json['thumbnail_version']
    primary = openscrub.PipelineCancelled()
    real_cleanup, calls = web._thumbnail_cleanup, []
    def cleanup(job):
        calls.append(True)
        if len(calls) == 2: raise KeyboardInterrupt('cleanup interrupted')
        return real_cleanup(job)
    def decode(*args, **kwargs): raise primary
    monkeypatch.setattr(web, '_thumbnail_cleanup', cleanup)
    monkeypatch.setattr(web, '_read_thumbnail_ordinal', decode)
    with pytest.raises(openscrub.PipelineCancelled) as caught:
        web._thumbnail_image(exact.job, 0, 'crop', version)
    assert caught.value is primary and web.FILES.count == 0


def test_vault_cleanup_lookup_does_not_scan_live_nondeferred_readers(exact):
    version = request('get', exact.url + '/detections').json['thumbnail_version']
    assert request('get', exact.url + '/thumb/0?v=' + version).status_code == 200
    files = web.FILES.initialize(exact.job)
    state = files.thumbnail
    entry = state.entries[('crop', 0)]
    class NoScan(set):
        def __iter__(self): raise AssertionError('live-reader scan under report lock')
    readers, leases = [], []
    try:
        for _ in range(128):
            lease = web._own_files(exact.job)
            leases.append(lease)
            opened = open(entry.path, 'rb')
            with files.report_lock:
                readers.append(web.thumbs.begin_reader_locked(state, state.current, entry, opened))
        state.readers = NoScan(state.readers)
        web._thumbnail_lifecycle_cleanup(exact.job)
        assert len(state.readers) == 128
    finally:
        state.readers = state.readers.copy()
        for reader in readers:
            reader.file.close()
            with files.report_lock: web.thumbs.end_reader_locked(state, reader)
        for lease in leases: lease.release()
    assert web.FILES.count == 0


def test_target_index_retries_only_its_nested_lease_owners_and_unwinds(exact):
    version = request('get', exact.url + '/detections').json['thumbnail_version']
    for route in ('thumb', 'detframe'):
        assert request('get', exact.url + '/' + route + '/0?v=' + version).status_code == 200
    files = web.FILES.initialize(exact.job)
    state = files.thumbnail
    other = web.new_job('', {}, 'other')
    containing = web.new_job('', {}, 'containing')
    other['phase'] = containing['phase'] = 'review'
    other_state = web.FILES.initialize(other)
    target = web.FILES.initialize(containing)
    leases, tickets, disposals = [], [], []
    class Retry:
        def __init__(self, file, failures):
            self.file, self.failures, self.attempts = file, failures, 0
        def __getattr__(self, name): return getattr(self.file, name)
        def close(self):
            self.attempts += 1
            if self.attempts <= len(self.failures): raise self.failures[self.attempts - 1]
            self.file.close()
    class Bucket(set):
        def __del__(self):
            disposals.append((files.report_lock.locked(), web.VAULT_LOCK.locked()))
    try:
        for index, entry in enumerate(list(state.entries.values())):
            lease = web._own_files(exact.job)
            leases.append(lease)
            if index == 0:
                with web.VAULT_LOCK:
                    related = web.FILES.reserve(other)
                    related.related.append(web.FILES.reserve(containing))
                    lease.related.append(related)
            failures = [KeyboardInterrupt('interrupt retry'), OSError('retry failed')] if index == 0 else []
            opened = Retry(open(entry.path, 'rb'), failures)
            with files.report_lock:
                reader = web.thumbs.begin_reader_locked(state, state.current, entry, opened)
                web.thumbs.defer_resource_locked(state, reader, lease)
            tickets.append(reader)
        with files.report_lock:
            web.thumbs.invalidate_locked(state, 'deferred index control')
            state.deferred_by_owner = {key: Bucket(value) for key, value in state.deferred_by_owner.items()}
        first, unrelated = tickets
        with pytest.raises(KeyboardInterrupt): web._thumbnail_cleanup(exact.job, target=target)
        assert not first._close_claimed and first in state.deferred
        assert first in state.deferred_by_owner[target] and first in state.deferred_by_owner[other_state]
        assert unrelated.file.attempts == 0
        web._thumbnail_lifecycle_cleanup(exact.job, target=target)
        assert first in state.deferred and first.file.attempts == 2 and unrelated.file.attempts == 0
        web._thumbnail_lifecycle_cleanup(exact.job, target=target)
        assert first.file.closed and first not in state.deferred
        assert target not in state.deferred_by_owner and other_state not in state.deferred_by_owner
        assert unrelated.file.attempts == 0 and unrelated in state.deferred
        web._thumbnail_lifecycle_cleanup(exact.job)
        assert unrelated.file.closed and not state.deferred and not state.deferred_by_owner
        assert web.FILES.count == 0
        assert disposals and all(not report and not vault for report, vault in disposals)
    finally:
        for ticket in tickets:
            if not ticket.file.closed: ticket.file.file.close()
        for _ in range(4):
            if not state.deferred: break
            try: web._thumbnail_cleanup(exact.job)
            except KeyboardInterrupt: pass
        for lease in leases: lease.release()


def test_interrupted_deferred_lease_release_restores_retry_index(exact, monkeypatch):
    version = request('get', exact.url + '/detections').json['thumbnail_version']
    assert request('get', exact.url + '/thumb/0?v=' + version).status_code == 200
    files = web.FILES.initialize(exact.job)
    state = files.thumbnail
    entry = state.entries[('crop', 0)]
    lease = web._own_files(exact.job)
    real_release, calls = lease.release, []
    def release():
        calls.append(True)
        if len(calls) == 1: raise KeyboardInterrupt('interrupted lease release')
        real_release()
    monkeypatch.setattr(lease, 'release', release)
    opened = open(entry.path, 'rb')
    with files.report_lock:
        reader = web.thumbs.begin_reader_locked(state, state.current, entry, opened)
        web.thumbs.defer_resource_locked(state, reader, lease)
        web.thumbs.invalidate_locked(state, 'interrupted release control')
    try:
        with pytest.raises(KeyboardInterrupt): web._thumbnail_cleanup(exact.job)
        assert opened.closed and reader in state.deferred and not lease.released
        web._thumbnail_lifecycle_cleanup(exact.job)
        assert lease.released and not state.deferred and not state.deferred_by_owner
        assert len(calls) == 2 and web.FILES.count == 0
    finally:
        if not opened.closed: opened.close()
        if not lease.released: real_release()
        with files.report_lock:
            if reader in state.deferred:
                discarded = web.thumbs.remove_deferred_locked(state, reader)
            else:
                discarded = None
            if reader in state.readers and opened.closed:
                web.thumbs.end_reader_locked(state, reader)
        discarded = None


def test_deferred_claim_does_not_iterate_ticket_set(exact):
    version = request('get', exact.url + '/detections').json['thumbnail_version']
    assert request('get', exact.url + '/thumb/0?v=' + version).status_code == 200
    files = web.FILES.initialize(exact.job)
    state = files.thumbnail
    entry = state.entries[('crop', 0)]
    lease = web._own_files(exact.job)
    opened = open(entry.path, 'rb')
    class NoIteration(set):
        def __iter__(self): raise AssertionError('deferred set iterated under report lock')
    with files.report_lock:
        reader = web.thumbs.begin_reader_locked(state, state.current, entry, opened)
        web.thumbs.defer_resource_locked(state, reader, lease)
        web.thumbs.invalidate_locked(state, 'bounded deferred claim')
        state.deferred = NoIteration(state.deferred)
    try:
        web._thumbnail_lifecycle_cleanup(exact.job)
        assert opened.closed and lease.released and not state.deferred
        assert not state.deferred_by_owner and web.FILES.count == 0
    finally:
        if not opened.closed: opened.close()
        state.deferred = state.deferred.copy()
        if state.deferred: web._thumbnail_cleanup(exact.job)
        if not lease.released: lease.release()


def test_missing_other_report_does_not_authorize_rehydrate_deletion(exact):
    original = exact.path.parent / 'thumb2_170.jpg'
    original.write_bytes(b'other job former original')
    other = web.new_job('', {}, 'retained job')
    other['phase'] = 'review'
    other['video'] = str(exact.path.parent / 'independent-input.avi')
    with open(exact.job['video'], 'rb') as src, open(other['video'], 'wb') as dst:
        dst.write(src.read())
    # The other job had a report but it is now missing; its original is unknowable.
    with web.JOBS_LOCK: web.JOBS.pop(exact.job['id'])
    web.rehydrate_jobs()
    response = request('get', exact.url + '/detections')
    assert original.read_bytes() == b'other job former original'
    assert response.status_code == 200


@pytest.mark.parametrize('kind', ['detections', 'thumb/0', 'detframe/0'])
def test_unrelated_old_file_collection_never_blocks_thumbnail_admission(exact, monkeypatch, kind):
    files = web.FILES.initialize(exact.job)
    files.thumbnail_sweep_pending = True
    entered, resume, done = threading.Event(), threading.Event(), threading.Event()
    real = getattr(web, '_sweep_thumbnail_derivatives', None)
    def held(*args, **kwargs):
        entered.set()
        assert resume.wait(8)
        return real(*args, **kwargs) if real is not None else True
    monkeypatch.setattr(web, '_sweep_thumbnail_derivatives', held, raising=False)
    responses, errors = [], []
    def first():
        try: responses.append(request('get', exact.url + '/detections'))
        except BaseException as exc: errors.append(exc)
        finally: done.set()
    worker = threading.Thread(target=first)
    worker.start()
    try:
        if entered.wait(.5):
            second = request('get', exact.url + '/' + kind)
            assert second.status_code == 200 and second.is_json == (kind == 'detections')
        else:
            assert done.wait(5)
    finally:
        resume.set()
        join(worker)
    assert not errors and responses[0].status_code == 200


def test_partial_related_lease_release_can_resume_without_double_count(exact, monkeypatch):
    other = web.new_job('', {}, 'related')
    lease = web._own_files(exact.job)
    with web.VAULT_LOCK:
        child = web.FILES.reserve(other)
        lease.related.append(child)
    real_child, calls = child.release_locked, []
    def interrupted():
        real_child()
        calls.append(True)
        if len(calls) == 1: raise KeyboardInterrupt('after child released')
    monkeypatch.setattr(child, 'release_locked', interrupted)
    try:
        with pytest.raises(KeyboardInterrupt): lease.release()
        assert not lease.released
        lease.release()
        assert lease.released and child.released
        assert web.FILES.count == 0
        assert web.FILES.initialize(exact.job).count == 0
        assert web.FILES.initialize(other).count == 0
    finally:
        if web.FILES.count:
            lease.released = False
            lease.release()


def test_primary_failure_keeps_foreground_release_continuation(exact, monkeypatch):
    version = request('get', exact.url + '/detections').json['thumbnail_version']
    assert request('get', exact.url + '/thumb/0?v=' + version).status_code == 200
    primary = openscrub.PipelineCancelled()
    real_prepare, captured = web._prepare_observed_source, []
    def prepare(*args):
        prepared, lease = real_prepare(*args)
        real_release, calls = lease.release, []
        def interrupted():
            calls.append(True)
            if len(calls) == 1: raise KeyboardInterrupt('release guard interrupted')
            real_release()
        lease.release = interrupted
        captured.append((lease, real_release, calls))
        return prepared, lease
    original_open = web._thumbnail_open
    class BadRead:
        def __init__(self, file): self.file = file
        def __getattr__(self, name): return getattr(self.file, name)
        def read(self): raise primary
    def fail_read(path, reader): return BadRead(original_open(path, reader))
    monkeypatch.setattr(web, '_prepare_observed_source', prepare)
    monkeypatch.setattr(web, '_thumbnail_open', fail_read)
    try:
        with pytest.raises(openscrub.PipelineCancelled) as caught:
            web._thumbnail_image(exact.job, 0, 'crop', version)
        assert caught.value is primary and web.FILES.count > 0
        web._thumbnail_lifecycle_cleanup(exact.job)
        assert captured[0][0].released and web.FILES.count == 0
    finally:
        for lease, real_release, _ in captured:
            if not lease.released: real_release()


@pytest.mark.parametrize('factory', [web._ThumbnailHandle, web.thumbs._StageHandle])
def test_consumed_raw_close_interruption_never_recloses_reused_fd(tmp_path, monkeypatch, factory):
    source, other = tmp_path / 'source', tmp_path / 'other'
    source.write_bytes(b'original')
    other.write_bytes(b'protected')
    handle = factory()
    handle.fd = os.open(source, os.O_RDONLY)
    target, real_close, calls, replacement = handle.fd, os.close, [], []
    def close_then_interrupt(fd):
        if fd == target:
            calls.append(fd)
            real_close(fd)
            replacement.append(os.open(other, os.O_RDONLY))
            assert replacement[-1] == target
            raise KeyboardInterrupt('after raw close')
        return real_close(fd)
    monkeypatch.setattr(os, 'close', close_then_interrupt)
    try:
        with pytest.raises(KeyboardInterrupt): handle.close()
        with pytest.raises(BaseException): handle.close()
        assert calls == [target]
        assert os.read(replacement[0], 9) == b'protected'
    finally:
        for fd in replacement:
            try: real_close(fd)
            except OSError: pass


@pytest.mark.parametrize('factory', [web._ThumbnailHandle, web.thumbs._StageHandle])
def test_raw_close_interrupt_before_fd_clearing_keeps_reused_fd(tmp_path, monkeypatch, factory):
    import inspect
    import sys
    source, other = tmp_path / 'source', tmp_path / 'other'
    source.write_bytes(b'original')
    other.write_bytes(b'protected')
    handle = factory()
    handle.fd = os.open(source, os.O_RDONLY)
    target, real_close, calls, replacement = handle.fd, os.close, [], []
    lines, first = inspect.getsourcelines(factory.close)
    clear_line = first + next(i for i, line in enumerate(lines) if 'self.fd = None' in line)
    def tracked_close(fd):
        if fd == target:
            calls.append(fd)
            real_close(fd)
            replacement.append(os.open(other, os.O_RDONLY))
            assert replacement[-1] == target
            return
        return real_close(fd)
    def trace(frame, event, arg):
        if frame.f_code is factory.close.__code__ and event == 'line' and frame.f_lineno == clear_line:
            raise KeyboardInterrupt('before descriptor clearing')
        return trace
    monkeypatch.setattr(os, 'close', tracked_close)
    try:
        sys.settrace(trace)
        with pytest.raises(KeyboardInterrupt): handle.close()
        sys.settrace(None)
        with pytest.raises(OSError): handle.close()
        assert calls == [target] and os.read(replacement[0], 9) == b'protected'
    finally:
        sys.settrace(None)
        for fd in replacement:
            try: real_close(fd)
            except OSError: pass


@pytest.mark.parametrize('step', ['global', 'job', 'work'])
@pytest.mark.parametrize('when', ['before', 'after'])
def test_release_counter_interruption_reconciles_once(step, when):
    from openscrub_internal.lifetimes import FileOwners, _JobFiles
    class InterruptOwner(FileOwners):
        def __setattr__(self, name, value):
            if name == 'count' and getattr(self, 'armed', False):
                object.__setattr__(self, 'armed', False)
                if when == 'before': raise KeyboardInterrupt('before global count')
                object.__setattr__(self, name, value)
                raise KeyboardInterrupt('after global count')
            object.__setattr__(self, name, value)
    class InterruptJob(_JobFiles):
        def __setattr__(self, name, value):
            if name == ('count' if step == 'job' else step) and getattr(self, 'armed', False):
                object.__setattr__(self, 'armed', False)
                if when == 'before': raise KeyboardInterrupt('before job count')
                object.__setattr__(self, name, value)
                raise KeyboardInterrupt('after job count')
            object.__setattr__(self, name, value)
    owners = InterruptOwner(threading.Lock())
    job = {'_files': InterruptJob()}
    lease = owners.reserve(job, work=True)
    obj = owners if step == 'global' else job['_files']
    obj.armed = True
    with pytest.raises(KeyboardInterrupt): lease.release()
    lease.release()
    assert lease.released and owners.count == 0
    assert job['_files'].count == 0 and job['_files'].work == 0


def test_unowned_final_thumbnail_name_is_never_clobbered(exact):
    version = request('get', exact.url + '/detections').json['thumbnail_version']
    old = exact.path.parent / ('thumb3_%s_crop_0.jpg' % version)
    old.write_bytes(b'unowned authoritative bytes')
    response = request('get', exact.url + '/thumb/0?v=' + version)
    assert response.status_code == 200
    assert old.read_bytes() == b'unowned authoritative bytes'


def test_interrupt_between_decrement_and_progress_marker_reconciles_once():
    import inspect
    import sys
    from openscrub_internal.lifetimes import FileOwners, _Lease
    owners = FileOwners(threading.Lock())
    job = {}
    lease = owners.reserve(job, work=True)
    lines, first = inspect.getsourcelines(_Lease._decrement_locked)
    marker_line = first + next(i for i, line in enumerate(lines) if 'setattr(self, marker, True)' in line)
    def trace(frame, event, arg):
        if frame.f_code is _Lease._decrement_locked.__code__ and event == 'line' and frame.f_lineno == marker_line:
            sys.settrace(None)
            raise KeyboardInterrupt('before progress marker')
        return trace
    try:
        sys.settrace(trace)
        with pytest.raises(KeyboardInterrupt): lease.release()
        sys.settrace(None)
        lease.release()
        assert lease.released and owners.count == 0
        assert job['_files'].count == 0 and job['_files'].work == 0
    finally:
        sys.settrace(None)


@pytest.mark.parametrize('alias', [False, True])
def test_current_thumbnail_promoted_to_another_job_source_is_preserved(exact, alias):
    version = request('get', exact.url + '/detections').json['thumbnail_version']
    assert request('get', exact.url + '/thumb/0?v=' + version).status_code == 200
    files = web.FILES.initialize(exact.job)
    entry = files.thumbnail.entries['crop', 0]
    source = entry.path
    if alias:
        source = str(exact.root / 'alias-source.avi')
        os.link(entry.path, source)
    other = web.new_job(source, {}, 'promoted source')
    other['phase'] = 'review'
    with files.report_lock:
        web.thumbs.invalidate_locked(files.thumbnail, 'retire after promotion')
    web._thumbnail_cleanup(exact.job)
    assert os.path.exists(entry.path)
    assert files.thumbnail.retirement is None


def test_unprotected_current_artifact_is_really_unlinked(exact):
    version = request('get', exact.url + '/detections').json['thumbnail_version']
    assert request('get', exact.url + '/thumb/0?v=' + version).status_code == 200
    files = web.FILES.initialize(exact.job)
    entry = files.thumbnail.entries['crop', 0]
    with files.report_lock: web.thumbs.invalidate_locked(files.thumbnail, 'ordinary retirement')
    web._thumbnail_cleanup(exact.job)
    assert not os.path.exists(entry.path)
    assert files.thumbnail.retirement is None
    assert entry.path not in web.FILES.thumbnail_paths


@pytest.mark.parametrize('endpoint', ['detections', 'thumb/0', 'detframe/0'])
def test_claimed_artifact_refuses_matching_thumbnail_admission_with_json(exact, monkeypatch, endpoint):
    version = request('get', exact.url + '/detections').json['thumbnail_version']
    assert request('get', exact.url + '/thumb/0?v=' + version).status_code == 200
    files = web.FILES.initialize(exact.job)
    entry = files.thumbnail.entries['crop', 0]
    other = web.new_job('', {}, 'claim contender')
    other['video'] = entry.path
    other['phase'] = 'review'
    entered, resume = threading.Event(), threading.Event()
    real_unlink = os.unlink
    def held_unlink(path, *args, **kwargs):
        if str(path) == entry.path:
            entered.set()
            assert resume.wait(8)
        return real_unlink(path, *args, **kwargs)
    monkeypatch.setattr(os, 'unlink', held_unlink)
    with files.report_lock: web.thumbs.invalidate_locked(files.thumbnail, 'claim test')
    worker = threading.Thread(target=web._thumbnail_cleanup, args=(exact.job,))
    worker.start()
    try:
        assert entered.wait(5)
        response = request('get', '/api/jobs/' + other['id'] + '/' + endpoint)
        assert response.status_code == 409
        assert response.is_json and response.json['error'] == 'thumbnail_pending'
        assert response.headers['Cache-Control'] == 'private, no-store'
    finally:
        resume.set()
        join(worker)
    assert not os.path.exists(entry.path) and not web.FILES.thumbnail_resolving


def test_unresolved_alias_admission_relinquishes_candidate_without_blocking_metadata(exact, monkeypatch):
    version = request('get', exact.url + '/detections').json['thumbnail_version']
    assert request('get', exact.url + '/thumb/0?v=' + version).status_code == 200
    files = web.FILES.initialize(exact.job)
    entry = files.thumbnail.entries['crop', 0]
    alias = str(exact.root / 'pending-alias.avi')
    os.link(entry.path, alias)
    entered, resume, errors = threading.Event(), threading.Event(), []
    real_stat = os.stat
    def held_stat(path, *args, **kwargs):
        if str(path) == alias and threading.current_thread() is worker:
            entered.set()
            assert resume.wait(8)
        return real_stat(path, *args, **kwargs)
    monkeypatch.setattr(os, 'stat', held_stat)
    def admit():
        try: web.new_job(alias, {}, 'pending alias')
        except BaseException as error: errors.append(error)
    worker = threading.Thread(target=admit)
    worker.start()
    try:
        assert entered.wait(5)
        with files.report_lock: web.thumbs.invalidate_locked(files.thumbnail, 'pending alias')
        web._thumbnail_cleanup(exact.job)
        assert os.path.exists(entry.path) and files.thumbnail.retirement is None
        assert request('get', exact.url + '/detections').status_code == 200
    finally:
        resume.set()
        join(worker)
    assert not errors and not web.FILES.thumbnail_resolving


@pytest.mark.parametrize('error', [OSError('identity unavailable'), KeyboardInterrupt('identity interrupted')])
def test_identity_resolution_failure_drains_its_owned_marker(exact, monkeypatch, error):
    target = str(exact.root / 'identity-error.avi')
    real_stat = os.stat
    def failed_stat(path, *args, **kwargs):
        if str(path) == target: raise error
        return real_stat(path, *args, **kwargs)
    monkeypatch.setattr(os, 'stat', failed_stat)
    with pytest.raises(type(error)) as caught:
        web.new_job(target, {}, 'failed source admission')
    assert caught.value is error
    assert not web.FILES.thumbnail_resolving and web.FILES.count == 0


def test_mkstemp_collision_preserves_existing_unowned_file(exact, monkeypatch):
    version = request('get', exact.url + '/detections').json['thumbnail_version']
    old = exact.path.parent / '.thumb3-stage-collision'
    old.write_bytes(b'unowned file')
    def collision(*args, **kwargs): raise FileExistsError(str(old))
    monkeypatch.setattr(web.thumbs.tempfile, 'mkstemp', collision)
    response = request('get', exact.url + '/thumb/0?v=' + version)
    assert response.status_code == 500 and response.json['error'] == 'thumbnail_io_failed'
    assert old.read_bytes() == b'unowned file'


def test_render_original_input_alias_protects_owned_artifact(exact, monkeypatch):
    version = request('get', exact.url + '/detections').json['thumbnail_version']
    assert request('get', exact.url + '/thumb/0?v=' + version).status_code == 200
    files = web.FILES.initialize(exact.job)
    entry = files.thumbnail.entries['crop', 0]
    alias = str(exact.root / 'original-input.avi')
    os.link(entry.path, alias)
    other = web.new_job(exact.job['video'], {}, 'render original')
    other['phase'] = 'review'
    monkeypatch.setattr(web, '_load_job_report', lambda job: {'provenance': {'original_input': alias}})
    owner = web._own_files(other, work=True)
    try:
        web._select_render_input(other, owner)
        assert owner.source == alias
        with files.report_lock: web.thumbs.invalidate_locked(files.thumbnail, 'original input')
        web._thumbnail_cleanup(exact.job)
        assert os.path.exists(entry.path) and files.thumbnail.retirement is None
    finally:
        owner.release()


def test_stage_receipt_interruption_preserves_private_inode(exact, monkeypatch):
    version = request('get', exact.url + '/detections').json['thumbnail_version']
    original = web.FILES.thumbnail_inodes
    error = RuntimeError('receipt insertion interrupted')
    class InterruptedIndex(dict):
        def __setitem__(self, key, value):
            super().__setitem__(key, value)
            raise error
    index = InterruptedIndex(original)
    monkeypatch.setattr(web.FILES, 'thumbnail_inodes', index)
    with pytest.raises(RuntimeError) as caught:
        web._thumbnail_image(exact.job, 0, 'crop', version)
    assert caught.value is error
    files = web.FILES.initialize(exact.job)
    paths = list(exact.path.parent.glob('.thumb3-stage-*'))
    assert len(paths) == 1 and paths[0].exists()
    web._thumbnail_cleanup(exact.job)
    assert paths[0].exists() and files.thumbnail.retirement is None
    assert str(paths[0]) not in web.FILES.thumbnail_paths


def test_overlapping_admission_protects_unregistered_new_stage(exact, monkeypatch):
    version = request('get', exact.url + '/detections').json['thumbnail_version']
    entered, resume, responses, errors = threading.Event(), threading.Event(), [], []
    real_mkstemp = web.thumbs.tempfile.mkstemp
    def held_mkstemp(*args, **kwargs):
        result = real_mkstemp(*args, **kwargs)
        entered.set()
        assert resume.wait(8)
        return result
    monkeypatch.setattr(web.thumbs.tempfile, 'mkstemp', held_mkstemp)
    def generate():
        try: responses.append(request('get', exact.url + '/thumb/0?v=' + version))
        except BaseException as error: errors.append(error)
    worker = threading.Thread(target=generate)
    worker.start()
    try:
        assert entered.wait(5)
        other = web.new_job(exact.job['video'], {}, 'overlap')
        other['phase'] = 'review'
        assert request('get', exact.url + '/detections').status_code == 200
    finally:
        resume.set()
        join(worker)
    assert not errors and responses[0].status_code == 200
    files = web.FILES.initialize(exact.job)
    entry = files.thumbnail.entries['crop', 0]
    with files.report_lock: web.thumbs.invalidate_locked(files.thumbnail, 'overlap')
    web._thumbnail_cleanup(exact.job)
    assert os.path.exists(entry.path) and files.thumbnail.retirement is None
    assert entry.path not in web.FILES.thumbnail_paths


def test_replaced_owned_leaf_is_relinquished_without_unlink(exact):
    version = request('get', exact.url + '/detections').json['thumbnail_version']
    assert request('get', exact.url + '/thumb/0?v=' + version).status_code == 200
    files = web.FILES.initialize(exact.job)
    entry = files.thumbnail.entries['crop', 0]
    protected = exact.root / 'protected-file'
    protected.write_bytes(b'keep me')
    os.unlink(entry.path)
    os.symlink(protected, entry.path)
    with files.report_lock: web.thumbs.invalidate_locked(files.thumbnail, 'replaced file')
    web._thumbnail_cleanup(exact.job)
    assert os.path.islink(entry.path) and protected.read_bytes() == b'keep me'
    assert files.thumbnail.retirement is None and entry.path not in web.FILES.thumbnail_paths


def test_successful_render_output_alias_protects_owned_artifact(exact, monkeypatch):
    version = request('get', exact.url + '/detections').json['thumbnail_version']
    assert request('get', exact.url + '/thumb/0?v=' + version).status_code == 200
    files = web.FILES.initialize(exact.job)
    entry = files.thumbnail.entries['crop', 0]
    alias = str(exact.root / 'rendered-output.avi')
    os.link(entry.path, alias)
    other = web.new_job(exact.job['video'], {}, 'render output')
    other['phase'] = 'review'
    monkeypatch.setattr(openscrub, 'run_pipeline', lambda args, cb: {'output': alias})
    web._run_job(other, 'render')
    assert other['phase'] == 'done' and other['output'] == alias
    with files.report_lock: web.thumbs.invalidate_locked(files.thumbnail, 'render output')
    web._thumbnail_cleanup(exact.job)
    assert os.path.exists(entry.path) and files.thumbnail.retirement is None


def test_deletion_drains_owned_receipts_in_bounded_batches_outside_guard(exact):
    files = web.FILES.initialize(exact.job)
    released = []
    class TrackedReceipt(dict):
        def __del__(self): released.append(web.VAULT_LOCK.locked())
    with web.VAULT_LOCK:
        for number in range(65):
            path = str(exact.path.parent / ('synthetic-owned-%d' % number))
            identity = (-9912, number)
            record = TrackedReceipt(path=path, identity=identity, job=exact.job,
                                    protected=False, claimed=False)
            files.thumbnail_artifacts.add(path)
            web.FILES.thumbnail_paths[path] = record
            web.FILES.thumbnail_inodes[identity] = record
        del record
    response = request('delete', exact.url)
    assert response.status_code == 200 and response.json['ok']
    assert not files.thumbnail_artifacts
    assert len(released) == 65 and not any(released)
