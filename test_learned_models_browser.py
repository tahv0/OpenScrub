"""Real browser save/select/export/import flow at desktop and mobile widths."""
import json
import os
from pathlib import Path
import shutil

import pytest
import openscrub_web as web
from test_learned_models import accepted_job, library
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



def _defer_next_model_list_response(page):
    """Delay delivery of a real API response without replacing its contents."""
    page.evaluate("""() => {
      const originalFetch=window.fetch.bind(window);
      let delayNext=true;
      window.__releaseModelList=null;
      window.fetch=async(input, options={})=>{
        const address=typeof input==="string" ? input : input.url;
        const isList=new URL(address,document.baseURI).pathname==="/api/jobs/learned-models";
        if(delayNext && isList && (options.method||"GET").toUpperCase()==="GET"){
          delayNext=false;
          const response=await originalFetch(input,options);
          return new Promise(resolve=>{
            window.__releaseModelList=()=>resolve(response);
          });
        }
        return originalFetch(input,options);
      };
      window.__pendingModelRefresh=refreshLearnedModels();
    }""")
    page.wait_for_function("typeof window.__releaseModelList==='function'")


def _release_model_list_response(page):
    page.evaluate("""async() => {
      window.__releaseModelList();
      await window.__pendingModelRefresh;
    }""")


def test_model_library_refresh_keeps_selection_made_while_response_is_pending(
        review_server, tmp_path, monkeypatch):
    sync = pytest.importorskip("playwright.sync_api")
    url, _ = review_server
    root = tmp_path / "selection-jobs"
    root.mkdir()
    monkeypatch.setattr(web, "JOBS_DIR", str(root))
    monkeypatch.setattr(web, "vault_locked", lambda: False)
    saved = library().save_model(root / "learned_plate_models",
                                 accepted_job(tmp_path / "trained-seed"),
                                 "Garage daylight")
    with sync.sync_playwright() as pw:
        browser = browser_instance(pw)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_default_timeout(15000)
            load_browser_page(page, url, [], [])
            sync.expect(page.locator("#learnedPlateModel option")).to_have_count(2)
            page.evaluate("location.hash='#settings'")
            page.locator("#learnedModelLibrary .learned-model").wait_for()
            assert page.locator("#learnedPlateModel").input_value() == ""
            _defer_next_model_list_response(page)
            page.get_by_role("button", name="Use for next scan", exact=True).click()
            sync.expect(page.locator("#mainview")).to_be_visible()
            assert page.locator("#learnedPlateModel").input_value() == saved["id"]
            _release_model_list_response(page)
            assert page.locator("#learnedPlateModel").input_value() == saved["id"], (
                "An earlier list request discarded the model chosen for the next scan")
        finally:
            browser.close()


def test_model_library_ignores_an_older_list_response(
        review_server, tmp_path, monkeypatch):
    sync = pytest.importorskip("playwright.sync_api")
    url, _ = review_server
    root = tmp_path / "response-order-jobs"
    root.mkdir()
    monkeypatch.setattr(web, "JOBS_DIR", str(root))
    monkeypatch.setattr(web, "vault_locked", lambda: False)
    seed = accepted_job(tmp_path / "trained-seed")
    library().save_model(root / "learned_plate_models", seed, "First camera")
    with sync.sync_playwright() as pw:
        browser = browser_instance(pw)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_default_timeout(15000)
            load_browser_page(page, url, [], [])
            sync.expect(page.locator("#learnedPlateModel option")).to_have_count(2)
            _defer_next_model_list_response(page)
            # The delayed response already contains the one-model snapshot.
            second = library().save_model(root / "learned_plate_models", seed, "Second camera")
            assert page.evaluate("refreshLearnedModels()") is True
            sync.expect(page.locator("#learnedModelLibrary .learned-model")).to_have_count(2)
            sync.expect(page.locator("#learnedPlateModel option")).to_have_count(3)
            _release_model_list_response(page)
            sync.expect(page.locator("#learnedModelLibrary .learned-model")).to_have_count(2)
            assert page.locator("#learnedPlateModel option").evaluate_all(
                "(items)=>items.map(item=>item.value)").count(second["id"]) == 1, (
                "An older response replaced the newer model library")
        finally:
            browser.close()


def test_model_library_controls_follow_real_vault_unlock_and_lock(
        review_server, tmp_path, monkeypatch):
    sync = pytest.importorskip("playwright.sync_api")
    url, _ = review_server
    data_root = tmp_path / "encrypted-application"
    root = data_root / "jobs"
    root.mkdir(parents=True)
    monkeypatch.setattr(web, "_data_root", lambda: str(data_root))
    monkeypatch.setattr(web, "JOBS_DIR", str(root))
    monkeypatch.setattr(web, "VAULT", {"key": None})
    monkeypatch.setattr(web, "_web_settings", lambda: {})
    saved = library().save_model(root / "learned_plate_models",
                                 accepted_job(tmp_path / "trained-seed"),
                                 "Private garage camera")
    model_dir = root / "learned_plate_models" / saved["id"]
    password = "synthetic-vault-password"
    with web.app.test_client() as client:
        assert client.post("/api/vault/setup", json={"password": password}).status_code == 200
        assert client.post("/api/vault/lock").status_code == 200
    assert (model_dir / "model.onnx.osvault").is_file()
    assert not (model_dir / "model.onnx").exists()
    errors = []
    with sync.sync_playwright() as pw:
        browser = browser_instance(pw)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_default_timeout(15000)
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("dialog", lambda dialog: dialog.accept())
            load_browser_page(page, url, [], [])
            selector = page.locator("#learnedPlateModel")
            sync.expect(selector).to_be_disabled()
            page.evaluate("location.hash='#settings'")
            sync.expect(page.locator("#vunlock")).to_be_visible()
            sync.expect(page.locator("#learnedModelLibrary .learned-model")).to_have_count(0)
            sync.expect(page.locator("#learnedPlateModel option")).to_have_count(1)
            assert saved["name"] not in page.locator("#learnedModelsPanel").inner_text()
            page.locator("#vpw").fill(password)
            page.get_by_role("button", name="Unlock", exact=True).click()
            # No manual model Refresh or view navigation should be necessary.
            sync.expect(selector).to_be_enabled()
            sync.expect(page.locator("#learnedModelLibrary .learned-model")).to_have_count(1)
            sync.expect(page.locator("#learnedModelLibrary")).to_contain_text(saved["name"])
            sync.expect(page.locator("#learnedPlateModel option")).to_have_count(2)
            assert selector.input_value() == ""
            assert (model_dir / "model.onnx").is_file()
            page.get_by_role("button", name="Lock now (encrypt all job files)", exact=True).click()
            sync.expect(page.locator("#vstat")).to_contain_text("LOCKED")
            sync.expect(selector).to_be_disabled()
            sync.expect(page.locator("#learnedModelLibrary .learned-model")).to_have_count(0)
            sync.expect(page.locator("#learnedPlateModel option")).to_have_count(1)
            assert selector.input_value() == ""
            assert saved["name"] not in page.locator("#learnedModelsPanel").inner_text()
            assert (model_dir / "model.onnx.osvault").is_file()
            assert not (model_dir / "model.onnx").exists()
            assert not errors, errors
        finally:
            browser.close()
