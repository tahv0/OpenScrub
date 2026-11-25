"""A failed render keeps the review: the job says which step failed, a full
disk is explained, and the page offers Retry render, not only a new scan."""
import errno
import threading

import openscrub
import openscrub_web as web
from test_assisted_letters_web import store  # noqa: F401  (fixture)


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
    thread.join(8)
    assert not thread.is_alive(), "worker did not finish"


def _fail_with(monkeypatch, error):
    def run_pipeline(args, cb=None):
        raise error
    monkeypatch.setattr(openscrub, "run_pipeline", run_pipeline)


def test_disk_full_render_is_marked_as_a_render_failure(store, monkeypatch):
    job = store("full")
    _fail_with(monkeypatch, OSError(errno.ENOSPC, "No space left on device"))
    assert _post(f"/api/jobs/{job['id']}/render").status_code == 200
    _run_worker()
    public = web.job_public(job)
    assert public["phase"] == "error" and public["failed_action"] == "render"
    assert "disk is full" in public["error"]
    assert "Retry render" in public["error"] and "review choices are kept" in public["error"]
    # the server already accepts a render of a failed job: Retry render works
    assert _post(f"/api/jobs/{job['id']}/render").status_code == 200
    assert job.get("failed_action") is None          # cleared when the job is queued again
    _run_worker()


def test_ffmpeg_disk_full_text_is_recognised(store, monkeypatch):
    job = store("full")
    _fail_with(monkeypatch, RuntimeError("ffmpeg failed: av_interleaved_write_frame(): "
                                         "No space left on device"))
    _post(f"/api/jobs/{job['id']}/render")
    _run_worker()
    assert "disk is full" in job["error"] and web.job_public(job)["failed_action"] == "render"


def test_other_render_errors_get_no_disk_hint(store, monkeypatch):
    job = store("full")
    _fail_with(monkeypatch, RuntimeError("synthetic encoder failure"))
    _post(f"/api/jobs/{job['id']}/render")
    _run_worker()
    assert job["error"] == "synthetic encoder failure"
    assert web.job_public(job)["failed_action"] == "render"


def test_failed_scan_is_marked_as_a_scan_failure(store, monkeypatch):
    job = store("full")
    job["phase"] = "error"
    _fail_with(monkeypatch, OSError(errno.ENOSPC, "No space left on device"))

    def run_scan(*args, **kwargs):
        raise OSError(errno.ENOSPC, "No space left on device")
    monkeypatch.setattr(openscrub, "run_scan", run_scan)
    assert _post(f"/api/jobs/{job['id']}/retry").status_code == 200
    _run_worker()
    assert web.job_public(job)["failed_action"] == "scan"
    assert "Retry scan" in job["error"] and "Retry render" not in job["error"]


def test_page_offers_retry_render_and_guards_a_rescan():
    page = web.PAGE
    assert "Retry render" in page and "Back to review" in page
    assert 'failed_action==="render"' in page
    assert "retryRender(" in page
    # starting the scan over after a failed render replaces the review: ask first
    assert "discards your review choices" in page and "use Retry render instead" in page
    start = page.index("async function retryJob(")
    body = page[start:page.index("\n}\n", start)]
    assert "confirm(" in body
