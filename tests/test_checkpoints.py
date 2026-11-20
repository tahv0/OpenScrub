"""Portable checkpoint contract: no engine, UI, or publication ownership."""
import copy
import json
import math

import pytest

from openscrub_internal.checkpoints import (
    CheckpointError, join_reports, validate_resume, with_checkpoint,
)
from openscrub_internal.reports import atomic_report


SCAN = 'a' * 64
ORIGINAL = 'b' * 64
RENDER = 'c' * 64
MODEL = 'd' * 64


def identity():
    return {
        'sources': {
            'scan': {'sha256': SCAN, 'width': 640, 'height': 480,
                     'fps': 120.0, 'fps_source': 'probe'},
            'original': {'sha256': ORIGINAL, 'width': 640, 'height': 480,
                         'fps': 120.0, 'fps_source': 'probe'},
            'render': {'sha256': RENDER, 'width': 640, 'height': 480,
                       'fps': 120.0, 'fps_source': 'probe'},
        },
        'normalization': {'mode': 'cfr', 'target': '30fps', 'transform_version': '1'},
        'timeline': {'fps': 120.0, 'fps_source': 'probe', 'total_frames': 10,
                     'count_source': 'validated normalization', 'count_verified': True},
        # Real producers must resolve the complete effective options, including
        # windows, zones and all relevant thresholds and input contents.
        'effective_settings': {'categories': ['face'], 'zones': {'ignore': []},
                               'sample_interval': .5, 'allowlist': ['sample']},
        'file_identities': {'face_model': MODEL},
    }


def row(start=0.0, end=.05, track=2, person=5, **extra):
    result = dict(t_start=start, t_end=end, last_seen=start, cbox=[1, 2, 30, 40],
                  aoff=[3, 4], category='face', text='', enabled=True,
                  track=track, person=person)
    result.update(extra)
    return result


def raw(n=4, rows=None):
    return {
        'provenance': {'input_sha256': SCAN, 'settings': {'legacy_path': 'local'},
                       'output': 'old.mp4', 'output_sha256': 'e' * 64,
                       'future_provenance': {'data': [1, None]}},
        'render_state': {'fps': 120.0, 'cum': [[n, i] for i in range(n)],
                         'bands': [[0, i] for i in range(n)], 'future_state': [3]},
        'detections': copy.deepcopy(rows if rows is not None else [row()]),
        'audio_redactions': [{'t0': 0, 't1': 1, 'extra': {'keep': True}}],
        'future_top': {'arbitrary': [False, None, 'x']},
    }


def previous():
    result = with_checkpoint(raw(), 4, 10, identity())
    # A review edit after checkpoint may add any user-owned row, no authority.
    result['detections'].append(row(0, .2, track=10, person=20, enabled=False,
                                    zone_dropped=True, manual_id='m',
                                    manual_creation={'cbox': [1, 2, 3, 4]},
                                    poly=[[[0, 0], [1, 0], [.5, 1]]],
                                    extra={'nested': [1, None]}))
    return result


def continuation(n=7, rows=None):
    doc = raw(n, rows if rows is not None else [
        row(0, .06, track=2, person=5, confidence=.99, future_suffix={'x': 1}),
        row(.04, .06, track=2, person=5),
        row(0, 0, track=12, person=30),  # wholly before the suffix
    ])
    doc['provenance']['checkpoint_identity'] = identity()
    return doc


def complete_doc():
    doc = continuation(10, [])
    doc['scan_completion'] = {'reason': 'accounted_verified_range',
                              'next_frame': 10, 'total_frames': 10}
    return doc


