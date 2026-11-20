"""Short-lived, job-owned subprocess for bounded exact-frame OCR lookups.

The query travels only through stdin. The child never imports the web app and
returns geometry/match kinds, not recognized text or the supplied query.
"""
import json
import os
import selectors
import signal
import subprocess
import sys
import tempfile
import time

MAX_RESPONSE = 65536
SEARCH_DEADLINE = 15.0


class WorkerCancelled(Exception):
    pass


class WorkerTimedOut(Exception):
    pass


class WorkerFailed(Exception):
    pass


def validate_result(value, width, height, mode):
    """Validate child output before considering its process group successful."""
    if (not isinstance(value, dict) or value.get('complete') is not True
            or type(value.get('truncated')) is not bool
            or not isinstance(value.get('suggestions'), list)
            or len(value['suggestions']) > 128
            or type(width) is not int or type(height) is not int
            or width <= 0 or height <= 0 or mode not in ('full', 'fragment')):
        raise WorkerFailed()
    allowed = 'full_equal' if mode == 'full' else 'fragment'
    suggestions = []
    for row in value['suggestions']:
        if not isinstance(row, dict) or set(row) != {'box', 'match', 'boundary'}:
            raise WorkerFailed()
        box = row['box']
        if (not isinstance(box, list) or len(box) != 4
                or any(type(v) is not int for v in box)
                or not 0 <= box[0] < box[2] <= width
                or not 0 <= box[1] < box[3] <= height
                or row['match'] != allowed or row['boundary'] != 'unknown'):
            raise WorkerFailed()
        suggestions.append({'box': list(box), 'match': row['match'], 'boundary': 'unknown'})
    return suggestions


def validate_sampled_result(value, width, height, mode, indices):
    """Accept only complete, ordered results for the requested exact samples."""
    if (not isinstance(indices, list) or not 1 <= len(indices) <= 4
            or any(type(i) is not int or i < 0 for i in indices)
            or any(a >= b for a, b in zip(indices, indices[1:]))
            or not isinstance(value, dict) or value.get('complete') is not True
            or not isinstance(value.get('frames'), list) or len(value['frames']) != len(indices)):
        raise WorkerFailed()
    frames = []
    for index, frame in zip(indices, value['frames']):
        if (not isinstance(frame, dict) or set(frame) != {'index','truncated','suggestions'}
                or type(frame['index']) is not int or frame['index'] != index):
            raise WorkerFailed()
        suggestions = validate_result({'complete': True, 'truncated': frame['truncated'],
                                       'suggestions': frame['suggestions']}, width, height, mode)
        frames.append({'index': index, 'truncated': frame['truncated'], 'suggestions': suggestions})
    return frames


def _group_live(group):
    """Ignore dead zombies on Linux; otherwise wait for the group to vanish."""
    if sys.platform.startswith('linux') and os.path.isdir('/proc'):
        try:
            with os.scandir('/proc') as entries:
                for entry in entries:
                    if not entry.name.isdigit():
                        continue
                    try:
                        with open(os.path.join(entry.path, 'stat'), encoding='ascii') as stream:
                            stat = stream.read()
                        fields = stat[stat.rfind(')')+2:].split()
                        if len(fields) >= 3 and int(fields[2]) == group and fields[0] not in ('Z', 'X'):
                            return True
                    except (FileNotFoundError, ProcessLookupError):
                        continue
            return False
        except (OSError, ValueError, IndexError):
            pass
    try:
        snapshot = subprocess.run(['ps', '-axo', 'pid=,pgid=,stat='],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True, timeout=3).stdout
        for line in snapshot.splitlines():
            fields = line.split()
            if len(fields) >= 3 and int(fields[1]) == group and fields[2][:1] not in (b'Z', b'X'):
                return True
        return False
    except (OSError, subprocess.SubprocessError, ValueError):
        raise WorkerFailed() from None


def _stop(process):
    # The unreaped leader pins the private POSIX process-group ID until its
    # descendants are dead, so a recycled PID cannot name another group.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    while True:
        try:
            live = _group_live(process.pid)
        except WorkerFailed:
            # An unreadable process table is not proof the OCR child stopped.
            time.sleep(.1)
            continue
        if not live:
            break
        # Retain the caller's file lease while a killed process can still run.
        time.sleep(.01)
    process.wait()


