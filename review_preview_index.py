"""On-disk, revision-bound metadata for individual Review preview requests.

The authoritative report.json is never changed by this index. A full report is
read only once to construct/reconstruct the index, then each thumbnail fetch
reads exactly one row from SQLite. No video bytes or plaintext OCR hints live
in the index beyond what was already in the report. Index files are job-local,
vault-managed and disposable; rebuilding must never change review decisions.
"""
import json
import os
from pathlib import Path
import sqlite3
import tempfile

from flask import abort

NAME = 'review-preview-index.sqlite3'
VERSION = 1
META_KEYS = ('render_state', 'provenance', 'source_identity',
             'compact_preview_source', 'preview_revision', 'video_sections')


def report_identity(path):
    stat = os.stat(path)
    return [stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns]


def _index_path(report_path):
    path = Path(report_path)
    index = path.with_name(NAME)
    if index.is_symlink() or path.is_symlink():
        raise ValueError('Review index or report is a symlink')
    return index


def _open_read(index):
    # A missing index must not be created merely because a preview was read.
    return sqlite3.connect('file:%s?mode=ro' % index.as_posix(), uri=True, timeout=2)


class IndexedRows:
    """Bounded-memory, read-only report row accessor with revision fencing."""
    def __init__(self, report_path, index_path, identity, count):
        self.report_path = str(report_path)
        self.index_path = str(index_path)
        self.identity = identity
        self.count = count

    def __len__(self):
        return self.count

    def __getitem__(self, key):
        if not isinstance(key, int):
            raise TypeError('Review preview indices must be integers')
        if key < 0:
            key += self.count
        if not 0 <= key < self.count:
            raise IndexError(key)
        try:
            if report_identity(self.report_path) != self.identity:
                abort(409, description='Review changed. Reload its previews.')
            with _open_read(Path(self.index_path)) as db:
                record = db.execute('SELECT record FROM rows WHERE row_index=?', (key,)).fetchone()
                if record is None:
                    abort(409, description='Review preview index changed. Reload.')
                return json.loads(record[0])
        except (OSError, sqlite3.DatabaseError):
            abort(503, description='Review preview index unavailable. Retry shortly.')

    def __iter__(self):
        for i in range(self.count):
            yield self[i]


def load(report_path):
    """Return a read-only lightweight document or None when absent/stale."""
    index = _index_path(report_path)
    if not index.is_file():
        return None
    try:
        expected = report_identity(report_path)
        with _open_read(index) as db:
            fields = dict(db.execute('SELECT name, value FROM metadata').fetchall())
            if int(fields.get('version', '-1')) != VERSION:
                return None
            if json.loads(fields['identity']) != expected:
                return None
            count = int(fields['count'])
            if count < 0:
                return None
            meta = json.loads(fields['doc'])
            if not isinstance(meta.get('render_state'), dict):
                return None
            meta['detections'] = IndexedRows(report_path, index, expected, count)
            return meta
    except (OSError, ValueError, KeyError, TypeError, sqlite3.DatabaseError):
        return None


def prepare(report_path, doc):
    """Atomically publish an index from an already parsed authoritative report.

    On any failure the previous revision's index and the authoritative report
    remain intact. The report is rechecked immediately before publication.
    """
    index = _index_path(report_path)
    expected = report_identity(report_path)
    if load(report_path) is not None:
        return False
    if not isinstance(doc.get('detections'), list):
        raise ValueError('Index source must be a full report')
    header = {key: doc[key] for key in META_KEYS if key in doc}
    directory = index.parent
    temporary = None
    try:
        fd, temporary = tempfile.mkstemp(prefix='.review-index-', suffix='.sqlite3', dir=str(directory))
        os.chmod(temporary, 0o600)
        with os.fdopen(fd, 'wb'):
            pass
        with sqlite3.connect(temporary, timeout=5) as db:
            db.execute('PRAGMA journal_mode=DELETE')
            db.execute('PRAGMA cache_size=-4096')
            db.execute('CREATE TABLE metadata (name TEXT PRIMARY KEY, value TEXT NOT NULL)')
            db.execute('CREATE TABLE rows (row_index INTEGER PRIMARY KEY, record TEXT NOT NULL)')
            db.executemany('INSERT INTO metadata VALUES (?,?)', [
                ('version', str(VERSION)),
                ('identity', json.dumps(expected)),
                ('count', str(len(doc['detections']))),
                ('doc', json.dumps(header, separators=(',', ':'), ensure_ascii=False)),
            ])
            batch = []
            for i, row in enumerate(doc['detections']):
                batch.append((i, json.dumps(row, separators=(',', ':'), ensure_ascii=False)))
                if len(batch) >= 512:
                    db.executemany('INSERT INTO rows VALUES (?,?)', batch)
                    batch.clear()
            if batch:
                db.executemany('INSERT INTO rows VALUES (?,?)', batch)
            db.commit()
        if report_identity(report_path) != expected:
            return False
        os.replace(temporary, index)
        temporary = None
        return True
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
