"""Frame evidence for a deliberately narrow checkpoint-scan source.

This module does not publish checkpoints.  Its caller must hold the source
stable throughout the attempt, bind the source and scan settings to the
portable checkpoint identity, and combine the observed frame range with the
already-accounted prefix.  A successful suffix stream alone is not evidence
that the prefix was scanned.
"""
import json
import os
import queue
import re
import subprocess
import stat
import threading
import time
from dataclasses import dataclass
from fractions import Fraction

import numpy as np


class FrameEvidenceError(RuntimeError):
    """The selected source cannot supply an unambiguous frame timeline."""


@dataclass(frozen=True)
class Source:
    path: str
    width: int
    height: int
    fps: Fraction
    time_base: Fraction
    total_frames: int
    sha256: str
    file_stat: tuple
    count_verified: bool = False


def _fraction(value, name):
    try:
        result = Fraction(value)
    except (TypeError, ValueError, ZeroDivisionError):
        raise FrameEvidenceError('invalid MP4 %s; use a CFR H.264 source' % name) from None
    if result <= 0:
        raise FrameEvidenceError('invalid MP4 %s; use a CFR H.264 source' % name)
    return result


def _source_hash(path):
    # Use the engine's existing streaming fingerprint owner.  Import lazily
    # so the engine can import this module without a circular import.
    from openscrub import sha256_file
    try:
        return sha256_file(path)
    except OSError as exc:
        raise FrameEvidenceError('checkpoint source changed or is unavailable') from exc


def _stat_tuple(value):
    if not stat.S_ISREG(value.st_mode):
        raise FrameEvidenceError('checkpoint source must be a regular file')
    return (value.st_dev, value.st_ino, value.st_size,
            value.st_mtime_ns, value.st_ctime_ns)


def _path_stat(path):
    try:
        return _stat_tuple(os.stat(path))
    except OSError as exc:
        raise FrameEvidenceError('checkpoint source changed or is unavailable') from exc


def _check_source(source):
    if _path_stat(source.path) != source.file_stat:
        raise FrameEvidenceError('checkpoint source changed; start a fresh scan')


class SourceLease:
    """Hold a descriptor and detect ordinary replacement or mutation.

    External writers still require operation-level exclusion: a stat fence
    is not a mandatory operating-system write lock.
    """
    def __init__(self, source):
        self.source = source
        self._file = None

    def __enter__(self):
        try:
            self._file = open(self.source.path, 'rb')
            self.check()
            return self
        except BaseException:
            if self._file is not None:
                self._file.close()
            raise

    def check(self):
        _check_source(self.source)
        if _stat_tuple(os.fstat(self._file.fileno())) != self.source.file_stat:
            raise FrameEvidenceError('checkpoint source changed during the scan')

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type is None:
                self.check()
        finally:
            self._file.close()


