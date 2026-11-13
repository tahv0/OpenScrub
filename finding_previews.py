"""Bounded job-local JPEGs from already decoded, unpainted scan frames.

Public rows may be Detection instances or dictionaries. cbox is in content
coordinates, aoff is the content-to-source offset at capture, track >= 0 is
an object identity, and frame_index >= 0 pins a source frame. No function in
this module opens a video. ``store`` accepts an already decoded legacy crop.

All geometry (box/crop/points/width/height) uses original source coordinates.
Display coordinates are (source_x-crop[0])*scale_x, similarly for y. JPEGs
are <=640 px at quality 65. Lookup defaults to the exact requested frame;
callers must explicitly opt into a representative from a different frame
and use the returned actual frame and geometry, never the requested row's.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import threading

import cv2
import numpy as np

# Item count is only a safety ceiling; the 64 MiB byte budget is the real disk bound.
MAX_ITEMS = 10000
MAX_BYTES = 64 * 1024 * 1024
MAX_PER_CAPTURE = 12
_LOCK = threading.RLock()
_SCHEMA_READY = set()
_KEY = re.compile(r'[a-f0-9]{64}\Z')


class PreviewLimitError(ValueError):
    """The bounded cache could not accept a new representative."""


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _hash(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _row(value):
    return value if isinstance(value, dict) else vars(value)


def _box(value):
    result = [float(x) for x in value]
    if (len(result) != 4 or not all(math.isfinite(x) for x in result)
            or result[2] <= result[0] or result[3] <= result[1]):
        raise ValueError('invalid source box')
    return result


def _offset(value):
    result = [float(x) for x in value]
    if len(result) != 2 or not all(math.isfinite(x) for x in result):
        raise ValueError('invalid source offset')
    return result


def _db(job_dir, create=False):
    directory = Path(job_dir) / 'compact_previews'
    if directory.is_symlink():
        raise ValueError('preview cache must be confined, not a symlink')
    if not directory.exists():
        if not create:
            return None
        directory.mkdir(mode=0o700)
    path = directory / 'index.sqlite3'
    for suffix in ('', '-journal', '-wal', '-shm'):
        if Path(str(path) + suffix).is_symlink():
            raise ValueError('preview database must be confined, not a symlink')
    existed = path.exists()
    if not create and not existed:
        return None
    connection = sqlite3.connect(str(path), timeout=2)
    ready_key = str(path)
    if create and (not existed or ready_key not in _SCHEMA_READY):
        os.chmod(path, 0o600)
        connection.execute('CREATE TABLE IF NOT EXISTS previews ('
                           'key TEXT PRIMARY KEY, group_key TEXT UNIQUE, '
                           'frame INTEGER, category TEXT, track INTEGER, '
                           'metadata TEXT NOT NULL, jpeg BLOB NOT NULL)')
        connection.execute('CREATE INDEX IF NOT EXISTS frame_category '
                           'ON previews(frame,category)')
        connection.execute('CREATE INDEX IF NOT EXISTS track_category '
                           'ON previews(track,category)')
        connection.execute('CREATE TABLE IF NOT EXISTS settings '
                           '(key TEXT PRIMARY KEY, value INTEGER)')
        # Old caches predate the O(1) counters. Compute them exactly once on
        # first open after upgrade, then maintain them transactionally.
        connection.execute("INSERT OR IGNORE INTO settings "
                           "SELECT 'count', count(*) FROM previews")
        connection.execute("INSERT OR IGNORE INTO settings "
                           "SELECT 'bytes', coalesce(sum(length(jpeg) + "
                           "length(CAST(metadata AS BLOB))),0) FROM previews")
        connection.commit()
        # Apply the physical ceiling AFTER schema/index creation. SQLite
        # refuses to lower max_page_count below the current page_count; doing
        # this before DDL let later schema pages silently raise the effective
        # ceiling and explicit review crops could grow past MAX_BYTES.
        page_size = int(connection.execute('PRAGMA page_size').fetchone()[0])
        page_limit = max(8, MAX_BYTES // max(1, page_size))
        page_count = int(connection.execute('PRAGMA page_count').fetchone()[0])
        if page_count <= page_limit:
            connection.execute('PRAGMA max_page_count=%d' % page_limit)
        _SCHEMA_READY.add(ready_key)
    return connection


def _set_total(db, key, value):
    db.execute("INSERT INTO settings(key,value) VALUES (?,?) "
               "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
               (key, int(value)))


def _totals(db):
    values = dict(db.execute(
        "SELECT key,value FROM settings WHERE key IN ('count','bytes','truncated')"))
    if 'count' not in values or 'bytes' not in values:
        count, size = db.execute(
            'SELECT count(*), coalesce(sum(length(jpeg) + '
            'length(CAST(metadata AS BLOB))),0) FROM previews').fetchone()
        _set_total(db, 'count', count)
        _set_total(db, 'bytes', size)
        values.update(count=int(count), bytes=int(size))
    return (int(values.get('count', 0)), int(values.get('bytes', 0)),
            bool(values.get('truncated', 0)))


def _truncate(db):
    # Once saturated, later frames must not create a disk write per object.
    db.execute("INSERT OR IGNORE INTO settings VALUES ('truncated',1)")


def _group(row, content, frame_index, fps):
    category, track = str(row.get('category', '')), int(row.get('track', -1))
    if track >= 0:
        return _hash([category, 'track', track])
    # Dense scan tracks are often assigned only after scanning. Nearby boxes
    # in a ten-second window share one sample, avoiding per-frame JPEGs.
    center = [(content[0]+content[2])/2, (content[1]+content[3])/2]
    quantized = [int(round(v / 32)) for v in center]
    quantized += [int(round((content[2]-content[0]) / 32)),
                  int(round((content[3]-content[1]) / 32))]
    return _hash([category, str(row.get('text', '')).casefold()[:1024],
                  quantized, int(frame_index / fps / 10)])


def _points(row, box):
    quad = row.get('plate_quad') or [[0, 0], [1, 0], [1, 1], [0, 1]]
    if len(quad) != 4:
        raise ValueError('invalid preview quadrilateral')
    result = [[box[0]+float(x)*(box[2]-box[0]),
               box[1]+float(y)*(box[3]-box[1])] for x, y in quad]
    if not all(math.isfinite(v) for point in result for v in point):
        raise ValueError('non-finite preview geometry')
    return result


def _fits(points, crop):
    return all(crop[0] <= x <= crop[2] and crop[1] <= y <= crop[3] for x, y in points)


def _metadata(row, frame_index, fps, width, height, offset, crop, source=None):
    content = _box(row['cbox'])
    box = [content[0]+offset[0], content[1]+offset[1],
           content[2]+offset[0], content[3]+offset[1]]
    points = _points(row, box)
    if not _fits(points, crop):
        raise ValueError('preview geometry lies outside the crop')
    category, track = str(row.get('category', '')), int(row.get('track', -1))
    key = _hash([frame_index, fps, width, height, content, offset, category,
                 str(row.get('text', ''))[:1024]])
    meta = dict(key=key, frame=frame_index, frame_index=frame_index,
                t=frame_index/fps, fps=fps, width=width, height=height,
                box=box, content_box=content, offset=offset, crop=list(crop),
                points=points, category=category, track=track,
                text=str(row.get('text', ''))[:1024], source=source,
                source_token=key)
    # A queue entry can be bound back to the exact sample without guessing a
    # transient report row number. It does not contain a human classification.
    meta['detection'] = dict(t_start=frame_index/fps, t_end=frame_index/fps,
                             last_seen=frame_index/fps, frame_index=frame_index,
                             cbox=content, aoff=offset, category=category,
                             text=meta['text'], track=track,
                             confidence=float(row.get('confidence', 0)))
    meta['preview_token'] = _hash([key, points])
    if source is not None and len(_json(source).encode()) > 4096:
        raise ValueError('preview source identity is too large')
    return meta


def _encode(meta, pixels):
    if not isinstance(pixels, np.ndarray) or pixels.dtype != np.uint8 or pixels.ndim != 3 or pixels.shape[2] != 3:
        raise ValueError('preview pixels must be uint8 BGR')
    height, width = pixels.shape[:2]
    if not width or not height:
        raise ValueError('empty preview crop')
    factor = min(1., 640/max(width, height))
    iw, ih = max(1, round(width*factor)), max(1, round(height*factor))
    if factor < 1:
        pixels = cv2.resize(pixels, (iw, ih), interpolation=cv2.INTER_AREA)
    success, encoded = cv2.imencode('.jpg', pixels, [cv2.IMWRITE_JPEG_QUALITY, 65])
    if not success:
        raise OSError('could not encode compact preview')
    meta = dict(meta, image_width=iw, image_height=ih,
                scale_x=iw/(meta['crop'][2]-meta['crop'][0]),
                scale_y=ih/(meta['crop'][3]-meta['crop'][1]))
    return meta, encoded.tobytes()


def _insert(db, group, meta, jpeg, totals=None):
    count, size = (_totals(db)[:2] if totals is None else totals)
    serialized = _json(meta)
    needed = len(serialized.encode()) + len(jpeg)
    if count >= MAX_ITEMS or size + needed > MAX_BYTES:
        _truncate(db)
        return False
    try:
        db.execute('INSERT INTO previews VALUES (?,?,?,?,?,?,?)',
                   (meta['key'], group, meta['frame'], meta['category'], meta['track'],
                    serialized, jpeg))
        _set_total(db, 'count', count + 1)
        _set_total(db, 'bytes', size + needed)
    except sqlite3.IntegrityError:
        return False
    except sqlite3.OperationalError as exc:
        if 'full' not in str(exc).lower():
            raise
        db.rollback()
        _truncate(db)
        return False
    return True


def _insert_explicit(db, group, meta, jpeg):
    """Make room for an explicit request, retaining all rows if it cannot fit.

    Oldest insertion wins eviction order; reads need no LRU timestamp writes.
    SQLITE_FULL can roll back the whole transaction, including deletions, so
    each retry repeats its eviction plan in a fresh transaction. At most one
    retry per existing row is allowed, and only this job's previews are touched.
    """
    serialized = _json(meta)
    needed = len(serialized.encode()) + len(jpeg)
    if MAX_ITEMS < 1 or needed > MAX_BYTES:
        _truncate(db)
        return False
    eviction_floor, attempts = 0, None
    while attempts is None or attempts > 0:
        db.execute('BEGIN IMMEDIATE')
        records = db.execute('SELECT key, length(jpeg) + length(CAST(metadata AS BLOB)) '
                             'FROM previews ORDER BY rowid').fetchall()
        if attempts is None:
            attempts = len(records) + 1
        attempts -= 1
        if any(key == meta['key'] for key, _ in records):
            db.rollback()
            return False
        count, size = len(records), sum(size for _, size in records)
        victims = []
        for key, record_size in records:
            if (len(victims) >= eviction_floor and count < MAX_ITEMS
                    and size + needed <= MAX_BYTES):
                break
            victims.append((key,))
            count -= 1
            size -= record_size
        try:
            db.executemany('DELETE FROM previews WHERE key=?', victims)
            if victims:
                _truncate(db)
            db.execute('INSERT INTO previews VALUES (?,?,?,?,?,?,?)',
                       (meta['key'], group, meta['frame'], meta['category'], meta['track'],
                        serialized, jpeg))
            _set_total(db, 'count', count + 1)
            _set_total(db, 'bytes', size + needed)
        except sqlite3.IntegrityError:
            db.rollback()
            return False
        except sqlite3.OperationalError as exc:
            db.rollback()
            if 'full' not in str(exc).lower():
                raise
            if len(victims) == len(records):
                break
            eviction_floor = len(victims) + 1
        else:
            return True
    _truncate(db)
    return False


def capture(job_dir, frame_bgr, frame_index, fps, detections, source=None, seen_groups=None, previous_stats=None):
    """Capture <=12 new groups per call; report bounded sampling honestly.

    The caller retains ownership of frame_bgr; pixels are read synchronously
    and never mutated or retained. Sampled groups are not replaced by later
    frames. No labels are inferred from detection/checker confidence.
    """
    fps = float(fps)
    frame_index = int(frame_index)
    if not math.isfinite(fps) or fps <= 0 or frame_index < 0:
        raise ValueError('invalid capture timeline')
    if (not isinstance(frame_bgr, np.ndarray) or frame_bgr.ndim != 3
            or frame_bgr.shape[2] != 3 or frame_bgr.dtype != np.uint8):
        raise ValueError('source pixels must be uint8 BGR')
    height, width = frame_bgr.shape[:2]
    prior = previous_stats or {}
    stats = dict(added=0, duplicates=0, invalid=0, skipped=0,
                 total=int(prior.get('total', 0)), bytes=int(prior.get('bytes', 0)),
                 truncated=bool(prior.get('truncated', False)))
    candidates = []
    for detection in detections:
        try:
            row = _row(detection)
            content = _box(row['cbox'])
            offset = _offset(row.get('aoff', [0, 0]))
            exact = int(row.get('frame_index', -1))
            if exact >= 0 and exact != frame_index:
                raise ValueError('detection belongs to a different frame')
            group = _group(row, content, frame_index, fps)
            if seen_groups is not None and group in seen_groups:
                stats['duplicates'] += 1
                continue
            candidates.append((row, content, offset, group))
        except (ValueError, TypeError, KeyError, OverflowError):
            stats['invalid'] += 1

    # Dense plate/face detectors can emit the same preview group on hundreds
    # of consecutive frames. The per-scan seen set makes those frames do zero
    # SQLite work instead of opening/querying the cache every time.
    if not candidates:
        return stats

    with _LOCK:
        db = _db(job_dir, create=True)
        try:
            count, size, truncated = _totals(db)
            stats.update(total=count, bytes=size,
                         truncated=stats['truncated'] or truncated)
            for row, content, offset, group in candidates:
                if db.execute('SELECT 1 FROM previews WHERE group_key=?', (group,)).fetchone():
                    stats['duplicates'] += 1
                    if seen_groups is not None:
                        seen_groups.add(group)
                    continue
                if seen_groups is not None:
                    # Whether inserted or deliberately skipped because the
                    # bounded cache is full, don't retry this group every frame.
                    seen_groups.add(group)
                if (stats['added'] >= MAX_PER_CAPTURE or count >= MAX_ITEMS
                        or size >= MAX_BYTES):
                    stats['skipped'] += 1
                    _truncate(db)
                    stats['truncated'] = True
                    continue
                box = [content[0]+offset[0], content[1]+offset[1],
                       content[2]+offset[0], content[3]+offset[1]]
                # Square rotation envelope + context, matching editor needs.
                cx, cy = (box[0]+box[2])/2, (box[1]+box[3])/2
                radius = max(38., math.hypot(box[2]-box[0], box[3]-box[1])/2
                             + max(28., .15*(box[2]-box[0])))
                crop = [max(0, math.floor(cx-radius)), max(0, math.floor(cy-radius)),
                        min(width, math.ceil(cx+radius)), min(height, math.ceil(cy+radius))]
                if crop[2] <= crop[0] or crop[3] <= crop[1]:
                    stats['invalid'] += 1
                    continue
                try:
                    meta = _metadata(row, frame_index, fps, width, height, offset, crop, source)
                    meta, jpeg = _encode(meta, frame_bgr[crop[1]:crop[3], crop[0]:crop[2]])
                    needed = len(_json(meta).encode()) + len(jpeg)
                    if _insert(db, group, meta, jpeg, totals=(count, size)):
                        stats['added'] += 1
                        count += 1
                        size += needed
                    else:
                        stats['skipped'] += 1
                        stats['truncated'] = True
                        # SQLITE_FULL can roll back the active transaction,
                        # including earlier inserts in this capture. This is
                        # exceptional; resync the O(1) counters here rather
                        # than carrying optimistic local totals forward.
                        count, size, _ = _totals(db)
                except (ValueError, TypeError, KeyError, OverflowError):
                    stats['invalid'] += 1
            db.commit()
            _, _, truncated = _totals(db)
            stats.update(total=count, bytes=size,
                         truncated=stats['truncated'] or truncated)
            return stats
        finally:
            db.close()


def _requested(row, render_state):
    fps = float(render_state['fps'])
    if not math.isfinite(fps) or fps <= 0 or not render_state.get('cum'):
        raise ValueError('missing preview timeline')
    exact = int(row.get('frame_index', -1))
    start, end = float(row['t_start']), float(row['t_end'])
    tref = min(max(float(row.get('last_seen', start)), start), end)
    index = exact if exact >= 0 else int(tref*fps)
    if index < 0 or index >= len(render_state['cum']):
        raise ValueError('preview frame outside timeline')
    return index, fps, _offset(render_state['cum'][index])


def lookup(job_dir, row, render_state, *, allow_representative=False):
    """Read exact pixels, or explicitly opt into an actual-frame representative.

    Changed cbox/timeline/offset or geometry outside the stored crop misses.
    A representative never receives the requested frame's polygon/box.
    """
    try:
        row = _row(row)
        index, fps, offset = _requested(row, render_state)
        content, category = _box(row['cbox']), str(row.get('category', ''))
        track = int(row.get('track', -1))
    except (ValueError, TypeError, KeyError, OverflowError):
        return None
    with _LOCK:
        db = _db(job_dir)
        if db is None:
            return None
        try:
            records = db.execute('SELECT metadata,jpeg FROM previews WHERE frame=? '
                                 'AND category=? ORDER BY rowid', (index, category)).fetchall()
            for serialized, jpeg in records:
                meta = json.loads(serialized)
                if (meta['content_box'] != content or meta['offset'] != offset
                        or meta['fps'] != fps):
                    continue
                points = _points(row, meta['box'])
                if not _fits(points, meta['crop']):
                    continue
                return dict(meta, points=points, preview_token=_hash([meta['key'], points]),
                            match='exact', requested_frame=index), bytes(jpeg)
            if not allow_representative:
                return None
            if track >= 0:
                records = db.execute(
                    'SELECT metadata,jpeg FROM previews WHERE category=? AND track=? '
                    'ORDER BY abs(frame-?), rowid', (category, track, index)).fetchall()
            else:
                records = db.execute('SELECT metadata,jpeg FROM previews WHERE category=? '
                                     'ORDER BY rowid', (category,)).fetchall()
            for serialized, jpeg in records:
                meta = json.loads(serialized)
                if meta['fps'] != fps or meta['frame'] == index:
                    continue
                same_track = track >= 0 and meta.get('track', -1) == track
                same_region = (track < 0 and
                               str(row.get('text', ''))[:1024] == meta['text'] and
                               float(row['t_start']) <= meta['t'] <= float(row['t_end'])
                               and _iou(content, meta['content_box']) >= .5)
                if not (same_track or same_region):
                    continue
                f = meta['frame']
                if f >= len(render_state['cum']) or _offset(render_state['cum'][f]) != meta['offset']:
                    continue
                points = _points(row, meta['box'])
                if not _fits(points, meta['crop']):
                    continue
                return dict(meta, points=points,
                            preview_token=_hash([meta['key'], points]),
                            match='representative', requested_frame=index), bytes(jpeg)
        except (ValueError, TypeError, KeyError):
            return None
        finally:
            db.close()
    return None



def _iou(a, b):
    ix = max(0., min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0., min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = ((a[2]-a[0])*(a[3]-a[1]) +
             (b[2]-b[0])*(b[3]-b[1]) - inter)
    return inter / union if union > 0 else 0.


def reconcile(job_dir, detections, render_state):
    """Link scan-time compact pictures to the final post-processed tracks.

    Compact pictures are captured while frames are already decoded, before
    dense tracking, continuity interpolation, reverse-pass recovery and other
    post-processing finish. Final Review can therefore point at a synthetic
    row whose exact frame was never stored even though the same physical
    object has a nearby cached detector frame.

    Reconciliation never decodes video. It only matches existing compact
    pictures to final rows from the same category/frame by source-space IoU
    and writes the final track id into the compact index. That lets Review use
    a real cached representative of the final track automatically.
    """
    try:
        fps = float(render_state['fps'])
        cum = render_state['cum']
        if not math.isfinite(fps) or fps <= 0 or not cum:
            return dict(total=0, linked=0, already=0)
    except (KeyError, TypeError, ValueError):
        return dict(total=0, linked=0, already=0)

    by_frame = {}
    for row in detections or []:
        try:
            row = _row(row)
            track = int(row.get('track', -1))
            if track < 0:
                continue
            category = str(row.get('category', ''))
            exact = int(row.get('frame_index', -1))
            if exact >= 0:
                frame = exact
            else:
                t = min(max(float(row.get('last_seen', row['t_start'])),
                            float(row['t_start'])), float(row['t_end']))
                frame = int(round(t * fps))
            if not 0 <= frame < len(cum):
                continue
            content = _box(row['cbox'])
            offset = _offset(cum[frame])
            box = [content[0]+offset[0], content[1]+offset[1],
                   content[2]+offset[0], content[3]+offset[1]]
            by_frame.setdefault((frame, category), []).append(
                (track, int(row.get('person', -1)), box))
        except (ValueError, TypeError, KeyError, OverflowError):
            continue

    with _LOCK:
        db = _db(job_dir)
        if db is None:
            return dict(total=0, linked=0, already=0)
        try:
            records = db.execute(
                'SELECT key, metadata, track FROM previews ORDER BY rowid').fetchall()
            linked = already = 0
            byte_delta = 0
            updates = []
            for key, serialized, old_track in records:
                try:
                    meta = json.loads(serialized)
                    candidates = by_frame.get((int(meta['frame']),
                                               str(meta['category'])), ())
                    if not candidates:
                        continue
                    best = max(candidates, key=lambda item: _iou(meta['box'], item[2]))
                    score = _iou(meta['box'], best[2])
                    if score < .5:
                        continue
                    track, person, _ = best
                    if int(old_track) == track and int(meta.get('track', -1)) == track:
                        already += 1
                        continue
                    meta['track'] = track
                    if person >= 0:
                        meta['person'] = person
                    updated = _json(meta)
                    byte_delta += len(updated.encode()) - len(serialized.encode())
                    updates.append((track, updated, key))
                    linked += 1
                except (ValueError, TypeError, KeyError, OverflowError):
                    continue
            if updates:
                db.executemany('UPDATE previews SET track=?, metadata=? WHERE key=?',
                               updates)
                count, size, _ = _totals(db)
                _set_total(db, 'bytes', size + byte_delta)
                db.commit()
            return dict(total=len(records), linked=linked, already=already)
        finally:
            db.close()


def pending(job_dir, offset=0, limit=60):
    """Paginated sample metadata, never video decoding or JPEG loading."""
    offset, limit = max(0, int(offset)), min(100, max(0, int(limit)))
    with _LOCK:
        db = _db(job_dir)
        if db is None:
            return dict(items=[], total=0, truncated=False)
        try:
            count, _, truncated = _totals(db)
            records = db.execute('SELECT metadata FROM previews ORDER BY rowid LIMIT ? OFFSET ?',
                                 (limit, offset))
            return dict(items=[json.loads(r[0]) for r in records], total=count, truncated=truncated)
        finally:
            db.close()


def image(job_dir, key):
    """Read a confined immutable sample by its opaque 64-character key."""
    if not isinstance(key, str) or not _KEY.fullmatch(key):
        return None
    with _LOCK:
        db = _db(job_dir)
        if db is None:
            return None
        try:
            record = db.execute('SELECT metadata,jpeg FROM previews WHERE key=?', (key,)).fetchone()
            return (json.loads(record[0]), bytes(record[1])) if record else None
        finally:
            db.close()


def store(job_dir, row, render_state, meta, pixels):
    """Cache an externally decoded legacy crop with an explicit source mapping.

    ``pixels`` must cover exactly meta['crop'] at original source resolution;
    meta also supplies original width/height. Explicit requests may evict the
    oldest job-local previews within the same bounds. An image that cannot fit
    raises without evicting existing previews. Exact cached images are reused.
    """
    cached = lookup(job_dir, row, render_state)
    if cached is not None:
        return cached
    row = _row(row)
    index, fps, offset = _requested(row, render_state)
    if int(meta['frame']) != index:
        raise ValueError('legacy crop belongs to a different frame')
    width, height = int(meta['width']), int(meta['height'])
    crop = [int(v) for v in meta['crop']]
    if (len(crop) != 4 or width <= 0 or height <= 0 or crop[0] < 0 or crop[1] < 0
            or crop[2] > width or crop[3] > height
            or tuple(pixels.shape[:2]) != (crop[3]-crop[1], crop[2]-crop[0])):
        raise ValueError('legacy crop dimensions do not match source mapping')
    result = _metadata(row, index, fps, width, height, offset, crop, meta.get('source'))
    if 'box' in meta and _box(meta['box']) != result['box']:
        raise ValueError('legacy box does not match source mapping')
    result, jpeg = _encode(result, pixels)
    with _LOCK:
        db = _db(job_dir, create=True)
        try:
            if not _insert_explicit(db, 'legacy:'+result['key'], result, jpeg):
                db.commit()
                cached = image(job_dir, result['key'])
                if cached is not None:
                    # The same source/box key cannot acknowledge a different
                    # crop or polygon that the persisted pixels do not cover.
                    reusable = lookup(job_dir, row, render_state)
                    if reusable is not None:
                        return reusable
                    raise ValueError('existing preview crop is incompatible with geometry')
                raise PreviewLimitError('compact preview cache is full')
            db.commit()
        finally:
            db.close()
    return result, jpeg
