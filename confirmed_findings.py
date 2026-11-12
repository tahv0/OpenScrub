"""Durable, explicit human findings, independent of scan jobs and source paths.

Only ``record`` creates evidence. Source hashes and a compatible variant/timeline
bind coordinates; display names and transient track/job IDs never identify it.
SQLite serializes revisions, while fsynced content-addressed JPEGs remain valid
for frozen training snapshots even after the current finding changes or revokes.
No operation in this module opens a video.
"""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import struct
import tempfile

import cv2
import numpy as np


class ConflictError(ValueError):
    """A supplied revision is stale, or a stale job tried to replace evidence."""


_HASH = re.compile(r'^[0-9a-f]{64}$')
_CATEGORY = re.compile(r'^[a-z][a-z0-9_]{0,63}$')
_MAX_JPEG_BYTES = 16 * 1024 * 1024


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _hash(value, what='hash'):
    if not isinstance(value, str) or not _HASH.fullmatch(value):
        raise ValueError('A lowercase SHA-256 content %s is required' % what)
    return value


def _number(value, what):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('Invalid %s' % what)
    return float(value)


def _integer(value, what, minimum=0):
    number = _number(value, what)
    if number != int(number) or number < minimum:
        raise ValueError('Invalid %s' % what)
    return int(number)


def _video(value):
    v = dict(sha256=_hash(value.get('sha256'), 'source identity'),
             variant_sha256=_hash(value.get('variant_sha256'), 'variant identity'),
             name=str(value.get('name') or 'Video').replace('\\', '/').rsplit('/', 1)[-1][:255],
             fps=_number(value.get('fps'), 'fps'),
             width=_integer(value.get('width'), 'width', 1),
             height=_integer(value.get('height'), 'height', 1),
             total_frames=_integer(value.get('total_frames'), 'total_frames', 1))
    if v['fps'] <= 0:
        raise ValueError('Invalid fps')
    return v


def _box(value, width, height, what='box'):
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ValueError('Invalid %s' % what)
    b = [_number(n, what) for n in value]
    if not (0 <= b[0] < b[2] <= width and 0 <= b[1] < b[3] <= height):
        raise ValueError('%s is outside the source or has no area' % what)
    return b


def _points(value, crop, category):
    if value is None:
        return None
    if not isinstance(value, (list, tuple)) or not 3 <= len(value) <= 32:
        raise ValueError('Invalid points')
    result = []
    for point in value:
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise ValueError('Invalid point')
        x, y = [_number(n, 'point') for n in point]
        if not crop[0] <= x <= crop[2] or not crop[1] <= y <= crop[3]:
            raise ValueError('Points must lie inside the stored crop')
        result.append([x, y])
    contour = np.asarray(result, np.float32)
    if len(set(map(tuple, result))) != len(result) or abs(cv2.contourArea(contour)) < 1e-6:
        raise ValueError('Points must describe a nondegenerate polygon')
    if category == 'plate' and (len(result) != 4 or not cv2.isContourConvex(contour)):
        raise ValueError('Plate corners must describe a convex quadrilateral')
    return result


def _label(label):
    if label not in ('positive', 'negative'):
        raise ValueError('An explicit positive or negative label is required')
    return label


def _category(value):
    if not isinstance(value, str) or not _CATEGORY.fullmatch(value):
        raise ValueError('Invalid finding category')
    return value


def _jpeg_dimensions(data):
    """Read SOF dimensions before allocating decoded pixels."""
    if not data.startswith(b'\xff\xd8'):
        raise ValueError('A JPEG image is required')
    pos = 2
    while pos < len(data):
        if data[pos] != 255:
            raise ValueError('Invalid JPEG image')
        while pos < len(data) and data[pos] == 255:
            pos += 1
        if pos >= len(data):
            break
        marker = data[pos]
        pos += 1
        if marker in (0xd8, 0x01) or 0xd0 <= marker <= 0xd7:
            continue
        if marker in (0xd9, 0xda) or pos + 2 > len(data):
            break
        length = struct.unpack('>H', data[pos:pos + 2])[0]
        if length < 2 or pos + length > len(data):
            break
        if marker in (0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7,
                      0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf):
            if length < 8:
                break
            height, width = struct.unpack('>HH', data[pos + 3:pos + 7])
            return width, height
        pos += length
    raise ValueError('Invalid JPEG image dimensions')


