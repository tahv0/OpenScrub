"""Private, caller-locked thumbnail primitives."""
import math
import cv2


class ThumbnailDecodeError(ValueError):
    """The requested thumbnail frame could not be obtained safely."""


def read_ordinal_capture(cap, index, *, count):
    if type(index) is not int or type(count) is not int or count <= 0 or not 0 <= index < count:
        raise ThumbnailDecodeError('thumbnail unavailable')
    if not cap.isOpened() or not cap.set(cv2.CAP_PROP_POS_FRAMES, index):
        raise ThumbnailDecodeError('thumbnail unavailable')
    pos = cap.get(cv2.CAP_PROP_POS_FRAMES)
    if not math.isfinite(pos) or abs(pos - index) > 1e-6:
        raise ThumbnailDecodeError('thumbnail unavailable')
    ok, frame = cap.read()
    if not ok or frame is None or not frame.size:
        raise ThumbnailDecodeError('thumbnail unavailable')
    pos = cap.get(cv2.CAP_PROP_POS_FRAMES)
    if not math.isfinite(pos) or abs(pos - (index + 1)) > 1e-6:
        raise ThumbnailDecodeError('thumbnail unavailable')
    return frame

import hashlib
import json
import os
import tempfile
import uuid
from dataclasses import dataclass, field


class ThumbnailPending(Exception):
    pass


class ThumbnailObsolete(Exception):
    pass


class ThumbnailRecipeError(ValueError):
    pass


@dataclass(frozen=True)
class Candidate:
    incarnation: object = None
    report_epoch: object = None
    source_epoch: object = None
    operation: object = None
    selected_source: object = None
    source_path: object = None
    source_stamp: object = None
    report_path: object = None
    report_stamp: object = None
    source_handle: object = None
    report_handle: object = None


@dataclass(frozen=True, eq=False)
class Generation:
    version: str
    incarnation: object
    report_epoch: object
    source_epoch: object
    operation: object
    selected_source: object
    source_path: object
    source_stamp: object
    report_path: object
    report_stamp: object
    crop_recipe: str
    detframe_recipe: str
    row_count: int
    validated: bool


@dataclass(frozen=True)
class JPEGEntry:
    kind: str
    index: int
    path: str
    stamp: object
    size: int
    etag: str


@dataclass(frozen=True)
class StagedJPEG:
    path: str
    destination: str
    stamp: object
    size: int
    etag: str


@dataclass(frozen=True)
class Recipe:
    kind: str
    cbox: tuple
    candidate_times: tuple
    indices: tuple
    offsets: tuple
    padding: int
    jpeg_quality: int
    outline_expansion: int
    outline_thickness: int
    recipe_version: str


@dataclass(eq=False)
class FillTicket:
    generation: Generation
    kind: str
    index: int
    obsolete: bool = False
    settled: bool = False
    stage_path: object = None
    stage_closed: bool = True
    prospective_destination: object = None


@dataclass(eq=False)
class ReaderTicket:
    generation: Generation
    entry: JPEGEntry
    file: object
    released: bool = False


@dataclass(eq=False)
class Retirement:
    paths: set = field(default_factory=set)
    fills: set = field(default_factory=set)
    readers: set = field(default_factory=set)
    claimed: object = None


@dataclass(eq=False)
class CleanupBatch:
    retirement: Retirement
    paths: tuple


class ThumbnailState:
    def __init__(self):
        self.current = None
        self.discovery = None
        self.entries = {}
        self.fills = set()
        self.readers = set()
        self.retirement = None


def raw_row_fingerprint(row):
    digest = hashlib.sha256(b'openscrub-thumbnail-row-v1\0')
    for fragment in json.JSONEncoder(sort_keys=True, ensure_ascii=True, separators=(',', ':'), allow_nan=True).iterencode(row):
        digest.update(fragment.encode('ascii'))
    return digest.hexdigest()


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ThumbnailRecipeError('invalid thumbnail recipe')
    return float(value)


