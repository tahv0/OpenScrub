"""Stop & Review regression tests. No model downloads or CUDA needed."""
import copy
import json
import os
import threading

import cv2
import numpy as np
import pytest

import openscrub
import stop_review


def doc_from(cum, detections=None, hash_value="video-hash", fps=30):
    return {
        "provenance": {"input": "/local/video.mp4", "input_sha256": hash_value,
                       "settings": {"categories": "plate"},
                       "original_input": "/local/original.mov",
                       "vfr_normalized": True},
        "render_state": {
            "fps": fps, "cum": [[float(i), 0] for i in range(cum)],
            "bands": [[0, 0] for _ in range(cum)]
        },
        "detections": detections or []
    }


def sample_plate():
    return {
        "t_start": 0.5, "t_end": 3.5, "last_seen": 2,
        "cbox": [10, 4, 28, 10], "category": "plate", "text": "plate",
        "track": 0, "person": -1, "dense": True, "enabled": False,
        "verified_label": "not_plate",
        "plate_quad": [[0, 0.3], [1, 0.1], [1, 0.9], [0, 1]],
        "confidence": 0.8,
    }


def test_pause_checkpoint_preserves_exact_frame_and_options():
    original = doc_from(90, [sample_plate()])
    options = {"categories": "plate", "windows": [{"t0": 0, "t1": 1}]}
    saved = stop_review.with_checkpoint(original, 90, 300, options)
    assert saved["stop_review"]["next_frame"] == 90
    assert saved["stop_review"]["total_frames"] == 300
    assert saved["stop_review"]["fps"] == 30
    assert saved["stop_review"]["options"] == options
    assert original.get("stop_review") is None
    assert saved["detections"][0]["plate_quad"] == sample_plate()["plate_quad"]
    assert stop_review.validate_resume(saved, "video-hash") == saved["stop_review"]


def test_resume_merges_timeline_and_never_loses_human_feedback():
    edited = sample_plate()
    old = stop_review.with_checkpoint(doc_from(90, [edited]), 90, 300,
                                       {"categories": "plate"})
    old["audio_redactions"] = [{"t0": 1, "t1": 2, "mode": "mute"}]
    new_plate = {
        **sample_plate(), "t_start": 3.03, "t_end": 8.0,
        "track": 0, "person": 0, "enabled": True,
        "plate_quad": [], "verified_label": ""}
    suffix = doc_from(180, [new_plate])
    for i in range(60, 180):
        suffix["render_state"]["cum"][i] = [float(1000+i), 0]
    merged = stop_review.join_reports(old, suffix, 180, 300, completed=False)
    assert merged["stop_review"]["next_frame"] == 180
    assert merged["render_state"]["cum"][89] == [89.0, 0]
    assert merged["render_state"]["cum"][90] == [1090.0, 0]
    assert merged["render_state"]["cum"][179] == [1179.0, 0]
    assert merged["detections"][0] == edited
    assert merged["detections"][1]["t_start"] >= 3.0
    assert merged["detections"][1]["track"] != edited["track"]
    assert merged["audio_redactions"] == old["audio_redactions"]
    assert merged["provenance"] == old["provenance"]
    completed = stop_review.join_reports(
        merged, doc_from(300, [new_plate]), 300, 300, completed=True)
    assert "stop_review" not in completed
    assert completed["detections"][0] == edited


def test_corrupt_or_different_video_refused():
    old = stop_review.with_checkpoint(doc_from(30), 30, 100, {})
    with pytest.raises(stop_review.CheckpointError, match="Source video changed"):
        stop_review.validate_resume(old, "different")
    bad = doc_from(80, [sample_plate()], hash_value="different")
    with pytest.raises(stop_review.CheckpointError, match="Source hash"):
        stop_review.join_reports(old, bad, 80, 100)
    with pytest.raises(stop_review.CheckpointError, match="frame count"):
        stop_review.join_reports(old, doc_from(80), 80, 102)


