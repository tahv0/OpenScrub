"""Web lifecycle of stop and continue: stopped phase, Continue, Cancel,
restart/crash recovery and docker-stop, driven through the real worker."""
import os
import threading
import time

import pytest

import openscrub
import openscrub_web as web
from openscrub_internal import scan_progress as sp
from test_assisted_letters_web import store  # noqa: F401  (fixture)
from test_scan_stop_continue import N, _write_video, _square, _Base

STOP = {"at": None, "job": None, "crash_at": None, "calls": 0}


class _Plate(_Base):
    def find(self, frame, scale):
        STOP["calls"] += 1
        if STOP["crash_at"] is not None and STOP["calls"] == STOP["crash_at"]:
            raise RuntimeError("synthetic detector crash")
        if STOP["at"] is not None and STOP["calls"] == STOP["at"]:
            assert _post(f"/api/jobs/{STOP['job']['id']}/stop_scan").status_code == 202
        return _square(frame)


@pytest.fixture
def scan_job(store, tmp_path, monkeypatch):
    monkeypatch.setenv("OPENSCRUB_NO_AUTOFETCH", "1")
    monkeypatch.setattr(openscrub, "PlateDetector", _Plate)
    monkeypatch.setattr(web, "load_custom_cats", lambda: [])
    monkeypatch.setattr(web, "load_model_select", lambda: {})
    monkeypatch.setattr(web, "ZONES_PATH", str(tmp_path / "zones.json"))
    STOP.update(at=None, job=None, crash_at=None, calls=0)

    def make(categories="plate"):
        video = str(tmp_path / "clip.avi")
        _write_video(video)
        job = web.new_job(video, {"categories": categories, "tile": "off"}, "clip.avi")
        STOP["job"] = job
        return job
    return make


def _post(url):
    with web.app.test_client() as client:
        response = client.post(url)
        response.get_data()
        response.close()
        return response


def _run_worker():
    web.WORK_Q.put(None)
    thread = threading.Thread(target=web.worker)
    thread.start()
    thread.join(30)
    assert not thread.is_alive(), "worker did not finish"
    # a scan that reached review starts a background thumbnail pass that
    # still owns the job's files for a moment
    deadline = time.monotonic() + 10
    while web.FILES.count and time.monotonic() < deadline:
        time.sleep(0.02)


def _progress(job):
    return os.path.join(job["dir"], sp.PROGRESS_NAME)


def _scan(job):
    web.enqueue(job, "scan")
    _run_worker()


def test_stop_then_continue_reaches_review_and_deletes_progress(scan_job):
    job = scan_job()
    STOP["at"] = 12
    _scan(job)
    public = web.job_public(job)
    assert public["phase"] == "stopped" and public["stopped_total"] == N
    assert 0 < public["stopped_frame"] < N and os.path.exists(_progress(job))
    STOP["at"] = None
    assert _post(f"/api/jobs/{job['id']}/continue").status_code == 200
    _run_worker()
    assert job["phase"] == "review", job.get("error")
    assert not os.path.exists(_progress(job))
    assert os.path.exists(os.path.join(job["dir"], "report.json"))


def test_stop_scan_is_refused_for_text_jobs(scan_job, monkeypatch):
    job = scan_job("plate")
    seen = {}

    def run_scan(args, cb=None, progress=None, **kw):
        seen["progress"] = progress
        seen["public"] = web.job_public(job)
        seen["stop"] = _post(f"/api/jobs/{job['id']}/stop_scan").status_code
        raise RuntimeError("stub")
    monkeypatch.setattr(openscrub, "run_scan", run_scan)
    job["options"]["categories"] = "name,plate"
    _scan(job)
    assert seen["progress"] is None and seen["stop"] == 409
    assert seen["public"]["stop_supported"] is False


def test_cancel_stopped_job_deletes_progress(scan_job):
    job = scan_job()
    STOP["at"] = 10
    _scan(job)
    assert job["phase"] == "stopped" and os.path.exists(_progress(job))
    assert _post(f"/api/jobs/{job['id']}/cancel").status_code == 200
    assert job["phase"] == "cancelled" and not os.path.exists(_progress(job))


def test_continue_twice_is_queued_once(scan_job):
    job = scan_job()
    STOP["at"] = 10
    _scan(job)
    assert _post(f"/api/jobs/{job['id']}/continue").status_code == 200
    assert _post(f"/api/jobs/{job['id']}/continue").status_code == 409
    assert web.WORK_Q.qsize() == 1
    _run_worker()
    assert job["phase"] == "review"