def recipe_for_row(row, render_state, kind):
    try:
        if kind not in ('crop', 'detframe'):
            raise ThumbnailRecipeError('invalid thumbnail kind')
        start, end = _number(row['t_start']), _number(row['t_end'])
        last, fps = _number(row.get('last_seen', start)), _number(render_state['fps'])
        box = tuple(_number(x) for x in row['cbox'])
        cum = render_state['cum']
        if start < 0 or end < start or fps <= 0 or len(box) != 4 or box[2] <= box[0] or box[3] <= box[1] or not cum:
            raise ThumbnailRecipeError('invalid thumbnail recipe')
        times = (min(max(last, start), end), (start + end) / 2, min(start + .2, end))
        if kind == 'detframe': times = times[:1]
        indices = tuple(max(0, min(math.floor(t * fps), len(cum) - 1)) for t in times)
        offsets = tuple(tuple(_number(v) for v in cum[k]) for k in indices)
        if any(len(offset) != 2 for offset in offsets): raise ThumbnailRecipeError('invalid thumbnail recipe')
        return Recipe(kind, box, times, indices, offsets, 24, 80 if kind == 'crop' else 84,
                      0 if kind == 'crop' else 4, 2 if kind == 'crop' else 3,
                      'crop-v3' if kind == 'crop' else 'detframe-v3')
    except (KeyError, TypeError, OverflowError, IndexError) as exc:
        raise ThumbnailRecipeError('invalid thumbnail recipe') from exc


def crop_frame(frame, cbox, offset):
    h, w = frame.shape[:2]; pad = 24
    x1 = min(w, max(0, int(cbox[0] + offset[0]) - pad))
    y1 = min(h, max(0, int(cbox[1] + offset[1]) - pad))
    x2 = min(w, max(0, int(cbox[2] + offset[0]) + pad))
    y2 = min(h, max(0, int(cbox[3] + offset[1]) + pad))
    crop = frame[y1:y2, x1:x2].copy()
    if not crop.size: return None, False
    inner = crop[pad:-pad or None, pad:-pad or None]
    nonblank = bool(inner.size and float(inner.std()) > 8)
    cv2.rectangle(crop, (pad, pad), (crop.shape[1] - pad, crop.shape[0] - pad), (0, 0, 255), 2)
    return crop, nonblank


def encode_jpeg(image, quality):
    ok, result = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok: raise ThumbnailDecodeError('thumbnail unavailable')
    return result.tobytes()


def _stamp(path):
    s = os.stat(path)
    return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)


def jpeg_etag(kind, version, index, jpeg):
    digest = hashlib.sha256(b'openscrub-thumbnail-jpeg-v1\0')
    for component in (kind, version, str(index)):
        digest.update(component.encode('ascii'))
        digest.update(b'\0')
    digest.update(jpeg)
    return '"' + digest.hexdigest() + '"'


def stage_jpeg(job_dir, ticket, jpeg):
    if ticket.kind not in ('crop', 'detframe') or type(ticket.index) is not int or ticket.index < 0 or ticket.settled or ticket.stage_path is not None:
        raise ValueError('invalid thumbnail ticket')
    final = os.path.join(os.fspath(job_dir), 'thumb3_%s_%s_%d.jpg' % (ticket.generation.version, ticket.kind, ticket.index))
    fd, path = tempfile.mkstemp(prefix='.thumb3-stage-', dir=job_dir)
    ticket.stage_path = path
    ticket.stage_closed = False
    try:
        out = os.fdopen(fd, 'wb')
    except BaseException:
        os.close(fd)
        ticket.stage_closed = True
        raise
    try:
        with out:
            out.write(jpeg); out.flush(); os.fsync(out.fileno())
    finally:
        ticket.stage_closed = out.closed
    return StagedJPEG(path, final, _stamp(path), len(jpeg), jpeg_etag(ticket.kind, ticket.generation.version, ticket.index, jpeg))


def accept_generation_locked(state, candidate, row_count):
    if type(row_count) is not int or row_count < 0: raise ValueError('invalid row count')
    if state.current is not None: raise ValueError('generation already selected')
    g = Generation(uuid.uuid4().hex, candidate.incarnation, candidate.report_epoch,
                   candidate.source_epoch, candidate.operation, candidate.selected_source,
                   candidate.source_path, candidate.source_stamp, candidate.report_path,
                   candidate.report_stamp, 'crop-v3', 'detframe-v3', row_count, True)
    state.current = g
    return g



def begin_discovery_locked(state):
    if state.current is not None or state.discovery is not None: raise ThumbnailPending()
    ticket = object()
    state.discovery = ticket
    return ticket


def accept_discovery_locked(state, ticket, candidate, row_count):
    if state.discovery is not ticket: raise ThumbnailObsolete()
    result = accept_generation_locked(state, candidate, row_count)
    state.discovery = None
    return result


def finish_discovery_locked(state, ticket):
    if state.discovery is ticket: state.discovery = None

def begin_fill_locked(state, generation, kind, index):
    if state.current is not generation: raise ThumbnailObsolete()
    if kind not in ('crop', 'detframe') or type(index) is not int or not 0 <= index < generation.row_count: raise ValueError('invalid thumbnail key')
    if state.retirement is not None or len(state.fills) >= 4 or any(t.generation is generation and (t.kind, t.index) == (kind, index) for t in state.fills): raise ThumbnailPending()
    if (kind, index) in state.entries: raise ThumbnailPending()
    ticket = FillTicket(generation, kind, index); state.fills.add(ticket); return ticket