def _compact_jpeg(data):
    if not isinstance(data, (bytes, bytearray)) or not 0 < len(data) <= _MAX_JPEG_BYTES:
        raise ValueError('Invalid or oversized JPEG image')
    data = bytes(data)
    width, height = _jpeg_dimensions(data)
    if width <= 0 or height <= 0 or width * height > 64_000_000:
        raise ValueError('Oversized JPEG image dimensions')
    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError('Cannot decode JPEG image')
    height, width = image.shape[:2]
    factor = min(1., 640. / max(width, height))
    if factor < 1:
        width, height = max(1, round(width * factor)), max(1, round(height * factor))
        image = cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)
    ok, encoded = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 65])
    if not ok:
        raise ValueError('Cannot encode compact JPEG image')
    return encoded.tobytes(), width, height


def _sync_dir(path):
    # Windows file/SQLite flushes and atomic replacement remain available;
    # the CRT cannot open a directory descriptor for POSIX fsync.
    if os.name == 'nt':
        return
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _private_dir(path):
    path = Path(path)
    if not path.exists():
        path.mkdir(parents=True, mode=0o700, exist_ok=True)
        _sync_dir(path.parent)
    return path


@contextmanager
def _db(root, write=False):
    root = _private_dir(root)
    dbpath = root / 'findings.sqlite3'
    conn = sqlite3.connect(dbpath, timeout=30, isolation_level=None)
    try:
        os.chmod(dbpath, 0o600)
        conn.execute('PRAGMA synchronous=FULL')
        conn.execute('CREATE TABLE IF NOT EXISTS findings '
                     '(id TEXT PRIMARY KEY, value TEXT NOT NULL)')
        conn.execute('CREATE TABLE IF NOT EXISTS revisions '
                     '(id TEXT NOT NULL, revision INTEGER NOT NULL, value TEXT NOT NULL, '
                     'PRIMARY KEY(id, revision))')
        _sync_dir(root)
        conn.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def _load(conn, identity):
    _hash(identity, 'finding ID')
    result = conn.execute('SELECT value FROM findings WHERE id=?', (identity,)).fetchone()
    if result is None:
        raise KeyError(identity)
    return json.loads(result[0])


def _public(entry):
    return {k: deepcopy(v) for k, v in entry.items() if k != 'revoked'}


def _save(conn, entry):
    value = _json(entry)
    conn.execute('INSERT OR REPLACE INTO findings(id,value) VALUES (?,?)', (entry['id'], value))
    conn.execute('INSERT INTO revisions(id,revision,value) VALUES (?,?,?)',
                 (entry['id'], entry['revision'], value))


def _asset_path(root, digest):
    return Path(root) / 'images' / (_hash(digest, 'image hash') + '.jpg')


def _store_image(root, data, digest):
    folder = _private_dir(Path(root) / 'images')
    target = _asset_path(root, digest)
    if target.exists():
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise ValueError('Stored image hash does not match its content')
        return
    fd, temporary = tempfile.mkstemp(prefix='.image-', suffix='.jpg', dir=folder)
    try:
        os.chmod(temporary, 0o600)
        with os.fdopen(fd, 'wb') as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, target)
        _sync_dir(folder)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _revision_receipt(entry):
    """Safe conflict metadata, without image bytes or source paths."""
    return dict(id=entry['id'],revision=entry['revision'],revoked=bool(entry.get('revoked')),
                label=None if entry.get('revoked') else entry['label'])


def _check_revision(entry, expected):
    if expected is not None and _integer(expected, 'expected revision', 1) != entry['revision']:
        error = ConflictError('Finding changed; reload its current revision before saving')
        error.current_archive = _revision_receipt(entry)
        raise error


