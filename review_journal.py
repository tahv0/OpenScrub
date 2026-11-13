"""Crash-safe, job-local SQLite journal for small human Review corrections.

report.json is the immutable scan/snapshot input while a review is in progress.
A confirmation/corner edit updates only its group and anchor in SQLite. Consumers
that need a report (render, rescan, export, training) publish the journal as a
single atomic report snapshot first. No uncommitted or ambiguous edit may be
silently discarded on restart or after an unrelated report replacement.
"""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import threading
import uuid

NAME = 'review-journal.sqlite3'
MARKER = '_review_journal_snapshot'
_LOCKS = {}
_LOCKS_LOCK = threading.Lock()
_READ_CACHE = {}
# Small in-memory reports still contain thousands of rows. Compute group
# cardinalities once per actual underlying report list, not on every click.
_COUNT_CACHE = {}


class ConflictError(ValueError):
    """The report changed without first publishing its pending review edits."""


def _lock(directory):
    directory = str(Path(directory).resolve())
    with _LOCKS_LOCK:
        return _LOCKS.setdefault(directory, threading.RLock())


def _paths(directory):
    root = Path(directory)
    database, report = root / NAME, root / 'report.json'
    if database.is_symlink() or report.is_symlink():
        raise ConflictError('The review journal or report is a symlink.')
    return database, report


def _stamp(report):
    stat = report.stat()
    return json.dumps([stat.st_dev, stat.st_ino, stat.st_size,
                       stat.st_mtime_ns, stat.st_ctime_ns], separators=(',', ':'))


def _connection(path, create=False):
    if not create and not path.exists():
        return None
    db = sqlite3.connect(str(path), timeout=15)
    db.execute('PRAGMA busy_timeout=15000')
    if create:
        if path.is_symlink():
            db.close()
            raise ConflictError('Review journal must not be a symlink.')
        os.chmod(path, 0o600)
        db.execute('PRAGMA synchronous=FULL')
        db.execute('CREATE TABLE IF NOT EXISTS meta (name TEXT PRIMARY KEY, value TEXT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS groups ('
                   'kind TEXT NOT NULL, category TEXT NOT NULL, member INTEGER NOT NULL, '
                   'anchor INTEGER NOT NULL, patch TEXT NOT NULL, '
                   'PRIMARY KEY(kind,category,member))')
        db.execute('CREATE TABLE IF NOT EXISTS anchors ('
                   'row_index INTEGER PRIMARY KEY, patch TEXT NOT NULL)')
        db.commit()
    return db


def _meta(db):
    return dict(db.execute('SELECT name,value FROM meta'))


def _set(db, key, value):
    db.execute('INSERT INTO meta(name,value) VALUES (?,?) '
               'ON CONFLICT(name) DO UPDATE SET value=excluded.value', (key, str(value)))


def _recover(db, report, meta, current):
    """Finish an interrupted atomic report publication only with its marker."""
    expected = meta.get('baseline')
    if expected is None or expected == current:
        return
    # A previously completed snapshot leaves an empty journal. A new scan,
    # rescan or section publish may legitimately replace that snapshot.
    if (not db.execute('SELECT 1 FROM groups LIMIT 1').fetchone()
            and not db.execute('SELECT 1 FROM anchors LIMIT 1').fetchone()):
        db.execute('BEGIN IMMEDIATE')
        _set(db, 'baseline', current)
        db.execute('DELETE FROM meta WHERE name=?', ('publishing',))
        db.commit()
        return
    pending = meta.get('publishing')
    if pending:
        try:
            with report.open(encoding='utf-8') as source:
                published = json.load(source).get(MARKER)
        except (OSError, ValueError, TypeError):
            published = None
        if published == pending:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM groups')
            db.execute('DELETE FROM anchors')
            _set(db, 'baseline', current)
            db.execute('DELETE FROM meta WHERE name=?', ('publishing',))
            db.commit()
            return
    raise ConflictError('The Review report changed while SQLite corrections were pending. '
                        'The corrections were retained; do not render or train until the conflict is resolved.')


