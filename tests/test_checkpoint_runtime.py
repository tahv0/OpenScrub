"""A paused native MP4 scan can resume without losing raw review edits."""
import importlib
import importlib.util
import json
import os
import shutil
import subprocess
import threading

import cv2
import numpy as np
import pytest

import openscrub as core
from openscrub_internal.reports import atomic_report


def runtime():
    assert importlib.util.find_spec('openscrub_internal.checkpoint_runtime') is not None, (
        'checkpoint scans need a native source and settings owner')
    return importlib.import_module('openscrub_internal.checkpoint_runtime')


def movie(tmp_path):
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        pytest.skip('stock ffmpeg and ffprobe required')
    code = cv2.QRCodeEncoder_create().encode('https://example.invalid/test')
    code = cv2.resize(code, (192, 192), interpolation=cv2.INTER_NEAREST)
    image = np.full((256, 256), 255, np.uint8)
    image[32:224, 32:224] = code
    still = tmp_path / 'qr.png'
    assert cv2.imwrite(str(still), image)
    path = tmp_path / 'scan.mp4'
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-loop', '1',
                    '-framerate', '6', '-i', str(still), '-frames:v', '24',
                    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-bf', '2',
                    '-g', '12', '-y', str(path)], check=True)
    return path


def args_for(video):
    parser = core.build_parser()
    args = parser.parse_args([str(video), '--categories', 'qrcode',
                              '--no-vfr-fix', '--scroll-track', 'off',
                              '--no-backtrack'])
    return core._prep_args(args, parser)


class Quiet(core.Callbacks):
    def log(self, message):
        pass


def stop_after(n):
    checks = [0]
    def requested():
        checks[0] += 1
        return checks[0] > n
    return requested


def owned_scan(rt, *args, **kwargs):
    kwargs.setdefault('publication_lock', threading.RLock())
    return rt.scan_to_report(*args, **kwargs)


def test_real_scan_pause_edit_restart_and_resume_keep_raw_decisions(tmp_path):
    rt = runtime()
    video = movie(tmp_path)
    args = args_for(video)
    path = tmp_path / 'review.json'
    paused = owned_scan(rt, args, str(path), cb=Quiet(),
                               stop_requested=stop_after(9))
    assert paused['stop_review']['next_frame'] == 9
    assert paused['stop_review']['options']['timeline']['count_verified'] is False
    assert paused['detections'], 'the real QR detector found the fixture'
    assert len(paused['render_state']['cum']) == len(paused['render_state']['bands']) == 9
    assert json.loads(path.read_text()) == paused

    saved = json.loads(path.read_text())
    saved['detections'][0]['enabled'] = False
    saved['detections'][0]['t_end'] = 3.0
    saved['detections'][0]['unknown_row'] = {'keep': [1, 2]}
    manual = dict(saved['detections'][0], category='manual', text='manual',
                  t_start=0.0, t_end=1.0, track=321,
                  enabled=True, manual_geometry={'future': 'opaque'})
    manual.pop('scan_frame_start')
    manual.pop('scan_frame_end')
    saved['detections'].append(manual)
    saved['audio_redactions'] = [{'t0': .2, 't1': .7, 'mode': 'mute', 'extra': 1}]
    saved['audio_suggestions'] = []
    saved['unknown_top'] = {'retain': True}
    saved['provenance']['unknown_provenance'] = 'keep'
    atomic_report(str(path), saved)
    previous_rows = saved['detections'].copy()

    # Loading from disk models a fresh-process resume. A stop before advancing
    # cannot rewrite even one byte of the reviewed document.
    before = path.read_bytes()
    owned_scan(rt, args_for(video), str(path), cb=Quiet(),
                      stop_requested=lambda: True, resume=True)
    assert path.read_bytes() == before

    result = owned_scan(rt, args_for(video), str(path), cb=Quiet(),
                               stop_requested=lambda: False, resume=True)
    assert result == json.loads(path.read_text())
    assert 'stop_review' not in result
    assert result['provenance']['checkpoint_identity']['timeline']['count_verified'] is True
    assert result['detections'][:len(previous_rows)] == previous_rows
    assert result['unknown_top'] == {'retain': True}
    assert result['provenance']['unknown_provenance'] == 'keep'
    assert result['audio_redactions'] == saved['audio_redactions']
    assert result['audio_suggestions'] == []
    assert len(result['render_state']['cum']) == len(result['render_state']['bands']) == 24
    assert all(row['scan_frame_start'] == 9 and row['scan_frame_end'] == 24
               for row in result['detections'][len(previous_rows):])
    assert result['detections'][len(previous_rows):]