def record(root, video, finding, jpeg_bytes):
    """Archive one explicit classification and return its durable save receipt.

    Repeating the same classification/shape is idempotent across jobs. Replacing
    existing values, including a revocation, requires ``finding.expected_revision``
    so an old scan cannot silently resurrect or relabel a newer human decision.
    """
    if finding.get('explicit') is not True:
        raise ValueError('Only an explicit human classification can be archived')
    v = _video(video)
    category, label = _category(finding.get('category')), _label(finding.get('label'))
    frame = _integer(finding.get('frame'), 'frame')
    if frame >= v['total_frames']:
        raise ValueError('Finding frame is outside the source timeline')
    box = _box(finding.get('box'), v['width'], v['height'])
    crop = finding.get('crop')
    crop = _box(crop.get('box') if isinstance(crop, dict) else crop,
                v['width'], v['height'], 'crop')
    if not (crop[0] <= box[0] and crop[1] <= box[1] and box[2] <= crop[2] and box[3] <= crop[3]):
        raise ValueError('Stored crop must contain the original box')
    points = _points(finding.get('points'), crop, category)
    shape_confirmed = finding.get('shape_confirmed') is True
    if points is not None and not shape_confirmed:
        raise ValueError('Unconfirmed geometry cannot become training evidence')
    image_bytes, width, height = _compact_jpeg(jpeg_bytes)
    digest = hashlib.sha256(image_bytes).hexdigest()
    timeline = [v[k] for k in ('variant_sha256', 'fps', 'width', 'height', 'total_frames')]
    identity = hashlib.sha256(_json([v['sha256'], timeline, category, frame, box]).encode()).hexdigest()
    if finding.get('id') is not None and finding['id'] != identity:
        raise ValueError('Finding ID does not match source identity and geometry')
    expected = finding.get('expected_revision')
    with _db(root, write=True) as conn:
        try:
            old = _load(conn, identity)
        except KeyError:
            old = None
        if old:
            _check_revision(old, expected)
            if not old.get('revoked') and all((old['label'] == label,
                    old['points'] == points, old['shape_confirmed'] == shape_confirmed)):
                _verified_image(root, old)
                return _public(old)
            if expected is None:
                error = ConflictError('Existing finding requires its current revision before replacement')
                error.current_archive = _revision_receipt(old)
                raise error
        elif expected not in (None, 0):
            raise ConflictError('Finding does not exist at the requested revision')
        _store_image(root, image_bytes, digest)
        now = _now()
        entry = dict(id=identity, video_id=v['sha256'], video=v, category=category,
                     explicit=True, label=label, frame=frame, time=frame / v['fps'],
                     box=box, points=points, shape_confirmed=shape_confirmed,
                     crop=dict(box=crop, width=width, height=height,
                               scale_x=(crop[2]-crop[0])/width, scale_y=(crop[3]-crop[1])/height),
                     image=dict(sha256=digest, width=width, height=height,
                                mime_type='image/jpeg', quality=65),
                     job_id=str(finding.get('job_id') or '').replace('\\', '/').rsplit('/', 1)[-1][:255],
                     created_at=old['created_at'] if old else now, confirmed_at=now,
                     revision=old['revision'] + 1 if old else 1, revoked=False)
        _save(conn, entry)
    return _public(entry)


def get_finding(root, id):
    with _db(root) as conn:
        entry = _load(conn, id)
    if entry.get('revoked'):
        raise KeyError(id)
    return _public(entry)


def revision_state(root, id):
    """Small conflict receipt, including tombstones, without reading pixels."""
    with _db(root) as conn:
        entry = _load(conn,id)
    return _revision_receipt(entry)


def image_path(root, id):
    entry = get_finding(root, id)
    return _asset_path(root, entry['image']['sha256'])


def list_findings(root, video_id=None, category=None, label=None, offset=0, limit=60):
    offset = _integer(offset, 'offset')
    limit = min(_integer(limit, 'limit', 1), 200)
    if video_id is not None:
        _hash(video_id, 'video identity')
    if category is not None:
        _category(category)
    if label is not None:
        _label(label)
    with _db(root) as conn:
        entries = [json.loads(r[0]) for r in conn.execute('SELECT value FROM findings')]
    entries = [e for e in entries if not e.get('revoked')]
    videos = {}
    for entry in entries:
        v = videos.setdefault(entry['video_id'], dict(id=entry['video_id'],
                              name=entry['video']['name'], count=0))
        v['count'] += 1
    chosen = [e for e in entries if (video_id is None or e['video_id'] == video_id)
              and (category is None or e['category'] == category)
              and (label is None or e['label'] == label)]
    chosen.sort(key=lambda e: (e['confirmed_at'], e['id']), reverse=True)
    return dict(items=[_public(e) for e in chosen[offset:offset+limit]], total=len(chosen),
                videos=sorted(videos.values(), key=lambda v: (v['name'], v['id'])))


