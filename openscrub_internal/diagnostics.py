"""Small opt-in, content-free service lifecycle records.

This is deliberately independent of Python logging and job storage: callbacks
may contain private content and must never be passed to this module.
"""
import datetime
import json
import math
import os
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
        return (type(value) in (int, float) and math.isfinite(value)
                and 0 <= value <= _MAX_NUMBER)
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
    except BaseException:
        pass
    return 'other', None


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
        self._enabled = False
        self._closed = False
        self._stop = threading.Event()
        self._last_notice = None
        try:
            os.makedirs(self._directory, mode=0o700, exist_ok=True)
            self._lockfile = self._open_private('writer.lock', 'a+b', restrict=False)
            if not self._acquire():
                self._lockfile.close()
                self._lockfile = None
                return
            os.chmod(self._directory, 0o700)
            os.chmod(os.path.join(self._directory, 'writer.lock'), 0o600)
            previous = self._read_marker()
            self._stream = self._open_private('runtime.jsonl', 'ab')
            self._enabled = True
            if previous is not None:
                self.emit('previous_run_unclean', **previous)
            self._marker()
            self.emit('service_started', version=version, transport=transport)
            if self._enabled and monitor:
                threading.Thread(target=self._monitor, daemon=True,
                                 name='diagnostics-monitor').start()
        except BaseException:
            self._disable()

    def _open_private(self, name, mode, restrict=True):
        path = os.path.join(self._directory, name)
        fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_APPEND, 0o600)
        try:
            if restrict:
                os.chmod(path, 0o600)
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
        path = os.path.join(self._directory, 'running.json')
        try:
            with open(path, 'rb') as stream:
                data = stream.read(_MAX_EVENT + 1)
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
        except (OSError, ValueError, TypeError, UnicodeError):
            return None

    def _marker(self):
        marker = {'schema': 1, 'active': bool(self._actions)}
        if self._actions:
            marker['stage'] = next(iter(self._actions.values()))['stage']
        data = json.dumps(marker, separators=(',', ':')).encode('ascii')
        path = os.path.join(self._directory, 'running.json')
        temp = os.path.join(self._directory, 'running.json.tmp')
        fd = os.open(temp, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
        try:
            os.fchmod(fd, 0o600) if hasattr(os, 'fchmod') else None
            with os.fdopen(fd, 'wb') as stream:
                fd = None
                stream.write(data)
                stream.flush()
            os.replace(temp, path)
        finally:
            if fd is not None:
                os.close(fd)

    def _disable(self):
        self._enabled = False
        self._stop.set()
        try:
            if self._stream is not None:
                self._stream.close()
        except BaseException:
            pass
        self._stream = None
        try:
            if self._lockfile is not None:
                self._lockfile.close()
        except BaseException:
            pass
        self._lockfile = None
        try:
            now = self._clock()
            if self._last_notice is None or now - self._last_notice >= 60:
                print('[web] diagnostics unavailable', flush=True)
                self._last_notice = now
        except BaseException:
            pass

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
                if kind == 'job_stage' and fields['stage'] == 'prepare':
                    return False
                if kind == 'job_finished' and ((fields['outcome'] == 'error') != ('error' in fields)):
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
                    path = os.path.join(self._directory, 'runtime.jsonl')
                    if os.path.exists(path + '.1'):
                        os.replace(path + '.1', path + '.2')
                    os.replace(path, path + '.1')
                    self._stream = self._open_private('runtime.jsonl', 'ab')
                self._stream.write(data)
                self._stream.flush()
                return True
        except BaseException:
            self._disable()
            return False

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
        except BaseException:
            self._disable()
            return None

    def progress(self, ref, stage, current, total):
        try:
            with self._mutex:
                if not self._enabled or not _reference(ref):
                    return
                state = self._actions.get(ref)
                if (state is None or stage not in ('scan', 'post', 'render')
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
        except BaseException:
            self._disable()

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
        except BaseException:
            self._disable()

    def _monitor(self):
        try:
            while not self._stop.wait(1):
                self.heartbeat()
        except BaseException:
            self._disable()

    def abandon(self, ref):
        """Forget an action lost with its worker without inventing an outcome."""
        try:
            with self._mutex:
                if not self._enabled or not _reference(ref):
                    return
                if self._actions.pop(ref, None) is not None:
                    self._marker()
        except BaseException:
            self._disable()

    def finish(self, ref, outcome, exc=None):
        try:
            with self._mutex:
                if not self._enabled or not _reference(ref) or not _valid_field('outcome', outcome):
                    return
                state = self._actions.get(ref)
                if state is None:
                    return
                fields = {'action_ref': ref, 'action': state['action'], 'outcome': outcome}
                if exc is not None:
                    fields['error'], number = classify(exc)
                    if number is not None:
                        fields[number[0]] = number[1]
                self.emit('job_finished', **fields)
                self._actions.pop(ref, None)
                if self._enabled:
                    self._marker()
        except BaseException:
            self._disable()

    def close(self, reason, vault):
        try:
            with self._mutex:
                if self._closed:
                    return
                self._closed = True
                self._stop.set()
                if self._enabled and self.emit('service_stop', reason=reason,
                                               active_actions=len(self._actions), vault=vault):
                    os.unlink(os.path.join(self._directory, 'running.json'))
                self._actions.clear()
                if self._stream is not None:
                    self._stream.close()
                self._stream = None
                self._enabled = False
                if self._lockfile is not None:
                    self._lockfile.close()
                self._lockfile = None
        except BaseException:
            self._disable()
