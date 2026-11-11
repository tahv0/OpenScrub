"""Reusable model API, exact-frame inference and preserved review lifecycle."""
import copy
import importlib.util
import io
import json
from pathlib import Path
import threading

import cv2
import numpy as np
import pytest

import openscrub_web as web
import openscrub
import learning_session
import stop_review
import video_learning
from test_learned_models import library, model_bytes, accepted_job


@pytest.fixture
def model_app(tmp_path, monkeypatch):
    root = tmp_path / "different-recipient-layout" / "jobs"
    root.mkdir(parents=True)
    monkeypatch.setattr(web, "JOBS_DIR", str(root))
    monkeypatch.setattr(web, "JOBS", {})
    monkeypatch.setattr(web, "TOKEN", None)
    monkeypatch.setattr(web, "vault_locked", lambda: False)
    return web.app.test_client(), root


def _saved(root, tmp_path):
    return library().save_model(root / "learned_plate_models",
                                accepted_job(tmp_path / "training"),
                                "Garage camera", "Evening lighting")


def _video(path, frames=12):
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"),
                             10, (96, 64))
    assert writer.isOpened()
    for index in range(frames):
        frame = np.full((64, 96, 3), 60 + index, np.uint8)
        cv2.rectangle(frame, (24, 24), (70, 40), (210, 210, 210), -1)
        writer.write(frame)
    writer.release()
    return path


def _report(path, frames=6):
    return {
        "provenance": {"input": str(path),
                       "input_sha256": openscrub.sha256_file(str(path))},
        "render_state": {"fps": 10., "cum": [[0., 0.]] * frames,
                         "bands": [[0., 0.]] * frames},
        "detections": [{
            "t_start": .2, "t_end": .3, "last_seen": .2, "frame_index": 2,
            "cbox": [24, 24, 70, 40], "category": "plate", "text": "plate",
            "confidence": .99, "aoff": [0, 0], "dense": True,
            "track": 1, "enabled": True,
        }],
    }


def test_library_endpoint_starts_empty(model_app):
    client, _ = model_app
    response = client.get("/api/jobs/learned-models")
    assert response.status_code == 200
    assert response.get_json() == {"models": []}


def test_ui_routes_save_export_import_without_activating_a_job(model_app, tmp_path):
    client, root = model_app
    source = accepted_job(tmp_path / "accepted")
    job = web.new_job(str(source / "unrelated-video.mp4"), {}, "Other recording.mp4")
    (Path(job["dir"]) / "report.json").write_text(
        (source / "report.json").read_text(), encoding="utf-8")
    # Use the authoritative job report with artifacts inside its own directory.
    import shutil
    shutil.copytree(source / "learning", Path(job["dir"]) / "learning")
    doc = json.loads((Path(job["dir"]) / "report.json").read_text())
    doc["learning"]["active"]["model"] = str(
        Path(job["dir"]) / "learning" / Path(doc["learning"]["active"]["model"]).relative_to(source / "learning"))
    (Path(job["dir"]) / "report.json").write_text(json.dumps(doc), encoding="utf-8")
    job["phase"] = "review"
    response = client.post("/api/jobs/" + job["id"] + "/learned-models",
                           json={"name": "Workshop daylight", "description": "Camera A"})
    assert response.status_code == 200, response.get_data(as_text=True)
    saved = response.get_json()["model"]
    exported = client.get("/api/jobs/learned-models/" + saved["id"] + "/export")
    assert exported.status_code == 200
    imported = client.post("/api/jobs/learned-models/import",
                           data={"model": (io.BytesIO(exported.data), "renamed.openscrub-model")},
                           content_type="multipart/form-data")
    assert imported.status_code == 200, imported.get_data(as_text=True)
    assert imported.get_json()["model"]["model_sha256"] == saved["model_sha256"]
    assert job["options"].get("learned_plate_model", "") == ""
    assert not (Path(job["dir"]) / "plate_model").exists()


def test_selected_model_is_pinned_and_runs_on_an_unrelated_video(model_app, tmp_path):
    _, root = model_app
    selected = _saved(root, tmp_path)
    src = _video(tmp_path / "another-drive" / "renamed.mp4")
    job = web.new_job(str(src), {"categories": "plate",
                                "learned_plate_model": selected["id"]}, src.name)
    manifest, data = library().load_snapshot(job["dir"])
    assert manifest["model_sha256"] == selected["model_sha256"]
    assert data == model_bytes()
    args = web.build_args(job)
    assert args.plate_learning_exact is True
    original = _report(src)
    assert hasattr(web, "apply_selected_plate_model"), "Selected models never reach the scan"
    result = web.apply_selected_plate_model(job, original)
    assert result["refinement"]["model_sha256"] == selected["model_sha256"]
    assert result["refinement"]["inference"]["model_calls"] == 1
    assert result["refinement"]["inference"]["decoded_frames"] == 6
    assert result["detections"][0]["enabled"] is True
    assert "learning" not in result  # Not a fabricated local training pass.
    assert original == _report(src)


def test_unselected_scan_has_no_model_side_effects(model_app, tmp_path):
    _, root = model_app
    _saved(root, tmp_path)
    src = _video(tmp_path / "plain.mp4")
    job = web.new_job(str(src), {"categories": "plate"}, src.name)
    original = _report(src)
    assert hasattr(web, "apply_selected_plate_model"), "Inference selection hook is missing"
    assert web.apply_selected_plate_model(job, original) is original
    assert not (Path(job["dir"]) / "plate_model").exists()


