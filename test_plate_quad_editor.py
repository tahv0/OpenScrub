"""Regression tests for the four-corner plate editor and saved review geometry."""
import json
import shutil
import subprocess
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



def test_rotation_helpers_preserve_shape_and_reject_off_frame():
    """Run the actual browser geometry helpers in Node; no DOM or GPU."""
    if shutil.which("node") is None:
        pytest.skip("Node.js is not installed")
    source = web.APP_JS
    start = source.index("function plateQuadRotate(")
    end = source.index("let QEDIT=null;", start)
    helpers = source[start:end]
    script = helpers + """
const assert = require('node:assert/strict');
const original = [[40,40],[100,40],[100,60],[40,60]];
const rotated = plateQuadRotate(original, Math.PI/2, 140,140);
assert.ok(rotated && rotated.length===4);
const center = q=>q.reduce((p,c)=>[p[0]+c[0],p[1]+c[1]],[0,0]).map(v=>v/4);
const span = (q,i,j)=>Math.hypot(q[i][0]-q[j][0],q[i][1]-q[j][1]);
for(const pair of [[0,1],[1,2],[2,3],[3,0],[0,2]]) {
  assert.ok(Math.abs(span(original,...pair)-span(rotated,...pair))<1e-8);
}
assert.ok(center(original).every((v,i)=>Math.abs(v-center(rotated)[i])<1e-8));
assert.ok(Math.abs(rotated[0][0]-80)<1e-8);
assert.ok(Math.abs(rotated[0][1]-20)<1e-8);
const restored=plateQuadRotate(rotated,-Math.PI/2,140,140);
assert.ok(restored.every((p,k)=>p.every((v,j)=>Math.abs(v-original[k][j])<1e-8)));
const skewed=[[40,39],[102,35],[96,62],[38,64]];
const angled=plateQuadRotate(skewed,0.22,140,140);
assert.ok(angled && angled.length===4);
assert.ok(angled.some((p,k)=>Math.abs(p[0]-skewed[k][0])>1));
assert.equal(plateQuadRotate(original,Math.PI/2,70,70),null);
assert.equal(plateQuadRotate([[1,2]],.1,140,140),null);
assert.equal(plateQuadRotate(original,Infinity,140,140),null);
const h=plateQuadRotationHandle(original,[0,0,140,140],
                                {width:560,height:560});
assert.ok(h && h.x>=20 && h.x<=540 && h.y>=20 && h.y<=540);
console.log('rotation geometry OK');
"""
    result = subprocess.run(["node", "-e", script], capture_output=True,
                            text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr


def test_rotated_four_corners_save_as_normalized_polygon(plate_job):
    client, jid, report, _ = plate_job
    # Deliberately rotated and perspective-skewed, not axis-aligned.
    points = [[68, 51], [130, 74], [121, 103], [58, 84]]
    response = client.post("/api/jobs/%s/plate_quad/0" % jid,
                           json={"points": points})
    assert response.status_code == 200, response.get_json()
    stored = json.loads(report.read_text())["detections"][0]
    expected = [[(x-45)/92, (y-67)/36] for x,y in points]
    for p, q in zip(stored["plate_quad"], expected):
        assert p == pytest.approx(q, abs=1e-6)
    assert stored["verified_label"] == "plate"