def test_first_checkpoint_roundtrip_adds_exclusive_authority_and_keeps_raw(tmp_path):
    source = raw(rows=[row(0, .1, unknown={'preserve': ['\u2603']})])
    options = identity()
    before = copy.deepcopy(source)
    result = with_checkpoint(source, 4, 10, options)
    assert source == before
    assert result['detections'][0] == dict(source['detections'][0],
                                           scan_frame_start=0, scan_frame_end=4)
    assert result['provenance']['checkpoint_identity'] == options
    assert result['stop_review']['next_frame'] == 4
    assert result['stop_review']['options'] == options
    assert 'output' not in result['provenance']
    assert 'output_sha256' not in result['provenance']
    path = tmp_path / 'report.json'
    atomic_report(path, result)
    saved = json.loads(path.read_text())
    assert validate_resume(saved, SCAN)['next_frame'] == 4
    assert validate_resume(saved, options)['total_frames'] == 10
    options['effective_settings']['zones']['ignore'].append('changed')
    assert not result['stop_review']['options']['effective_settings']['zones']['ignore']


def test_append_twice_preserves_all_prior_rows_choices_and_raw_audio():
    old = previous()
    untouched = copy.deepcopy(old)
    new = continuation()
    old_new = copy.deepcopy(new)
    joined = join_reports(old, new, 7, 10)
    assert old == untouched and new == old_new
    assert joined['detections'][:2] == old['detections']
    suffix = joined['detections'][2:]
    assert len(suffix) == 2
    assert all((r['scan_frame_start'], r['scan_frame_end']) == (4, 7) for r in suffix)
    assert [(r['track'], r['person']) for r in suffix] == [(11, 21), (11, 21)]
    assert suffix[0]['t_start'] == 0 and suffix[0]['t_end'] == .06
    assert suffix[0]['future_suffix'] == {'x': 1}
    assert joined['audio_redactions'] == old['audio_redactions']
    assert joined['future_top'] == old['future_top']
    assert joined['render_state']['future_state'] == old['render_state']['future_state']
    assert joined['provenance']['future_provenance'] == old['provenance']['future_provenance']
    assert joined['render_state']['cum'] == old['render_state']['cum'] + new['render_state']['cum'][4:7]
    assert joined['render_state']['bands'] == old['render_state']['bands'] + new['render_state']['bands'][4:7]
    assert 'output' not in joined['provenance'] and 'output_sha256' not in joined['provenance']
    assert joined['stop_review']['next_frame'] == 7
    second = continuation(9, [row(.05, .1, track=2, person=5)])
    again = join_reports(joined, second, 9, 10)
    assert again['detections'][:-1] == joined['detections']
    assert (again['detections'][-1]['track'], again['detections'][-1]['person']) == (12, 22)
    assert (again['detections'][-1]['scan_frame_start'], again['detections'][-1]['scan_frame_end']) == (7, 9)


def test_audio_completion_fills_only_absent_machine_fields():
    old = previous()
    old['audio_redactions'] = []
    old['audio_suggestions'] = []
    c = complete_doc()
    c['audio_redactions'] = [{'t0': 1}]
    c['audio_suggestions'] = [{'t0': 2}]
    c['audio_transcript'] = [[0, 1, 'complete']]
    result = join_reports(old, c, 10, 10, completed=True)
    assert result['audio_redactions'] == []
    assert result['audio_suggestions'] == []
    assert result['audio_transcript'] == c['audio_transcript']
    assert 'stop_review' not in result
    assert result['provenance']['checkpoint_identity'] == identity()
    assert result['detections'] == old['detections']


@pytest.mark.parametrize('frame,total', [(True, 10), (2.0, 10), (0, 10), (10, 10),
                                        (2, False), (2, 10.0)])
def test_strict_frame_boundaries(frame, total):
    with pytest.raises(CheckpointError):
        with_checkpoint(raw(), frame, total, identity())


