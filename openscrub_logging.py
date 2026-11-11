"""Local, bounded diagnostics for the web worker. Never log request bodies.

Regular records go to stderr and rotating files under the existing data root.
Fault dumps use a separate, stable file descriptor (rotated only at startup).
No logger can record SIGKILL, power loss, or a filesystem that has stopped
accepting writes; the running marker and periodic records expose that gap.
"""
from contextvars import ContextVar
import atexit
import faulthandler
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re
import shutil
import sys
import threading
import time

_RUNTIME = None
_JOB = ContextVar('openscrub_diagnostic_job', default=None)
_SECRETS = []
_ANSI = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')
_CREDENTIAL = re.compile(r'(?i)((?:token|password|secret|api[_-]?key|authorization)\s*[=:]\s*)([^\s&;]+)')


def set_secrets(values):
    global _SECRETS
    _SECRETS = [str(v) for v in values if v]


def _scrub(value, limit=None):
    text = _ANSI.sub('', str(value))
    for secret in _SECRETS:
        text = text.replace(secret, '[REDACTED]')
    text = _CREDENTIAL.sub(r'\1[REDACTED]', text)
    if limit and len(text) > limit:
        text = text[:limit] + ' [truncated]'
    return text


class _Formatter(logging.Formatter):
    converter = time.gmtime

    def format(self, record):
        # Never mutate a shared record or cache unsanitized exception text.
        import copy
        record = copy.copy(record)
        record.job_id = getattr(record, 'job_id', '-')
        record.phase = getattr(record, 'phase', '-')
        record.stage = getattr(record, 'stage', '-')
        record.msg = _scrub(record.getMessage(), 16000).replace('\r', r'\r').replace('\n', r'\n')
        record.args = ()
        record.exc_text = None
        return _scrub(super().format(record))


class _FileHandler(RotatingFileHandler):
    def __init__(self, path, console, **kwargs):
        self.console = console
        self.last_error = -float('inf')
        super().__init__(path, encoding='utf-8', errors='backslashreplace', **kwargs)

    def _open(self):
        stream = super()._open()
        if os.name != 'nt':
            os.chmod(self.baseFilename, 0o600)
        return stream

    def handleError(self, record):
        # Logging must not mask the original failure or recursively log itself.
        now = time.monotonic()
        if now - self.last_error < 60:
            return
        self.last_error = now
        error = sys.exc_info()[1]
        try:
            self.console.write('ERROR persistent_log_write_failed: %s; console logging continues\n' % _scrub(error))
            self.console.flush()
        except Exception:
            pass


class _ConsoleHandler(logging.StreamHandler):
    def handleError(self, record):
        pass  # The independent file handler may still succeed.


def _context(job):
    job = job if job is not None else _JOB.get()
    if not job:
        return {'job_id':'-', 'phase':'-', 'stage':'-'}
    return {'job_id':job.get('id','-'), 'phase':job.get('phase','-'),
            'stage':(job.get('learning') or {}).get('stage') or
                    (job.get('_diagnostic_progress') or {}).get('stage','-')}


def event(name, job=None, level=logging.INFO, exc_info=None, **fields):
    message = str(name)
    if fields:
        message += ' ' + ' '.join('%s=%s' % (k, _scrub(v, 8000)) for k,v in fields.items())
    try:
        logging.getLogger('openscrub.runtime').log(level, message, extra=_context(job), exc_info=exc_info)
    except Exception:
        # Last resort, without involving logging again.
        try:
            sys.__stderr__.write('OpenScrub diagnostic emission failed\n')
        except Exception:
            pass


def exception(name, job=None, **fields):
    event(name, job, level=logging.ERROR, exc_info=sys.exc_info(), **fields)


class JobLog(list):
    """Preserve the existing UI log API while persisting every added message."""
    def __init__(self, job, previous):
        super().__init__(previous)
        self.job = job

    def append(self, message):
        message = str(message)
        super().append(message)
        self.job['_diagnostic_activity'] = time.monotonic()
        level = logging.ERROR if message.lstrip().startswith(('ERROR:', 'Learning stopped:')) else logging.INFO
        event('job_message', self.job, level=level, message=message)

    def extend(self, messages):
        for message in messages:
            self.append(message)


def attach_job(job):
    if not isinstance(job.get('log'), JobLog):
        job['log'] = JobLog(job, job.get('log', []))


