"""Web adapter for explicit confirmed examples and compact image review."""
from copy import deepcopy
from functools import wraps
import hashlib
import json
import math
from pathlib import Path
import re
import threading
import time

import cv2
import numpy as np
from flask import Response, abort, jsonify, request, g, has_request_context
from werkzeug.exceptions import HTTPException

import confirmed_findings as library
import finding_previews as previews
import plate_boundaries
import findings_training as training
import learning_session
import stop_review
import review_journal
import video_learning


RESERVED = {'learned_plate_models', 'confirmed_findings', 'learned_model_training'}
_LEGACY_TIMING_NOTE = ('This legacy variable-frame-rate picture uses an approximate timestamp. '
    'Output and draft area edits remain available. Rescan with frame-rate normalization '
    'before saving confirmed training examples.')
_OFF_FRAME_GEOMETRY_NOTE = (
    'Detector box or plate corners extend outside the source video frame. '
    'This original-frame picture is for inspection only. Use Redraw plate area '
    'on its exact source frame to replace the invalid detection before saving '
    'corners or trusted training. Automatic redaction is unchanged.')
_web = None


def root():
    return Path(_web.JOBS_DIR) / 'confirmed_findings'


def _guard(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except library.ConflictError as error:
            return jsonify(error=str(error),current_archive=getattr(error,'current_archive',None)), 409
        except review_journal.ConflictError as error:
            return jsonify(error=str(error)), 409
        except HTTPException as error:
            # A displayed JPEG can be evicted by bounded background prefetch.
            # Return a machine-readable recovery hint so the browser may
            # reload the JPEG without sacrificing the user's unsaved draft.
            if error.code == 409 and error.description.startswith(
                    'This displayed picture is no longer a valid cached sample.'):
                return jsonify(error=error.description,
                               conflict='stale_preview'), 409
            raise
        except (KeyError, FileNotFoundError):
            return jsonify(error='This saved finding is no longer available.'), 404
        except ValueError as error:
            return jsonify(error=str(error)), 400
    return wrapped


def _body():
    value = request.get_json(silent=True)
    if not isinstance(value, dict):
        abort(400, description='Supply a JSON object.')
    return value


def _job(jid, edit=False):
    job = _web.JOBS.get(jid) or abort(404)
    if edit and job['phase'] not in ('review', 'paused', 'done'):
        abort(409, description='Pause or finish scanning before saving review decisions.')
    return job


def _source_hash(doc):
    # Some legacy reports explicitly contain compact_preview_source=None.
    # dict.get(..., fallback) does NOT use its fallback for that case.
    return (doc.get('compact_preview_source')
            or (doc.get('provenance') or {}).get('input_sha256')
            or (doc.get('source_identity') or {}).get('input_sha256'))


def _token(doc, row, frame, sample_key=None):
    value = [_source_hash(doc), frame,
             sample_key, row['category'], row['cbox'], row.get('plate_quad') or [],
             doc['render_state']['cum'][frame], doc.get('preview_revision')]
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def _cold_frame(job,doc,row,frame,box,points,long_retry=False):
    """Decode only a source-verified original-frame crop, not a full 4K PPM."""
    if not _web._REVIEW_WORK_LOCK.acquire(blocking=False):
        abort(503,description='Another preview is decoding. Retry shortly.')
    try:
        if _web.vault_locked():
            abort(423)
        identity = _web._video_identity(job['video'])
        expected = (doc.get('provenance') or {}).get('input_sha256') or (doc.get('source_identity') or {}).get('input_sha256')
        signature = (identity,expected)
        verified = job.get('_finding_source_verified')
        if not verified or verified['signature'] != signature:
            actual = learning_session.sha256(job['video'])
            if expected and actual != expected:
                raise library.ConflictError('The source video changed. Rescan it before creating new previews or examples.')
            verified = dict(signature=signature,sha256=actual)
            job['_finding_source_verified'] = verified
        rs = doc['render_state']
        info = _web._review_probe(job['video'],identity)
        if not math.isclose(float(rs['fps']),info['fps'],rel_tol=1e-4,abs_tol=.001):
            raise library.ConflictError('The source frame rate differs from the saved review timeline. Rescan before creating new previews.')
        source_identity = doc.get('source_identity') or {}
        if any(source_identity.get(key) not in (None,info[key]) for key in ('width','height')):
            raise library.ConflictError('The source dimensions differ from the saved review timeline. Rescan before creating new previews.')
        # Compute and validate the crop using original source dimensions
        # BEFORE requesting pixels. The JPEG and metadata retain original
        # coordinates, so a manually drawn quad remains frame-bound.
        crop = _web._plate_editor_crop(box, points, info['width'], info['height'])
        budget = 60 if long_retry else None
        approximate = row.get('frame_index',-1) < 0 and not info['cfr']
        source = dict(sha256=verified['sha256'],timing='timestamp' if approximate else 'frame')
        if approximate:
            # Preserve the legacy review timestamp, without pretending that
            # timestamp seeking established an exact source frame for training.
            tref = min(max(float(row.get('last_seen',row['t_start'])),float(row['t_start'])),float(row['t_end']))
            source['requested_time'] = tref
            pixels = _web._frame_at(job,tref,rs,None,
                                    crop=crop,decode_timeout=budget)
        else:
            pixels = _web._frame_at(job,frame/float(rs['fps']),rs,frame,
                                    crop=crop,decode_timeout=budget)
        if _web._video_identity(job['video']) != identity:
            job.pop('_finding_source_verified',None)
            raise library.ConflictError('The source changed while reading this preview. Retry with the original video.')
        return pixels,source,crop,info['width'],info['height']
    finally:
        _web._REVIEW_WORK_LOCK.release()


def preview(job, index, doc=None, cache_only=False, preferred_key=None,
            exact_only=False, retry_decode=False):
    """Return source geometry and compact pixels; a warm read never opens video."""
    doc = doc if doc is not None else _web._load_preview_report(job)
    if not 0 <= index < len(doc.get('detections', [])):
        abort(404)
    row, rs = doc['detections'][index], doc['render_state']
    frame = video_learning._frame(row, rs)
    if row.get('frame_index',-1) < 0:
        tref = min(max(float(row.get('last_seen',row['t_start'])),float(row['t_start'])),float(row['t_end']))
        position = tref*float(rs['fps'])
        if 0 <= position < len(rs['cum']):
            # A valid final legacy timestamp may round to the exclusive end.
            # Keep its coordinate lookup on the last available timeline entry.
            frame = min(round(position),len(rs['cum'])-1)
    if not 0 <= frame < len(rs['cum']):
        abort(400, description='Finding is outside the scanned timeline.')
    # Match the canonical report frame even when a legacy fractional timestamp
    # would be rounded differently by the generic cache's time-based lookup.
    cache_row = dict(row,frame_index=frame)
    if row.get('category') == 'plate' and not plate_boundaries.trusted_plate_quad(row):
        cache_row['plate_quad'] = []
    if preferred_key is not None:
        # An in-flight cache fill may add a newer exact sample, but must not
        # change the source JPEG of a human decision already being saved.
        # Verify both the pinned sample's binding and the full preview_token.
        cached = _web._serialize_review_read(previews.lookup)(
            job['dir'], cache_row, rs, allow_representative=True,
            preferred_key=preferred_key)
        if cached is None:
            abort(409, description='This displayed picture is no longer a valid cached sample. Reload its preview.')
    else:
        cached = _web._serialize_review_read(previews.lookup)(job['dir'], cache_row, rs)
        if (cached is None and not exact_only and not row.get('source_repair_receipt')
                and int(row.get('track', -1)) >= 0):
            cached = _web._serialize_review_read(previews.lookup)(
                job['dir'], cache_row, rs, allow_representative=True)
    if cached is None and cache_only:
        return None
    box = list(map(float, video_learning._screen_box(row, rs, frame)))
    q = cache_row.get('plate_quad') or ((0., 0.), (1., 0.), (1., 1.), (0., 1.))
    points = [[box[0]+x*(box[2]-box[0]), box[1]+y*(box[3]-box[1])] for x,y in q]
    if cached is None:
        # Legacy jobs may need one bounded CPU decode. All subsequent thumbnail,
        # confirmation and area-editor requests share this compact cache.
        pixels,source,crop,w,h = _cold_frame(
            job,doc,row,frame,box,points,long_retry=retry_decode)
        if pixels is None:
            abort(404, description='Source frame is unavailable and has no saved preview.')
        meta = dict(width=w, height=h, crop=crop, box=box, points=points,
                    frame=frame, t=frame/float(rs['fps']), fps=float(rs['fps']),
                    source=source,
                    track=row.get('track', -1))
        cached = _web._serialize_review_read(previews.store)(
            job['dir'], cache_row, rs, meta, pixels)
    meta, jpeg = cached
    source = meta.get('source') or {}
    exact = source.get('timing') != 'timestamp'
    unsafe_geometry = meta.get('geometry_outside_frame') is True
    representative = meta.get('match') == 'representative'
    shown_frame = int(meta['frame']) if representative else frame
    shown_box = list(map(float, meta['box'])) if representative else box
    shown_points = meta.get('points') if representative else points
    shown_t = float(meta.get('t', shown_frame/float(rs['fps'])))
    sample_key = meta.get('key')
    meta = dict(meta, i=index, frame=shown_frame,
                frame_index=shown_frame if exact else -1,
                t=shown_t if exact else source['requested_time'], box=shown_box,
                points=shown_points, track=row.get('track', -1), compact=True,
                exact_frame=exact, source_repaired=bool(row.get('source_repair_receipt')),
                classification_allowed=exact and not unsafe_geometry,
                classification_note=(_OFF_FRAME_GEOMETRY_NOTE if unsafe_geometry
                                     else None if exact else _LEGACY_TIMING_NOTE),
                requested_frame=frame,
                preview_token=_token(doc, row, shown_frame, sample_key))
    if not exact:
        meta['match'] = 'timestamp'
    source_row = dict(row, plate_quad=[])
    meta['source_token'] = _token(doc, source_row, shown_frame, sample_key)
    # Separate the immutable *frame/box/timeline* binding from the mutable
    # JPEG cache key. A picture may be evicted while a person adjusts corners;
    # a newly fetched crop of the very SAME source frame may safely reuse
    # those frame coordinates, but a changed frame or detection may not.
    meta['frame_source_token'] = (
        _token(doc, source_row, shown_frame, None) if _source_hash(doc) else None)
    return doc, row, meta, jpeg



_REPAIR_VERIFY_LOCK = threading.Lock()


def _plate_repair_source_check(job, identity, expected):
    """Start one nonblocking SHA-256 verification for the selected source.

    A preview GET can show exact PTS-checked pixels before this multi-GB
    integrity check completes. POST must still wait for successful verification.
    Never reuse a SHA from a different file stat or source hash.
    """
    signature = (identity, expected)
    with _REPAIR_VERIFY_LOCK:
        previous = job.get('_plate_repair_source_check')
        if previous and previous['signature'] == signature:
            return previous['status']
        if previous and previous['status'] == 'pending':
            raise library.ConflictError(
                'The source video changed while an earlier integrity check is running. '
                'Reopen Review after it completes.')
        verified = job.get('_finding_source_verified')
        if verified and verified.get('signature') == signature:
            job['_plate_repair_source_check'] = dict(signature=signature,
                                                     status='verified')
            return 'verified'
        record = dict(signature=signature, status='pending')
        job['_plate_repair_source_check'] = record

    def verify():
        started = time.monotonic()
        try:
            digest = learning_session.sha256(job['video'])
            unchanged = _web._video_identity(job['video']) == identity
            valid = unchanged and digest == expected
        except (OSError, ValueError):
            valid = False
        with _REPAIR_VERIFY_LOCK:
            if job.get('_plate_repair_source_check') is record:
                record['status'] = 'verified' if valid else 'failed'
                if valid:
                    job['_finding_source_verified'] = dict(
                        signature=signature, sha256=expected)
        try:
            _web.diagnostics.event(
                'plate_repair_source_hash_finished', job,
                status='verified' if valid else 'failed',
                elapsed_ms=round((time.monotonic()-started)*1000))
        except Exception:
            pass

    threading.Thread(target=verify, name='openscrub-repair-source-hash',
                     daemon=True).start()
    return 'pending'


def _plate_repair_require_verified(job, identity, expected):
    signature = (identity, expected)
    with _REPAIR_VERIFY_LOCK:
        state = job.get('_plate_repair_source_check')
        status = state.get('status') if state and state.get('signature') == signature else None
    if status == 'pending':
        abort(503, description='Original video verification is still running. '
              'The replacement was not saved; retry the same request shortly.')
    if status != 'verified' or _web._video_identity(job['video']) != identity:
        raise library.ConflictError(
            'Original video verification failed or the source changed. '
            'No plate correction was saved.')


def _plate_repair_preview(job, index, doc=None):
    """Metadata-only, exact-frame identity independent of disposable JPEG keys.

    Do not call preview(): that can hash a huge source file and decode an
    unrelated compact crop before the user can even open the full-frame tool.
    The image returned by plate_repair_frame is separately PTS-checked.
    """
    doc = doc if doc is not None else _web._load_preview_report(job)
    if not (0 <= index < len(doc.get('detections', []))):
        abort(404)
    row = doc['detections'][index]
    if row.get('category') != 'plate':
        abort(404)
    rs = doc['render_state']
    fps = float(rs['fps'])
    if fps <= 0 or float(row['t_end']) - float(row['t_start']) > 1.5 / fps:
        raise library.ConflictError(
            'This detection spans several frames. Open the video editor to '
            'correct a time interval instead of applying one frame shape.')
    frame = int(row.get('frame_index', -1))
    if not (0 <= frame < len(rs.get('cum') or [])):
        raise library.ConflictError('Redraw needs an exact indexed source frame.')
    if not _source_hash(doc):
        raise library.ConflictError(
            'This scan has no verified source identity. Rescan or restore its source metadata.')
    dimensions = doc.get('source_identity') or {}
    width, height = int(dimensions.get('width') or 0), int(dimensions.get('height') or 0)
    if width <= 0 or height <= 0:
        info = _web._review_probe(job['video'], _web._video_identity(job['video']))
        width, height = info['width'], info['height']
    box = video_learning._screen_box(row, rs, frame)
    quad = row.get('plate_quad') or ((0., 0.), (1., 0.), (1., 1.), (0., 1.))
    points = [[box[0]+float(x)*(box[2]-box[0]),
               box[1]+float(y)*(box[3]-box[1])] for x, y in quad]
    if not previews._outside_source_frame(box, points, width, height):
        raise library.ConflictError(
            'This detection no longer extends beyond the source video. '
            'Reload Review to edit its corrected corners.')
    source_row = dict(row, plate_quad=[])
    meta = dict(i=index, width=width, height=height, frame=frame,
                requested_frame=frame, box=box, points=points,
                geometry_outside_frame=True, exact_frame=True,
                preview_token=_token(doc, row, frame, None),
                frame_source_token=_token(doc, source_row, frame, None))
    return doc, row, meta


def plate_repair_frame(job, index):
    """Return a FULL, PTS-verified source frame for an explicit user redraw.

    A thumbnail may be cropped around the wrong detector rectangle, hiding
    the real plate. Never redraw on a neighboring track representative.
    """
    began = time.monotonic()
    doc, _, meta = _plate_repair_preview(job, index)
    prepared = time.monotonic()
    identity = _web._video_identity(job['video'])
    expected = ((doc.get('provenance') or {}).get('input_sha256')
                or (doc.get('source_identity') or {}).get('input_sha256'))
    if not expected:
        raise library.ConflictError('An original video SHA-256 is required for a plate repair.')
    # First return exact PTS-checked pixels; the multi-GB SHA check runs in a
    # single background worker and gates POST, not the browser's image GET.
    original = _web._read_exact_frame(job['video'], meta['frame'], decode_timeout=60)
    if original is None or _web._video_identity(job['video']) != identity:
        raise library.ConflictError('The original source frame changed or could not be decoded.')
    height, width = original.shape[:2]
    if (width, height) != (int(meta['width']), int(meta['height'])):
        raise library.ConflictError('Source dimensions changed. No correction was saved.')
    decoded = time.monotonic()
    scale = min(1., 1920.0 / max(width, height))
    displayed = (cv2.resize(original, (max(1, round(width * scale)),
                                     max(1, round(height * scale))),
                            interpolation=cv2.INTER_AREA)
                 if scale < 1 else original)
    ok, encoded = cv2.imencode('.jpg', displayed, [cv2.IMWRITE_JPEG_QUALITY, 82])
    if not ok:
        abort(500, description='Could not encode the exact source frame.')
    encoded_at = time.monotonic()
    status = _plate_repair_source_check(job, identity, expected)
    # Keep a single bounded full-resolution frame in RAM until its explicit
    # redraw is saved, so the corrected JPEG can be prepared without another
    # costly 4K FFmpeg seek. Never write these private pixels to logs.
    job['_plate_repair_frame_cache'] = (
        dict(identity=identity, frame=meta['frame'], pixels=original)
        if original.nbytes <= 48 * 1024 * 1024 else None)
    if encoded_at-began >= 1:
        try:
            _web.diagnostics.event('plate_repair_frame_stages', job,
                metadata_ms=round((prepared-began)*1000),
                ffmpeg_decode_ms=round((decoded-prepared)*1000),
                jpeg_encode_ms=round((encoded_at-decoded)*1000),
                source_hash_status=status)
        except Exception:
            pass
    # A POST must prove that this SAME current process served the full exact
    # frame, not merely that a cropped/borrowed JPEG existed.
    evidence = dict(identity=identity, source_sha256=expected,
                    frame=meta['frame'], preview_token=meta['preview_token'],
                    frame_source_token=meta['frame_source_token'])
    receipts = job.setdefault('_plate_repair_views', {})
    receipts[index] = evidence
    if len(receipts) > 12:
        receipts.pop(next(iter(receipts)))
    response = Response(encoded.tobytes(), mimetype='image/jpeg',
                        headers={'Cache-Control': 'no-store'})
    response.headers['X-Repair-Geometry'] = json.dumps(dict(
        frame=meta['frame'], width=width, height=height,
        source_verification=status,
        preview_token=meta['preview_token'],
        frame_source_token=meta['frame_source_token']), separators=(',', ':'))
    return response


def repair_plate_anchor(job, index, payload):
    """Explicitly replace ONLY the bad source-frame box and perspective quad.

    No automatic Is/Not label, no trusted training archive, no propagation of
    one frame's polygon to the rest of a rotating/moving track.
    """
    edit_id = payload.get('edit_id')
    if not isinstance(edit_id, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,120}', edit_id):
        raise ValueError('Redrawing requires an idempotent edit identifier.')
    doc = _web._load_preview_report(job)
    if not (0 <= index < len(doc.get('detections', []))):
        abort(404)
    row = doc['detections'][index]
    receipt = row.get('source_repair_receipt') or {}
    if receipt.get('edit_id') == edit_id:
        box, quad = receipt.get('box'), row.get('plate_quad')
        current_points = ([[box[0] + float(p[0]) * (box[2]-box[0]),
                            box[1] + float(p[1]) * (box[3]-box[1])]
                           for p in quad] if box and quad and len(quad) == 4 else [])
        if (payload.get('points') != receipt.get('points')
                or receipt.get('source_sha256') != _source_hash(doc)
                or any(abs(a-b) > .01 for p, q in zip(
                    current_points, receipt['points']) for a, b in zip(p, q))
                or len(current_points) != 4):
            raise library.ConflictError('This repair has been changed or superseded.')
        return dict(ok=True, applied=1, source_repaired=True,
                    needs_confirmation=True, box=receipt['box'],
                    points=receipt['points'], frame=receipt['frame'],
                    verified_samples_added=0)
    doc, row, meta = _plate_repair_preview(job, index, doc=doc)
    if (payload.get('preview_token') != meta['preview_token']
            or payload.get('frame_source_token') != meta['frame_source_token']
            or payload.get('frame') != meta['frame']):
        raise library.ConflictError('This source frame or detector changed. Reopen Redraw plate.')
    evidence = (job.get('_plate_repair_views') or {}).get(index)
    if not evidence or any((
            evidence.get('identity') != _web._video_identity(job['video']),
            evidence.get('source_sha256') != ((doc.get('provenance') or {}).get('input_sha256')
                                                 or (doc.get('source_identity') or {}).get('input_sha256')),
            evidence.get('frame') != meta['frame'],
            evidence.get('preview_token') != meta['preview_token'],
            evidence.get('frame_source_token') != meta['frame_source_token'])):
        raise library.ConflictError(
            'Open the verified full source frame again before saving a redrawn plate.')
    _plate_repair_require_verified(job, evidence['identity'], evidence['source_sha256'])
    if ((job.get('section') or {}).get('role') == 'export'
            or any(item.get('approved') for item in
                   ((doc.get('video_sections') or {}).get('items') or []))):
        raise library.ConflictError(
            'This section is protected. Open an editable section candidate to repair it.')
    points = _shape(payload.get('points'),
                    dict(crop=[0, 0, meta['width'], meta['height']]))
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    span = max(max(xs)-min(xs), max(ys)-min(ys))
    pad = max(2., min(32., .04 * span))
    width, height = int(meta['width']), int(meta['height'])
    new_box = [max(0., float(math.floor(min(xs)-pad))),
               max(0., float(math.floor(min(ys)-pad))),
               min(float(width), float(math.ceil(max(xs)+pad))),
               min(float(height), float(math.ceil(max(ys)+pad)))]
    if not (new_box[0] < new_box[2] and new_box[1] < new_box[3]):
        raise ValueError('Select a plate area inside the original video.')
    sx, sy = new_box[2]-new_box[0], new_box[3]-new_box[1]
    normalized = [[round((x-new_box[0])/sx, 6),
                   round((y-new_box[1])/sy, 6)] for x, y in points]
    ox, oy = doc['render_state']['cum'][meta['frame']]
    new_content_box = [new_box[0]-ox, new_box[1]-oy,
                       new_box[2]-ox, new_box[3]-oy]
    patch = dict(cbox=new_content_box, plate_quad=normalized,
                 human_region_confirmed=True, plate_verification_override=True,
                 plate_verification=None, poly=[], poly_holes=[], mask_pad=-1,
                 fallback_reason='', enabled=True, output_choice_explicit=False,
                 verified_label='', human_confirmation=None,
                 confirmed_finding_id=None, confirmed_finding_revision=None,
                 source_repair_receipt=dict(edit_id=edit_id, points=points,
                                            box=new_box, frame=meta['frame'],
                                            source_sha256=_source_hash(doc)))
    # A fresh source anchor replaces the old detector identity, not any
    # previously archived human finding or its revision.
    review_journal.write_anchor(job['dir'], index, patch)
    ready = False
    frame_cache = job.pop('_plate_repair_frame_cache', None)
    if (frame_cache and frame_cache['identity'] == evidence['identity']
            and frame_cache['frame'] == meta['frame']):
        try:
            # A source SHA was fully verified before the journal write. Publish
            # the NEW source-bound JPEG before the browser asks for it: no
            # second FFmpeg seek or another full-video integrity hash.
            crop = _web._plate_editor_crop(new_box, points, width, height)
            pixels = frame_cache['pixels'][crop[1]:crop[3], crop[0]:crop[2]].copy()
            new_row = dict(row, **patch, frame_index=meta['frame'])
            source = dict(sha256=evidence['source_sha256'], timing='frame')
            previews.store(job['dir'], new_row, doc['render_state'],
                           dict(frame=meta['frame'], width=width, height=height,
                                box=new_box, crop=crop, points=points,
                                source=source), pixels)
            ready = True
        except (OSError, ValueError, TypeError, KeyError, RuntimeError):
            # The durable source-frame repair is already committed. Missing
            # cache is recoverable, never roll back or invent a saved label.
            try:
                _web.diagnostics.exception('plate_repair_preview_prewarm_failed', job)
            except Exception:
                pass
    return dict(ok=True, applied=1, source_repaired=True,
                preview_ready=ready, needs_confirmation=True, box=new_box, points=points,
                frame=meta['frame'], verified_samples_added=0)


def _video(job, doc, meta):
    if meta.get('exact_frame') is False:
        raise library.ConflictError(_LEGACY_TIMING_NOTE)
    p = doc.get('provenance') or {}
    source = p.get('input_sha256')
    if not source:
        # Old reports only: verify once on explicit confirmation, never listing.
        # Existing open thumbnails must keep their source token when this old
        # report first acquires its verified content hash.
        doc.setdefault('compact_preview_source',None)
        source = (meta.get('source') or {}).get('sha256') or learning_session.verify_source(job, doc)
        doc.setdefault('provenance', {})['input_sha256'] = source
    identity = doc.setdefault('source_identity', {})
    identity.update(input_sha256=source, width=meta['width'], height=meta['height'])
    return dict(sha256=p.get('original_input_sha256') or source, variant_sha256=source,
                name=Path(job.get('name') or p.get('original_input') or p.get('input') or 'Video').name,
                fps=float(doc['render_state']['fps']), width=meta['width'], height=meta['height'],
                total_frames=int(identity.get('total_frames') or len(doc['render_state']['cum'])))


def _require_exact_corners(row, rs, meta, payload):
    """A borrowed cached neighbor cannot authorize a narrow quad in another frame."""
    if (payload.get('points') is not None
            and int(meta['frame']) != video_learning._frame(row, rs)):
        raise library.ConflictError(
            'This picture is from another frame. Load the exact source frame before editing corners.')


def _shape(points, meta):
    try:
        value = np.asarray(points, dtype=float)
    except (ValueError,TypeError) as error:
        raise ValueError('Select four finite corner points.') from error
    if value.shape != (4,2) or not np.isfinite(value).all():
        raise ValueError('Select four finite corner points.')
    crop = meta['crop']
    if (np.any(value[:,0] < crop[0]) or np.any(value[:,0] > crop[2]) or
            np.any(value[:,1] < crop[1]) or np.any(value[:,1] > crop[3])):
        raise ValueError('Keep the corners inside the saved picture. Open the source view for a wider area.')
    contour = value.astype(np.float32).reshape(-1,1,2)
    if not cv2.isContourConvex(contour) or cv2.contourArea(contour) < 8:
        raise ValueError('Corners must form a convex region of at least eight source pixels.')
    return value.tolist()


def _archived_identity_changed(job, doc, row, meta):
    """Detect a stale training-archive link without changing its immutable ID.

    An archive ID includes source bytes/variant, timeline, frame and source
    detection box (not the editable four-corner polygon). A tracked review
    representative can change frame/box after reconciling cached scan pixels.
    That MUST NOT overwrite the original confirmed example or silently carry
    a negative classification to the new source frame.
    """
    current = row.get('confirmed_finding_id')
    if not current:
        return False
    original = library.get_finding(root(), current, include_revoked=True)
    # _video may fill legacy provenance. Inspect a tiny shallow copy instead
    # of mutating the authoritative report before its approved-section guard.
    identity_doc = dict(doc, provenance=dict(doc.get('provenance') or {}),
                        source_identity=dict(doc.get('source_identity') or {}))
    video = _video(job, identity_doc, meta)
    required = ('sha256', 'variant_sha256', 'fps', 'width', 'height', 'total_frames')
    if (original['category'] != row['category'] or
            any(original['video'].get(key) != video[key] for key in required)):
        raise library.ConflictError(
            'Confirmed finding belongs to a different source or timeline. '
            'Restore the original video and rescan before editing this example.')
    return (original['frame'] != int(meta['frame']) or
            original['box'] != [float(x) for x in meta['box']])


def _archived(job, doc, row, meta, jpeg, label, expected_revision=None):
    value = dict(category=row['category'], label=label, frame=meta['frame'],
                 box=meta['box'], crop=meta['crop'], job_id=job['id'], explicit=True,
                 shape_confirmed=bool(row.get('human_region_confirmed')),
                 points=meta['points'] if row.get('human_region_confirmed') else None)
    current = row.get('confirmed_finding_id')
    if current and _archived_identity_changed(job, doc, row, meta):
        # The user explicitly pressed Is / Not on a different verified image.
        # Create a NEW deterministic archive identity. Never mutate the
        # previous example or apply its revision to another source geometry.
        current = None
        expected_revision = None
    if current:
        value['id'] = current
        value['expected_revision'] = (expected_revision if expected_revision is not None
                                     else row.get('confirmed_finding_revision'))
    elif expected_revision is not None:
        value['expected_revision'] = expected_revision
    try:
        return library.record(root(), _video(job, doc, meta), value, jpeg)
    except library.ConflictError as error:
        # The archive may already be durable when a report write or its HTTP
        # acknowledgment failed. A matching current value is a safe receipt;
        # a different newer human decision must still raise a conflict.
        if current:
            state = library.revision_state(root(),current)
            latest = library.get_finding(root(), current) if not state['revoked'] else None
            if latest and all(latest.get(key) == value.get(key)
                   for key in ('label', 'points', 'shape_confirmed')):
                return latest
            error.current_archive = state
        raise


def _members(doc, index):
    row = doc['detections'][index]
    tid = row.get('track', -1)
    person = row.get('person', -1)
    return [(i,d) for i,d in enumerate(doc['detections'])
            if i == index or (d['category'] == row['category'] and
                (d.get('person', -1) == person if person >= 0 else tid >= 0 and d.get('track', -1) == tid))]


def _guard_section(job, before, after):
    if before.get('video_sections') or (job.get('section') or {}).get('role') == 'export':
        _web._SECTIONS.guard_edits(job, before, after)



def _journal_doc(job):
    """Only section-safe, source-bound reviews take the incremental path."""
    doc = _web._load_preview_report(job)
    sections = ((doc.get('video_sections') or {}).get('items') or [])
    if ((job.get('section') or {}).get('role') == 'export'
            or any(item.get('approved') for item in sections)
            or not (doc.get('provenance') or {}).get('input_sha256')
            or not doc.get('source_identity')):
        return None
    return doc


def _journal_members(doc, index):
    rows = doc['detections']
    return (rows.member_count(index) if hasattr(rows, 'member_count')
            else review_journal.member_count(rows, index))


def _journal_matches_archived_source(job, doc, index, preferred_key=None):
    """Never carry a confirmed label over to a different source box/frame.

    The fast path may edit an existing archive only while its immutable
    identity still matches the displayed exact-frame representative.
    Relocalization must take the full legacy protection/rebind path.
    """
    row = doc['detections'][index]
    if not row.get('confirmed_finding_id'):
        return True
    _, _, meta, _ = preview(job, index, doc=doc, preferred_key=preferred_key)
    return not _archived_identity_changed(job, doc, row, meta)


_CONFIRM_SLOW_TRACE_SECONDS = 3.0


class _ConfirmTrace:
    """Stage timings for slow confirmations only; never include source PII.

    A successful HTTP 200 that takes 115 seconds has already acquired the
    nonblocking review-edit lock. Identify its active operation before
    changing locking or journal durability.
    """
    def __init__(self, job):
        self.job = job
        self.start = self.last = time.monotonic()
        self.mode = 'selecting'
        self.current = 'start'
        self.stages = {}

    def enter(self, name):
        self.current = name

    def mark(self, name):
        now = time.monotonic()
        self.stages[name + '_ms'] = round((now - self.last) * 1000, 1)
        self.last = now

    def finish(self):
        now = time.monotonic()
        total = now - self.start
        if total < _CONFIRM_SLOW_TRACE_SECONDS:
            return
        # Only stage timings/mode/request id are recorded. No disk usage,
        # original filename, video pixels, plate labels or coordinates.
        try:
            _web.diagnostics.event(
                'review_confirmation_stages_slow', self.job,
                request_id=(getattr(g, 'diagnostic_id', None)
                            if has_request_context() else None),
                total_ms=round(total * 1000, 1), mode=self.mode,
                current_stage=self.current,
                unfinished_stage_ms=round((now - self.last) * 1000, 1),
                **self.stages)
        except Exception:
            # A logging failure must never change the save receipt.
            pass


def _journal_confirm(job, index, payload, doc, trace=None, rebind=False):
    label = payload.get('label')
    if label not in ('positive', 'negative') or type(label) is not str:
        raise ValueError('Choose Is a … or Not a … to store a confirmed example.')
    if trace: trace.enter('preview')
    _, _, meta, jpeg = preview(
        job, index, doc=doc, preferred_key=payload.get('preview_key'))
    if trace: trace.mark('preview')
    if meta.get('classification_allowed') is False:
        raise library.ConflictError(meta.get('classification_note') or _LEGACY_TIMING_NOTE)
    row = dict(doc['detections'][index])
    if payload.get('preview_token') not in (None, meta['preview_token']):
        abort(409, description='The finding changed. Reload its picture.')
    unverified_rebound_shape = (rebind and row['category'] == 'plate'
                                and payload.get('points') is None)
    if unverified_rebound_shape:
        # This Is/Not click proves only the displayed *new* source image.
        # Never transplant corners, polygons or machine masks associated with
        # the previously archived frame. Keep the original archived example
        # intact; use conservative detector-box coverage on the new frame.
        row.update(plate_quad=[], human_region_confirmed=False)
        box = meta['box']
        meta['points'] = [[box[0], box[1]], [box[2], box[1]],
                          [box[2], box[3]], [box[0], box[3]]]
    fields = dict(enabled=(label == 'positive'), output_choice_explicit=True,
                  human_confirmation=dict(label=label, category=row['category'],
                                          source='explicit'))
    if row['category'] == 'plate':
        fields.update(verified_label='plate' if label == 'positive' else 'not_plate',
                      plate_verification_override=True,
                      _remove_plate_verification=True)
    if payload.get('points') is not None:
        _require_exact_corners(row, doc['render_state'], meta, payload)
        meta['points'] = _shape(payload['points'], meta)
        box = meta['box']
        row['plate_quad'] = [[(x-box[0])/(box[2]-box[0]), (y-box[1])/(box[3]-box[1])]
                             for x,y in meta['points']]
        row['human_region_confirmed'] = True
        row['plate_boundary_source'] = 'human_corners'
        row['plate_quad_frame'] = (int(meta['frame']) if int(row.get('frame_index', -1)) < 0 else -1)
    # Archive evidence first. If the later small SQLite transaction fails,
    # retrying the same evidence is idempotent and no false saved ACK is sent.
    if trace: trace.enter('archive')
    entry = _archived(job, doc, row, meta, jpeg, label, payload.get('expected_revision'))
    if trace: trace.mark('archive')
    anchor = dict(confirmed_finding_id=entry['id'],
                  confirmed_finding_revision=entry['revision'])
    if row.get('source_repair_receipt'):
        # An earlier invalid-box repair explicitly reset this one frame's
        # untrusted label and protective output. A NEW human Is/Not click
        # updates that source-row exception without altering sibling shapes.
        anchor.update(human_confirmation=dict(fields['human_confirmation']),
                      enabled=(label == 'positive'),
                      output_choice_explicit=True,
                      verified_label=fields.get('verified_label', ''),
                      plate_verification_override=True)
    if unverified_rebound_shape:
        # Source-bound redaction geometry is an anchor override, never a
        # group-wide replacement of other frames' independently saved shapes.
        anchor.update(plate_quad=[], human_region_confirmed=False,
                      poly=[], poly_holes=[], mask_pad=-1)
    if payload.get('points') is not None:
        # Classification is group-wide; geometry belongs to this frame only.
        anchor.update(human_region_confirmed=True,
                      plate_quad=row['plate_quad'],
                      plate_quad_frame=row['plate_quad_frame'],
                      plate_boundary_source='human_corners',
                      poly=[], poly_holes=[], mask_pad=0,
                      _remove_plate_verification=True)
    if trace: trace.enter('journal_commit')
    review_journal.write(job['dir'], row, index, fields, anchor)
    if trace: trace.mark('journal_commit')
    row.update(fields)
    row['confirmed_finding_id'] = entry['id']
    row['confirmed_finding_revision'] = entry['revision']
    meta['preview_token'] = _token(doc, row, meta['frame'], meta.get('key'))
    if trace: trace.enter('member_count')
    count = _journal_members(doc, index)
    if trace: trace.mark('member_count')
    return dict(ok=True, finding=entry, applied=count,
                label=fields.get('verified_label',''), preview=meta)


def _journal_region(job, index, payload, doc):
    started = time.monotonic()
    _, _, meta, jpeg = preview(
        job, index, doc=doc, preferred_key=payload.get('preview_key'))
    if meta.get('geometry_outside_frame'):
        raise library.ConflictError(_OFF_FRAME_GEOMETRY_NOTE)
    row = dict(doc['detections'][index])
    if row['category'] != 'plate':
        raise ValueError('Four-corner area editing currently applies to plate findings.')
    _require_exact_corners(row, doc['render_state'], meta, payload)
    points = _shape(payload.get('points'),meta)
    box = meta['box']
    quad = [[round((x-box[0])/(box[2]-box[0]),6),
             round((y-box[1])/(box[3]-box[1]),6)] for x,y in points]
    edit_id = payload.get('edit_id') if payload.get('autosave') is True else None
    if payload.get('autosave') is True and (not isinstance(edit_id,str)
            or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,120}',edit_id)):
        raise ValueError('Autosave requires a valid edit identifier.')
    receipt = row.get('compact_edit_receipt') or {}
    if edit_id and receipt.get('id') == edit_id:
        if (receipt.get('source') != meta['source_token'] or row.get('plate_quad') != quad
                or receipt.get('token') != payload.get('preview_token')):
            raise library.ConflictError('Edit identifier belongs to different corners.')
        return dict(ok=True,applied=1,verified_samples_added=0,
                    preview=meta,verified_label=row.get('verified_label',''),
                    classification_required=not bool((row.get('human_confirmation') or {}).get('label')),
                    reconfirmation_required=bool(receipt.get('reconfirmation_required')),
                    cleared_indices=receipt.get('cleared_indices') or [])
    if payload.get('preview_token') not in (None, meta['preview_token']):
        raise library.ConflictError('This finding changed. Reload its picture before saving.')
    confirmed = row.get('human_confirmation') or {}
    row['plate_quad'] = quad
    row['human_region_confirmed'] = True
    row['plate_quad_frame'] = (int(meta['frame']) if int(row.get('frame_index', -1)) < 0 else -1)
    meta['points'] = points
    archive = None
    if (row.get('confirmed_finding_id')
            and confirmed.get('label') in ('positive','negative')
            and not confirmed.get('propagated')):
        archive = _archived(job, doc, row, meta, jpeg, confirmed['label'])
    anchor = dict(human_region_confirmed=True, plate_quad=quad,
                  plate_quad_frame=row['plate_quad_frame'],
                  plate_boundary_source='human_corners',
                  poly=[], poly_holes=[], mask_pad=0,
                  plate_verification_override=True,
                  _remove_plate_verification=True)
    if edit_id:
        anchor['compact_edit_receipt'] = dict(
            id=edit_id,source=meta['source_token'],token=payload.get('preview_token'))
    if archive:
        anchor.update(confirmed_finding_id=archive['id'],
                      confirmed_finding_revision=archive['revision'])
    if row.get('source_repair_receipt'):
        # Repaired frames have an independent source-row override.
        review_journal.write_anchor(job['dir'], index, anchor)
    else:
        # Exact-frame corners must not enter the shared group patch.
        review_journal.write(job['dir'], row, index, {}, anchor)
    meta['preview_token'] = _token(doc,row,meta['frame'],meta.get('key'))
    elapsed = time.monotonic()-started
    if elapsed >= 3:
        _web.diagnostics.event('review_corner_save_slow',job,
            total_ms=round(elapsed*1000), report_write_ms=0,
            rows=_journal_members(doc,index), mode='sqlite_journal')
    return dict(ok=True, applied=1,
                verified_samples_added=0, finding=archive, preview=meta,
                verified_label=row.get('verified_label',''),
                classification_required=not bool(confirmed.get('label')),
                reconfirmation_required=False, cleared_indices=[])


def confirm(job, index, payload):
    trace = _ConfirmTrace(job)
    try:
        trace.enter('load_preview_report')
        journal_doc = _journal_doc(job)
        trace.mark('load_preview_report')
        trace.enter('source_identity_check')
        fast_path = (journal_doc is not None and _journal_matches_archived_source(
            job, journal_doc, index, payload.get('preview_key')))
        trace.mark('source_identity_check')
        if journal_doc is not None:
            # An explicit Is/Not click may deliberately reconfirm a *different*
            # source frame/box from the same track. _archived() already proves
            # the original video/timeline identity and then derives a NEW
            # immutable archive ID for a relocated sample. It never changes
            # the old confirmed example. The small SQLite group/anchor journal
            # can safely record that new receipt without rewriting all rows of
            # a large report, which also invalidated the preview index.
            #
            # Do NOT apply this relaxation to region(): a corner drag alone
            # cannot transfer a prior human classification to a new picture.
            trace.mode = 'journal' if fast_path else 'journal_rebound'
            return _journal_confirm(job, index, payload, journal_doc, trace,
                                    rebind=not fast_path)
        trace.mode = 'full_report'
        # Approved sections and legacy reports missing verified source
        # metadata still require the original guarded full-report path.
        # Those operations remain fail-closed until their source is verified.
        trace.enter('publish_journal')
        _web._review_journal_snapshot(job)
        trace.mark('publish_journal')
        label = payload.get('label')
        if label not in ('positive', 'negative') or type(label) is not str:
            raise ValueError('Choose Is a … or Not a … to store a confirmed example.')
        # Explicit edits must operate on the complete authoritative report; the
        # read-only per-finding index is for thumbnail GETs only.
        trace.enter('load_full_report')
        before = _web._load_job_report(job)
        trace.mark('load_full_report')
        trace.enter('preview')
        _, _, meta, jpeg = preview(
            job, index, doc=before, preferred_key=payload.get('preview_key'))
        trace.mark('preview')
        if meta.get('classification_allowed') is False:
            raise library.ConflictError(meta.get('classification_note') or _LEGACY_TIMING_NOTE)
        # The authoritative JSON load already gives this request an independent
        # mutable document. Duplicating its complete 4K timeline and hundreds of
        # thousands of findings for every corner autosave costs gigabytes of RAM.
        # Approved sections alone require the old/new pair for the overlap guard.
        # Merely having section metadata does not require duplicating a huge
        # report: only actually approved/locked intervals need old/new comparison.
        section_rows = ((before.get('video_sections') or {}).get('items') or [])
        sections = ((job.get('section') or {}).get('role') == 'export'
                    or any(item.get('approved') for item in section_rows))
        doc = deepcopy(before) if sections else before
        row = doc['detections'][index]
        if payload.get('preview_token') not in (None, meta['preview_token']):
            abort(409, description='The finding changed. Reload its picture.')
        if payload.get('points') is not None:
            _require_exact_corners(row, doc['render_state'], meta, payload)
            meta['points'] = _shape(payload['points'], meta)
            box = meta['box']
            row['plate_quad'] = [[(x-box[0])/(box[2]-box[0]),(y-box[1])/(box[3]-box[1])]
                                 for x,y in meta['points']]
            row['human_region_confirmed'] = True
            row['plate_quad_frame'] = (int(meta['frame']) if int(row.get('frame_index', -1)) < 0 else -1)
            row['plate_boundary_source'] = 'human_corners'
        trace.enter('propagate_group')
        for i, member in _members(doc, index):
            _web._human_plate_override(member)
            member['enabled'] = label == 'positive'
            member['output_choice_explicit'] = True
            member['human_confirmation'] = dict(label=label, category=row['category'],
                                                source='explicit', propagated=i != index)
            if row['category'] == 'plate':
                member['verified_label'] = 'plate' if label == 'positive' else 'not_plate'
                if payload.get('points') is not None and i == index:
                    member.update(plate_quad=row['plate_quad'],
                                  plate_quad_frame=row['plate_quad_frame'],
                                  plate_boundary_source='human_corners',
                                  human_region_confirmed=True,
                                  poly=[], poly_holes=[], mask_pad=0)
        trace.mark('propagate_group')
        trace.enter('section_guard')
        _guard_section(job, before, doc)
        trace.mark('section_guard')
        # Archive first. A failed report write is retryable/idempotent; never tell
        # the UI the example is saved if its JPEG/metadata transaction failed.
        trace.enter('archive')
        entry = _archived(job, doc, row, meta, jpeg, label, payload.get('expected_revision'))
        trace.mark('archive')
        row['confirmed_finding_id'] = entry['id']
        row['confirmed_finding_revision'] = entry['revision']
        row['human_confirmation'].update(id=entry['id'], revision=entry['revision'])
        doc['render_required'] = True
        trace.enter('save_full_report')
        stop_review.atomic_report(str(Path(job['dir'])/'report.json'), doc)
        trace.mark('save_full_report')
        meta['preview_token'] = _token(doc,row,meta['frame'],meta.get('key'))
        trace.enter('member_count')
        count = len(_members(doc, index))
        trace.mark('member_count')
        return dict(ok=True, finding=entry, applied=count,
                    label=row.get('verified_label',''), preview=meta)

    finally:
        trace.finish()

def region(job, index, payload):
    journal_doc = _journal_doc(job)
    if journal_doc is not None and _journal_matches_archived_source(
            job, journal_doc, index, payload.get('preview_key')):
        return _journal_region(job, index, payload, journal_doc)
    # An old confirmed example cannot authorize changed source geometry.
    _web._review_journal_snapshot(job)
    started = time.monotonic()
    # Explicit edits must operate on the complete authoritative report; the
    # read-only per-finding index is for thumbnail GETs only.
    before = _web._load_job_report(job)
    _, _, meta, jpeg = preview(
        job, index, doc=before, preferred_key=payload.get('preview_key'))
    if meta.get('geometry_outside_frame'):
        raise library.ConflictError(_OFF_FRAME_GEOMETRY_NOTE)
    # The authoritative JSON load already gives this request an independent
    # mutable document. Duplicating its complete 4K timeline and hundreds of
    # thousands of findings for every corner autosave costs gigabytes of RAM.
    # Approved sections alone require the old/new pair for the overlap guard.
    # Merely having section metadata does not require duplicating a huge
    # report: only actually approved/locked intervals need old/new comparison.
    section_rows = ((before.get('video_sections') or {}).get('items') or [])
    sections = ((job.get('section') or {}).get('role') == 'export'
                or any(item.get('approved') for item in section_rows))
    doc = deepcopy(before) if sections else before
    row = doc['detections'][index]
    if row['category'] != 'plate':
        raise ValueError('Four-corner area editing currently applies to plate findings.')
    _require_exact_corners(row, doc['render_state'], meta, payload)
    points = _shape(payload.get('points'), meta)
    box = meta['box']
    quad = [[round((x-box[0])/(box[2]-box[0]),6),round((y-box[1])/(box[3]-box[1]),6)] for x,y in points]
    members = _members(doc,index)
    # A previously confirmed archive is keyed to its original source frame
    # and detection box. If the displayed representative has genuinely moved,
    # this is a draft AREA save, not permission to relabel a different image.
    moved_identity = _archived_identity_changed(job, doc, row, meta)
    edit_id = payload.get('edit_id') if payload.get('autosave') is True else None
    if payload.get('autosave') is True and (not isinstance(edit_id,str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,120}',edit_id)):
        raise ValueError('Autosave requires a valid edit identifier.')
    confirmed = row.get('human_confirmation') or {}
    receipt = row.get('compact_edit_receipt') or {}
    if edit_id and receipt.get('id') == edit_id:
        if (receipt.get('source') != meta['source_token'] or row.get('plate_quad') != quad
                or receipt.get('token') != payload.get('preview_token')):
            raise library.ConflictError('Edit identifier belongs to different corners.')
        return dict(ok=True,applied=len(members),verified_samples_added=0,preview=meta,
                    verified_label=row.get('verified_label',''),
                    classification_required=not bool(confirmed.get('label')),
                    reconfirmation_required=bool(receipt.get('reconfirmation_required')),
                    cleared_indices=receipt.get('cleared_indices') or [])
    if payload.get('preview_token') not in (None, meta['preview_token']):
        raise library.ConflictError('This finding changed. Reload its picture before saving.')
    # Other track frames may have a different rotation or perspective.
    _web._human_plate_override(row)
    row.update(plate_quad=quad, plate_boundary_source='human_corners',
               plate_quad_frame=(int(meta['frame']) if int(row.get('frame_index', -1)) < 0 else -1),
               human_region_confirmed=True, poly=[], poly_holes=[], mask_pad=0)
    row.pop('compact_edit_receipt',None)
    meta['points'] = points
    cleared_indices = []
    if moved_identity:
        # The old training example stays untouched and available for its
        # ORIGINAL frame/box. A new source view must be explicitly confirmed.
        # Remove stale propagated labels from this group, restore protective
        # output and retain the newly drawn four-corner geometry as a draft.
        previous_id = row.get('confirmed_finding_id')
        previous_label = confirmed.get('label')
        for member_index, member in members:
            if member_index != index:
                propagated = member.get('human_confirmation') or {}
                if (propagated.get('propagated') is not True or
                        propagated.get('label') != previous_label or
                        member.get('confirmed_finding_id') not in (None, previous_id)):
                    continue
            for key in ('confirmed_finding_id', 'confirmed_finding_revision',
                        'human_confirmation', 'plate_verification_override'):
                member.pop(key, None)
            member['verified_label'] = ''
            member['enabled'] = True
            member['output_choice_explicit'] = False
            cleared_indices.append(member_index)
    _guard_section(job,before,doc)
    entry = None
    if (not moved_identity and row.get('confirmed_finding_id') and
            confirmed.get('label') in ('positive','negative') and
            not confirmed.get('propagated')):
        entry = _archived(job,doc,row,meta,jpeg,confirmed['label'])
        row['confirmed_finding_revision'] = entry['revision']
        row['human_confirmation']['revision'] = entry['revision']
    if edit_id:
        row['compact_edit_receipt'] = dict(
            id=edit_id, source=meta['source_token'],
            token=payload.get('preview_token'),
            reconfirmation_required=moved_identity,
            cleared_indices=cleared_indices)
    doc['render_required'] = True
    report_path = Path(job['dir'])/'report.json'
    writing = time.monotonic()
    stop_review.atomic_report(str(report_path),doc)
    elapsed = time.monotonic()-started
    if elapsed >= 3:
        # Diagnostic/stat failures must never turn an already committed
        # human adjustment into an HTTP 500 (and a needless retry).
        try:
            report_mb=round(report_path.stat().st_size/1048576,1)
        except OSError:
            report_mb=None
        _web.diagnostics.event('review_corner_save_slow', job,
            total_ms=round(elapsed*1000),
            report_write_ms=round((time.monotonic()-writing)*1000),
            rows=len(doc['detections']), report_mb=report_mb)
    meta['preview_token'] = _token(doc,row,meta['frame'],meta.get('key'))
    return dict(ok=True, applied=1, verified_samples_added=0,
                finding=entry, preview=meta, verified_label=row.get('verified_label',''),
                classification_required=moved_identity or not bool(confirmed.get('label')),
                reconfirmation_required=moved_identity,
                cleared_indices=cleared_indices)


def _state(job):
    keep = ('id','name','kind','phase','created','error','learning','training_result','learning_request')
    learning_session.atomic_json(Path(job['dir'])/'training_job.json',
                                 {k:job[k] for k in keep if k in job})


def perform_training(job):
    cb = _web.WebCallbacks(job)
    try:
        result = training.run(job,root(),_web.learned_models_root(),job['learning_request'],cb.log)
        job.update(phase='model_ready',progress=1.,error=None,training_result=result)
        cb.log('Saved named model: '+result['name'])
    except InterruptedError:
        job.update(phase='cancelled',error=None)
        cb.log('Model training cancelled; previous models and confirmed examples kept.')
    except Exception as error:
        _web.diagnostics.exception('confirmed_findings_training_failed',job)
        job.update(phase='error',error=str(error))
        cb.log('Model training stopped: '+str(error))
    finally:
        _state(job)


def recover_training(jid, jdir):
    path = Path(jdir)/'training_job.json'
    if not path.is_file():
        return None
    data = json.loads(path.read_text())
    if data.get('id') != jid or data.get('kind') != 'model_training':
        return None
    job = dict(data, dir=str(jdir), video='',options={},progress=0.,size=0,
               output=None,eta=None,log=[],cancel=threading.Event(),stop=threading.Event(),stats={})
    if job.get('phase') in ('queued','learning'):
        job.update(phase='error',error='Training was interrupted. Confirmed examples and saved models are kept; start a new training run.')
    return job


def install(app, web):
    global _web
    _web = web

    @app.get('/api/findings')
    @_guard
    @web._serialize_review_read
    def findings_list():
        return jsonify(library.list_findings(root(),video_id=request.args.get('video_id') or None,
            category=request.args.get('category') or None,label=request.args.get('label') or None,
            offset=int(request.args.get('offset',0)),limit=int(request.args.get('limit',60))))

    @app.get('/api/findings/selection')
    @_guard
    @web._serialize_review_read
    def findings_selection():
        """Return counts and a revision fingerprint, never thousands of IDs."""
        selection = library.plate_selection(
            root(), video_id=request.args.get('video_id') or None,
            label=request.args.get('label') or None)
        return jsonify({key: selection[key] for key in
                        ('snapshot', 'video_id', 'category', 'label', 'total',
                         'positive', 'negative', 'video_count')})

    @app.route('/api/findings/<identity>',methods=['GET','POST','DELETE'])
    @_guard
    @web._serialize_review_edit
    def finding_detail(identity):
        if request.method == 'GET':
            return jsonify(finding=library.get_finding(root(),identity))
        value = _body()
        if request.method == 'DELETE':
            library.forget(root(),identity,expected_revision=value.get('expected_revision'))
            return jsonify(ok=True)
        return jsonify(finding=library.update_finding(root(),identity,
            label=value.get('label'),points=value.get('points'),expected_revision=value.get('expected_revision')))

    @app.get('/api/findings/<identity>/image')
    @_guard
    @web._serialize_review_read
    def finding_image(identity):
        # Read the bounded JPEG before releasing the vault gate; no file handle
        # may remain open while encryption replaces the archive's files.
        return Response(library.image_path(root(),identity).read_bytes(),mimetype='image/jpeg',
                        headers={'Cache-Control':'no-store'})

    @app.get('/api/jobs/<jid>/finding-preview/<int:index>')
    @_guard
    def finding_preview(jid,index):
        result = preview(_job(jid),index,
                         cache_only=request.args.get('cache_only')=='1',
                         exact_only=request.args.get('exact')=='1',
                         retry_decode=request.args.get('retry_decode')=='1')
        if result is None:
            return Response(status=204,headers={'Cache-Control':'no-store'})
        _,_,meta,jpeg = result
        response = Response(jpeg,mimetype='image/jpeg',headers={'Cache-Control':'no-store'})
        response.headers['X-Finding-Geometry'] = json.dumps(meta,separators=(',',':'))
        response.headers['X-Plate-Geometry'] = response.headers['X-Finding-Geometry']
        return response

    @app.get('/api/jobs/<jid>/plate-repair/<int:index>/frame')
    @_guard
    def plate_repair_image(jid, index):
        return plate_repair_frame(_job(jid), index)

    @app.post('/api/jobs/<jid>/plate-repair/<int:index>')
    @_guard
    @web._serialize_review_edit
    def plate_repair_save(jid, index):
        return jsonify(repair_plate_anchor(_job(jid, True), index, _body()))

    @app.post('/api/jobs/<jid>/confirm/<int:index>')
    @_guard
    @web._serialize_review_edit
    def finding_confirm(jid,index):
        return jsonify(confirm(_job(jid,True),index,_body()))

    @app.post('/api/jobs/<jid>/finding-region/<int:index>')
    @_guard
    @web._serialize_review_edit
    def finding_region(jid,index):
        return jsonify(region(_job(jid,True),index,_body()))

    @app.get('/api/jobs/<jid>/review-queue')
    @_guard
    @web._serialize_review_read
    def finding_queue(jid):
        job = _job(jid)
        data = previews.pending(job['dir'],offset=int(request.args.get('offset',0)),limit=60)
        data['phase'] = job['phase']
        return jsonify(data)

    @app.get('/api/jobs/<jid>/review-queue/<key>/image')
    @_guard
    @web._serialize_review_read
    def finding_queue_image(jid,key):
        result = previews.image(_job(jid)['dir'],key)
        if result is None:
            abort(404)
        return Response(result[1],mimetype='image/jpeg',headers={'Cache-Control':'no-store'})

    @app.post('/api/findings/train')
    @_guard
    @web._serialize_review_edit
    def findings_train():
        value = _body()
        if value.get('license_accepted') is not True:
            raise ValueError('Acknowledge the existing training framework terms before training.')
        manual_ids = value.get('example_ids', [])
        if not isinstance(manual_ids, list) or len(manual_ids) > 10000:
            raise ValueError('Provide a list of at most 10000 manually selected example IDs')
        if any(not isinstance(identity, str) for identity in manual_ids):
            raise ValueError('Invalid manually selected example ID')
        scope = value.get('selection')
        scope_revisions = {}
        if scope is not None:
            if not isinstance(scope, dict) or scope.get('category') != 'plate':
                raise ValueError('Bulk training selection must be scoped to plate examples')
            if scope.get('label') not in (None, 'positive', 'negative'):
                raise ValueError('Invalid bulk selection confirmation filter')
            if not isinstance(scope.get('snapshot'), str):
                raise ValueError('Bulk selection requires the original revision snapshot')
            selection = library.plate_selection(
                root(), video_id=scope.get('video_id'),
                label=scope.get('label'), expected_snapshot=scope['snapshot'],
                excluded_ids=scope.get('excluded_ids', []))
            scope_revisions = selection['revisions']
        if not manual_ids and not scope_revisions:
            raise ValueError('Select confirmed plate examples to train.')
        ids = sorted(set(manual_ids) | set(scope_revisions))
        if len(ids) > 50000:
            raise ValueError('Too many training examples in one selection')
        selected = library.training_snapshot(root(), ids=ids, category='plate')
        current = {item['id']: item['revision'] for item in selected}
        if set(current) != set(ids) or any(current.get(identity) != revision
                                         for identity, revision in scope_revisions.items()):
            raise library.ConflictError(
                'Selected confirmed examples changed or were forgotten. '
                'Refresh the selection before training.')
        # Individual page selections can pin their displayed revisions too.
        manual_revisions = value.get('expected_revisions')
        if manual_revisions is not None:
            if not isinstance(manual_revisions, dict) or set(manual_revisions) - set(manual_ids):
                raise ValueError('Invalid manually selected revision map')
            if any(type(revision) is not int or revision < 1 or
                   current.get(identity) != revision
                   for identity, revision in manual_revisions.items()):
                raise library.ConflictError(
                    'A manually selected example changed after it was displayed. Refresh it.')
        parent = training.resolve_parent(web.learned_models_root(),value.get('parent_model_id'))
        ready = learning_session.preflight(weights=parent['weights'])
        if not ready['ready']:
            return jsonify(error='; '.join(ready['problems'])),409
        name = value.get('name') or training.default_name([item['video']['name'] for item in selected])
        if not isinstance(name,str) or not name.strip() or len(name)>80 or any(ord(c)<32 or ord(c)==127 for c in name):
            raise ValueError('Use a model name between 1 and 80 characters.')
        settings = {key:value[key] for key in ('parent_model_id',) if key in value}
        settings.update(name=name.strip(),license_accepted=True,epochs=40,batch=8)
        # The worker verifies these exact revisions again before freezing pixels.
        settings['example_ids'] = ids
        settings['expected_revisions'] = current
        job = web.new_job('',{},name.strip())
        job.update(kind='model_training',phase='learning',learning_request=settings,
                   learning={'stage':'queued','message':'Named model training queued'})
        _state(job)
        web.WORK_Q.put((job['id'],'learn_examples'))
        return jsonify(id=job['id'],name=job['name'])
