"""Hard source-frame authority in completed report and render paths."""
from dataclasses import asdict
import copy
import hashlib
import json
import os
import shutil
import subprocess
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

import openscrub as core
from openscrub_internal.checkpoints import join_reports, with_checkpoint


class Quiet(core.Callbacks):
    def log(self, msg):
        pass


def row(box, start=0.0, end=11 / 120, **extra):
    value = dict(t_start=start, t_end=end, cbox=box, category='email',
                 text='synthetic', confidence=.99, aoff=[0., 0.],
                 last_seen=start, enabled=True, dense=False, track=-1,
                 person=-1, poly=[])
    value.update(extra)
    return value


def report(rows, count=12):
    return {'provenance': {'input_sha256': 'a' * 64, 'future': {'keep': True}},
            'render_state': {'fps': 120., 'cum': [[0., 0.]] * count,
                             'bands': [[0., 0.]] * count, 'future': 'keep'},
            'detections': copy.deepcopy(rows), 'audio_redactions': [],
            'future_top': {'x': [1, None]}}


def test_bounded_report_decodes_roundtrips_and_preserves_legacy_shape(tmp_path):
    legacy = row([5, 10, 25, 30])
    bounded = row([36, 10, 56, 30], scan_frame_start=4, scan_frame_end=8,
                  future_row={'preserve': True})
    original = report([legacy, bounded])
    dets, state, _ = core._decode_report(original)
    assert asdict(dets[0]) == {k: v for k, v in asdict(dets[0]).items()
                              if k not in ('scan_frame_start', 'scan_frame_end')}
    assert (dets[1].scan_frame_start, dets[1].scan_frame_end) == (4, 8)
    assert asdict(dets[1])['scan_frame_start'] == 4
    for mode in ('tight', 'box', 'concealed'):
        projected = core.apply_coverage(dets, mode)
        assert (projected[1].scan_frame_start, projected[1].scan_frame_end) == (4, 8)
    assert 'scan_frame_start' not in asdict(core.Detection(0, 1, (0, 0, 1, 1), 'x', '', 1))
    args = core.build_parser().parse_args([str(tmp_path / 'input.avi')])
    state.update(detections=dets, input_sha256='a' * 64, stats={}, source_report=original)
    saved = core._report_document(args, state)
    assert saved['detections'] == original['detections']
    assert saved['audio_redactions'] == original['audio_redactions']
    assert saved['future_top'] == original['future_top']
    assert saved['render_state'] == original['render_state']
    fresh_state = dict(state)
    del fresh_state['source_report']
    fresh = core._report_document(args, fresh_state)
    assert 'scan_frame_start' not in fresh['detections'][0]
    assert (fresh['detections'][1]['scan_frame_start'],
            fresh['detections'][1]['scan_frame_end']) == (4, 8)


@pytest.mark.parametrize('patch', [
    {'scan_frame_start': 2}, {'scan_frame_end': 3},
    {'scan_frame_start': None, 'scan_frame_end': None},
    {'scan_frame_start': True, 'scan_frame_end': 3},
    {'scan_frame_start': 1.0, 'scan_frame_end': 3},
    {'scan_frame_start': -1, 'scan_frame_end': 3},
    {'scan_frame_start': 3, 'scan_frame_end': 3},
    {'scan_frame_start': 3, 'scan_frame_end': 13},
    {'scan_frame_start': 1, 'scan_frame_end': '3'},
])
@pytest.mark.parametrize('enabled', [True, False])
def test_malformed_bounds_are_rejected_including_disabled_rows(patch, enabled):
    doc = report([row([5, 10, 25, 30], enabled=enabled, **patch)])
    with pytest.raises(ValueError, match='scan.frame|frame.authority'):
        core._decode_report(doc)


def test_mismatched_trajectory_or_absent_timeline_refuses_authority():
    doc = report([row([5, 10, 25, 30], scan_frame_start=0, scan_frame_end=4)])
    doc['render_state']['bands'].pop()
    with pytest.raises(ValueError, match='scan.frame|frame.authority'):
        core._decode_report(doc)
    doc['render_state']['cum'] = 'x' * 12
    doc['render_state']['bands'] = 'y' * 12
    with pytest.raises(ValueError, match='scan.frame|frame.authority'):
        core._decode_report(doc)
    del doc['render_state']
    with pytest.raises(ValueError, match='scan.frame|frame.authority'):
        core._decode_report(doc)