@pytest.mark.parametrize('change', [
    lambda d: d['stop_review'].update(schema=1),
    lambda d: d['stop_review'].update(state='complete'),
    lambda d: d['stop_review'].update(next_frame=True),
    lambda d: d['stop_review'].update(fps=120.001),
    lambda d: d['provenance'].update(input_sha256='0' * 64),
    lambda d: d['provenance']['checkpoint_identity']['sources']['scan'].update(sha256='z' * 64),
    lambda d: d['stop_review']['options']['sources']['original'].update(sha256='0' * 64),
    lambda d: d['render_state']['cum'].append([0, 0]),
    lambda d: d['render_state']['bands'].pop(),
    lambda d: d['render_state']['bands'].__setitem__(0, [0, float('nan')]),
    lambda d: d['detections'][0].pop('scan_frame_end'),
    lambda d: d['detections'][0].update(scan_frame_end=4.0),
    lambda d: d['detections'][0].update(last_seen=float('inf')),
    lambda d: d['detections'][0].update(t_start=.5, t_end=.1),
    lambda d: d['detections'][0].update(track=True),
    lambda d: d['future_top'].update(nonjson={1, 2}),
])
def test_malformed_documents_have_actionable_checkpoint_errors(change):
    doc = previous()
    change(doc)
    with pytest.raises(CheckpointError):
        validate_resume(doc)


@pytest.mark.parametrize('mutate', [
    lambda o: o['sources']['original'].update(sha256='0' * 64),
    lambda o: o['sources'].update(render=None),
    lambda o: o['sources']['scan'].update(width=641),
    lambda o: o['normalization'].update(transform_version='2'),
    lambda o: o['timeline'].update(fps_source='other'),
    lambda o: o['effective_settings']['zones'].update(ignore=['changed']),
    lambda o: o['file_identities'].update(face_model='0' * 64),
])
def test_current_identity_must_match_all_sources_and_effective_settings(mutate):
    doc = previous()
    now = identity()
    mutate(now)
    with pytest.raises(CheckpointError):
        validate_resume(doc, now)
    c = continuation()
    c['provenance']['checkpoint_identity'] = now
    with pytest.raises(CheckpointError):
        join_reports(doc, c, 7, 10)


@pytest.mark.parametrize('mutate', [
    lambda o: o['sources'].pop('original'),
    lambda o: o['sources']['scan'].update(sha256=''),
    lambda o: o['sources']['scan'].update(width=True),
    lambda o: o['sources'].pop('render'),
    lambda o: o['normalization'].pop('transform_version'),
    lambda o: o['timeline'].update(count_verified=1),
    lambda o: o['timeline'].update(total_frames=11),
    lambda o: o.update(effective_settings={}),
    lambda o: o['file_identities'].update(face_model='/model/on/disk'),
])
def test_missing_and_malformed_identity_refused_on_creation(mutate):
    options = identity()
    mutate(options)
    with pytest.raises(CheckpointError):
        with_checkpoint(raw(), 4, 10, options)


@pytest.mark.parametrize('end,total,completed', [(4, 10, False), (3, 10, False),
                                                   (7, 9, False), (7, 10, True),
                                                   (10, 10, False), (True, 10, False)])
def test_no_progress_or_unproved_completion_cannot_replace_old_doc(end, total, completed, tmp_path):
    old = previous()
    path = tmp_path / 'report.json'
    atomic_report(path, old)
    before, inode = path.read_bytes(), path.stat().st_ino
    with pytest.raises(CheckpointError):
        join_reports(old, continuation(max(4, int(end))), end, total, completed)
    assert path.read_bytes() == before and path.stat().st_ino == inode


def test_completion_requires_explicit_proof_and_verified_count():
    old = previous()
    with pytest.raises(CheckpointError):
        join_reports(old, continuation(10), 10, 10, True)
    bad = complete_doc()
    bad['scan_completion']['next_frame'] = 9
    with pytest.raises(CheckpointError):
        join_reports(old, bad, 10, 10, True)
    # Reported but unverified counts can describe partial progress only.
    i = identity()
    i['timeline']['count_verified'] = False
    unverified = with_checkpoint(raw(), 4, 10, i)
    bad = complete_doc()
    bad['provenance']['checkpoint_identity'] = i
    with pytest.raises(CheckpointError):
        join_reports(unverified, bad, 10, 10, True)


