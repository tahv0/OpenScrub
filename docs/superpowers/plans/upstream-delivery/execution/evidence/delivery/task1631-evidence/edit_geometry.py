# Source editing only; never imports the application.
from pathlib import Path
p=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub/openscrub.py')
s=p.read_text().replace('import json\n','import json\nimport math\n',1)
helpers='''def _geometry_finite(values, size, stage, field):
    """Check ordinary scalar coordinates without coercing their arithmetic."""
    try:
        valid = len(values) == size and all(
            isinstance(values[i], (int, float, np.integer, np.floating))
            and math.isfinite(values[i]) for i in range(size))
    except (TypeError, ValueError, IndexError, OverflowError):
        valid = False
    if not valid:
        raise ValueError(f"render geometry {stage}: invalid {field}") from None


def _geometry_detections(detections, stage):
    for ordinal, d in enumerate(detections, 1):
        where = f"{stage} detection {ordinal}"
        _geometry_finite(d.cbox, 4, where, "cbox")
        if d.cbox[2] <= d.cbox[0] or d.cbox[3] <= d.cbox[1]:
            raise ValueError(f"render geometry {where}: invalid cbox extents")
        _geometry_finite(d.aoff, 2, where, "aoff")
        _geometry_finite((d.t_start,), 1, where, "t_start")
        _geometry_finite((d.t_end,), 1, where, "t_end")
        if d.t_end < d.t_start:
            raise ValueError(f"render geometry {where}: invalid t_end order")


def _geometry_preflight(detections, cum, bands, fps, pad, band_margin, stage):
    _geometry_detections(detections, stage)
    for field, value in (("fps", fps), ("pad", pad),
                         ("band_margin", band_margin)):
        _geometry_finite((value,), 1, stage, field)
    if fps <= 0:
        raise ValueError(f"render geometry {stage}: invalid fps")
    for field, trajectory in (("cum", cum), ("bands", bands)):
        try:
            length = len(trajectory)
        except TypeError:
            length = 0
        if not length:
            raise ValueError(f"render geometry {stage}: invalid {field}")
        for i in range(length):
            _geometry_finite(trajectory[i], 2, stage, f"{field} entry {i}")


def _geometry_box(d, ox, oy, pad, stage):
    # Shared by SDR/HDR: clipping or the drift cap must not hide overflow.
    try:
        dx, dy = ox - d.aoff[0], oy - d.aoff[1]
        _geometry_finite((dx, dy), 2, stage, "drift offset")
        distance = abs(dx) + abs(dy)
        _geometry_finite((distance,), 1, stage, "drift distance")
        drift = min(24.0, 0.05 * distance)
        px = pad + drift
        _geometry_finite((px,), 1, stage, "effective padding")
        pbox = (d.cbox[0] + ox, d.cbox[1] + oy,
                d.cbox[2] + ox, d.cbox[3] + oy)
        _geometry_finite(pbox, 4, stage, "translated box")
        box = (pbox[0] - px, pbox[1] - px, pbox[2] + px, pbox[3] + px)
        _geometry_finite(box, 4, stage, "padded box")
    except (OverflowError, FloatingPointError):
        raise ValueError(f"render geometry {stage}: invalid box arithmetic") from None
    return box, pbox, px


def _geometry_metadata(cap, stage):
    try:
        values = (cap.get(cv2.CAP_PROP_FRAME_WIDTH),
                  cap.get(cv2.CAP_PROP_FRAME_HEIGHT),
                  cap.get(cv2.CAP_PROP_FRAME_COUNT))
        _geometry_finite(values, 3, stage, "video dimensions/count")
        w, h, total = (int(value) for value in values)
        if w <= 0 or h <= 0 or total < 0:
            raise ValueError(f"render geometry {stage}: invalid video dimensions/count")
    except Exception:
        cap.release()
        raise
    return w, h, total


'''
s=s.replace('def blur_region(',helpers+'def blur_region(',1)
s=s.replace('    h, w = frame.shape[:2]\n    x1 = max(0, int(x1));', '    _geometry_finite((x1, y1, x2, y2), 4, "paint", "box")\n    h, w = frame.shape[:2]\n    x1 = max(0, int(x1));',1)
s=s.replace('    h, w = frame.shape[:2]\n    x1i, y1i', '    _geometry_finite((x1, y1, x2, y2), 4, "paint", "box")\n    _geometry_finite((pad_px,), 1, "paint", "padding")\n    h, w = frame.shape[:2]\n    x1i, y1i',1)
s=s.replace('    h, w = y.shape\n    x1 = max(0, int(x1));','    _geometry_finite((x1, y1, x2, y2), 4, "paint", "box")\n    h, w = y.shape\n    x1 = max(0, int(x1));',1)
s=s.replace('    h, w = y.shape\n    x1i, y1i','    _geometry_finite((x1, y1, x2, y2), 4, "paint", "box")\n    _geometry_finite((pad_px,), 1, "paint", "padding")\n    h, w = y.shape\n    x1i, y1i',1)
s=s.replace('    if coverage not in ("box", "concealed"):', '    _geometry_detections(dets, "coverage")\n    if coverage not in ("box", "concealed"):',1)
s=s.replace('    for d in dets:\n        if getattr(d, "dense", False)', '    for ordinal, d in enumerate(dets, 1):\n        if getattr(d, "dense", False)',1)
s=s.replace('per_track.setdefault(c.track, []).append(c)','per_track.setdefault(c.track, []).append((ordinal, c))',1)
s=s.replace('    for ds in per_track.values():\n        ds.sort', '    for entries in per_track.values():\n        ordinals = {id(d): ordinal for ordinal, d in entries}\n        ds = [d for _, d in entries]\n        ds.sort',1)
s=s.replace('            new.append((int(x1 - px), int(y1 - py),\n                        int(x2 + px), int(y2 + py)))', '''            expanded = (x1 - px, y1 - py, x2 + px, y2 + py)
            _geometry_finite(expanded, 4,
                             f"coverage detection {ordinals[id(ds[i])]}",
                             "expanded cbox")
            new.append(tuple(int(value) for value in expanded))''',1)
