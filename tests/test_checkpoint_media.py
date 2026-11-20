"""Frame evidence for checkpoint scans, using stock FFmpeg and real MP4s."""
import importlib
import importlib.util
import os
import shutil
import subprocess
from dataclasses import replace

import numpy as np
import pytest


def media_module():
    assert importlib.util.find_spec('openscrub_internal.checkpoint_media') is not None, (
        'checkpoint scanner needs a verified frame stream')
    return importlib.import_module('openscrub_internal.checkpoint_media')


def clip(tmp_path, rate='6', count=18):
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        pytest.skip('stock ffmpeg and ffprobe required')
    path = tmp_path / 'source.mp4'
    cmd = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-f', 'lavfi',
           '-i', f'testsrc2=size=96x64:rate={rate}', '-frames:v', str(count),
           '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-g', '12',
           '-bf', '2', '-y', str(path)]
    subprocess.run(cmd, check=True)
    return path


def read_all(reader):
    frames = []
    with reader:
        while True:
            result = reader.read()
            if result is None:
                break
            frames.append(result)
    return frames


def test_real_mp4_seek_resolves_absolute_indices_and_clean_completion(tmp_path):
    media = media_module()
    source = clip(tmp_path)
    identity = media.inspect_source(str(source))
    assert (identity.width, identity.height, identity.total_frames) == (96, 64, 18)
    assert identity.count_verified is False
    with media.FrameStream(identity, start_frame=0) as whole:
        frames = []
        while (frame := whole.read()) is not None:
            frames.append(frame)
        assert whole.completed is True
        assert whole.next_frame == 18
    with media.FrameStream(identity, start_frame=8) as suffix:
        suffix_frames = []
        while (frame := suffix.read()) is not None:
            suffix_frames.append(frame)
        assert suffix.completed is True
    assert [index for index, _ in suffix_frames] == list(range(8, 18))
    raw = subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error',
                          '-noautorotate', '-i', str(source), '-map', '0:v:0',
                          '-fps_mode', 'passthrough', '-f', 'rawvideo',
                          '-pix_fmt', 'bgr24', 'pipe:1'],
                         stdout=subprocess.PIPE, check=True).stdout
    assert b''.join(frame.tobytes() for _, frame in frames) == raw
    for (_, expected), (_, actual) in zip(frames[8:], suffix_frames):
        assert np.array_equal(actual, expected)


def test_stopping_is_never_completion_even_at_reported_count(tmp_path):
    media = media_module()
    source = clip(tmp_path)
    identity = media.inspect_source(str(source))
    with media.FrameStream(identity, start_frame=0) as reader:
        for index in range(18):
            assert reader.read()[0] == index
        assert reader.next_frame == 18
        assert reader.completed is False
    assert reader.completed is False


def test_slow_reader_keeps_every_decoder_timestamp(tmp_path):
    import time

    media = media_module()
    identity = media.inspect_source(str(clip(tmp_path, count=28)))
    with media.FrameStream(identity) as reader:
        for index in range(identity.total_frames):
            assert reader.read()[0] == index
            time.sleep(.08)
        assert reader.read() is None
        assert reader.completed


@pytest.mark.parametrize('reported', [17, 19])
def test_contradictory_reported_count_fails_instead_of_certifying(tmp_path, reported):
    media = media_module()
    source = clip(tmp_path)
    identity = replace(media.inspect_source(str(source)), total_frames=reported)
    with pytest.raises(media.FrameEvidenceError, match='frame count'):
        read_all(media.FrameStream(identity, start_frame=8))


