"""Process-isolated known-plate OCR for Linux/Docker web installations.

The child owns video decoding, Tesseract and a private report snapshot. It
writes only bounded OCR deltas and progress into a private temporary directory.
The parent alone validates and atomically publishes report.json under the web
writer lock. Child memory pressure, crashes or cancellation cannot publish a
partially updated report or erase existing human decisions.
"""
from contextlib import suppress
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time

DEFAULT_MAX_RSS_MB = 3072
MIN_AVAILABLE_MB = 1024


def _digest_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(part)
    return digest.hexdigest()


def _rss_tree_bytes(pid):
    """Resident bytes for Linux worker and descendants (including Tesseract)."""
    seen, pending, total = set(), [pid], 0
    while pending:
        ident = pending.pop()
        if ident in seen:
            continue
        seen.add(ident)
        try:
            status = Path('/proc/%d/status' % ident).read_text()
            for line in status.splitlines():
                if line.startswith('VmRSS:'):
                    total += int(line.split()[1]) * 1024
                    break
            children = Path('/proc/%d/task/%d/children' % (ident, ident)).read_text()
            pending.extend(int(value) for value in children.split())
        except (OSError, ValueError, IndexError):
            pass  # a short-lived Tesseract child may exit while sampled
    return total


def _available_bytes():
    try:
        for line in Path('/proc/meminfo').read_text().splitlines():
            if line.startswith('MemAvailable:'):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    return None


def _rss_limit_mb():
    try:
        value = int(os.environ.get('OPENSCRUB_OCR_MAX_RSS_MB', DEFAULT_MAX_RSS_MB))
    except ValueError:
        value = DEFAULT_MAX_RSS_MB
    return max(512, min(4096, value))


def _terminate(process):
    # Even after the main child exits, a Tesseract descendant may still
    # belong to its session. Terminate the whole private process group.
    try:
        if os.name == 'posix':
            os.killpg(process.pid, signal.SIGTERM)
        elif process.poll() is None:
            process.terminate()
    except ProcessLookupError:
        return
    if process.poll() is not None:
        return
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        if os.name == 'posix':
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
        process.wait(timeout=5)


def _atomic_small_json(path, document):
    path = Path(path)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(document, separators=(',', ':')), encoding='utf-8')
    os.replace(temporary, path)


def _child_process():
    """Child entry: stdin is the only input; no private plate hints in argv."""
    import plate_text_web as search
    import learning_session
    import stop_review

    try:
        import cv2
        cv2.setNumThreads(1)
    except Exception:
        pass
    if sys.platform.startswith('linux') and sys.argv[-1:] == ['--child']:
        # Prefer the expendable OCR child over the web server if the kernel's
        # global OOM killer fires before the parent resource watchdog.
        with suppress(OSError, ValueError):
            Path('/proc/self/oom_score_adj').write_text('500')
    try:
        request = json.load(sys.stdin)
        stage = Path(request['stage'])
        job = {'dir': request['directory'], 'video': request['video'],
               'options': request.get('section_options') or {},
               'cancel': threading.Event(), 'stop': threading.Event()}
        report_path = Path(job['dir']) / 'report.json'
        before = report_path.read_bytes()
        doc = json.loads(before)
        fingerprint = learning_session.verify_source(job, doc)
        for identity in (doc.get('source_identity'), doc.get('stop_review')):
            if identity and identity.get('input_sha256') not in (None, fingerprint):
                raise ValueError('OCR source identity differs')
        if doc.get('stop_review'):
            stop_review.validate_resume(doc, fingerprint)
        old_count = len(doc['detections'])
        doc['_ocr_original_count'] = old_count
        doc['_ocr_updates'] = {}
        stats = dict(added=0, matched_existing=0, decoded_frames=0, sampled_frames=[])
        job['_ocr_progress'] = lambda public: _atomic_small_json(stage / 'progress.json', public)
        search._scan(job, doc, request['settings'], stats)
        result = dict(report_sha256=hashlib.sha256(before).hexdigest(),
                      fingerprint=fingerprint, original_count=old_count,
                      updates=doc['_ocr_updates'],
                      additions=doc['detections'][old_count:],
                      stats=stats)
        stop_review.atomic_report(str(stage / 'result.json'), result)
    except Exception as error:
        # No exception text: OCR adapters can embed private license numbers.
        # Preserve just a safe failure class for the supervising process.
        with suppress(Exception):
            _atomic_small_json(stage / 'failure.json',
                               dict(error_type=type(error).__name__))
        return 2
    return 0