def inspect_source(path):
    """Probe a single-track, progressive, 8-bit H.264 MP4.

    The returned count is only the container's report.  Exact PTS and a clean
    decoder termination are established by FrameStream as frames are read.
    """
    path = os.path.abspath(os.fspath(path))
    source_stat = _path_stat(path)
    digest = _source_hash(path)
    if _path_stat(path) != source_stat:
        raise FrameEvidenceError('checkpoint source changed during hashing')
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries',
             'format=format_name:stream=index,codec_type,codec_name,width,height,'
             'pix_fmt,r_frame_rate,avg_frame_rate,time_base,start_pts,nb_frames,'
             'field_order:stream_tags=rotate:stream_side_data_list',
             '-of', 'json', path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        if result.returncode:
            detail = (result.stderr or b'')[:2000].decode('utf-8', errors='replace').strip()
            raise ValueError('ffprobe exited %s%s'
                             % (result.returncode, ': ' + detail if detail else ''))
        data = json.loads(result.stdout)
        if 'mp4' not in data['format']['format_name'].split(','):
            raise ValueError('not an MP4-family container')
        videos = [s for s in data['streams'] if s.get('codec_type') == 'video']
        if len(videos) != 1:
            raise ValueError('select a source with exactly one video track')
        video = videos[0]
        if (video.get('codec_name') != 'h264' or video.get('pix_fmt') != 'yuv420p'
                or video.get('field_order') != 'progressive'):
            raise ValueError('only progressive 8-bit H.264 yuv420p is supported')
        if video.get('tags', {}).get('rotate') or video.get('side_data_list'):
            raise ValueError('rotated video is not supported')
        width, height = int(video['width']), int(video['height'])
        count = int(video['nb_frames'])
        if (not 0 < width <= 8192 or not 0 < height <= 8192 or
                width % 2 or height % 2 or not 0 < count <= (1 << 53) - 1 or
                video.get('start_pts') != 0):
            raise ValueError('unsupported size, start timestamp, or reported frame count')
        fps = _fraction(video['r_frame_rate'], 'frame rate')
        if fps != _fraction(video['avg_frame_rate'], 'average frame rate') or fps > 240:
            raise ValueError('frame rates disagree or exceed 240 fps')
        time_base = _fraction(video['time_base'], 'time base')
        if (Fraction(1, 1) / fps / time_base).denominator != 1:
            raise ValueError('frame rate does not map to integral source timestamps')
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise FrameEvidenceError('cannot probe supported MP4 source: %s' % exc) from exc
    if _path_stat(path) != source_stat:
        raise FrameEvidenceError('checkpoint source changed during probing')
    return Source(path, width, height, fps, time_base, count, digest, source_stat)


_SHOWINFO = re.compile(
    r'^\[Parsed_showinfo_\d+ @ 0x[0-9a-fA-F]+\] n:\s*(\d+)\s+pts:\s*(-?\d+)'
    r'.*?\bs:(\d+)x(\d+)\b')
_TIME_BASE = re.compile(
    r'^\[Parsed_showinfo_\d+ @ 0x[0-9a-fA-F]+\] config in time_base: (\d+)/(\d+)')
_END = object()
_METADATA_TIMEOUT = 5.0
_FRAME_TIMEOUT = 30.0
_PIPE_POLL = 0.1
_MAX_LOG_LINE = 65536


