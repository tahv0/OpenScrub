"""Report-to-render tests use encoded synthetic frames and actual Flask saves."""
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

import openscrub
from test_exact_samples import exact, sample, precondition, post
from test_job_lifecycle import store
from test_report_roundtrip import Quiet


def saved_plate(exact):
    path = Path(exact.job['video'])
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'MJPG'), 5, (64, 48))
    assert writer.isOpened()
    for i in range(10):
        writer.write(np.full((48, 64, 3), 180, dtype=np.uint8))
    writer.release()
    doc = json.loads(exact.path.read_text())
    doc['provenance']['input_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    doc['render_state'].update(cum=[[0, 0]] * 10, bands=[[0, 0]] * 10)
    doc['detections'][0].update(category='plate', cbox=[5, 5, 55, 35], aoff=[0, 0])
    exact.path.write_text(json.dumps(doc))
    sampled = sample(exact, 1.0)
    pc = precondition(sampled)
    pc['quad_context_eq'] = sampled['boxes'][0].get('quad_context_eq', '0' * 64)
    response = post(exact, geometry_preconditions={'0': pc},
                    manual_plate_quads={'0': {'points': [[20, 15], [40, 15], [40, 25], [20, 25]]}})
    assert response.status_code == 200, response.get_data(as_text=True)
    return path


def render(exact, path, tmp_path, *options):
    output = tmp_path / 'out.mp4'
    args = openscrub.build_parser().parse_args([str(path), '--from-report', str(exact.path),
        '--report', str(exact.path), '--output', str(output), '--encoder', 'x264',
        '--mode', 'box', '--pad', '0', *options])
    openscrub.run_pipeline(args, Quiet())
    cap = cv2.VideoCapture(str(output))
    frames = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frames.append(frame)
    cap.release()
    assert len(frames) == 10
    return frames


def test_source_bound_quad_only_changes_the_inspected_frame(exact, tmp_path):
    path = saved_plate(exact)
    frames = render(exact, path, tmp_path)
    assert frames[5][20, 30].mean() < 20
    assert frames[5][10, 10].mean() > 150
    assert frames[4][10, 10].mean() < 20
    assert frames[6][10, 10].mean() < 20
    assert 'manual_plate_quad' in json.loads(exact.path.read_text())['detections'][0]


@pytest.mark.parametrize('condition', ['digest', 'scan_digest', 'timeline', 'stream', 'size',
                                      'index', 'policy', 'version', 'normalized', 'hdr', 'coverage'])
def test_unproven_identity_or_broader_coverage_falls_back(exact, tmp_path, condition):
    path = saved_plate(exact)
    doc = json.loads(exact.path.read_text())
    record = doc['detections'][0]['manual_plate_quad']
    if condition == 'digest': record['source']['sha256'] = 'a' * 64
    if condition == 'scan_digest': doc['provenance']['input_sha256'] = 'a' * 64
    if condition == 'timeline': doc['render_state']['cum'][8] = [1, 0]
    if condition == 'stream': record['source']['stream'] += 1
    if condition == 'size': record['source']['width'] += 1
    if condition == 'index': record['frame']['index'] = 4
    if condition == 'policy': record['frame']['policy'] = 'unknown'
    if condition == 'version': record['version'] = 99
    if condition == 'normalized': doc['provenance']['vfr_normalized'] = True
    if condition == 'hdr': doc['provenance']['hdr_tonemapped'] = True
    exact.path.write_text(json.dumps(doc))
    frames = render(exact, path, tmp_path, *(['--coverage', 'box'] if condition == 'coverage' else []))
    assert frames[5][10, 10].mean() < 20


def test_nonfinite_decoder_timestamp_cannot_authorize_narrowing(exact, tmp_path, monkeypatch):
    path = saved_plate(exact)
    real_capture = openscrub.cv2.VideoCapture
    class BadTime:
        def __init__(self, *args):
            self.cap = real_capture(*args)
        def __getattr__(self, name):
            return getattr(self.cap, name)
        def get(self, prop):
            if prop == cv2.CAP_PROP_POS_MSEC:
                return float('nan')
            return self.cap.get(prop)
    monkeypatch.setattr(openscrub.cv2, 'VideoCapture', BadTime)
    frames = render(exact, path, tmp_path)
    assert frames[5][10, 10].mean() < 20


def test_padded_quad_raster_is_based_on_full_source_coordinates():
    frame = np.full((48, 64, 3), 200, dtype=np.uint8)
    quad = {'points': [[20/64, 15/48], [40/64, 15/48], [40/64, 25/48], [20/64, 25/48]]}
    openscrub._paint_plate_quad(frame, quad, 'box', 2)
    expected = np.full((48, 64, 3), 200, dtype=np.uint8)
    expected[13:28, 18:43] = 0
    np.testing.assert_array_equal(frame, expected)


def test_trim_keeps_original_source_frame_index(exact, tmp_path):
    path = saved_plate(exact)
    output = tmp_path / 'trimmed.mp4'
    args = openscrub.build_parser().parse_args([str(path), '--from-report', str(exact.path),
        '--report', str(exact.path), '--output', str(output), '--encoder', 'x264',
        '--mode', 'box', '--pad', '0', '--clip-start', '.8'])
    openscrub.run_pipeline(args, Quiet())
    cap = cv2.VideoCapture(str(output))
    ok4, frame4 = cap.read()
    ok5, frame5 = cap.read()
    cap.release()
    assert ok4 and ok5
    assert frame4[10, 10].mean() < 20
    assert frame5[10, 10].mean() > 150
    assert frame5[20, 30].mean() < 20


def test_source_change_after_quad_paint_aborts_before_output_publication(exact, tmp_path):
    import os
    path = saved_plate(exact)
    output = tmp_path / 'out.mp4'
    output.write_bytes(b'previous-output')
    previous_report = exact.path.read_bytes()
    replacement = tmp_path / 'replacement.avi'
    replacement.write_bytes(path.read_bytes())
    class ReplaceAfterRender(Quiet):
        def progress(self, stage, done, total):
            if stage == 'render' and done == total:
                os.replace(replacement, path)
    args = openscrub.build_parser().parse_args([str(path), '--from-report', str(exact.path),
        '--report', str(exact.path), '--output', str(output), '--encoder', 'x264',
        '--mode', 'box', '--pad', '0'])
    with pytest.raises(RuntimeError, match='quad input changed'):
        openscrub.run_pipeline(args, ReplaceAfterRender())
    assert output.read_bytes() == b'previous-output'
    assert exact.path.read_bytes() == previous_report


def test_invalid_report_closes_the_held_source_descriptor(exact, tmp_path, monkeypatch):
    import builtins
    path = saved_plate(exact)
    doc = json.loads(exact.path.read_text())
    del doc['render_state']['bands']
    exact.path.write_text(json.dumps(doc))
    real_open = builtins.open
    tracked = []
    def watching(name, mode='r', *args, **kwargs):
        stream = real_open(name, mode, *args, **kwargs)
        if str(name) == str(path) and mode == 'rb':
            tracked.append(stream)
        return stream
    monkeypatch.setattr(builtins, 'open', watching)
    args = openscrub.build_parser().parse_args([str(path), '--from-report', str(exact.path),
        '--report', str(exact.path), '--output', str(tmp_path / 'bad.mp4')])
    with pytest.raises(KeyError) as caught:
        openscrub.run_pipeline(args, Quiet())
    assert caught.value.__traceback__ is not None
    assert tracked and all(stream.closed for stream in tracked)


def test_preview_outlines_the_effective_quad_only_on_the_inspected_frame(exact, tmp_path):
    path = saved_plate(exact)
    frames = render(exact, path, tmp_path, '--preview')
    def red(pixel):
        b, g, r = map(int, pixel)
        return r > max(b, g) + 60
    assert red(frames[5][15, 30])
    assert not red(frames[5][5, 48])
    assert red(frames[4][5, 48])


def test_huge_padding_covers_the_frame_without_allocating_a_huge_kernel(monkeypatch):
    frame = np.full((48, 64, 3), 200, dtype=np.uint8)
    quad = {'points': [[20/64, 15/48], [40/64, 15/48], [40/64, 25/48], [20/64, 25/48]]}
    real_ones = openscrub.np.ones
    def bounded(shape, *args, **kwargs):
        assert all(axis < 1000 for axis in shape), 'excessive dilation allocation'
        return real_ones(shape, *args, **kwargs)
    monkeypatch.setattr(openscrub.np, 'ones', bounded)
    openscrub._paint_plate_quad(frame, quad, 'box', 1000000)
    assert not frame.any()


def test_decoder_count_disagreeing_with_timeline_uses_whole_plate(exact, tmp_path, monkeypatch):
    path = saved_plate(exact)
    real_capture = openscrub.cv2.VideoCapture
    class BadCount:
        def __init__(self, *args): self.cap = real_capture(*args)
        def __getattr__(self, name): return getattr(self.cap, name)
        def get(self, prop):
            return 9 if prop == cv2.CAP_PROP_FRAME_COUNT else self.cap.get(prop)
    monkeypatch.setattr(openscrub.cv2, 'VideoCapture', BadCount)
    frames = render(exact, path, tmp_path)
    assert frames[5][10, 10].mean() < 20


@pytest.mark.parametrize('mode', ['box', 'blur', 'mosaic', 'inpaint'])
def test_each_fill_mode_changes_only_the_padded_quad(mode):
    rng = np.random.default_rng(178)
    frame = rng.integers(50, 230, (48, 64, 3), dtype=np.uint8)
    before = frame.copy()
    quad = {'points': [[20/64, 15/48], [40/64, 15/48], [40/64, 25/48], [20/64, 25/48]]}
    openscrub._paint_plate_quad(frame, quad, mode, 2)
    assert np.any(frame[15:26, 20:41] != before[15:26, 20:41])
    outside = np.ones((48, 64), dtype=bool)
    outside[13:28, 18:43] = False
    np.testing.assert_array_equal(frame[outside], before[outside])


def test_replaced_source_bytes_fall_back_on_every_render(exact, tmp_path):
    path = saved_plate(exact)
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'MJPG'), 5, (64, 48))
    assert writer.isOpened()
    for i in range(10): writer.write(np.full((48, 64, 3), 210, dtype=np.uint8))
    writer.release()
    for _ in range(2):
        frames = render(exact, path, tmp_path)
        assert frames[5][10, 10].mean() < 20