def _progress_parent(job, progress):
    import learning_session
    if not isinstance(progress, dict) or progress.get('state') != 'running':
        return
    allowed = ('state', 'done', 'total', 'added', 'matched_existing', 'source_frame', 'note')
    safe = {key: progress[key] for key in allowed if key in progress}
    job['plate_text_search'] = safe
    learning_session.update_learning(job, 'plate_text_search', 'Searching known plate text',
        done=safe.get('done'), total=safe.get('total'), unit='frames',
        source_frame=safe.get('source_frame'))


def _run_child(job, settings):
    limit = _rss_limit_mb()
    with tempfile.TemporaryDirectory(prefix='.plate-ocr-', dir=job['dir']) as directory:
        stage = Path(directory)
        command = [sys.executable, '-m', 'plate_text_subprocess', '--child']
        env = dict(os.environ, OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1',
                   MKL_NUM_THREADS='1', NUMEXPR_NUM_THREADS='1')
        process = subprocess.Popen(command, stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env,
            start_new_session=os.name == 'posix')
        # Preserve scanned section bounds inside the isolated worker; never
        # widen OCR discovery into an approved/out-of-scope section.
        options = job.get('options') or {}
        section_options = {key: options[key] for key in ('section_context', 'section_range')
                           if key in options}
        request = dict(stage=str(stage), directory=job['dir'], video=job['video'],
                       section_options=section_options,
                       settings=dict(plate_texts=settings['plate_texts'],
                                     max_frames=settings['max_frames']))
        try:
            process.stdin.write(json.dumps(request).encode('utf-8'))
            process.stdin.close()
            last_progress, last_log, peak_rss = None, 0., 0
            while process.poll() is None:
                if job['cancel'].is_set() or job['stop'].is_set():
                    raise InterruptedError('OCR search cancelled')
                if (job.get('phase') != 'learning'):
                    raise InterruptedError('OCR job changed')
                rss = _rss_tree_bytes(process.pid)
                peak_rss = max(peak_rss, rss)
                available = _available_bytes()
                if (rss > limit * 1024 * 1024 or
                        (available is not None and available < MIN_AVAILABLE_MB * 1024 * 1024)):
                    import openscrub_logging as diagnostics
                    reason = ('rss_budget' if rss > limit * 1024 * 1024
                              else 'host_memory_pressure')
                    diagnostics.event('ocr_worker_limit_exceeded', job, level=40,
                        reason=reason, rss_mb=round(rss/1024**2),
                        limit_mb=limit,
                        available_mb=round(available/1024**2) if available is not None else None)
                    raise MemoryError('OCR worker stopped at memory safety limit')
                progress_path = stage / 'progress.json'
                if progress_path.exists():
                    with suppress(OSError, ValueError):
                        stamp = progress_path.stat().st_mtime_ns
                        if stamp != last_progress:
                            last_progress = stamp
                            _progress_parent(job, json.loads(progress_path.read_text()))
                now = time.monotonic()
                if now - last_log > 30:
                    import openscrub_logging as diagnostics
                    diagnostics.event('ocr_worker_memory', job,
                        rss_mb=round(rss/1024**2), peak_rss_mb=round(peak_rss/1024**2),
                        limit_mb=limit,
                        available_mb=round(available/1024**2) if available is not None else None)
                    last_log = now
                time.sleep(.25)
            if process.returncode:
                failure = stage / 'failure.json'
                kind = 'unknown'
                if failure.exists():
                    with suppress(OSError, ValueError, KeyError):
                        kind = str(json.loads(failure.read_text())['error_type'])[:80]
                import openscrub_logging as diagnostics
                diagnostics.event('ocr_worker_exited', job, level=40,
                                  exit_code=process.returncode, failure_type=kind,
                                  peak_rss_mb=round(peak_rss/1024**2))
                raise RuntimeError('OCR worker exited without publishing results')
            result = json.loads((stage / 'result.json').read_text())
            return result, peak_rss
        finally:
            _terminate(process)


