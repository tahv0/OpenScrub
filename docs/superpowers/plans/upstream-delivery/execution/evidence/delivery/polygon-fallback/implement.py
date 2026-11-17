from pathlib import Path
root=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
p=root/'openscrub.py'
s=p.read_text()
helper='''def _silhouette_mask(polys, poly_box, x1i, y1i, rw, rh):
    """Rasterize usable contours, or request the caller's known-box fallback.

    Validate before int32 conversion; out-of-box coordinates remain legal for
    OpenCV clipping. Noncollinearity uses exact integer arithmetic rather than
    signed contour area, which can be zero for usable self-intersections.
    """
    if polys is None:
        return None
    mask = np.zeros((rh, rw), np.uint8)
    try:
        pbx1, pby1, pbx2, pby2 = map(float, poly_box)
        if not all(math.isfinite(v) for v in (pbx1, pby1, pbx2, pby2)):
            return None
        if pbx2 <= pbx1 or pby2 <= pby1:
            return None
        pbw, pbh = max(1.0, pbx2 - pbx1), max(1.0, pby2 - pby1)
        if not math.isfinite(pbw) or not math.isfinite(pbh):
            return None
        for pts in polys:
            points = np.asarray(pts, dtype=np.float64)
            if points.shape == (0,):  # existing empty-component behaviour
                continue
            if points.ndim != 2 or points.shape[1] != 2 or not np.isfinite(points).all():
                return None
            if len(points) < 3:
                continue
            vertices = []
            for qx, qy in points:
                px = float(qx) * pbw + pbx1
                py = float(qy) * pbh + pby1
                if not math.isfinite(px) or not math.isfinite(py):
                    return None
                vx, vy = int(round(px)) - x1i, int(round(py)) - y1i
                if not (-2147483648 <= vx <= 2147483647 and
                        -2147483648 <= vy <= 2147483647):
                    return None
                vertices.append((vx, vy))
            ax, ay = vertices[0]
            second = next((v for v in vertices[1:] if v != (ax, ay)), None)
            if second is None:
                return None
            bx, by = second
            if not any((bx - ax) * (cy - ay) != (by - ay) * (cx - ax)
                       for cx, cy in vertices):
                return None
            cv2.fillPoly(mask, [np.array(vertices, np.int32)], 255)
    except (TypeError, ValueError, OverflowError):
        return None
    except cv2.error as exc:
        if exc.code not in (cv2.Error.StsBadArg, cv2.Error.StsOutOfRange,
                            cv2.Error.StsAssert):
            raise
        return None
    return mask if mask.any() else None


'''
s=s.replace('import json\n', 'import json\nimport math\n', 1)
s=s.replace('def blur_silhouette(',helper+'def blur_silhouette(',1)
for hdr in (False,True):
 start=s.index('    if not polys:\n',s.index('def _blur_silhouette_yuv10(' if hdr else 'def blur_silhouette('))
 end=s.index('    if pad_px > 0:',start)
 fallback='_blur_yuv10(y, u, v, x1, y1, x2, y2, mode)' if hdr else 'blur_region(frame, x1, y1, x2, y2, mode)'
 s=s[:start]+'''    rw, rh = x2i - x1i, y2i - y1i
    mask = _silhouette_mask(polys, poly_box, x1i, y1i, rw, rh)
    if mask is None:
        '''+fallback+'''     # fail closed over the known region
        return
'''+s[end:]
p.write_text(s)