@pytest.mark.parametrize('marker', [None, {}, {'schema': 1, 'state': 'paused'},
                                    {'schema': 2, 'state': 'paused'},
                                    {'schema': 999, 'state': 'paused'}])
def test_any_unfinished_checkpoint_marker_cannot_enter_report_render(marker):
    doc = report([row([5, 10, 25, 30])])
    doc['stop_review'] = marker
    with pytest.raises(ValueError, match='checkpoint|paused'):
        core._decode_report(doc)


def test_bounds_survive_dense_coverage_copies_and_keep_index_before_dedupe():
    doc = report([row([5, 10, 25, 30], category='person', dense=True, track=1,
                      poly=[[[0, 0], [1, 0], [1, 1]]],
                      scan_frame_start=0, scan_frame_end=4),
                  row([36, 10, 56, 30], category='person', dense=True, track=1,
                      start=3 / 120, end=7 / 120,
                      scan_frame_start=4, scan_frame_end=8)])
    dets, _, _ = core._decode_report(doc)
    for mode in ('box', 'concealed'):
        result = core.apply_coverage(dets, mode)
        assert [d.scan_frame_start for d in result] == [0, 4]
        assert [d.scan_frame_end for d in result] == [4, 8]
        assert result[0] is not dets[0]


def make_video(tmp_path, n=12, fps=120):
    path = tmp_path / 'input.avi'
    out = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'FFV1'), fps, (96, 64))
    assert out.isOpened()
    try:
        for _ in range(n):
            out.write(np.full((64, 96, 3), 200, np.uint8))
    finally:
        out.release()
    return path


def identity(digest, n=12):
    source = {'sha256': digest, 'width': 96, 'height': 64,
              'fps': 120., 'fps_source': 'synthetic source'}
    return {'sources': {'scan': source, 'original': copy.deepcopy(source), 'render': None},
            'normalization': {'mode': 'none', 'target': 'none', 'transform_version': 'none'},
            'timeline': {'fps': 120., 'fps_source': 'synthetic source',
                         'total_frames': n, 'count_source': 'fixture', 'count_verified': True},
            'effective_settings': {'categories': ['email']}, 'file_identities': {}}


def completed_report(video):
    digest = hashlib.sha256(video.read_bytes()).hexdigest()
    opts = identity(digest)
    first = report([row([5, 10, 25, 30], end=3 / 120)], count=4)
    first['provenance']['input_sha256'] = digest
    old = with_checkpoint(first, 4, 12, opts)
    old['detections'].append(row([68, 10, 88, 30], unknown=['legacy']))
    old['detections'].append(row([1, 40, 15, 55], enabled=False,
                                 manual_id='saved', future_row={'keep': True}))
    new = report([row([36, 10, 56, 30], start=4 / 120, end=7 / 120,
                      scan_frame_start=4, scan_frame_end=8)], count=12)
    new['provenance'].update(input_sha256=digest, checkpoint_identity=opts)
    new['scan_completion'] = {'reason': 'accounted_verified_range',
                              'next_frame': 12, 'total_frames': 12}
    return join_reports(old, new, 12, 12, completed=True)


def decode_bgr(path):
    cap = cv2.VideoCapture(str(path))
    frames = []
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            frames.append(frame)
    finally:
        cap.release()
    return frames


def test_actual_sdr_completed_checkpoint_roundtrip_masks_exact_120fps_boundaries(tmp_path):
    if not shutil.which('ffmpeg'):
        pytest.skip('ffmpeg is required')
    video = make_video(tmp_path)
    doc = completed_report(video)
    path, dst = tmp_path / 'report.json', tmp_path / 'out.mp4'
    path.write_text(json.dumps(doc), encoding='utf-8')
    args = core.build_parser().parse_args([str(video), '--from-report', str(path),
            '--report', str(path), '--output', str(dst), '--encoder', 'x264',
            '--mode', 'box', '--pad', '0', '--no-vfr-fix'])
    core.run_pipeline(args, Quiet())
    frames = decode_bgr(dst)
    assert len(frames) == 12
    for i, frame in enumerate(frames):
        assert (frame[20, 15].mean() < 30) == (i < 4), i
        assert (frame[20, 46].mean() < 30) == (4 <= i < 8), i
        assert frame[20, 78].mean() < 30, i  # legacy row still works
        assert frame[47, 8].mean() > 150, i  # disabled row stays visible
    saved = json.loads(path.read_text())
    assert saved['detections'] == doc['detections']
    assert saved['render_state'] == doc['render_state']
    assert saved['audio_redactions'] == doc['audio_redactions']
    assert saved['future_top'] == doc['future_top']


