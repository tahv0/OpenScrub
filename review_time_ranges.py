"""Explicit, source-bound plate-free Review intervals.

A reviewer can know that a whole video segment contains no registration plates.
This statement is stronger than an individual detector's score but narrower
than a whole person's/track's life. Keep its source-frame interval separate
from the existing group-wide Is/Not buttons and from saved-image confirmations.
"""
from copy import deepcopy
import hashlib
import json
import math
import uuid


class RangeConflict(ValueError):
    """A proposed bulk decision would overwrite a different human decision."""


_FIELDS = ('enabled', 'output_choice_explicit', 'verified_label',
           'human_confirmation', 'plate_verification', 'plate_verification_override',
           'learning_anchor', 'learning_group', 'interval_negative')
_MISSING = {'_range_missing': True}


def bounds(doc, start, end):
    """Inclusive start, exclusive end snapped to exact source frames."""
    rs = doc['render_state']
    fps = float(rs['fps'])
    total = len(rs['cum'])
    if not math.isfinite(fps) or fps <= 0 or total <= 0:
        raise ValueError('The scanned source timeline is invalid.')
    if (type(start) not in (int, float) or type(end) not in (int, float)
            or not math.isfinite(start) or not math.isfinite(end)
            or not 0 <= start < end <= total / fps + 1e-8):
        raise ValueError('Choose a valid start and end within the scanned video.')
    # Follow the project's frame-ceiling convention; tolerate float ULPs.
    def ceil_frame(seconds):
        value = seconds * fps
        nearest = round(value)
        if abs(value - nearest) <= 4 * math.ulp(value):
            value = nearest
        return math.ceil(value)
    first, last = ceil_frame(start), ceil_frame(end)
    if not 0 <= first < last <= total:
        raise ValueError('The selected interval contains no scanned source frames.')
    return first, last, fps


def source_hash(doc):
    provenance = (doc.get('provenance') or {}).get('input_sha256')
    verified = (doc.get('source_identity') or {}).get('input_sha256')
    digest = provenance or verified
    if (not isinstance(digest, str) or len(digest) != 64
            or any(c not in '0123456789abcdef' for c in digest)
            or verified and provenance and verified != provenance):
        raise ValueError('A verified, unchanged video source is required for bulk review.')
    return digest


def _inside(row, first, last, fps):
    """Do not change any unindexed long-duration box across a range edge."""
    frame = row.get('frame_index', -1)
    if type(frame) is int and frame >= 0:
        return first <= frame < last
    try:
        start = float(row['t_start'])
        end = float(row['t_end'])
    except (KeyError, ValueError, TypeError):
        return False
    return start >= first / fps - 1e-7 and end <= last / fps + 1e-7


def _overlaps(row, first, last, fps):
    try:
        return float(row['t_start']) < last / fps and float(row['t_end']) > first / fps
    except (ValueError, TypeError, KeyError):
        return False


def _protected(row):
    """Never silently override a per-image human confirmation or archive."""
    confirmation = row.get('human_confirmation') or {}
    return (bool(row.get('confirmed_finding_id')) or
            row.get('verified_label') == 'plate' or
            (confirmation.get('label') in ('positive', 'negative')
             and confirmation.get('source') != 'time_range'))


def _selection(doc, first, last, fps):
    selected, protected, boundary = [], 0, 0
    for i, row in enumerate(doc['detections']):
        if row.get('category') != 'plate':
            continue
        if not _inside(row, first, last, fps):
            if _overlaps(row, first, last, fps) and row.get('frame_index', -1) < 0:
                boundary += 1
            continue
        if _protected(row):
            protected += 1
        else:
            selected.append(i)
    return selected, protected, boundary


def _snapshot(row):
    return {k: deepcopy(row[k]) if k in row else deepcopy(_MISSING)
            for k in _FIELDS}


def _restore(row, snapshot):
    for k, value in snapshot.items():
        if value == _MISSING:
            row.pop(k, None)
        else:
            row[k] = deepcopy(value)


def preview(doc, start, end):
    first, last, fps = bounds(doc, start, end)
    selected, protected, boundary = _selection(doc, first, last, fps)
    return dict(start_frame=first, end_frame=last, seconds=[first / fps, last / fps],
                matched=len(selected), protected=protected, crossing_boundary=boundary)


def apply(doc, start, end, *, training=False):
    """One report transaction: only selected plate rows, never their whole track."""
    if type(training) is not bool:
        raise ValueError('Training selection must be an explicit true/false value.')
    summary = preview(doc, start, end)
    first, last = summary['start_frame'], summary['end_frame']
    source = source_hash(doc)
    for interval in doc.get('plate_free_intervals') or []:
        if interval['start_frame'] < last and interval['end_frame'] > first:
            raise RangeConflict('This interval overlaps an existing plate-free declaration. Undo the last range or choose an uncovered interval.')
    identity = uuid.uuid4().hex
    record = dict(id=identity, source_sha256=source,
                  start_frame=first, end_frame=last, training=training)
    fps = float(doc['render_state']['fps'])
    selected, _, _ = _selection(doc, first, last, fps)
    changes = []
    for i in selected:
        row = doc['detections'][i]
        previous = _snapshot(row)
        row['enabled'] = False
        row['output_choice_explicit'] = True
        row['verified_label'] = 'not_plate' if training else ''
        row['plate_verification_override'] = True
        row.pop('plate_verification', None)
        row['human_confirmation'] = dict(
            label='negative', category='plate', source='time_range',
            training=training, range_id=identity)
        row['interval_negative'] = dict(id=identity, training=training)
        # Prevent the legacy denied-track propagation from leaking past bounds.
        row['learning_anchor'] = hashlib.sha256(
            json.dumps([source, identity, i, row.get('cbox')]).encode()
        ).hexdigest()[:24]
        row.pop('learning_group', None)
        changes.append(dict(index=i, before=previous, after=_snapshot(row)))
    doc.setdefault('plate_free_intervals', []).append(record)
    # The last bulk operation is reversible even after Save or reopening Review.
    doc['plate_free_range_undo'] = dict(record=record, row_count=len(doc['detections']),
                                        changes=changes)
    doc['render_required'] = True
    return dict(summary, ok=True, training=training, interval_id=identity)


def undo(doc):
    action = doc.get('plate_free_range_undo')
    if not isinstance(action, dict):
        raise RangeConflict('There is no recent plate-free range to undo.')
    record = action.get('record') or {}
    if (record.get('source_sha256') != source_hash(doc)
            or action.get('row_count') != len(doc['detections'])):
        raise RangeConflict('The report or source changed. Review the affected findings instead of undoing stale labels.')
    for change in action['changes']:
        if _snapshot(doc['detections'][change['index']]) != change['after']:
            raise RangeConflict('A finding was edited after the range action. Undo would overwrite newer work.')
    for change in action['changes']:
        _restore(doc['detections'][change['index']], change['before'])
    doc['plate_free_intervals'] = [item for item in doc.get('plate_free_intervals', [])
                                   if item.get('id') != record.get('id')]
    doc.pop('plate_free_range_undo', None)
    doc['render_required'] = True
    return dict(ok=True, undone=len(action['changes']),
                start_frame=record.get('start_frame'), end_frame=record.get('end_frame'))
