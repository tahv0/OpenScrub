"""Fresh report validation reuse through the thumbnail routes."""
import dataclasses
import json
import math
import os
import threading

import cv2
import numpy as np
import pytest
import openscrub_web as web

from test_exact_samples import exact
from test_job_lifecycle import finish, request, start_call, store


@pytest.mark.skipif(os.name != 'posix', reason='requires POSIX proof reuse')
def test_fresh_metadata_and_cold_crop_reuse_validation(exact, monkeypatch):
    real_load, real_validate = web.json.load, web._thumbnail_validate_report
    counts = {'parse': 0, 'validate': 0}

    def load(stream, *args, **kwargs):
        if getattr(stream, 'name', None) == str(exact.path):
            counts['parse'] += 1
        return real_load(stream, *args, **kwargs)

    def validate(doc):
        counts['validate'] += 1
        return real_validate(doc)

    monkeypatch.setattr(web.json, 'load', load)
    monkeypatch.setattr(web, '_thumbnail_validate_report', validate)
    first = request('get', exact.url + '/detections')
    assert first.status_code == 200
    second = request('get', exact.url + '/detections')
    assert second.status_code == 200 and second.json == first.json
    version = first.json['thumbnail_version']
    cold = request('get', exact.url + '/thumb/0?v=' + version)
    warm = request('get', exact.url + '/thumb/0?v=' + version)
    assert cold.status_code == warm.status_code == 200
    assert cold.data == warm.data and cold.headers['ETag'] == warm.headers['ETag']
    assert cv2.imdecode(np.frombuffer(cold.data, np.uint8), 1).size > 0
    # One parse per report identity: metadata, cold and warm crops share it.
    assert counts == {'parse': 1, 'validate': 1}


def test_plain_tuple_snapshot_requires_full_validation(exact, monkeypatch):
    assert request('get', exact.url + '/detections').status_code == 200
    snapshot = web._thumbnail_snapshot(exact.job)
    original = web._thumbnail_validate_report
    calls = []
    def validate(doc):
        calls.append(doc)
        return original(doc)
    monkeypatch.setattr(web, '_thumbnail_validate_report', validate)
    try:
        rows, rs, generation = web._thumbnail_validate_snapshot(exact.job, tuple(snapshot))
        assert generation is None and rows is snapshot[0]['detections'] and rs is snapshot[0]['render_state']
        assert calls == [snapshot[0]]
    finally:
        snapshot[3].release()


@pytest.mark.parametrize('bad', ['row', 'cum', 'json'])
def test_first_or_changed_report_validates_all_rows_and_cum(exact, bad):
    assert request('get', exact.url + '/detections').status_code == 200
    doc = json.loads(exact.path.read_text())
    if bad == 'row':
        doc['detections'][1]['confidence'] = float('nan')
    elif bad == 'cum':
        doc['render_state']['cum'][-1][1] = float('inf')
    if bad == 'json':
        exact.path.write_text('{')
    else:
        exact.path.write_text(json.dumps(doc))
    response = request('get', exact.url + '/detections')
    assert response.status_code == 500 and response.json['error'] == 'thumbnail_invalid_report'


