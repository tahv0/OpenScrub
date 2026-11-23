"""Assisted plate letters: plan which frames get a letter mask and which are gaps.

Pure planning, no video or engine imports. ``plan_cover`` lets a sample with
no mask borrow the mask of a nearby direct sample of the same track in the
same shot, and lists the stretches that still have no mask as gaps.
"""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field

import cv2

BORROW_S = 1.0
JOIN_S = 1.0
MERGE_FRAMES = 3
CUT_CORREL = 0.5
JOIN_AREA = (0.5, 2.0)
_EPS = 1e-9


@dataclass(frozen=True)
class Sample:
    key: int
    track: int
    t0: float
    t1: float
    box: tuple
    poly: tuple
    direct: bool


@dataclass(frozen=True)
class Bridge:
    track: int
    frame: int
    box: tuple
    poly: tuple


@dataclass(frozen=True)
class Gap:
    track: int
    t0: float
    t1: float
    frames: int
    frame: int
    box: tuple


@dataclass
class CoverPlan:
    polys: dict = field(default_factory=dict)
    drop: set = field(default_factory=set)
    bridges: list = field(default_factory=list)
    gaps: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)


def frame_signature(frame):
    """Normalized hue/saturation histogram of a copy 64 px wide."""
    h, w = frame.shape[:2]
    small = cv2.resize(frame, (64, max(1, round(h * 64 / w))), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [16, 16], [0, 180, 0, 256])
    return cv2.normalize(hist, hist, 1.0, 0.0, cv2.NORM_L1).astype("float32")


def is_cut(previous, current):
    return cv2.compareHist(previous, current, cv2.HISTCMP_CORREL) < CUT_CORREL


def _frames(s, fps, frame_count=None):
    lo, hi = round(s.t0 * fps), round(s.t1 * fps) + 1
    if frame_count is not None:
        lo, hi = max(lo, 0), min(hi, frame_count)
    return range(lo, hi)


def _dist(a, b):
    return max(0.0, a.t0 - b.t1, b.t0 - a.t1)


def _merge_runs(frames):
    """Group sorted unique frames into runs whose neighbours are <= MERGE_FRAMES apart."""
    runs = []
    for f in frames:
        if runs and f - runs[-1][-1] <= MERGE_FRAMES:
            runs[-1].append(f)
        else:
            runs.append([f])
    return runs


def _join(plan, ends, starts, state, fps, cuts, join_s, frame_count=None):
    """Bridge short dropouts between the end of one track and the start of another."""
    order = sorted(starts, key=lambda tr: starts[tr].t0)
    t0s = [starts[tr].t0 for tr in order]
    pairs = []
    for ta, a in ends.items():
        af = round(a.t1 * fps)
        ax = (a.box[0] + a.box[2]) / 2
        ay = (a.box[1] + a.box[3]) / 2
        aw = a.box[2] - a.box[0]
        aarea = aw * (a.box[3] - a.box[1])
        i = bisect_right(t0s, a.t1)
        while i < len(order) and t0s[i] - a.t1 <= join_s + _EPS:
            tb = order[i]
            i += 1
            if tb == ta:
                continue
            b = starts[tb]
            bf = round(b.t0 * fps)
            if bisect_right(cuts, bf) != bisect_right(cuts, af):
                continue
            dist = ((((b.box[0] + b.box[2]) / 2 - ax) ** 2 + ((b.box[1] + b.box[3]) / 2 - ay) ** 2)) ** 0.5
            barea = (b.box[2] - b.box[0]) * (b.box[3] - b.box[1])
            if dist > aw or aarea <= 0 or not JOIN_AREA[0] <= barea / aarea <= JOIN_AREA[1]:
                continue
            pairs.append((dist, ta, tb))
    pairs.sort()
    used_a, used_b = set(), set()
    for _, ta, tb in pairs:
        if ta in used_a or tb in used_b:
            continue
        used_a.add(ta)
        used_b.add(tb)
        a, b = ends[ta], starts[tb]
        af, bf = round(a.t1 * fps), round(b.t0 * fps)
        top = bf if frame_count is None else min(bf, frame_count)
        for f in range(max(af + 1, 0), top):
            u = (f - af) / (bf - af)
            box = tuple(x + (y - x) * u for x, y in zip(a.box, b.box))
            plan.bridges.append(Bridge(ta, f, box, plan.polys[a.key]))
            state[ta][0].add(f)
            state[tb][0].add(f)
    plan.bridges.sort(key=lambda br: (br.frame, br.track))


