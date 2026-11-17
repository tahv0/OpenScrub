"""Publish complete report JSON without truncating the previous report."""
from contextlib import contextmanager
import json
import os
import tempfile


@contextmanager
def _staged_report(path, report):
    """Stage private UTF-8 JSON beside *path*, sync, close, then replace it.

    A failure before replacement leaves the previous report intact and raises.
    Readers opening the path see a complete old or new report on filesystems
    supporting atomic replacement. This does not serialize read/apply/write
    transactions or guarantee power-loss durability: the directory is not
    fsynced, and filesystem/network storage guarantees vary. On Windows an open
    destination may prevent replacement; that failure is propagated. Temporary
    files use the vault's .tmp crash-cleanup convention. POSIX staging permissions
    are 0600; Windows access restrictions also depend on the directory ACL.
    """
    path = os.path.abspath(path)
    staged = None
    try:
        # NamedTemporaryFile creates exclusively with restrictive permissions.
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                         dir=os.path.dirname(path),
                                         prefix=".report-", suffix=".tmp",
                                         delete=False) as stream:
            staged = stream.name
            # Consume the public encoder iterator in TextIOWrapper rather than
            # dispatching one Python stream.write call for every JSON token.
            # Tokens remain streamed; a single large string is still one token.
            stream.writelines(json.JSONEncoder(indent=1).iterencode(report))
            stream.flush()
            os.fsync(stream.fileno())
        # Close first: Windows cannot rename an open staging file.
        yield staged
    finally:
        if staged is not None:
            try:
                os.unlink(staged)
            except OSError:
                # After replace the name is gone. On cleanup failure leave a
                # .tmp for vault crash cleanup without masking the write error.
                pass


def atomic_report(path, report) -> None:
    """Publish one closed shared-serializer stage."""
    with _staged_report(path, report) as staged:
        os.replace(staged, os.path.abspath(path))