def test_resume_rejects_changed_scan_settings_without_touching_checkpoint(tmp_path):
    rt = runtime()
    video = movie(tmp_path)
    path = tmp_path / 'review.json'
    owned_scan(rt, args_for(video), str(path), cb=Quiet(),
                      stop_requested=stop_after(9))
    before = path.read_bytes()
    args = args_for(video)
    args.dense_face_stride = 3
    with pytest.raises(ValueError, match='settings changed'):
        owned_scan(rt, args, str(path), cb=Quiet(),
                          stop_requested=lambda: False, resume=True)
    assert path.read_bytes() == before


def test_resume_postprocessing_never_restarts_decode_from_frame_zero(tmp_path, monkeypatch):
    rt = runtime()
    video = movie(tmp_path)
    path = tmp_path / 'review.json'
    owned_scan(rt, args_for(video), str(path), cb=Quiet(),
                      stop_requested=stop_after(15))
    def forbidden(*args, **kwargs):
        raise AssertionError('postprocessing reopened the full prefix with OpenCV')
    monkeypatch.setattr(core.cv2, 'VideoCapture', forbidden)
    result = owned_scan(rt, args_for(video), str(path), cb=Quiet(),
                               stop_requested=lambda: False, resume=True)
    assert 'stop_review' not in result


def test_review_choices_saved_during_resume_are_merged_from_latest_report(tmp_path):
    rt = runtime()
    video = movie(tmp_path)
    path = tmp_path / 'review.json'
    owned_scan(rt, args_for(video), str(path), cb=Quiet(),
                      stop_requested=stop_after(9))
    changed = [False]
    def edit_during_scan():
        if not changed[0]:
            document = json.loads(path.read_text())
            document['detections'][0]['enabled'] = False
            document['detections'][0]['newer_choice'] = 'keep'
            document['audio_redactions'] = [{'t0': 0.1, 't1': 1.0, 'mode': 'mute'}]
            atomic_report(str(path), document)
            changed[0] = True
        return False
    result = owned_scan(rt, args_for(video), str(path), cb=Quiet(),
                               stop_requested=edit_during_scan, resume=True)
    assert result['detections'][0]['enabled'] is False
    assert result['detections'][0]['newer_choice'] == 'keep'
    assert result['audio_redactions'] == [{'t0': 0.1, 't1': 1.0, 'mode': 'mute'}]


def test_attempt_hashes_source_once_and_fences_it_through_publication(tmp_path, monkeypatch):
    rt = runtime()
    video = movie(tmp_path)
    path = tmp_path / 'review.json'
    actual_hash = core.sha256_file
    source_hashes = []
    def record_hash(filename, *args, **kwargs):
        if os.path.abspath(filename) == os.path.abspath(video):
            source_hashes.append(str(filename))
        return actual_hash(filename, *args, **kwargs)
    monkeypatch.setattr(core, 'sha256_file', record_hash)
    owned_scan(rt, args_for(video), str(path), cb=Quiet(),
                      stop_requested=stop_after(9))
    assert len(source_hashes) == 1


def test_cancel_at_publication_preserves_previous_report(tmp_path, monkeypatch):
    from contextlib import contextmanager
    rt = runtime()
    video = movie(tmp_path)
    path = tmp_path / 'review.json'
    owned_scan(rt, args_for(video), str(path), cb=Quiet(), stop_requested=stop_after(9))
    before = path.read_bytes()
    cancelled = threading.Event()
    actual_stage = rt._staged_report
    @contextmanager
    def cancel_after_staging(*args, **kwargs):
        with actual_stage(*args, **kwargs) as staged:
            cancelled.set()
            yield staged
    class Cancelling(Quiet):
        def cancelled(self):
            return cancelled.is_set()
    monkeypatch.setattr(rt, '_staged_report', cancel_after_staging)
    with pytest.raises(core.PipelineCancelled):
        owned_scan(rt, args_for(video), str(path), cb=Cancelling(),
                   stop_requested=lambda: False, resume=True)
    assert path.read_bytes() == before
    assert not list(tmp_path.glob('.report-*.tmp'))


def test_source_mutation_during_resume_preserves_checkpoint(tmp_path):
    rt = runtime()
    video = movie(tmp_path)
    path = tmp_path / 'review.json'
    owned_scan(rt, args_for(video), str(path), cb=Quiet(), stop_requested=stop_after(9))
    before = path.read_bytes()
    changed = [False]
    def alter_source():
        if not changed[0]:
            value = video.stat()
            os.utime(video, ns=(value.st_atime_ns, value.st_mtime_ns + 10000000))
            changed[0] = True
        return False
    with pytest.raises(rt.checkpoint_media.FrameEvidenceError, match='source changed'):
        owned_scan(rt, args_for(video), str(path), cb=Quiet(),
                   stop_requested=alter_source, resume=True)
    assert path.read_bytes() == before


