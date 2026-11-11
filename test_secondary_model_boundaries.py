"""Checker provenance and assessed model identity survive worker boundaries."""
from copy import deepcopy
import hashlib
import json

import pytest

import learning_candidates
import openscrub_web as web
import stop_review
import video_sections
from test_learning_candidates import CANDIDATE_ID, proposal_model_bytes
from test_secondary_models_web import checker_job, run_check
from test_stop_review import doc_from, sample_plate
from test_video_sections import report as section_report, row as section_row


@pytest.mark.parametrize('checked_suffix', [False, True])
def test_resume_retains_earlier_checker_audit_without_claiming_suffix_coverage(checked_suffix):
    earlier = {
        'schema': 1, 'candidate_id': CANDIDATE_ID, 'model_sha256': 'a' * 64,
        'mode': 'filter', 'assessment': {'status': 'validated', 'threshold': .5},
        'inference': {'checked': 1, 'suppressed': 1},
    }
    row = sample_plate()
    row.update(verified_label='', plate_verification={
        'decision': 'suppress', 'applied': True, 'previous_enabled': True,
        'model_sha256': earlier['model_sha256'], 'mode': 'filter', 'threshold': .5,
    })
    previous = stop_review.with_checkpoint(doc_from(90, [row]), 90, 300, {})
    oldest = dict(earlier, model_sha256='c' * 64, mode='review')
    previous['verification_history'] = [oldest, earlier]
    previous['verification'] = earlier
    continuation = doc_from(180)
    current = dict(earlier, model_sha256='b' * 64, mode='review')
    if checked_suffix:
        continuation['verification_history'] = [earlier]
        continuation['verification'] = current
    before, suffix = deepcopy(previous), deepcopy(continuation)

    merged = stop_review.join_reports(previous, continuation, 180, 300)

    expected_history = [oldest, earlier] + ([current] if checked_suffix else [])
    assert merged.get('verification_history') == expected_history
    if checked_suffix:
        assert current in merged['verification_history']
        assert merged['verification'] == current
    else:
        assert 'verification' not in merged
    assert merged['detections'][0] == row
    assert previous == before and continuation == suffix


def test_section_replacement_keeps_checker_history_in_each_owned_range():
    previous = section_report([section_row(1), section_row(5), section_row(9)])
    earlier = {'model_sha256': 'a' * 64, 'mode': 'filter', 'assessment': {'threshold': .5}}
    current = {'model_sha256': 'b' * 64, 'mode': 'review', 'assessment': {'threshold': .25}}
    previous['verification_history'] = [earlier]
    candidate = section_report([section_row(5)])
    candidate['verification_history'] = [current]
    before, incoming = deepcopy(previous), deepcopy(candidate)

    merged = video_sections.replace_range(previous, candidate, 4, 8)

    assert 'verification_history' not in merged
    assert [(item['start_frame'], item['end_frame'], item['verification_history'])
            for item in merged['range_provenance']] == [
        (0, 4, [earlier]), (4, 8, [current]), (8, 12, [earlier])]
    sliced = video_sections.slice_report(merged, 4, 8)
    assert len(sliced['range_provenance']) == 1
    assert sliced['range_provenance'][0]['verification_history'] == [current]
    assert previous == before and candidate == incoming


def _replace_candidate_model(job):
    """Simulate an externally replaced version with coherent new artifact hashes."""
    candidate = learning_candidates.load_candidate(job['dir'], CANDIDATE_ID)
    payload = proposal_model_bytes(separable=False)
    replacement_sha = hashlib.sha256(payload).hexdigest()
    assert replacement_sha != candidate['model_sha256']
    candidate['model_path'].write_bytes(payload)
    path = candidate['folder'] / 'manifest.json'
    manifest = json.loads(path.read_text())
    manifest['artifacts']['model.onnx'] = replacement_sha
    path.write_text(json.dumps(manifest))
    assert learning_candidates.load_candidate(job['dir'], CANDIDATE_ID)['assessment'] is None


def test_candidate_changed_after_assessment_cannot_use_old_filter_acceptance(checker_job, monkeypatch):
    client, job, report, _ = checker_job
    before = report.read_bytes()
    evaluate = learning_candidates.evaluate

    def replace_after_evaluation(*args, **kwargs):
        assessment = evaluate(*args, **kwargs)
        assert assessment['status'] == 'validated'
        _replace_candidate_model(job)
        return assessment

    monkeypatch.setattr(learning_candidates, 'evaluate', replace_after_evaluation)
    run_check(client, job, 'filter')

    assert report.read_bytes() == before
    assert job['phase'] == 'review' and job['error']
    assert 'verification' not in job


def test_candidate_changed_during_inference_does_not_publish_stale_result(checker_job, monkeypatch):
    client, job, report, _ = checker_job
    before = report.read_bytes()
    review_report = web.plate_verifier.review_report

    def replace_after_inference(*args, **kwargs):
        result = review_report(*args, **kwargs)
        _replace_candidate_model(job)
        return result

    monkeypatch.setattr(web.plate_verifier, 'review_report', replace_after_inference)
    run_check(client, job, 'filter')

    assert report.read_bytes() == before
    assert job['phase'] == 'review' and job['error']
    assert 'verification' not in job
