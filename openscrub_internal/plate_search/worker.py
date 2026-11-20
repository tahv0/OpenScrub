"""Short-lived, job-owned subprocess for one exact-frame OCR lookup.

The query travels only through stdin. The child never imports the web app and
returns geometry/match kinds, not recognized text or the supplied query.
"""
import json
import os
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


def _stop(process):
    # The child starts a private POSIX session; kill OCR descendants too.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    try:
        process.communicate(timeout=3)
    except subprocess.TimeoutExpired:
        # Keep the caller's file lease until the child has actually exited.
        process.wait()


def run(payload, job_directory, cancelled, timeout=SEARCH_DEADLINE):
    if os.name != 'posix' or getattr(sys, 'frozen', False):
        raise WorkerFailed('isolated plate search is unavailable on this platform')
    deadline = time.monotonic() + timeout
    app_directory = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    request_bytes = json.dumps(payload, ensure_ascii=True, separators=(',', ':')).encode('ascii')
    with tempfile.TemporaryDirectory(prefix='.plate-search-', dir=job_directory) as directory:
        env = dict(os.environ)
        env.update(TMPDIR=directory, TMP=directory, TEMP=directory, OMP_NUM_THREADS='1',
                   OMP_THREAD_LIMIT='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1')
        process = None
        try:
            if cancelled():
                raise WorkerCancelled()
            process = subprocess.Popen([sys.executable, '-m', 'openscrub_internal.plate_search.worker', '--child'],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                cwd=app_directory, env=env, start_new_session=True)
            first = True
            while True:
                if cancelled():
                    raise WorkerCancelled()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise WorkerTimedOut()
                try:
                    output, _ = process.communicate(input=request_bytes if first else None,
                                                    timeout=min(.1, remaining))
                    break
                except subprocess.TimeoutExpired:
                    first = False
            if cancelled():
                raise WorkerCancelled()
            if process.returncode != 0 or len(output) > MAX_RESPONSE:
                raise WorkerFailed()
            try:
                return json.loads(output)
            except (ValueError, UnicodeError):
                raise WorkerFailed() from None
        except (OSError, subprocess.SubprocessError):
            raise WorkerFailed() from None
        finally:
            if process is not None and process.poll() is None:
                _stop(process)


def _stamp(value):
    return [value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns]


def _child(payload):
    import cv2
    from openscrub_internal import exact_samples
    from .matching import normalize_queries
    from .search import search_frame

    cv2.setNumThreads(1)
    queries = normalize_queries(payload['query'], mode=payload['mode'])
    path, expected = payload['path'], payload['stamp']
    with open(path, 'rb') as source:
        if _stamp(os.fstat(source.fileno())) != expected:
            raise WorkerFailed()
        capture = cv2.VideoCapture(path)
        try:
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
