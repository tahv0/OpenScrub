"""Owned renderer handles remain observable through retained exceptions.

Harness containment runs only after production assertions; no GC dependency.
"""
from contextlib import contextmanager
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys

import pytest

import openscrub as app


class Sentinel(RuntimeError):
    pass


@pytest.fixture
def source(tmp_path):
    if not shutil.which('ffmpeg'):
        pytest.skip('ffmpeg required')
    path = tmp_path / 'input.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
                    'color=c=blue:s=64x64:r=3:d=1', '-c:v', 'mpeg4', str(path)],
                   check=True, capture_output=True, timeout=30)
    return path


@contextmanager
def owners(monkeypatch, failure=None):
    caps, writers, children, files = [], [], [], []
    real_cap, real_writer = app.cv2.VideoCapture, app.cv2.VideoWriter
    real_popen, real_file = subprocess.Popen, app.tempfile.TemporaryFile
    sentinel = Sentinel(failure)

    class Capture:
        def __init__(self, *args, **kwargs):
            self.actual = real_cap(*args, **kwargs)
            caps.append(self)

        def __getattr__(self, name):
            return getattr(self.actual, name)

        def get(self, prop):
            if failure == 'metadata':
                raise sentinel
            return self.actual.get(prop)

        def release(self):
            self.actual.release()
            if failure in ('release', 'cancel-release'):
                raise OSError('capture cleanup sentinel')

    def writer(*args, **kwargs):
        obj = real_writer(*args, **kwargs)
        writers.append(obj)
        return obj

    class Child(real_popen):
        def __init__(self, args, *a, **kw):
            owned = 'pipe:0' in args or 'pipe:1' in args
            if failure == 'spawn' and 'pipe:0' in args:
                raise sentinel
            self.owned = owned
            self.waited = []
            self.wait_timeouts = []
            super().__init__(args, *a, **kw)
            if owned:
                children.append(self)

        def wait(self, *args, **kwargs):
            if (failure == 'wait' and self.owned and 'pipe:0' in self.args
                    and not args and not kwargs):
                raise sentinel
            rc = super().wait(*args, **kwargs)
            self.waited.append(rc)
            self.wait_timeouts.append(kwargs.get("timeout"))
            return rc

    def temporary(*args, **kwargs):
        obj = real_file(*args, **kwargs)
        files.append(obj)
        return obj

    with monkeypatch.context() as patch:
        patch.setattr(app.cv2, 'VideoCapture', Capture)
        patch.setattr(app.cv2, 'VideoWriter', writer)
        patch.setattr(app.subprocess, 'Popen', Child)
        patch.setattr(app.tempfile, 'TemporaryFile', temporary)
        try:
            yield caps, writers, children, files, sentinel
        finally:
            # Kill/reap before closing buffered pipes even when a RED fails.
            for child in children:
                if child.poll() is None:
                    child.kill()
                child.wait(timeout=5)
                for name in ('stdin', 'stdout', 'stderr'):
                    stream = getattr(child, name)
                    if stream is not None:
                        try:
                            stream.close()
                        except OSError:
                            pass
            for cap in caps:
                cap.actual.release()
            for obj in writers:
                obj.release()
            for obj in files:
                obj.close()


def assert_closed(observed):
    caps, writers, children, files, _ = observed
    assert caps and all(not cap.isOpened() for cap in caps)
    assert all(not obj.isOpened() for obj in writers)
    for child in children:
        assert child.returncode is not None and child.waited
        if os.name == 'posix':
            with pytest.raises(ChildProcessError):
                os.waitpid(child.pid, os.WNOHANG)
        for name in ('stdin', 'stdout', 'stderr'):
            stream = getattr(child, name)
            assert stream is None or stream.closed
    assert all(obj.closed for obj in files)


def render(kind, source, output, cb, **kwargs):
    common = (str(source), str(output), [], [(0, 0)] * 3,
              [(0, 0)] * 3, 3.0, 0, 'box')
    if kind == 'hdr':
        return app.render_hdr(*common, 'libx265', {}, cb=cb, **kwargs)
    return app.render(*common, False, encoder='x264', cb=cb, **kwargs)


