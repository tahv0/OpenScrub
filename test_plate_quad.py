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
             "plate_quad": quad, "verified_label": "plate", "enabled": True},
            {"t_start": 0, "t_end": 1, "cbox": [70, 10, 120, 25],
             "category": "plate", "text": "plate", "confidence": 1,
             "enabled": False}
        ]}), encoding="utf-8")
    detections, _, _ = openscrub.load_report(str(path))
    assert len(detections) == 1
    assert detections[0].plate_quad == tuple(tuple(p) for p in quad)
    assert detections[0].verified_label == "plate"


def test_local_export_uses_review_labels_not_time_sampling(tmp_path):
    import cv2  # Used to write the synthetic annotation crop below.
    from scripts.prepare_plate_dataset import export
    jobs = tmp_path / "jobs"
    job = jobs / "job1"
    job.mkdir(parents=True)
    video = job / "input.mp4"
    out = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"),
                          5, (120, 80))
    for i in range(15):
        frame = np.full((80, 120, 3), 90+i, np.uint8)
        cv2.rectangle(frame, (20, 30), (60, 39), (225, 200, 195), -1)
        out.write(frame)
    out.release()
    ann = job / "plate_annotations"
    ann.mkdir()
    crop = np.full((40, 80, 3), 180, np.uint8)
    cv2.rectangle(crop, (12, 14), (65, 25), (255, 255, 255), -1)
    assert cv2.imwrite(str(ann / "quad.jpg"), crop)
    (ann / "annotations.jsonl").write_text(json.dumps({
        "verified_by_user": True, "image": "quad.jpg", "detection_index": 0,
        "corners": [[.15,.35],[.81,.35],[.81,.63],[.15,.63]]
    }) + "\n", encoding="utf-8")
    detections = [
        {"category": "plate", "t_start": 0, "last_seen": 0.2,
         "cbox": [20,30,60,40], "verified_label": "plate",
         "plate_quad": [[0,0],[1,0],[1,1],[0,1]], "track": 1},
        {"category": "plate", "t_start": 1, "last_seen": 1.1,
         "cbox": [20,30,60,40], "verified_label": "not_plate",
         "track": 2, "confidence": .98},
        {"category": "plate", "t_start": 2, "last_seen": 2.1,
         "cbox": [20,30,60,40], "enabled": True, "track": 3}
    ]
    (job / "report.json").write_text(json.dumps({
        "provenance": {"input": str(video)},
        "render_state": {"fps": 5, "cum": [[0,0]]*15},
        "detections": detections
    }), encoding="utf-8")
    target = tmp_path / "exported"
    stats = export(jobs, target, "segment", val_ratio=0,
                   negative_ratio=2, dedup_hamming=0)
    assert stats["positive"] == 1
    assert stats["negative"] == 1
    manifest = [json.loads(s) for s in
                (target / "manifest.jsonl").read_text().splitlines()]
    assert {s["quality"] for s in manifest} == {
        "human_quad", "human_hard_negative"}
    labels = list((target / "labels" / "train").glob("*.txt"))
    assert len(labels) == 2
    assert len([p for p in labels if p.read_text().strip()]) == 1
