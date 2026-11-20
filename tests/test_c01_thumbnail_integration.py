"""Thumbnail responses share the clean build's containing-source fences."""
import json
from pathlib import Path

import pytest
import openscrub_web as web
from test_exact_samples import exact, raw, sample
from test_job_lifecycle import request, store


@pytest.fixture
def foreign_review(exact):
    source = web.new_job('', {}, 'thumbnail-source.avi')
    video = Path(source['dir']) / 'output.avi'
    video.write_bytes(Path(exact.job['video']).read_bytes())
    source.update(video=str(video), phase='review')
    exact.job['video'] = str(video)
    doc = raw(exact)
    doc['provenance']['input'] = str(video)
    exact.path.write_text(json.dumps(doc))
    return exact, source


def thumbnail_version(exact):
    metadata = request('get', exact.url + '/detections')
    assert metadata.status_code == 200, metadata.get_data(as_text=True)
    return metadata.json['thumbnail_version']


def publish_source_report(source):
    owner = web.FILES.initialize(source)
    with owner.report_lock:
        web._publish_job_report_locked(source, str(Path(source['dir']) / 'report.json'), {'updated': True})


def test_managed_source_publication_invalidates_old_thumbnail_validator(foreign_review):
    exact, source = foreign_review
    inspected = sample(exact)['sample']['source_ref']
    version = thumbnail_version(exact)
    url = exact.url + '/thumb/0?v=' + version
    image = request('get', url)
    assert image.status_code == 200
    headers = {'If-None-Match': image.headers['ETag']}
    assert request('get', url, headers=headers).status_code == 304

    publish_source_report(source)
    stale = request('get', url, headers=headers)
    assert stale.status_code == 409
    assert stale.json['error'] == 'thumbnail_obsolete'
    current = thumbnail_version(exact)
    assert current != version
    assert request('get', exact.url + '/thumb/0?v=' + current).status_code == 200
    assert sample(exact)['sample']['source_ref'] == inspected
    assert web.FILES.count == 0


@pytest.mark.parametrize('change', ['publication', 'recovery'])
def test_managed_source_change_during_encode_prevents_acceptance(foreign_review, monkeypatch, change):
    exact, source = foreign_review
    version = thumbnail_version(exact)
    original = web.thumbs.encode_jpeg
    owner = web.FILES.initialize(source)
    encoded = []

    def encode(*args, **kwargs):
        jpeg = original(*args, **kwargs)
        encoded.append(True)
        if change == 'publication':
            publish_source_report(source)
        else:
            with owner.report_lock:
                owner.recovery_required = True
        return jpeg

    monkeypatch.setattr(web.thumbs, 'encode_jpeg', encode)
    try:
        response = request('get', exact.url + '/thumb/0?v=' + version)
        assert encoded == [True]
        assert response.status_code == 409
        assert response.json['error'] == 'thumbnail_obsolete'
        assert not web.FILES.initialize(exact.job).thumbnail.entries
        assert web.FILES.count == 0
    finally:
        with owner.report_lock:
            owner.recovery_required = False


@pytest.mark.parametrize('kind', ['thumb', 'detframe'])
def test_warm_versioned_thumbnail_reports_obsolete_when_foreign_source_enters_recovery(foreign_review, kind):
    exact, source = foreign_review
    version = thumbnail_version(exact)
    url = exact.url + '/' + kind + '/0?v=' + version
    image = request('get', url)
    assert image.status_code == 200
    owner = web.FILES.initialize(source)
    try:
        with owner.report_lock:
            owner.recovery_required = True
        response = request('get', url, headers={'If-None-Match': image.headers['ETag']})
        assert response.status_code == 409
        assert response.is_json
        assert response.json['error'] == 'thumbnail_obsolete'
        assert response.json['refresh'] == 'detections'
        assert 'no-store' in response.headers['Cache-Control']
        legacy = request('get', exact.url + '/' + kind + '/0')
        assert legacy.status_code == 409
        assert not legacy.is_json
        non_image = request('get', exact.url + '/mediainfo')
        assert non_image.status_code == 409
        assert not non_image.is_json
        assert web.FILES.count == 0
    finally:
        with owner.report_lock:
            owner.recovery_required = False


def test_pregen_capture_cannot_fill_generation_refreshed_after_foreign_publication(foreign_review, monkeypatch):
    import cv2
    import numpy as np
    exact, source = foreign_review
    writer = cv2.VideoWriter(source['video'], cv2.VideoWriter_fourcc(*'MJPG'), 5, (160, 120))
    assert writer.isOpened()
    try:
        for _ in range(10):
            frame = np.zeros((120, 160, 3), np.uint8)
            frame[:, ::4] = (20, 180, 230)
            writer.write(frame)
    finally:
        writer.release()
    doc = raw(exact)
    for row in doc['detections']:
        row['cbox'] = [55, 45, 105, 75]
    monkeypatch.setattr(web.openscrub, 'run_scan', lambda args, cb: dict(source_report=doc, stats={}))
    deferred = []
    monkeypatch.setattr(web, '_start_owned_thread', lambda target, lease: deferred.append((target, lease)))
    original_capture = web.cv2.VideoCapture
    versions = []
    def capture(path):
        cap = original_capture(path)
        assert cap.isOpened()
        state = web.FILES.initialize(exact.job).thumbnail
        versions.append(state.current.version)
        publish_source_report(source)
        versions.append(thumbnail_version(exact))
        return cap
    monkeypatch.setattr(web.cv2, 'VideoCapture', capture)
    web._run_job(exact.job, 'scan')
    assert exact.job['phase'] == 'review'
    target, lease = deferred.pop()
    try:
        target()
    finally:
        lease.release()
    assert len(versions) == 2 and versions[0] != versions[1]
    state = web.FILES.initialize(exact.job).thumbnail
    assert state.current.version == versions[1]
    assert not state.entries
    assert web.FILES.count == 0


def test_versioned_thumbnail_preserves_own_job_recovery_gate(foreign_review):
    exact, source = foreign_review
    version = thumbnail_version(exact)
    owner = web.FILES.initialize(exact.job)
    try:
        with owner.report_lock:
            owner.recovery_required = True
        response = request('get', exact.url + '/thumb/0?v=' + version)
        assert response.status_code == 409
        assert not response.is_json
        assert web.FILES.count == 0
    finally:
        with owner.report_lock:
            owner.recovery_required = False
