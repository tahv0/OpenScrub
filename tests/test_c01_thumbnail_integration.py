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
