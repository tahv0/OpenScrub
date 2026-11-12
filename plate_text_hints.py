"""Bounded, local OCR evidence for user-supplied license plate numbers.

This module proposes UNREVIEWED examples, never labels training data or claims a
number is redacted. Hints currently use ASCII A-Z/0-9 (3..16 characters); spaces,
hyphens and periods are presentation separators. No fuzzy O/0 substitutions are
made. The default reader is local Tesseract with a per-call timeout. Discovery
uses at most six candidates, eight right-angle/mirror views per candidate, 64
tokens per view, and returns at most twelve proposals. No video is opened here.

``regions`` accepts pixel boxes, pixel quads, or dictionaries containing
source_box/box/cbox and optional plate_quad/quad. Quad coordinates are absolute
source pixels unless plate_quad_normalized=True is explicitly provided, in
which case they are relative to the box. Output coordinates are always source
pixels, with boxes in x1,y1,x2,y2 order. A supplied reader is callable (or has
``read``) and returns (text, pixel_box, confidence) triples for its input image.
"""
from __future__ import annotations

import math
import os
import re
import shutil

import cv2
import numpy as np

MAX_CANDIDATES = 6
MAX_PROPOSALS = 12
MAX_TOKENS = 64
MAX_SIDE = 1280


def normalize_hints(value):
    """Validate a string (comma/semicolon/newline separated) or up to ten strings.

    Raises ValueError for empty/invalid input or payloads above 1024 characters.
    ASCII is explicit: unsupported country alphabets are rejected, not silently
    transliterated into a different registration number.
    """
    if isinstance(value, str):
        if len(value) > 1024:
            raise ValueError("Known plate hints must be at most 1024 characters.")
        values = [part for part in re.split(r"[,;\r\n]+", value) if part.strip()]
    elif isinstance(value, (list, tuple)):
        values = list(value)
    else:
        raise ValueError("Provide one or more known plate numbers as text or a list.")
    if not values or len(values) > 10:
        raise ValueError("Provide between one and ten known plate numbers.")
    result = []
    payload_size = 0
    for item in values:
        if not isinstance(item, str):
            raise ValueError("Each known plate number must be text.")
        payload_size += len(item)
        if payload_size > 1024 or len(item) > 128:
            raise ValueError("Known plate hints exceed the allowed input size.")
        if not re.fullmatch(r"[A-Za-z0-9 .\t-]+", item):
            raise ValueError("Known plate numbers support ASCII A-Z, 0-9, spaces, periods and hyphens.")
        normalized = re.sub(r"[ .\t-]", "", item).upper()
        if not 3 <= len(normalized) <= 16:
            raise ValueError("Each known plate number needs 3 to 16 letters or digits.")
        if normalized not in result:
            result.append(normalized)
    return result


def _ocr_text(value):
    return re.sub(r"[^A-Z0-9]", "", str(value)[:512].upper())


def match_text(observed, hints):
    """Return strongest literal evidence, with an ordinal score, not confidence.

    An exact match contains the whole target. Partial evidence requires a common
    contiguous run of at least three characters AND at least half the target.
    OCR confidence is deliberately separate from this deterministic evidence.
    """
    targets = normalize_hints(hints)
    text = _ocr_text(observed)
    best = None
    for target in targets:
        matched = ""
        for length in range(len(target), max(3, math.ceil(len(target) / 2))-1, -1):
            matched = next((target[i:i+length] for i in range(len(target)-length+1)
                            if target[i:i+length] in text), "")
            if matched:
                break
        if not matched:
            continue
        exact = len(matched) == len(target)
        evidence = {"observed_text": str(observed)[:512], "matched_target": target,
                    "matched_text": matched, "match_kind": "exact" if exact else "partial",
                    "match_strength": 1.0 if exact else round(.5 * len(matched)/len(target), 4),
                    "target_coverage": len(matched)/len(target)}
        if best is None or evidence["match_strength"] > best["match_strength"]:
            best = evidence
    return best


