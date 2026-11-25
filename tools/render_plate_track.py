"""Render one plate from reviewed corner observations using local optical flow.

Usage: python tools/render_plate_track.py source.mp4 observations.json output.mp4
Each JSON entry has a zero-based frame and four clockwise corner points in
source pixels, starting at the same physical corner in every observation.
Coordinates may extend beyond the image. Intended for short constant-rate clips.
"""
import argparse
import json
import subprocess

import cv2
import numpy as np


# Support direct execution from a source checkout.
if __package__ in (None, ''):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from openscrub_internal.plate_outline import follow


def trajectory(frames, anchors):
    result = np.empty((len(frames), 4, 2), np.float32)
    keys = sorted(anchors)
    for k in keys:
        result[k] = anchors[k]
    def walk(start, end, step):
        q = anchors[start]
        for i in range(start + step, end + step, step):
            moved = follow(frames[i-step], frames[i], q)
            if moved is not None:
                q = moved
            yield i, q
    for i, q in walk(keys[0], 0, -1):
        result[i] = q
    for a, b in zip(keys, keys[1:]):
        for i, q in walk(a, b-1, 1):
            result[i] = q
        for i, q in walk(b, a+1, -1):
            result[i] += (q - result[i]) * ((i-a)/(b-a))
    for i, q in walk(keys[-1], len(frames)-1, 1):
        result[i] = q
    return result


def visible_strip(frame, quad, previous=None, *, adaptive=False):
    """Fit two plate boundaries in perspective-corrected track coordinates."""
    width, height = 192, 64
    corners = np.float32([[0, 10], [width-1, 10], [width-1, 53], [0, 53]])
    warp = cv2.getPerspectiveTransform(quad.astype(np.float32), corners)
    patch = cv2.warpPerspective(frame, warp, (width, height))
    if adaptive:
        # Sample the backing and the surround along the tracked plate's short
        # axis. Geometry fixes the search area even on a matching body panel.
        # Comparing colors along their measured difference also handles a dark
        # backing or colors with similar luminance.
        h, w = frame.shape[:2]
        if np.any(quad < 0) or np.any(quad >= [w, h]):
            return None
        surround = np.median(patch[4:10, 24:168], axis=(0, 1))
        interior = patch[32:47, 24:168].astype(np.float32)
        distances = np.linalg.norm(interior - surround, axis=2)
        backing = np.median(interior[distances >= np.percentile(distances, 65)], axis=0)
        direction = backing - surround
        separation = np.linalg.norm(direction)
        if separation < 24:
            return None
        patch = (patch.astype(np.float32) - surround.astype(np.float32)) @ (
            direction.astype(np.float32) / separation)
    # Fit a line to the dark/light boundary across the lettering. A single
    # character or mounting screw can interrupt it over only a few columns.
    x = np.arange(20, 181)
    delta = np.arange(-10, 11)[:, None, None]
    offsets = np.arange(6, 56)[None, :, None]
    y = np.rint(offsets + delta * (x - 96) / 191).astype(int)
    smooth = cv2.blur(patch, (3, 3)).astype(np.float32)
    contrast = (smooth[y + 2, x] - smooth[y - 2, x]).mean(axis=2)
    def edge(score):
        slope_index, offset_index = np.unravel_index(score.argmax(), score.shape)
        center = offset_index + 6
        tilt = slope_index - 10
        return np.array([center - tilt / 2, center + tilt / 2])
    # Search for the top in the upper portion of the tracked observation.
    # The bright baseline below the digits also produces a rising edge.
    ceiling = 33
    if previous is not None:
        # When perspective pushes the lamp boundary past the initial search
        # window, follow it a few rows farther in rectified plate coordinates.
        previous_center = 10 + 43 * previous[:, 0].mean()
        ceiling = max(ceiling, previous_center + 4)
    upper_scores = np.where(offsets[:, :, 0] <= ceiling, contrast, -np.inf)
    upper = edge(upper_scores)
    # Require the lower edge to be below the upper edge across the strip.
    allowed = offsets[:, :, 0] > upper.mean() + 5
    lower_scores = np.where(allowed, -contrast, -np.inf)
    lower = edge(lower_scores)
    ends = np.column_stack((upper, lower))
    if adaptive:
        # Require a coherent pair of long, opposing plate boundaries. If the
        # crop contains only bodywork, keep the reviewed outline as fallback.
        if min(upper_scores.max(), lower_scores.max()) < 12:
            return None
    if np.min(lower - upper) < 3:
        return None
    return (ends - 10) / 43


def lettering_path(frames, path, *, adaptive=False):
    bounds = []
    for frame, quad in zip(frames, path):
        bounds.append(visible_strip(frame, quad, bounds[-1] if bounds else None, adaptive=adaptive))
    result = path.copy()
    for i, quad in enumerate(path):
        if adaptive and bounds[i] is None:
            continue
        nearby = [b for b in bounds[max(0, i-2):i+3] if b is not None]
        if not nearby:
            continue
        ends = np.median(nearby, axis=0)
        for side, lower in ((0, 3), (1, 2)):
            edge = quad[lower] - quad[side]
            result[i, side] = quad[side] + edge * (ends[side, 0] - .075)
            result[i, lower] = quad[side] + edge * (ends[side, 1] + .025)
    return result