def test_direct_bounded_detection_and_bad_bounds_fail_before_render_acquisition(monkeypatch):
    bounded = core.FrameBoundedDetection(0, 1, (5, 10, 25, 30), 'email', '', 1.,
                                         scan_frame_start=2, scan_frame_end=4)
    assert asdict(bounded)['scan_frame_start'] == 2
    assert asdict(bounded)['scan_frame_end'] == 4
    bounded.scan_frame_end = True
    def no_acquisition(*a, **kw):
        pytest.fail('render opened native resources for malformed bounds')
    monkeypatch.setattr(core, '_RenderDelivery', no_acquisition)
    with pytest.raises(ValueError, match='scan frame authority'):
        core.render('input', 'output', [bounded], [(0, 0)] * 4, [(0, 0)] * 4,
                    120., 0, 'box', False)


def test_paused_marker_is_rejected_before_render_or_publication(tmp_path, monkeypatch):
    doc = report([row([5, 10, 25, 30])])
    doc['stop_review'] = {'schema': 2, 'state': 'paused'}
    state = dict(detections=[], fps=120., cum=[[0, 0]] * 12, bands=[[0, 0]] * 12,
                 stats={}, source_report=doc)
    args = core.build_parser().parse_args(['input.avi', '--output', str(tmp_path / 'out.mp4'),
                                           '--report', str(tmp_path / 'report.json')])
    def no_acquisition(*a, **kw):
        pytest.fail('paused report reached render or publication')
    monkeypatch.setattr(core, '_RenderDelivery', no_acquisition)
    with pytest.raises(ValueError, match='paused checkpoint'):
        core.run_render(args, state, Quiet())
    assert not (tmp_path / 'out.mp4').exists()
    assert not (tmp_path / 'report.json').exists()


HDR_TAGS = {'-color_primaries': 'bt2020', '-color_trc': 'smpte2084',
            '-colorspace': 'bt2020nc'}


def make_hdr_video(tmp_path):
    if not (shutil.which('ffmpeg') and shutil.which('ffprobe')):
        pytest.skip('ffmpeg and ffprobe are required')
    encoders = subprocess.run(['ffmpeg', '-hide_banner', '-encoders'], capture_output=True,
                              check=True, timeout=20).stdout
    if b'libx265' not in encoders:
        pytest.skip('libx265 is required')
    frame = np.concatenate([np.full(96 * 64, 900, np.uint16),
                            np.full(48 * 32, 512, np.uint16),
                            np.full(48 * 32, 512, np.uint16)])
    raw, video = tmp_path / 'source.yuv', tmp_path / 'hdr.mp4'
    raw.write_bytes(frame.tobytes() * 12)
    color = [part for pair in HDR_TAGS.items() for part in pair]
    subprocess.run(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error',
        '-f', 'rawvideo', '-pix_fmt', 'yuv420p10le', '-s', '96x64', '-r', '120',
        *color, '-i', str(raw), '-c:v', 'libx265', '-pix_fmt', 'yuv420p10le',
        '-x265-params', 'lossless=1:pools=1:frame-threads=1:colorprim=bt2020:'
                        'transfer=smpte2084:colormatrix=bt2020nc',
        *color, str(video)], check=True, capture_output=True, timeout=30)
    return video