def _box(points, width, height):
    pts = np.asarray(points, dtype=float).reshape(-1, 2)
    return [max(0, int(math.floor(pts[:, 0].min()))),
            max(0, int(math.floor(pts[:, 1].min()))),
            min(width, int(math.ceil(pts[:, 0].max()))),
            min(height, int(math.ceil(pts[:, 1].max())))]


def _quad(box):
    x1, y1, x2, y2 = box
    return np.float32([[x1, y1], [x2, y1], [x2, y2], [x1, y2]])


def _ordered(points):
    pts = np.asarray(points, dtype=np.float32).reshape(4, 2)
    # The two topmost points followed by the two bottommost avoids the duplicate
    # corners produced by argmin(sum) for a diamond or strongly tilted rectangle.
    order = pts[np.argsort(pts[:, 1], kind="stable")]
    top = order[:2][np.argsort(order[:2, 0])]
    bottom = order[2:][np.argsort(order[2:, 0])]
    return np.float32([top[0], top[1], bottom[1], bottom[0]])


def _provided(region, width, height):
    try:
        if isinstance(region, dict):
            box = region.get("source_box", region.get("box", region.get("cbox")))
            points = region.get("plate_quad", region.get("quad"))
            if points is not None and region.get("plate_quad_normalized"):
                x1, y1, x2, y2 = map(float, box)
                points = np.asarray(points, float) * [x2-x1, y2-y1] + [x1, y1]
            if points is None:
                points = _quad(box)
        else:
            array = np.asarray(region)
            points = _quad(array) if array.shape == (4,) else array
        points = _ordered(points)
        if not np.isfinite(points).all():
            return None
        # Boxes use half-open pixel bounds: an x2==width region must still
        # protect the final source column. Do not shrink it to width-1.
        points[:, 0] = points[:, 0].clip(0, width)
        points[:, 1] = points[:, 1].clip(0, height)
        if abs(cv2.contourArea(points)) < 24 or not cv2.isContourConvex(points):
            return None
        return {"quad": points, "kind": "provided_region"}
    except (TypeError, ValueError, IndexError):
        return None


def _iou(a, b):
    intersection = max(0, min(a[2], b[2])-max(a[0], b[0])) * max(0, min(a[3], b[3])-max(a[1], b[1]))
    return intersection / max(1, (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1])-intersection)


def _retain_proposal(proposals, proposal, width, height):
    """Keep strongest overlapping evidence and union all proposed protection."""
    for index, previous in enumerate(proposals):
        if previous["matched_target"] != proposal["matched_target"]:
            continue
        a, b = previous["source_box"], proposal["source_box"]
        intersection = max(0, min(a[2], b[2])-max(a[0], b[0])) * max(0, min(a[3], b[3])-max(a[1], b[1]))
        smaller = min((a[2]-a[0])*(a[3]-a[1]), (b[2]-b[0])*(b[3]-b[1]))
        # Contained OCR number evidence can upgrade a larger plate candidate.
        if intersection / max(1, smaller) < .7:
            continue
        strongest = proposal if proposal["match_strength"] > previous["match_strength"] else previous
        strongest = dict(strongest)
        all_boxes = [row[key] for row in (previous, proposal)
                     for key in ("source_box", "protection_box")]
        union = _box([[min(box[0] for box in all_boxes), min(box[1] for box in all_boxes)],
                      [max(box[2] for box in all_boxes), max(box[3] for box in all_boxes)]], width, height)
        strongest.update(source_box=union, protection_box=list(union),
                         plate_quad=_quad(union).astype(float).tolist(),
                         protection_quad=_quad(union).astype(float).tolist())
        strongest["provenance"] = dict(strongest["provenance"])
        strongest["provenance"]["boundary_requires_review"] = any(
            row["provenance"]["boundary_requires_review"] for row in (previous, proposal))
        proposals[index] = strongest
        return
    if len(proposals) < MAX_PROPOSALS:
        proposals.append(proposal)
    else:
        weakest = min(range(len(proposals)), key=lambda index: proposals[index]["match_strength"])
        if proposal["match_strength"] > proposals[weakest]["match_strength"]:
            proposals[weakest] = proposal


