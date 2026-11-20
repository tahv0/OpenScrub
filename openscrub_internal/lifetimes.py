"""In-process web file ownership. Reserve/inspect only under the web guard.

Per-job state also owns the report transaction lock and operation identity.
This does not coordinate other processes. A lifetime token may move to a queued task, thread, or WSGI iterable; release is idempotent.
"""

import threading
import uuid
from .thumbnails import ThumbnailState


class _JobFiles:
    def __init__(self):
        self._leases = set()
        self._work_leases = set()
        self.closed = False
        self.queued = {}
        self.tracker = None
        # Initialized before a new/rehydrated job enters the registry. Never
        # persisted: one stable transaction boundary per live job identity.
        self.report_lock = threading.Lock()
        self.operation = None
        self.active = None
        self.output_epoch = 0
        self.recovery_required = False
        self.recovery_diagnostics = ()
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

    @property
    def count(self):
        return len(self._leases)

    @property
    def work(self):
        return len(self._work_leases)


class FileOwners:
    def __init__(self, guard):
        self.guard = guard
        self._leases = set()
        # Current process-created thumbnail inodes only. These indexes deny
        # deletion; they never select a source or retain source history.
        self.thumbnail_paths = {}
        self.thumbnail_inodes = {}
        self.thumbnail_resolving = set()
        self.thumbnail_admission = 0
        self.thumbnail_authority = object()

    @staticmethod
    def initialize(job):
        try:
            return job["_files"]
        except KeyError:
            return job.setdefault("_files", _JobFiles())

    @property
    def count(self):
        return len(self._leases)

    def reserve(self, job=None, work=False):
        state = self.initialize(job) if job is not None else None
        lease = _Lease(self, state, work)
        try:
            self._leases.add(lease)
            if state is not None:
                state._leases.add(lease)
                if work:
                    state._work_leases.add(lease)
        except BaseException:
            self._leases.discard(lease)
            if state is not None:
                state._leases.discard(lease)
                state._work_leases.discard(lease)
            raise
        return lease


class _Lease:
    def __init__(self, owners, state, work):
        self.owners, self.state, self.work = owners, state, work
        self.released = False
        self.release_started = False
        self._global_done = False
        self._job_done = state is None
        self._work_done = state is None or not work
        self.related = []
        self.source = None
        self.source_job = None
        self.source_state = None
        self.report_input = False
        self.operation = None

    def _decrement_locked(self, obj, name, marker, invocation):
        if getattr(self, marker):
            return
        contributions = obj._work_leases if name == 'work' else obj._leases
        contributions.discard(self)
        setattr(self, marker, True)

    def release_locked(self):
        if self.released:
            return
        invocation = object()
        self.release_started = True
        self.owners.thumbnail_resolving.discard(self)
        for lease in self.related:
            lease.release_locked()
        def remove_contributions():
            if self.state is not None:
                self._decrement_locked(self.state, 'work', '_work_done', invocation)
                self._decrement_locked(self.state, 'count', '_job_done', invocation)
            self._decrement_locked(self.owners, 'count', '_global_done', invocation)
            self.released = self._work_done and self._job_done and self._global_done
        try:
            remove_contributions()
        except BaseException:
            try:
                remove_contributions()
            except BaseException:
                pass
            raise

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
