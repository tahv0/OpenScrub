"""The existing report transaction owns optional intent and policy switches."""

import copy
import json

from test_job_lifecycle import store, request


def capable(store):
    doc = copy.deepcopy(store.doc)
    doc['plate_policy_evidence_version'] = 1
    doc['provenance']['settings'] = {'uncertain_policy': 'manual_review',
                                    'plate_threshold': .1, 'plate_auto_cutoff': .8}
    rows = []
    for frame, enabled in ((2, False), (4, True)):
        rows.append(dict(t_start=frame/30, t_end=(frame+1)/30,
                         cbox=[1, 2, 8, 9], category='plate', text='plate',
                         confidence=.9, aoff=[0, 0], last_seen=frame/30,
                         dense=True, track=3, enabled=enabled,
                         policy_evidence={'origin': 'detection', 'frame': frame,
                                          'geometry_valid': True}))
    rows.append(dict(rows[0], t_start=.1, t_end=.13, enabled=False,
                     policy_evidence={'origin': 'interpolation', 'frame': None,
                                      'geometry_valid': False}))
    doc['detections'] = rows
    store.path.write_text(json.dumps(doc))
    return doc


def test_same_valued_explicit_keep_survives_policy_switch_and_reopen(store):
    capable(store)
    assert request('post', store.url + '/detections',
                   json={'enabled': {'0': False}}).status_code == 200
    doc = json.loads(store.path.read_text())
    assert doc['detections'][0]['output_choice'] == 'keep'
    assert 'output_choice' not in doc['detections'][1]
    assert request('post', store.url + '/detections',
                   json={'plate_policy': {'uncertain_policy': 'blur_candidates'}}).status_code == 200
    doc = json.loads(store.path.read_text())
    # The automatic frame-4 mask covers its track's interpolated sample; the
    # Keep on frame 2 still wins for that sample.
    assert [r['enabled'] for r in doc['detections']] == [False, True, True]
    assert doc['detections'][0]['output_choice'] == 'keep'
    assert doc['provenance']['settings']['uncertain_policy'] == 'blur_candidates'
    assert request('post', store.url + '/detections',
                   json={'plate_policy': {'uncertain_policy': 'off'}}).status_code == 200
    assert request('post', store.url + '/detections',
                   json={'plate_policy': {'uncertain_policy': 'manual_review'}}).status_code == 200
    doc = json.loads(store.path.read_text())
    assert doc['detections'][0]['output_choice'] == 'keep'
    assert doc['detections'][0]['enabled'] is False
    assert doc['plate_policy_evidence_version'] == 1
    assert doc['custom'] == {'preserved': True}


def test_explicit_blur_on_an_interpolated_sample_masks_it(store):
    capable(store)
    assert request('post', store.url + '/detections',
                   json={'enabled': {'2': True}}).status_code == 200
    row = json.loads(store.path.read_text())['detections'][2]
    assert row['output_choice'] == 'blur'
    assert row['enabled'] is True


def test_explicit_blur_without_supported_geometry_is_retained_as_a_gap(store):
    doc = capable(store)
    doc['detections'][2]['policy_evidence'] = {'origin': 'detection', 'frame': None,
                                               'geometry_valid': False}
    store.path.write_text(json.dumps(doc))
    assert request('post', store.url + '/detections',
                   json={'enabled': {'2': True}}).status_code == 200
    row = json.loads(store.path.read_text())['detections'][2]
    assert row['output_choice'] == 'blur'
    assert row['enabled'] is False


def test_legacy_click_does_not_enroll_and_switch_cannot_convert(store):
    assert request('post', store.url + '/detections',
                   json={'enabled': {'0': False}}).status_code == 200
    doc = json.loads(store.path.read_text())
    assert doc['detections'][0]['enabled'] is False
    assert 'output_choice' not in doc['detections'][0]
    before = store.path.read_bytes()
    response = request('post', store.url + '/detections',
                       json={'plate_policy': {'uncertain_policy': 'blur_candidates',
                                              'plate_auto_cutoff': .8}})
    assert response.status_code == 409
    assert store.path.read_bytes() == before


def test_invalid_optional_settings_and_floor_changes_are_rejected_atomically(store):
    capable(store)
    before = store.path.read_bytes()
    for settings in ({'uncertain_policy': 'manual_review', 'plate_auto_cutoff': float('nan')},
                     {'uncertain_policy': 'manual_review', 'plate_auto_cutoff': 10**1000},
                     {'uncertain_policy': 'manual_review', 'plate_threshold': .05}):
        assert request('post', store.url + '/detections',
                       json={'plate_policy': settings}).status_code == 400
        assert store.path.read_bytes() == before


def test_clean_boxes_follow_actual_supported_frame_not_smoothed_span(store):
    capable(store)
    at_observed = request('get', store.url + '/boxes_at?t=0.13333333333333333').json
    after_observed = request('get', store.url + '/boxes_at?t=0.16666666666666666').json
    assert [box['i'] for box in at_observed['boxes']] == [1]
    assert after_observed['boxes'] == []
    suggestions = request('get', store.url + '/boxes_at?t=0.06666666666666667&all=1').json
    assert [box['i'] for box in suggestions['boxes']] == [0]


def test_off_mode_retains_blur_intent_without_inventing_a_gap_location(store):
    doc = capable(store)
    doc['detections'][2]['policy_evidence'] = {'origin': 'detection', 'frame': None,
                                               'geometry_valid': False}
    store.path.write_text(json.dumps(doc))
    assert request('post', store.url + '/detections',
                   json={'plate_policy': {'uncertain_policy': 'off'}}).status_code == 200
    assert request('post', store.url + '/detections',
                   json={'enabled': {'2': True}}).status_code == 200
    row = json.loads(store.path.read_text())['detections'][2]
    assert row['output_choice'] == 'blur'
    assert row['enabled'] is False
