"""Review filters for detection types and actual output protection."""
import json

import pytest

from test_review_browser import review_server, browser_instance, load_browser_page


def test_type_and_output_filters_combine_without_mutating_review(review_server):
    api = pytest.importorskip("playwright.sync_api")
    url, report = review_server
    doc = json.loads(report.read_text())
    for i in range(70, 80):
        doc["detections"][i]["category"] = "face"
    for i in range(80, 90):
        doc["detections"][i]["category"] = "manual"
    report.write_text(json.dumps(doc))
    with api.sync_playwright() as pw:
        browser = browser_instance(pw)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.set_default_timeout(15000)
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        load_browser_page(page, url, [], [])
        page.get_by_role("link", name="Synthetic review fixture", exact=True).click()
        kind = page.locator("#reviewTypeFilter")
        output = page.locator("#reviewOutputFilter")
        status = page.locator("#reviewStatusFilter")
        kind.wait_for()
        assert "License plates (70)" == kind.locator('option[value="plate"]').text_content()
        assert "Other sensitive areas (20)" == kind.locator('option[value="other"]').text_content()
        assert "Will be blurred (90)" == output.locator('option[value="blur"]').text_content()

        # Human output choices are not the same as Is/Not training labels.
        page.locator("#det0").get_by_role("button", name="Keep visible", exact=True).click()
        page.locator("#det70").get_by_role("button", name="Keep visible", exact=True).click()
        page.evaluate("""() => {
          window.__plate=document.getElementById('det0');
          window.__face=document.getElementById('det70');
          window.__version=REVIEW_VERSION;
        }""")
        kind.select_option("plate")
        output.select_option("blur")
        assert page.locator("#det0").is_hidden()
        assert page.locator("#det1").is_visible()
        assert page.locator("#det70").is_hidden()
        assert "69 of 90 review groups match" in page.locator("#reviewFilterSummary").inner_text()
        status.select_option("unreviewed")
        assert page.locator("#det1").is_visible()
        output.select_option("visible")
        assert "0 of 90 review groups match" in page.locator("#reviewFilterSummary").inner_text()
        status.select_option("reviewed")
        assert page.locator("#det0").is_visible()
        kind.select_option("other")
        assert page.locator("#det70").is_visible()
        assert page.locator("#det80").is_hidden()
        assert page.evaluate("REVIEW_VERSION===window.__version")
        assert page.evaluate("document.getElementById('det0')===window.__plate")
        assert page.evaluate("document.getElementById('det70')===window.__face")

        page.get_by_role("button", name="Show all findings").click()
        assert kind.input_value() == "all"
        assert output.input_value() == "all"
        assert status.input_value() == "all"
        assert page.locator("#det0").is_visible()
        assert page.locator("#det70").is_visible()
        assert page.evaluate("EN[0]") is False
        assert page.evaluate("EN[70]") is False
        assert page.evaluate("OUTPUT_CHOICES[0]") is True
        assert page.evaluate("OUTPUT_CHOICES[70]") is True
        assert not errors, errors
        browser.close()


def test_blur_filter_preserves_unsaved_corners_and_mixed_group_outputs(review_server):
    api = pytest.importorskip("playwright.sync_api")
    url, _report = review_server
    with api.sync_playwright() as pw:
        browser = browser_instance(pw)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.set_default_timeout(20000)
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        load_browser_page(page, url, [], [])
        page.get_by_role("link", name="Synthetic review fixture", exact=True).click()
        card = page.locator("#det0")
        card.scroll_into_view_if_needed()
        page.wait_for_function("!!PLATE_EDITS.get(0)")
        page.evaluate("""() => {
          const s=PLATE_EDITS.get(0);
          s.points=s.points.map(p=>p.slice());
          s.points[0][0]+=2;s.version++;s.dirty=true;
          s.error=Object.assign(new Error("Synthetic failed area"),{status:503});
          plateStatus(s,"Not saved — synthetic",true);
          window.__edit=s;
          window.__card=document.getElementById("det0");
        }""")
        output = page.locator("#reviewOutputFilter")
        output.select_option("visible")
        assert card.is_hidden()
        output.select_option("blur")
        assert card.is_visible()
        assert page.evaluate("PLATE_EDITS.get(0)===window.__edit")
        assert page.evaluate('document.getElementById("det0")===window.__card')
        assert page.evaluate("PLATE_EDITS.get(0).dirty") is True
        # A tracked group with both protected and visible member frames
        # must appear in BOTH output views rather than be mislabeled.
        page.evaluate("""() => {
          window.__group=TRKMEM[0];TRKMEM[0]=[0,1];
          EN[0]=false;EN[1]=true;
        }""")
        assert page.evaluate('reviewOutputMatches(0,"blur")') is True
        assert page.evaluate('reviewOutputMatches(0,"visible")') is True
        page.evaluate("() => {TRKMEM[0]=window.__group;EN[0]=true}")
        assert not errors, errors
        browser.close()


def test_filter_lazy_queue_includes_hidden_output_choices(review_server):
    api = pytest.importorskip("playwright.sync_api")
    url, report = review_server
    doc = json.loads(report.read_text())
    prototype = dict(doc["detections"][0])
    for i in range(len(doc["detections"]), 520):
        doc["detections"].append(dict(prototype, track=i))
    report.write_text(json.dumps(doc))
    with api.sync_playwright() as pw:
        browser = browser_instance(pw)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.set_default_timeout(20000)
        page.add_init_script("window.IntersectionObserver=undefined")
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        load_browser_page(page, url, [], [])
        page.get_by_role("link", name="Synthetic review fixture", exact=True).click()
        output = page.locator("#reviewOutputFilter")
        output.wait_for()
        assert page.locator('[data-review-category="plate"] .det').count() == 48
        page.evaluate("() => {EN[450]=false;OUTPUT_CHOICES[450]=true}")
        output.select_option("visible")
        page.wait_for_function('!!document.getElementById("det450")')
        assert page.locator("#det450").is_visible()
        assert page.locator("#det0").is_hidden()
        assert "1 of 520 review groups match" in page.locator("#reviewFilterSummary").inner_text()
        assert page.locator('[data-review-category="plate"] .det').count() < 60

        output.select_option("blur")
        assert page.locator("#det450").is_hidden()
        button = page.locator('[data-review-more="plate"]')
        assert button.is_visible()
        button.click()
        assert page.locator('[data-review-category="plate"] .det').count() >= 96
        assert page.locator("#det450").is_hidden()
        page.get_by_role("button", name="Show all findings").click()
        assert page.locator("#det450").is_visible()
        assert page.evaluate("OUTPUT_CHOICES[450]") is True
        assert not errors, errors
        browser.close()
