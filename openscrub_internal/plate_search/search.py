"""Bounded local OCR discovery; results are suggestions, never redactions.

Text coordinates describe the whole OCR token, not a physical plate outline.
Each native-resolution tile is read independently, without joining text across
observations. No query is sent to the OCR reader or included in diagnostics.
"""
from dataclasses import dataclass, field
import heapq
from itertools import islice
import math
import os
import shutil

import cv2
import numpy as np

from .matching import match_text, normalize_queries

TILE_WIDTH, TILE_HEIGHT, OVERLAP = 1280, 960, 160
MAX_TILES, MAX_REGIONS, MAX_TOKENS, MAX_HITS = 64, 8, 64, 128
MAX_DIMENSION = 8192
MAX_CONTOURS = 3
OCR_TIMEOUT_SECONDS = 3.0


class SearchError(RuntimeError):
    """An OCR call failed; no inference can be made about missing results."""


@dataclass(frozen=True)
class Observation:
    text: str = field(repr=False)
    box: tuple
    confidence: float
    source: str


@dataclass(frozen=True)
class SearchHit:
    observation: Observation = field(repr=False)
    matches: tuple = field(repr=False)
    suggested_box: tuple
    boundary: str


@dataclass(frozen=True)
class FrameSearch:
    hits: tuple = field(repr=False)
    complete: bool
    tiles_completed: int
    tiles_total: int
    truncated: bool


class LocalTesseract:
    """Use the installed Tesseract executable with a per-tile time limit."""

    def __init__(self, cancelled=None):
        try:
            import pytesseract
        except ImportError:
            raise SearchError('Plate search needs pytesseract and local Tesseract') from None
        self.pt = pytesseract
        self.cancelled = cancelled if callable(cancelled) else lambda: False
        executable = pytesseract.pytesseract.tesseract_cmd
        if not shutil.which(executable) and os.name == 'nt':
            for candidate in (r'C:\Program Files\Tesseract-OCR\tesseract.exe',
                              r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
                              os.path.expandvars(r'%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe')):
                if os.path.isfile(candidate):
                    pytesseract.pytesseract.tesseract_cmd = candidate
                    break

    def _read(self, image, psm):
        data = self.pt.image_to_data(
            cv2.cvtColor(image, cv2.COLOR_BGR2GRAY),
            config='--psm %d -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789' % psm,
            timeout=OCR_TIMEOUT_SECONDS, output_type=self.pt.Output.DICT)
        for i in range(len(data['text'])):
            try:
                confidence = float(data['conf'][i]) / 100.0
                x, y = int(data['left'][i]), int(data['top'][i])
                width, height = int(data['width'][i]), int(data['height'][i])
                if data['text'][i].strip() and confidence >= 0:
                    yield data['text'][i], (x, y, x + width, y + height), confidence
            except (ValueError, TypeError, IndexError, OverflowError):
                continue

    def __call__(self, image):
        # Sparse page mode alone can ignore text enclosed by a plate border.
        # Still search the complete tile, then independently read at most three
        # classical quadrilateral crops. These are discovery hints, not plate
        # outlines, and need no vehicle or detector output.
        yield from self._read(image, 11)
        for crop, inverse, padded, padded_inverse in _contour_crops(image):
            if self.cancelled():
                return
            retry = False
            for active, transform in ((crop, inverse), (padded, padded_inverse)):
                if active is padded and (not retry or self.cancelled()):
                    break
                crop_h, crop_w = active.shape[:2]
                for text, box, confidence in self._read(active, 6):
                    local = _box(box, crop_w, crop_h)
                    if local is None:
                        continue
                    if (local[0] == 0 or local[1] == 0
                            or local[2] == crop_w or local[3] == crop_h):
                        retry = True
                        continue
                    x1, y1, x2, y2 = local
                    points = np.float32([[[x1,y1],[x2,y1],[x2,y2],[x1,y2]]])
                    mapped = cv2.perspectiveTransform(points, transform)[0]
                    if not np.isfinite(mapped).all():
                        continue
                    h, w = image.shape[:2]
                    mapped_box = (max(0, math.floor(float(mapped[:,0].min()))),
                                  max(0, math.floor(float(mapped[:,1].min()))),
                                  min(w, math.ceil(float(mapped[:,0].max()))),
                                  min(h, math.ceil(float(mapped[:,1].max()))))
                    yield text, mapped_box, confidence