def test_no_progress_does_not_advance_checkpoint():
    old = stop_review.with_checkpoint(doc_from(60), 60, 150, {})
    with pytest.raises(stop_review.CheckpointError, match="did not advance"):
        stop_review.join_reports(old, doc_from(60), 60, 150)


def test_atomic_save_never_destroys_previous_checkpoint(tmp_path, monkeypatch):
    path = tmp_path / "report.json"
    before = stop_review.with_checkpoint(doc_from(60), 60, 150, {})
    stop_review.atomic_report(str(path), before)
    assert json.loads(path.read_text()) == before
    original_replace = stop_review.os.replace

    def failed_replace(*args):
        raise OSError("disk write interrupted")
    monkeypatch.setattr(stop_review.os, "replace", failed_replace)
    with pytest.raises(OSError, match="interrupted"):
        stop_review.atomic_report(str(path), doc_from(150))
    monkeypatch.setattr(stop_review.os, "replace", original_replace)
    assert json.loads(path.read_text()) == before
    assert not list(tmp_path.glob(".report-*.json"))


def make_video(path, seconds=6, fps=30):
    out = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"),
                          fps, (160, 90))
    assert out.isOpened()
    for i in range(seconds*fps):
        frame = np.zeros((90, 160, 3), dtype=np.uint8)
        cv2.putText(frame, str(i), (30, 50), cv2.FONT_HERSHEY_SIMPLEX,
                    0.5, (150, 200, 230), 1)
        out.write(frame)
    out.release()


class RequestStop(openscrub.Callbacks):
    def __init__(self):
        self.want_stop = False
    def log(self, m):
        pass
    def progress(self, stage, cur, total):
        if stage == "scan" and cur >= 90:
            self.want_stop = True
    def stop_requested(self):
        return self.want_stop


class Quiet(openscrub.Callbacks):
    def log(self, m):
        pass


def test_engine_stops_on_completed_frame_and_resume_seeks_without_prefix(
        tmp_path, monkeypatch):
    src = tmp_path / "clip.mp4"
    make_video(src)
    parser = openscrub.build_parser()
    def args(*extra):
        result = parser.parse_args([str(src), "--categories", "none",
                                    "--no-backtrack", "--scroll-track", "off",
                                    *extra])
        return openscrub._prep_args(result, parser)
    original = openscrub.run_scan(args(), RequestStop())
    assert 90 <= original["stop_at_frame"] <= 91
    assert original["total_frames"] == 180
    assert len(original["cum"]) == original["stop_at_frame"]
    report = tmp_path / "report.json"
    openscrub.write_report(str(report), args(), original)
    old = stop_review.with_checkpoint(json.loads(report.read_text()),
                                       original["stop_at_frame"], 180,
                                       {"categories": "none"})
    resumed = openscrub.run_scan(args("--resume-start", "2.0"), Quiet())
    assert resumed["stop_at_frame"] is None
    assert len(resumed["cum"]) == 180
    openscrub.write_report(str(report), args("--resume-start", "2.0"), resumed)
    result = stop_review.join_reports(old, json.loads(report.read_text()),
                                      180, 180, completed=True)
    assert result["render_state"]["fps"] == old["render_state"]["fps"]
    assert len(result["render_state"]["cum"]) == 180
    assert "stop_review" not in result


