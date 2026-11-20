"""Manual plate quads through the real report transaction (synthetic media)."""
import hashlib
import json
from pathlib import Path

import pytest

from test_exact_samples import exact, sample, precondition, post, raw
from test_job_lifecycle import store


@pytest.fixture
def plate(exact):
    doc = raw(exact)
    doc['provenance']['input_sha256'] = hashlib.sha256(Path(exact.job['video']).read_bytes()).hexdigest()
    doc['detections'][0].update(category='plate', plate_quad={'legacy': [3, 4]}, future={'keep': True})
    exact.path.write_text(json.dumps(doc))
    return exact


def quad_edit(store, points=None):
    sampled = sample(store)
    pc = precondition(sampled)
    box = sampled['boxes'][0]
    pc['quad_context_eq'] = box.get('quad_context_eq', '0' * 64)
    return {'geometry_preconditions': {'0': pc},
            'manual_plate_quads': {'0': {'points': points or [[12, 12], [40, 12], [40, 25], [12, 25]]}}}


def test_quad_only_save_binds_sample_and_lost_ack_replay_is_noop(plate):
    edits = quad_edit(plate)
    edits['enabled'] = {'1': True}
    response = post(plate, **edits)
    assert response.status_code == 200, response.get_data(as_text=True)
    doc = raw(plate)
    row = doc['detections'][0]
    record = row['manual_plate_quad']
    assert record['points'] == [[12/64, 12/48], [40/64, 12/48], [40/64, 25/48], [12/64, 25/48]]
    assert record['frame']['index'] == 1
    assert record['source']['sha256'] == doc['provenance']['input_sha256']
    assert row['plate_quad'] == {'legacy': [3, 4]} and row['future'] == {'keep': True}
    assert row['cbox'] == [1, 2, 8, 9] and row['t_end'] == 2
    before = plate.path.read_bytes(), plate.path.stat().st_mtime_ns
    response = post(plate, **edits)
    assert response.status_code == 200, response.get_data(as_text=True)
    assert (plate.path.read_bytes(), plate.path.stat().st_mtime_ns) == before


def test_stale_quad_replacement_cannot_overwrite_or_change_choices(plate):
    edits = quad_edit(plate)
    assert post(plate, **edits).status_code == 200
    stale = dict(edits)
    stale['manual_plate_quads'] = {'0': {'points': [[13, 12], [40, 12], [40, 25], [13, 25]]}}
    stale['enabled'] = {'1': True}
    before = plate.path.read_bytes()
    assert post(plate, **stale).status_code == 409
    assert plate.path.read_bytes() == before


@pytest.mark.parametrize('points', [
    [[12, 12], [40, 25], [40, 12], [12, 25]],
    [[12, 12], [12, 25], [40, 25], [40, 12]],
    [[12, 12], [40, 12], [20, 15], [12, 25]],
    [[12, 12], [40, 12], [40, 12], [12, 25]],
    [[-1, 12], [40, 12], [40, 25], [12, 25]],
    [[12, 12], [65, 12], [40, 25], [12, 25]],
    [[12, 12], [float('nan'), 12], [40, 25], [12, 25]],
    [[12, 12], [True, 12], [40, 25], [12, 25]],
    [[12, 12], [12.1, 12], [12.1, 12.1], [12, 12.1]],
])
def test_invalid_corners_reject_the_whole_save(plate, points):
    edits = quad_edit(plate, points)
    edits['enabled'] = {'1': True}
    before = plate.path.read_bytes()
    assert post(plate, **edits).status_code == 400
    assert plate.path.read_bytes() == before


@pytest.mark.parametrize('kind', ['missing_digest', 'wrong_digest', 'normalized', 'hdr', 'other_category'])
def test_unverified_scan_or_nonplate_rejects_atomically(plate, kind):
    edits = quad_edit(plate)
    doc = raw(plate)
    if kind == 'missing_digest': del doc['provenance']['input_sha256']
    if kind == 'wrong_digest': doc['provenance']['input_sha256'] = 'a' * 64
    if kind == 'normalized': doc['provenance']['vfr_normalized'] = True
    if kind == 'hdr': doc['provenance']['hdr_tonemapped'] = True
    if kind == 'other_category': doc['detections'][0]['category'] = 'face'
    plate.path.write_text(json.dumps(doc))
    before = plate.path.read_bytes()
    edits['enabled'] = {'1': True}
    assert post(plate, **edits).status_code == 409
    assert plate.path.read_bytes() == before


def test_clear_is_explicit_and_preserves_other_opaque_geometry(plate):
    doc = raw(plate)
    doc['detections'][0]['manual_plate_quad'] = {'version': 99, 'unknown': [1, 2]}
    plate.path.write_text(json.dumps(doc))
    edits = quad_edit(plate)
    edits['manual_plate_quads']['0'] = None
    assert post(plate, **edits).status_code == 200
    row = raw(plate)['detections'][0]
    assert 'manual_plate_quad' not in row
    assert row['plate_quad'] == {'legacy': [3, 4]}
    before = plate.path.read_bytes(), plate.path.stat().st_mtime_ns
    assert post(plate, **edits).status_code == 200
    assert (plate.path.read_bytes(), plate.path.stat().st_mtime_ns) == before