def paint(image, quad, lettering=False):
    quad = quad.mean(axis=0) + (quad - quad.mean(axis=0)) * (1.0 if lettering else 1.07)
    points = np.rint(quad).astype(np.int32)
    x, y, w, h = cv2.boundingRect(points)
    left, top = max(x-8, 0), max(y-8, 0)
    roi = image[top:max(0, y+h+8), left:max(0, x+w+8)]
    if not roi.size:
        return
    mask = np.zeros(roi.shape[:2], np.uint8)
    cv2.fillConvexPoly(mask, points - [left, top], 255)
    if not lettering:
        mask = cv2.dilate(mask, np.ones((9, 9), np.uint8))
    # Use the full plate scale even if only a sliver is on camera.
    edges = np.linalg.norm(np.roll(quad, -1, axis=0) - quad, axis=1)
    cell = max(8, round(min(edges) * .8), round(max(edges) / 5) if lettering else 0)
    tiny = cv2.resize(roi, (max(1, roi.shape[1] // cell), max(1, roi.shape[0] // cell)),
                      interpolation=cv2.INTER_AREA)
    blurred = cv2.resize(tiny, (roi.shape[1], roi.shape[0]), interpolation=cv2.INTER_LINEAR)
    roi[mask != 0] = blurred[mask != 0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'observations', 'output'):
        parser.add_argument(name)
    parser.add_argument('--ffmpeg', default='ffmpeg')
    parser.add_argument('--light-plate-strip', action='store_true',
                        help='fit the visible lettering strip on a light-backed plate')
    parser.add_argument('--adaptive-plate-strip', action='store_true',
                        help='use plate geometry and locally measured colors for the lettering strip')
    parser.add_argument('--scene-cut', type=int, action='append', default=[],
                        help='first frame of a new shot (repeatable)')
    args = parser.parse_args()
    cap = cv2.VideoCapture(args.source)
    width, height, fps = [cap.get(p) for p in (3, 4, 5)]
    if min(width, height, fps) <= 0:
        raise ValueError('Cannot read source')
    size = (800, round(800 * height / width))
    scale = np.array(size) / [width, height]
    with open(args.observations) as file:
        anchors = {row['frame']: np.asarray(row['points'], np.float32) * scale
                   for row in json.load(file)}
    frames = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frames.append(cv2.cvtColor(cv2.resize(frame, size, interpolation=cv2.INTER_AREA),
                                    cv2.COLOR_BGR2GRAY))
    cap.release()
    if not anchors or any(k < 0 or k >= len(frames) or q.shape != (4, 2)
                          or not np.isfinite(q).all() for k, q in anchors.items()):
        raise ValueError('Invalid plate observations')
    cuts = sorted(set(args.scene_cut))
    if any(index <= 0 or index >= len(frames) for index in cuts):
        parser.error('scene cuts must be inside the clip')
    paths = []
    for start, stop in zip([0, *cuts], [*cuts, len(frames)]):
        local = {i - start: quad for i, quad in anchors.items() if start <= i < stop}
        if not local:
            parser.error(f'no plate observation for shot starting on frame {start}')
        paths.append(trajectory(frames[start:stop], local))
    path = np.concatenate(paths)
    if args.adaptive_plate_strip:
        def color_frames():
            reader = cv2.VideoCapture(args.source)
            try:
                for _ in path:
                    ok, frame = reader.read()
                    if not ok:
                        raise ValueError('Source ended during plate color sampling')
                    yield cv2.resize(frame, size, interpolation=cv2.INTER_AREA)
            finally:
                reader.release()
        path = lettering_path(color_frames(), path, adaptive=True)
    elif args.light_plate_strip:
        path = lettering_path(frames, path)
    path = path / scale
    del frames
    cap = cv2.VideoCapture(args.source)
    command = [args.ffmpeg, '-loglevel', 'error', '-n', '-f', 'rawvideo', '-pix_fmt', 'bgr24',
               '-s', f'{int(width)}x{int(height)}', '-r', str(fps), '-i', '-',
               '-i', args.source, '-map', '0:v', '-map', '1:a?', '-c:v', 'libx264',
               '-preset', 'veryfast', '-crf', '19', '-pix_fmt', 'yuv420p', '-c:a', 'copy',
               '-movflags', '+faststart', args.output]
    with subprocess.Popen(command, stdin=subprocess.PIPE) as proc:
        try:
            for q in path:
                ok, frame = cap.read()
                if not ok:
                    raise ValueError('Source ended during second pass')
                paint(frame, q, args.light_plate_strip or args.adaptive_plate_strip)
                proc.stdin.write(frame.tobytes())
        finally:
            cap.release()
            proc.stdin.close()
        if proc.wait():
            raise RuntimeError('Video encoding failed')


if __name__ == '__main__':
    main()