def _candidates(frame, regions):
    height, width = frame.shape[:2]
    candidates = []
    def add(candidate):
        if candidate is None or len(candidates) >= MAX_CANDIDATES-1:
            return
        bounds = _box(candidate["quad"], width, height)
        if any(_iou(bounds, _box(c["quad"], width, height)) > .65 for c in candidates):
            return
        candidate["box"] = bounds
        candidates.append(candidate)
    if regions is not None:
        # Bounded even for malformed or adversarial input collections.
        for index, region in enumerate(regions):
            # Reserve two slots for missed-plate discovery, plus full-frame OCR.
            if index >= 64 or len(candidates) >= MAX_CANDIDATES-3:
                break
            add(_provided(region, width, height))
    scale = min(1., MAX_SIDE/max(width, height))
    small = cv2.resize(frame, None, fx=scale, fy=scale) if scale < 1 else frame
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 60, 180)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    found = []
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:160]:
        area = abs(cv2.contourArea(contour))
        if area < 100 or area > gray.size * .6:
            continue
        approx = cv2.approxPolyDP(contour, .035*cv2.arcLength(contour, True), True)
        if len(approx) != 4 or not cv2.isContourConvex(approx):
            continue
        rect = cv2.minAreaRect(contour)
        rw, rh = sorted(rect[1], reverse=True)
        if rh < 8 or rw < 24 or not 1.4 <= rw/rh <= 8.5:
            continue
        found.append({"quad": _ordered(approx.reshape(4, 2)/scale), "kind": "plate_contour"})
    for candidate in found:
        add(candidate)
    # A morphology pass can rescue text-only number lines lacking a plate border.
    if len(candidates) < MAX_CANDIDATES-1:
        grouped = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((3, 17), np.uint8))
        contours, _ = cv2.findContours(grouped, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:40]:
            x, y, w, h = cv2.boundingRect(contour)
            if w >= 30 and h >= 8 and 1.4 <= w/h <= 12 and w*h <= gray.size*.5:
                pad = max(3, h*.25)
                q = _quad([max(0, x-pad)/scale, max(0, y-pad)/scale,
                           min(gray.shape[1]-1, x+w+pad)/scale,
                           min(gray.shape[0]-1, y+h+pad)/scale])
                add({"quad": q, "kind": "text_contour"})
    candidates.append({"quad": _quad([0, 0, width-1, height-1]),
                       "box": [0, 0, width, height], "kind": "full_frame_text"})
    return candidates


def _rectified(frame, quad, full_frame=False):
    tl, tr, br, bl = quad
    width = max(np.linalg.norm(tr-tl), np.linalg.norm(br-bl))
    height = max(np.linalg.norm(bl-tl), np.linalg.norm(br-tr))
    if full_frame:
        scale = min(1., (MAX_SIDE-1)/max(1., width, height))
    else:
        scale = min(3., 100/max(1., height), MAX_SIDE/max(1., width, height))
    out_w, out_h = max(2, round(width*scale)+1), max(2, round(height*scale)+1)
    target = _quad([0, 0, out_w-1, out_h-1])
    transform = cv2.getPerspectiveTransform(np.float32(quad), target)
    return cv2.warpPerspective(frame, transform, (out_w, out_h)), transform