def accept_jpeg_locked(state, ticket, staged):
    if ticket not in state.fills or ticket.obsolete or state.current is not ticket.generation or state.retirement is not None: raise ThumbnailObsolete()
    key = ticket.kind, ticket.index
    expected = 'thumb3_%s_%s_%d.jpg' % (ticket.generation.version, ticket.kind, ticket.index)
    if not ticket.stage_closed or staged.path != ticket.stage_path or os.path.basename(staged.destination) != expected or os.path.dirname(staged.path) != os.path.dirname(staged.destination): raise ValueError('stage does not belong to ticket')
    if key in state.entries: raise ThumbnailObsolete()
    ticket.prospective_destination = staged.destination
    os.replace(staged.path, staged.destination)
    entry = JPEGEntry(ticket.kind, ticket.index, staged.destination, staged.stamp, staged.size, staged.etag)
    state.entries[key] = entry
    ticket.stage_path = None
    ticket.prospective_destination = None
    return entry


def invalidate_locked(state, reason):
    old = state.current
    if state.entries or state.fills or state.readers:
        if state.retirement is None: state.retirement = Retirement()
        retirement = state.retirement
        retirement.paths.update(entry.path for entry in state.entries.values())
        for ticket in state.fills:
            if ticket.generation is old:
                ticket.obsolete = True; retirement.fills.add(ticket)
        retirement.readers.update(t for t in state.readers if t.generation is old)
    state.entries.clear(); state.current = None; state.discovery = None
    return state.retirement


def finish_fill_locked(state, ticket, owned_path=None):
    if ticket not in state.fills or ticket.settled: raise ValueError('unknown fill')
    if not ticket.stage_closed: raise ValueError('stage writer remains open')
    if owned_path is not None and os.fspath(owned_path) != ticket.stage_path: raise ValueError('wrong owned stage')
    owned_paths = {path for path in (ticket.stage_path, ticket.prospective_destination) if path is not None}
    if owned_paths:
        if state.current is ticket.generation:
            invalidate_locked(state, 'failed stage')
        if state.retirement is None: raise ValueError('missing retirement')
        state.retirement.paths.update(os.fspath(path) for path in owned_paths)
    if state.retirement is not None: state.retirement.fills.discard(ticket)
    state.fills.remove(ticket); ticket.stage_path = None; ticket.prospective_destination = None; ticket.settled = True
    _clear_retirement(state)


def begin_reader_locked(state, generation, entry, file):
    """Pin an already-open file after the caller checks its identity and stamp."""
    if state.current is not generation or state.entries.get((entry.kind, entry.index)) is not entry or file.closed: raise ThumbnailObsolete()
    ticket = ReaderTicket(generation, entry, file); state.readers.add(ticket); return ticket


def end_reader_locked(state, ticket):
    """Release a pin only after the caller closes its exact opened file."""
    if ticket not in state.readers or not ticket.file.closed: raise ValueError('reader must close before release')
    state.readers.remove(ticket); ticket.released = True
    if state.retirement is not None: state.retirement.readers.discard(ticket)
    _clear_retirement(state)


def _clear_retirement(state):
    r = state.retirement
    if r is not None and not r.paths and not r.fills and not r.readers and r.claimed is None: state.retirement = None


def claim_cleanup_locked(state):
    """Claim unpinned paths; caller must complete this batch in a finally block."""
    r = state.retirement
    if r is None or r.claimed is not None: return None
    pinned = {reader.entry.path for reader in r.readers}
    paths = tuple(sorted(r.paths - pinned))
    if not paths: _clear_retirement(state); return None
    batch = CleanupBatch(r, paths); r.claimed = batch; return batch


def cleanup(batch, unlink=os.unlink):
    succeeded = set()
    for path in batch.paths:
        for _ in range(3):
            try:
                unlink(path)
            except FileNotFoundError:
                succeeded.add(path); break
            except OSError:
                continue
            else:
                succeeded.add(path); break
    return succeeded


def complete_cleanup_locked(state, batch, succeeded):
    """Apply the outside-lock cleanup result to the same claimed batch."""
    r = state.retirement
    if r is not batch.retirement or r.claimed is not batch or not set(succeeded).issubset(batch.paths): raise ValueError('wrong cleanup batch')
    r.paths.difference_update(succeeded); r.claimed = None; _clear_retirement(state)