def _contour_crops(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 60, 180)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    retained = []
    for contour in heapq.nlargest(160, contours, key=cv2.contourArea):
        area = abs(cv2.contourArea(contour))
        if area < 100 or area > gray.size * .6:
            continue
        points = cv2.approxPolyDP(contour, .035 * cv2.arcLength(contour, True), True)
        if len(points) != 4 or not cv2.isContourConvex(points):
            continue
        rw, rh = sorted(cv2.minAreaRect(contour)[1], reverse=True)
        if rh < 8 or rw < 24 or not 1.4 <= rw / rh <= 8.5:
            continue
        vertices = np.float32(points.reshape(4, 2))
        ordered = vertices[np.argsort(vertices[:,1], kind='stable')]
        top = ordered[:2][np.argsort(ordered[:2,0])]
        bottom = ordered[2:][np.argsort(ordered[2:,0])]
        quad = np.float32([top[0], top[1], bottom[1], bottom[0]])
        bounds = (int(quad[:,0].min()), int(quad[:,1].min()),
                  int(quad[:,0].max()) + 1, int(quad[:,1].max()) + 1)
        if any(_overlap(bounds, previous) >= .8 for previous in retained):
            continue
        out_w = max(2, round(max(np.linalg.norm(quad[1]-quad[0]), np.linalg.norm(quad[2]-quad[3]))))
        out_h = max(2, round(max(np.linalg.norm(quad[3]-quad[0]), np.linalg.norm(quad[2]-quad[1]))))
        target = np.float32([[0,0], [out_w-1,0], [out_w-1,out_h-1], [0,out_h-1]])
        matrix = cv2.getPerspectiveTransform(quad, target)
        inverse = cv2.getPerspectiveTransform(target, quad)
        crop = cv2.warpPerspective(image, matrix, (out_w, out_h))
        # If an OCR observation touches the tight crop, retry using source
        # pixels beyond the contour, without accepting the clipped observation.
        pad_x, pad_y = max(4, round(out_w*.05)), max(4, round(out_h*.10))
        padded_target = np.float32([[pad_x,pad_y], [pad_x+out_w-1,pad_y],
                                    [pad_x+out_w-1,pad_y+out_h-1], [pad_x,pad_y+out_h-1]])
        padded_matrix = cv2.getPerspectiveTransform(quad, padded_target)
        padded_inverse = cv2.getPerspectiveTransform(padded_target, quad)
        retained.append(bounds)
        padded = cv2.warpPerspective(image, padded_matrix, (out_w+2*pad_x, out_h+2*pad_y))
        yield crop, inverse, padded, padded_inverse
        if len(retained) == MAX_CONTOURS:
            break


def _positions(size, extent):
    if size <= extent:
        return [0]
    starts = list(range(0, size - extent + 1, extent - OVERLAP))
    if starts[-1] != size - extent:
        starts.append(size - extent)
    return starts


def _box(value, width, height):
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        valid = all(type(v) in (int, float) and math.isfinite(v) for v in value)
    except OverflowError:
        valid = False
    if not valid:
        return None
    x1, y1, x2, y2 = value
    if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
        return None
    return (math.floor(x1), math.floor(y1), math.ceil(x2), math.ceil(y2))


def _queries(hints):
    if isinstance(hints, str):
        hints = normalize_queries(hints)
    # The matcher validates the entire prepared batch, including mixed modes.
    match_text('', hints)
    return tuple(hints)


def _inputs(frame, hints, regions):
    if (not isinstance(frame, np.ndarray) or frame.dtype != np.uint8
            or frame.ndim != 3 or frame.shape[2] != 3 or min(frame.shape[:2]) < 2):
        raise ValueError('Expected a nonempty uint8 BGR frame')
    hints = _queries(hints)
    height, width = frame.shape[:2]
    if max(height, width) > MAX_DIMENSION:
        raise ValueError('Frame exceeds the bounded OCR dimension limit')
    if regions is None:
        regions = ()
    if not isinstance(regions, (list, tuple)) or len(regions) > MAX_REGIONS:
        raise ValueError('At most eight source regions are allowed')
    provided = []
    for region in regions:
        box = _box(region, width, height)
        if box is None:
            raise ValueError('Invalid source region')
        provided.append(box)
    xs, ys = _positions(width, TILE_WIDTH), _positions(height, TILE_HEIGHT)
    if len(xs) * len(ys) + len(provided) > MAX_TILES:
        raise ValueError('Frame exceeds the bounded OCR tile limit')
    full = [(x, y, min(x + TILE_WIDTH, width), min(y + TILE_HEIGHT, height))
            for y in ys for x in xs]
    return hints, provided, full


