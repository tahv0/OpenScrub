"""On-disk, revision-bound metadata for individual Review preview requests.

The authoritative report.json is never changed by this index. A full report is
read only once to construct/reconstruct the index, then each thumbnail fetch
reads exactly one row from SQLite. No video bytes or plaintext OCR hints live
in the index beyond what was already in the report. Index files are job-local,
vault-managed and disposable; rebuilding must never change review decisions.
"""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import tempfile

from flask import abort

NAME = 'review-preview-index.sqlite3'
VERSION = 3
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
    return sqlite3.connect(index.resolve().as_uri() + '?mode=ro', uri=True, timeout=2)


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
            with closing(_open_read(Path(self.index_path))) as db:
                record = db.execute('SELECT record FROM rows WHERE row_index=?', (key,)).fetchone()
                if record is None:
                    abort(409, description='Review preview index changed. Reload.')
                return json.loads(record[0])
        except (OSError, sqlite3.DatabaseError):
            abort(503, description='Review preview index unavailable. Retry shortly.')

    def __iter__(self):
        for i in range(self.count):
            yield self[i]

    def member_count(self, index):
        """Find exact person/track membership without reading every 4K row."""
        row = self[index]
        category = str(row.get('category', ''))
        person, track = int(row.get('person', -1)), int(row.get('track', -1))
        if person < 0 and track < 0:
            return 1
        column, value = ('person', person) if person >= 0 else ('track', track)
        try:
            if report_identity(self.report_path) != self.identity:
                abort(409, description='Review changed. Reload its previews.')
            with closing(_open_read(Path(self.index_path))) as db:
                return int(db.execute('SELECT count(*) FROM rows WHERE '
                    'category=? AND '+column+'=?', (category, value)).fetchone()[0])
        except (OSError, sqlite3.DatabaseError):
            abort(503, description='Review preview index unavailable. Retry shortly.')


def load(report_path):
    """Return a read-only lightweight document or None when absent/stale."""
    index = _index_path(report_path)
    if not index.is_file():
        return None
    try:
        expected = report_identity(report_path)
        with closing(_open_read(index)) as db:
            fields = dict(db.execute(
                "SELECT name,value FROM metadata WHERE name IN ('version','identity','count','doc')"
            ).fetchall())
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



def public_item(index, d):
    """Stable, lightweight detection fields already exposed by /detections."""
    return dict(i=index, category=d.get('category', ''), text=d.get('text', ''),
                t_start=d['t_start'], t_end=round(d['t_end'], 2),
                enabled=d.get('enabled', True),
                track=d.get('track', -1), person=d.get('person', -1),
                confidence=d.get('confidence', 0),
                verified_label=d.get('verified_label', ''),
                human_confirmation=d.get('human_confirmation'),
                confirmed_finding_id=d.get('confirmed_finding_id'),
                confirmed_finding_revision=d.get('confirmed_finding_revision'),
                output_choice_explicit=bool(d.get('output_choice_explicit')),
                plate_text_evidence=d.get('plate_text_evidence'),
                learning_conflict=d.get('learning_conflict', ''),
                learning_score=d.get('learning_score'),
                plate_verification=d.get('plate_verification'),
                fallback_reason=d.get('fallback_reason', ''),
                human_region_confirmed=bool(d.get('human_region_confirmed')),
                zone_dropped=bool(d.get('zone_dropped')),
                shaped=bool(d.get('poly')))


