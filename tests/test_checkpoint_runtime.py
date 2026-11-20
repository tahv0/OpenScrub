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