# Acquisition entry checks and guarded metadata conversion.
s=s.replace('    meta = cv2.VideoCapture(src)\n    w = int(meta.get(cv2.CAP_PROP_FRAME_WIDTH))\n    h = int(meta.get(cv2.CAP_PROP_FRAME_HEIGHT))\n    total = int(meta.get(cv2.CAP_PROP_FRAME_COUNT))', '    _geometry_preflight(detections, cum, bands, fps, pad, band_margin, "HDR")\n    meta = cv2.VideoCapture(src)\n    w, h, total = _geometry_metadata(meta, "HDR")',1)
s=s.replace('    cap = cv2.VideoCapture(src)\n    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))\n    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))\n    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))', '    _geometry_preflight(detections, cum, bands, fps, pad, band_margin, "SDR")\n    cap = cv2.VideoCapture(src)\n    w, h, total = _geometry_metadata(cap, "SDR")',1)
# Keep stable enabled-subset ordinals through deduplication without adding fields.
s=s.replace('    buckets = {}\n', '    ordinals = {id(d): i for i, d in enumerate(detections, 1)}\n    buckets = {}\n',2)
s=s.replace('        ox, oy = cum[min(idx, len(cum) - 1)]', '        ox, oy = cum[min(idx, len(cum) - 1)]\n        _geometry_finite((ox, oy), 2, f"frame {idx}", "cum")',2)
start=s.index('            drift = min(24.0', s.index('def render_hdr('))
end=s.index('\n        bx, by = bands',start)
s=s[:start]+'''            box, pbox, px = _geometry_box(
                d, ox, oy, pad, f"HDR detection {ordinals[id(d)]} frame {idx}")
            if d.poly:
                _blur_silhouette_yuv10(y, u, v, *box, _mode_for(d.category),
                                       d.poly, pbox, pad_px=px)
            else:
                _blur_yuv10(y, u, v, *box, _mode_for(d.category),
                            shape=("ellipse" if d.category == "face"
                                   and face_shape == "ellipse" else "rect"))
''' + s[end:]
start=s.index('            # drift allowance:',s.index('def render('))
end=s.index('            if preview:', start)
s=s[:start]+'''            (x1, y1, x2, y2), pbox, px = _geometry_box(
                d, ox, oy, pad, f"SDR detection {ordinals[id(d)]} frame {idx}")
''' + s[end:]
s=s.replace('        bx, by = bands[min(idx, len(bands) - 1)]', '        bx, by = bands[min(idx, len(bands) - 1)]\n        _geometry_finite((bx, by), 2, f"frame {idx}", "bands")',2)
s=s.replace('        def band(x1, y1_, x2, y2_):\n', '        def band(x1, y1_, x2, y2_):\n            _geometry_finite((x1, y1_, x2, y2_), 4, f"HDR frame {idx}", "band box")\n',1)
s=s.replace('        def band(x1, y1, x2, y2):\n', '        def band(x1, y1, x2, y2):\n            _geometry_finite((x1, y1, x2, y2), 4, f"SDR frame {idx}", "band box")\n',1)
s=s.replace('    dets_r = apply_coverage(state["detections"],', '    _geometry_preflight(state["detections"], state["cum"], state["bands"],\n                        state["fps"], args.pad, 25, "run_render")\n    dets_r = apply_coverage(state["detections"],',1)
p.write_text(s)
# New owning tests must be included in the sdist.
p=p.with_name('pyproject.toml'); s=p.read_text(); s=s.replace('    "test_openscrub.py",','    "test_openscrub.py",\n    "tests/test_render_geometry.py",'); p.write_text(s)
