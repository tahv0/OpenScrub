"""Search explicitly selected, exactly decoded CFR samples.

The caller owns the capture and its source lifetime/identity. This module does
not publish reports or claim that the intervening frames were searched.
"""
from dataclasses import dataclass, field

from openscrub_internal import exact_samples
from .search import _queries, search_frame

MAX_FRAMES = 16


@dataclass(frozen=True)
class SampleHits:
    index: int
    time_s: float
    hits: tuple = field(repr=False)
    truncated: bool


@dataclass(frozen=True)
class SampleSearch:
    fps: float
    frame_count: int
    requested_indices: tuple
    completed_indices: tuple
    frames: tuple = field(repr=False)
    cancelled: bool


def search_capture(cap, hints, indices, *, fps, count, width, height, tolerance_s,
                   reader=None, cancelled=None):
    """Search up to 16 explicitly named frame indices through the exact reader.

    The caller must qualify the CFR metadata, bind the capture to a stable source
    and release it. Completed indices identify sampled frames, not continuous
    temporal coverage. An OCR/decode failure raises; cancellation returns only
    fully completed frames and explicitly marks the result as cancelled.
    """
    if (type(count) is not int or count <= 0 or not exact_samples.finite(fps) or fps <= 0
            or any(type(v) is not int or v <= 0 for v in (width, height))
            or not exact_samples.finite(tolerance_s) or not 0 < tolerance_s <= .25/fps
            or not isinstance(indices, (list, tuple)) or not 1 <= len(indices) <= MAX_FRAMES
            or any(type(i) is not int or not 0 <= i < count for i in indices)
            or any(a >= b for a, b in zip(indices, indices[1:]))):
        raise ValueError('Invalid bounded sample selection or stream metadata')
    hints = _queries(hints)
    stop = cancelled if callable(cancelled) else lambda: False
    frames = []
    for index in indices:
        if stop():
            break
        decoded = exact_samples.read_indexed_capture(cap, index, fps=fps, count=count,
            width=width, height=height, tolerance_s=tolerance_s)
        result = search_frame(decoded.pixels, hints, reader=reader, cancelled=stop)
        if not result.complete:
            break
        frames.append(SampleHits(index, decoded.canonical_s, result.hits, result.truncated))
    return SampleSearch(fps, count, tuple(indices), tuple(frame.index for frame in frames),
                        tuple(frames), len(frames) != len(indices))