@pytest.mark.parametrize('replace', [True, False])
def test_same_size_inode_and_inplace_ctime_refuse_held_proof(exact, replace):
    assert request('get', exact.url + '/detections').status_code == 200
    snapshot = web._thumbnail_snapshot(exact.job)
    before = exact.path.stat()
    try:
        content = exact.path.read_bytes()
        changed = content.replace(b'disabled', b'DISABLED', 1)
        assert changed != content and len(changed) == len(content)
        if replace:
            other = exact.path.with_suffix('.replacement')
            other.write_bytes(changed)
            os.utime(other, ns=(before.st_atime_ns, before.st_mtime_ns))
            os.replace(other, exact.path)
        else:
            exact.path.write_bytes(changed)
            os.utime(exact.path, ns=(before.st_atime_ns, before.st_mtime_ns))
        after = exact.path.stat()
        assert after.st_size == before.st_size and after.st_mtime_ns == before.st_mtime_ns
        if replace or after.st_ctime_ns != before.st_ctime_ns:
            if replace:
                assert after.st_ino != before.st_ino
            with pytest.raises(web._ThumbnailError) as error:
                web._thumbnail_validate_snapshot(exact.job, snapshot)
            assert error.value.code == 'thumbnail_obsolete'
        else:
            # Windows may expose creation time as ctime, leaving the stamp equal.
            assert os.name != 'posix'
            fresh = web._thumbnail_snapshot(exact.job)
            try:
                rows, _, reused = web._thumbnail_validate_snapshot(exact.job, fresh)
                assert reused is None and rows[1]['text'] == 'DISABLED'
            finally:
                fresh[3].release()
    finally:
        snapshot[3].release()


@pytest.mark.skipif(os.name != 'posix', reason='requires POSIX proof reuse')
def test_reused_generation_cannot_create_replacement(exact, monkeypatch):
    assert request('get', exact.url + '/detections').status_code == 200
    snapshot = web._thumbnail_snapshot(exact.job)
    try:
        _, _, generation = web._thumbnail_validate_snapshot(exact.job, snapshot)
        assert generation is not None
        files = web.FILES.initialize(exact.job)
        with files.report_lock:
            web.thumbs.invalidate_locked(files.thumbnail, 'test invalidation')
        def forbidden(*args, **kwargs):
            raise AssertionError('reuse cannot create a replacement')
        monkeypatch.setattr(web.thumbs, 'accept_discovery_locked', forbidden)
        with pytest.raises(web._ThumbnailError) as error:
            web._thumbnail_select(exact.job, *snapshot[:3], snapshot[3], reuse_generation=generation)
        assert error.value.code == 'thumbnail_obsolete' and files.thumbnail.current is None
    finally:
        snapshot[3].release()


@pytest.mark.parametrize('field,value', [('crop_recipe', 'other'), ('row_count', 999), ('source_epoch', -1), ('incarnation', object())])
def test_proof_mismatch_requires_validation(exact, monkeypatch, field, value):
    assert request('get', exact.url + '/detections').status_code == 200
    files = web.FILES.initialize(exact.job)
    with files.report_lock:
        files.thumbnail.current = dataclasses.replace(files.thumbnail.current, **{field: value})
    snapshot = web._thumbnail_snapshot(exact.job)
    original = web._thumbnail_validate_report
    calls = []
    def validate(doc):
        calls.append(doc)
        return original(doc)
    monkeypatch.setattr(web, '_thumbnail_validate_report', validate)
    try:
        _, _, reused = web._thumbnail_validate_snapshot(exact.job, snapshot)
        assert reused is None and calls == [snapshot[0]]
    finally:
        snapshot[3].release()


def test_mismatched_generation_is_not_reselected_after_validation(exact):
    first = request('get', exact.url + '/detections')
    assert first.status_code == 200
    files = web.FILES.initialize(exact.job)
    with files.report_lock:
        files.thumbnail.current = dataclasses.replace(files.thumbnail.current, row_count=999)
    second = request('get', exact.url + '/detections')
    assert second.status_code == 200
    assert second.json['thumbnail_version'] != first.json['thumbnail_version']
    assert files.thumbnail.current.row_count == len(second.json['detections'])


