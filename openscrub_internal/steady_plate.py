"""Estimate shot-local plate trajectories from sparse, fully visible outlines."""

import tempfile
import cv2 as cv
import numpy as np
from .plate_outline import follow


def _fit(image, polygons):
    """Find the visible plate surface around a previously identified lettering strip."""
    h, w = image.shape[:2]
    polys = [np.float32(p) for p in polygons]
    # Rectify the neighborhood using the strip with the most character evidence.
    # The mask can contain a second projection over a sleeve or the bumper.
    gray = cv.cvtColor(image, cv.COLOR_BGR2GRAY)
    strongest = None
    best = 0
    for p in polys:
        x, y, bw, bh = cv.boundingRect(p)
        x1, y1 = max(0, x), max(0, y)
        x2, y2 = min(w, x + bw), min(h, y + bh)
        if x2 <= x1 or y2 <= y1:
            continue
        roi = gray[y1:y2, x1:x2]
        mask = np.zeros(roi.shape, np.uint8)
        cv.fillPoly(mask, [np.int32(p - [x1, y1])], 1)
        gx = cv.Sobel(roi, cv.CV_32F, 1, 0)
        gy = cv.Sobel(roi, cv.CV_32F, 0, 1)
        score = np.count_nonzero((gx * gx + gy * gy > 10000) & (mask > 0))
        if score > best:
            best = score
            strongest = p
    if strongest is None:
        return None
    rect = cv.minAreaRect(strongest)
    q = cv.boxPoints(rect)
    if np.linalg.norm(q[1] - q[0]) < np.linalg.norm(q[2] - q[1]):
        q = np.roll(q, -1, axis=0)
    L, D = sorted(rect[1], reverse=True)
    if D < 3 or L < 1.8 * D:
        return None
    target = np.float32([[100, 52], [259, 52], [259, 91], [100, 91]])
    M = cv.getPerspectiveTransform(q, target)
    inv = cv.getPerspectiveTransform(target, q)
    patch = cv.warpPerspective(image, M, (360, 144), borderValue=(111, 111, 111))
    # The frame boundary is real; never count the artificial warp padding as backing.
    yy, xx = np.indices((144, 360), dtype=np.float32)
    uv = cv.perspectiveTransform(np.dstack((xx, yy)), inv)
    valid = (
        (uv[:, :, 0] >= 0) & (uv[:, :, 0] < w) & (uv[:, :, 1] >= 0) & (uv[:, :, 1] < h)
    )
    seedmask = np.zeros(valid.shape, np.uint8)
    cv.fillPoly(
        seedmask,
        [np.rint(cv.perspectiveTransform(strongest[None], M)[0]).astype("int32")],
        1,
    )
    samp = patch[(seedmask > 0) & valid]
    if len(samp) < 64:
        return None
    bins = (samp // 32).astype(int) @ [64, 8, 1]
    back = np.median(samp[bins == np.bincount(bins).argmax()], axis=0)
    dist = np.max(np.abs(patch.astype("float32") - back), axis=2)
    mask = np.uint8((dist < 54) & valid) * 255
    mask = cv.morphologyEx(mask, cv.MORPH_CLOSE, np.ones((3, 7), np.uint8))
    contours, _ = cv.findContours(mask, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE)
    pieces = []
    for c in contours:
        area = cv.contourArea(c)
        if area < 135:
            continue
        hull = cv.convexHull(c)
        x, y, cw, ch = cv.boundingRect(hull)
        if x == 0 or y == 0 or x + cw >= 360 or y + ch >= 144:
            continue
        rw, rh = sorted(cv.minAreaRect(hull)[1], reverse=True)
        if area < 0.54 * cv.contourArea(hull) or not 8 < rh < 62 or cw < 14 or cw < ch:
            continue
        if y > 88 or y + ch < 56 or x + cw < 86 or x > 273:
            continue
        region = np.zeros(valid.shape, np.uint8)
        cv.drawContours(region, [hull], 0, 1, cv.FILLED)
        core = cv.erode(region, np.ones((5, 5), np.uint8)).astype(bool) & valid
        strokes = (dist > 65) & core
        if strokes.sum() < 35 or strokes.any(axis=0).sum() < 8:
            continue
        pieces.append(hull)
    if not pieces:
        # At a matching body panel, locate the pair of longitudinal edges
        # enclosing the word first, then find the character run between them.
        choices = []
        for colorbin in np.argsort(np.bincount(bins))[::-1]:
            sel = samp[bins == colorbin]
            if len(sel) < 0.018 * len(samp) or len(choices) >= 4:
                break
            col = np.median(sel, axis=0)
            if any(np.max(abs(col - old)) < 48 for old in choices):
                continue
            choices.append(col)
        cand = []
        for col in choices:
            d = np.max(abs(patch.astype("float32") - col), axis=2)
            score = cv.blur(1 - np.minimum(d / 120, 1), (3, 3)).astype(np.float32)
            xs = np.arange(119, 241)
            slopes = np.arange(-32, 33, 2)[:, None, None]
            centers = np.arange(30, 114)[None, :, None]
            ys = np.rint(centers + slopes * (xs - 180) / 160).astype(int)
            contrast = (score[ys + 3, xs] - score[ys - 3, xs]).mean(axis=2)

            def line(scores, allowed):
                a, b = np.unravel_index(
                    np.argmax(np.where(allowed, scores, -2)), scores.shape
                )
                return (
                    float(centers[0, b, 0]),
                    float(slopes[a, 0, 0]),
                    float(scores[a, b]),
                )

            top = line(contrast, centers[:, :, 0] < 76)
            bottom = line(-contrast, (centers[:, :, 0] > max(70, top[0] + 11)))
            if min(top[2], bottom[2]) < 0.15:
                continue
            cols = np.arange(360)
            up = top[0] + top[1] * (cols - 180) / 160
            low = bottom[0] + bottom[1] * (cols - 180) / 160
            ys = (
                np.rint(up + np.linspace(0.12, 0.88, 13)[:, None] * (low - up))
                .astype(int)
                .clip(0, 143)
            )
            inside = score[ys, cols]
            backing = np.percentile(inside, 82, axis=0)
            gradient = backing - np.maximum(
                score[(up - 4).round().astype(int).clip(0, 143), cols],
                score[(low + 4).round().astype(int).clip(0, 143), cols],
            )
            ok = (backing > 0.55) & (gradient > 0.15) & (low - up > 6)
            merged = cv.morphologyEx(
                ok[None].astype("uint8"), cv.MORPH_CLOSE, np.ones((1, 11), np.uint8)
            )[0]
            runs = np.flatnonzero(np.diff(np.r_[0, merged, 0])).reshape(-1, 2)
            for left, right in runs:
                if (
                    left < 9
                    or right > 351
                    or left > 150
                    or right < 202
                    or right - left < 85
                ):
                    continue
                # Require interior ink along the line, not just a solid trim bar.
                strokes = (np.percentile(inside, 15, axis=0) < 0.38) & (backing > 0.6)
                if np.count_nonzero(strokes[left:right]) < 18:
                    continue
                left -= 6
                right += 6
                q = np.float32(
                    [
                        [
                            [left, up[left] - 3],
                            [right, up[right] - 3],
                            [right, low[right] + 3],
                            [left, low[left] + 3],
                        ]
                    ]
                )
                cand.append(
                    (min(top[2], bottom[2]), cv.perspectiveTransform(q, inv)[0])
                )
        return max(cand, key=lambda c: c[0])[1] if cand else None
    hull = cv.convexHull(np.vstack(pieces))
    x, y, cw, ch = cv.boundingRect(hull)
    if cw < 95 or ch < 11:
        return None
    # A shallow rim/character margin protects strokes that meet the outer contour.
    mask = np.zeros(valid.shape, np.uint8)
    cv.drawContours(mask, [hull], 0, 255, cv.FILLED)
    mask = cv.dilate(mask, np.ones((5, 5), np.uint8))
    p = cv.approxPolyDP(
        cv.findContours(mask, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE)[0][0], 1.6, True
    )
    return cv.perspectiveTransform(np.float32(p), inv)[:, 0]


def trajectory(frames, anchors, check=lambda: None, alternatives=None):
    result = np.empty((len(frames), 4, 2), np.float32)
    keys = sorted(anchors)
    for k in keys:
        result[k] = anchors[k]

    def walk(start, end, step, q=None):
        if q is None:
            q = anchors[start]
        for i in range(start + step, end + step, step):
            check()
            moved = follow(frames[i - step], frames[i], q)
            if moved is not None:
                q = moved
            yield i, q

    for i, q in walk(keys[0], 0, -1):
        result[i] = q
    for a, b in zip(keys, keys[1:]):
        for i, q in walk(a, b - 1, 1):
            result[i] = q
        # At near-vertical angles the rectangle fitter can label opposite
        # corners first in two successive sightings. Interpolating those
        # labels would collapse the entire mask midway between the anchors.
        target = result[b - 1] - result[b - 1].mean(axis=0)
        ordered = min(
            (
                np.roll(points, shift, axis=0)
                for points in (anchors[b], anchors[b][::-1])
                for shift in range(4)
            ),
            key=lambda points: np.square(points - points.mean(axis=0) - target).sum(),
        )
        for i, q in walk(b, a + 1, -1, ordered):
            if alternatives is not None:
                shared, _ = cv.intersectConvexConvex(result[i], q)
                if shared < 0.5 * min(cv.contourArea(result[i]), cv.contourArea(q)):
                    alternatives[i] = q.copy()
                    continue
            result[i] += (q - result[i]) * ((i - a) / (b - a))
    for i, q in walk(keys[-1], len(frames) - 1, 1):
        result[i] = q
    return result


def shot_paths(capture, first, end, cuts, samples, fps, check, *, multi=False):
    """Yield shot-local paths and alternative locations for independent appearances."""
    size = None
    period = max(1, round(fps * 5 / 6))
    boundaries = [first, *sorted(c for c in cuts if first < c < end), end]
    for start, stop in zip(boundaries, boundaries[1:]):
        by_track = {}
        spans = {}
        with tempfile.TemporaryFile() as gray_file:
            for i in range(start, stop):
                check()
                ok, image = capture.read()
                if not ok:
                    raise ValueError("Source ended during single-plate tracking")
                h, w = image.shape[:2]
                if size is None:
                    width = min(800, w)
                    size = (width, max(1, round(width * h / w)))
                    scale = np.array(size) / [w, h]
                view = cv.resize(image, size, interpolation=cv.INTER_AREA)
                gray_file.write(cv.cvtColor(view, cv.COLOR_BGR2GRAY).tobytes())
                if i not in samples:
                    continue
                # Match the geometry sampler to the original prototype;
                # optical flow above uses area resampling for fine texture.
                color = cv.resize(image, size)
                for track, polygons, lo, hi in samples[i]:
                    old_lo, old_hi = spans.get(track, (i, i + 1))
                    spans[track] = max(start, min(old_lo, lo)), min(
                        stop, max(old_hi, hi)
                    )
                    if not polygons:
                        continue
                    outline = _fit(color, [np.float32(p * scale) for p in polygons])
                    if (
                        outline is None
                        or np.any(outline < 4)
                        or np.any(outline > np.array(size) - 5)
                    ):
                        continue
                    rect = cv.minAreaRect(outline)
                    length, depth = sorted(rect[1], reverse=True)
                    if depth < 5 or not 2.2 < length / depth < 7:
                        continue
                    corners = cv.boxPoints(rect)
                    if np.linalg.norm(corners[1] - corners[0]) < np.linalg.norm(
                        corners[2] - corners[1]
                    ):
                        corners = np.roll(corners, -1, axis=0)
                    if corners[1, 0] < corners[0, 0]:
                        corners = np.roll(corners, 2, axis=0)
                    score = (
                        cv.contourArea(outline)
                        / (length * depth)
                        * min(1, length / 100)
                    )
                    anchors = by_track.setdefault(track, {})
                    key = i // period
                    if key not in anchors or score > anchors[key][0]:
                        anchors[key] = score, i - start, corners
            if not by_track:
                continue
            gray_file.flush()
            frames = np.memmap(
                gray_file,
                mode="r",
                dtype=np.uint8,
                shape=(stop - start, size[1], size[0]),
            )
            for track, anchors in by_track.items():
                begin, end = spans[track] if multi else (start, stop)
                points = {i + start - begin: q for _, i, q in anchors.values()}
                alternatives = {} if multi else None
                path = (
                    trajectory(
                        frames[begin - start : end - start], points, check, alternatives
                    )
                    / scale
                )
                extra = {begin + i: q / scale for i, q in (alternatives or {}).items()}
                yield track, begin, end, path, extra
            del frames


def assign_appearances(rows, fps, width, height, cuts, next_id):
    """Associate concurrent plates by predicted center and size within a shot."""
    from bisect import bisect_right
    from itertools import groupby

    def geometry(row):
        x, y, right, bottom = np.array(row.cbox) + [*row.aoff, *row.aoff]
        size = np.maximum([right - x, bottom - y], 1.0)
        margin = max(2.0, 0.05 * max(size))
        edge = min(x, y, width - right, height - bottom) <= margin
        return np.array([(x + right) / 2, (y + bottom) / 2]), size, edge

    active = {}
    bounds = {}
    cuts = sorted(cuts)
    shot = -1
    for frame, group in groupby(
        sorted(rows, key=lambda r: r.t_start), lambda r: round(r.t_start * fps)
    ):
        current_shot = bisect_right(cuts, frame)
        if current_shot != shot:
            active.clear()
            shot = current_shot
        group = list(group)
        observations = [geometry(r) for r in group]
        pairs = []
        for track, (when, center, size, velocity, at_edge) in list(active.items()):
            gap = frame - when
            last_prediction = center + velocity * (gap - 1)
            outside = np.any(last_prediction + size / 2 <= 0) or np.any(
                last_prediction - size / 2 >= [width, height]
            )
            if gap > max(1, round(0.6 * fps)) or (gap > 1 and (at_edge or outside)):
                if outside:
                    bounds[track][1] = when
                del active[track]
                continue
            predicted = center + velocity * gap
            for j, (point, dims, edge) in enumerate(observations):
                if gap > 1 and edge:
                    continue
                distance = np.linalg.norm(point - predicted) / max(max(size), max(dims))
                if distance < 1.5:
                    pairs.append(
                        (
                            distance + 0.25 * np.linalg.norm(np.log(dims / size)),
                            track,
                            j,
                        )
                    )
        matches = {}
        used = set()
        for _, track, j in sorted(pairs):
            if j not in matches and track not in used:
                matches[j] = track
                used.add(track)
        for j, row in enumerate(group):
            point, size, edge = observations[j]
            if j in matches:
                track = matches[j]
                when, center, _, velocity, _ = active[track]
                velocity = 0.25 * velocity + 0.75 * (point - center) / (frame - when)
            else:
                track = next_id
                next_id += 1
                velocity = np.zeros(2)
                bounds[track] = [frame if edge else None, None]
            bounds[track][1] = frame if edge else None
            active[track] = frame, point, size, velocity, edge
            row.track = track
    return next_id, bounds
