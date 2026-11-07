"""Regression tests for the four-corner plate editor and saved review geometry."""
import json
import threading

import cv2
import numpy as np
import pytest

import openscrub_web as web


@pytest.fixture
def plate_job(tmp_path, monkeypatch):
    jid = "plateeditorfixture"
    job_dir = tmp_path / jid
    job_dir.mkdir()
    video = job_dir / "input.mp4"
    writer = cv2.VideoWriter(
        str(video), cv2.VideoWriter_fourcc(*"mp4v"), 10, (240, 160))
    assert writer.isOpened()
    for k in range(10):
        frame = np.full((160, 240, 3), 110, np.uint8)
        cv2.rectangle(frame, (50, 75), (125, 90), (245, 245, 245), -1)
        writer.write(frame)
    writer.release()
    doc = {
        "provenance": {"input": str(video)},
        "render_state": {"fps": 10, "cum": [[0, 0]] * 10,
                         "bands": [[0, 0]] * 10},
        "detections": [
            {"t_start": 0.0, "t_end": 0.8, "last_seen": 0.2,
             "cbox": [45, 67, 137, 103], "category": "plate",
             "text": "plate", "confidence": 0.95,
             "enabled": True, "track": 2, "dense": True}
        ]
    }
    report = job_dir / "report.json"
    report.write_text(json.dumps(doc), encoding="utf-8")
    job = {
        "id": jid, "name": "input.mp4", "dir": str(job_dir),
        "video": str(video), "phase": "review",
        "cancel": threading.Event(), "stop": threading.Event(),
        "options": {}, "stats": {},
    }
    monkeypatch.setitem(web.JOBS, jid, job)
    monkeypatch.setattr(web, "TOKEN", None)
    return web.app.test_client(), jid, report, job_dir


def test_plate_editor_metadata_and_magnified_image(plate_job):
    client, jid, report, job_dir = plate_job
    endpoint = "/api/jobs/%s/plate_quad/0" % jid
    response = client.get(endpoint)
    assert response.status_code == 200
    data = response.get_json()
    assert data["box"] == [45, 67, 137, 103]
    assert data["width"] == 240 and data["height"] == 160
    assert data["points"] == [[45, 67], [137, 67],
                               [137, 103], [45, 103]]
    x1, y1, x2, y2 = data["crop"]
    assert 0 <= x1 < 45 < 137 < x2 <= 240
    assert 0 <= y1 < 67 < 103 < y2 <= 160
    image_response = client.get(endpoint + "/frame")
    assert image_response.status_code == 200
    assert image_response.mimetype == "image/jpeg"
    assert image_response.headers["Cache-Control"] == "no-store"
    decoded = cv2.imdecode(np.frombuffer(image_response.data, np.uint8),
                           cv2.IMREAD_COLOR)
    assert decoded.shape[:2] == (y2-y1, x2-x1)
    assert decoded.shape[:2] != (160, 240)


def test_four_corner_drag_save_creates_verified_sample(plate_job):
    client, jid, report, job_dir = plate_job
    endpoint = "/api/jobs/%s/plate_quad/0" % jid
    new_points = [[54., 77.], [126., 74.], [129., 91.], [52., 94.]]
    response = client.post(endpoint, json={
        "points": new_points, "apply_track": False})
    assert response.status_code == 200, response.get_json()
    assert response.get_json()["verified_samples_added"] == 1
    saved = json.loads(report.read_text(encoding="utf-8"))["detections"][0]
    assert saved["verified_label"] == "plate"
    assert len(saved["plate_quad"]) == 4
    assert saved["plate_quad"][0][0] == pytest.approx((54-45)/92, abs=1e-6)
    labels = job_dir / "plate_annotations" / "annotations.jsonl"
    assert labels.is_file()
    entries = [json.loads(line) for line in labels.read_text().splitlines()]
    assert len(entries) == 1 and entries[0]["verified_by_user"] is True
    assert (labels.parent / entries[0]["image"]).is_file()


def test_bowtie_or_outside_corners_rejected_without_saving(plate_job):
    client, jid, report, job_dir = plate_job
    endpoint = "/api/jobs/%s/plate_quad/0" % jid
    before = report.read_text(encoding="utf-8")
    crossed = [[54, 75], [132, 95], [54, 95], [132, 75]]
    response = client.post(endpoint, json={"points": crossed})
    assert response.status_code == 400
    outside = [[-1, 3], [110, 3], [110, 15], [3, 15]]
    response = client.post(endpoint, json={"points": outside})
    assert response.status_code == 400
    assert report.read_text(encoding="utf-8") == before
    assert not (job_dir / "plate_annotations").exists()


def test_plate_editor_requires_plate_category(plate_job):
    client, jid, report, job_dir = plate_job
    assert client.get("/api/jobs/%s/plate_quad/3" % jid).status_code == 404
    assert client.get("/api/jobs/%s/plate_quad/3/frame" % jid).status_code == 404
