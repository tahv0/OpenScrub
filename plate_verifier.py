"""Proposal-specific secondary plate checks, separate from mask tightening.

Low plate confidence is an empirical rejection rule, not a negative-class
probability. Automatic filtering requires its own held-out assessment.
"""
from copy import deepcopy
import json
import math
from pathlib import Path

import cv2
import numpy as np

import video_learning as vl


_FIELDS = {'schema', 'status', 'threshold', 'held_out_positive', 'held_out_negative',
           'retained_positive', 'rejected_positive', 'rejected_negative', 'reason'}
_COUNTS = ('held_out_positive', 'held_out_negative', 'retained_positive',
           'rejected_positive', 'rejected_negative')


def validate_assessment(value):
    """Validate both evaluated statuses; filtering separately requires validated."""
    if not isinstance(value, dict) or set(value) != _FIELDS:
        raise ValueError('Unsupported verifier assessment fields')
    if type(value['schema']) is not int or value['schema'] != 1:
        raise ValueError('Unsupported verifier assessment schema')
    if value['status'] not in ('validated', 'review_only'):
        raise ValueError('Invalid verifier assessment status')
    threshold = value['threshold']
    if (isinstance(threshold, bool) or not isinstance(threshold, (int, float))
            or not math.isfinite(threshold) or not 0 < threshold <= 1):
        raise ValueError('Verifier threshold must be in (0, 1]')
    if any(type(value[key]) is not int or not 0 <= value[key] <= 2**53 for key in _COUNTS):
        raise ValueError('Invalid verifier assessment counts')
    if (value['retained_positive'] + value['rejected_positive'] != value['held_out_positive']
            or value['rejected_negative'] > value['held_out_negative']):
        raise ValueError('Inconsistent verifier assessment counts')
    if not isinstance(value['reason'], str) or not value['reason'] or len(value['reason']) > 1000:
        raise ValueError('Invalid verifier assessment reason')
    if value['status'] == 'validated' and not (
            value['held_out_positive'] >= 4 and value['held_out_negative'] >= 2
            and value['rejected_positive'] == 0 and value['rejected_negative'] >= 1):
        raise ValueError('Filtering requires four positives, two negatives, no positive rejection and useful negative rejection')
    return dict(value)


def _cancel(cancelled):
    if cancelled and cancelled():
        raise InterruptedError('Plate verification cancelled; previous review retained')


def _score(model, image, box):
    _, score = model.predict_proposal(image, box)
    if (isinstance(score, bool) or not isinstance(score, (int, float, np.floating))
            or not math.isfinite(score) or not 0 <= score <= 1):
        raise ValueError('Verifier returned an invalid plate score')
    return float(score)


def assess(model, dataset, cancelled=None, progress=None):
    """Count every held-out positive, including empty/low-score predictions."""
    root = Path(dataset).resolve(strict=True)
    records = []
    for line in (root / 'manifest.jsonl').read_text(encoding='utf-8').splitlines():
        _cancel(cancelled)
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get('split') == 'val' and record.get('label') in ('positive', 'negative'):
            records.append(record)
    scores = {'positive': [], 'negative': []}
    if progress:
        progress(0, len(records))
    for index, record in enumerate(records):
        _cancel(cancelled)
        relative = Path(record['image'])
        image_path = root / relative
        if relative.is_absolute() or '..' in relative.parts or image_path.is_symlink():
            raise ValueError('Unsafe held-out verifier crop path')
        try:
            image_path.resolve(strict=True).relative_to(root)
        except (OSError, ValueError) as error:
            raise ValueError('Missing or unsafe held-out verifier crop') from error
        image = cv2.imread(str(image_path))
        if image is None:
            raise ValueError('Unreadable held-out verifier crop')
        box = np.asarray(record['baseline_box'], dtype=np.float64)
        if (box.shape != (4,) or not np.isfinite(box).all() or np.any(box < 0) or np.any(box > 1)
                or box[2] <= box[0] or box[3] <= box[1]):
            raise ValueError('Invalid held-out verifier proposal box')
        h, w = image.shape[:2]
        scores[record['label']].append(_score(model, image, box * [w, h, w, h]))
        if progress:
            progress(index + 1, len(records))
    _cancel(cancelled)
    positive, negative = scores['positive'], scores['negative']
    threshold = min(positive, default=0.)
    separated = threshold > 0 and any(score < threshold for score in negative)
    enough = len(positive) >= 4 and len(negative) >= 2
    validated = separated and enough
    if validated:
        # Reject the same observed negatives while leaving room below the
        # weakest known positive rather than using its exact floating score.
        lower = max(score for score in negative if score < threshold)
        threshold = lower + (threshold - lower) / 2
    else:
        threshold = .25
    rejected = sum(score < threshold for score in positive)
    reason = ('Observed no rejected held-out plates and useful background rejection; unseen footage still needs review.'
              if validated else 'Review suggestions only: ' + (
                  'at least four held-out plates and two held-out negatives are required.' if not enough else
                  'no cutoff rejects known negatives while retaining every held-out plate.'))
    return validate_assessment(dict(schema=1, status='validated' if validated else 'review_only',
        threshold=threshold, held_out_positive=len(positive), held_out_negative=len(negative),
        retained_positive=len(positive) - rejected, rejected_positive=rejected,
        rejected_negative=sum(score < threshold for score in negative), reason=reason))


