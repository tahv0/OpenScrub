"""Four-corner plate redaction regressions.

Run: pytest -q test_plate_quad.py
"""
import json

import numpy as np
import openscrub


def test_quad_mask_preserves_background_and_tight_corners():
    frame = np.full((90, 140, 3), 211, dtype=np.uint8)
    box = (25., 25., 115., 60.)
    # Trapezoid, perspective-skewed plate. Background inside the outer
    # detection rectangle must remain untouched.
    quad = ((0.05, 0.30), (0.90, 0.05), (0.95, 0.65), (0.04, 0.82))
    pts = openscrub._plate_quad_pixels(box, quad)
    openscrub.blur_silhouette(
        frame, min(p[0] for p in pts)-2, min(p[1] for p in pts)-2,
        max(p[0] for p in pts)+2, max(p[1] for p in pts)+2,
        "box", (quad,), box, pad_px=1)
    assert (frame[42, 75] == 0).all()  # middle of the plate
    assert (frame[27, 25] == 211).all()  # unneeded outer bbox area
    assert (frame[42, 122] == 211).all()  # beyond the plate


def test_quad_coordinates_can_extend_beyond_detector_box():
    box = (40., 30., 80., 48.)
    quad = ((-0.2, 0.1), (1.1, 0.0), (1.2, 1.1), (-0.1, 1.0))
    points = openscrub._plate_quad_pixels(box, quad)
    assert points[0][0] == 32.
    assert points[2][0] == 88.
    assert round(points[2][1], 3) == 49.8


def test_plate_corners_survive_report_roundtrip(tmp_path):
    path = tmp_path / "report.json"
    quad = [[0.1, 0.2], [0.9, 0.1], [1.0, 0.8], [0.0, 0.9]]
    path.write_text(json.dumps({
        "provenance": {},
        "render_state": {"fps": 30, "cum": [[0, 0]], "bands": [[0, 0]]},
        "detections": [
            {"t_start": 0, "t_end": 1, "cbox": [10, 10, 60, 25],
             "category": "plate", "text": "plate", "confidence": 1,
             "plate_quad": quad, "enabled": True},
            {"t_start": 0, "t_end": 1, "cbox": [70, 10, 120, 25],
             "category": "plate", "text": "plate", "confidence": 1,
             "enabled": False}
        ]}), encoding="utf-8")
    detections, _, _ = openscrub.load_report(str(path))
    assert len(detections) == 1
    assert detections[0].plate_quad == tuple(tuple(p) for p in quad)
