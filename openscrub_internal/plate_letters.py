"""Assisted plate letters: plan which frames get a letter mask and which are gaps.

Pure planning, no video or engine imports. ``plan_cover`` lets a sample with
no mask borrow the mask of a nearby direct sample of the same track in the
same shot, and lists the stretches that still have no mask as gaps.
"""
from __future__ import annotations

import math
from bisect import bisect_left, bisect_right
from collections import Counter
from dataclasses import dataclass, field, replace

import cv2
import numpy as np

BORROW_S = 1.0
JOIN_S = 1.0
STABLE_LINE_S = 0.45
MERGE_FRAMES = 3
CUT_CORREL = 0.5
JOIN_AREA = (0.5, 2.0)
_EPS = 1e-9
# The renderer paints a sample on frame idx when
# t_start - 0.01 <= idx / fps <= t_end + 0.01 (openscrub._active_on_frame and
# plate_policy.active_on_frame). Keep this equal to that tolerance: the plan
# must count exactly the frames the renderer paints, or a visible frame can
# be missing from the gap list.
RENDER_TOL_S = 0.01


@dataclass(frozen=True)
class Sample:
    key: int
    track: int
    t0: float
    t1: float
    box: tuple
    poly: tuple
    direct: bool
    seen: float | None = None


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
    spans: dict = field(default_factory=dict)
    polys: dict = field(default_factory=dict)
    drop: set = field(default_factory=set)
    bridges: list = field(default_factory=list)
    gaps: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)


def frame_signature(frame):
    """Small BGR image and its normalized hue/saturation histogram."""
    h, w = frame.shape[:2]
    small = cv2.resize(frame, (64, max(1, round(h * 64 / w))), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [16, 16], [0, 180, 0, 256])
    thumbnail = cv2.resize(small, (16, 12), interpolation=cv2.INTER_AREA)
    return thumbnail, cv2.normalize(hist, hist, 1.0, 0.0, cv2.NORM_L1).astype("float32")


def is_cut(previous, current):
    before, before_hist = previous
    after, after_hist = current
    if cv2.compareHist(before_hist, after_hist, cv2.HISTCMP_CORREL) >= CUT_CORREL:
        return False
    # Hue is unstable around gray and near histogram bin boundaries. Require
    # a visible change in the downsampled image as well before ending the shot.
    return cv2.absdiff(before, after).mean() > 12


def _span(t0, t1, fps):
    """First and last frame the renderer paints for a span (may be empty)."""
    lo_t, hi_t = t0 - RENDER_TOL_S, t1 + RENDER_TOL_S
    lo = math.ceil(lo_t * fps)
    while lo / fps < lo_t:          # the same float test as the renderer
        lo += 1
    while (lo - 1) / fps >= lo_t:
        lo -= 1
    hi = math.floor(hi_t * fps)
    while hi / fps > hi_t:
        hi -= 1
    while (hi + 1) / fps <= hi_t:
        hi += 1
    return lo, hi


def _frames(s, fps, frame_count=None, first_frame=None):
    lo, hi = _span(s.t0, s.t1, fps)
    hi += 1
    if frame_count is not None:
        lo, hi = max(lo, 0), min(hi, frame_count)
    if first_frame is not None:
        lo = max(lo, first_frame)
    return range(lo, hi)


def _first(s, fps):
    return _span(s.t0, s.t1, fps)[0]


def _last(s, fps):
    return _span(s.t0, s.t1, fps)[1]


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


def _has_letter_cover(rows, first, last, fps):
    """Is every frame of a hold outside the handoff covered by the other track?"""
    if first > last:
        return True
    for row in sorted(rows, key=lambda s: s.t0):
        if not row.poly:
            continue
        lo, hi = _span(row.t0, row.t1, fps)
        if lo > first:
            break
        first = max(first, hi + 1)
        if first > last:
            return True
    return False