def test_corrupted_media_and_unsupported_video_fail_closed(tmp_path):
    media = media_module()
    source = clip(tmp_path)
    identity = media.inspect_source(str(source))
    data = source.read_bytes()
    source.write_bytes(data[:len(data) // 2])
    with pytest.raises(media.FrameEvidenceError):
        read_all(media.FrameStream(identity, start_frame=0))
    unsupported = tmp_path / 'no-video.txt'
    unsupported.write_text('not a video')
    with pytest.raises(media.FrameEvidenceError, match='MP4|probe'):
        media.inspect_source(str(unsupported))


def test_fractional_cfr_seek_does_not_round_away_anchor(tmp_path):
    media = media_module()
    source = clip(tmp_path, rate='30000/1001', count=32)
    identity = media.inspect_source(str(source))
    with media.FrameStream(identity, start_frame=18) as stream:
        assert stream.read()[0] == 18
        assert stream.read()[0] == 19
        assert not stream.completed



def test_missing_frame_timestamp_does_not_hang_while_decoder_is_writing(tmp_path, monkeypatch):
    import sys
    import time
    media = media_module()
    source = clip(tmp_path)
    identity = media.inspect_source(str(source))
    fake_bin = tmp_path / 'fake-bin'
    fake_bin.mkdir()
    decoder = fake_bin / 'ffmpeg'
    decoder.write_text(
        '#!' + sys.executable + '\n'
        'import sys, time\n'
        'sys.stdout.buffer.write(b"\\x00" * (96 * 64 * 3))\n'
        'sys.stdout.buffer.flush()\n'
        'time.sleep(2)\n')
    decoder.chmod(0o755)
    monkeypatch.setenv('PATH', str(fake_bin) + os.pathsep + os.environ.get('PATH', ''))
    monkeypatch.setattr(media, '_METADATA_TIMEOUT', 0.2, raising=False)
    started = time.monotonic()
    with pytest.raises(media.FrameEvidenceError, match='timestamp'):
        with media.FrameStream(identity) as reader:
            reader.read()
    assert time.monotonic() - started < 1.0


def test_source_replaced_after_probe_is_rejected_before_decoding(tmp_path):
    media = media_module()
    source = clip(tmp_path)
    identity = media.inspect_source(str(source))
    replacement_dir = tmp_path / 'replacement'
    replacement_dir.mkdir()
    other = clip(replacement_dir, count=18, rate='12')
    os.replace(other, source)
    with pytest.raises(media.FrameEvidenceError, match='source.*changed'):
        with media.FrameStream(identity) as reader:
            reader.read()


def test_source_replaced_during_scan_invalidates_paused_evidence(tmp_path):
    media = media_module()
    source = clip(tmp_path)
    identity = media.inspect_source(str(source))
    replacement_dir = tmp_path / 'replacement'
    replacement_dir.mkdir()
    other = clip(replacement_dir, count=18, rate='12')
    with pytest.raises(media.FrameEvidenceError, match='source.*changed'):
        with media.FrameStream(identity) as reader:
            assert reader.read()[0] == 0
            os.replace(other, source)


def test_partial_raw_frame_stall_times_out_and_reaps_decoder(tmp_path, monkeypatch):
    import sys
    import time
    media = media_module()
    source = clip(tmp_path)
    identity = media.inspect_source(str(source))
    decoder = tmp_path / 'stall.py'
    decoder.write_text('import sys, time\n'
                       'sys.stdout.buffer.write(b"x" * 100)\n'
                       'sys.stdout.buffer.flush()\n'
                       'time.sleep(2)\n')
    original = subprocess.Popen
    children = []
    def launch(command, *args, **kwargs):
        process = original([sys.executable, '-u', str(decoder)], *args, **kwargs)
        children.append(process)
        return process
    monkeypatch.setattr(media.subprocess, 'Popen', launch)
    monkeypatch.setattr(media, '_FRAME_TIMEOUT', .2, raising=False)
    start = time.monotonic()
    with pytest.raises(media.FrameEvidenceError, match='stalled|partial'):
        with media.FrameStream(identity) as reader:
            reader.read()
    elapsed = time.monotonic() - start
    assert elapsed < 1.0, 'a partial raw frame blocked the scanner until the decoder exited'
    assert len(children) == 1 and children[0].poll() is not None
    assert children[0].stdout.closed and children[0].stderr.closed


@pytest.mark.parametrize('stall', ['metadata', 'exit'])
def test_cancel_unblocks_metadata_and_child_exit_waits(tmp_path, monkeypatch, stall):
    import sys
    import threading
    import openscrub as core
    media = media_module()
    source = clip(tmp_path)
    identity = media.inspect_source(str(source))
    decoder = tmp_path / 'decoder.py'
    if stall == 'metadata':
        program = ('import sys, time\n'
                   'sys.stdout.buffer.write(b"x" * (96 * 64 * 3))\n'
                   'sys.stdout.buffer.flush()\n'
                   'time.sleep(2)\n')
    else:
        identity = replace(identity, total_frames=1)
        program = ('import os, sys, time\n'
                   'sys.stderr.write("[Parsed_showinfo_0 @ 0x1] config in time_base: %s/%s\\n")\n'
                   'sys.stderr.write("[Parsed_showinfo_0 @ 0x1] n: 0 pts: 0 s:96x64\\n")\n'
                   'sys.stderr.flush()\n'
                   'sys.stdout.buffer.write(b"x" * (96 * 64 * 3))\n'
                   'sys.stdout.buffer.flush()\n'
                   'os.close(sys.stdout.fileno())\n'
                   'time.sleep(2)\n') % (identity.time_base.numerator, identity.time_base.denominator)
    decoder.write_text(program)
    original = subprocess.Popen
    children = []
    def launch(command, *args, **kwargs):
        process = original([sys.executable, '-u', str(decoder)], *args, **kwargs)
        children.append(process)
        return process
    monkeypatch.setattr(media.subprocess, 'Popen', launch)
    cancelled = threading.Event()
    def check_cancelled():
        if cancelled.is_set():
            raise core.PipelineCancelled()
    timer = threading.Timer(.2, cancelled.set)
    try:
        with pytest.raises(core.PipelineCancelled):
            with media.FrameStream(identity, check_cancelled=check_cancelled) as reader:
                if stall == 'exit':
                    assert reader.read()[0] == 0
                timer.start()
                reader.read()
    finally:
        timer.cancel()
    assert len(children) == 1 and children[0].poll() is not None
    assert children[0].stdout.closed and children[0].stderr.closed
    assert not reader._raw_thread.is_alive() and not reader._thread.is_alive()


def test_unread_pipe_data_is_bounded_and_workers_stop(tmp_path, monkeypatch):
    import sys
    import time
    media = media_module()
    source = clip(tmp_path)
    identity = media.inspect_source(str(source))
    decoder = tmp_path / 'flood.py'
    decoder.write_text(
        'import sys\n'
        'sys.stderr.write("[Parsed_showinfo_0 @ 0x1] config in time_base: %s/%s\\n")\n'
        'sys.stderr.flush()\n'
        'for i in range(1000):\n'
        ' sys.stderr.write("[Parsed_showinfo_0 @ 0x1] n: %%d pts: %%d s:96x64\\n" %% (i,i*%d))\n'
        ' sys.stderr.flush()\n'
        ' sys.stdout.buffer.write(b"x" * (96 * 64 * 3))\n'
        ' sys.stdout.buffer.flush()\n' % (identity.time_base.numerator,
                                           identity.time_base.denominator,
                                           int(1 / identity.fps / identity.time_base)))
    original = subprocess.Popen
    children = []
    def launch(command, *args, **kwargs):
        process = original([sys.executable, '-u', str(decoder)], *args, **kwargs)
        children.append(process)
        return process
    monkeypatch.setattr(media.subprocess, 'Popen', launch)
    with media.FrameStream(identity) as reader:
        assert reader.read()[0] == 0
        time.sleep(.15)  # let the producer run ahead until its bounded queues fill
        assert reader._frames.qsize() <= 1
        assert reader._info.qsize() <= 8
    assert len(children) == 1 and children[0].poll() is not None
    assert children[0].stdout.closed and children[0].stderr.closed
    assert not reader._raw_thread.is_alive() and not reader._thread.is_alive()


@pytest.mark.skipif(os.name == 'nt', reason='POSIX signal behavior')
def test_cancel_kills_decoder_that_ignores_termination(tmp_path, monkeypatch):
    import sys
    import threading
    import time
    import openscrub as core
    media = media_module()
    source = clip(tmp_path)
    identity = media.inspect_source(str(source))
    ready = tmp_path / 'ready'
    decoder = tmp_path / 'ignore_term.py'
    decoder.write_text('import signal, sys, time\n'
                       'signal.signal(signal.SIGTERM, signal.SIG_IGN)\n'
                       'open(%r, "w").close()\n'
                       'sys.stdout.buffer.write(b"x" * 100)\n'
                       'sys.stdout.buffer.flush()\n'
                       'time.sleep(10)\n' % str(ready))
    original = subprocess.Popen
    children = []
    def launch(command, *args, **kwargs):
        process = original([sys.executable, '-u', str(decoder)], *args, **kwargs)
        children.append(process)
        return process
    monkeypatch.setattr(media.subprocess, 'Popen', launch)
    cancelled = threading.Event()
    def check_cancelled():
        if cancelled.is_set():
            raise core.PipelineCancelled()
    with pytest.raises(core.PipelineCancelled):
        with media.FrameStream(identity, check_cancelled=check_cancelled) as reader:
            deadline = time.monotonic() + 3
            while not ready.exists() and time.monotonic() < deadline:
                time.sleep(.01)
            assert ready.exists()
            timer = threading.Timer(.2, cancelled.set)
            timer.start()
            reader.read()
    timer.join()
    assert len(children) == 1 and children[0].poll() is not None
    assert children[0].stdout.closed and children[0].stderr.closed
    assert not reader._raw_thread.is_alive() and not reader._thread.is_alive()