@pytest.mark.parametrize(('kind', 'failure'), [
    (kind, failure)
    for kind, failures in [
        ('sdr', ['success', 'metadata', 'callback', 'final', 'spawn', 'wait',
                 'release', 'cancel', 'cancel-release']),
        ('hdr', ['success', 'metadata', 'callback', 'final', 'spawn', 'wait',
                 'release', 'cancel', 'log']),
        ('fallback', ['success', 'metadata', 'callback', 'final', 'release',
                      'cancel', 'cancel-release']),
    ]
    for failure in failures
])
def test_owned_resources_across_render_lifetime(kind, failure, source,
                                                tmp_path, monkeypatch):
    """Missing any setup/frame/finally release is visible before harness cleanup."""
    output = tmp_path / 'output.mp4'
    if failure in ('metadata', 'spawn'):
        output.write_bytes(b'previous untouched output')
    if kind == 'fallback':
        monkeypatch.setattr(app, 'nvenc_available', lambda *a: None)
    held = []
    with owners(monkeypatch, failure) as observed:
        sentinel = observed[-1]

        class Callbacks(app.Callbacks):
            final_hits = 0

            def log(self, text):
                if failure == 'log' and 'HDR preserved' in text:
                    raise sentinel

            def cancelled(self):
                return failure in ('cancel', 'cancel-release')

            def progress(self, stage, done, total):
                if failure in ('callback', 'release') and done == 1:
                    raise sentinel
                if done == total:
                    self.final_hits += 1
                    if failure == 'final' and self.final_hits == 2:
                        raise sentinel

        try:
            render(kind, source, output, Callbacks(), progress_every=1)
        except BaseException as error:
            held.append(error)
        if failure == 'success':
            assert not held
            cap = app.cv2.VideoCapture(str(output))
            try:
                assert cap.isOpened()
                assert int(cap.get(app.cv2.CAP_PROP_FRAME_COUNT)) == 3
            finally:
                cap.release()
            for child in observed[2]:
                assert None in child.wait_timeouts  # normal finalization has no deadline
        else:
            assert len(held) == 1
            assert held[0].__traceback__ is not None
            if failure in ('cancel', 'cancel-release'):
                assert type(held[0]) is app.PipelineCancelled
                assert not output.exists()
            elif failure == 'release' and kind == 'hdr':
                assert str(held[0]) == 'capture cleanup sentinel'
            else:
                assert held[0] is sentinel
            if failure in ('release', 'cancel-release'):
                assert 'capture cleanup sentinel' in ' '.join(
                    held[0].render_cleanup_errors)
            if failure in ('metadata', 'spawn'):
                assert output.read_bytes() == b'previous untouched output'
        assert_closed(observed)


@pytest.mark.parametrize('kind', ['sdr', 'hdr'])
def test_encoder_error_keeps_stderr_and_closes_owners(kind, source, tmp_path,
                                                      monkeypatch):
    """Real FFmpeg rejects its task-owned destination; retain diagnostic and IO."""
    output = tmp_path / 'missing-directory' / 'output.mp4'
    held = []
    with owners(monkeypatch) as observed:
        try:
            render(kind, source, output, app.Callbacks())
        except BaseException as error:
            held.append(error)
        assert len(held) == 1
        assert isinstance(held[0], RuntimeError)
        assert 'encode' in str(held[0])
        assert ('No such file or directory' in str(held[0])
                or 'Error opening output' in str(held[0]))
        assert_closed(observed)


def test_failed_writer_is_released_without_deleting_previous(source, tmp_path,
                                                             monkeypatch):
    """A real failed-open VideoWriter must fail instead of replacing the output."""
    monkeypatch.setattr(app, 'nvenc_available', lambda *a: None)
    output = tmp_path / 'previous.mp4'
    output.write_bytes(b'previous')
    # The exact fallback destination cannot open because it is a directory.
    Path(str(output) + '.noaudio.mp4').mkdir()
    with owners(monkeypatch) as observed:
        with pytest.raises(RuntimeError, match='writer|Writer|output') as held:
            render('fallback', source, output, app.Callbacks())
        assert held.value.__traceback__ is not None
        assert output.read_bytes() == b'previous'
        assert_closed(observed)


