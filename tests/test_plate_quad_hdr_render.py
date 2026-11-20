"""Fresh HDR pairing through real scan, exact editor, and 10-bit render."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

import cv2
import numpy as np
import pytest

import openscrub
import openscrub_web as web
from test_exact_samples import sample, precondition, post
from test_hdr_chroma_coverage import _decode, _observe_encoder
from test_job_lifecycle import store
from test_plate_quad_correspondence import _ffmpeg, _require_media_tools
from test_report_transactions import join


@pytest.fixture
def plate_model():
    path = os.environ.get('OPENSCRUB_TEST_PLATE_MODEL')
    if not path or not Path(path).is_file():
        pytest.skip('set OPENSCRUB_TEST_PLATE_MODEL to the stock pinned plate model')
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == (
        'c3c1026ca7d0585dd88084d68182dd897113712fa734ae1557ca70174440c076')
    return path


def _hdr_plate(source):
    rng = np.random.default_rng(747)
    frame = rng.integers(50, 85, (360, 640, 3), dtype=np.uint8)
    x, y, w, h = 204, 146, 232, 62
    cv2.rectangle(frame, (x, y), (x + w, y + h), (236,) * 3, -1)
    cv2.rectangle(frame, (x, y), (x + w, y + h), (20,) * 3, 2)
    cv2.rectangle(frame, (x + 4, y + 3), (x + 28, y + h - 3), (178, 49, 20), -1)
    cv2.putText(frame, 'QZ 27 KTX', (x + 32, y + 42), cv2.FONT_HERSHEY_SIMPLEX,
                1.12, (19,) * 3, 2, cv2.LINE_AA)
    raw = source.with_suffix('.bgr')
    with raw.open('wb') as stream:
        for i in range(10):
            frame[:12, :12] = i * 20
            stream.write(frame.tobytes())
    _ffmpeg('-f', 'rawvideo', '-pixel_format', 'bgr24', '-video_size', '640x360',
            '-framerate', '5', '-i', raw, '-c:v', 'libx265', '-pix_fmt', 'yuv420p10le',
            '-x265-params', 'lossless=1:pools=1:frame-threads=1:log-level=error:'
                            'colorprim=bt2020:transfer=smpte2084:colormatrix=bt2020nc',
            '-color_primaries', 'bt2020', '-color_trc', 'smpte2084',
            '-colorspace', 'bt2020nc', source)
    raw.unlink()


@pytest.fixture
def verified_job(store, plate_model, monkeypatch):
    source = Path(store.job['dir']) / 'hdr.mp4'
    _hdr_plate(source)
    monkeypatch.setenv('OPENSCRUB_NO_AUTOFETCH', '1')
    monkeypatch.setattr(web, 'load_model_select', lambda: {'plate': 'pinned-stock'})
    monkeypatch.setattr(web, 'find_model_file', lambda name: plate_model if name == 'pinned-stock.onnx' else None)
    threads = []
    start = web._start_owned_thread
    def track_thread(*args):
        thread = start(*args)
        threads.append(thread)
        return thread
    monkeypatch.setattr(web, '_start_owned_thread', track_thread)
    store.job['video'] = str(source)
    store.job['options'].update(categories='plate', encoder='x264', plate_threshold=.05,
        hdr_output='match', mode='box', pad=0, verify_hdr_plate_frames=True)
    web._run_job(store.job, 'scan')
    for thread in threads:
        join(thread)
    assert store.job['phase'] == 'review', store.job.get('error')
    inspected = sample(store, 1.0)
    row = next(row for row in inspected['boxes']
               if row['category'] == 'plate' and row['t_start'] == 1.0)
    assert row['quad_edit_eligibility'] == 'verification_required'
    pc = precondition(inspected, row['i'])
    pc['quad_context_eq'] = row['quad_context_eq']
    points = [[220, 155], [420, 155], [420, 200], [220, 200]]
    key = str(row['i'])
    result = post(store, geometry_preconditions={key: pc},
                  manual_plate_quads={key: {'points': points}})
    assert result.status_code == 200, result.get_data(as_text=True)
    assert sample(store, 1.0)['boxes'][-1]['quad_eligibility'] == 'eligible_sdr_frame'
    return store, source, points


def test_actual_hdr_plate_scan_editor_and_10bit_render(verified_job, monkeypatch):
    store, source, points = verified_job
    with _observe_encoder(monkeypatch, openscrub._render_hdr_into) as (captured, _):
        web._run_job(store.job, 'render')
    assert store.job['phase'] == 'done', store.job.get('error')
    output = Path(store.job['output'])
    metadata = json.loads(subprocess.check_output([
        'ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
        'stream=pix_fmt,color_transfer', '-of', 'json', str(output)]))['streams'][0]
    assert metadata == {'pix_fmt': 'yuv420p10le', 'color_transfer': 'smpte2084'}
    assert len(captured) == 10
    raw = _decode(source, 'yuv420p10le')
    frame_words = 640 * 360 * 3 // 2
    before = np.frombuffer(raw, dtype=np.uint16).reshape(10, frame_words)
    after = np.frombuffer(b''.join(captured), dtype=np.uint16).reshape(10, frame_words)
    for index in (4, 6):
        y = after[index, :640 * 360].reshape(360, 640)
        assert y[145, 195] == 64
    y0 = before[5, :640 * 360].reshape(360, 640)
    y1 = after[5, :640 * 360].reshape(360, 640)
    mask = np.zeros((360, 640), dtype=np.uint8)
    cv2.fillPoly(mask, [np.array(points, dtype=np.int32)], 1)
    assert np.all(y1[mask == 1] == 64)
    np.testing.assert_array_equal(y1[mask == 0], y0[mask == 0])
    for plane in (1, 2):
        start = 640 * 360 + (plane - 1) * (320 * 180)
        c0 = before[5, start:start + 320 * 180].reshape(180, 320)
        c1 = after[5, start:start + 320 * 180].reshape(180, 320)
        cmask = mask.reshape(180, 2, 320, 2).max(axis=(1, 3)).astype(bool)
        assert np.all(c1[cmask] == 512)
        np.testing.assert_array_equal(c1[~cmask], c0[~cmask])


@pytest.mark.parametrize('loss', ['restart', 'source_replaced', 'scan_replaced'])
def test_lost_or_changed_pair_uses_full_hdr_mask(verified_job, monkeypatch, loss):
    store, source, _ = verified_job
    if loss == 'restart':
        # A new job owner has no ephemeral trace, even if both files survive.
        del store.job['_files']
        inspected = sample(store, 1.0)
        row = next(row for row in inspected['boxes'] if row['t_start'] == 1.0)
        assert row['quad_eligibility'] == 'unavailable'
    else:
        scan = Path(store.job['video'])
        target = source if loss == 'source_replaced' else scan
        replacement = target.with_name('replacement.mp4')
        replacement.write_bytes(target.read_bytes())
        if loss == 'source_replaced':
            # Preserve the old mtime so the existing scan cache remains selected.
            os.utime(replacement, ns=(target.stat().st_atime_ns, target.stat().st_mtime_ns))
        os.replace(replacement, target)
    with _observe_encoder(monkeypatch, openscrub._render_hdr_into) as (captured, _):
        web._run_job(store.job, 'render')
    assert store.job['phase'] == 'done', store.job.get('error')
    frame = np.frombuffer(captured[5], dtype=np.uint16)[:640 * 360].reshape(360, 640)
    assert frame[145, 195] == 64


def test_hdr_source_change_after_paint_aborts_publication(verified_job, monkeypatch):
    store, source, _ = verified_job
    output = source.parent / 'output.mp4'
    output.write_bytes(b'prior-output')
    prior_report = store.path.read_bytes()
    replacement = source.with_name('replacement.mp4')
    replacement.write_bytes(source.read_bytes())
    progress = web.WebCallbacks.progress
    changed = []
    def replace_source(callback, stage, done, total):
        if stage == 'render' and done == total and not changed:
            os.replace(replacement, source)
            changed.append(True)
        return progress(callback, stage, done, total)
    monkeypatch.setattr(web.WebCallbacks, 'progress', replace_source)
    web._run_job(store.job, 'render')
    assert changed
    assert store.job['phase'] == 'error'
    assert 'quad input changed' in store.job['error']
    assert output.read_bytes() == b'prior-output'
    assert store.path.read_bytes() == prior_report


def test_early_hdr_decoder_eof_after_quad_cannot_publish(verified_job, monkeypatch):
    store, source, _ = verified_job
    output = source.parent / 'output.mp4'
    output.write_bytes(b'prior-output')
    prior_report = store.path.read_bytes()
    real_popen = subprocess.Popen
    class Truncated:
        def __init__(self, stream, process):
            self.stream, self.process, self.reads = stream, process, 0
        def read(self, size):
            if self.reads == 6:
                self.process.terminate()
                return b''
            self.reads += 1
            return self.stream.read(size)
        def close(self): self.stream.close()
        def __getattr__(self, key): return getattr(self.stream, key)
    def popen(args, *a, **kwargs):
        process = real_popen(args, *a, **kwargs)
        if isinstance(args, list) and 'rawvideo' in args and 'pipe:1' in args:
            process.stdout = Truncated(process.stdout, process)
        return process
    monkeypatch.setattr(openscrub.subprocess, 'Popen', popen)
    web._run_job(store.job, 'render')
    assert store.job['phase'] == 'error'
    assert 'HDR frame' in store.job['error']
    assert output.read_bytes() == b'prior-output'
    assert store.path.read_bytes() == prior_report