def public_listing(doc):
    """Serialize the stable Review GET response once after report publication.

    learned_candidates is an independent library and is inserted dynamically
    by the HTTP route. The preview index stores only data tied to report.json.
    """
    rows = doc['detections']
    state = doc['render_state']
    provenance = doc.get('provenance') or {}
    data = dict(
        detections=[public_item(i, row) for i, row in enumerate(rows)],
        learning=doc.get('learning'),
        video_id=provenance.get('original_input_sha256') or provenance.get('input_sha256'),
        plate_text_search=doc.get('plate_text_search'),
        refinement=doc.get('refinement'),
        verification=doc.get('verification'),
        verification_history=doc.get('verification_history'),
        indexed_frames=any(d.get('frame_index', -1) >= 0 for d in rows),
        frame_count=len(state['cum']), fps=state['fps'],
        duration=len(state['cum'])/state['fps'])
    return json.dumps(data, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def read_listing(report_path):
    """Get an exact-revision cached JSON response without parsing report.json."""
    index = _index_path(report_path)
    if not index.is_file():
        return None
    try:
        identity = report_identity(report_path)
        with closing(_open_read(index)) as db:
            values = dict(db.execute(
                "SELECT name,value FROM metadata WHERE name IN ('version','identity','listing_identity','listing')"
            ).fetchall())
            if (int(values.get('version', '-1')) != VERSION
                    or json.loads(values.get('listing_identity') or values['identity']) != identity):
                return None
            payload = values.get('listing')
            if not payload or not payload.endswith('}'):
                return None
        if report_identity(report_path) != identity:
            return None
        return payload
    except (OSError, ValueError, KeyError, TypeError, sqlite3.DatabaseError):
        return None


def publish_listing(report_path, doc, expected_identity=None):
    """Refresh the full Review GET response without rebuilding per-row indexes.

    Saving a report changes its inode, invalidating a formerly fast SQLite
    listing. Rebuilding tens of thousands of indexed rows on a Windows-mounted
    volume would put that cost straight back on every Save. Instead, publish
    the new listing and its *own* report identity in one small transaction.
    Existing row-index identity stays unchanged so stale geometry can never
    be returned to previews; a separate rebuild can refresh those rows.
    Missing indexes use an atomic, restricted-permissions listing-only DB.
    All source data remains in the vault-managed job directory.
    """
    index = _index_path(report_path)
    expected = report_identity(report_path)
    # Callers in background workers must pass the exact revision from which
    # their in-memory document was read. Otherwise a newer report could be
    # accidentally labeled with stale rows after a concurrent Save.
    if expected_identity is not None and expected != list(expected_identity):
        return False
    payload = public_listing(doc)
    values = (
        ('version', str(VERSION)),
        ('listing_identity', json.dumps(expected, separators=(',', ':'))),
        ('listing', payload),
    )

    def write(db):
        db.execute('CREATE TABLE IF NOT EXISTS metadata ('
                   'name TEXT PRIMARY KEY, value TEXT NOT NULL)')
        db.executemany(
            'INSERT INTO metadata(name,value) VALUES (?,?) '
            'ON CONFLICT(name) DO UPDATE SET value=excluded.value', values)
        # Do not acknowledge a listing from a report replaced by another
        # render/scan while this (potentially expensive) JSON was assembled.
        if report_identity(report_path) != expected:
            db.rollback()
            return False
        db.commit()
        return True

    if index.is_file():
        with closing(sqlite3.connect(index, timeout=5)) as db:
            return write(db)
    fd, temporary = tempfile.mkstemp(prefix='.review-listing-', suffix='.sqlite3',
                                      dir=str(index.parent))
    try:
        os.chmod(temporary, 0o600)
        os.close(fd)
        with closing(sqlite3.connect(temporary, timeout=5)) as db:
            if not write(db):
                return False
        if report_identity(report_path) != expected:
            return False
        # Another cache builder may have published an index since our check;
        # its listing is also revision-checked on every read.
        os.replace(temporary, index)
        temporary = None
        return True
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass


def prepare(report_path, doc, expected_identity=None):
    """Atomically publish an index from an already parsed authoritative report.

    On any failure the previous revision's index and the authoritative report
    remain intact. The report is rechecked immediately before publication.
    """
    index = _index_path(report_path)
    expected = report_identity(report_path)
    if expected_identity is not None and expected != list(expected_identity):
        return False
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
        with closing(sqlite3.connect(temporary, timeout=5)) as db:
            db.execute('PRAGMA journal_mode=DELETE')
            db.execute('PRAGMA cache_size=-4096')
            db.execute('CREATE TABLE metadata (name TEXT PRIMARY KEY, value TEXT NOT NULL)')
            db.execute('CREATE TABLE rows (row_index INTEGER PRIMARY KEY, '
                       'record TEXT NOT NULL, category TEXT NOT NULL, '
                       'track INTEGER NOT NULL, person INTEGER NOT NULL)')
            db.execute('CREATE INDEX rows_track ON rows(category,track)')
            db.execute('CREATE INDEX rows_person ON rows(category,person)')
            db.executemany('INSERT INTO metadata VALUES (?,?)', [
                ('version', str(VERSION)),
                ('identity', json.dumps(expected)),
                ('listing_identity', json.dumps(expected)),
                ('count', str(len(doc['detections']))),
                ('doc', json.dumps(header, separators=(',', ':'), ensure_ascii=False)),
                ('listing', public_listing(doc)),
            ])
            batch = []
            for i, row in enumerate(doc['detections']):
                batch.append((i, json.dumps(row, separators=(',', ':'), ensure_ascii=False),
                              str(row.get('category', '')), int(row.get('track', -1)),
                              int(row.get('person', -1))))
                if len(batch) >= 512:
                    db.executemany('INSERT INTO rows VALUES (?,?,?,?,?)', batch)
                    batch.clear()
            if batch:
                db.executemany('INSERT INTO rows VALUES (?,?,?,?,?)', batch)
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