@pytest.mark.parametrize('point', ['entry', 'after_proof'])
def test_helper_entry_and_after_proof_failures_drain_lease(exact, monkeypatch, point):
    first = request('get', exact.url + '/detections')
    version = first.json['thumbnail_version']
    original = web._thumbnail_validate_snapshot
    def interrupted(*args, **kwargs):
        if point == 'after_proof':
            original(*args, **kwargs)
        raise RuntimeError('injected helper interruption')
    monkeypatch.setattr(web, '_thumbnail_validate_snapshot', interrupted)
    with pytest.raises(RuntimeError, match='injected helper interruption'):
        web._thumbnail_image(exact.job, 0, 'crop', version)
    monkeypatch.setattr(web, '_thumbnail_validate_snapshot', original)
    files = web.FILES.initialize(exact.job)
    web._thumbnail_cleanup(exact.job)
    assert not files.thumbnail.fills and not files.thumbnail.deferred and web.FILES.count == 0
    assert request('delete', exact.url).status_code == 200


@pytest.mark.parametrize('transition', ['delete', 'vault', 'report', 'pending'])
@pytest.mark.skipif(os.name != 'posix', reason='requires POSIX proof reuse')
def test_source_operation_pending_delete_and_vault_fence_reuse(exact, monkeypatch, transition):
    if transition == 'vault':
        exact.enable()
    assert request('get', exact.url + '/detections').status_code == 200
    entered, release = threading.Event(), threading.Event()
    original = web._thumbnail_validate_snapshot
    def held(*args, **kwargs):
        result = original(*args, **kwargs)
        assert result[2] is not None
        entered.set()
        assert release.wait(8)
        return result
    monkeypatch.setattr(web, '_thumbnail_validate_snapshot', held)
    call = start_call('get', exact.url + '/detections')
    try:
        assert entered.wait(5)
        if transition == 'delete':
            assert request('delete', exact.url).status_code == 409
        elif transition == 'vault':
            assert request('post', '/api/vault/lock').status_code == 409
        elif transition == 'report':
            doc = json.loads(exact.path.read_text())
            doc['detections'][1]['confidence'] = float('nan')
            exact.path.write_text(json.dumps(doc))
        else:
            files = web.FILES.initialize(exact.job)
            with files.report_lock:
                files.source_status = 'pending'
    finally:
        release.set()
        result = finish(call)
    if transition in ('report', 'pending'):
        assert result.status_code == 409
    else:
        assert result.status_code == 200
    if transition == 'pending':
        with files.report_lock:
            files.source_status = 'coherent'
    assert web.FILES.count == 0
    assert request('delete', exact.url).status_code == 200


def test_warm_hit_does_not_parse_or_validate(exact, monkeypatch):
    first = request('get', exact.url + '/detections')
    url = exact.url + '/thumb/0?v=' + first.json['thumbnail_version']
    cold = request('get', url)
    assert cold.status_code == 200
    def forbidden(*args, **kwargs):
        raise AssertionError('warm hit must not parse or validate')
    monkeypatch.setattr(web, '_thumbnail_snapshot', forbidden)
    monkeypatch.setattr(web, '_thumbnail_validate_report', forbidden)
    warm = request('get', url)
    assert warm.status_code == 200 and warm.data == cold.data
    assert warm.headers['ETag'] == cold.headers['ETag']


@pytest.mark.skipif(os.name != 'posix', reason='requires POSIX proof reuse')
def test_reuse_selection_rechecks_source_epoch(exact):
    assert request('get', exact.url + '/detections').status_code == 200
    snapshot = web._thumbnail_snapshot(exact.job)
    files = web.FILES.initialize(exact.job)
    try:
        _, _, generation = web._thumbnail_validate_snapshot(exact.job, snapshot)
        with files.report_lock:
            old_epoch = files.source_epoch
            files.source_epoch += 1
        try:
            with pytest.raises(web._ThumbnailError) as error:
                web._thumbnail_select(exact.job, *snapshot[:3], snapshot[3], reuse_generation=generation)
            assert error.value.code == 'thumbnail_obsolete'
        finally:
            with files.report_lock:
                files.source_epoch = old_epoch
    finally:
        snapshot[3].release()


class _PlatformOS:
    """Override only the web module's platform selector, not global os.name."""
    def __init__(self, name):
        self.name = name

    def __getattr__(self, name):
        return getattr(os, name)


