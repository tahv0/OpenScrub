"""In-process web file ownership. Reserve/inspect only under the web guard.

Per-job state also owns the report transaction lock and operation identity.
This does not coordinate other processes. A lifetime token may move to a queued task, thread, or WSGI iterable; release is idempotent.
"""

import threading
import uuid


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
        self.output_epoch = 0
        self.recovery_required = False
        self.recovery_diagnostics = ()
        # Current observed input only; no durable identity or sample history.
        self.incarnation = uuid.uuid4().hex
        self.source_epoch = 0
        self.current_source = None
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

    @staticmethod
    def initialize(job):
        try:
            return job["_files"]
        except KeyError:
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
        self.related = []
        self.source = None
        self.source_job = None
        self.source_state = None
        self.report_input = False
        self.operation = None

    def release_locked(self):
        if self.released:
            return
        self.released = True
        for lease in self.related:
            lease.release_locked()
        self.owners.count -= 1
        if self.state is not None:
            self.state.count -= 1
            self.state.work -= int(self.work)

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