@pytest.mark.parametrize("hardlink", [False, True])
def test_actual_hdr_completed_checkpoint_masks_exact_120fps_boundaries(tmp_path, hardlink):
    video = make_hdr_video(tmp_path)
    render_source = video
    if hardlink:
        render_source = tmp_path / "same-source.mp4"
        try:
            os.link(video, render_source)
        except OSError as error:
            pytest.skip("hardlinks unavailable: " + str(error))
    doc = completed_report(video)
    dets, render_state, _ = core._decode_report(doc)
    path, dst = tmp_path / 'report.json', tmp_path / 'out.mp4'
    path.write_text(json.dumps(doc), encoding='utf-8')
    args = core.build_parser().parse_args([str(video), '--output', str(dst),
        '--report', str(path), '--encoder', 'x264', '--mode', 'box', '--pad', '0'])
    args.hdr_source, args.hdr_encoder, args.hdr_tags = str(render_source), 'libx265', HDR_TAGS
    state = dict(render_state, detections=dets, input_sha256=doc['provenance']['input_sha256'],
                 stats={}, source_report=doc)
    core.run_render(args, state, Quiet())
    decoded = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(dst), '-f', 'rawvideo',
        '-pix_fmt', 'yuv420p10le', 'pipe:1'], capture_output=True, check=True, timeout=30).stdout
    frame_words = 96 * 64 + 2 * 48 * 32
    assert len(decoded) == 12 * frame_words * 2
    frames = np.frombuffer(decoded, np.uint16).reshape(12, frame_words)
    for i, raw in enumerate(frames):
        y = raw[:96 * 64].reshape(64, 96)
        assert (y[20, 15] < 200) == (i < 4), (i, y[20, 15])
        assert (y[20, 46] < 200) == (4 <= i < 8), (i, y[20, 46])
        assert y[20, 78] < 200, (i, y[20, 78])
        assert y[47, 8] > 700, (i, y[47, 8])
    saved = json.loads(path.read_text())
    assert saved['detections'] == doc['detections']
    assert saved['render_state'] == doc['render_state']
    assert saved['future_top'] == doc['future_top']


@pytest.mark.parametrize("coverage", ["tight", "box", "concealed"])
def test_sdr_dense_dedupe_never_uses_a_sample_outside_its_authority(tmp_path, coverage):
    if not shutil.which('ffmpeg'):
        pytest.skip('ffmpeg is required')
    video = make_video(tmp_path)
    doc = report([
        row([5, 10, 25, 30], category='person', dense=True, track=7,
            start=0, end=5 / 120, scan_frame_start=0, scan_frame_end=4),
        row([36, 10, 56, 30], category='person', dense=True, track=7,
            start=3 / 120, end=8 / 120, scan_frame_start=4, scan_frame_end=8),
    ])
    digest = hashlib.sha256(video.read_bytes()).hexdigest()
    doc['provenance'].update(input_sha256=digest, checkpoint_identity=identity(digest))
    path, dst = tmp_path / 'dense.json', tmp_path / 'dense.mp4'
    path.write_text(json.dumps(doc), encoding='utf-8')
    args = core.build_parser().parse_args([str(video), '--from-report', str(path),
        '--output', str(dst), '--encoder', 'x264', '--mode', 'box', '--pad', '0',
        '--coverage', coverage, '--no-vfr-fix'])
    core.run_pipeline(args, Quiet())
    frames = decode_bgr(dst)
    assert len(frames) == 12
    for i, frame in enumerate(frames):
        assert (frame[20, 15].mean() < 30) == (i < 4), i
        assert (frame[20, 46].mean() < 30) == (4 <= i < 8), i


def test_sdr_trim_uses_original_source_indices_for_authority(tmp_path, monkeypatch):
    if not shutil.which('ffmpeg'):
        pytest.skip('ffmpeg is required')
    video = tmp_path / 'sequence.avi'
    out = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*'FFV1'), 120, (96, 64))
    assert out.isOpened()
    try:
        for i in range(96):
            out.write(np.full((64, 96, 3), 100 + i, np.uint8))
    finally:
        out.release()
    doc = report([row([5, 10, 25, 30], start=70 / 120, end=74 / 120,
                      scan_frame_start=70, scan_frame_end=75)], count=96)
    digest = hashlib.sha256(video.read_bytes()).hexdigest()
    doc['provenance'].update(input_sha256=digest, checkpoint_identity=identity(digest, 96))
    path, dst = tmp_path / 'trim.json', tmp_path / 'trim.mp4'
    path.write_text(json.dumps(doc), encoding='utf-8')
    args = core.build_parser().parse_args([str(video), '--from-report', str(path),
        '--output', str(dst), '--encoder', 'x264', '--mode', 'box', '--pad', '0',
        '--clip-start', '0.55', '--clip-end', '0.65', '--no-vfr-fix'])
    def no_unverified_seek(*a, **kw):
        pytest.fail('bounded output cannot use the unverified trim seek')
    monkeypatch.setattr(core, '_seek_cap', no_unverified_seek)
    core.run_pipeline(args, Quiet())
    frames = decode_bgr(dst)
    assert len(frames) == 13
    assert abs(float(frames[0][50, 90].mean()) - 166) < 4
    for i, frame in enumerate(frames):
        assert (frame[20, 15].mean() < 30) == (4 <= i < 9), i