def test_source_replacement_rejects_even_an_identical_lost_ack_retry(plate):
    import os
    edits = quad_edit(plate)
    assert post(plate, **edits).status_code == 200
    source = Path(plate.job['video'])
    replacement = source.with_name('new-source.avi')
    replacement.write_bytes(source.read_bytes())
    os.replace(replacement, source)
    before = plate.path.read_bytes()
    assert post(plate, **edits).status_code == 409
    assert plate.path.read_bytes() == before


def test_report_change_during_digest_rejects_stale_quad(plate, monkeypatch):
    import threading
    import openscrub_web as web
    from test_job_lifecycle import start_call, finish
    entered, release = threading.Event(), threading.Event()
    original = web._quad_source_digest
    def paused(job, source):
        digest = original(job, source)
        entered.set()
        assert release.wait(8)
        return digest
    monkeypatch.setattr(web, '_quad_source_digest', paused)
    edits = quad_edit(plate)
    call = start_call('post', plate.url + '/detections', json=edits)
    try:
        assert entered.wait(5)
        assert post(plate, enabled={'1': True}).status_code == 200
        committed = plate.path.read_bytes()
    finally:
        release.set()
        response = finish(call)
    assert response.status_code == 409
    assert plate.path.read_bytes() == committed
    assert 'manual_plate_quad' not in raw(plate)['detections'][0]


def test_live_source_digest_is_reused_after_first_explicit_quad(plate, monkeypatch):
    import builtins
    real_open = builtins.open
    seen = []
    source = str(Path(plate.job['video']).resolve())
    class Watched:
        def __init__(self, inner): self.inner = inner
        def __enter__(self): return self
        def __exit__(self, *args): return self.inner.__exit__(*args)
        def __getattr__(self, name): return getattr(self.inner, name)
        def read(self, *args):
            value = self.inner.read(*args)
            seen.append(len(value))
            return value
    def watching(path, mode='r', *args, **kwargs):
        inner = real_open(path, mode, *args, **kwargs)
        return Watched(inner) if str(path) == source and mode == 'rb' else inner
    monkeypatch.setattr(builtins, 'open', watching)
    sampled = sample(plate)
    assert not seen
    assert post(plate, enabled={'1': True}).status_code == 200
    assert not seen
    edits = quad_edit(plate)
    assert post(plate, **edits).status_code == 200
    assert sum(seen) == Path(source).stat().st_size
    first = len(seen)
    fresh = quad_edit(plate, [[13, 12], [40, 12], [40, 25], [13, 25]])
    assert post(plate, **fresh).status_code == 200
    assert len(seen) == first


def test_positional_detection_and_fresh_report_omit_absent_quad():
    import openscrub
    poly = (((0., 0.), (1., 0.), (.5, 1.)),)
    detection = openscrub.Detection(0., 1., (1, 2, 8, 9), 'plate', 'p', .9,
                                     (0., 0.), .5, False, 11, 12, poly)
    assert detection.poly == poly and detection.manual_plate_quad is None
    args = openscrub.build_parser().parse_args(['dummy.mp4'])
    state = dict(fps=5, cum=[(0, 0)], bands=[(0, 0)], detections=[detection],
                 zdropped=[detection])
    doc = openscrub._report_document(args, state)
    assert all('manual_plate_quad' not in row for row in doc['detections'])
    assert doc['detections'][0]['poly'] == poly
    assert doc['detections'][1]['zone_dropped'] is True


def test_exact_frame_edges_are_accepted(plate):
    edits = quad_edit(plate, [[0, 0], [64, 0], [64, 48], [0, 48]])
    assert post(plate, **edits).status_code == 200
    assert raw(plate)['detections'][0]['manual_plate_quad']['points'] == [[0, 0], [1, 0], [1, 1], [0, 1]]


def test_reopened_sample_exposes_saved_quad_and_honest_eligibility_without_hash(plate):
    import openscrub_web as web
    edits = quad_edit(plate)
    assert post(plate, **edits).status_code == 200
    saved = raw(plate)['detections'][0]['manual_plate_quad']
    inspected = sample(plate, .2)['boxes'][0]
    assert inspected['manual_plate_quad'] == saved
    assert inspected['quad_eligibility'] == 'eligible_sdr_frame'
    assert sample(plate, .4)['boxes'][0]['quad_eligibility'] == 'other_frame'
    files = web.FILES.initialize(plate.job)
    with files.report_lock:
        files.current_source.pop('quad_sha256')
    assert sample(plate, .2)['boxes'][0]['quad_eligibility'] == 'unverified'


def test_sample_reports_whether_new_quad_requires_verification(plate):
    assert sample(plate)['boxes'][0]['quad_edit_eligibility'] == 'verification_required'
    edits = quad_edit(plate)
    assert post(plate, **edits).status_code == 200
    assert sample(plate)['boxes'][0]['quad_edit_eligibility'] == 'ready'
    doc = raw(plate)
    doc['provenance']['input_sha256'] = 'a' * 64
    plate.path.write_text(json.dumps(doc))
    assert sample(plate)['boxes'][0]['quad_edit_eligibility'] == 'unavailable'


def test_saved_quad_with_mismatched_report_digest_is_not_unverified(plate):
    import openscrub_web as web
    assert post(plate, **quad_edit(plate)).status_code == 200
    doc = raw(plate)
    doc['provenance']['input_sha256'] = 'a' * 64
    plate.path.write_text(json.dumps(doc))
    files = web.FILES.initialize(plate.job)
    with files.report_lock:
        files.current_source.pop('quad_sha256')
    assert sample(plate)['boxes'][0]['quad_eligibility'] == 'unavailable'
