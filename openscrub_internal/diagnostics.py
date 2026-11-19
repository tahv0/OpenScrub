"""Small opt-in, content-free service lifecycle records.

This is deliberately independent of Python logging and job storage: callbacks
may contain private content and must never be passed to this module.
"""
import datetime
import json
import math
import os
import stat
from functools import wraps
import threading
import time
import uuid

_MAX_EVENT = 1024
_MAX_FILE = 5 * 1024 * 1024
_MAX_NUMBER = 2**31 - 1
_STAGES = frozenset(('prepare', 'scan', 'post', 'render'))
_ENUMS = {
    'transport': frozenset(('http', 'https')),
    'action': frozenset(('scan', 'render')),
    'stage': _STAGES,
    'outcome': frozenset(('review', 'done', 'cancelled', 'error', 'superseded')),
    'error': frozenset(('system_exit', 'os_error', 'value_error', 'runtime_error', 'other')),
    'reason': frozenset(('normal', 'sigterm', 'interrupt', 'startup_failure', 'serve_failure')),
    'vault': frozenset(('not_enabled', 'already_locked', 'locked', 'busy', 'failed')),
}
_FIELDS = {
    'service_started': ({'version', 'transport'}, set()),
    'job_started': ({'action_ref', 'action', 'stage'}, set()),
    'job_stage': ({'action_ref', 'stage'}, set()),
    'job_heartbeat': ({'action_ref', 'stage', 'current', 'total', 'idle_seconds'}, set()),
    'job_finished': ({'action_ref', 'action', 'outcome'}, {'error', 'errno', 'exit_code'}),
    'worker_restarted': ({'active_action_lost'}, set()),
    'worker_loop_error': ({'active_action_lost', 'error'}, set()),
    'service_stop': ({'reason', 'active_actions', 'vault'}, set()),
    'previous_run_unclean': ({'previous_active'}, {'stage'}),
}


def _reference(value):
    return (type(value) is str and len(value) == 32
            and all(c in '0123456789abcdef' for c in value))


def _is_reparse(st):
    """Reject Windows reparse metadata, including junctions, without 3.12 APIs."""
    try:
        attributes = getattr(st, 'st_file_attributes', 0)
        tag = getattr(st, 'st_reparse_tag', 0)
        return (type(attributes) is not int or type(tag) is not int
                or attributes < 0 or tag < 0
                or bool(attributes & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400))
                or tag != 0)
    except Exception:
        return True


def _valid_field(key, value):
    if key in _ENUMS:
        return type(value) is str and value in _ENUMS[key]
    if key == 'action_ref':
        return _reference(value)
    if key == 'version':
        # Versions come from the application, but do not allow arbitrary text.
        return (type(value) is str and 0 < len(value) <= 32
                and all(c in '0123456789.' for c in value))
    if key in ('active_action_lost', 'previous_active'):
        return type(value) is bool
    if key in ('current', 'total', 'active_actions'):
        return type(value) is int and 0 <= value <= _MAX_NUMBER
    if key in ('errno', 'exit_code'):
        return type(value) is int and -_MAX_NUMBER <= value <= _MAX_NUMBER
    if key == 'idle_seconds':
        if type(value) is int:
            return 0 <= value <= _MAX_NUMBER
        return type(value) is float and math.isfinite(value) and 0 <= value <= _MAX_NUMBER
    return False


def classify(exc):
    """Reduce an exception to fixed types and optional bounded numbers."""
    try:
        if isinstance(exc, SystemExit):
            code = exc.code
            return 'system_exit', ('exit_code', code) if _valid_field('exit_code', code) else None
        if isinstance(exc, OSError):
            code = exc.errno
            return 'os_error', ('errno', code) if _valid_field('errno', code) else None
        if isinstance(exc, ValueError):
            return 'value_error', None
        if isinstance(exc, RuntimeError):
            return 'runtime_error', None
    except Exception:
        pass
    return 'other', None


def _serialized(method):
    """Keep failure cleanup and ownership release serialized with every write."""
    @wraps(method)
    def guarded(self, *args, **kwargs):
        with self._mutex:
            try:
                return method(self, *args, **kwargs)
            except BaseException:
                self._disable(notice=False)
                raise
    return guarded