def _overlap(a, b):
    inter = max(0, min(a[2], b[2])-max(a[0], b[0])) * max(0, min(a[3], b[3])-max(a[1], b[1]))
    area = min((a[2]-a[0])*(a[3]-a[1]), (b[2]-b[0])*(b[3]-b[1]))
    return inter / area if area else 0


def _suggested(box, width, height):
    x1, y1, x2, y2 = box
    mx, my = max(4, math.ceil((x2-x1)*.12)), max(4, math.ceil((y2-y1)*.4))
    return max(0,x1-mx), max(0,y1-my), min(width,x2+mx), min(height,y2+my)


def search_frame(frame_bgr, hints, regions=None, reader=None, cancelled=None):
    """Search complete native-resolution tiles and optional source boxes.

    ``hints`` is a batch of PlateQuery values, or a string of full queries.
    A reader accepts BGR pixels and yields (text, x1/y1/x2/y2 box, confidence)
    with confidence in [0,1]. Fragment hits retain the entire OCR word. Results
    are unreviewed suggestions; neither OCR nor a supplied box proves a plate
    boundary. Cancellation leaves an explicit incomplete result. OCR failure
    raises SearchError rather than treating an unsearched tile as a negative.
    """
    queries, provided, tiles = _inputs(frame_bgr, hints, regions)
    stop = cancelled if callable(cancelled) else lambda: False
    work = [(box, 'provided_region') for box in provided] + [(box, 'full_frame') for box in tiles]
    height, width = frame_bgr.shape[:2]
    hits, completed, truncated = [], 0, False
    for box, source in work:
        if stop():
            break
        x1, y1, x2, y2 = box
        image = frame_bgr[y1:y2, x1:x2]
        if reader is None:
            reader = LocalTesseract(stop)
        read = reader if callable(reader) else reader.read
        try:
            for row_index, row in enumerate(islice(read(image), MAX_TOKENS + 1)):
                if row_index == MAX_TOKENS:
                    truncated = True
                    break
                try:
                    text, raw_box, raw_confidence = row
                    local = _box(raw_box, x2-x1, y2-y1)
                    if local is None or not isinstance(text, str):
                        continue
                    if (isinstance(raw_confidence, (bool, np.bool_))
                            or not isinstance(raw_confidence, (int, float, np.integer, np.floating))):
                        continue
                    confidence = float(raw_confidence)
                    if not math.isfinite(confidence) or not 0 <= confidence <= 1:
                        continue
                    # An internally clipped OCR word cannot safely represent the
                    # whole observed token. Overlap supplies another view.
                    if (local[0] == 0 or local[1] == 0 or
                            local[2] == x2-x1 or local[3] == y2-y1):
                        continue
                    matches = match_text(text, queries)
                    if not matches:
                        continue
                    source_box = (local[0]+x1, local[1]+y1, local[2]+x1, local[3]+y1)
                    obs = Observation(text, source_box, confidence, source)
                    candidate = SearchHit(obs, matches,
                        box if source == 'provided_region' else _suggested(source_box, width, height),
                        'provided_unverified' if source == 'provided_region' else 'unknown')
                    duplicate = next((i for i, previous in enumerate(hits)
                        if previous.matches == matches and _overlap(previous.observation.box, source_box) >= .8), None)
                    if duplicate is not None:
                        # Prefer an explicitly supplied whole-region suggestion.
                        if source == 'provided_region' and hits[duplicate].boundary == 'unknown':
                            hits[duplicate] = candidate
                    elif len(hits) < MAX_HITS:
                        hits.append(candidate)
                    else:
                        truncated = True
                except (TypeError, ValueError, OverflowError):
                    continue
        except Exception:
            raise SearchError('OCR reader failed or timed out') from None
        if stop():
            break
        completed += 1
    return FrameSearch(tuple(hits), completed == len(work), completed, len(work), truncated)