@pytest.mark.parametrize('kind', ['sdr', 'hdr'])
def test_nonzero_final_encoder_wait_retains_stderr(kind, tmp_path, monkeypatch):
    """Sub-buffer frames reach EOF before FFmpeg rejects its output path."""
    src = tmp_path / 'small.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
                    'color=c=blue:s=16x16:r=3:d=1', '-c:v', 'mpeg4', str(src)],
                   check=True, capture_output=True, timeout=30)
    output = tmp_path / 'missing' / 'output.mp4'
    progress = []

    class Callbacks(app.Callbacks):
        def progress(self, stage, done, total):
            progress.append(done)

    with owners(monkeypatch) as observed:
        with pytest.raises(RuntimeError, match='encode.*failed') as held:
            render(kind, src, output, Callbacks(), progress_every=1)
        assert progress == [1, 2, 3, 3]
        assert 'No such file or directory' in str(held.value)
        enc, = [p for p in observed[2] if 'pipe:0' in p.args]
        assert enc.waited[0] != 0
        # The diagnostic is raised at final wait, outside the write handler.
        assert not isinstance(held.value.__context__, BrokenPipeError)
        assert_closed(observed)


@pytest.mark.parametrize('cleanup_failure', [None, 'wait', 'terminate'])
def test_abort_kills_and_reaps_only_owned_stubborn_child(
        tmp_path, monkeypatch, cleanup_failure):
    """Bounded fallback begins after Python control; this is no native watchdog."""
    if os.name != 'posix':
        pytest.skip('SIGTERM handler requires POSIX')
    child = subprocess.Popen([
        sys.executable, '-c',
        'import signal,sys,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); '
        'print("ready", flush=True); time.sleep(30)'],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    try:
        while True:
            line = child.stdout.readline()
            assert line, 'owned child exited before readiness'
            if line == b'ready\n':
                break
        actual_wait = child.wait
        injected = []

        def wait(*args, **kwargs):
            if cleanup_failure == 'wait' and not injected:
                injected.append(True)
                raise OSError('shutdown sentinel')
            return actual_wait(*args, **kwargs)

        def terminate():
            raise OSError('shutdown sentinel')

        monkeypatch.setattr(child, 'wait', wait)
        if cleanup_failure == 'terminate':
            monkeypatch.setattr(child, 'terminate', terminate)
        errors = app._stop_render_children((child,))
        if cleanup_failure is None:
            assert not errors
        else:
            assert any('shutdown sentinel' in str(e) for e in errors)
        assert child.returncode == -signal.SIGKILL
        with pytest.raises(ChildProcessError):
            os.waitpid(child.pid, os.WNOHANG)
        assert child.stdin.closed and child.stdout.closed
    finally:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=5)
        child.stdin.close()
        child.stdout.close()


@pytest.mark.parametrize('kind', ['sdr', 'hdr'])
@pytest.mark.parametrize('primary', [False, True])
def test_stderr_close_failure_preserves_primary_or_fails_success(
        kind, primary, source, tmp_path, monkeypatch, request):
    """Final close failure fails success and cannot mask a callback sentinel."""
    actual_file = app.tempfile.TemporaryFile
    files = []
    sentinel = Sentinel('callback primary')

    class ErrorFile:
        def __init__(self):
            self.actual = actual_file()
            files.append(self)
            request.addfinalizer(self.actual.close)  # containment after assertions

        def __getattr__(self, name):
            return getattr(self.actual, name)

        def close(self):
            self.actual.close()
            raise OSError('stderr close sentinel')

    class Callbacks(app.Callbacks):
        def progress(self, stage, done, total):
            if primary:
                raise sentinel

    with owners(monkeypatch) as observed:
        monkeypatch.setattr(app.tempfile, 'TemporaryFile', ErrorFile)
        with pytest.raises((Sentinel, OSError)) as held:
            render(kind, source, tmp_path / 'out.mp4', Callbacks())
        if primary:
            assert held.value is sentinel
            assert 'stderr close sentinel' in ' '.join(
                held.value.render_cleanup_errors)
        else:
            assert str(held.value) == 'stderr close sentinel'
        assert files and all(obj.closed for obj in files)
        assert_closed(observed)
