"""Retry a timed-out saved-picture decode without guessing source frames.

Synthetic 640x360 video only: same source-frame timestamp/box verification as
normal review. No user videos, reports, model files or drives are touched.
"""
import json
import subprocess

import numpy as np
import pytest
from werkzeug.exceptions import abort

import openscrub_web as web
from test_review_browser import review_server, browser_instance, load_browser_page


def _cold_review_row(report):
    doc = json.loads(report.read_text())
    # The scan saved group-0 JPEG at 300. Request an EXACT uncached source
    # frame 299: no cached neighbor may silently masquerade as frame 299.
    doc["detections"][0].update(
        frame_index=299, t_start=299/30, t_end=299/30,
        last_seen=299/30, track=-1
    report.write_text(json.dumps(doc))


def test_source_crop_decodes_exact_same_pixels_and_pts_as_full_frame(review_server):
    _, _report = review_server
    path = web.JOBS["inline-fixture"]["video"]
    crop = (181, 121, 417, 217)
    with web.app.test_request_context():
        full = web._read_exact_frame(path, 299)
        with web._REVIEW_CACHE_LOCK:
            web._REVIEW_FRAMES.clear()  # Exercise FFmpeg crop, not a warm full-frame slice.
        cropped = web._read_exact_frame(path, 299, crop=crop)
        assert full is not None
        assert cropped is not None
        x1, y1, x2, y2 = crop
        assert cropped.shape[:2] == (y2-y1, x2-x1)
        assert np.array_equal(cropped, full[y1:y2, x1:x2])
        assert cropped.shape[0] < full.shape[0]
        assert cropped.shape[1] < full.shape[1]


def test_uncached_exact_preview_is_cropped_and_retains_source_dimensions(
    review_server, monkeypatch
):
    _, report = review_server
    _cold_review_row(report)
    original = web._frame_at
    calls = []

    def traced(job, timestamp, rstate, frame_index=None, **kwargs):
        calls.append(dict(frame=frame_index, **kwargs))
        return original(job, timestamp, rstate, frame_index, **kwargs)

    monkeypatch.setattr(web, "_frame_at", traced)
    with web.app.test_client() as client:
        endpoint = "/api/jobs/inline-fixture/finding-preview/0"
        assert client.get(endpoint + "?exact=1&cache_only=1").status_code == 204
        image = client.get(endpoint + "?exact=1")
        assert image.status_code == 200, image.get_data(as_text=True)[:300]
        meta = json.loads(image.headers["X-Finding-Geometry"])
        assert meta["frame"] == meta["requested_frame"] == 299
        assert meta["width"] == 640
        assert meta["height"] == 360
        assert meta["source"]["timing"] == "frame"
        assert meta["classification_allowed"] is True
        assert len(calls) == 1
        assert calls[0]["frame"] == 299
        assert calls[0]["crop"] == tuple(meta["crop"])
        assert calls[0]["decode_timeout"] is None
        # Once the exact crop has been cached, even a subsequent old cached
        # neighbor or transient decoder failure cannot replace its identity.
        assert client.get(endpoint + "?exact=1&cache_only=1").status_code == 200


def test_retry_uses_longer_deadline_once_and_keeps_precise_identity(
    review_server, monkeypatch
):
    _, report = review_server
    _cold_review_row(report)
    original = web._frame_at
    calls = []

    def slow_only_at_normal_deadline(job, timestamp, rstate, frame_index=None,
                                    **kwargs):
        calls.append((frame_index, kwargs))
        if kwargs.get("decode_timeout") is None:
            abort(504, description="Synthetic original 10-second decoding timeout")
        return original(job, timestamp, rstate, frame_index, **kwargs)

    monkeypatch.setattr(web, "_frame_at", slow_only_at_normal_deadline)
    with web.app.test_client() as client:
        path = "/api/jobs/inline-fixture/finding-preview/0?exact=1"
        first = client.get(path)
        assert first.status_code == 504
        assert len(calls) == 1
        assert calls[0][1]["crop"] is not None
        # Cache-only never starts a source decoder, even with retry flag.
        assert client.get(path + "&retry_decode=1&cache_only=1").status_code == 204
        second = client.get(path + "&retry_decode=1")
        assert second.status_code == 200, second.get_data(as_text=True)[:300]
        meta = json.loads(second.headers["X-Finding-Geometry"])
        assert meta["frame"] == 299
        assert meta["requested_frame"] == 299
        assert calls[-1][0] == 299
        assert calls[-1][1]["decode_timeout"] == 60
        assert meta["classification_allowed"] is True


def test_extended_process_limit_is_explicit_not_global(monkeypatch):
    observed = []

    def timed_out(command, **kwargs):
        observed.append(kwargs["timeout"])
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(web.subprocess, "run", timed_out)
    with web.app.test_request_context():
        with pytest.raises(Exception) as first:
            web._review_process(["ffmpeg", "test"])
        with pytest.raises(Exception) as extended:
            web._review_process(["ffmpeg", "test"], timeout=60)
    assert getattr(first.value, "code", None) == 504
    assert getattr(extended.value, "code", None) == 504
    assert observed == [10, 60]


def test_browser_retry_recovers_504_without_changing_output_or_drafts(
    review_server, monkeypatch
):
    api = pytest.importorskip("playwright.sync_api")
    url, report = review_server
    _cold_review_row(report)
    original = web._frame_at
    calls = []

    def timed_out_on_normal(job, timestamp, rstate, frame_index=None, **kwargs):
        calls.append((frame_index, kwargs.get("decode_timeout"), kwargs.get("crop")))
        if kwargs.get("decode_timeout") is None:
            abort(504, description="Synthetic source-frame timeout")
        return original(job, timestamp, rstate, frame_index, **kwargs)

    monkeypatch.setattr(web, "_frame_at", timed_out_on_normal)
    with api.sync_playwright() as pw:
        browser = browser_instance(pw)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.set_default_timeout(20000)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        load_browser_page(page, url, [], [])
        page.get_by_role("link", name="Synthetic review fixture", exact=True).click()
        card = page.locator("#det0")
        card.scroll_into_view_if_needed()
        retry = card.locator(".preview-retry")
        retry.wait_for(state="visible")
        assert "Retry preview" in retry.inner_text()
        assert "too long" in card.locator(".preview-status").inner_text()
        before = page.evaluate("EN[0]")
        retry.click()
        page.wait_for_function("""() => {
          const img=document.querySelector('#det0 img');
          return img?._plateMeta?.frame===299&&img.naturalWidth>0;
        }""")
        assert len(calls) >= 2
        assert calls[-1][0] == 299
        assert calls[-1][1] == 60
        assert calls[-1][2] is not None
        assert page.evaluate("EN[0]") == before
        assert page.evaluate("OUTPUT_CHOICES[0]") is None
        assert page.evaluate("CONFIRM_FAILED.size") == 0
        assert not errors, errors
        browser.close()


def test_one_click_recovers_multiple_timed_out_cards_without_implicit_choices(
    review_server, monkeypatch
):
    """Batch the user's failed cards in the existing single cold-decoder lane."""
    api = pytest.importorskip("playwright.sync_api")
    url, report = review_server
    _cold_review_row(report)
    doc = json.loads(report.read_text())
    doc["detections"][1].update(
        frame_index=298, t_start=298/30, t_end=298/30,
        last_seen=298/30, track=-1)
    report.write_text(json.dumps(doc))
    original = web._frame_at
    calls = []

    def timeout_then_long(job, timestamp, rstate, frame_index=None, **kwargs):
        calls.append((frame_index, kwargs.get("decode_timeout")))
        if kwargs.get("decode_timeout") is None:
            abort(504, description="Synthetic strict preview decoder timeout")
        return original(job, timestamp, rstate, frame_index, **kwargs)

    monkeypatch.setattr(web, "_frame_at", timeout_then_long)
    with api.sync_playwright() as pw:
        browser = browser_instance(pw)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.set_default_timeout(20000)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        load_browser_page(page, url, [], [])
        page.get_by_role("link", name="Synthetic review fixture", exact=True).click()
        all_retry = page.locator("#reviewRetryTimedOut")
        page.wait_for_function("""() =>
          document.querySelectorAll("#review .preview-retry:not([hidden])").length>=2
        """)
        assert all_retry.is_visible()
        assert "2" in all_retry.inner_text()
        assert page.evaluate("REVIEW_VERSION") == 0
        all_retry.click()
        page.wait_for_function("""() => {
          const a=document.querySelector("#det0 img")?._plateMeta;
          const b=document.querySelector("#det1 img")?._plateMeta;
          return a?.frame===299&&b?.frame===298;
        }""")
        assert all_retry.is_hidden()
        assert sorted(calls) == [(298, None), (298, 60), (299, None), (299, 60)]
        assert page.evaluate("REVIEW_VERSION") == 0
        assert page.evaluate("EN[0]") is True
        assert page.evaluate("EN[1]") is True
        assert page.evaluate("CONFIRM_FAILED.size") == 0
        assert not errors, errors
        browser.close()