def _exchange(process, request_bytes, cancelled, deadline):
    """Use bounded pipes and observe exit without reaping the group leader."""
    output = bytearray()
    sent = 0
    with selectors.DefaultSelector() as selector:
        os.set_blocking(process.stdin.fileno(), False)
        os.set_blocking(process.stdout.fileno(), False)
        selector.register(process.stdin, selectors.EVENT_WRITE, 'in')
        selector.register(process.stdout, selectors.EVENT_READ, 'out')
        try:
            while True:
                if cancelled():
                    raise WorkerCancelled()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise WorkerTimedOut()
                for key, _ in selector.select(min(.1, remaining)):
                    if key.data == 'in':
                        try:
                            sent += os.write(key.fd, request_bytes[sent:])
                        except BrokenPipeError:
                            raise WorkerFailed() from None
                        if sent == len(request_bytes):
                            selector.unregister(key.fileobj)
                            key.fileobj.close()
                    else:
                        chunk = os.read(key.fd, 8192)
                        if not chunk:
                            selector.unregister(key.fileobj)
                            key.fileobj.close()
                        else:
                            output.extend(chunk)
                            if len(output) > MAX_RESPONSE:
                                raise WorkerFailed()
                info = os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
                if info is not None:
                    if info.si_code != os.CLD_EXITED or info.si_status != 0 or sent != len(request_bytes):
                        raise WorkerFailed()
                    # The leader has stopped. Drain the bounded bytes already
                    # written; an open pipe now indicates a surviving child.
                    if not process.stdout.closed:
                        while True:
                            try:
                                chunk = os.read(process.stdout.fileno(), 8192)
                            except BlockingIOError:
                                raise WorkerFailed() from None
                            if not chunk:
                                break
                            output.extend(chunk)
                            if len(output) > MAX_RESPONSE:
                                raise WorkerFailed()
                    return bytes(output)
        finally:
            for stream in (process.stdin, process.stdout):
                if not stream.closed:
                    stream.close()


def run(payload, job_directory, cancelled, timeout=SEARCH_DEADLINE):
    if (os.name != 'posix' or getattr(sys, 'frozen', False)
            or not all(hasattr(os, name) for name in ('waitid', 'WNOWAIT', 'CLD_EXITED'))):
        raise WorkerFailed('isolated plate search is unavailable on this platform')
    deadline = time.monotonic() + timeout
    app_directory = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    request_bytes = json.dumps(payload, ensure_ascii=True, separators=(',', ':')).encode('ascii')
    with tempfile.TemporaryDirectory(prefix='.plate-search-', dir=job_directory) as directory:
        env = dict(os.environ)
        env.update(TMPDIR=directory, TMP=directory, TEMP=directory, OMP_NUM_THREADS='1',
                   OMP_THREAD_LIMIT='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1')
        process = None
        successful = False
        try:
            if cancelled():
                raise WorkerCancelled()
            process = subprocess.Popen([sys.executable, '-m', 'openscrub_internal.plate_search.worker', '--child'],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                cwd=app_directory, env=env, start_new_session=True)
            output = _exchange(process, request_bytes, cancelled, deadline)
            if cancelled():
                raise WorkerCancelled()
            try:
                value = json.loads(output)
                if 'indices' in payload:
                    validate_sampled_result(value, payload['width'], payload['height'], payload['mode'], payload['indices'])
                else:
                    validate_result(value, payload['width'], payload['height'], payload['mode'])
            except (KeyError, TypeError, ValueError, UnicodeError):
                raise WorkerFailed() from None
            if _group_live(process.pid):
                raise WorkerFailed()
            process.wait()
            successful = True
            return value
        except (OSError, subprocess.SubprocessError):
            raise WorkerFailed() from None
        finally:
            if process is not None and not successful:
                _stop(process)


def _stamp(value):
    return [value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns]


def _child(payload):
    import cv2
    from openscrub_internal import exact_samples
    from .matching import normalize_queries
    from .search import search_frame
    from .samples import search_capture

    cv2.setNumThreads(1)
    queries = normalize_queries(payload['query'], mode=payload['mode'])
    path, expected = payload['path'], payload['stamp']
    with open(path, 'rb') as source:
        if _stamp(os.fstat(source.fileno())) != expected:
            raise WorkerFailed()
        capture = cv2.VideoCapture(path)
        try:
            if 'indices' in payload:
                result = search_capture(capture, queries, payload['indices'], fps=payload['fps'],
                    count=payload['count'], width=payload['width'], height=payload['height'],
                    tolerance_s=payload['tolerance_s'])
                if _stamp(os.fstat(source.fileno())) != expected or _stamp(os.stat(path)) != expected:
                    raise WorkerFailed()
                return {'complete': not result.cancelled, 'frames': [
                    dict(index=frame.index, truncated=frame.truncated,
                         suggestions=[dict(box=list(hit.suggested_box), match=hit.matches[0].match_kind,
                                           boundary=hit.boundary) for hit in frame.hits])
                    for frame in result.frames]}
            frame = exact_samples.read_indexed_capture(capture, payload['index'],
                fps=payload['fps'], count=payload['count'], width=payload['width'],
                height=payload['height'], tolerance_s=payload['tolerance_s'])
        finally:
            capture.release()
        if _stamp(os.fstat(source.fileno())) != expected or _stamp(os.stat(path)) != expected:
            raise WorkerFailed()
    result = search_frame(frame.pixels, queries)
    return {'complete': result.complete, 'truncated': result.truncated,
            'suggestions': [dict(box=list(hit.suggested_box),
                                 match=hit.matches[0].match_kind, boundary=hit.boundary)
                            for hit in result.hits]}


def main():
    try:
        if sys.argv[1:] != ['--child']:
            return 2
        body = sys.stdin.buffer.read(16385)
        if len(body) > 16384:
            return 2
        payload = json.loads(body)
        result = _child(payload)
        data = json.dumps(result, separators=(',', ':'), allow_nan=False).encode('ascii')
        if len(data) > MAX_RESPONSE:
            return 2
        sys.stdout.buffer.write(data)
        return 0
    except BaseException:
        # Adapter errors can include sensitive OCR text; never echo them.
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