class Diagnostics:
    """One exclusive service writer. All public methods are best effort."""
    def __init__(self, directory, transport, version, *, max_file=_MAX_FILE,
                 clock=time.monotonic, monitor=True):
        self._mutex = threading.RLock()
        self._clock = clock
        self._actions = {}
        self._session = uuid.uuid4().hex
        self._directory = os.fspath(directory)
        self._max_file = max_file
        self._stream = None
        self._lockfile = None
        self._dirfd = None
        self._enabled = False
        self._closed = False
        self._stop = threading.Event()
        self._last_notice = None
        try:
            self._open_directory()
            self._lockfile = self._open_private('writer.lock', 'a+b', restrict=False)
            if not self._acquire():
                self._release_resources()
                return
            if self._dirfd is not None and hasattr(os, 'fchmod'):
                os.fchmod(self._dirfd, 0o700)
            if hasattr(os, 'fchmod'):
                os.fchmod(self._lockfile.fileno(), 0o600)
            # Refuse unsuitable or oversized existing state before any marker
            # or event write. Preserve those bytes for the owner to inspect.
            for name in ('runtime.jsonl', 'runtime.jsonl.1', 'runtime.jsonl.2'):
                entry = self._entry(name)
                if entry is not None and entry.st_size > self._max_file:
                    raise OSError('oversized diagnostics file')
            self._entry('running.json')
            if self._entry('running.json.tmp') is not None:
                raise OSError('unexpected marker temporary file')
            previous = self._read_marker()
            self._stream = self._open_private('runtime.jsonl', 'ab')
            self._enabled = True
            if previous is not None and not self.emit('previous_run_unclean', **previous):
                self._disable()
                return
            if not self._enabled:
                return
            self._marker()
            if not self.emit('service_started', version=version, transport=transport):
                self._disable()
                return
            if self._enabled and monitor:
                threading.Thread(target=self._monitor, daemon=True,
                                 name='diagnostics-monitor').start()
        except Exception:
            self._disable()
        except BaseException:
            self._disable(notice=False)
            raise

    def _open_directory(self):
        """Open each directory without following links; create only the leaf."""
        path = os.path.abspath(self._directory)
        self._directory = path
        if os.name != 'nt' and os.open in os.supports_dir_fd:
            parts = [part for part in path.split(os.sep) if part]
            fd = os.open(os.sep, os.O_RDONLY | os.O_DIRECTORY)
            try:
                for index, part in enumerate(parts):
                    try:
                        st = os.stat(part, dir_fd=fd, follow_symlinks=False)
                    except FileNotFoundError:
                        if index != len(parts) - 1:
                            raise
                        os.mkdir(part, 0o700, dir_fd=fd)
                        st = os.stat(part, dir_fd=fd, follow_symlinks=False)
                    if not stat.S_ISDIR(st.st_mode):
                        raise OSError('unsafe diagnostics directory')
                    child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | getattr(os, 'O_NOFOLLOW', 0), dir_fd=fd)
                    os.close(fd)
                    fd = child
                self._dirfd = fd
                fd = None
            finally:
                if fd is not None:
                    os.close(fd)
        else:
            # Windows fallback refuses links and non-directories before use.
            parents = []
            while path and path != os.path.dirname(path):
                parents.append(path)
                path = os.path.dirname(path)
            if path:
                parents.append(path)  # Include the drive or filesystem root.
            for index, part in enumerate(reversed(parents)):
                try:
                    st = os.lstat(part)
                except FileNotFoundError:
                    if index != len(parents) - 1:
                        raise
                    os.mkdir(part, 0o700)
                    st = os.lstat(part)
                if not stat.S_ISDIR(st.st_mode) or _is_reparse(st):
                    raise OSError('unsafe diagnostics directory')

    def _path_args(self, name):
        if self._dirfd is not None:
            return name, {'dir_fd': self._dirfd}
        return os.path.join(self._directory, name), {}

    def _entry(self, name):
        path, kw = self._path_args(name)
        try:
            st = os.stat(path, follow_symlinks=False, **kw)
        except FileNotFoundError:
            return None
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or _is_reparse(st):
            raise OSError('unsafe diagnostics entry')
        return st

    def _open_private(self, name, mode, restrict=True):
        self._entry(name)
        path, kw = self._path_args(name)
        flags = os.O_CREAT | os.O_RDWR | os.O_APPEND | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0) | getattr(os, 'O_BINARY', 0)
        fd = os.open(path, flags, 0o600, **kw)
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or _is_reparse(st):
                raise OSError('unsafe diagnostics entry')
            if restrict and hasattr(os, 'fchmod'):
                os.fchmod(fd, 0o600)
            return os.fdopen(fd, mode)
        except BaseException:
            os.close(fd)
            raise

    def _acquire(self):
        try:
            if os.name == 'nt':
                import msvcrt
                self._lockfile.seek(0)
                msvcrt.locking(self._lockfile.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._lockfile.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except (OSError, IOError):
            return False

    def _read_marker(self):
        entry = self._entry('running.json')
        if entry is None:
            return None
        if entry.st_size > _MAX_EVENT:
            return None
        path, kw = self._path_args('running.json')
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0) | getattr(os, 'O_BINARY', 0), **kw)
        try:
            st = os.fstat(fd)
            if (not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or _is_reparse(st)
                    or (st.st_dev, st.st_ino) != (entry.st_dev, entry.st_ino)):
                raise OSError('unsafe marker')
            with os.fdopen(fd, 'rb') as stream:
                fd = None
                data = stream.read(_MAX_EVENT + 1)
        finally:
            if fd is not None:
                os.close(fd)
        try:
            if len(data) > _MAX_EVENT:
                return None
            marker = json.loads(data)
            if (type(marker) is not dict or set(marker) - {'schema', 'active', 'stage'}
                    or type(marker.get('schema')) is not int or marker['schema'] != 1
                    or type(marker.get('active')) is not bool):
                return None
            result = {'previous_active': marker['active']}
            if 'stage' in marker:
                if not marker['active'] or not _valid_field('stage', marker['stage']):
                    return None
                result['stage'] = marker['stage']
            return result
        except (ValueError, TypeError, UnicodeError):
            return None

    def _marker(self):
        if not self._enabled or self._lockfile is None:
            raise OSError('diagnostics not owned')
        marker = {'schema': 1, 'active': bool(self._actions)}
        if self._actions:
            marker['stage'] = next(iter(self._actions.values()))['stage']
        data = json.dumps(marker, separators=(',', ':')).encode('ascii')
        if len(data) > _MAX_EVENT:
            raise ValueError('marker exceeds limit')
        self._entry('running.json')
        name = 'running.json.tmp'
        temp, kw = self._path_args(name)
        target, _ = self._path_args('running.json')
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0)
        fd = os.open(temp, flags, 0o600, **kw)
        created = True
        try:
            if hasattr(os, 'fchmod'):
                os.fchmod(fd, 0o600)
            with os.fdopen(fd, 'wb') as stream:
                fd = None
                stream.write(data)
                stream.flush()
            self._entry('running.json')
            if self._dirfd is not None:
                os.replace(temp, target, src_dir_fd=self._dirfd, dst_dir_fd=self._dirfd)
            else:
                os.replace(temp, target)
            created = False
        finally:
            if fd is not None:
                os.close(fd)
            if created:
                try:
                    os.unlink(temp, **kw)
                except FileNotFoundError:
                    pass

    def _release_resources(self):
        stream, self._stream = self._stream, None
        directory, self._dirfd = self._dirfd, None
        lock, self._lockfile = self._lockfile, None
        try:
            try:
                if stream is not None:
                    stream.close()
            except Exception:
                pass
        finally:
            try:
                if directory is not None:
                    os.close(directory)
            finally:
                if lock is not None:
                    lock.close()

    def _disable(self, notice=True):
        with self._mutex:
            self._enabled = False
            self._stop.set()
            self._actions.clear()
            try:
                self._release_resources()
            except Exception:
                pass
            if notice:
                try:
                    now = self._clock()
                    if self._last_notice is None or now - self._last_notice >= 60:
                        print('[web] diagnostics unavailable', flush=True)
                        self._last_notice = now
                except Exception:
                    pass

    @_serialized
    def emit(self, kind, **fields):
        try:
            with self._mutex:
                if not self._enabled or type(kind) is not str or kind not in _FIELDS:
                    return False
                required, optional = _FIELDS[kind]
                if not required <= fields.keys() or fields.keys() - required - optional:
                    return False
                if not all(_valid_field(k, v) for k, v in fields.items()):
                    return False
                if 'action_ref' in fields and fields['action_ref'] not in self._actions:
                    return False
                if kind == 'job_started' and fields['stage'] != 'prepare':
                    return False
                if kind == 'job_stage' and fields['stage'] == 'prepare':
                    return False
                if kind == 'job_finished' and ((fields['outcome'] == 'error') != ('error' in fields)):
                    return False
                if kind == 'job_finished' and fields['outcome'] != 'error' and ('errno' in fields or 'exit_code' in fields):
                    return False
                record = {'schema': 1, 'time': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                          'session': self._session, 'kind': kind}
                record.update(fields)
                data = (json.dumps(record, separators=(',', ':'), allow_nan=False) + '\n').encode('utf-8')
                if len(data) > _MAX_EVENT or len(data) > self._max_file:
                    return False
                if self._stream.tell() + len(data) > self._max_file:
                    self._stream.close()
                    self._stream = None
                    current = self._entry('runtime.jsonl')
                    backup = self._entry('runtime.jsonl.1')
                    backup2 = self._entry('runtime.jsonl.2')
                    if (current is None or current.st_size > self._max_file
                            or (backup is not None and backup.st_size > self._max_file)
                            or (backup2 is not None and backup2.st_size > self._max_file)):
                        raise OSError('unsafe rotation state')
                    if self._dirfd is not None:
                        if backup is not None:
                            os.replace('runtime.jsonl.1', 'runtime.jsonl.2', src_dir_fd=self._dirfd, dst_dir_fd=self._dirfd)
                        os.replace('runtime.jsonl', 'runtime.jsonl.1', src_dir_fd=self._dirfd, dst_dir_fd=self._dirfd)
                    else:
                        path = os.path.join(self._directory, 'runtime.jsonl')
                        if backup is not None:
                            os.replace(path + '.1', path + '.2')
                        os.replace(path, path + '.1')
                    self._stream = self._open_private('runtime.jsonl', 'ab')
                self._stream.write(data)
                self._stream.flush()
                return True
        except Exception:
            self._disable()
            return False

    @_serialized
    def start(self, action):
        try:
            with self._mutex:
                if not self._enabled or not _valid_field('action', action):
                    return None
                ref = uuid.uuid4().hex
                now = self._clock()
                self._actions[ref] = {'action': action, 'stage': 'prepare', 'current': 0,
                                      'total': 0, 'changed': now, 'heartbeat': now}
                self._marker()
                self.emit('job_started', action_ref=ref, action=action, stage='prepare')
                return ref
        except Exception:
            self._disable()
            return None

    @_serialized
    def progress(self, ref, stage, current, total):
        try:
            with self._mutex:
                if not self._enabled or not _reference(ref):
                    return
                state = self._actions.get(ref)
                if (state is None or type(stage) is not str or stage not in ('scan', 'post', 'render')
                        or not _valid_field('current', current) or not _valid_field('total', total)):
                    return
                now = self._clock()
                if (state['stage'], state['current'], state['total']) != (stage, current, total):
                    state['changed'] = now
                if stage != state['stage']:
                    state['stage'] = stage
                    self._marker()
                    self.emit('job_stage', action_ref=ref, stage=stage)
                state['current'], state['total'] = current, total
        except Exception:
            self._disable()

    @_serialized
    def heartbeat(self):
        try:
            with self._mutex:
                now = self._clock()
                for ref, state in list(self._actions.items()):
                    if now - state['heartbeat'] >= 60:
                        state['heartbeat'] = now
                        self.emit('job_heartbeat', action_ref=ref, stage=state['stage'],
                                  current=state['current'], total=state['total'],
                                  idle_seconds=min(_MAX_NUMBER, max(0, now - state['changed'])))
        except Exception:
            self._disable()

    def _monitor(self):
        try:
            while not self._stop.wait(1):
                self.heartbeat()
        except Exception:
            self._disable()
        except BaseException:
            self._disable(notice=False)
            raise

    @_serialized
    def abandon(self, ref):
        """Forget an action lost with its worker without inventing an outcome."""
        try:
            with self._mutex:
                if not self._enabled or not _reference(ref):
                    return
                if self._actions.pop(ref, None) is not None:
                    self._marker()
        except Exception:
            self._disable()

    @_serialized
    def finish(self, ref, outcome, error=None):
        try:
            with self._mutex:
                if not self._enabled or not _reference(ref) or not _valid_field('outcome', outcome):
                    return
                state = self._actions.get(ref)
                if state is None:
                    return
                fields = {'action_ref': ref, 'action': state['action'], 'outcome': outcome}
                if (type(error) is tuple and len(error) == 2
                        and _valid_field('error', error[0])):
                    fields['error'], number = error
                    if (type(number) is tuple and len(number) == 2
                            and type(number[0]) is str and number[0] in ('errno', 'exit_code')
                            and _valid_field(number[0], number[1])):
                        fields[number[0]] = number[1]
                self.emit('job_finished', **fields)
                self._actions.pop(ref, None)
                if self._enabled:
                    self._marker()
        except Exception:
            self._disable()

    @_serialized
    def close(self, reason, vault):
        try:
            with self._mutex:
                if self._closed:
                    return
                self._closed = True
                self._stop.set()
                if self._enabled and self.emit('service_stop', reason=reason,
                                               active_actions=len(self._actions), vault=vault):
                    self._entry('running.json')
                    path, kw = self._path_args('running.json')
                    os.unlink(path, **kw)
                self._actions.clear()
                self._enabled = False
                self._release_resources()
        except Exception:
            self._disable()