def _weak_stamp_fixture(exact, monkeypatch, platform):
    doc = json.loads(exact.path.read_text())
    doc['render_state']['cum'][-1][1] = 1000.0
    doc['detections'][1]['confidence'] = 1000.0
    content = json.dumps(doc).encode()
    exact.path.write_bytes(content)
    monkeypatch.setattr(web, 'os', _PlatformOS(platform))
    first = request('get', exact.url + '/detections')
    assert first.status_code == 200
    before = exact.path.stat()
    real_stamp = web._file_stamp
    original_stamp = real_stamp(before)
    def creation_time_stamp(info):
        stamp = real_stamp(info)
        if stamp[:2] == original_stamp[:2]:
            return stamp[:4] + (original_stamp[4],)
        return stamp
    monkeypatch.setattr(web, '_file_stamp', creation_time_stamp)
    return first.json['thumbnail_version'], before, content


def _same_stamp_write(exact, before, content):
    exact.path.write_bytes(content)
    os.utime(exact.path, ns=(before.st_atime_ns, before.st_mtime_ns))
    after = exact.path.stat()
    assert (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) == (
        before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    assert web._file_stamp(after) == web._file_stamp(before)


@pytest.mark.parametrize('platform', ['nt', 'unsupported'])
@pytest.mark.parametrize('bad', ['row', 'cum'])
@pytest.mark.parametrize('route', ['metadata', 'cold'])
def test_weak_stamp_platform_refuses_invalid_fresh_report(exact, monkeypatch, platform, bad, route):
    version, before, content = _weak_stamp_fixture(exact, monkeypatch, platform)
    position = content.rfind(b'1000.0') if bad == 'row' else content.find(b'1000.0')
    assert position >= 0
    invalid = content[:position] + b'1e9999' + content[position + 6:]
    parsed = json.loads(invalid)
    value = (parsed['detections'][1]['confidence'] if bad == 'row'
             else parsed['render_state']['cum'][-1][1])
    assert math.isinf(value)
    _same_stamp_write(exact, before, invalid)
    endpoint = '/detections' if route == 'metadata' else '/thumb/0?v=' + version
    response = request('get', exact.url + endpoint)
    assert response.status_code == 500 and response.json['error'] == 'thumbnail_invalid_report'
    files = web.FILES.initialize(exact.job)
    assert not files.thumbnail.entries and not files.thumbnail.fills and not files.thumbnail.deferred
    assert web.FILES.count == 0
    assert request('delete', exact.url).status_code == 200


@pytest.mark.parametrize('platform', ['nt', 'unsupported'])
def test_weak_stamp_platform_valid_fresh_reads_still_validate(exact, monkeypatch, platform):
    version, before, content = _weak_stamp_fixture(exact, monkeypatch, platform)
    changed = content.replace(b'disabled', b'DISABLED', 1)
    assert changed != content and len(changed) == len(content)
    _same_stamp_write(exact, before, changed)
    real_load, real_validate = web.json.load, web._thumbnail_validate_report
    counts = {'parse': 0, 'validate': 0}
    def load(stream, *args, **kwargs):
        if getattr(stream, 'name', None) == str(exact.path):
            counts['parse'] += 1
        return real_load(stream, *args, **kwargs)
    def validate(doc):
        counts['validate'] += 1
        return real_validate(doc)
    monkeypatch.setattr(web.json, 'load', load)
    monkeypatch.setattr(web, '_thumbnail_validate_report', validate)
    metadata = request('get', exact.url + '/detections')
    crop = request('get', exact.url + '/thumb/0?v=' + version)
    assert metadata.status_code == crop.status_code == 200
    assert metadata.json['detections'][1]['text'] == 'DISABLED'
    assert counts == {'parse': 2, 'validate': 2}
    assert web.FILES.count == 0