def test_suffix_array_length_and_original_times_are_checked():
    old = previous()
    c = continuation(8)
    with pytest.raises(CheckpointError):
        join_reports(old, c, 7, 10)
    c = continuation(7, [row(0, .1, scan_frame_start=5, scan_frame_end=6)])
    result = join_reports(old, c, 7, 10)
    assert (result['detections'][-1]['scan_frame_start'],
            result['detections'][-1]['scan_frame_end']) == (5, 6)


def test_nonportable_large_numbers_raise_checkpoint_error():
    doc = previous()
    doc['detections'][0]['t_start'] = 10 ** 1000
    with pytest.raises(CheckpointError, match='number|integer'):
        validate_resume(doc)


def test_no_shared_references_in_returned_document_or_validation_result():
    old, c = previous(), continuation()
    result = join_reports(old, c, 7, 10)
    result['detections'][0]['cbox'][0] = 999
    result['detections'][-2]['future_suffix']['x'] = 999
    result['render_state']['cum'][-1][0] = 999
    result['provenance']['checkpoint_identity']['effective_settings']['categories'].append('x')
    assert old['detections'][0]['cbox'][0] == 1
    assert c['detections'][0]['future_suffix']['x'] == 1
    assert c['render_state']['cum'][-1][0] == 7
    meta = validate_resume(old)
    meta['options']['effective_settings']['categories'].append('x')
    assert old['stop_review']['options']['effective_settings']['categories'] == ['face']


def test_new_track_ids_cannot_exceed_json_interoperable_integer_range():
    old = previous()
    old['detections'][-1]['track'] = 2 ** 53 - 1
    with pytest.raises(CheckpointError, match='track|integer'):
        join_reports(old, continuation(), 7, 10)


def test_every_additional_declared_source_has_content_identity():
    options = identity()
    options['sources']['additional_render'] = {'path': '/tmp/only-a-path.mp4'}
    with pytest.raises(CheckpointError, match='additional_render'):
        with_checkpoint(raw(), 4, 10, options)


def test_finite_source_duration_is_required():
    options = identity()
    options['timeline']['fps'] = 5e-324
    options['sources']['scan']['fps'] = 5e-324
    doc = raw()
    doc['render_state']['fps'] = 5e-324
    with pytest.raises(CheckpointError, match='duration|timeline'):
        with_checkpoint(doc, 4, 10, options)


def test_excessive_identity_nesting_returns_checkpoint_error():
    options = identity()
    nested = []
    options['effective_settings']['nested'] = nested
    for _ in range(1500):
        child = []
        nested.append(child)
        nested = child
    with pytest.raises(CheckpointError, match='nest'):
        with_checkpoint(raw(), 4, 10, options)


def test_suffix_frame_authority_is_intersected_with_the_new_segment():
    old = previous()
    candidate = continuation(7, [row(0, .2, scan_frame_start=2, scan_frame_end=9),
                                 row(0, .2, scan_frame_start=8, scan_frame_end=9)])
    result = join_reports(old, candidate, 7, 10)
    assert len(result['detections']) == len(old['detections']) + 1
    assert result['detections'][-1]['scan_frame_start'] == 4
    assert result['detections'][-1]['scan_frame_end'] == 7


def test_suffix_drops_a_time_span_between_discrete_frames():
    options = identity()
    options['timeline']['fps'] = 1.0
    options['sources']['scan']['fps'] = 1.0
    first = raw()
    first['render_state']['fps'] = 1.0
    old = with_checkpoint(first, 4, 10, options)
    c = continuation(7, [row(5.2, 5.4), row(5.005, 5.005)])
    c['render_state']['fps'] = 1.0
    c['provenance']['checkpoint_identity'] = options
    joined = join_reports(old, c, 7, 10)
    assert len(joined['detections']) == len(old['detections']) + 1
    assert joined['detections'][-1]['t_start'] == 5.005