def test_web_stop_and_resume_routes_preserve_job_state(tmp_path, monkeypatch):
    import openscrub_web as web
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    source = job_dir / "input.mp4"
    source.write_bytes(b"source-video-checksum")
    checksum = openscrub.sha256_file(str(source))
    old = doc_from(30, hash_value=checksum)
    old["provenance"]["input"] = str(source)
    old = stop_review.with_checkpoint(old, 30, 100, {"categories": "none"})
    stop_review.atomic_report(str(job_dir / "report.json"), old)
    jid = "teststopreview"
    job = {"id": jid, "dir": str(job_dir), "video": str(source),
           "name": "clip.mp4", "options": {}, "phase": "paused",
           "progress": .5, "eta": None, "size": source.stat().st_size,
           "log": [], "error": None, "output": None,
           "created": 0, "cancel": threading.Event(), "stop": threading.Event(),
           "stats": {}}
    monkeypatch.setitem(web.JOBS, jid, job)
    monkeypatch.setattr(web, "TOKEN", None)
    client = web.app.test_client()
    # Partial report is not a legal output. Render must fail closed.
    assert client.post("/api/jobs/" + jid + "/render").status_code == 400
    assert client.post("/api/jobs/" + jid + "/stop").status_code == 409
    resp = client.post("/api/jobs/" + jid + "/resume")
    assert resp.status_code == 200
    assert resp.get_json()["next_frame"] == 30
    assert job["phase"] == "queued"
    assert job["options"] == {"categories": "none"}
    # No worker was started in this unit test; remove queued item.
    assert web.WORK_Q.get_nowait() == (jid, "resume")
    web.WORK_Q.task_done()
    job["phase"] = "scanning"
    assert client.post("/api/jobs/" + jid + "/stop").status_code == 200
    assert job["stop"].is_set()
    assert json.loads((job_dir / "report.json").read_text()) == old



def test_web_server_rehydrates_paused_checkpoint(tmp_path, monkeypatch):
    import openscrub_web as web
    root = tmp_path / "jobs"
    jdir = root / "recoveredjob"
    jdir.mkdir(parents=True)
    src = jdir / "input.mp4"
    src.write_bytes(b"sample-video")
    original = doc_from(45, hash_value=openscrub.sha256_file(str(src)))
    original["provenance"]["input"] = str(src)
    paused = stop_review.with_checkpoint(
        original, 45, 150,
        {"categories": "plate", "scan_speed": "thorough"})
    stop_review.atomic_report(str(jdir / "report.json"), paused)
    monkeypatch.setattr(web, "JOBS_DIR", str(root))
    with web.JOBS_LOCK:
        web.JOBS.pop("recoveredjob", None)
    web.rehydrate_jobs()
    try:
        job = web.JOBS["recoveredjob"]
        assert job["phase"] == "paused"
        assert job["options"]["scan_speed"] == "thorough"
        assert job["checkpoint_frame"] == 45
        assert job["checkpoint_total"] == 150
        assert isinstance(job["stop"], threading.Event().__class__)
        assert job["output"] is None
    finally:
        web.JOBS.pop("recoveredjob", None)


def test_paused_edits_cannot_mark_the_unscanned_tail(tmp_path, monkeypatch):
    import openscrub_web as web
    jid = "boundedreview"
    jdir = tmp_path / jid
    jdir.mkdir()
    src = jdir / "input.mp4"
    src.write_bytes(b"source")
    doc = doc_from(60, [sample_plate()],
                   hash_value=openscrub.sha256_file(str(src)))
    doc["provenance"]["input"] = str(src)
    paused = stop_review.with_checkpoint(doc, 60, 120, {})
    stop_review.atomic_report(str(jdir / "report.json"), paused)
    job = {"id": jid, "dir": str(jdir), "video": str(src),
           "phase": "paused", "stop": threading.Event(),
           "cancel": threading.Event(), "trackbg": {},
           "stats": {}, "options": {}}
    monkeypatch.setitem(web.JOBS, jid, job)
    monkeypatch.setattr(web, "TOKEN", None)
    client = web.app.test_client()
    bad = client.post("/api/jobs/" + jid + "/detections",
                      json={"manual": [{
                          "t_start": 4.0, "t_end": 5.0, "t_ref": 4.0,
                          "screen_box": [1, 1, 4, 4]}]})
    assert bad.status_code == 400
    assert json.loads((jdir / "report.json").read_text()) == paused
    allowed = client.post("/api/jobs/" + jid + "/detections",
                          json={"manual": [{
                              "t_start": 1.0, "t_end": 7.0, "t_ref": 1.0,
                              "screen_box": [1, 1, 4, 4]}]})
    assert allowed.status_code == 200
    saved = json.loads((jdir / "report.json").read_text())
    assert saved["detections"][-1]["t_end"] == 2.0
    assert saved["stop_review"]["next_frame"] == 60
