"""In-process web file ownership. Reserve/inspect only under the web guard.

Per-job state also owns the report transaction lock and operation identity.
This does not coordinate other processes. A lifetime token may move to a queued task, thread, or WSGI iterable; release is idempotent.
"""

import threading
import uuid
from .thumbnails import ThumbnailState


class _JobFiles:
    def __init__(self):
        self.count = 0
        self.work = 0
        self.closed = False
        self.queued = {}
        self.tracker = None
        # Initialized before a new/rehydrated job enters the registry. Never
        # persisted: one stable transaction boundary per live job identity.
        self.report_lock = threading.Lock()
        self.operation = None
        self.active = None
        # Current observed input only; no durable identity or sample history.
        self.incarnation = uuid.uuid4().hex
        self.source_epoch = 0
        self.current_source = None
        self.source_report_bound = False
        self.thumbnail = ThumbnailState()
        self.thumbnail_artifacts = set()
        self.committed_report_epoch = 0
        self.source_pair = None
        self.source_status = "undiscovered"
        self.source_reason = None
        self.source_retired = False
        self.vault_transition = None


class FileOwners:
    def __init__(self, guard):
        self.guard = guard
        self.count = 0
        # Current process-created thumbnail inodes only. These indexes deny
        # deletion; they never select a source or retain source history.
        self.thumbnail_paths = {}
        self.thumbnail_inodes = {}
        self.thumbnail_resolving = set()
        self.thumbnail_admission = 0

    @staticmethod
    def initialize(job):
        return job.setdefault("_files", _JobFiles())

    def reserve(self, job=None, work=False):
        state = self.initialize(job) if job is not None else None
        self.count += 1
        if state is not None:
            state.count += 1
            state.work += int(work)
        return _Lease(self, state, work)


class _Lease:
    def __init__(self, owners, state, work):
        self.owners, self.state, self.work = owners, state, work
        self.released = False
        self.release_started = False
        self._global_done = False
        self._job_done = state is None
        self._work_done = state is None or not work
        self._decrement_intent = None
        self._decrement_uncertain = False
        self.related = []
        self.source = None
        self.report_input = False
        self.operation = None

    def _decrement_locked(self, obj, name, marker):
        if self._decrement_uncertain:
            raise RuntimeError('interrupted lease decrement needs same-guard reconciliation')
        if getattr(self, marker):
            if self._decrement_intent is not None and self._decrement_intent[3] == marker:
                self._decrement_intent = None
            return
        intent = self._decrement_intent
        if intent is None:
            before = getattr(obj, name)
            self._decrement_intent = (obj, name, before, marker)
        else:
            if intent[0] is not obj or intent[1] != name or intent[3] != marker:
                raise RuntimeError('unfinished lease decrement')
            before = intent[2]
        try:
            if getattr(obj, name) == before:
                setattr(obj, name, before - 1)
        finally:
            # The guard prevents unrelated updates while reconciling a
            # single interrupted assignment with its own before value.
            if getattr(obj, name) == before - 1:
                setattr(self, marker, True)
                self._decrement_intent = None

    def release_locked(self):
        if self.released:
            return
        self.release_started = True
        self.owners.thumbnail_resolving.discard(self)
        for lease in self.related:
            lease.release_locked()
        try:
            try:
                if self.state is not None:
                    self._decrement_locked(self.state, 'work', '_work_done')
                    self._decrement_locked(self.state, 'count', '_job_done')
                self._decrement_locked(self.owners, 'count', '_global_done')
            finally:
                # Reconcile the saved before-value only while this guard is
                # continuously held: other owners may change counts later.
                if self.state is not None:
                    self._decrement_locked(self.state, 'work', '_work_done')
                    self._decrement_locked(self.state, 'count', '_job_done')
                self._decrement_locked(self.owners, 'count', '_global_done')
                self.released = self._work_done and self._job_done and self._global_done
        finally:
            intent = self._decrement_intent
            if intent is not None:
                if getattr(self, intent[3]):
                    self._decrement_intent = None
                else:
                    self._decrement_uncertain = True

    def release(self):
        with self.owners.guard:
            self.release_locked()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.release()


class OwnedIterable:
    """Keep the file open/owned through WSGI close, including early disconnect.

    Deliberately hide the server's file_wrapper optimization so every server
    takes the same close path; the underlying streaming/range iterator remains
    incremental and its headers/bytes are unchanged.
    """
    def __init__(self, iterable, lease):
        self.iterable, self.iterator = iterable, iter(iterable)
        self.lease = lease
        self.closed = False

    def __iter__(self):
        return self

    def __next__(self):
        try:
            return next(self.iterator)
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            close = getattr(self.iterable, "close", None)
            if close is not None:
                close()
        finally:
            self.lease.release()