def test_invalid_selected_id_does_not_create_or_queue_job(model_app, monkeypatch, tmp_path):
    client, root = model_app
    queued = []
    monkeypatch.setattr(web.WORK_Q, "put", queued.append)
    response = client.post("/api/jobs",
        data={"options": json.dumps({"learned_plate_model": "../outside"}),
              "video": (io.BytesIO(b"not decoded"), "clip.mp4")},
        content_type="multipart/form-data")
    assert response.status_code == 400
    assert not queued and not web.JOBS
    assert not list(root.glob("????????????"))


def test_library_is_excluded_from_job_retention(model_app, tmp_path):
    _, root = model_app
    selected = _saved(root, tmp_path)
    web.retention_sweep(-1)
    assert library().list_models(root / "learned_plate_models")[0]["id"] == selected["id"]


@pytest.mark.parametrize("method,path", [
    ("get", "/api/jobs/learned-models"),
    ("post", "/api/jobs/learned-models/import"),
    ("get", "/api/jobs/learned-models/" + "a" * 32 + "/export"),
    ("delete", "/api/jobs/learned-models/" + "a" * 32),
])
def test_model_routes_follow_vault_lock(model_app, monkeypatch, method, path):
    client, _ = model_app
    monkeypatch.setattr(web, "vault_locked", lambda: True)
    assert getattr(client, method)(path).status_code == 423


def test_render_keeps_model_identity_and_application_counts(tmp_path):
    src = _video(tmp_path / "render-source.mp4")
    before = _report(src)
    before["refinement"] = {"id": "a" * 32, "name": "Camera",
                            "model_sha256": "b" * 64, "threshold": .9,
                            "inference": {"model_calls": 1, "refined": 1}}
    rendered = copy.deepcopy(before)
    rendered.pop("refinement")
    result = learning_session.preserve_render_review(before, rendered)
    assert result.get("refinement") == before["refinement"]


def test_real_refiner_stops_at_paused_scan_boundary(tmp_path):
    src = _video(tmp_path / "longer-than-checkpoint.mp4", frames=12)
    report = _report(src, frames=6)
    model = video_learning.CropRefiner(model_bytes(), providers=["CPUExecutionProvider"])
    refined, stats = video_learning.refine_report(src, report, model, threshold=.9)
    assert stats["decoded_frames"] == 6
    assert stats["model_calls"] == 1
    assert len(refined["render_state"]["cum"]) == 6


def test_deleting_library_model_does_not_break_recovered_job(model_app, tmp_path):
    _, root = model_app
    selected = _saved(root, tmp_path)
    src = _video(tmp_path / "source.mp4")
    job = web.new_job(str(src), {"categories": "plate",
                                "learned_plate_model": selected["id"]}, src.name)
    assert hasattr(web, "apply_selected_plate_model"), "Selected inference is missing"
    report = web.apply_selected_plate_model(job, _report(src))
    report = stop_review.with_checkpoint(report, 6, 12, job["options"])
    stop_review.atomic_report(str(Path(job["dir"]) / "report.json"), report)
    library().delete_model(root / "learned_plate_models", selected["id"])
    jid = job["id"]
    web.JOBS.clear()
    web.rehydrate_jobs()
    restored = web.JOBS[jid]
    assert restored["phase"] == "paused"
    assert web.build_args(restored).plate_learning_exact is True
    manifest, _ = library().load_snapshot(restored["dir"])
    assert manifest["model_sha256"] == selected["model_sha256"]


def test_worker_refines_fresh_chunks_before_merge_and_preserves_review(model_app, tmp_path, monkeypatch):
    _, root = model_app
    selected = _saved(root, tmp_path)
    src = _video(tmp_path / "worker.mp4")
    job = web.new_job(str(src), {"categories": "plate",
                                "learned_plate_model": selected["id"]}, src.name)
    calls = []
    def scan(args, cb):
        continuing = bool(getattr(args, "resume_start", 0))
        # A short checkpoint can resume at zero due to its 1-second overlap.
        continuing = len(calls) > 0
        calls.append(args)
        frames = 12 if continuing else 6
        doc = _report(src, frames)
        if continuing:
            doc["detections"][0].update(t_start=.8, t_end=.9, last_seen=.8, frame_index=8)
        return {"cum": doc["render_state"]["cum"], "stats": {},
                "stop_at_frame": None if continuing else 6,
                "total_frames": 12, "_doc": doc}
    def write(path, args, state):
        Path(path).write_text(json.dumps(state["_doc"]), encoding="utf-8")
    monkeypatch.setattr(openscrub, "run_scan", scan)
    monkeypatch.setattr(openscrub, "write_report", write)
    class Once:
        def __init__(self, action): self.items = iter([(job["id"], action)])
        def get(self): return next(self.items)
        def task_done(self): pass
    def run(action):
        monkeypatch.setattr(web, "WORK_Q", Once(action))
        with pytest.raises(StopIteration):
            web.worker()
    run("scan")
    assert job["phase"] == "paused", job.get("error")
    path = Path(job["dir"]) / "report.json"
    report = json.loads(path.read_text())
    assert report.get("refinement", {}).get("inference", {}).get("model_calls") == 1
    assert calls[0].plate_learning_exact is True
    edited = copy.deepcopy(report["detections"][0])
    edited.update(enabled=False, verified_label="not_plate",
                  plate_quad=[[0., 0.], [1., 0.], [1., 1.], [0., 1.]])
    report["detections"][0] = edited
    stop_review.atomic_report(str(path), report)
    run("resume")
    assert job["phase"] == "review", job.get("error")
    final = json.loads(path.read_text())
    assert final["detections"][0] == edited
    assert final["detections"][1]["frame_index"] == 8
    assert final["refinement"]["inference"]["model_calls"] == 1
    assert calls[1].plate_learning_exact is True