def _view(image, rotation, mirrored):
    height, width = image.shape[:2]
    if rotation == 0:
        result, matrix = image, np.eye(3)
    elif rotation == 90:
        result = cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
        matrix = np.array([[0, -1, height-1], [1, 0, 0], [0, 0, 1]], float)
    elif rotation == 180:
        result = cv2.rotate(image, cv2.ROTATE_180)
        matrix = np.array([[-1, 0, width-1], [0, -1, height-1], [0, 0, 1]], float)
    else:
        result = cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
        matrix = np.array([[0, 1, 0], [-1, 0, width-1], [0, 0, 1]], float)
    if mirrored:
        result = cv2.flip(result, 1)
        matrix = np.array([[-1, 0, result.shape[1]-1], [0, 1, 0], [0, 0, 1]], float) @ matrix
    return result, matrix


class _LocalTesseract:
    def __init__(self):
        try:
            import pytesseract
        except ImportError as exc:
            raise RuntimeError("Known plate text search needs pytesseract and local Tesseract; run openscrub-setup.") from exc
        self.pt = pytesseract
        if not shutil.which(pytesseract.pytesseract.tesseract_cmd):
            candidates = [r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                          r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
                          os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe")]
            executable = next((path for path in candidates if os.path.isfile(path)), None)
            if not executable:
                raise RuntimeError("Known plate text search needs local Tesseract. Run openscrub-setup or install Tesseract and add it to PATH.")
            pytesseract.pytesseract.tesseract_cmd = executable

    def __call__(self, image):
        try:
            data = self.pt.image_to_data(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY),
                config="--psm 11 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
                timeout=1.5, output_type=self.pt.Output.DICT)
        except self.pt.TesseractNotFoundError as exc:
            raise RuntimeError("Known plate text search needs local Tesseract; run openscrub-setup or add Tesseract to PATH.") from exc
        except RuntimeError as exc:
            if "timeout" in str(exc).lower():
                return []
            raise
        return [(data["text"][i], (data["left"][i], data["top"][i],
                 data["left"][i]+data["width"][i], data["top"][i]+data["height"][i]),
                 float(data["conf"][i])/100) for i in range(len(data["text"]))
                if data["text"][i].strip() and float(data["conf"][i]) >= 0][:MAX_TOKENS]


def _token_groups(raw, image):
    height, width = image.shape[:2]
    tokens = []
    for index, row in enumerate(raw):
        if index >= MAX_TOKENS:
            break
        try:
            text, bounds, confidence = row
            bounds = np.asarray(bounds, float)
            if bounds.shape != (4,) or not np.isfinite(bounds).all() or not _ocr_text(text):
                continue
            x1, y1, x2, y2 = bounds
            if x1 < 0 or y1 < 0 or x2 > width or y2 > height or x2 <= x1 or y2 <= y1:
                continue
            confidence = float(confidence)
            if not math.isfinite(confidence):
                continue
            tokens.append((str(text)[:128], bounds, confidence))
        except (TypeError, ValueError):
            continue
    # Start from every token, extending only along its own nearby text line.
    for token in tokens:
        yield token
        text, box, confidence = token
        for following in sorted(tokens, key=lambda row: row[1][0]):
            if following is token:
                continue
            nxt, rect, conf = following
            overlap = min(box[3], rect[3])-max(box[1], rect[1])
            if rect[0] < box[2] or rect[0]-box[2] > 2*max(box[3]-box[1], rect[3]-rect[1]):
                continue
            if overlap < .5*min(box[3]-box[1], rect[3]-rect[1]):
                continue
            text += " " + nxt
            box = np.array([min(box[0], rect[0]), min(box[1], rect[1]),
                            max(box[2], rect[2]), max(box[3], rect[3])])
            confidence = min(confidence, conf)
            yield text, box, confidence
            if len(text) > 128:
                break


