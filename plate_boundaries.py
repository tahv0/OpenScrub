"""Source-frame-safe, conservative quadrilaterals for learned license-plate masks.

The detector supplies a proposal, not physical corners. This module fits four
corners to a *learned segmentation mask* only when the result is geometrically
credible and covers essentially the entire predicted mask. It never makes a
not-plate decision: failures retain the detector's protective redaction.
"""
import math

import cv2
import numpy as np



def trusted_plate_quad(row):
    """Read old reports safely: only a source-bound plate quad may narrow output.

    Older Review versions copied one row's plate_quad to every track member,
    often across different viewpoints. An old propagated Is/Not label is not
    polygon provenance. If a row has no independent mask/confirmation source,
    its safe geometry is the original detector box.
    """
    quad = row.get('plate_quad') or ()
    if row.get('category') != 'plate' or len(quad) != 4:
        return ()
    origin = row.get('plate_boundary_source') or ''
    confirmation = row.get('human_confirmation') or {}
    if (row.get('human_region_confirmed') is True
            or origin in ('human_corners', 'learned_perspective',
                          'learned_rotated_box')
            or row.get('poly')
            or (row.get('verified_label') == 'plate'
                and confirmation.get('propagated') is not True)):
        return quad
    return ()

def quad_source_frame(row, fps=None):
    """Restrict time-spanning plate quadrilaterals to their reviewed sample.

    Old report rows lack plate_quad_frame: those source-frame annotations
    cannot safely be assumed valid throughout a moving time interval.
    Ordinary exact-frame detector rows need no additional restriction.
    """
    if not trusted_plate_quad(row):
        return -1
    marker = row.get('plate_quad_frame', -1)
    if type(marker) is int and marker >= 0:
        return marker
    if int(row.get('frame_index', -1)) >= 0:
        return -1
    try:
        rate = float(fps)
        start = float(row.get('t_start', 0))
        end = float(row.get('t_end', start))
        if not math.isfinite(rate) or rate <= 0 or end - start <= 1.5 / rate:
            return -1
        seen = float(row.get('last_seen', start))
        if not math.isfinite(seen):
            return -1
    except (ValueError, TypeError):
        return -1
    return max(0, int(round(max(start, min(end, seen)) * rate)))


def _ordered_quad(points):
    points = np.asarray(points, dtype=np.float64).reshape(4, 2)
    center = points.mean(axis=0)
    points = points[np.argsort(np.arctan2(
        points[:, 1] - center[1], points[:, 0] - center[0]))]
    return np.roll(points, -int(np.argmin(points.sum(axis=1))), axis=0)


def _fill(shape, corners):
    coverage = np.zeros(shape, np.uint8)
    cv2.fillConvexPoly(coverage, np.rint(corners).astype(np.int32), 1)
    return coverage


def _fit(mask):
    """Return (crop-local four corners, filled polygon, method), or no fit."""
    if mask is None:
        return None, None, None
    mask = np.asarray(mask)
    if mask.ndim != 2 or min(mask.shape) < 4 or not np.issubdtype(mask.dtype, np.number):
        return None, None, None
    if not np.isfinite(mask).all():
        return None, None, None
    binary = (mask > 0).astype(np.uint8)
    if cv2.countNonZero(binary) < 8:
        return None, None, None
    # One source pixel around the mask protects its high-contrast edges.
    padded = cv2.dilate(binary, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(padded, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None, None, None
    points = np.concatenate(contours)
    hull = cv2.convexHull(points)
    perimeter = cv2.arcLength(hull, True)
    candidates = []
    # A trapezoidal mask often has small stair-step edges. Try progressively
    # simplified hulls before discarding perspective for a rotated rectangle.
    for ratio in (.004, .008, .012, .018, .025, .035, .05, .07):
        candidate = cv2.approxPolyDP(hull, ratio * perimeter, True).reshape(-1, 2)
        if len(candidate) == 4:
            candidate = _ordered_quad(candidate)
            candidates.append((candidate, 'perspective'))
    if not candidates:
        candidates = [(_ordered_quad(cv2.boxPoints(cv2.minAreaRect(points))),
                       'rotated_box')]
    total = cv2.countNonZero(padded)
    for candidate, method in candidates:
        # Inward polygon simplification can clip the true predicted mask.
        # Expand slightly and require >=99.5% pixel coverage; never silently
        # trade away a dark corner or a single line of lettering.
        center = candidate.mean(axis=0)
        vectors = candidate - center
        lengths = np.maximum(np.linalg.norm(vectors, axis=1), 1.)
        expanded = candidate + vectors / lengths[:, None] * 2.0
        cover = _fill(binary.shape, expanded)
        missed = cv2.countNonZero(cv2.bitwise_and(padded, 1 - cover))
        if missed <= max(1, math.floor(total * .005)):
            return expanded, cover, method
    return None, None, None


def conservative_quad(mask):
    """Legacy two-value API used by model calibration and mask refinement."""
    corners, covered, _ = _fit(mask)
    return corners, covered


def safe_plate_boundary(mask, proposal, crop_origin, frame_shape):
    """Accept a learned quad only when it is a credible, safe plate outline.

    All source-space geometry is tied to the frame actually used for model
    inference. No track-wide reuse or extrapolation of a narrow quad is safe.
    Returns (crop-local corners, method, reason). A rejected candidate has
    None corners, and the caller must keep the full detector proposal.
    """
    corners, covered, method = _fit(mask)
    if corners is None:
        return None, None, 'mask has no enclosing four-corner outline'
    box = np.asarray(proposal, dtype=np.float64)
    if box.shape != (4,) or not np.isfinite(box).all():
        return None, None, 'invalid original detector proposal'
    bw, bh = box[2] - box[0], box[3] - box[1]
    if bw <= 0 or bh <= 0:
        return None, None, 'invalid detector box'
    xy = corners + np.asarray(crop_origin, dtype=np.float64)
    if not np.isfinite(xy).all():
        return None, None, 'non-finite learned corners'
    fh, fw = frame_shape[:2]
    # Outside the source frame cannot be treated as covered.
    if (xy[:, 0].min() < -1 or xy[:, 1].min() < -1 or
            xy[:, 0].max() > fw + 1 or xy[:, 1].max() > fh + 1):
        return None, None, 'learned corners leave the source frame'
    width = np.ptp(xy[:, 0])
    height = np.ptp(xy[:, 1])
    area = abs(cv2.contourArea(xy.astype(np.float32)))
    box_area = bw * bh
    # Reject tiny disconnected text fragments, unrelated predictions and
    # masks that would make a large real plate almost entirely visible.
    if (width < .40 * bw or height < .35 * bh or
            area < .22 * box_area or area > 2.5 * box_area):
        return None, None, 'learned mask would conceal too little or too much'
    center = xy.mean(axis=0)
    if not (box[0] <= center[0] <= box[2] and box[1] <= center[1] <= box[3]):
        return None, None, 'learned outline is outside the detector proposal'
    if (min(np.linalg.norm(xy[(k + 1) % 4] - xy[k]) for k in range(4)) < 3 or
            not cv2.isContourConvex(xy.astype(np.float32).reshape(4, 1, 2))):
        return None, None, 'degenerate learned corners'
    # Covered already includes every positive mask pixel (within 0.5%).
    # That proves mask coverage, not correctness of unseen plate characters.
    return corners, method, ''