def test_changed_video_keeps_job_stopped_with_reason(scan_job):
    job = scan_job()
    STOP["at"] = 10
    _scan(job)
    _write_video(job["video"], changed_frame=30)
    _post(f"/api/jobs/{job['id']}/continue")
    _run_worker()
    assert job["phase"] == "stopped"
    assert job["error"] == ("Can't continue: the video file changed. Cancel the scan "
                            "and start it again.")
    assert os.path.exists(_progress(job))


def test_error_after_autosave_becomes_stopped(scan_job, monkeypatch):
    job = scan_job()
    now = [0.0]
    real = sp.ScanProgressControl

    class Fast(real):
        def __init__(self, *a, **kw):
            kw["autosave_seconds"] = 0.5
            kw["clock"] = lambda: now[0]
            super().__init__(*a, **kw)

        def autosave_due(self):
            now[0] += 0.3          # due every second frame
            return super().autosave_due()
    monkeypatch.setattr(sp, "ScanProgressControl", Fast)
    STOP["crash_at"] = 20
    _scan(job)
    assert job["phase"] == "stopped"
    assert job["error"].startswith("The scan stopped because of an error at ")
    assert "synthetic detector crash" in job["error"]
    assert web.job_public(job)["stopped_frame"] > 0


def test_rehydrate_registers_stopped_job_even_without_source(scan_job):
    job = scan_job()
    STOP["at"] = 10
    _scan(job)
    frame = job["stopped_frame"]
    os.remove(job["video"])
    web.JOBS.clear()
    web._rehydrate_jobs()
    again = web.JOBS[job["id"]]
    assert again["phase"] == "stopped" and again["stopped_frame"] == frame
    assert again["name"] == "clip.avi"
    assert again["error"].startswith("source video not found at " + job["video"])


def test_rehydrate_cleans_progress_of_completed_job_and_stage_files(scan_job):
    job = scan_job()
    _scan(job)
    assert job["phase"] == "review"
    sp.save(_progress(job), {"next_frame": 3, "total": N})
    with open(_progress(job) + ".stage", "wb") as handle:
        handle.write(b"half")
    web.JOBS.clear()
    web._rehydrate_jobs()
    assert web.JOBS[job["id"]]["phase"] == "review"
    assert not os.path.exists(_progress(job))
    assert not os.path.exists(_progress(job) + ".stage")


def test_watchdog_orphan_with_progress_becomes_stopped(scan_job):
    job = scan_job()
    STOP["at"] = 10
    _scan(job)
    job["phase"] = "scanning"                 # as if the worker died mid-continue
    web.WORKER.update(current=job["id"], thread=None)
    started = []
    original = web.start_worker
    web.start_worker = lambda: started.append(1)
    try:
        assert web.check_worker()
    finally:
        web.start_worker = original
    assert job["phase"] == "stopped" and "Continue scan" in job["error"]


def test_sigterm_stops_running_scan_before_lock(scan_job, monkeypatch):
    job = scan_job()
    result = {}

    class Slow(_Plate):
        def find(self, frame, scale):
            if STOP["calls"] == 8 and "stopped" not in result:
                result["stopped"] = web.stop_scan_for_shutdown(timeout=0.0)
            return super().find(frame, scale)
    monkeypatch.setattr(openscrub, "PlateDetector", Slow)
    _scan(job)
    assert job["phase"] == "stopped" and os.path.exists(_progress(job))


def test_retry_deletes_stale_progress(scan_job):
    job = scan_job()
    sp.save(_progress(job), {"next_frame": 3, "total": N})
    job["phase"] = "error"
    assert _post(f"/api/jobs/{job['id']}/retry").status_code == 200
    _run_worker()
    assert job["phase"] == "review" and not os.path.exists(_progress(job))


def test_page_has_stop_continue_controls():
    page = web.PAGE
    for text in ("Stop the scan and free the GPU. Continue later from this point.",
                 "Stopping…", "Continue scan", "Cancel scan",
                 "Progress is saved in the\n    job folder. Continue scan carries on from here",
                 "Cancel throws away the scanning done so far. Use Stop to continue later.",
                 "Cancel throws away the saved progress of this scan.",
                 '"/stop_scan"', '"/continue"', 'title="Continue scan"'):
        assert text in page, text
    start = page.index("async function cancelJob(")
    assert "confirm(" in page[start:page.index("\n}\n", start)]