def search_frame(frame_bgr, hints, regions=None, reader=None, cancelled=None):
    """Find bounded UNREVIEWED OCR proposals without changing app/training state.

    Existing plate-like regions may use meaningful partial matches. Text-only
    discovery needs a full target match. Protection covers the complete candidate
    (or complete OCR number with margin for text-only full-frame evidence), never
    merely the matched substring. Callers must have a human review these regions.
    Cancellation is checked between views; an active Tesseract call has a 1.5s
    timeout. Missing Tesseract raises an actionable RuntimeError, never sys.exit.
    """
    targets = normalize_hints(hints)
    stop = cancelled if callable(cancelled) else lambda: False
    if stop() or not isinstance(frame_bgr, np.ndarray) or frame_bgr.ndim != 3:
        return []
    if frame_bgr.shape[2] != 3 or min(frame_bgr.shape[:2]) < 2:
        return []
    height, width = frame_bgr.shape[:2]
    proposals = []
    for candidate in _candidates(frame_bgr, regions):
        if stop():
            break
        image, source_to_rect = _rectified(frame_bgr, candidate["quad"],
                                         full_frame=candidate["kind"] == "full_frame_text")
        strongest = None
        full_frame_hits = []
        full_frame = candidate["kind"] == "full_frame_text"
        for attempt in range(8):
            if stop():
                break
            rotation, mirrored = (attempt % 4)*90, attempt >= 4
            view, rect_to_view = _view(image, rotation, mirrored)
            if reader is None:
                reader = _LocalTesseract()
            read = reader if callable(reader) else reader.read
            inverse = np.linalg.inv(rect_to_view @ source_to_rect)
            for text, text_box, confidence in _token_groups(read(view), view):
                evidence = match_text(text, targets)
                if evidence is None or (candidate["kind"] in ("full_frame_text", "text_contour")
                                        and evidence["match_kind"] != "exact"):
                    continue
                if not full_frame and strongest is not None and evidence["match_strength"] <= strongest["match_strength"]:
                    continue
                points = cv2.perspectiveTransform(_quad(text_box)[None], inverse)[0]
                points[:, 0] = points[:, 0].clip(0, width)
                points[:, 1] = points[:, 1].clip(0, height)
                bounds = _box(points, width, height)
                protection = candidate["box"]
                protection_quad = candidate["quad"]
                if candidate["kind"] == "full_frame_text":
                    # No plate boundary is known: preserve the whole OCR number,
                    # expanded on every side, and flag the boundary uncertainty.
                    margin_x = max(4, (bounds[2]-bounds[0])*.12)
                    margin_y = max(4, (bounds[3]-bounds[1])*.4)
                    protection = _box([[bounds[0]-margin_x, bounds[1]-margin_y],
                                       [bounds[2]+margin_x, bounds[3]+margin_y]], width, height)
                    protection_quad = _quad(protection)
                proposal = dict(evidence, source_box=list(protection),
                    plate_quad=np.asarray(protection_quad, float).tolist(),
                    text_box=bounds, text_quad=points.astype(float).tolist(),
                    protection_box=list(protection),
                    protection_quad=np.asarray(protection_quad, float).tolist(),
                    ocr_confidence=confidence, review_status="unreviewed",
                    orientation={"rotation": rotation, "mirrored": mirrored},
                    provenance={"method": "known_plate_text", "candidate": candidate["kind"],
                                "reader": "local_tesseract" if isinstance(reader, _LocalTesseract) else "injected_local_reader",
                                "geometry": "perspective_rectified", "score_type": "literal_match_strength",
                                "boundary_requires_review": evidence["match_kind"] == "partial" or candidate["kind"] in ("full_frame_text", "text_contour")})
                if full_frame:
                    _retain_proposal(full_frame_hits, proposal, width, height)
                else:
                    strongest = proposal
            if full_frame and (len(full_frame_hits) >= MAX_PROPOSALS or
                               set(targets).issubset({row["matched_target"] for row in full_frame_hits})):
                break
            if not full_frame and strongest is not None and strongest["match_kind"] == "exact":
                break
        for proposal in full_frame_hits if full_frame else ([strongest] if strongest is not None else []):
            _retain_proposal(proposals, proposal, width, height)
        if len(proposals) >= MAX_PROPOSALS:
            break
    return sorted(proposals, key=lambda row: row["match_strength"], reverse=True)