def test_time_eligibility_still_intersects_wider_frame_authority(tmp_path):
    if not shutil.which('ffmpeg'):
        pytest.skip('ffmpeg is required')
    video = make_video(tmp_path)
    doc = report([row([5, 10, 25, 30], start=4 / 120, end=7 / 120,
                      scan_frame_start=0, scan_frame_end=12)])
    digest = hashlib.sha256(video.read_bytes()).hexdigest()
    doc['provenance'].update(input_sha256=digest, checkpoint_identity=identity(digest))
    path, dst = tmp_path / 'time.json', tmp_path / 'time.mp4'
    path.write_text(json.dumps(doc), encoding='utf-8')
    args = core.build_parser().parse_args([str(video), '--from-report', str(path),
        '--output', str(dst), '--encoder', 'x264', '--mode', 'box', '--pad', '0',
        '--no-vfr-fix'])
    core.run_pipeline(args, Quiet())
    frames = decode_bgr(dst)
    assert len(frames) == 12
    for i, frame in enumerate(frames):
        # Existing +/- .01s time eligibility reaches frames 3 and 8 at 120 fps.
        assert (frame[20, 15].mean() < 30) == (3 <= i <= 8), i


@pytest.mark.parametrize('invalid', ['source_mismatch', 'missing_source', 'missing_identity',
                                     'unverified_count', 'count_mismatch', 'fps_mismatch',
                                     'identity_hash_mismatch'])
def test_bounded_report_requires_matching_source_and_verified_timeline_before_render(
        tmp_path, monkeypatch, invalid):
    video = make_video(tmp_path)
    doc = completed_report(video)
    provenance = doc['provenance']
    identity_value = provenance['checkpoint_identity']
    if invalid == 'source_mismatch':
        provenance['input_sha256'] = '0' * 64
        identity_value['sources']['scan']['sha256'] = '0' * 64
    elif invalid == 'missing_source':
        provenance.pop('input_sha256')
    elif invalid == 'missing_identity':
        provenance.pop('checkpoint_identity')
    elif invalid == 'unverified_count':
        identity_value['timeline']['count_verified'] = False
    elif invalid == 'count_mismatch':
        identity_value['timeline']['total_frames'] = 13
    elif invalid == 'fps_mismatch':
        identity_value['timeline']['fps'] = 121.0
    else:
        identity_value['sources']['scan']['sha256'] = '0' * 64
    path, dst = tmp_path / 'existing.json', tmp_path / 'existing.mp4'
    path.write_text(json.dumps(doc), encoding='utf-8')
    before = path.read_bytes()
    dst.write_bytes(b'previous video')
    args = core.build_parser().parse_args([str(video), '--from-report', str(path),
        '--output', str(dst), '--report', str(path), '--encoder', 'x264',
        '--mode', 'box', '--pad', '0', '--no-vfr-fix'])
    hashes = []
    actual_hash = core.sha256_file
    def observed_hash(path):
        hashes.append(str(path))
        return actual_hash(path)
    monkeypatch.setattr(core, 'sha256_file', observed_hash)
    def no_acquisition(*a, **kw):
        pytest.fail('incompatible bounded report reached render publication')
    monkeypatch.setattr(core, '_RenderDelivery', no_acquisition)
    with pytest.raises(ValueError, match='source|timeline|frame'):
        core.run_pipeline(args, Quiet())
    assert hashes == [str(video)]
    assert path.read_bytes() == before and dst.read_bytes() == b'previous video'


def test_distinct_hdr_render_source_without_frame_mapping_is_refused(tmp_path, monkeypatch):
    video = make_video(tmp_path)
    other = tmp_path / 'other.avi'
    other.write_bytes(video.read_bytes() + b'changed')
    doc = completed_report(video)
    dets, rs, _ = core._decode_report(doc)
    state = dict(rs, detections=dets, input_sha256=doc['provenance']['input_sha256'],
                 stats={}, source_report=doc)
    args = core.build_parser().parse_args([str(video), '--output', str(tmp_path / 'out.mp4'),
                                          '--encoder', 'x264', '--mode', 'box', '--pad', '0'])
    args.hdr_source, args.hdr_encoder = str(other), 'libx265'
    def no_acquisition(*a, **kw):
        pytest.fail('unproven HDR source mapping reached render')
    def no_rehash(*a, **kw):
        pytest.fail('a distinct render source must not trigger another full hash')
    monkeypatch.setattr(core, '_RenderDelivery', no_acquisition)
    monkeypatch.setattr(core, 'sha256_file', no_rehash)
    with pytest.raises(ValueError, match='HDR|source|mapping'):
        core.run_render(args, state, Quiet())
    assert not (tmp_path / 'out.mp4').exists()


