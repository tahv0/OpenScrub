"""Portable data contract for a paused scan, independent of its publisher.

This module does not stop a scan, validate files, align scroll origins, or
render a checkpoint. Producers must provide the identities and proof described
in CHECKPOINT_CONTRACT.md and use the existing atomic report publisher.
"""
import copy
import json
import math
import re


class CheckpointError(ValueError):
    """The report is not a safely resumable checkpoint or merge candidate."""


_SCHEMA = 2
_HASH = re.compile(r'^[0-9a-f]{64}$')
_MAX_SAFE_INTEGER = (1 << 53) - 1


def _error(message):
    raise CheckpointError(message)


def _object(value, name):
    if type(value) is not dict:
        _error('%s must be a JSON object' % name)
    return value


def _text(value, name):
    if type(value) is not str or not value.strip():
        _error('%s must be a nonempty string' % name)
    return value


def _integer(value, name, minimum=0):
    if type(value) is not int or not minimum <= value <= _MAX_SAFE_INTEGER:
        _error('%s must be an interoperable integer >= %s' % (name, minimum))
    return value


def _number(value, name, positive=False):
    try:
        valid = (type(value) in (int, float) and math.isfinite(value)
                 and (not positive or value > 0))
    except OverflowError:
        valid = False
    if not valid:
        _error('%s must be a finite%s number' % (name, ' positive' if positive else ''))
    return value


def _digest(value, name):
    if type(value) is not str or not _HASH.fullmatch(value):
        _error('%s must be a lowercase SHA-256 content digest' % name)
    return value


def _json(value, name, active=None):
    """Accept only portable JSON values, including unknown preserved fields."""
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float:
        _number(value, name)
        return
    if type(value) not in (list, dict):
        _error('%s contains a non-JSON value' % name)
    if active is None:
        active = set()
    if id(value) in active:
        _error('%s contains a cycle' % name)
    active.add(id(value))
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                _error('%s contains a non-string JSON key' % name)
            _json(item, name, active)
    else:
        for item in value:
            _json(item, name, active)
    active.remove(id(value))


def _equal_json(a, b):
    # Unlike Python equality, JSON boolean, integer and float types remain
    # distinguishable; key order is not an identity property.
    try:
        return json.dumps(a, sort_keys=True, separators=(',', ':'), allow_nan=False) == \
            json.dumps(b, sort_keys=True, separators=(',', ':'), allow_nan=False)
    except (RecursionError, ValueError, OverflowError):
        _error('identity cannot be encoded as portable JSON')


def _copy_json(value):
    try:
        return copy.deepcopy(value)
    except RecursionError:
        _error('report nesting exceeds the portable limit')


def _identity(options, total, fps, scan_hash):
    options = _object(options, 'checkpoint options')
    try:
        _json(options, 'checkpoint options')
    except RecursionError:
        _error('checkpoint options nesting exceeds the portable limit')
    sources = _object(options.get('sources'), 'sources')
    for role in ('scan', 'original', 'render'):
        if role not in sources:
            _error('sources.%s is missing; provide the selected participant or null' % role)
    for role, participant in sources.items():
        _text(role, 'source participant name')
        if role == 'render' and participant is None:
            continue
        participant = _object(participant, 'sources.%s' % role)
        _digest(participant.get('sha256'), 'sources.%s.sha256' % role)
        _integer(participant.get('width'), 'sources.%s.width' % role, 1)
        _integer(participant.get('height'), 'sources.%s.height' % role, 1)
        _number(participant.get('fps'), 'sources.%s.fps' % role, positive=True)
        _text(participant.get('fps_source'), 'sources.%s.fps_source' % role)
    if sources['scan']['sha256'] != scan_hash:
        _error('scan participant and report input SHA-256 differ')
    if sources['scan']['fps'] != fps:
        _error('scan participant and report FPS differ')
    norm = _object(options.get('normalization'), 'normalization')
    for field in ('mode', 'target', 'transform_version'):
        _text(norm.get(field), 'normalization.%s' % field)
    timeline = _object(options.get('timeline'), 'timeline')
    _number(timeline.get('fps'), 'timeline.fps', positive=True)
    _text(timeline.get('fps_source'), 'timeline.fps_source')
    _integer(timeline.get('total_frames'), 'timeline.total_frames', 1)
    _text(timeline.get('count_source'), 'timeline.count_source')
    if type(timeline.get('count_verified')) is not bool:
        _error('timeline.count_verified must be a boolean')
    if timeline['fps'] != fps or timeline['total_frames'] != total:
        _error('source timeline does not match checkpoint FPS or frame count')
    if not math.isfinite(total / fps):
        _error('source timeline duration must be finite')
    settings = _object(options.get('effective_settings'), 'effective_settings')
    if not settings:
        _error('effective_settings must contain the resolved scan settings')
    files = _object(options.get('file_identities'), 'file_identities')
    for name, digest in files.items():
        _text(name, 'file identity name')
        _digest(digest, 'file_identities.%s' % name)
    return options


