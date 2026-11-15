"""Review status filtering: view-only, group-aware, safe with unsaved corner drafts.

Run: pytest -q test_review_status_filter.py (requires Chromium / Playwright).
"""
import json
from pathlib import Path

import pytest

from test_review_browser import review_server, browser_instance, load_browser_page


def test_needs_review_hides_handled_and_preserves_unsaved_corner_drafts(review_server):
    sync_api = pytest.importorskip("playwright.sync_api")
    url, _ = review_server
    with sync_api.sync_playwright() as pw:
        browser = browser_instance(pw)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.set_default_timeout(15000)
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        load_browser_page(page, url, [], [])
        page.get_by_role("link", name="Synthetic review fixture", exact=True).click()

        control = page.locator("#reviewStatusFilter")
        control.wait_for()
        assert page.locator('#review .det').count() == 90
        assert "Needs review (90)" == control.locator('option[value="unreviewed"]').inner_text()

        control.select_option("unreviewed")
        card = page.locator("#det0")
        card.get_by_role("button", name="Keep visible", exact=True).click()
        page.wait_for_function('document.querySelector("#det0").hidden')
        assert page.evaluate("EN[0]") is False
        assert page.evaluate("OUTPUT_CHOICES[0]") is True
        assert "Needs review (89)" == control.locator('option[value="unreviewed"]').inner_text()
        assert page.locator("#det1").is_visible()

        # A handled card remains reachable; filtering does not unmount it.
        control.select_option("reviewed")
        assert card.is_visible()
        assert page.locator("#det1").is_hidden()
        original = card.evaluate("(el)=>el")
        control.select_option("pending")
        assert card.is_hidden()
        assert control.locator('option[value="pending"]').inner_text() == "Unsaved / failed (0)"

        # Failed corner autosaves MUST surface in Needs review even for a
        # previously handled group, and retain the same in-memory editor.
        control.select_option("all")
        card.scroll_into_view_if_needed()
        page.wait_for_function('!!document.querySelector("#det0 img")._quadEdit')
        page.evaluate("""() => {
          const s=PLATE_EDITS.get(0);
          s.points=s.points.map(p=>p.slice());
          s.points[0][0]+=2;
          s.version++;
          s.dirty=true;
          s.error=Object.assign(new Error("Injected offline failure"),{status:503});
          plateStatus(s,"Not saved — offline",true);
        }""")
        control.select_option("unreviewed")
        page.wait_for_function('!document.querySelector("#det0").hidden')
        assert page.evaluate("PLATE_EDITS.get(0).dirty") is True
        assert control.locator('option[value="pending"]').inner_text() == "Unsaved / failed (1)"

        control.select_option("all")
        assert card.is_visible()
        assert card.evaluate("(el)=>el") == original
        assert not errors, errors
        browser.close()


def test_lazy_filter_can_find_unmounted_handled_groups_without_loading_all(review_server):
    sync_api = pytest.importorskip("playwright.sync_api")
    url, report = review_server
    doc = json.loads(Path(report).read_text())
    prototype = dict(doc["detections"][0])
    # More than REVIEW_PAGE_THRESHOLD (400): only the first 48 mount initially.
    for i in range(len(doc["detections"]), 520):
        doc["detections"].append(dict(prototype, track=i))
    Path(report).write_text(json.dumps(doc))

    with sync_api.sync_playwright() as pw:
        browser = browser_instance(pw)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.set_default_timeout(20000)
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        load_browser_page(page, url, [], [])
        page.get_by_role("link", name="Synthetic review fixture", exact=True).click()

        control = page.locator("#reviewStatusFilter")
        control.wait_for()
        assert page.locator('[data-review-category="plate"] .det').count() == 48
        # A previously saved choice may be on an unmounted card. Filtering
        # must find it in the group metadata rather than in mounted DOM only.
        page.evaluate("() => {OUTPUT_CHOICES[450]=true}")
        control.select_option("reviewed")
        page.wait_for_function('!!document.querySelector("#det450")')
        assert page.locator("#det450").is_visible()
        assert page.locator("#det0").is_hidden()
        assert control.locator('option[value="reviewed"]').inner_text() == "Handled (1)"
        assert page.locator('[data-review-category="plate"] .det').count() < 60

        control.select_option("unreviewed")
        assert page.locator("#det450").is_hidden()
        more = page.locator('[data-review-more="plate"]')
        assert more.is_visible()
        assert "remaining" in more.inner_text()
        more.click()
        assert page.locator('[data-review-category="plate"] .det').count() >= 96
        # The group must stay handled, and therefore invisible in Needs review.
        assert page.locator("#det450").is_hidden()

        control.select_option("all")
        assert page.locator("#det450").is_visible()
        assert page.evaluate('OUTPUT_CHOICES[450]') is True
        assert not errors, errors
        browser.close()