def _human_preserved(row):
    if row.get('verified_label') or row.get('plate_verification_override'):
        return True
    return row.get('enabled') is False and not vl.machine_suppressed(row)


def review_report(video, doc, model, assessment, mode='review', cancelled=None,
                  progress=None, frame_range=None):
    """Check current proposals without changing their geometry or human labels."""
    gate = validate_assessment(assessment)
    if mode not in ('review', 'filter'):
        raise ValueError('Verifier mode must be review or filter')
    if mode == 'filter' and gate['status'] != 'validated':
        raise ValueError('Automatic filtering requires a validated verifier assessment')
    _cancel(cancelled)
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        cap.release()
        raise ValueError('Cannot open video for the plate verification pass')
    result = deepcopy(doc)
    rs = result['render_state']
    stats = dict(model_calls=0, checked=0, suggested=0, suppressed=0, kept=0,
                 human_preserved=0, decoded_frames=0)
    start, end = 0, len(rs['cum'])
    targets = {}
    try:
        fps = float(cap.get(cv2.CAP_PROP_FPS))
        if not math.isclose(fps, float(rs['fps']), rel_tol=1e-4, abs_tol=.001):
            raise ValueError('Verification video frame rate differs from the scan timeline')
        if frame_range is not None:
            from openscrub import _section_frame_bounds, _seek_cap, sha256_file
            start, end = _section_frame_bounds(frame_range, cap, float(rs['fps']), rs['cum'])
            identity = doc.get('source_identity') or {}
            expected = identity.get('input_sha256') or doc.get('provenance', {}).get('input_sha256')
            if expected and sha256_file(video) != expected:
                raise ValueError('Verification source changed; previous result retained')
            if identity.get('total_frames') not in (None, int(cap.get(cv2.CAP_PROP_FRAME_COUNT))):
                raise ValueError('Verification source timeline changed; previous result retained')
            if start and not _seek_cap(cap, start, fps):
                raise ValueError('Verification decoder cannot reach the section start frame')
        for row in result['detections']:
            if row.get('category') != 'plate' or row.get('zone_dropped'):
                continue
            frame = vl._frame(row, rs)
            if frame_range is None and not 0 <= frame < end:
                raise ValueError('Verifier proposal is outside the scanned timeline')
            if not start <= frame < end:
                continue
            if _human_preserved(row):
                stats['human_preserved'] += 1
                continue
            if vl.machine_suppressed(row):
                previous = row['plate_verification'].get('previous_enabled', True)
                row['enabled'] = previous if type(previous) is bool else True
            targets.setdefault(frame, []).append(row)
        index = start
        while index < end:
            _cancel(cancelled)
            ok, image = cap.read()
            if not ok:
                break
            stats['decoded_frames'] += 1
            for row in targets.get(index, []):
                _cancel(cancelled)
                box = vl._screen_box(row, rs, index)
                if not np.isfinite(box).all() or box[2] <= box[0] or box[3] <= box[1]:
                    raise ValueError('Invalid verifier proposal crop')
                x1, y1, x2, y2 = vl.crop_bounds(box, image.shape)
                if x2 <= x1 or y2 <= y1:
                    raise ValueError('Invalid verifier proposal crop')
                score = _score(model, image[y1:y2, x1:x2],
                               [box[0] - x1, box[1] - y1, box[2] - x1, box[3] - y1])
                stats['model_calls'] += 1
                stats['checked'] += 1
                low = score < gate['threshold']
                previous = row.get('enabled', True) is not False
                applied = low and mode == 'filter'
                decision = 'suppress' if applied else 'suggest_not_plate' if low else 'retain'
                row['plate_verification'] = dict(decision=decision, score=score,
                    threshold=gate['threshold'], mode=mode, applied=applied, previous_enabled=previous)
                if applied:
                    row['enabled'] = False
                stats['suggested'] += int(low)
                stats['suppressed'] += int(applied)
                stats['kept'] += int(not low)
            index += 1
            if progress and (index - start) % 30 == 0:
                progress(index - start, end - start)
        if index < end:
            raise ValueError('Verification decoder did not cover the scan timeline')
        _cancel(cancelled)
        if progress:
            progress(index - start, end - start)
        return result, stats
    finally:
        cap.release()