def _read(directory):
    database, report = _paths(directory)
    if not database.exists():
        return {}, {}
    # Browser image GETs can arrive hundreds of times while scrolling. Most
    # must not even open SQLite: stat the job-local DB and reuse an immutable
    # group/anchor snapshot until a real write or report replacement.
    st = database.stat()
    signature = (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns,
                 st.st_ctime_ns, _stamp(report))
    cached = _READ_CACHE.get(str(database))
    if cached is not None and cached[0] == signature:
        return cached[1], cached[2]
    db = _connection(database)
    try:
        meta = _meta(db)
        current = _stamp(report)
        _recover(db, report, meta, current)
        groups = {}
        for kind, category, member, anchor, value in db.execute(
                'SELECT kind,category,member,anchor,patch FROM groups'):
            groups[(kind, category, member)] = (anchor, json.loads(value))
        anchors = {i: json.loads(value) for i, value in db.execute(
            'SELECT row_index,patch FROM anchors')}
        newstat = database.stat()
        signature = (newstat.st_dev, newstat.st_ino, newstat.st_size,
                     newstat.st_mtime_ns, newstat.st_ctime_ns, _stamp(report))
        # No caller mutates either snapshot: patch_row always makes a copy.
        _READ_CACHE[str(database)] = (signature, groups, anchors)
        if len(_READ_CACHE) > 12:
            _READ_CACHE.pop(next(iter(_READ_CACHE)))
        return groups, anchors
    finally:
        db.close()


def key(row, index):
    category = row.get('category', '')
    person = int(row.get('person', -1))
    track = int(row.get('track', -1))
    if person >= 0:
        return 'person', category, person
    if track >= 0:
        return 'track', category, track
    return 'row', category, int(index)


def patch_row(row, index, groups, anchors):
    group = groups.get(key(row, index))
    anchor = anchors.get(index)
    if group is None and anchor is None:
        return row
    result = dict(row)
    if group is not None:
        source_index, fields = group
        if fields.get('_remove_plate_verification'):
            result.pop('plate_verification', None)
        result.update({field: value for field, value in fields.items()
                       if not field.startswith('_') and field != 'human_confirmation'})
        if 'human_confirmation' in fields:
            confirmation = dict(fields['human_confirmation'])
            confirmation['propagated'] = index != source_index
            result['human_confirmation'] = confirmation
    if anchor:
        result.update({field: value for field, value in anchor.items()
                       if not field.startswith('_')})
        if (group is None or index == group[0]) and 'human_confirmation' in result:
            receipt_id = anchor.get('confirmed_finding_id', result.get('confirmed_finding_id'))
            receipt_revision = anchor.get('confirmed_finding_revision')
            if receipt_id and receipt_revision:
                result['human_confirmation'] = dict(
                    result['human_confirmation'], id=receipt_id, revision=receipt_revision)
    return result


class PatchedRows:
    def __init__(self, rows, groups, anchors):
        self.rows, self.groups, self.anchors = rows, groups, anchors

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, index):
        if isinstance(index, slice):
            return [self[i] for i in range(*index.indices(len(self)))]
        return patch_row(self.rows[index], index, self.groups, self.anchors)

    def __iter__(self):
        for index in range(len(self)):
            yield self[index]

    def member_count(self, index):
        if hasattr(self.rows, 'member_count'):
            return self.rows.member_count(index)
        return member_count(self.rows, index)


def member_count(rows, index):
    """O(1) group counts after one bounded in-memory index build.

    IndexedRows has its own SQL index. For small reports kept in RAM, reuse
    one count map per source list rather than walking every detection after
    each human classification. Keep the referenced list to avoid id reuse.
    """
    if not isinstance(rows, list):
        row = rows[index]
        return sum(key(other, i) == key(row, index) for i, other in enumerate(rows))
    cached = _COUNT_CACHE.get(id(rows))
    if cached is None or cached[0] is not rows:
        counts = {}
        for i, row in enumerate(rows):
            group = key(row, i)
            counts[group] = counts.get(group, 0) + 1
        _COUNT_CACHE.clear()
        _COUNT_CACHE[id(rows)] = (rows, counts)
    else:
        counts = cached[1]
    return counts.get(key(rows[index], index), 1)


def view(directory, doc):
    """A small, read-only overlay on an indexed or in-memory report."""
    with _lock(directory):
        groups, anchors = _read(directory)
    if not groups and not anchors:
        return doc
    out = dict(doc)
    out['detections'] = PatchedRows(doc['detections'], groups, anchors)
    out['render_required'] = True
    return out


def apply(directory, doc):
    """Mutate an independent full report with committed SQLite corrections."""
    with _lock(directory):
        groups, anchors = _read(directory)
    if groups or anchors:
        doc['detections'] = [patch_row(row, i, groups, anchors)
                             for i, row in enumerate(doc['detections'])]
        doc['render_required'] = True
    return doc