def update_finding(root, id, label=None, points=None, expected_revision=None):
    with _db(root, write=True) as conn:
        entry = _load(conn, id)
        if entry.get('revoked'):
            raise KeyError(id)
        _check_revision(entry, expected_revision)
        changed = deepcopy(entry)
        if label is not None:
            changed['label'] = _label(label)
        if points is not None:
            changed['points'] = _points(points, entry['crop']['box'], entry['category'])
            changed['shape_confirmed'] = True
        if changed == entry:
            return _public(entry)
        changed.update(revision=entry['revision'] + 1, confirmed_at=_now())
        _save(conn, changed)
    return _public(changed)


def forget(root, id, expected_revision=None):
    with _db(root, write=True) as conn:
        entry = _load(conn, id)
        _check_revision(entry, expected_revision)
        if not entry.get('revoked'):
            entry.update(revoked=True, revision=entry['revision']+1, confirmed_at=_now())
            _save(conn, entry)
    return dict(id=entry['id'], revision=entry['revision'], revoked=True)


def training_snapshot(root, ids=None, video_ids=None, category='plate'):
    """Return detached revision-frozen values and verified immutable JPEG paths."""
    if category is not None:
        _category(category)
    selected = None if ids is None else {_hash(i, 'finding ID') for i in ids}
    videos = None if video_ids is None else {_hash(i, 'video identity') for i in video_ids}
    with _db(root) as conn:
        entries = [json.loads(row[0]) for row in conn.execute('SELECT value FROM findings')]
    result = []
    for entry in entries:
        if (entry.get('revoked') or entry.get('explicit') is not True or
                entry['label'] not in ('positive', 'negative') or
                (category is not None and entry['category'] != category) or
                (selected is not None and entry['id'] not in selected) or
                (videos is not None and entry['video_id'] not in videos)):
            continue
        path = _verified_image(root, entry)
        item = _public(entry)
        item['image_path'] = str(path.resolve())
        result.append(item)
    result.sort(key=lambda e: e['id'])
    return result


def _verified_image(root, entry):
    path = _asset_path(root, entry['image']['sha256'])
    try:
        image = path.read_bytes()
    except OSError as exc:
        raise ValueError('Saved training image is missing or unreadable') from exc
    if hashlib.sha256(image).hexdigest() != entry['image']['sha256']:
        raise ValueError('Saved training image hash does not match its content')
    return path


def training_revisions(root, ids):
    """Reconcile inherited example IDs at one consistent archive revision view.

    Forgotten IDs must be dropped from a cumulative parent corpus. Missing IDs
    are distinct: the parent may carry a standalone frozen corpus originating
    from another installation. Active entries use the same verified, detached
    values as ``training_snapshot`` and supersede an older frozen label/shape.
    """
    selected = sorted({_hash(identity, 'finding ID') for identity in ids})
    result = dict(active=[], revoked_ids=[], missing_ids=[])
    if not selected:
        return result
    with _db(root) as conn:
        for identity in selected:
            try:
                entry = _load(conn, identity)
            except KeyError:
                result['missing_ids'].append(identity)
                continue
            if entry.get('revoked'):
                result['revoked_ids'].append(identity)
                continue
            if entry.get('explicit') is not True or entry.get('label') not in ('positive', 'negative'):
                raise ValueError('Inherited training finding lacks an explicit human label')
            item = _public(entry)
            item['image_path'] = str(_verified_image(root, entry).resolve())
            result['active'].append(item)
    return result


def _report_video(doc):
    prov = doc.get('provenance') or {}
    source = doc.get('source_identity') or {}
    rs = doc.get('render_state') or {}
    variant = prov.get('input_sha256') or source.get('input_sha256')
    return dict(sha256=prov.get('original_input_sha256') or variant,
                variant_sha256=variant, fps=rs.get('fps'), width=source.get('width'),
                height=source.get('height'),
                total_frames=source.get('total_frames', len(rs.get('cum') or [])))