def _trim_overlapping_holds(by_track, fps, cuts, join_s, plan):
    """Find consecutive sightings whose overlapping grace periods paint two positions."""
    starts, ends = [], []
    for rows in by_track.values():
        # Only trim an outermost row with its own observed lettering. Other
        # rows must already end/start on their own side of that observation.
        first = min(rows, key=lambda s: s.t0)
        last = max(rows, key=lambda s: s.t1)
        if (first.seen is not None and first.poly and
                all(s is first or s.t0 >= first.seen for s in rows)):
            starts.append(first)
        if (last.seen is not None and last.poly and
                all(s is last or s.t1 <= last.seen + _EPS for s in rows)):
            ends.append(last)
    starts.sort(key=lambda s: s.seen)
    times = [s.seen for s in starts]
    pairs = []
    for a in ends:
        lo = bisect_right(times, a.seen + _EPS)
        hi = bisect_right(times, a.seen + join_s + _EPS)
        for b in starts[lo:hi]:
            if a.track == b.track or a.t1 < b.t0:
                continue
            if bisect_right(cuts, round(a.seen * fps)) != bisect_right(cuts, round(b.seen * fps)):
                continue
            # Strong overlap in the observed boxes. Two plates seen together
            # cannot qualify as a handoff, regardless of their distance.
            ax, ay, ax2, ay2 = a.box
            bx, by, bx2, by2 = b.box
            area = max(0, min(ax2, bx2) - max(ax, bx)) * max(0, min(ay2, by2) - max(ay, by))
            union = (ax2 - ax) * (ay2 - ay) + (bx2 - bx) * (by2 - by) - area
            if union > 0 and area / union > 0.5:
                pairs.append((a, b))

    outgoing = Counter(a.track for a, _ in pairs)
    incoming = Counter(b.track for _, b in pairs)
    joins = {}
    for a, b in pairs:
        if outgoing[a.track] != 1 or incoming[b.track] != 1:
            continue
        af, bf = round(a.seen * fps), round(b.seen * fps)
        if not (_has_letter_cover(by_track[a.track], _first(b, fps), af - 1, fps)
                and _has_letter_cover(by_track[b.track], bf + 1, _last(a, fps), fps)):
            continue
        # A singleton track can participate at both ends.
        plan.spans[a.key] = (plan.spans.get(a.key, (a.t0, a.t1))[0], a.seen)
        plan.spans[b.key] = (b.seen, plan.spans.get(b.key, (b.t0, b.t1))[1])
        joins[a.track, b.track] = (replace(a, t1=a.seen), replace(b, t0=b.seen))
    for track in {tr for pair in joins for tr in pair}:
        by_track[track] = [replace(s, t0=plan.spans[s.key][0], t1=plan.spans[s.key][1])
                           if s.key in plan.spans else s for s in by_track[track]]
    return joins


def _join(plan, ends, starts, state, fps, cuts, join_s, trimmed, frame_count=None, first_frame=None):
    """Bridge short dropouts between the end of one track and the start of another."""
    order = sorted(starts, key=lambda tr: starts[tr].t0)
    t0s = [starts[tr].t0 for tr in order]
    pairs = [(False, 0.0, ta, tb) for ta, tb in trimmed]
    for ta, a in ends.items():
        af = _last(a, fps)
        ax = (a.box[0] + a.box[2]) / 2
        ay = (a.box[1] + a.box[3]) / 2
        aw = a.box[2] - a.box[0]
        aarea = aw * (a.box[3] - a.box[1])
        i = bisect_right(t0s, a.t1)
        while i < len(order) and t0s[i] - a.t1 <= join_s + _EPS:
            tb = order[i]
            i += 1
            if tb == ta or (ta, tb) in trimmed:
                continue
            b = starts[tb]
            bf = _first(b, fps)
            if bisect_right(cuts, bf) != bisect_right(cuts, af):
                continue
            dist = ((((b.box[0] + b.box[2]) / 2 - ax) ** 2 + ((b.box[1] + b.box[3]) / 2 - ay) ** 2)) ** 0.5
            barea = (b.box[2] - b.box[0]) * (b.box[3] - b.box[1])
            if dist > aw or aarea <= 0 or not JOIN_AREA[0] <= barea / aarea <= JOIN_AREA[1]:
                continue
            pairs.append((True, dist, ta, tb))
    pairs.sort()
    used_a, used_b = set(), set()
    for _, _, ta, tb in pairs:
        if ta in used_a or tb in used_b:
            continue
        used_a.add(ta)
        used_b.add(tb)
        a, b = trimmed.get((ta, tb), (ends[ta], starts[tb]))
        af, bf = _last(a, fps), _first(b, fps)
        top = bf if frame_count is None else min(bf, frame_count)
        for f in range(max(af + 1, 0 if first_frame is None else first_frame), top):
            u = (f - af) / (bf - af)
            box = tuple(x + (y - x) * u for x, y in zip(a.box, b.box))
            plan.bridges.append(Bridge(ta, f, box, plan.polys[a.key]))
            state[ta][0].add(f)
            state[tb][0].add(f)
    plan.bridges.sort(key=lambda br: (br.frame, br.track))