def test_cancel_interrupts_a_stalled_decoder_and_preserves_report(tmp_path, monkeypatch):
    import sys
    import time
    rt = runtime()
    video = movie(tmp_path)
    report = tmp_path / 'review.json'
    owned_scan(rt, args_for(video), str(report), cb=Quiet(), stop_requested=stop_after(9))
    before = report.read_bytes()
    decoder = tmp_path / 'stall_decoder.py'
    decoder.write_text('import sys, time\n'
                       'sys.stdout.buffer.write(b"x" * 100)\n'
                       'sys.stdout.buffer.flush()\n'
                       'time.sleep(2)\n')
    original = subprocess.Popen
    children = []
    def launch(command, *args, **kwargs):
        if command[0] == 'ffmpeg':
            process = original([sys.executable, '-u', str(decoder)], *args, **kwargs)
            children.append(process)
            return process
        return original(command, *args, **kwargs)
    monkeypatch.setattr(rt.checkpoint_media.subprocess, 'Popen', launch)
    class CancelDuringRead(Quiet):
        started = None
        def cancelled(self):
            if self.started is None:
                self.started = time.monotonic()
            return time.monotonic() - self.started > .2
    callback = CancelDuringRead()
    with pytest.raises(core.PipelineCancelled):
        owned_scan(rt, args_for(video), str(report), cb=callback,
                   stop_requested=lambda: False, resume=True)
    assert time.monotonic() - callback.started < 1
    assert report.read_bytes() == before
    assert len(children) == 1 and children[0].poll() is not None
    assert children[0].stdout.closed and children[0].stderr.closed


def test_initial_clean_eof_publishes_verified_completed_report(tmp_path):
    rt = runtime()
    video = movie(tmp_path)
    path = tmp_path / 'review.json'
    result = owned_scan(rt, args_for(video), str(path), cb=Quiet(),
                        stop_requested=lambda: False)
    assert result == json.loads(path.read_text())
    assert 'stop_review' not in result
    assert result['provenance']['checkpoint_identity']['timeline']['count_verified'] is True
    assert len(result['render_state']['cum']) == len(result['render_state']['bands']) == 24
    assert result['detections']
    assert all((row['scan_frame_start'], row['scan_frame_end']) == (0, 24)
               for row in result['detections'])
    # The completed producer's output must be accepted by the actual bounded
    # renderer, with all source-frame indices intact.
    out = tmp_path / 'completed.mp4'
    parser = core.build_parser()
    render_args = core._prep_args(parser.parse_args([
        str(video), '--from-report', str(path), '--output', str(out),
        '--encoder', 'x264', '--mode', 'box', '--pad', '0', '--no-vfr-fix']), parser)
    core.run_pipeline(render_args, Quiet())
    capture = cv2.VideoCapture(str(out))
    frames = []
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            frames.append(frame)
    finally:
        capture.release()
    assert len(frames) == 24
    assert frames[0][0, 0].mean() > 230
    assert frames[0][128, 128].mean() < 30


def test_stop_after_last_frame_checks_eof_and_completes(tmp_path):
    rt = runtime()
    video = movie(tmp_path)
    path = tmp_path / 'review.json'
    result = owned_scan(rt, args_for(video), str(path), cb=Quiet(),
                        stop_requested=stop_after(24))
    assert 'stop_review' not in result
    assert result['provenance']['checkpoint_identity']['timeline']['count_verified'] is True
    assert len(result['render_state']['cum']) == 24


def test_last_frame_stop_cannot_certify_without_decoder_eof(tmp_path, monkeypatch):
    rt = runtime()
    video = movie(tmp_path)
    path = tmp_path / 'review.json'
    actual_read = rt.checkpoint_media.FrameStream.read
    def fail_at_terminal_read(stream):
        if stream.next_frame == stream.source.total_frames:
            raise rt.checkpoint_media.FrameEvidenceError('terminal EOF unavailable')
        return actual_read(stream)
    monkeypatch.setattr(rt.checkpoint_media.FrameStream, 'read', fail_at_terminal_read)
    with pytest.raises(rt.checkpoint_media.FrameEvidenceError, match='terminal EOF unavailable'):
        owned_scan(rt, args_for(video), str(path), cb=Quiet(),
                   stop_requested=stop_after(24))
    assert not path.exists()