def bind_job(job):
    return _JOB.set(job)


def reset_job(token):
    _JOB.reset(token)


def progress(job, stage, current, total):
    # In-memory, not a write per frame. The watchdog samples this every 30s.
    previous = job.get('_diagnostic_progress') or {}
    if (previous.get('stage'), previous.get('current')) != (stage, current):
        job['_diagnostic_activity'] = time.monotonic()
    job['_diagnostic_progress'] = {'stage':stage, 'current':current, 'total':total}


def start_job(job, action):
    attach_job(job)
    job['_diagnostic_activity'] = time.monotonic()
    job['_diagnostic_progress'] = {}
    if _RUNTIME:
        with _RUNTIME.lock:
            _RUNTIME.active[job['id']] = job
        _RUNTIME.marker()
    event('job_action_started', job, action=action)


def finish_job(job, action):
    event('job_action_finished', job, action=action, outcome='error' if job.get('error') else 'returned')
    if _RUNTIME:
        with _RUNTIME.lock:
            _RUNTIME.active.pop(job['id'], None)
        _RUNTIME.marker()


def _resources(data_root):
    result = {}
    try:
        result['disk_free_mb'] = shutil.disk_usage(data_root).free // (1024*1024)
    except OSError:
        result['disk_free_mb'] = 'unavailable'
    try:
        for line in Path('/proc/self/status').read_text().splitlines():
            if line.startswith('VmRSS:'):
                result['rss_mb'] = int(line.split()[1]) // 1024
    except (OSError,ValueError):
        pass
    for filename, key in [('memory.current','cgroup_memory_bytes'),('memory.max','cgroup_limit_bytes')]:
        try:
            result[key] = Path('/sys/fs/cgroup', filename).read_text().strip()
        except OSError:
            pass
    return result