def _report(doc, length, total, bounds_until=None):
    doc = _object(doc, 'report')
    try:
        _json(doc, 'report')
    except RecursionError:
        _error('report nesting exceeds the portable limit')
    provenance = _object(doc.get('provenance'), 'provenance')
    scan_hash = _digest(provenance.get('input_sha256'), 'provenance.input_sha256')
    state = _object(doc.get('render_state'), 'render_state')
    fps = _number(state.get('fps'), 'render_state.fps', positive=True)
    for field in ('cum', 'bands'):
        values = state.get(field)
        if type(values) is not list or len(values) != length:
            _error('render_state.%s must contain exactly %s frames' % (field, length))
        for i, pair in enumerate(values):
            if type(pair) is not list or len(pair) != 2:
                _error('render_state.%s[%s] must be a two-vector' % (field, i))
            for value in pair:
                _number(value, 'render_state.%s[%s]' % (field, i))
    rows = doc.get('detections')
    if type(rows) is not list:
        _error('detections must be a JSON array')
    for i, row in enumerate(rows):
        _row(row, i, total, length if bounds_until is None else bounds_until)
    return provenance, state, rows, fps, scan_hash


def _row(row, index, total, bound_limit):
    row = _object(row, 'detections[%s]' % index)
    start = _number(row.get('t_start'), 'detections[%s].t_start' % index)
    end = _number(row.get('t_end'), 'detections[%s].t_end' % index)
    if start < 0 or end < start:
        _error('detections[%s] has an invalid time interval' % index)
    if 'last_seen' in row:
        if _number(row['last_seen'], 'detections[%s].last_seen' % index) < 0:
            _error('detections[%s].last_seen must not be negative' % index)
    for field in ('track', 'person'):
        if field in row:
            _integer(row[field], 'detections[%s].%s' % (index, field), -1)
    has_start = 'scan_frame_start' in row
    has_end = 'scan_frame_end' in row
    if has_start != has_end:
        _error('detections[%s] must have paired scan frame bounds' % index)
    if has_start:
        first = _integer(row['scan_frame_start'], 'scan_frame_start')
        after = _integer(row['scan_frame_end'], 'scan_frame_end', 1)
        if first >= after or after > total or after > bound_limit:
            _error('detections[%s] has invalid scan frame bounds' % index)


def _invalidate_output(provenance):
    # These are the output identity fields of the existing report writer.
    provenance.pop('output', None)
    provenance.pop('output_sha256', None)


def with_checkpoint(doc, frame, total, options):
    """Construct a first paused snapshot from fully postprocessed raw scan data."""
    _integer(frame, 'frame', 1)
    _integer(total, 'total', 1)
    if frame >= total:
        _error('a paused frame must be strictly before the total')
    provenance, _, rows, fps, scan_hash = _report(doc, frame, total)
    if 'stop_review' in doc:
        _error('report already has checkpoint metadata; resume it or start a fresh scan')
    options = _identity(options, total, fps, scan_hash)
    if ('checkpoint_identity' in provenance and
            not _equal_json(provenance['checkpoint_identity'], options)):
        _error('existing scan identity differs; start a fresh scan')
    for row in rows:
        if 'scan_frame_start' in row and (row['scan_frame_start'], row['scan_frame_end']) != (0, frame):
            _error('first checkpoint contains incompatible existing frame authority')
    result = _copy_json(doc)
    result['provenance']['checkpoint_identity'] = _copy_json(options)
    _invalidate_output(result['provenance'])
    for row in result['detections']:
        row['scan_frame_start'], row['scan_frame_end'] = 0, frame
    result['stop_review'] = {
        'schema': _SCHEMA, 'state': 'paused', 'next_frame': frame,
        'total_frames': total, 'fps': fps, 'input_sha256': scan_hash,
        'options': _copy_json(options),
    }
    return result