def test_cancel_at_final_frame_preserves_paused_report_bytes(tmp_path):
    rt = runtime()
    video = movie(tmp_path)
    path = tmp_path / 'review.json'
    owned_scan(rt, args_for(video), str(path), cb=Quiet(), stop_requested=stop_after(9))
    before = path.read_bytes()
    cancelled = threading.Event()
    class Cancelled(Quiet):
        def cancelled(self):
            return cancelled.is_set()
    calls = [0]
    def stop_and_cancel_at_end():
        calls[0] += 1
        # Resume starts at frame 3 and observes 21 frames through frame 23.
        if calls[0] > 21:
            cancelled.set()
            return True
        return False
    with pytest.raises(core.PipelineCancelled):
        owned_scan(rt, args_for(video), str(path), cb=Cancelled(),
                   stop_requested=stop_and_cancel_at_end, resume=True)
    assert path.read_bytes() == before


def test_zero_detection_completed_checkpoint_rejects_another_source(tmp_path):
    rt = runtime()
    video = movie(tmp_path)
    args = args_for(video)
    args.categories = 'none'
    source = rt.checkpoint_media.inspect_source(str(video))
    identity = rt._identity(args, source)
    identity['timeline']['count_verified'] = True
    state = {'fps': 6.0, 'cum': [(0.0, 0.0)] * 24,
             'bands': [(0.0, 0.0)] * 24, 'detections': [],
             'input_sha256': source.sha256, 'stats': {}}
    report = core._report_document(args, state)
    report['provenance']['checkpoint_identity'] = identity
    report_path = tmp_path / 'complete.json'
    atomic_report(str(report_path), report)
    other = tmp_path / 'other.mp4'
    # Appending an inert byte keeps a decodable video while changing the
    # selected file's content identity.
    other.write_bytes(video.read_bytes() + b'\x00')
    out = tmp_path / 'must-not-render.mp4'
    parser = core.build_parser()
    render_args = core._prep_args(parser.parse_args([
        str(other), '--from-report', str(report_path), '--output', str(out),
        '--encoder', 'x264', '--no-vfr-fix']), parser)
    with pytest.raises(ValueError, match='source|SHA-256'):
        core.run_pipeline(render_args, Quiet())
    assert not out.exists()


def test_initial_checkpoint_retains_configured_audio_redactions(tmp_path):
    rt = runtime()
    video = movie(tmp_path)
    args = args_for(video)
    args.audio_redact = '0.25-0.75'
    args.audio_redact_mode = 'mute'
    path = tmp_path / 'review.json'
    result = owned_scan(rt, args, str(path), cb=Quiet(), stop_requested=stop_after(9))
    assert result['audio_redactions'] == [{'t0': .25, 't1': .75, 'mode': 'mute'}]


def test_zero_detection_checkpoint_rejects_early_render_decode(tmp_path, monkeypatch):
    rt = runtime()
    video = movie(tmp_path)
    args = args_for(video)
    args.categories = 'none'
    source = rt.checkpoint_media.inspect_source(str(video))
    identity = rt._identity(args, source)
    identity['timeline']['count_verified'] = True
    state = {'fps': 6.0, 'cum': [(0.0, 0.0)] * 24,
             'bands': [(0.0, 0.0)] * 24, 'detections': [],
             'input_sha256': source.sha256, 'stats': {}}
    document = core._report_document(args, state)
    document['provenance']['checkpoint_identity'] = identity
    report = tmp_path / 'complete.json'
    atomic_report(str(report), document)
    out = tmp_path / 'previous.mp4'
    out.write_bytes(b'previous video remains')
    actual_capture = core.cv2.VideoCapture
    class EarlyCapture:
        def __init__(self, *a, **kw):
            self.capture = actual_capture(*a, **kw)
            self.reads = 0
        def read(self):
            if self.reads == 8:
                return False, None
            ok, frame = self.capture.read()
            if ok:
                self.reads += 1
            return ok, frame
        def __getattr__(self, name):
            return getattr(self.capture, name)
    monkeypatch.setattr(core.cv2, 'VideoCapture', EarlyCapture)
    parser = core.build_parser()
    render_args = core._prep_args(parser.parse_args([
        str(video), '--from-report', str(report), '--output', str(out),
        '--encoder', 'x264', '--no-vfr-fix']), parser)
    with pytest.raises(ValueError, match='frame|decoder'):
        core.run_pipeline(render_args, Quiet())
    assert out.read_bytes() == b'previous video remains'