class FrameStream:
    """Decode one sequential range and verify its absolute source PTS.

    Only EOF plus a successful FFmpeg exit and the exact reported count set
    ``completed``. A caller stopping after the last expected frame has not
    observed termination and must not promote the count. Owned pipe workers use
    bounded queues so an incomplete raw frame has a finite wait and cleanup.
    """
    def __init__(self, source, start_frame=0, *, check_cancelled=None):
        if check_cancelled is not None and not callable(check_cancelled):
            raise TypeError('check_cancelled must be callable')
        if (type(start_frame) is not int or not 0 <= start_frame < source.total_frames):
            raise FrameEvidenceError('start frame must be inside the reported timeline')
        self.source = source
        self.check_cancelled = check_cancelled or (lambda: None)
        self.start_frame = start_frame
        self.next_frame = start_frame
        self.completed = False
        self._proc = None
        self._thread = None
        self._raw_thread = None
        self._stop_workers = threading.Event()
        # At most one raw frame waits in the queue; the raw worker can hold
        # one additional frame while it waits to hand it over.
        self._frames = queue.Queue(maxsize=1)
        self._info = queue.Queue(maxsize=8)
        self._last_index = None
        self._showinfo_number = 0
        self._time_base = None
        self._closed = False

    def __enter__(self):
        _check_source(self.source)
        # Seeking a frame before the requested overlap leaves a whole-frame
        # margin against FFmpeg's microsecond seek rounding.  Only the exact
        # requested index and later are returned to semantic analysis.
        preceding = max(0, self.start_frame - 1)
        us = (preceding * 1000000 * self.source.fps.denominator
              // self.source.fps.numerator)
        # Progress records use carriage returns and can prefix a showinfo line.
        cmd = ['ffmpeg', '-hide_banner', '-loglevel', 'info', '-nostats', '-nostdin',
               '-xerror', '-err_detect', 'explode', '-copyts']
        if us:
            cmd += ['-ss', '%d.%06d' % (us // 1000000, us % 1000000)]
        cmd += ['-noautorotate', '-i', self.source.path, '-map', '0:v:0',
                '-vf', 'showinfo', '-fps_mode', 'passthrough',
                '-f', 'rawvideo', '-pix_fmt', 'bgr24', 'pipe:1']
        try:
            self._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                          stderr=subprocess.PIPE, stdin=subprocess.DEVNULL)
        except OSError as exc:
            raise FrameEvidenceError('cannot start FFmpeg frame decoder: %s' % exc) from exc
        self._thread = threading.Thread(target=self._read_info, daemon=True,
                                        name='checkpoint-ffmpeg-metadata')
        self._raw_thread = threading.Thread(target=self._read_raw, daemon=True,
                                            name='checkpoint-ffmpeg-frames')
        try:
            self._thread.start()
            self._raw_thread.start()
        except BaseException:
            self.close()
            raise
        return self

    def _offer(self, destination, item):
        while not self._stop_workers.is_set():
            try:
                destination.put(item, timeout=_PIPE_POLL)
                return True
            except queue.Full:
                pass
        return False

    def _read_raw(self):
        frame_size = self.source.width * self.source.height * 3
        try:
            while not self._stop_workers.is_set():
                frame = self._proc.stdout.read(frame_size)
                if not self._offer(self._frames, ('data', frame)):
                    return
                if len(frame) != frame_size:
                    return
        except Exception as exc:
            self._offer(self._frames, ('error', exc))

    def _read_info(self):
        try:
            while not self._stop_workers.is_set():
                raw = self._proc.stderr.readline(_MAX_LOG_LINE + 1)
                if not raw:
                    break
                if len(raw) > _MAX_LOG_LINE:
                    self._offer(self._info, ('error', 'decoder metadata line is too long'))
                    break
                line = raw.decode('utf-8', 'replace').strip()
                match = _TIME_BASE.match(line)
                if match:
                    if not self._offer(self._info, ('base', match.groups())):
                        return
                    continue
                match = _SHOWINFO.match(line)
                if match and not self._offer(self._info, ('frame', match.groups())):
                    return
        finally:
            self._offer(self._info, (_END, ()))

    def _take(self, values, deadline, message):
        while True:
            self.check_cancelled()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise FrameEvidenceError(message)
            try:
                return values.get(timeout=min(_PIPE_POLL, remaining))
            except queue.Empty:
                pass

    def _wait_child(self):
        deadline = time.monotonic() + _FRAME_TIMEOUT
        while True:
            self.check_cancelled()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise FrameEvidenceError('FFmpeg decoder stalled before termination')
            try:
                return self._proc.wait(timeout=min(_PIPE_POLL, remaining))
            except subprocess.TimeoutExpired:
                pass

    def _wait_metadata_reader(self):
        deadline = time.monotonic() + _METADATA_TIMEOUT
        while self._thread.is_alive():
            self.check_cancelled()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise FrameEvidenceError('FFmpeg metadata reader did not terminate')
            self._thread.join(timeout=min(_PIPE_POLL, remaining))

    def _frame_info(self):
        # showinfo runs before FFmpeg writes the corresponding raw frame.  A
        # missing/unrecognized line must not wait for EOF: FFmpeg may itself
        # be blocked writing the next frame while we wait for its metadata.
        deadline = time.monotonic() + _METADATA_TIMEOUT
        while True:
            kind, values = self._take(
                self._info, deadline,
                'decoder did not provide a timestamp for a decoded frame')
            if kind is _END:
                raise FrameEvidenceError('decoder did not provide a timestamp for a decoded frame')
            if kind == 'error':
                raise FrameEvidenceError(values)
            if kind == 'base':
                try:
                    base = Fraction(int(values[0]), int(values[1]))
                except (ValueError, ZeroDivisionError):
                    raise FrameEvidenceError('invalid decoder timestamp base') from None
                if self._time_base is not None and self._time_base != base:
                    raise FrameEvidenceError('decoder timestamp base changed during the scan')
                self._time_base = base
                continue
            n, pts, width, height = map(int, values)
            if (self._time_base != self.source.time_base or n != self._showinfo_number
                    or (width, height) != (self.source.width, self.source.height)):
                raise FrameEvidenceError('decoder frame metadata changed or is incomplete')
            self._showinfo_number += 1
            index = pts * self._time_base * self.source.fps
            if index.denominator != 1 or index < 0:
                raise FrameEvidenceError('source has a non-CFR or invalid frame timestamp')
            index = int(index)
            if self._last_index is not None and index != self._last_index + 1:
                raise FrameEvidenceError('source frame timestamps are not consecutive')
            self._last_index = index
            return index

    def read(self):
        if self._proc is None or self._closed:
            raise FrameEvidenceError('frame stream is not open')
        if self.completed:
            return None
        frame_size = self.source.width * self.source.height * 3
        while True:
            kind, data = self._take(
                self._frames, time.monotonic() + _FRAME_TIMEOUT,
                'FFmpeg decoder stalled while reading a raw frame')
            if kind == 'error':
                raise FrameEvidenceError('cannot read FFmpeg raw frame') from data
            if not data:
                rc = self._wait_child()
                self._wait_metadata_reader()
                if rc != 0:
                    raise FrameEvidenceError('FFmpeg decoding failed before clean completion')
                if self.next_frame != self.source.total_frames:
                    raise FrameEvidenceError('decoded frame count differs from the reported frame count')
                if not self._info.empty():
                    kind, _ = self._info.get()
                    if kind is not _END:
                        raise FrameEvidenceError('decoder emitted unpaired frame metadata')
                _check_source(self.source)
                self.completed = True
                return None
            if len(data) != frame_size:
                raise FrameEvidenceError('FFmpeg returned a partial raw frame')
            index = self._frame_info()
            if index >= self.source.total_frames:
                raise FrameEvidenceError('decoded frame count exceeds the reported frame count')
            if self._last_index == index and index < self.start_frame:
                continue
            if index != self.next_frame:
                raise FrameEvidenceError('decoder did not reach the requested source frame')
            self.next_frame += 1
            return index, np.frombuffer(data, dtype=np.uint8).reshape(
                self.source.height, self.source.width, 3).copy()

    def close(self):
        if self._closed:
            return
        self._closed = True
        self._stop_workers.set()
        if self._proc is None:
            return
        if self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait(timeout=3)
        for worker in (self._raw_thread, self._thread):
            if worker is not None and worker.ident is not None:
                worker.join(timeout=3)
                if worker.is_alive():
                    raise FrameEvidenceError('FFmpeg pipe reader did not terminate')
        if self._proc.stdout:
            self._proc.stdout.close()
        if self._proc.stderr:
            self._proc.stderr.close()

    def __exit__(self, exc_type, exc, tb):
        self.close()
        # Do not mask a scanner or decoder failure during cleanup.
        if exc_type is None:
            _check_source(self.source)


class ScanCapture:
    """Expose an already-open verified stream to the existing scan loop."""
    def __init__(self, stream):
        self.stream = stream

    def get(self, prop):
        import cv2
        source = self.stream.source
        return {cv2.CAP_PROP_FPS: float(source.fps),
                cv2.CAP_PROP_FRAME_COUNT: source.total_frames,
                cv2.CAP_PROP_FRAME_WIDTH: source.width,
                cv2.CAP_PROP_FRAME_HEIGHT: source.height}.get(prop, 0.0)

    def read(self):
        frame = self.stream.read()
        return (False, None) if frame is None else (True, frame[1])

    def grab(self):
        return self.stream.read() is not None

    def isOpened(self):
        return not self.stream._closed

    def release(self):
        self.stream.close()
