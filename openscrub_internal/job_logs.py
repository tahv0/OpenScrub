"""Bounded, in-memory job messages with atomic absolute cursor snapshots.

Only plain strings are accepted (TypeError otherwise, without conversion).
Lone surrogates become '?' via UTF-8's replacement policy. Normalization
copies at most MAX_ENTRY_BYTES codepoints before encoding, even for enormous
inputs. Payload limits exclude caller inputs, Python overhead, detached
snapshots, JSON escaping, and browser history. No callbacks or job locks run
under the local store lock.
"""
from collections import deque
from threading import Lock
from uuid import uuid4

MAX_ENTRIES = 2000
MAX_BYTES = 512 * 1024
MAX_ENTRY_BYTES = 8 * 1024
TRUNCATION_SUFFIX = '... [message truncated]'


class JobLog:
    """One store per constructed job; retry keeps this store and epoch."""

    def __init__(self, messages=(), *, max_entries=MAX_ENTRIES,
                 max_bytes=MAX_BYTES, max_entry_bytes=MAX_ENTRY_BYTES):
        if (max_entries < 1 or max_bytes < max_entry_bytes
                or max_entry_bytes < len(TRUNCATION_SUFFIX)):
            raise ValueError('invalid job log bounds')
        self._max_entries = max_entries
        self._max_bytes = max_bytes
        self._max_entry_bytes = max_entry_bytes
        self._entries = deque()
        self._bytes = 0
        self._base = 0
        self._next = 0
        self._truncated = 0
        self._epoch = uuid4().hex
        self._lock = Lock()
        for message in messages:
            self.append(message)

    def append(self, message):
        if type(message) is not str:
            raise TypeError('job log message must be a plain string')
        # Bound work and temporary storage independently of caller input size.
        prefix = message[:self._max_entry_bytes].encode('utf-8', 'replace')
        truncated = (len(message) > self._max_entry_bytes
                     or len(prefix) > self._max_entry_bytes)
        if truncated:
            budget = self._max_entry_bytes - len(TRUNCATION_SUFFIX)
            text = prefix[:budget].decode('utf-8', 'ignore') + TRUNCATION_SUFFIX
        else:
            text = prefix.decode('utf-8')
        size = len(text.encode('utf-8'))
        with self._lock:
            while (len(self._entries) >= self._max_entries
                   or self._bytes + size > self._max_bytes):
                _, dropped_size = self._entries.popleft()
                self._bytes -= dropped_size
                self._base += 1
            self._entries.append((text, size))
            self._bytes += size
            self._next += 1
            self._truncated += int(truncated)

    def snapshot(self, cursor=0, epoch=None, *, tail=None):
        """Detach one coherent interval; JSON encoding belongs outside the lock.

        Tail snapshots supply metadata. Cursor snapshots prioritize epoch,
        stale, then future resets. `len` is absolute next, never deque length.
        """
        cursor = max(0, cursor)
        with self._lock:
            reset = None
            if tail is not None:
                start = max(self._base, self._next - tail)
            elif epoch is not None and epoch != self._epoch:
                start, reset = self._base, 'epoch'
            elif cursor < self._base:
                start, reset = self._base, 'stale'
            elif cursor > self._next:
                start, reset = self._base, 'future'
            else:
                start = cursor
            lines = [text for i, (text, _) in enumerate(self._entries, self._base)
                     if i >= start]
            return {'from': start, 'lines': lines, 'len': self._next,
                    'epoch': self._epoch, 'base': self._base, 'reset': reset,
                    'dropped': self._base, 'truncated': self._truncated,
                    'retained': len(self._entries), 'bytes': self._bytes}