def _compatible(stored, current):
    for key in ('sha256', 'variant_sha256', 'fps', 'total_frames'):
        if stored.get(key) != current.get(key):
            return False
    # Identical variant bytes already establish source dimensions. Older reports
    # omit them; present dimensions must agree exactly.
    return all(current.get(k) is None or stored[k] == current[k] for k in ('width', 'height'))


def apply_to_report(root, doc):
    """Conservatively replay exact, uniquely matched regions on the same timeline.

    Existing independent human choices always win. A prior replay marked with
    this finding ID/revision may advance to the library's newer revision.
    Output Blur/Keep is preserved as an independent user choice.
    """
    import video_learning as vl

    result = deepcopy(doc)
    stats = dict(applied=0, ambiguous=0, preserved=0, revoked=0)
    current = _report_video(doc)
    rs = result.get('render_state') or {}
    rows = result.get('detections') or []
    with _db(root) as conn:
        entries = [json.loads(r[0]) for r in conn.execute('SELECT value FROM findings')]
    for entry in entries:
        if not _compatible(entry['video'], current):
            continue
        candidates = []
        for row in rows:
            if row.get('category') != entry['category']:
                continue
            try:
                frame = vl._frame(row, rs)
                box = vl._screen_box(row, rs, frame)
            except (ValueError, TypeError, KeyError, IndexError):
                continue
            if frame == entry['frame'] and box == entry['box']:
                candidates.append(row)
        if len(candidates) != 1:
            stats['ambiguous'] += bool(candidates)
            continue
        row = candidates[0]
        old_replay = (row.get('confirmed_finding_id') == entry['id'] and
                      isinstance(row.get('human_confirmation'), dict) and
                      row['human_confirmation'].get('source') == 'confirmed_findings')
        if old_replay and entry['category'] == 'plate':
            previous = row['human_confirmation'].get('label')
            expected_label = {'positive': 'plate', 'negative': 'not_plate'}.get(previous)
            if row.get('verified_label') != expected_label:
                # A direct later choice may have retained an older save marker.
                old_replay = False
        has_human = (row.get('verified_label') or row.get('plate_verification_override') or row.get('output_choice_explicit') or
                     row.get('human_confirmation') or row.get('manual_override'))
        if has_human and not old_replay:
            stats['preserved'] += 1
            continue
        if entry.get('revoked'):
            if old_replay:
                previous_state = row['human_confirmation'].get('previous_state') or {'enabled':True}
                for key in ('enabled','output_choice_explicit','plate_verification','plate_verification_override',
                            'plate_quad','poly','poly_holes','mask_pad','fallback_reason','human_region_confirmed'):
                    row.pop(key,None)
                row.update(deepcopy(previous_state))
                for key in ('confirmed_finding_id', 'confirmed_finding_revision',
                            'human_confirmation', 'verified_label'):
                    row.pop(key, None)
                stats['revoked'] += 1
            continue
        if old_replay and row.get('confirmed_finding_revision', 0) >= entry['revision']:
            continue
        previous_state = ((row.get('human_confirmation') or {}).get('previous_state') if old_replay else None)
        if previous_state is None:
            previous_state = {key:deepcopy(row[key]) for key in (
                'enabled','output_choice_explicit','plate_verification','plate_verification_override',
                'plate_quad','poly','poly_holes','mask_pad','fallback_reason','human_region_confirmed') if key in row}
            previous_state.setdefault('enabled',True)
        row.update(confirmed_finding_id=entry['id'], confirmed_finding_revision=entry['revision'],
                   enabled=entry['label']=='positive',output_choice_explicit=True,
                   human_confirmation=dict(label=entry['label'], category=entry['category'],
                                           source='confirmed_findings', revision=entry['revision'],previous_state=previous_state))
        if entry['category'] == 'plate':
            row['verified_label'] = 'plate' if entry['label'] == 'positive' else 'not_plate'
            row['plate_verification_override'] = True
            row.pop('plate_verification', None)
            if entry['points'] is not None and entry['shape_confirmed']:
                x1, y1, x2, y2 = entry['box']
                row['plate_quad'] = [[(x-x1)/(x2-x1), (y-y1)/(y2-y1)]
                                     for x, y in entry['points']]
                row.update(poly=[], poly_holes=[], mask_pad=0, fallback_reason='')
        stats['applied'] += 1
    return result, stats