def perform(job, web):
    """Called only from the web job queue on Linux, never from an HTTP thread."""
    import learning_session
    import plate_text_web as search
    import stop_review
    settings = job.get('plate_text_request') or {}
    previous = settings.get('previous_phase', 'review')
    try:
        if job['cancel'].is_set() or job['stop'].is_set():
            raise InterruptedError('OCR search cancelled')
        expected = tuple(settings.get('report_identity') or ())
        if not expected or search._report_identity(job) != expected:
            raise ValueError('Review changed before OCR search started')
        payload, peak = _run_child(job, settings)
        if (job['cancel'].is_set() or job['stop'].is_set()):
            raise InterruptedError('OCR search cancelled')
        # This is the only publication point. Child output is a sparse proposal
        # delta, not a replacement report, and is never treated as a human label.
        with web._REVIEW_EDIT_LOCK, web._REVIEW_WORK_LOCK:
            if search._report_identity(job) != expected:
                raise ValueError('Review changed during OCR')
            if _digest_file(search._path(job)) != payload['report_sha256']:
                raise ValueError('Review changed during OCR')
            if web.vault_locked():
                raise ValueError('Review vault is locked')
            doc = web._load_job_report(job)
            if (learning_session.verify_source(job, doc) != payload['fingerprint']):
                raise ValueError('Source changed during OCR')
            protected = web._SECTIONS.whole_job_error(job)
            if protected:
                raise ValueError('Approved section changed during OCR')
            rows = doc['detections']
            count = int(payload['original_count'])
            if count != len(rows):
                raise ValueError('Review detection count changed during OCR')
            updates = payload['updates']
            additions = payload['additions']
            if not isinstance(updates, dict) or not isinstance(additions, list):
                raise ValueError('OCR result is invalid')
            for key, evidence in updates.items():
                index = int(key)
                if not 0 <= index < count or not isinstance(evidence, dict):
                    raise ValueError('OCR result has an invalid finding')
                rows[index]['plate_text_evidence'] = evidence
            for record in additions:
                if not isinstance(record, dict) or record.get('category') != 'plate' or record.get('verified_label') not in ('', None):
                    raise ValueError('OCR result has an invalid proposal')
            rows.extend(additions)
            stats = payload['stats']
            completed = dict(state='completed', note=search.NOTE,
                done=len(stats['sampled_frames']), total=len(stats['sampled_frames']),
                hint_count=len(settings['plate_texts']), **stats)
            doc['plate_text_search'] = completed
            if stats['added']:
                doc['render_required'] = True
            stop_review.atomic_report(str(search._path(job)), doc)
        job.update(phase='paused' if previous == 'paused' else 'review', error=None,
                   plate_text_search=completed)
        if stats['added']:
            job['output'] = None
        learning_session.update_learning(job, 'plate_text_complete', search.NOTE,
            done=completed['done'], total=completed['total'], unit='frames')
        import openscrub_logging as diagnostics
        diagnostics.event('ocr_worker_finished', job, peak_rss_mb=round(peak/1024**2),
                          added=stats['added'], matched_existing=stats['matched_existing'])
    except InterruptedError:
        message = 'Known plate text search cancelled; previous review retained.'
        job.update(phase=previous, error=None,
                   plate_text_search=dict(state='cancelled', note=search.NOTE, message=message),
                   learning=dict(stage='cancelled', message=message))
    except Exception as failure:
        # Exception messages can contain OCR observations; log only their
        # safe class and the failed phase, never paths or supplied plate text.
        import openscrub_logging as diagnostics
        diagnostics.event('ocr_worker_failed', job, level=40,
                          failure_type=type(failure).__name__)
        error = search._ERROR
        job.update(phase=previous, error=error,
                   plate_text_search=dict(state='failed', note=search.NOTE, message=error),
                   learning=dict(stage='failed', message=error))
    finally:
        job.pop('plate_text_request', None)
        job['cancel'].clear()
        job['stop'].clear()
        job['eta'] = None


if __name__ == '__main__':
    if len(sys.argv) == 2 and sys.argv[1] == '--child':
        sys.exit(_child_process())
    sys.exit(2)