class RuntimeLogs:
    def __init__(self, data_root, stream, max_bytes, backups):
        self.data_root = Path(data_root)
        self.directory = self.data_root/'logs'
        self.stream = stream
        self.clock = time.monotonic
        self.active = {}
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.thread = None
        self.file_handler = None
        self.fault_file = None
        self.hooks = None
        self.closed = False
        self.logger = logging.getLogger('openscrub.runtime')
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False
        formatter = _Formatter('%(asctime)sZ %(levelname)s pid=%(process)d thread=%(threadName)s job=%(job_id)s phase=%(phase)s stage=%(stage)s %(message)s', '%Y-%m-%dT%H:%M:%S')
        self.console_handler = _ConsoleHandler(stream)
        self.console_handler.setFormatter(formatter)
        self.logger.addHandler(self.console_handler)
        self.root_handler = None
        try:
            self.directory.mkdir(parents=True,exist_ok=True,mode=0o700)
            if os.name != 'nt': self.directory.chmod(0o700)
            self.file_handler = _FileHandler(self.directory/'openscrub.log', stream,
                maxBytes=max_bytes, backupCount=backups)
            self.file_handler.setFormatter(formatter)
            self.logger.addHandler(self.file_handler)
            marker = self.directory/'running.json'
            if marker.exists():
                try:
                    old = json.loads(marker.read_text()[:131072])
                except (OSError,ValueError):
                    old = {'previous_state':'unreadable'}
                event('previous_process_did_not_shutdown_cleanly', level=logging.WARNING,
                      previous=old, note='Could be kill, crash, host shutdown or interrupted restart; not a diagnosis')
        except OSError as error:
            event('persistent_logging_unavailable',level=logging.ERROR,error=error)
        self.marker()

    def marker(self):
        if not self.file_handler: return
        try:
            with self.lock:
                payload={'pid':os.getpid(),'updated_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
                         'active_jobs':[dict(id=j.get('id'),phase=j.get('phase'),
                                             stage=_context(j)['stage'],progress=j.get('_diagnostic_progress'))
                                        for j in self.active.values()]}
                tmp=self.directory/'running.json.tmp'
                with open(tmp,'w',encoding='utf-8') as output:
                    if os.name!='nt':os.chmod(tmp,0o600)
                    json.dump(payload,output);output.flush()
                os.replace(tmp,self.directory/'running.json')
        except (OSError,ValueError,TypeError) as error:
            event('running_marker_write_failed',level=logging.ERROR,error=error)

    def install_hooks(self):
        self.hooks=(sys.excepthook, threading.excepthook)
        def main_exception(kind, value, tb):
            event('process_unhandled_exception',level=logging.CRITICAL,exc_info=(kind,value,tb))
        def thread_exception(args):
            event('thread_unhandled_exception',level=logging.CRITICAL,
                  exc_info=(args.exc_type,args.exc_value,args.exc_traceback),
                  failed_thread=getattr(args.thread,'name','unknown'))
        sys.excepthook=main_exception;threading.excepthook=thread_exception
        # Capture warnings/errors from Flask, libraries and Python warnings.
        owner=self
        class Bridge(logging.Handler):
            def emit(self, record):
                if not record.name.startswith('openscrub.runtime'):
                    owner.logger.handle(record)
        self.root_handler=Bridge(logging.WARNING)
        logging.getLogger().addHandler(self.root_handler)
        logging.captureWarnings(True)
        try:
            if self.file_handler:
                for suffix in (2,1):
                    src=self.directory/('faults.log' if suffix==1 else 'faults.log.1')
                    dst=self.directory/('faults.log.%d'%suffix)
                    if src.exists():os.replace(src,dst)
                self.fault_file=open(self.directory/'faults.log','a',encoding='utf-8')
                if os.name!='nt':os.chmod(self.fault_file.name,0o600)
                self.fault_file.write('OpenScrub native fault log started %s pid=%d\n' % (time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),os.getpid()))
                self.fault_file.flush()
                faulthandler.enable(self.fault_file,all_threads=True)
            else:
                faulthandler.enable(all_threads=True)
        except (OSError,ValueError,RuntimeError) as error:
            event('fault_handler_unavailable',level=logging.WARNING,error=error)

    def heartbeat_once(self, now=None):
        now=self.clock() if now is None else now
        with self.lock: jobs=list(self.active.values())
        for job in jobs:
            idle=max(0,now-job.get('_diagnostic_activity',now))
            p=job.get('_diagnostic_progress') or {}
            event('job_heartbeat',job,seconds_since_activity=round(idle,1),
                  current=p.get('current','unknown'),total=p.get('total','unknown'),
                  **_resources(self.data_root))
            if idle>=300:
                event('no_recent_progress',job,level=logging.WARNING,
                      seconds=round(idle),note='Worker may be slow or blocked; job is not cancelled')
        self.marker()

    def start_monitor(self):
        def watch():
            while not self.stop.wait(30):
                try:self.heartbeat_once()
                except Exception:exception('logging_watchdog_failed')
        self.thread=threading.Thread(target=watch,name='openscrub-log-watchdog',daemon=True)
        self.thread.start()

    def close(self, clean=True):
        if self.closed:return
        self.closed=True;self.stop.set()
        if self.thread and self.thread is not threading.current_thread():self.thread.join(timeout=1)
        if self.active:
            event('server_shutdown_with_active_jobs', level=logging.WARNING, active_jobs=list(self.active))
        event('server_shutdown',active_jobs=list(self.active),clean=clean)
        if clean and self.file_handler:
            try:(self.directory/'running.json').unlink(missing_ok=True)
            except OSError as error:event('running_marker_cleanup_failed',level=logging.WARNING,error=error)
        if self.hooks:
            sys.excepthook,threading.excepthook=self.hooks
            logging.captureWarnings(False)
        if self.root_handler:logging.getLogger().removeHandler(self.root_handler)
        if self.fault_file:
            faulthandler.disable();self.fault_file.close()
        for handler in (self.file_handler,self.console_handler):
            if handler:
                self.logger.removeHandler(handler);handler.close()


def configure(data_root, stream=None, install_hooks=True, max_bytes=10*1024*1024, backups=5):
    global _RUNTIME
    if _RUNTIME:_RUNTIME.close()
    _RUNTIME=RuntimeLogs(data_root, stream if stream is not None else sys.__stderr__,max_bytes,backups)
    if install_hooks:
        _RUNTIME.install_hooks();_RUNTIME.start_monitor()
    event('server_logging_ready',log_directory=_RUNTIME.directory,rotation_bytes=max_bytes,backups=backups)
    return _RUNTIME


def shutdown(clean=True):
    global _RUNTIME
    if _RUNTIME:_RUNTIME.close(clean=clean);_RUNTIME=None


# An unhandled exception must keep the marker even though atexit still runs.
def _at_exit():
    if _RUNTIME:_RUNTIME.close(clean=False)
atexit.register(_at_exit)
