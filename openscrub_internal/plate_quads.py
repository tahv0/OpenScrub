"""Validated, source-bound manual plate quads; no inference or tracking."""
import math
import re

import cv2
import numpy as np

from openscrub_internal import exact_samples as exact


# Restrict v1 to common native 8-bit SDR formats. Unspecified colour tags on
# these formats are accepted; HDR transfer/primaries and all 10-bit formats are
# deliberately outside this contract.
_SDR_FORMATS = frozenset(('yuv420p', 'yuvj420p', 'yuv422p', 'yuvj422p',
                          'yuv444p', 'yuvj444p', 'nv12', 'bgr24', 'rgb24'))
_SDR_TRANSFER = frozenset(('', 'unknown', 'bt709', 'smpte170m', 'bt470bg',
                           'iec61966-2-1', 'smpte240m'))


def _sdr_facts(facts):
    return (isinstance(facts, dict)
            and facts.get('pixel_format') in _SDR_FORMATS
            and facts.get('color_transfer', '').lower() in _SDR_TRANSFER
            and facts.get('color_primaries', '').lower() != 'bt2020')


def native_sdr(provenance, facts):
    if not isinstance(provenance, dict):
        return False
    settings = provenance.get('settings') or {}
    return (isinstance(settings, dict)
            and not any(provenance.get(k) for k in ('vfr_normalized', 'hdr_tonemapped', 'hdr_output', 'original_input'))
            and not settings.get('no_vfr_fix') and settings.get('vfr') != 'ignore'
            and _sdr_facts(facts))


def same_sdr_scan(provenance, facts):
    """A normalized SDR scan is eligible only when SDR is the intended output.

    This admits no scan-to-original mapping. The caller must still verify the
    selected scan digest, timeline and exact decoded frame at save/render, and
    must never apply the quad to the separate HDR source.
    """
    if native_sdr(provenance, facts):
        return True
    if not isinstance(provenance, dict):
        return False
    source, original = provenance.get('input'), provenance.get('original_input')
    settings = provenance.get('settings') or {}
    return (provenance.get('vfr_normalized') is True
            and provenance.get('hdr_output') is False
            and isinstance(source, str) and bool(source)
            and isinstance(original, str) and bool(original) and source != original
            and isinstance(settings, dict) and not settings.get('no_vfr_fix')
            and settings.get('vfr') != 'ignore' and _sdr_facts(facts))


def points_in_frame(points, width, height, *, normalized=False):
    """Strict clockwise convex full-frame edges, with usable integer raster."""
    if (type(width) is not int or type(height) is not int
            or not 0 < width <= 2147483647 or not 0 < height <= 2147483647
            or not isinstance(points, list) or len(points) != 4):
        raise ValueError('four in-frame corners required')
    pixels = []
    for point in points:
        if not isinstance(point, list) or len(point) != 2 or not all(exact.finite(v) for v in point):
            raise ValueError('finite numeric corner pairs required')
        x, y = point
        if normalized:
            if not (0 <= x <= 1 and 0 <= y <= 1):
                raise ValueError('corner outside source frame')
            x, y = x * width, y * height
        if not (0 <= x <= width and 0 <= y <= height):
            raise ValueError('corner outside source frame')
        pixels.append((x, y))
    for i in range(4):
        a, b, c = pixels[i], pixels[(i+1) % 4], pixels[(i+2) % 4]
        cross = (b[0]-a[0])*(c[1]-b[1]) - (b[1]-a[1])*(c[0]-b[0])
        if not math.isfinite(cross) or cross <= 0:
            raise ValueError('corners must be a clockwise strictly convex ring')
    vertices = [(round(x), round(y)) for x, y in pixels]
    if (not all(0 <= x <= 2147483647 and 0 <= y <= 2147483647 for x, y in vertices)
            or cv2.contourArea(np.asarray(vertices, dtype=np.int32)) <= 0):
        raise ValueError('corners have no usable raster')
    return pixels


def make_record(points, pc, digest, fps, count, facts):
    w, h = facts['width'], facts['height']
    pixels = points_in_frame(points, w, h)
    normalized = [[x / w, y / h] for x, y in pixels]
    points_in_frame(normalized, w, h, normalized=True)
    return {'version': 1, 'points': normalized,
            'source': {'sha256': digest, 'stream': facts['stream'], 'width': w, 'height': h},
            'frame': {'index': pc['index'], 'fps': fps, 'count': count,
                      'policy': exact.POLICY, 'timeline_eq': pc['timeline_eq']}}


def valid_record(record):
    try:
        if (not isinstance(record, dict) or set(record) != {'version', 'points', 'source', 'frame'}
                or type(record['version']) is not int or record['version'] != 1):
            return False
        source, frame = record['source'], record['frame']
        if (not isinstance(source, dict) or set(source) != {'sha256', 'stream', 'width', 'height'}
                or not isinstance(source['sha256'], str) or re.fullmatch('[0-9a-f]{64}', source['sha256']) is None
                or type(source['stream']) is not int or source['stream'] < 0
                or not isinstance(frame, dict) or set(frame) != {'index', 'fps', 'count', 'policy', 'timeline_eq'}
                or type(frame['index']) is not int or type(frame['count']) is not int
                or not 0 <= frame['index'] < frame['count']
                or not exact.finite(frame['fps']) or frame['fps'] <= 0
                or frame['policy'] != exact.POLICY
                or not isinstance(frame['timeline_eq'], str)
                or re.fullmatch('[0-9a-f]{64}', frame['timeline_eq']) is None):
            return False
        points_in_frame(record['points'], source['width'], source['height'], normalized=True)
        return True
    except (KeyError, TypeError, ValueError, OverflowError, cv2.error):
        return False
