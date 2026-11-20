"""Quad correspondence when scan and render consume the same encoded file."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

import cv2
import numpy as np
import pytest

import openscrub
from test_exact_samples import sample, precondition, post
from test_job_lifecycle import store
from test_report_roundtrip import Quiet


@pytest.fixture(scope='module', autouse=True)
def _require_media_tools():
    if not all(shutil.which(name) for name in ('ffmpeg', 'ffprobe')):
        pytest.skip('ffmpeg and ffprobe are required')
    if not (openscrub._ffmpeg_has('zscale') and openscrub._ffmpeg_has('tonemap')):
        pytest.skip('FFmpeg zscale and tonemap are required')
    encoders = subprocess.check_output(['ffmpeg', '-hide_banner', '-encoders'], stderr=subprocess.STDOUT)
    if b'libx264' not in encoders or b'libx265' not in encoders:
        pytest.skip('FFmpeg libx264 and libx265 are required')


def _ffmpeg(*args):
    return subprocess.run(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', *map(str, args)],
                          check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45)


def _frames(path):
    cap = cv2.VideoCapture(str(path))
    try:
        result = []
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            result.append(frame)
        return result
    finally:
        cap.release()


def _hdr_source(path):
    # Each encoded frame has a different base luminance, so an adjacent-frame
    # substitution can be distinguished from the selected frame.
    pixels = []
    for index in range(10):
        y = np.full((48, 64), 500 + index * 25, dtype='<u2')
        y[36:44, 4:20] = 200 + index * 30
        pixels.append(y.tobytes() + np.full((24, 32), 512, dtype='<u2').tobytes() * 2)
    raw = path.with_suffix('.yuv')
    raw.write_bytes(b''.join(pixels))
    _ffmpeg('-f', 'rawvideo', '-pixel_format', 'yuv420p10le', '-video_size', '64x48',
            '-framerate', '5', '-i', raw, '-c:v', 'libx265', '-pix_fmt', 'yuv420p10le',
            '-x265-params', 'lossless=1:pools=1:frame-threads=1:log-level=error:'
                            'colorprim=bt2020:transfer=smpte2084:colormatrix=bt2020nc',
            '-color_primaries', 'bt2020', '-color_trc', 'smpte2084',
            '-colorspace', 'bt2020nc', path)
    raw.unlink()


def _prepare_sdr_copy(store, source):
    args = openscrub.build_parser().parse_args([
        str(source), '--output', str(source.parent / 'render.mp4'),
        '--encoder', 'x264', '--hdr-output', 'sdr'])
    openscrub.normalize_vfr(args, Quiet())
    assert os.path.realpath(args.video) != os.path.realpath(source)
    scan = Path(args.video)
    cap = cv2.VideoCapture(str(scan))
    fps, count = cap.get(cv2.CAP_PROP_FPS), int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    assert fps > 0 and count > 6
    state = {'fps': fps, 'cum': [[0, 0]] * count, 'bands': [[0, 0]] * count,
             'input_sha256': hashlib.sha256(scan.read_bytes()).hexdigest(),
             'detections': [openscrub.Detection(0, count / fps, (5, 5, 55, 35),
                                                'plate', '', 1, (0, 0), 1)]}
    doc = openscrub._report_document(args, state)
    store.job['video'] = str(scan)
    store.path.write_text(json.dumps(doc))
    return scan


def _save_quad(store, index=5):
    fps = json.loads(store.path.read_text())['render_state']['fps']
    time = (index + .01) / fps
    inspected = sample(store, time)
    assert inspected['sample']['index'] == index
    assert inspected['boxes'][0]['quad_edit_eligibility'] == 'verification_required'
    pc = precondition(inspected)
    pc['quad_context_eq'] = inspected['boxes'][0]['quad_context_eq']
    response = post(store, geometry_preconditions={'0': pc},
                    manual_plate_quads={'0': {'points': [[20, 15], [42, 13],
                                                          [40, 27], [18, 25]]}})
    assert response.status_code == 200, response.get_data(as_text=True)
    assert sample(store, time)['boxes'][0]['quad_eligibility'] == 'eligible_sdr_frame'


def _render(store, source, destination, hdr='sdr', count=10):
    args = openscrub.build_parser().parse_args([
        str(source), '--from-report', str(store.path), '--output', str(destination),
        '--encoder', 'x264', '--mode', 'box', '--pad', '0', '--hdr-output', hdr])
    openscrub.run_pipeline(args, Quiet())
    frames = _frames(destination)
    assert len(frames) == count
    return frames


def test_hdr_tonemapped_scan_is_same_verified_source_as_sdr_render(store, tmp_path):
    source = Path(store.job['dir']) / 'hdr.mp4'
    _hdr_source(source)
    metadata = json.loads(subprocess.check_output([
        'ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
        'stream=pix_fmt,color_transfer', '-of', 'json', str(source)]))['streams'][0]
    assert metadata == {'pix_fmt': 'yuv420p10le', 'color_transfer': 'smpte2084'}
    scan = _prepare_sdr_copy(store, source)
    assert _frames(scan)[5][10, 10].mean() > 30
    _save_quad(store)
    frames = _render(store, source, source.parent / 'render.mp4')
    # Center and a near-edge point in the polygon are masked, but the original
    # box's outer area and the pixel just outside that edge remain visible.
    assert frames[5][20, 30].mean() < 20
    assert frames[5][17, 21].mean() < 35
    assert frames[5][10, 10].mean() > 30
    assert frames[5][17, 15].mean() > 30
    assert frames[4][10, 10].mean() < 20
    assert frames[6][10, 10].mean() < 20


def _vfr_source(path):
    raw = path.with_suffix('.rgb')
    raw.write_bytes(b''.join(np.full((48, 64, 3), 160 + 5*i, np.uint8).tobytes()
                             for i in range(12)))
    # First six samples are 1/15s apart; the remainder are 1/30s apart.
    _ffmpeg('-f', 'rawvideo', '-pixel_format', 'rgb24', '-video_size', '64x48',
            '-framerate', '30', '-i', raw, '-vf',
            r"setpts=if(lt(N\,6)\,2*N\,N+6)", '-fps_mode', 'passthrough',
            '-c:v', 'libx264', '-pix_fmt', 'yuv420p', path)
    raw.unlink()


def test_vfr_normalization_uses_its_selected_scan_file_for_sdr_render(store):
    source = Path(store.job['dir']) / 'variable.mp4'
    _vfr_source(source)
    assert openscrub.probe_vfr(str(source))[0]
    scan = _prepare_sdr_copy(store, source)
    doc = json.loads(store.path.read_text())
    assert doc['provenance']['vfr_normalized'] is True
    assert doc['provenance']['hdr_tonemapped'] is False
    count = len(doc['render_state']['cum'])
    _save_quad(store)
    frames = _render(store, source, source.parent / 'render.mp4', count=count)
    assert frames[5][20, 30].mean() < 20
    assert frames[5][10, 10].mean() > 100
    assert frames[4][10, 10].mean() < 20
    assert frames[6][10, 10].mean() < 20
    assert hashlib.sha256(scan.read_bytes()).hexdigest() == doc['provenance']['input_sha256']


def test_changed_scan_and_separate_hdr_source_keep_full_plate(store):
    source = Path(store.job['dir']) / 'hdr.mp4'
    _hdr_source(source)
    scan = _prepare_sdr_copy(store, source)
    _save_quad(store)
    hdr_path = source.parent / 'hdr-render.mp4'
    hdr = _render(store, source, hdr_path, hdr='match')
    metadata = json.loads(subprocess.check_output([
        'ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
        'stream=pix_fmt,color_transfer', '-of', 'json', str(hdr_path)]))['streams'][0]
    assert metadata == {'pix_fmt': 'yuv420p10le', 'color_transfer': 'smpte2084'}
    assert hdr[5][10, 10].mean() < 20
    replacement = scan.with_name('replacement.mp4')
    _ffmpeg('-i', scan, '-vf', 'eq=brightness=0.03', '-c:v', 'libx264',
            '-pix_fmt', 'yuv420p', replacement)
    assert hashlib.sha256(replacement.read_bytes()).hexdigest() != hashlib.sha256(scan.read_bytes()).hexdigest()
    os.replace(replacement, scan)
    frames = _render(store, source, source.parent / 'sdr-render.mp4')
    assert frames[5][10, 10].mean() < 20


@pytest.mark.parametrize('role,alias_kind', [('render', 'direct'), ('render', 'hardlink'),
                                             ('report', 'symlink')])
def test_original_hdr_source_cannot_be_a_quad_destination(store, role, alias_kind):
    source = Path(store.job['dir']) / 'hdr.mp4'
    _hdr_source(source)
    _prepare_sdr_copy(store, source)
    _save_quad(store)
    original = source.read_bytes()
    alias = source.parent / 'alias.mp4'
    if alias_kind == 'direct':
        alias = source
    elif alias_kind == 'hardlink':
        os.link(source, alias)
    else:
        alias.symlink_to(source)
    output = alias if role == 'render' else source.parent / 'render.mp4'
    options = [] if role == 'render' else ['--report', str(alias)]
    args = openscrub.build_parser().parse_args([
        str(source), '--from-report', str(store.path), '--output', str(output),
        '--encoder', 'x264', '--mode', 'box', '--pad', '0', '--hdr-output', 'sdr', *options])
    with pytest.raises(RuntimeError, match='quad input cannot also be the ' + role + ' destination'):
        openscrub.run_pipeline(args, Quiet())
    assert source.read_bytes() == original