def _letter_quads(polys):
    """Only use convex, box-normalized detector quads for temporal comparisons."""
    quads = []
    for poly in polys:
        try:
            q = np.asarray(poly, dtype=np.float32)
        except (ValueError, TypeError, OverflowError):
            return []
        if (q.shape != (4, 2) or not np.isfinite(q).all() or
                q.min() < 0 or q.max() > 1 or not cv2.isContourConvex(q)):
            return []
        quads.append(q)
    return quads


def _line_axis(q):
    bounds = cv2.boxPoints(cv2.minAreaRect(q))
    edges = np.diff(bounds[:3], axis=0)
    axis = max(edges, key=lambda e: float(e @ e))
    return axis / np.linalg.norm(axis)


def _outside_letter_line(quads, ref, axis):
    """Identify small, detached groups beside a corroborated lettering band.

    Keep extensions at either end and substantial second lines. Measure the
    components on each side together so a row of individual characters counts
    as a row even when the text detector splits it into many small shapes.
    """
    normal = np.array([-axis[1], axis[0]])
    along, across = ref @ axis, ref @ normal
    lo, hi = along.min(), along.max()
    margin = max(.035, .16 * float(np.ptp(across)))
    sides = [[], []]
    for j, q in enumerate(quads):
        v, u = q @ normal, q @ axis
        if v.max() < across.min():
            side = 0
        elif v.min() > across.max():
            side = 1
        else:
            continue
        # Use the actual outline for clearance: a foreshortened plate can
        # be narrower at one end than its enclosing rotated rectangle.
        if (cv2.intersectConvexConvex(ref, q)[0] > 0
                or any(cv2.pointPolygonTest(ref, (float(x), float(y)), True) >= -margin
                       for x, y in q)):
            continue
        sides[side].append((j, u.min(), u.max(), cv2.contourArea(q)))

    outside = set()
    for group in sides:
        if group:
            left = min(item[1] for item in group)
            right = max(item[2] for item in group)
            if (lo <= left and right <= hi and right - left < .45 * (hi - lo)
                    and sum(item[3] for item in group) < .22 * cv2.contourArea(ref)):
                outside.update(item[0] for item in group)
    return outside


@dataclass
class _LineSighting:
    time: float
    shot: int
    sample: Sample
    quad: np.ndarray
    area: float


