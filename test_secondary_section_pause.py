"""Stopped sections apply learned models only to their scanned prefix."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

import learned_models
import openscrub_web as web
import stop_review
from test_learned_models import accepted_job
from test_secondary_models_web import (
    checker_job, proposal_report, run_check, saved_checker,
)


def _stopped_section(video, context):
    doc = proposal_report(Path(video))
    doc['render_state']['cum'] = doc['render_state']['cum'][:6]
    doc['render_state']['bands'] = doc['render_state']['bands'][:6]
    doc['detections'] = [row for row in doc['detections']
                         if row['frame_index'] < 6]
    # Empty prefixes can still carry unrelated prior detections. No row before
    # the requested section context is owned by this model application.
    options = {'categories': 'plate', 'section_context': context,
               'section_range': [context[0], 10]}
    return stop_review.with_checkpoint(doc, 6, 12, options), options


def _assert_prefix_audit(doc, mode, empty):
    audit = doc.get('verification') if mode != 'refine' else doc.get('refinement')
    if empty:
        # A true no-op may omit its audit, or report explicitly zero work.
        if audit is not None:
            assert audit['inference']['decoded_frames'] == 0
            assert audit['inference']['model_calls'] == 0
            if mode != 'refine':
                scope = audit['scope']
                assert 0 <= scope['start_frame'] == scope['end_frame'] <= 6
    else:
        assert audit is not None
        assert audit['inference']['decoded_frames'] == 5
        assert audit['inference']['model_calls'] > 0
        if mode != 'refine':
            assert audit['mode'] == mode
            assert audit['scope'] == {'start_frame': 1, 'end_frame': 6, 'fps': 10.}


@pytest.mark.parametrize('mode', ['review', 'filter', 'refine'])
@pytest.mark.parametrize('context,empty', [([1, 11], False), ([7, 11], True)])
def test_selected_model_can_finalize_a_stopped_section_prefix(
        checker_job, tmp_path, mode, context, empty):
    client, training, _, _ = checker_job
    if mode == 'refine':
        selected = learned_models.save_model(
            web.learned_models_root(), accepted_job(tmp_path / 'legacy'), 'Mask model')
    else:
        selected = saved_checker(client, training)
    chunk, options = _stopped_section(training['video'], context)
    options.update(learned_plate_model=selected['id'], learned_plate_model_mode=mode)
    job = web.new_job(training['video'], options, 'Stopped section')
    before = deepcopy(chunk)

    result = web.apply_selected_plate_model(job, chunk)

    assert chunk == before
    assert result['stop_review'] == before['stop_review']
    assert len(result['render_state']['cum']) == 6
    _assert_prefix_audit(result, mode, empty)
    if empty:
        assert result['detections'] == before['detections']
    elif mode != 'refine':
        assert result['detections'][0]['enabled'] is (mode == 'review')
        assert result['detections'][1:] == before['detections'][1:]


@pytest.mark.parametrize('mode', ['review', 'filter'])
@pytest.mark.parametrize('context,empty', [([1, 11], False), ([7, 11], True)])
def test_retained_candidate_can_check_a_paused_section_prefix(
        checker_job, mode, context, empty):
    client, job, report, _ = checker_job
    doc, options = _stopped_section(job['video'], context)
    job.update(phase='paused', options=options,
               section={'role': 'candidate', 'parent_id': 'parent',
                        'section_id': 'section', 'start_frame': context[0], 'end_frame': 10})
    report.write_text(json.dumps(doc), encoding='utf-8')

    run_check(client, job, mode)

    assert job['phase'] == 'paused'
    assert job['error'] is None, job['error']
    result = json.loads(report.read_text(encoding='utf-8'))
    assert result['stop_review'] == doc['stop_review']
    assert len(result['render_state']['cum']) == 6
    _assert_prefix_audit(result, mode, empty)
    if empty:
        assert result['detections'] == doc['detections']
    else:
        assert result['detections'][0]['enabled'] is (mode == 'review')
        assert result['detections'][1:] == doc['detections'][1:]
