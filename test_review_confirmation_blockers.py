"""Regression coverage for failed human confirmations blocking long video review.

One failed Is/Not save must be easy to locate and retry, and must not
cause unrelated output choices to be lost. Corner autosaves are separate.
"""
import json

import pytest

from test_review_browser import (
    review_server, browser_instance, load_browser_page, drag_corner
)
import openscrub_web as web


def test_failed_confirmation_can_be_located_retried_and_other_choices_saved(
    review_server, monkeypatch
):
    sync_api = pytest.importorskip("playwright.sync_api")
    from flask import jsonify, request

    url, _report = review_server
    original = web.app.view_functions["finding_confirm"]
    calls = []

    def once_rejected(*args, **kwargs):
        if request.method == "POST":
            calls.append(request.get_json())
            if len(calls) == 1:
                return jsonify(error="Synthetic archived example conflict"), 409
        return original(*args, **kwargs)

    monkeypatch.setitem(web.app.view_functions, "finding_confirm", once_rejected)
    with sync_api.sync_playwright() as pw:
        browser = browser_instance(pw)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.set_default_timeout(20000)
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        load_browser_page(page, url, [], [])
        page.get_by_role(
            "link", name="Synthetic review fixture", exact=True
        ).click()
        card = page.locator("#det0")
        card.scroll_into_view_if_needed()
        page.wait_for_function(
            '!!document.querySelector("#det0 img")._plateMeta'
        )
        card.get_by_role("button", name="✓ Is a plate", exact=True).click()
        page.evaluate("CONFIRM_CHAIN")
        assert page.evaluate("CONFIRM_FAILED.size") == 1
        panel = page.locator("#confirmationSaveIssues")
        assert panel.is_visible()
        assert "Synthetic archived example conflict" in panel.inner_text()
        assert panel.get_by_role("button", name="Show finding #0").count() == 1

        # Saving another user's explicit output choice is still allowed,
        # but no render/training may start with a failed confirmation.
        page.locator("#det1").get_by_role(
            "button", name="Keep visible", exact=True
        ).click()
        assert page.evaluate("saveAndRender(true)") is False
        assert "Other review choices saved to disk" in page.locator(
            ".review-save-status"
        ).first.inner_text()
        stored = web._load_job_report(web.JOBS["inline-fixture"])["detections"]
        assert stored[1]["enabled"] is False
        assert stored[1]["output_choice_explicit"] is True
        assert not stored[0].get("human_confirmation")

        # Confirmation retry is explicit and source-bound, never a blind
        # automatic replay of an ambiguous human classification.
        panel.get_by_role("button", name="Retry Is a plate").click()
        page.evaluate("CONFIRM_CHAIN")
        assert len(calls) == 2
        assert page.evaluate("CONFIRM_FAILED.size") == 0
        assert panel.is_hidden()
        assert page.evaluate("saveAndRender(true)") is True
        stored = web._load_job_report(web.JOBS["inline-fixture"])["detections"]
        assert stored[0]["human_confirmation"]["label"] == "positive"
        assert stored[1]["enabled"] is False
        assert not errors, errors
        browser.close()


def test_area_archive_conflict_is_not_misfiled_as_a_failed_human_confirmation(
    review_server, monkeypatch
):
    sync_api = pytest.importorskip("playwright.sync_api")
    from flask import jsonify, request

    url, _report = review_server
    original = web.app.view_functions["job_plate_quad"]

    def reject_area(*args, **kwargs):
        if request.method == "POST":
            return jsonify(
                error="Synthetic saved example changed",
                current_archive=dict(label="negative", revision=2)
            ), 409
        return original(*args, **kwargs)

    monkeypatch.setitem(web.app.view_functions, "job_plate_quad", reject_area)
    with sync_api.sync_playwright() as pw:
        browser = browser_instance(pw)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.set_default_timeout(20000)
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        load_browser_page(page, url, [], [])
        page.get_by_role(
            "link", name="Synthetic review fixture", exact=True
        ).click()
        card = page.locator("#det0")
        card.scroll_into_view_if_needed()
        page.wait_for_function(
            '!!document.querySelector("#det0 img")._quadEdit'
        )
        drag_corner(page, card)
        page.wait_for_function("PLATE_EDITS.get(0)?.archiveConflict===true")
        assert page.evaluate("PLATE_EDITS.get(0).dirty") is True
        assert page.evaluate("CONFIRM_FAILED.size") == 0
        assert page.locator("#confirmationSaveIssues").is_hidden()
        assert page.locator("#plateSaveIssues").is_visible()

        # Output can be saved separately but full render remains blocked
        # by unacknowledged polygon geometry.
        assert page.evaluate("saveAndRender(true)") is False
        assert "corner adjustment" in page.locator(
            ".review-save-status"
        ).first.inner_text()
        assert page.evaluate("PLATE_EDITS.get(0).dirty") is True

        # A deliberate Not-a-plate decision can discard an irrelevant draft.
        card.get_by_role("button", name="✕ Not a plate", exact=True).click()
        page.evaluate("CONFIRM_CHAIN")
        assert page.evaluate("CONFIRM_FAILED.size") == 0
        assert page.evaluate("PLATE_EDITS.get(0).dirty") is False
        assert page.evaluate("saveAndRender(true)") is True
        stored = web._load_job_report(web.JOBS["inline-fixture"])["detections"]
        assert stored[0]["verified_label"] == "not_plate"
        assert not errors, errors
        browser.close()