def _stable_letters(rows, fps, cuts):
    """Repair a short partial mask using two independent single-line sightings."""
    observed = [s for s in rows if s.poly]
    if not observed or all(s.poly == observed[0].poly for s in observed):
        return {}
    # Compare at the sighting time. Grace padding can move a sample's start
    # into the previous shot, especially on the first sample of a track.
    def time_of(s):
        return s.seen if s.seen is not None else s.t0

    shapes = {s.key: _letter_quads(s.poly) for s in observed}
    lines = []
    for s in sorted(observed, key=time_of):
        qs = shapes[s.key]
        if not s.direct or len(qs) != 1:
            continue
        q = qs[0]
        width, height = s.box[2] - s.box[0], s.box[3] - s.box[1]
        if min(width, height) <= 0 or np.ptp(q, axis=0).max() < .70:
            continue
        _, dims, _ = cv2.minAreaRect(q * np.float32([width, height]))
        if min(dims) <= 0 or max(dims) < 2 * min(dims):
            continue
        t = time_of(s)
        lines.append(_LineSighting(t, bisect_right(cuts, round(t * fps)), s, q, cv2.contourArea(q)))

    # A single unusually large outline must never seed subsequent masks.
    pairs = []
    for a, b in zip(lines, lines[1:]):
        if (round(a.time * fps) == round(b.time * fps) or
                b.time - a.time > .15 + _EPS or a.shot != b.shot):
            continue
        shared, _ = cv2.intersectConvexConvex(a.quad, b.quad)
        if shared >= .75 * max(a.area, b.area):
            pairs.append((a, b))
    if not pairs:
        return {}
    starts = [a.time for a, b in pairs]
    result = {}
    for s in observed:
        qs = shapes[s.key]
        if not qs:
            continue
        t = time_of(s)
        shot = bisect_right(cuts, round(t * fps))
        main = max(qs, key=cv2.contourArea)
        area = cv2.contourArea(main)
        # Compare in plate-box coordinates so the cover follows a moving plate.
        ref = None
        best_rank = (0., -math.inf)
        for k in range(bisect_left(starts, t - STABLE_LINE_S - _EPS),
                       bisect_right(starts, t + STABLE_LINE_S + _EPS)):
            a, b = pairs[k]
            if a.shot != shot or b.time > t + STABLE_LINE_S + _EPS:
                continue
            donor = a if abs(a.time - t) < abs(b.time - t) else b
            rank = (min(a.area, b.area), -abs(donor.time - t))
            if rank <= best_rank:
                continue
            box = donor.sample.box
            if not all(.7 <= (s.box[i+2] - s.box[i]) / (box[i+2] - box[i]) <= 1.45
                       for i in (0, 1)):
                continue
            shared, _ = cv2.intersectConvexConvex(donor.quad, main)
            if shared >= .65 * min(area, donor.area):
                ref, best_rank = donor, rank
        if ref is None:
            continue
        axis = _line_axis(ref.quad)
        full, current = ref.quad @ axis, main @ axis
        length = np.ptp(full)
        missing_end = max(current.min() - full.min(), full.max() - current.max())
        # A fragment left near the lost end distinguishes a split line from
        # a complete mask that just translated within a jittering plate box.
        split_end = (missing_end > .12 * length and any(
            q is not main and ((q @ axis).min() < current.min() - .04 * length or
                               (q @ axis).max() > current.max() + .04 * length)
            and cv2.intersectConvexConvex(q, ref.quad)[0] > .5 * cv2.contourArea(q)
            for q in qs))
        partial = np.ptp(current) < .90 * length or area < .70 * ref.area or split_end
        # On a full sighting use the current tilt. On a partial sighting
        # preserve every component near the projected full line.
        outside = set()
        if len(qs) > 1:
            outside = (_outside_letter_line(qs, ref.quad, axis) if partial else
                       _outside_letter_line(qs, main, _line_axis(main)))
        if outside or partial:
            polys = tuple(poly for i, poly in enumerate(s.poly) if i not in outside)
            result[s.key] = polys + ref.sample.poly if partial else polys
    return result


def plan_cover(samples, fps, cuts, borrow_s=BORROW_S, join_s=JOIN_S, frame_count=None,
               first_frame=None):
    """frame_count, when given, limits every counted or listed frame to
    0..frame_count-1: grace-padded spans past the video's end are ignored.
    first_frame, when given, also ignores frames before it (an output clip
    that starts later); borrowing still sees every sample."""
    cuts = sorted(cuts)
    plan = CoverPlan()
    by_track = {}
    for s in samples:
        by_track.setdefault(s.track, []).append(s)
    trimmed = _trim_overlapping_holds(by_track, fps, cuts, join_s, plan)
    masked_total = 0
    gap_total = 0

    def shot(s):
        return bisect_right(cuts, _first(s, fps))

    state = {}
    ends = {}
    starts_ = {}
    for track, lst in by_track.items():
        lst.sort(key=lambda s: (s.t0, s.key))
        stable = _stable_letters(lst, fps, cuts)
        maxdur = max(s.t1 - s.t0 for s in lst)
        donors = [s for s in lst if s.direct and s.poly]
        dt0 = [s.t0 for s in donors]
        covered = set()
        dropped = []
        for s in lst:
            if s.poly:
                plan.polys[s.key] = stable.get(s.key, s.poly)
                covered.update(_frames(s, fps, frame_count, first_frame))
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
                plan.polys[s.key] = stable.get(best.key, best.poly)
                covered.update(_frames(s, fps, frame_count, first_frame))
            else:
                plan.drop.add(s.key)
                dropped.append(s)
        masked_total += len(covered)
        masked = [s for s in lst if s.key in plan.polys]
        state[track] = (covered, dropped)
        if masked:
            ends[track] = max(masked, key=lambda s: (s.t1, s.key))
            starts_[track] = min(masked, key=lambda s: (s.t0, s.key))

    _join(plan, ends, starts_, state, fps, cuts, join_s, trimmed, frame_count, first_frame)

    for track, (covered, dropped) in state.items():
        if not dropped:
            continue
        gap_frames = set()
        for s in dropped:
            gap_frames.update(f for f in _frames(s, fps, frame_count, first_frame)
                              if f not in covered)
        if not gap_frames:
            continue
        dropped_frames = sorted(((_first(s, fps), s) for s in dropped), key=lambda x: x[0])
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
