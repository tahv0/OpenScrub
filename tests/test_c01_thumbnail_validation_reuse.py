"""Validation proofs remain bound to the containing source's owner epoch."""
import os
import threading

import pytest
import openscrub_web as web
from test_c01_thumbnail_integration import foreign_review, publish_source_report, thumbnail_version
from test_exact_samples import exact
from test_job_lifecycle import finish, request, start_call, store


@pytest.mark.skipif(os.name != 'posix', reason='requires POSIX proof reuse')
def test_foreign_publication_before_fresh_metadata_forces_validation_and_new_generation(foreign_review, monkeypatch):
    exact, source = foreign_review
    version = thumbnail_version(exact)
    validate = web._thumbnail_validate_report
    validations = []
    def count(doc):
        validations.append(True)
        return validate(doc)
    monkeypatch.setattr(web, '_thumbnail_validate_report', count)
    publish_source_report(source)
    response = request('get', exact.url + '/detections')
    assert response.status_code == 200
    new_version = response.json['thumbnail_version']
    assert new_version != version
    assert validations == [True]
    repeated = request('get', exact.url + '/detections')
    assert repeated.status_code == 200 and repeated.json['thumbnail_version'] == new_version
    assert validations == [True]
    assert web.FILES.count == 0


@pytest.mark.skipif(os.name != 'posix', reason='requires POSIX proof reuse')
@pytest.mark.parametrize('transition', ['publication', 'recovery'])
@pytest.mark.parametrize('route', ['metadata', 'cold'])
def test_foreign_transition_after_reuse_proof_refuses_stale_response(foreign_review, monkeypatch, transition, route):
    exact, source = foreign_review
    version = thumbnail_version(exact)
    entered, resume = threading.Event(), threading.Event()
    validate = web._thumbnail_validate_snapshot
    proofs = []
    projected = []
    fingerprint = web.thumbs.raw_row_fingerprint
    def hold(*args, **kwargs):
        result = validate(*args, **kwargs)
        assert result[2] is not None
        proofs.append(True)
        entered.set()
        assert resume.wait(8)
        return result
    def project(row):
        projected.append(True)
        return fingerprint(row)
    monkeypatch.setattr(web, '_thumbnail_validate_snapshot', hold)
    monkeypatch.setattr(web.thumbs, 'raw_row_fingerprint', project)
    url = exact.url + ('/detections' if route == 'metadata' else '/thumb/0?v=' + version)
    call = start_call('get', url)
    owner = web.FILES.initialize(source)
    try:
        assert entered.wait(5)
        if transition == 'publication':
            publish_source_report(source)
        else:
            with owner.report_lock:
                owner.recovery_required = True
    finally:
        resume.set()
        response = finish(call)
        with owner.report_lock:
            owner.recovery_required = False
    assert proofs == [True]
    assert response.status_code == 409
    assert response.is_json and response.json['error'] == 'thumbnail_obsolete'
    assert not projected
    assert not web.FILES.initialize(exact.job).thumbnail.entries
    assert web.FILES.count == 0
