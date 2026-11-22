"""Assisted plate letters: plan which frames get a letter mask and which are gaps.

Pure planning, no video or engine imports. ``plan_cover`` lets a sample with
no mask borrow the mask of a nearby direct sample of the same track in the
same shot, and lists the stretches that still have no mask as gaps.
"""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field

BORROW_S = 1.0
JOIN_S = 1.0
MERGE_FRAMES = 3
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


def _frames(s, fps):
    return range(round(s.t0 * fps), round(s.t1 * fps) + 1)


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


def plan_cover(samples, fps, cuts, borrow_s=BORROW_S, join_s=JOIN_S):
    cuts = sorted(cuts)
    plan = CoverPlan()
    by_track = {}
    for s in samples:
        by_track.setdefault(s.track, []).append(s)
    masked_total = 0
    gap_total = 0

    def shot(s):
        return bisect_right(cuts, round(s.t0 * fps))

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
                covered.update(_frames(s, fps))
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
                covered.update(_frames(s, fps))
            else:
                plan.drop.add(s.key)
                dropped.append(s)
        masked_total += len(covered)
        if not dropped:
            continue
        gap_frames = set()
        for s in dropped:
            gap_frames.update(f for f in _frames(s, fps) if f not in covered)
        if not gap_frames:
            continue
        dropped_frames = sorted((f, s) for s in dropped for f in (round(s.t0 * fps),))
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
    plan.stats = {"masked_frames": masked_total, "bridged_frames": 0, "gap_frames": gap_total}
    return plan