def test_unbounded_legacy_report_keeps_existing_input_hash_warning(tmp_path):
    if not shutil.which('ffmpeg'):
        pytest.skip('ffmpeg is required')
    video = make_video(tmp_path)
    doc = report([row([5, 10, 25, 30])])  # deliberately mismatching legacy hash
    path, dst = tmp_path / 'legacy.json', tmp_path / 'legacy.mp4'
    path.write_text(json.dumps(doc), encoding='utf-8')
    messages = []
    class Log(Quiet):
        def log(self, msg):
            messages.append(msg)
    args = core.build_parser().parse_args([str(video), '--from-report', str(path),
        '--output', str(dst), '--encoder', 'x264', '--mode', 'box', '--pad', '0',
        '--no-vfr-fix'])
    core.run_pipeline(args, Log())
    assert dst.exists()
    assert any('WARNING' in msg and 'sha256 mismatch' in msg for msg in messages)


def test_high_level_bounded_render_requires_completed_source_report(tmp_path, monkeypatch):
    video = make_video(tmp_path)
    doc = completed_report(video)
    dets, rs, _ = core._decode_report(doc)
    state = dict(rs, detections=dets, input_sha256=doc['provenance']['input_sha256'], stats={})
    args = core.build_parser().parse_args([str(video), '--output', str(tmp_path / 'out.mp4'),
                                          '--encoder', 'x264', '--mode', 'box', '--pad', '0'])
    def no_acquisition(*a, **kw):
        pytest.fail('bounded render without report provenance reached render')
    monkeypatch.setattr(core, '_RenderDelivery', no_acquisition)
    with pytest.raises(ValueError, match='bounded|report|source'):
        core.run_render(args, state, Quiet())


def test_legacy_unbounded_trim_keeps_existing_seek_optimization(tmp_path, monkeypatch):
    if not shutil.which('ffmpeg'):
        pytest.skip('ffmpeg is required')
    video = make_video(tmp_path, n=96)
    doc = report([row([5, 10, 25, 30], start=0, end=.75)], count=96)
    doc['provenance']['input_sha256'] = hashlib.sha256(video.read_bytes()).hexdigest()
    path, dst = tmp_path / 'legacy-trim.json', tmp_path / 'legacy-trim.mp4'
    path.write_text(json.dumps(doc), encoding='utf-8')
    actual_seek = core._seek_cap
    calls = []
    def observed(*a, **kw):
        calls.append(a[1])
        return actual_seek(*a, **kw)
    monkeypatch.setattr(core, '_seek_cap', observed)
    args = core.build_parser().parse_args([str(video), '--from-report', str(path),
        '--output', str(dst), '--encoder', 'x264', '--mode', 'box', '--pad', '0',
        '--clip-start', '0.55', '--clip-end', '0.65', '--no-vfr-fix'])
    core.run_pipeline(args, Quiet())
    assert calls == [66]
    assert len(decode_bgr(dst)) == 13


@pytest.mark.parametrize('mismatch', ['fps', 'length', 'cum', 'bands'])
def test_bounded_render_state_must_match_retained_report_timeline(tmp_path, monkeypatch, mismatch):
    video = make_video(tmp_path)
    doc = completed_report(video)
    dets, rs, _ = core._decode_report(doc)
    state = dict(copy.deepcopy(rs), detections=dets,
                 input_sha256=doc['provenance']['input_sha256'], stats={}, source_report=doc)
    if mismatch == 'fps':
        state['fps'] = 121.
    elif mismatch == 'length':
        state['cum'].pop()
        state['bands'].pop()
    elif mismatch == 'cum':
        state['cum'][4] = [1, 0]
    else:
        state['bands'][4] = [1, 0]
    args = core.build_parser().parse_args([str(video), '--output', str(tmp_path / 'out.mp4'),
                                          '--encoder', 'x264', '--mode', 'box', '--pad', '0'])
    def no_acquisition(*a, **kw):
        pytest.fail('mismatching bounded render state reached output')
    monkeypatch.setattr(core, '_RenderDelivery', no_acquisition)
    with pytest.raises(ValueError, match='timeline|frame'):
        core.run_render(args, state, Quiet())
