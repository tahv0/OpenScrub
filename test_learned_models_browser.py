"""Real browser save/select/export/import flow at desktop and mobile widths."""
import json
import os
from pathlib import Path
import shutil

import pytest
import openscrub_web as web
from test_learned_models import accepted_job
from test_review_browser import review_server, browser_instance, load_browser_page


@pytest.mark.parametrize("width,height", [(1440, 1000), (390, 844)])
def test_reusable_models_save_select_and_transfer_ui(review_server, tmp_path, monkeypatch, width, height):
    sync = pytest.importorskip("playwright.sync_api")
    url, report = review_server
    root = tmp_path / "application-data"
    root.mkdir()
    monkeypatch.setattr(web, "JOBS_DIR", str(root))
    monkeypatch.setattr(web, "vault_locked", lambda: False)
    seed = accepted_job(tmp_path / "trained-seed")
    original = json.loads((seed / "report.json").read_text())
    shutil.copytree(seed / "learning", report.parent / "learning")
    doc = json.loads(report.read_text())
    doc["learning"] = original["learning"]
    doc["learning"]["active"]["model"] = str(
        report.parent / "learning" /
        Path(original["learning"]["active"]["model"]).relative_to(seed / "learning"))
    report.write_text(json.dumps(doc))
    errors = []
    with sync.sync_playwright() as pw:
        browser = browser_instance(pw)
        page = browser.new_page(viewport={"width": width, "height": height},
                                accept_downloads=True)
        page.set_default_timeout(15000)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("dialog", lambda dialog: dialog.accept())
        load_browser_page(page, url, [], [])
        page.locator("#learnedPlateModel").wait_for()
        assert page.locator("#learnedPlateModel").input_value() == ""
        page.get_by_role("link", name="Synthetic review fixture", exact=True).click()
        page.locator("#review").wait_for()
        page.locator("#saveLearnedModelPanel summary").click()
        page.get_by_label("Model name", exact=True).fill("Garage <daylight>")
        page.get_by_label("Environment description", exact=True).fill("Fixed camera, daylight")
        page.get_by_role("button", name="Save model", exact=True).click()
        page.wait_for_function("document.querySelector('#saveLearnedModelStatus').textContent.includes('Saved')")
        assert page.locator("#learnedPlateModel").input_value() == ""
        page.evaluate("location.hash='#settings'")
        page.locator("#learnedModelLibrary .learned-model").wait_for()
        entry = page.locator("#learnedModelLibrary .learned-model")
        assert entry.count() == 1
        assert "Garage <daylight>" in entry.inner_text()
        assert entry.locator("daylight").count() == 0
        with page.expect_download() as download:
            entry.get_by_role("link", name="Export", exact=True).click()
        archive = tmp_path / ("transfer-%s.openscrub-model" % width)
        download.value.save_as(str(archive))
        page.locator("#learnedModelImport").set_input_files(str(archive))
        page.wait_for_function("document.querySelectorAll('#learnedModelLibrary .learned-model').length===2")
        assert page.locator("#learnedPlateModel").input_value() == ""
        page.locator("#learnedModelLibrary .learned-model").last.get_by_role(
            "button", name="Use for next scan", exact=True).click()
        assert page.locator("#learnedPlateModel").input_value()
        assert page.locator("#mainview").is_visible()
        selected = page.locator("#learnedPlateModel").input_value()
        page.evaluate("location.hash='#settings'")
        page.locator("#learnedModelLibrary .learned-model").first.get_by_role(
            "button", name="Remove", exact=True).click()
        page.wait_for_function("document.querySelectorAll('#learnedModelLibrary .learned-model').length===1")
        assert page.locator("#learnedPlateModel").input_value() == selected
        assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
        assert not errors, errors
        evidence = Path(os.environ.get("REVIEW_EVIDENCE_DIR", str(tmp_path)))
        evidence.mkdir(parents=True, exist_ok=True)
        page.locator("#learnedModelsPanel").screenshot(path=str(evidence / ("model-library-%s.png" % width)))
        page.evaluate("location.hash=''")
        page.locator("#learnedPlateModelControls").screenshot(path=str(evidence / ("model-selection-%s.png" % width)))
        browser.close()
