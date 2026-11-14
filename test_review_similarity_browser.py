"""Legacy scans group similar cached thumbnails without changing detections.

End-to-end tests use the real Flask review UI and its existing confirm endpoint.
"""
import json
from pathlib import Path

import cv2
import pytest

import openscrub_web as web
from test_review_browser import browser_instance, load_browser_page, review_server


def _browse(url, page):
    load_browser_page(page, url, [], [])
    page.get_by_role("link", name="Synthetic review fixture", exact=True).click()
    page.locator("#review .det").first.wait_for()
    page.wait_for_function(
        "() => !!document.getElementById('thumb0')._plateMeta")
    page.get_by_role("button", name="Group similar pictures").click()
    page.wait_for_function(
        "() => document.querySelectorAll('.review-similar-slot:not(:empty)').length > 0")


def test_cached_scan_groups_are_reversible_and_dont_auto_confirm(review_server):
    url, report = review_server
    api = pytest.importorskip("playwright.sync_api")
    with api.sync_playwright() as playwright:
        browser = browser_instance(playwright)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.set_default_timeout(16000)
            _browse(url, page)

            # The source has ninety different tracks with the same cropped
            # picture. No scan or report rewrite is needed to group them.
            assert page.locator("#review .det").count() == 90
            page.wait_for_function(
                "() => !!document.getElementById('det1').hidden")
            assert page.locator("#review .det:visible").count() < 90
            assert "visually similar" in page.locator("#similar0").inner_text()
            assert not any(row.get("human_confirmation") for row in
                           web._load_job_report(web.JOBS["inline-fixture"])["detections"])

            # Expand to reach every original card and correct mistakes.
            page.locator("#similar0 button[id^=similarExpand]").click()
            page.locator("#det1").wait_for(state="visible")
            page.locator("#det0").get_by_role("button", name="✕ Not a plate").click()
            page.wait_for_function(
                "() => FINDING_META[0]?.human_confirmation?.label === 'negative' && !CONFIRM_PENDING.has(0)")
            saved = web._load_job_report(web.JOBS["inline-fixture"])["detections"]
            assert saved[0]["verified_label"] == "not_plate"
            assert not saved[1].get("verified_label"), "Grouping must not propagate a decision"

            # Correct that exact human decision, including its archive revision.
            page.locator("#det0").get_by_role("button", name="✓ Is a plate").click()
            page.wait_for_function(
                "() => FINDING_META[0]?.human_confirmation?.label === 'positive' && !CONFIRM_PENDING.has(0)")
            saved = web._load_job_report(web.JOBS["inline-fixture"])["detections"]
            assert saved[0]["verified_label"] == "plate"
            assert not saved[1].get("verified_label")

            page.get_by_role("button", name="Show individual pictures").click()
            assert page.locator("#review .det:visible").count() == 90
            assert page.locator("#similar0").inner_text() == ""
        finally:
            browser.close()


def test_explicit_group_decision_saves_each_source_frame_separately(review_server):
    url, report = review_server
    job_dir = Path(report).parent
    doc = json.loads(Path(report).read_text())
    original = doc["detections"][0]
    doc["detections"] = []
    capture = cv2.VideoCapture(str(job_dir / "review.mp4"))
    try:
        for n in range(3):
            f = 300 + n
            row = dict(original, track=100 + n, frame_index=f,
                       t_start=f / 30, t_end=(f + 1) / 30,
                       last_seen=f / 30)
            doc["detections"].append(row)
            capture.set(cv2.CAP_PROP_POS_FRAMES, f)
            ok, pixels = capture.read()
            assert ok
            web.finding_previews.capture(str(job_dir), pixels, f, 30., [row])
    finally:
        capture.release()
    Path(report).write_text(json.dumps(doc))
    api = pytest.importorskip("playwright.sync_api")
    with api.sync_playwright() as playwright:
        browser = browser_instance(playwright)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.set_default_timeout(20000)
            page.on("dialog", lambda dialog: dialog.accept())
            _browse(url, page)
            page.wait_for_function(
                "() => document.querySelector('#similar0 strong')?.textContent.includes('3 visually similar')")
            assert page.locator("#review .det").count() == 3

            page.locator("#similar0 summary").click()
            page.locator('#similar0 [data-similar-batch="0"]').last.click()
            page.wait_for_function(
                "() => document.getElementById('reviewSimilarityStatus').textContent.includes('3 confirmations saved')")
            labels = [r.get("verified_label") for r in
                      web._load_job_report(web.JOBS["inline-fixture"])["detections"]]
            assert labels == ["not_plate"] * 3, labels
            with web.app.test_client() as client:
                items = client.get("/api/findings").get_json()["items"]
            assert {item["frame"] for item in items} == {300, 301, 302}

            # Show all and correct one saved decision; disagreement is visible.
            page.locator("#similar0 button[id^=similarExpand]").click()
            page.locator("#det1").get_by_role("button", name="✓ Is a plate").click()
            page.wait_for_function(
                "() => FINDING_META[1]?.human_confirmation?.label === 'positive' && !CONFIRM_PENDING.has(1)")
            assert "CONFLICTING HUMAN DECISIONS" in page.locator("#similar0").inner_text()
            labels = [r.get("verified_label") for r in
                      web._load_job_report(web.JOBS["inline-fixture"])["detections"]]
            assert labels == ["not_plate", "plate", "not_plate"]
        finally:
            browser.close()