def has_changes(directory):
    with _lock(directory):
        groups, anchors = _read(directory)
        return bool(groups or anchors)


def overlay_listing(directory, listing):
    """Update a cached public Review listing without opening report.json.

    Callers provide the existing decoded listing, not the authoritative full
    frame timeline. This only runs when SQLite contains actual corrections.
    """
    with _lock(directory):
        groups, anchors = _read(directory)
    if groups or anchors:
        rows = listing['detections']
        for index, item in enumerate(rows):
            updated = patch_row(item, index, groups, anchors)
            if updated is item:
                continue
            # Never expose internal receipt keys or duplicate archive data.
            public = set(item)
            rows[index] = {key: value for key, value in updated.items()
                           if key in public}
    return listing


def write(directory, row, index, group_fields, anchor_fields=None):
    """One durable transaction for all members of a track/person group.

    The caller must validate the frame, geometry and archive revision first.
    This routine neither reads nor writes the large report.json contents.
    """
    with _lock(directory):
        database, report = _paths(directory)
        with closing(_connection(database, create=True)) as db:
            current = _stamp(report)
            meta = _meta(db)
            _recover(db, report, meta, current)
            group = key(row, index)
            existing = db.execute(
                'SELECT patch FROM groups WHERE kind=? AND category=? AND member=?',
                group).fetchone()
            patch = json.loads(existing[0]) if existing else {}
            patch.update(group_fields)
            if 'human_confirmation' in group_fields:
                # Only the most recent explicit confirmation is the group's anchor.
                anchor_index = index
            else:
                previous = db.execute(
                    'SELECT anchor FROM groups WHERE kind=? AND category=? AND member=?',
                    group).fetchone()
                anchor_index = previous[0] if previous else index
            db.execute('BEGIN IMMEDIATE')
            _set(db, 'baseline', current if meta.get('baseline') is None else meta['baseline'])
            db.execute(
                'INSERT INTO groups(kind,category,member,anchor,patch) VALUES (?,?,?,?,?) '
                'ON CONFLICT(kind,category,member) DO UPDATE SET '
                'anchor=excluded.anchor,patch=excluded.patch',
                (*group, anchor_index, json.dumps(patch, separators=(',', ':'))))
            if anchor_fields:
                prior = db.execute('SELECT patch FROM anchors WHERE row_index=?',
                                   (index,)).fetchone()
                updated = json.loads(prior[0]) if prior else {}
                updated.update(anchor_fields)
                db.execute(
                    'INSERT INTO anchors(row_index,patch) VALUES (?,?) '
                    'ON CONFLICT(row_index) DO UPDATE SET patch=excluded.patch',
                    (index, json.dumps(updated, separators=(',', ':'))))
            db.commit()
            _READ_CACHE.pop(str(database), None)


def publish(directory, document=None):
    """Atomically materialize pending corrections, then retire the journal.

    A crash after os.replace but before SQLite acknowledgment is recovered via
    the unique marker in the published report; a crash before publication
    retains the old report and all SQLite changes.
    """
    with _lock(directory):
        database, report = _paths(directory)
        if not database.exists():
            return False
        with closing(_connection(database)) as db:
            meta = _meta(db)
            current = _stamp(report)
            _recover(db, report, meta, current)
            groups = list(db.execute('SELECT kind,category,member,anchor,patch FROM groups'))
            anchors = {i: json.loads(v) for i, v in db.execute(
                'SELECT row_index,patch FROM anchors')}
            if not groups and not anchors:
                return False
            if document is None:
                with report.open(encoding='utf-8') as source:
                    document = json.load(source)
            assembled = {(kind,category,member):(anchor,json.loads(patch))
                         for kind,category,member,anchor,patch in groups}
            document['detections'] = [
                patch_row(row, index, assembled, anchors)
                for index, row in enumerate(document['detections'])]
            document['render_required'] = True
            token = uuid.uuid4().hex
            document[MARKER] = token
            db.execute('BEGIN IMMEDIATE')
            _set(db, 'publishing', token)
            db.commit()
            # The journal stays valid and authoritative if the report write fails.
            import stop_review
            stop_review.atomic_report(str(report), document)
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM groups')
            db.execute('DELETE FROM anchors')
            _set(db, 'baseline', _stamp(report))
            db.execute('DELETE FROM meta WHERE name=?', ('publishing',))
            db.commit()
            _READ_CACHE.pop(str(database), None)
            return True
