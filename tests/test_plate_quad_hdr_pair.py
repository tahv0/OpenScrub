"""A fresh opt-in HDR tone-map produces frame-bound evidence, or none."""
import hashlib
import os
from pathlib import Path

import pytest

import openscrub
from test_job_lifecycle import store
from test_plate_quad_correspondence import _hdr_source, _require_media_tools
from test_report_roundtrip import Quiet


def _normalize(source, *, verify):
    options = ['--verify-hdr-plate-frames'] if verify else []
    try:
        args = openscrub.build_parser().parse_args([
            str(source), '--output', str(source.parent / 'render.mp4'),
            '--encoder', 'x264', '--hdr-output', 'match', *options])
    except SystemExit:
        pytest.fail('explicit HDR frame verification is unavailable')
    openscrub.normalize_vfr(args, Quiet())
    return args


def test_fresh_opt_in_tonemap_captures_and_binds_hdr_and_scan_frames(store):
    source = Path(store.job['dir']) / 'hdr.mp4'
    _hdr_source(source)
    args = _normalize(source, verify=True)
    candidate = getattr(args, '_hdr_quad_candidate', None)
    assert candidate is not None
    assert candidate['source_sha256'] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert candidate['count'] == 10 and candidate['fps'] == 5
    assert (candidate['width'], candidate['height']) == (64, 48)
    assert len(candidate['trace_sha256']) == 64
    digest = openscrub._quad_scan_digest(args)
    proof = args._hdr_quad_proof
    assert proof['scan_sha256'] == digest == hashlib.sha256(Path(args.video).read_bytes()).hexdigest()
    assert proof['source_sha256'] == candidate['source_sha256']
    assert proof['trace_sha256'] == candidate['trace_sha256']
    # Cached output is never promoted to a proof on a later invocation.
    cached = _normalize(source, verify=True)
    assert getattr(cached, '_hdr_quad_candidate', None) is None


def test_default_normalization_does_not_attempt_frame_proof(store, monkeypatch):
    from openscrub_internal import hdr_quad_pairs
    def unexpected(*args, **kwargs):
        pytest.fail('ordinary normalization attempted optional proof')
    monkeypatch.setattr(hdr_quad_pairs, 'fresh_tonemap', unexpected)
    source = Path(store.job['dir']) / 'hdr.mp4'
    _hdr_source(source)
    args = _normalize(source, verify=False)
    assert getattr(args, '_hdr_quad_candidate', None) is None
    assert 'verify_hdr_plate_frames' not in openscrub._settings_dict(args)


@pytest.mark.parametrize('changed', ['source', 'scan'])
def test_fresh_pair_changes_before_scan_digest_do_not_bind(store, changed):
    source = Path(store.job['dir']) / 'hdr.mp4'
    _hdr_source(source)
    args = _normalize(source, verify=True)
    assert getattr(args, '_hdr_quad_candidate', None) is not None
    target = source if changed == 'source' else Path(args.video)
    replacement = target.with_name('replacement.mp4')
    replacement.write_bytes(target.read_bytes())
    os.replace(replacement, target)
    openscrub._quad_scan_digest(args)
    assert getattr(args, '_hdr_quad_proof', None) is None


@pytest.mark.parametrize('mutation', ['wrong_pts', 'duplicate_index', 'changed_dimensions', 'missing_frame'])
def test_trace_requires_every_frame_at_the_same_exact_time_and_size(mutation):
    from openscrub_internal import hdr_quad_pairs
    lines = [
        '[showinfo@before @ 0x1] config in time_base: 1/10, frame_rate: 5/1\n',
        '[showinfo@after @ 0x2] config in time_base: 1/10, frame_rate: 5/1\n',
        '[showinfo@before @ 0x1] n: 0 pts: 0 s:64x48\n',
        '[showinfo@after @ 0x2] n: 0 pts: 0 s:64x48\n',
        '[showinfo@before @ 0x1] n: 1 pts: 2 s:64x48\n',
        '[showinfo@after @ 0x2] n: 1 pts: 2 s:64x48\n',
    ]
    assert hdr_quad_pairs._trace(lines, 5, 2, 64, 48, hashlib.sha256())
    if mutation == 'wrong_pts': lines[-1] = lines[-1].replace('pts: 2', 'pts: 3')
    if mutation == 'duplicate_index': lines[-1] = lines[-1].replace('n: 1', 'n: 0')
    if mutation == 'changed_dimensions': lines[-1] = lines[-1].replace('64x48', '48x64')
    if mutation == 'missing_frame': lines.pop()
    assert not hdr_quad_pairs._trace(lines, 5, 2, 64, 48, hashlib.sha256())


def test_unqualified_hdr_vfr_is_not_promoted_to_a_verified_pair(store):
    from test_plate_quad_correspondence import _ffmpeg
    original = Path(store.job['dir']) / 'original.mp4'
    _hdr_source(original)
    source = original.with_name('variable.mp4')
    _ffmpeg('-i', original, '-vf', r'setpts=if(lt(N\,5)\,2*N\,N+5)',
            '-fps_mode', 'passthrough', '-c:v', 'libx265', '-pix_fmt', 'yuv420p10le',
            '-x265-params', 'pools=1:frame-threads=1:log-level=error:'
                            'colorprim=bt2020:transfer=smpte2084:colormatrix=bt2020nc',
            '-color_primaries', 'bt2020', '-color_trc', 'smpte2084',
            '-colorspace', 'bt2020nc', source)
    assert openscrub.probe_vfr(str(source))[0]
    args = _normalize(source, verify=True)
    assert getattr(args, '_hdr_quad_candidate', None) is None


def test_fresh_pair_refuses_a_scan_destination_aliasing_the_hdr_source(store):
    source = Path(store.job['dir']) / 'hdr.mp4'
    _hdr_source(source)
    alias = source.with_name('hdr.sdr.mp4')
    os.link(source, alias)
    original = source.read_bytes()
    with pytest.raises(RuntimeError, match='HDR scan copy cannot alias source'):
        _normalize(source, verify=True)
    assert source.read_bytes() == original


def test_display_transform_cannot_qualify_for_a_fresh_pair(store):
    import subprocess
    from test_plate_quad_correspondence import _ffmpeg
    help_text = subprocess.check_output(['ffmpeg', '-hide_banner', '-h', 'full'],
                                        stderr=subprocess.STDOUT)
    if b'display_rotation' not in help_text:
        pytest.skip('FFmpeg display_rotation is required for this fixture')
    original = Path(store.job['dir']) / 'original.mp4'
    _hdr_source(original)
    source = original.with_name('rotated.mp4')
    _ffmpeg('-display_rotation', '90', '-i', original, '-c', 'copy', source)
    args = _normalize(source, verify=True)
    assert getattr(args, '_hdr_quad_candidate', None) is None


def test_cancelled_fresh_trace_removes_its_stage_and_preserves_source(store):
    source = Path(store.job['dir']) / 'hdr.mp4'
    _hdr_source(source)
    original = source.read_bytes()
    args = openscrub.build_parser().parse_args([
        str(source), '--output', str(source.parent / 'render.mp4'), '--encoder', 'x264',
        '--hdr-output', 'match', '--verify-hdr-plate-frames'])
    class Cancel(Quiet):
        def cancelled(self): return True
    with pytest.raises(openscrub.PipelineCancelled):
        openscrub.normalize_vfr(args, Cancel())
    assert source.read_bytes() == original
    assert not list(source.parent.glob('.hdr-quad-*'))
    assert not source.with_name('hdr.sdr.mp4').exists()