def plan_cover(samples, fps, cuts, borrow_s=BORROW_S, join_s=JOIN_S, frame_count=None):
    """frame_count, when given, limits every counted or listed frame to
    0..frame_count-1: grace-padded spans past the video's end are ignored."""
    cuts = sorted(cuts)
    plan = CoverPlan()
    by_track = {}
    for s in samples:
        by_track.setdefault(s.track, []).append(s)
    masked_total = 0
    gap_total = 0

    def shot(s):
        return bisect_right(cuts, round(s.t0 * fps))

    state = {}
    ends = {}
    starts_ = {}
    for track, lst in by_track.items():
        lst.sort(key=lambda s: (s.t0, s.key))
        maxdur = max(s.t1 - s.t0 for s in lst)
        donors = [s for s in lst if s.direct and s.poly]
        dt0 = [s.t0 for s in donors]
        covered = set()
        dropped = []
        for s in lst:
            if s.poly:
                plan.polys[s.key] = s.poly
                covered.update(_frames(s, fps, frame_count))
                continue
            sh = shot(s)
            best = None
            best_d = None
            i = bisect_right(dt0, s.t0)
            j = i - 1
            while j >= 0 and s.t0 - dt0[j] <= borrow_s + maxdur + _EPS:
                c = donors[j]
                if shot(c) == sh:
                    d = _dist(s, c)
                    if d <= borrow_s + _EPS:
                        best, best_d = c, d
                        break
                j -= 1
            k = i
            while k < len(donors) and dt0[k] - s.t1 <= borrow_s + _EPS:
                c = donors[k]
                if shot(c) == sh:
                    d = _dist(s, c)
                    if d <= borrow_s + _EPS and (best is None or d < best_d):
                        best, best_d = c, d
                    break
                k += 1
            if best is not None:
                plan.polys[s.key] = best.poly
                covered.update(_frames(s, fps, frame_count))
            else:
                plan.drop.add(s.key)
                dropped.append(s)
        masked_total += len(covered)
        masked = [s for s in lst if s.key in plan.polys]
        state[track] = (covered, dropped)
        if masked:
            ends[track] = max(masked, key=lambda s: (s.t1, s.key))
            starts_[track] = min(masked, key=lambda s: (s.t0, s.key))

    _join(plan, ends, starts_, state, fps, cuts, join_s, frame_count)

    for track, (covered, dropped) in state.items():
        if not dropped:
            continue
        gap_frames = set()
        for s in dropped:
            gap_frames.update(f for f in _frames(s, fps, frame_count) if f not in covered)
        if not gap_frames:
            continue
        dropped_frames = sorted(((round(s.t0 * fps), s) for s in dropped), key=lambda x: x[0])
        starts = [f for f, _ in dropped_frames]
        n = len(dropped_frames)
        for run in _merge_runs(sorted(gap_frames)):
            mid = run[len(run) // 2]
            p = bisect_left(starts, mid)
            if p >= n or (p > 0 and mid - starts[p - 1] <= starts[p] - mid):
                p -= 1
            box = dropped_frames[p][1].box
            plan.gaps.append(Gap(track, run[0] / fps, run[-1] / fps, len(run), mid, box))
            gap_total += len(run)
    plan.gaps.sort(key=lambda g: (g.t0, g.track))
    plan.stats = {"masked_frames": masked_total, "bridged_frames": len(plan.bridges), "gap_frames": gap_total}
    return plan