def validate_resume(doc, source_sha256=None):
    """Validate saved state; optionally compare the scan digest or full identity.

    A digest alone checks only the scan participant. A producer must compare a
    freshly measured complete identity before starting or publishing a resume.
    """
    doc = _object(doc, 'report')
    meta = _object(doc.get('stop_review'), 'stop_review')
    if type(meta.get('schema')) is not int or meta['schema'] != _SCHEMA:
        _error('unsupported checkpoint schema; start a fresh scan or explicitly migrate')
    if meta.get('state') != 'paused':
        _error('report is not paused at a checkpoint')
    frame = _integer(meta.get('next_frame'), 'stop_review.next_frame', 1)
    total = _integer(meta.get('total_frames'), 'stop_review.total_frames', 1)
    if frame >= total:
        _error('checkpoint must leave unprocessed frames')
    meta_fps = _number(meta.get('fps'), 'stop_review.fps', positive=True)
    provenance, _, _, fps, scan_hash = _report(doc, frame, total)
    if meta_fps != fps or _digest(meta.get('input_sha256'), 'stop_review.input_sha256') != scan_hash:
        _error('checkpoint FPS or input SHA-256 differs from the report')
    options = _identity(meta.get('options'), total, fps, scan_hash)
    retained = _identity(provenance.get('checkpoint_identity'), total, fps, scan_hash)
    if not _equal_json(options, retained):
        _error('checkpoint and provenance identities differ')
    if source_sha256 is not None:
        if type(source_sha256) is str:
            if _digest(source_sha256, 'current input SHA-256') != scan_hash:
                _error('scanned source changed; start a fresh scan')
        else:
            current = _identity(source_sha256, total, fps, scan_hash)
            if not _equal_json(current, options):
                _error('source or effective scan settings changed; start a fresh scan')
    return _copy_json(meta)


def join_reports(previous, continuation, next_frame, total_frames, completed=False):
    """Merge strictly advancing new scan output into the full prior raw report."""
    meta = validate_resume(previous)
    _integer(next_frame, 'next_frame', 1)
    _integer(total_frames, 'total_frames', 1)
    if type(completed) is not bool:
        _error('completed must be a boolean')
    boundary, total = meta['next_frame'], meta['total_frames']
    if total_frames != total or next_frame <= boundary or next_frame > total:
        _error('resume must advance within the original source frame count')
    if completed != (next_frame == total):
        _error('completion must end at the total; partial progress must end before it')
    prov, state, rows, fps, scan_hash = _report(continuation, next_frame, total, bounds_until=total)
    if fps != meta['fps'] or scan_hash != meta['input_sha256']:
        _error('continuation FPS or scanned source differs')
    current = _identity(prov.get('checkpoint_identity'), total, fps, scan_hash)
    if not _equal_json(current, meta['options']):
        _error('continuation source or effective scan settings changed')
    if completed:
        proof = _object(continuation.get('scan_completion'), 'scan_completion')
        if (not current['timeline']['count_verified'] or
                proof.get('reason') != 'accounted_verified_range' or
                type(proof.get('next_frame')) is not int or proof['next_frame'] != total or
                type(proof.get('total_frames')) is not int or proof['total_frames'] != total):
            _error('completion requires a verified count and accounted full-range proof')
    result = _copy_json(previous)
    result_state = result['render_state']
    for field in ('cum', 'bands'):
        result_state[field] = result_state[field] + _copy_json(state[field][boundary:next_frame])
    _invalidate_output(result['provenance'])
    remap = {'track': {}, 'person': {}}
    maxima = {field: max([row.get(field, -1) for row in result['detections']] + [-1])
              for field in remap}
    for row in rows:
        start = max(boundary, row.get('scan_frame_start', boundary))
        end = min(next_frame, row.get('scan_frame_end', next_frame))
        # Intersect the renderer's inclusive +/- .01 time test with actual
        # frame indices, not merely the continuous interval between them.
        if start >= end:
            continue
        time_start, time_end = row['t_start'] - .01, row['t_end'] + .01
        if time_end < start / fps or time_start > (end - 1) / fps:
            continue
        first = max(start, math.floor(time_start * fps))
        while first < end and first / fps < time_start:
            first += 1
        if first >= end or first / fps > time_end:
            continue
        new = _copy_json(row)
        new['scan_frame_start'], new['scan_frame_end'] = start, end
        for field in remap:
            original = new.get(field, -1)
            if original >= 0:
                mapping = remap[field]
                if original not in mapping:
                    mapping[original] = _integer(
                        maxima[field] + 1 + len(mapping), 'fresh %s ID' % field)
                new[field] = mapping[original]
        result['detections'].append(new)
    if completed:
        del result['stop_review']
        # Machine audio can be added once when it was deferred/absent; reviewed
        # redactions and even an explicit empty previous list remain untouched.
        for field in ('audio_suggestions', 'audio_transcript'):
            if field not in result and field in continuation:
                result[field] = _copy_json(continuation[field])
    else:
        result['stop_review']['next_frame'] = next_frame
    return result
