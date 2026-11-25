"""Recover a lettering strip inside a detector crop from a plate rim and glyphs."""
import cv2
import numpy as np


def lettering(crop):
    """Return a crop-local polygon only when both rim and character evidence agree."""
    h, w = crop.shape[:2]
    if min(h, w) < 12:
        return None
    scale = min(1.0, 320 / max(w, h))
    size = (max(1, round(w * scale)), max(1, round(h * scale)))
    image = cv2.resize(crop, size, interpolation=cv2.INTER_AREA)
    height, width = image.shape[:2]
    # Use the color channel with the greatest robust contrast. Opposite ink
    # polarities then give the same contour candidates.
    values = np.percentile(image[::2, ::2], [10, 90], axis=(0, 1))
    channel = image[:, :, np.argmax(values[1] - values[0])]
    _, mask = cv2.threshold(channel, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    for contour in sorted(contours, key=cv2.contourArea, reverse=True):
        area = cv2.contourArea(contour)
        if area < .09 * height * width:
            break
        perimeter = cv2.arcLength(contour, True)
        vertices = cv2.approxPolyDP(contour, .025 * perimeter, True)
        if len(vertices) != 4 or not cv2.isContourConvex(vertices):
            continue
        quad = vertices[:, 0].astype(np.float32)
        lengths = np.linalg.norm(quad - np.roll(quad, -1, axis=0), axis=1)
        if lengths[0] + lengths[2] < lengths[1] + lengths[3]:
            quad = np.roll(quad, -1, axis=0)
            lengths = np.roll(lengths, -1)
        length, depth = (lengths[0] + lengths[2]) / 2, (lengths[1] + lengths[3]) / 2
        if not (depth >= 5 and 1.7 * depth < length < 15 * depth):
            continue
        # The candidate must account for the detector's location in both axes.
        if np.any(np.ptp(quad, axis=0) < np.array([width, height]) * .49):
            continue
        target = np.float32([[0, 0], [159, 0], [159, 39], [0, 39]])
        transform = cv2.getPerspectiveTransform(quad, target)
        patch = cv2.warpPerspective(channel, transform, (160, 40))
        _, ink = cv2.threshold(patch, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
        if np.median(ink[3:-3, 3:-3]) > 0:
            ink = 255 - ink
        # Discard the rim before counting glyphs. A lamp or panel can have
        # four strong edges but seldom has a row of character-sized components.
        ink[:2] = ink[-2:] = 0
        ink[:, :2] = ink[:, -2:] = 0
        _, _, stats, _ = cv2.connectedComponentsWithStats(ink)
        glyphs = [(x, y, x + bw, y + bh) for x, y, bw, bh, a in stats[1:]
                  if 2 <= bw <= 38 and 9 <= bh <= 36 and a >= 12]
        if len(glyphs) < 3:
            continue
        centers = [(y1 + y2) / 2 for _, y1, _, y2 in glyphs]
        if np.ptp(centers) > 16 or max(g[2] for g in glyphs) - min(g[0] for g in glyphs) < 55:
            continue
        # Retain both ends: a clipped/connected glyph may not be a component.
        top = max(0, min(g[1] for g in glyphs) - 4)
        bottom = min(39, max(g[3] for g in glyphs) + 4)
        strip = np.float32([[[0, top], [159, top], [159, bottom], [0, bottom]]])
        mapped = cv2.perspectiveTransform(strip, cv2.getPerspectiveTransform(target, quad))[0]
        return mapped * [w / width, h / height]
    return None


def _patch_translation(previous, current, points):
    """Estimate translation on builds with imgproc but without LK or calib3d."""
    h, w = previous.shape
    radius, search = 4, 24
    shifts = []
    for px, py in np.rint(points[:40, 0]).astype(int):
        if not (radius <= px < w-radius and radius <= py < h-radius):
            continue
        patch = previous[py-radius:py+radius+1, px-radius:px+radius+1]
        if patch.std() < 6:
            continue
        left, top = max(0, px-search-radius), max(0, py-search-radius)
        region = current[top:py+search+radius+1, left:px+search+radius+1]
        scores = cv2.matchTemplate(region, patch, cv2.TM_CCOEFF_NORMED)
        _, score, _, (x, y) = cv2.minMaxLoc(scores)
        if score >= .85:
            shifts.append((left+x+radius-px, top+y+radius-py))
    if len(shifts) < 5:
        return None
    shifts = np.asarray(shifts)
    median = np.median(shifts, axis=0)
    agreeing = shifts[np.linalg.norm(shifts-median, axis=1) <= 2]
    if len(agreeing) < max(5, .6*len(shifts)):
        return None
    return np.float32(np.median(agreeing, axis=0))


def follow(previous, current, quad):
    """Estimate motion from plate and nearby visible features in a local window."""
    h, w = current.shape
    lo = np.maximum(np.floor(quad.min(axis=0) - 65).astype(int), 0)
    hi = np.minimum(np.ceil(quad.max(axis=0) + 65).astype(int), [w, h])
    x, y = lo
    right, bottom = hi
    if right - x < 12 or bottom - y < 12:
        return None
    a, b = previous[y:bottom, x:right], current[y:bottom, x:right]
    # Points near the lettering follow its depth plane; distant bumper,
    # sleeve or ground features may move in a different direction.
    support = np.zeros(a.shape, np.uint8)
    cv2.fillConvexPoly(support, np.rint(quad - lo).astype(np.int32), 255)
    support = cv2.dilate(support, np.ones((29, 29), np.uint8))
    points = cv2.goodFeaturesToTrack(a, 180, .012, 4, mask=support)
    if points is None or len(points) < 5:
        return None
    flow = getattr(cv2, "calcOpticalFlowPyrLK", None)
    fit_affine = getattr(cv2, "estimateAffinePartial2D", None)
    if flow is None or fit_affine is None:
        shift = _patch_translation(a, b, points)
        if shift is None:
            return None
        prediction = quad + shift
    else:
        moved, ok, _ = flow(a, b, points, None)
        back, valid, _ = flow(b, a, moved, None)
        keep = (ok.ravel() & valid.ravel()).astype(bool)
        keep &= np.linalg.norm((back - points)[:, 0], axis=1) < 1.2
        if keep.sum() < 5:
            return None
        matrix, inliers = fit_affine(
            points[keep] + lo, moved[keep] + lo, ransacReprojThreshold=2)
        if (matrix is None or inliers.sum() < max(5, keep.sum() * .55)
                or not .80 < np.linalg.det(matrix[:, :2]) < 1.25):
            return None
        prediction = cv2.transform(quad[None], matrix)[0]
    # Nearby features can vote consistently for a foreground hand. Check the
    # appearance of the plate itself where both frames have visible pixels.
    target = np.float32([[0, 0], [47, 0], [47, 15], [0, 15]])
    def patch(frame, points):
        warp = cv2.getPerspectiveTransform(np.float32(points), target)
        return cv2.warpPerspective(frame.astype(np.float32), warp, (48, 16), borderValue=-256)
    before, after = patch(a, quad - lo), patch(b, prediction - lo)
    visible = (before >= 0) & (after >= 0)
    if visible.sum() < 24 or np.mean(np.abs(before[visible] - after[visible])) > 36:
        return None
    return prediction


def adjacent_letters(image, seed):
    """Look beyond a truncated word for adjacent backing carrying more strokes."""
    quad = np.float32(seed)
    if np.linalg.norm(quad[1] - quad[0]) < np.linalg.norm(quad[2] - quad[1]):
        quad = np.roll(quad, -1, axis=0)
    target = np.float32([[140, 56], [279, 56], [279, 87], [140, 87]])
    transform = cv2.getPerspectiveTransform(quad, target)
    patch = cv2.warpPerspective(image, transform, (420, 144), borderValue=(127, 127, 127))
    sample = patch[60:84, 150:269].reshape(-1, 3)
    # Estimate the backing from the most populated color bin inside the word.
    bins = (sample // 32).astype(int) @ [64, 8, 1]
    backing = np.median(sample[bins == np.bincount(bins).argmax()], axis=0)
    distance = np.max(np.abs(patch.astype(np.float32) - backing), axis=2)
    mask = np.uint8(distance < 60) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 7), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    inverse = cv2.getPerspectiveTransform(target, quad)
    results = []
    seed_long, seed_short = sorted(cv2.minAreaRect(quad)[1], reverse=True)
    for contour in contours:
        area = cv2.contourArea(contour)
        if not 160 < area < 14000:
            continue
        x, y, w, h = cv2.boundingRect(contour)
        if (w < 15 or h < 9 or w < h or w > 340 or h > 95
                or x > 293 or x + w < 126 or y > 89 or y + h < 54
                or (x >= 137 and x + w <= 282)):
            continue
        hull = cv2.convexHull(contour)
        # A same-colored bumper may be continuous with the plate in the
        # threshold image. Refuse an extension thicker than the lettering band.
        if min(cv2.minAreaRect(hull)[1]) > 47 or area < .47 * cv2.contourArea(hull):
            continue
        region = np.zeros(mask.shape, np.uint8)
        cv2.drawContours(region, [hull], 0, 1, cv2.FILLED)
        # Test for strokes specifically in the part OUTSIDE the original word.
        interior = cv2.erode(region, np.ones((5, 5), np.uint8)).astype(bool)
        interior[:, 140:280] = False
        strokes = (distance > 65) & interior
        if strokes.sum() < 20 or np.count_nonzero(strokes.any(axis=0)) < 5:
            continue
        outline = cv2.approxPolyDP(hull, 1.6, True).astype(np.float32)
        if len(outline) >= 3:
            mapped = cv2.perspectiveTransform(outline, inverse)[:, 0]
            length, depth = sorted(cv2.minAreaRect(mapped)[1], reverse=True)
            if length <= 2.6 * seed_long and depth <= 1.55 * seed_short:
                results.append(mapped)
    return results


def edge_fragment(image, seed):
    """Recover the visible backing where the tracked strip meets the image edge."""
    height, width = image.shape[:2]
    seed = np.float32(seed)
    length, depth = sorted(cv2.minAreaRect(seed)[1], reverse=True)
    if depth < 3 or length < 1.7 * depth:
        return None
    lo = np.maximum(0, np.floor(seed.min(axis=0) - 2 * depth)).astype(int)
    hi = np.minimum([width, height], np.ceil(seed.max(axis=0) + 2 * depth)).astype(int)
    if np.all(lo > 0) and np.all(hi < [width, height]):
        return None
    if min(hi-lo) < 3:
        return None
    roi = image[lo[1]:hi[1], lo[0]:hi[0]]
    scale = min(1., 240 / max(roi.shape[:2]))
    roi = cv2.resize(roi, (max(1, round(roi.shape[1] * scale)),
                           max(1, round(roi.shape[0] * scale))), interpolation=cv2.INTER_AREA)
    q = np.float32((seed - lo) * scale)
    region = np.zeros(roi.shape[:2], np.uint8)
    cv2.fillConvexPoly(region, np.rint(q).astype(np.int32), 1)
    sample = roi[region != 0]
    if len(sample) < 9:
        return None
    bins = (sample // 32).astype(int) @ [64, 8, 1]
    backing = np.median(sample[bins == np.bincount(bins).argmax()], axis=0)
    distance = np.max(np.abs(roi.astype(np.float32) - backing), axis=2)
    mask = np.uint8(distance < 60) * 255
    kernel = max(3, int(depth * scale * .22) | 1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((kernel, kernel), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for contour in sorted(contours, key=cv2.contourArea, reverse=True):
        x, y, w, h = cv2.boundingRect(contour)
        touches = ((lo[0] == 0 and x == 0) or (lo[1] == 0 and y == 0)
                   or (hi[0] == width and x+w == roi.shape[1])
                   or (hi[1] == height and y+h == roi.shape[0]))
        if not touches:
            continue
        hull = cv2.convexHull(contour)
        long, short = sorted(cv2.minAreaRect(hull)[1], reverse=True)
        if not (.22 * depth * scale < short < 1.65 * depth * scale
                and .22 * length * scale < long < 2.35 * length * scale):
            continue
        area = cv2.contourArea(hull)
        shared, _ = cv2.intersectConvexConvex(np.float32(hull), q)
        if shared < .16 * min(area, cv2.contourArea(q)) or area-shared < .025 * area:
            continue
        # Include the thin rim and strokes splitting the backing at the edge.
        rim = np.zeros_like(region)
        cv2.drawContours(rim, [hull], 0, 255, cv2.FILLED)
        margin = max(3, int(.16 * depth * scale) | 1)
        rim = cv2.dilate(rim, np.ones((margin, margin), np.uint8))
        outline, _ = cv2.findContours(rim, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        return cv2.approxPolyDP(cv2.convexHull(outline[0]), .8, True)[:, 0] / scale + lo
    return None


class StripTracker:
    """Follow observed lettering between independent per-frame detections."""

    def __init__(self):
        self.frame = None
        self.index = -2
        self.tracks = []

    @staticmethod
    def _gray(image):
        height, width = image.shape[:2]
        size = (min(800, width), max(1, round(height * min(800, width) / width)))
        gray = cv2.cvtColor(cv2.resize(image, size, interpolation=cv2.INTER_AREA),
                            cv2.COLOR_BGR2GRAY)
        return gray, np.array(size) / [width, height]

    def restore(self, state, image, index):
        self.frame, _ = self._gray(image)
        self.index = index
        for points, last in state:
            q = np.asarray(points, np.float32)
            if (q.shape != (4, 2) or not np.isfinite(q).all()
                    or not cv2.isContourConvex(q) or type(last) is not int or not 0 <= last <= index):
                raise ValueError("invalid saved plate motion")
            self.tracks.append((q, last))

    def step(self, image, index, rows, letters, fps, cut, allowed):
        height, width = image.shape[:2]
        gray, scale = self._gray(image)
        moved = []
        if not cut and index == self.index + 1:
            for old, last in self.tracks:
                if index - last > max(1, round(.8 * fps)):
                    continue
                quad = follow(self.frame, gray, old)
                if quad is not None:
                    moved.append((quad, last))
        self.frame, self.index, self.tracks = gray, index, []
        output = []
        viewport = np.float32([[0, 0], [width, 0], [width, height], [0, height]])
        screen = np.float32(viewport * scale)
        for row, polys in zip(rows, letters):
            x1, y1, x2, y2, _ = row
            box = np.float32([[x1, y1], [x2, y1], [x2, y2], [x1, y2]]) * scale
            polys = [np.clip(p, (x1, y1), (x2, y2)) for p in polys]
            matches = []
            for j, (quad, _) in enumerate(moved):
                overlap, _ = cv2.intersectConvexConvex(quad, box.astype(np.float32))
                visible, _ = cv2.intersectConvexConvex(quad, screen)
                if visible > 0 and overlap > .38 * min(visible, cv2.contourArea(box.astype(np.float32))):
                    matches.append(j)
            prediction = None
            if matches:
                # A merged detector box can contain several old candidates.
                # Re-seed on ambiguous matches; never fork those old tracks.
                if len(matches) == 1:
                    prediction = moved[matches[0]][0]
                for j in reversed(matches):
                    moved.pop(j)
            # Keep a single strip as the motion anchor. A collapsed OCR word
            # cannot replace the whole moving plate, but a broader new reading
            # can reacquire it. Original detector polygons are always retained.
            candidates = [np.asarray(p * scale, np.float32) for p in polys if len(p) == 4]
            measured = max(candidates, key=cv2.contourArea, default=None)
            if measured is not None and not cv2.isContourConvex(measured):
                measured = None
            if measured is not None:
                extensions = adjacent_letters(image, measured / scale)
                if extensions:
                    polys.extend(extensions)
                    # Carry the full observed span across future misses. Keep
                    # the perspective quad when a new contour adds no length.
                    combined = np.vstack([measured, *(p * scale for p in extensions)]).astype(np.float32)
                    extent = cv2.minAreaRect(combined)
                    if max(extent[1]) > 1.09 * max(cv2.minAreaRect(measured)[1]):
                        measured = cv2.boxPoints(extent)
            if prediction is not None and measured is not None:
                overlap, _ = cv2.intersectConvexConvex(prediction, measured)
                predicted_area = cv2.contourArea(prediction)
                measured_area = cv2.contourArea(measured)
                if overlap > .35 * measured_area and overlap < .90 * predicted_area:
                    polys.append(prediction / scale)
                # A detector crop ends at the picture boundary. Keep the
                # motion-tracked corners outside the picture until the strip
                # comes back into view. Clipping the anchor here changes its
                # size on every partial sighting.
                outside = np.any(prediction < 0) or np.any(prediction > screen[2])
                partial = outside and overlap >= .70 * measured_area
                if partial or measured_area < .83 * predicted_area:
                    measured = None
            anchor = measured if measured is not None else prediction
            if anchor is not None:
                fragment = edge_fragment(image, anchor / scale)
                if fragment is not None:
                    polys.append(fragment)
                self.tracks.append((anchor, index))
                if measured is None:
                    polys.append(anchor / scale)
                    polys.extend(adjacent_letters(image, anchor / scale))
            output.append((row, polys, True))
        for quad, last in moved:
            # A new detector observation supersedes overlapping carryovers.
            if any(cv2.intersectConvexConvex(quad, other)[0] >
                   .15 * min(cv2.contourArea(quad), cv2.contourArea(other))
                   for other, _ in self.tracks):
                continue
            points = quad / scale
            lo = np.maximum(points.min(axis=0), 0)
            hi = np.minimum(points.max(axis=0), [width, height])
            box = (*lo, *hi)
            if np.all(hi - lo >= 3) and allowed(box):
                polygons = [points, *adjacent_letters(image, points)]
                fragment = edge_fragment(image, points)
                if fragment is not None:
                    polygons.append(fragment)
                output.append(((*box, 0.), polygons, False))
                self.tracks.append((quad, last))
        # Keep virtual corners in tracker state. Intersect polygons at the
        # image boundary only for the rows handed to the scan/report renderer.
        for _, polys, _ in output:
            for i in range(len(polys) - 1, -1, -1):
                points = polys[i]
                if np.all(points >= 0) and np.all(points <= [width, height]):
                    continue
                area, visible = cv2.intersectConvexConvex(np.float32(points), viewport)
                if area > 0:
                    polys[i] = visible[:, 0]
                else:
                    polys.pop(i)
        return output


def reverse_strips(samples, capture, fps, first, cuts, cancelled):
    """Project later sightings onto earlier frames, using bounded blocks of grays.

    samples maps frame -> track -> (row, screen-space polygons). Return a
    template row and a screen-space polygon. The caller owns scope/row policy.
    """
    if not samples:
        return
    horizon = max(2, min(18, round(.45 * fps)))
    blocks = set()
    for idx in samples:
        blocks.add(idx // horizon)
        if idx >= horizon:
            blocks.add(idx // horizon - 1)
    cache = {}
    position = first
    stop = max(samples) + 1
    for block in sorted(blocks):
        start = max(first, block * horizon)
        end = min(stop, (block + 1) * horizon)
        if start >= end:
            continue
        cancelled()
        cache = {i: gray for i, gray in cache.items() if i >= start}
        while position < start:
            if position % 120 == 0:
                cancelled()
            if not capture.grab():
                return
            position += 1
        while position < min(end + horizon, stop):
            ok, image = capture.read()
            if not ok:
                return
            cache[position], scale = StripTracker._gray(image)
            position += 1
        future = {}
        for i in range(max(cache), start - 1, -1):
            observed = samples.get(i, {})
            if i + 1 in cuts:
                future.clear()
            for track in list(future):
                quad, row, when = future[track]
                if when - i > horizon:
                    del future[track]
                    continue
                projected = follow(cache[i + 1], cache[i], quad)
                if projected is None:
                    del future[track]
                    continue
                future[track] = projected, row, when
                if i < end:
                    yield i, observed.get(track, (None,))[0], row, projected / scale
            for track, (row, polys) in observed.items():
                if not polys:
                    continue
                seed = max(polys, key=cv2.contourArea)
                if len(seed) != 4:
                    seed = cv2.boxPoints(cv2.minAreaRect(seed))
                seed = np.float32(seed * scale)
                if not cv2.isContourConvex(seed):
                    continue
                prior = future.get(track)
                if prior is None or cv2.contourArea(seed) >= .93 * cv2.contourArea(prior[0]):
                    future[track] = seed, row, i


def continuous_mask(polygons):
    """Fill seams between overlapping estimates of the same lettering strip."""
    contours = [np.asarray(p, np.float32) for p in polygons]
    merged = []
    for p in contours:
        if cv2.isContourConvex(p):
            for i, other in enumerate(merged):
                if not cv2.isContourConvex(other):
                    continue
                shared, _ = cv2.intersectConvexConvex(p, other)
                area = cv2.contourArea(p)
                other_area = cv2.contourArea(other)
                if shared <= .55 * max(area, other_area):
                    continue
                hull = cv2.convexHull(np.vstack((p, other)))[:, 0]
                if cv2.contourArea(hull) <= 1.08 * (area + other_area - shared):
                    merged[i] = hull
                    break
            else:
                merged.append(p)
        else:
            merged.append(p)
    return [points.tolist() for points in merged]
