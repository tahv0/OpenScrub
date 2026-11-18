"""Bounded CFR sample evidence, shared by web samples and future strict seeds.

Capture ownership stays with the caller. Metadata qualification and observed
stamps describe a declared source subset, not immutable bytes or a CFR proof.
"""
from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
import math

import cv2
import numpy as np

POLICY = 'opencv-ffmpeg-zero-cfr-v1'
_ENCODER = json.JSONEncoder(sort_keys=True, ensure_ascii=True,
                           separators=(',', ':'), allow_nan=True)
_EXCLUDED = frozenset(('enabled', 'cbox', 't_start', 't_end', 'last_seen'))


class ExactError(ValueError):
    def __init__(self, detail, status=422, code='exact_sample_unavailable'):
        super().__init__(detail)
        self.status, self.code = status, code


def finite(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def vector(value, length):
    if (not isinstance(value, list) or len(value) != length
            or not all(finite(v) for v in value)):
        raise ExactError('finite nonboolean coordinate vector required')
    return value


def _feed(digest, value):
    for chunk in _ENCODER.iterencode(value):
        digest.update(chunk.encode('ascii'))


def row_context_eq(row):
    digest = hashlib.sha256(b'openscrub-row-context-v1:')
    _feed(digest, {key:value for key,value in row.items() if key not in _EXCLUDED})
    return digest.hexdigest()


def row_base(row):
    box = vector(row['cbox'], 4)
    span = vector([row['t_start'], row['t_end'],
                   row.get('last_seen', row['t_start'])], 3)
    return {'cbox': list(box), 'span': span}


def timeline(doc, facts):
    """Validate/hash the parsed projection incrementally, retaining no copy."""
    try:
        rs = doc['render_state']
        fps, cum = rs['fps'], rs['cum']
        if (not finite(fps) or fps <= 0 or not isinstance(cum, list)
                or not cum or not finite(len(cum)/fps)):
            raise ExactError('invalid scan timeline')
        digest = hashlib.sha256(b'openscrub-timeline-v1:')
        _feed(digest, [POLICY, fps, len(cum), facts['stream'], facts['width'],
                       facts['height'], 'identity', 'selected-scan-input'])
        for offset in cum:
            _feed(digest, vector(offset, 2))
        return fps, cum, digest.hexdigest()
    except (KeyError, TypeError, OverflowError, ZeroDivisionError):
        raise ExactError('missing or invalid scan timeline') from None


def resolve_time(t, fps, count):
    if not finite(t) or not 0 <= t <= count/fps:
        raise ExactError('time outside scan timeline', 400, 'invalid_sample_request')
    return min(math.floor(t*fps), count-1)


def metadata_facts(probe):
    """Qualify small successful ffprobe facts; agreeing rates are an assumption."""
    try:
        streams = probe['streams']
        if len(streams) != 1:
            raise ValueError('one unambiguous video stream required')
        stream = streams[0]
        rate = Fraction(stream['r_frame_rate'])
        average = Fraction(stream['avg_frame_rate'])
        tick = Fraction(stream['time_base'])
        if rate <= 0 or average != rate or tick <= 0:
            raise ValueError('incompatible CFR rates/time base')
        if Fraction(stream['start_time']) != 0 or int(stream['start_pts']) != 0:
            raise ValueError('nonzero or unknown stream origin')
        width, height = stream['width'], stream['height']
        if any(type(v) is not int or v <= 0 for v in (width,height)):
            raise ValueError('invalid dimensions')
        # Conservatively reject display matrices, even an identity one. No
        # orientation transform is inferred from decoded dimensions.
        if stream.get('side_data_list') or float(stream.get('tags', {}).get('rotate', 0)) != 0:
            raise ValueError('unsupported display transform')
        count = stream.get('nb_frames')
        count = None if count in (None, 'N/A') else int(count)
        if count is not None and count <= 0:
            raise ValueError('invalid stream count')
        return dict(stream=stream['index'], width=width, height=height,
                    rate=float(rate), tick_s=float(tick),
                    grid_aligned=(1/rate/tick).denominator == 1, count=count)
    except (KeyError, ValueError, TypeError, ZeroDivisionError, OverflowError) as error:
        raise ExactError('unsupported stream metadata: '+str(error)) from None


def precision_bound(facts, fps, count):
    """Off-grid timestamp tick + full-timeline FPS drift + numerical roundoff.

    Integral ticks per CFR frame need only numerical precision; an off-grid
    frame can incur one tick of timestamp quantization. This is a declared
    bound, not the old probe's display epsilon.
    Never admit a bound exceeding a quarter frame; no adjacent sample fits it.
    """
    if (abs(facts['rate']-fps) > fps*1e-6
            or facts['count'] not in (None, count)):
        raise ExactError('source rates/count disagree with report')
    duration = count/fps
    quantization = 0. if facts['grid_aligned'] else facts['tick_s']
    bound = (quantization + count*abs(1/fps-1/facts['rate'])
             + 16*math.ulp(max(1., duration)))
    if not finite(bound) or not 0 < bound <= .25/fps:
        raise ExactError('timestamp precision cannot distinguish adjacent samples')
    return bound


@dataclass(frozen=True)
class DecodedFrame:
    pixels: object
    index: int
    canonical_s: float
    observed_s: float
    width: int
    height: int


@dataclass(frozen=True)
class StrictSeed:
    """Verified raw sample; lifetime is held by the caller, never a capture."""
    pixels: object
    source_selection: object
    index: int
    canonical_s: float
    observed_s: float
    fps: float
    count: int
    width: int
    height: int
    policy: str
    tolerance_s: float

    def __post_init__(self):
        if (self.policy != POLICY or not finite(self.fps) or self.fps <= 0
                or type(self.count) is not int or self.count <= 0
                or type(self.index) is not int or not 0 <= self.index < self.count
                or any(type(v) is not int or v <= 0 for v in (self.width, self.height))
                or not finite(self.tolerance_s) or not 0 < self.tolerance_s <= .25/self.fps
                or not finite(self.canonical_s) or self.canonical_s != self.index/self.fps
                or not finite(self.observed_s)
                or abs(self.observed_s-self.canonical_s) > self.tolerance_s
                or not isinstance(self.pixels, np.ndarray) or self.pixels.dtype != np.uint8
                or self.pixels.shape != (self.height,self.width,3)):
            raise ExactError('invalid strict seed')


def validate_strict_inputs(seed, box, t_ref, t0, t1):
    """Reject an explicit invalid seed/window before capture or model work."""
    if not isinstance(seed, StrictSeed):
        raise ExactError('StrictSeed required')
    seed.__post_init__()
    vector(list(box) if isinstance(box, (list,tuple)) else box, 4)
    if (not all(finite(v) for v in (t_ref,t0,t1))
            or not 0 <= t0 <= seed.canonical_s <= t1 <= seed.count/seed.fps
            or t_ref != seed.canonical_s
            or not 0 <= box[0] < box[2] <= seed.width
            or not 0 <= box[1] < box[3] <= seed.height):
        raise ExactError('strict box/reference/window differs from selected sample')


def read_indexed_capture(cap, index, *, fps, count, width, height, tolerance_s):
    """Read exactly one integer; never close or transfer the caller's capture."""
    if (type(index) is not int or not 0 <= index < count or not finite(fps) or fps <= 0
            or not finite(tolerance_s) or not 0 < tolerance_s <= .25/fps):
        raise ExactError('invalid indexed-read policy')
    if not cap.isOpened() or cap.getBackendName() != 'FFMPEG':
        raise ExactError('OpenCV FFmpeg backend required')
    actual_fps, actual_count = cap.get(cv2.CAP_PROP_FPS), cap.get(cv2.CAP_PROP_FRAME_COUNT)
    if not finite(actual_fps) or abs(actual_fps-fps) > fps*1e-6:
        raise ExactError('decoder fps differs from report')
    if finite(actual_count) and actual_count > 0 and actual_count != count:
        raise ExactError('decoder count differs from report')
    if not cap.set(cv2.CAP_PROP_POS_FRAMES, index):
        raise ExactError('decoder rejected integer seek')
    ok, pixels = cap.read()
    if not ok or pixels is None or pixels.size == 0:
        raise ExactError('indexed sample missing or EOF')
    if pixels.shape[:2] != (height, width):
        raise ExactError('decoded dimensions differ from stream')
    observed = cap.get(cv2.CAP_PROP_POS_MSEC)/1000
    canonical = index/fps
    if not finite(observed) or abs(observed-canonical) > tolerance_s:
        raise ExactError('observed sample time differs from selected index')
    return DecodedFrame(pixels, index, canonical, observed, width, height)
