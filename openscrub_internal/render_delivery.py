"""Transient render stage and ordinary-exception pair publication ownership.

No cross-process coordination or crash-atomic/durable transaction is promised.
Callers provide their existing short publication lock and keep input lifetimes.
"""
from contextlib import ExitStack
import json
import os
import re
import shutil
import stat
import uuid

from .reports import _staged_report

_STAGE = re.compile(r'^\.render-[0-9a-f]{32}\.tmp(?:\.[^.\/\\]+)?(?:\.noaudio\.mp4)?$')
_RECOVERY = re.compile(r'^\.render-recovery-[0-9a-f]{32}\.json$')


def _is_discardable_render_stage(path):
    name = os.path.basename(path)
    return name.endswith('.tmp') or _STAGE.fullmatch(name) is not None


def _has_render_recovery(directory):
    # The strict name alone is conservative evidence. Never trust descriptor
    # contents as authority to open paths or restore files on restart.
    return any(_RECOVERY.fullmatch(name) for name in os.listdir(directory))


class _DeliveryRecoveryError(RuntimeError):
    def __init__(self, primary, diagnostics):
        self.primary = primary
        self.rollback_diagnostics = tuple(diagnostics[:8])
        super().__init__('render delivery requires recovery')


def _entry_key(path):
    return os.path.normcase(os.path.join(os.path.realpath(os.path.dirname(path)),
                                        os.path.basename(path)))


def _identity(path):
    parent = os.path.dirname(path)
    pst = os.stat(parent)
    directory = (os.path.realpath(parent), pst.st_dev, pst.st_ino)
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return directory, None
    entry = (st.st_dev, st.st_ino, st.st_mode, st.st_size,
             st.st_mtime_ns, st.st_ctime_ns,
             os.readlink(path) if stat.S_ISLNK(st.st_mode) else None)
    return directory, entry


def _exclusive(path):
    return os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)


class _RenderDelivery:
    def __init__(self, video_path, report_path=None):
        self.video_path = os.path.abspath(video_path)
        self.report_path = os.path.abspath(report_path) if report_path else None
        if self.report_path and _entry_key(self.video_path) == _entry_key(self.report_path):
            raise ValueError('video and report require distinct destination entries')
        self.token = uuid.uuid4().hex
        self.video_stage = os.path.join(os.path.dirname(self.video_path),
            '.render-' + self.token + '.tmp' + os.path.splitext(self.video_path)[1])
        self.committed = False
        self.recovery_required = False
        self.cleanup_diagnostics = []
        self._stack = ExitStack()
        self._report_stage = None
        self._doc = self._legacy = None
        self._old = []
        self._descriptor = None
        self._prepared = False
        # Forward-only validation, distinct from the rollback epoch callback.
        self.validate_before_publication = None

    def __enter__(self):
        os.close(_exclusive(self.video_stage))
        return self

    def prepare_report(self, doc, legacy_publisher=None):
        self._doc, self._legacy = doc, legacy_publisher
        if self.report_path and legacy_publisher is None:
            self._report_stage = self._stack.enter_context(_staged_report(self.report_path, doc))

    def prepare_rollback(self):
        if self._prepared:
            return
        for role, path in [('video', self.video_path), ('report', self.report_path)]:
            if path is None:
                continue
            before = _identity(path)
            backup = os.path.join(os.path.dirname(path),
                                  '.render-recovery-' + self.token + '.' + role)
            # Register ownership before fallible copy/flush/close operations.
            old = dict(path=path, identity=before, backup=None, role=role)
            self._old.append(old)
            if before[1] is not None:
                kind = before[1][2]
                if stat.S_ISLNK(kind):
                    os.symlink(before[1][-1], backup)
                    old['backup'] = backup
                elif stat.S_ISREG(kind):
                    fd = _exclusive(backup)
                    old['backup'] = backup
                    with os.fdopen(fd, 'wb') as out, open(path, 'rb') as src:
                        shutil.copyfileobj(src, out)
                        out.flush()
                        os.fsync(out.fileno())
                else:
                    raise ValueError('unsupported render destination entry')
            if _identity(path) != before:
                raise RuntimeError('render destination changed during backup')
        descriptor = os.path.join(os.path.dirname(self.report_path or self.video_path),
                                  '.render-recovery-' + self.token + '.json')
        fd = _exclusive(descriptor)
        self._descriptor = descriptor
        with os.fdopen(fd, 'w', encoding='utf-8') as out:
            json.dump(dict(version=1, token=self.token, finals=[dict(
                role=o['role'], path=o['path'], present=o['identity'][1] is not None,
                backup=o['backup']) for o in self._old]), out)
            out.flush()
            os.fsync(out.fileno())
        self._prepared = True

    def commit(self, *, before_mutation=None, publish_success=None, restore_success=None):
        if self.committed:
            raise RuntimeError('render delivery already committed')
        if not self._prepared:
            raise RuntimeError('render rollback must be prepared before commit')
        if any(_identity(old['path']) != old['identity'] for old in self._old):
            raise RuntimeError('render destination changed before publication')
        attempted = []
        try:
            for old in self._old:
                if self.validate_before_publication is not None:
                    self.validate_before_publication()
                attempted.append(old)
                if before_mutation:
                    before_mutation()
                if old['role'] == 'video':
                    os.replace(self.video_stage, self.video_path)
                elif self._legacy is not None:
                    self._legacy(self.report_path, self._doc)
                else:
                    os.replace(self._report_stage, self.report_path)
            if publish_success:
                publish_success()
            if self.validate_before_publication is not None:
                self.validate_before_publication()
            # Last fallible authoritative action; backups are still present.
            os.unlink(self._descriptor)
            self._descriptor = None
            self.committed = True
        except BaseException as primary:
            diagnostics = []
            if restore_success:
                try:
                    restore_success()
                except BaseException as error:
                    diagnostics.append('terminal restoration: ' + type(error).__name__)
            for old in reversed(attempted):
                try:
                    if before_mutation:
                        before_mutation()
                    if old['backup'] is not None:
                        os.replace(old['backup'], old['path'])
                        old['backup'] = None
                    else:
                        try:
                            os.unlink(old['path'])
                        except FileNotFoundError:
                            pass
                except BaseException as error:
                    diagnostics.append(old['role'] + ' restoration: ' + type(error).__name__)
            if not diagnostics:
                try:
                    os.unlink(self._descriptor)
                    self._descriptor = None
                except BaseException as error:
                    diagnostics.append('descriptor retirement: ' + type(error).__name__)
            if diagnostics:
                self.recovery_required = True
                raise _DeliveryRecoveryError(primary, diagnostics) from primary
            raise

    def __exit__(self, *exc):
        if self.recovery_required:
            # Close the ExitStack to discard expendable report staging; required
            # recovery backups, final paths, and the descriptor remain discoverable.
            self._stack.close()
            return
        try:
            self._stack.close()
        except Exception as error:
            self.cleanup_diagnostics.append(type(error).__name__)
        for path in [self.video_stage, self.video_stage + '.noaudio.mp4', self._descriptor] + [old['backup'] for old in self._old]:
            if path is not None:
                try:
                    os.unlink(path)
                except FileNotFoundError:
                    pass
                except OSError as error:
                    self.cleanup_diagnostics.append(type(error).__name__)
