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


def test_pre_write_busy_confirmation_retries_without_creating_a_sticky_failure(
    review_server, monkeypatch
):
    sync_api = pytest.importorskip("playwright.sync_api")
    from flask import jsonify, request

    url, _report = review_server
    original = web.app.view_functions["finding_confirm"]
    calls = []

    def transient_busy(*args, **kwargs):
        if request.method == "POST":
            calls.append(request.get_json())
            if len(calls) <= 2:
                return jsonify(
                    error="Another review edit is saving. Retry shortly."
                ), 503
        return original(*args, **kwargs)

    monkeypatch.setitem(web.app.view_functions, "finding_confirm", transient_busy)
    with sync_api.sync_playwright() as pw:
        browser = browser_instance(pw)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.set_default_timeout(20000)
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        load_browser_page(page, url, [], [])
        page.get_by_role("link", name="Synthetic review fixture", exact=True).click()
        card = page.locator("#det0")
        card.scroll_into_view_if_needed()
        page.wait_for_function('!!document.querySelector("#det0 img")._plateMeta')
        card.get_by_role("button", name="✓ Is a plate", exact=True).click()
        page.evaluate("CONFIRM_CHAIN")
        assert len(calls) == 3
        assert page.evaluate("CONFIRM_FAILED.size") == 0
        assert page.locator("#confirmationSaveIssues").is_hidden()
        assert page.evaluate("saveAndRender(true)") is True
        stored = web._load_job_report(web.JOBS["inline-fixture"])["detections"]
        assert stored[0]["human_confirmation"]["label"] == "positive"
        assert not errors, errors
        browser.close()


def test_discarding_conflicted_corners_preserves_real_failed_confirmation():
    from test_findings_review import choices_script

    choices_script(r"""
const before=[[0,0],[10,0],[10,8],[0,8]];
const changed=[[1,1],[10,0],[10,8],[0,8]];
const error=Object.assign(new Error("Human confirmation not acknowledged"),{
  status:409,reviewAttemptedLabel:"positive"
});
const edit={i:0,job:CUR,dirty:true,archiveConflict:true,error,
  version:1,pending:null,points:plateCopy(changed),saved:plateCopy(before),
  draw(){}};
PLATE_EDITS.set(0,edit);CONFIRM_FAILED.set(0,error);
dismissFindingConfirmation(0);
assert.equal(edit.dirty,false);
assert.deepEqual(edit.points,before);
assert.equal(CONFIRM_FAILED.get(0),error,
  "The failed classification is independent of the discarded area");
dismissFindingConfirmation(0);
assert.equal(CONFIRM_FAILED.size,0,
  "A second explicit action can keep the current saved choice");
""")


def test_stale_picture_requires_new_human_click_then_clears_confirmation_failure():
    """409 changed-source rejection is not a permanent rendering blocker."""
    from test_findings_review import choices_script

    choices_script(r"""
const points=[[0,0],[10,0],[10,8],[0,8]];
const old={frame:100,key:"old",source_token:"old-image",preview_token:"old-token",
 box:[0,0,10,8],crop:[0,0,20,15],width:20,height:15,points};
const fresh={...old,frame:101,key:"fresh",source_token:"fresh-image",
 preview_token:"fresh-token",points};
const img={_plateMeta:{...old}};
const card={
 querySelector(){return img;},
 querySelectorAll(){return [];},
 classList:{toggle(){}}
};
document.getElementById=id=>id==="det0"?card:null;
const edit={i:0,job:CUR,img,meta:{...old},
 displayCrop:old.crop.slice(),points:plateCopy(points),
 saved:plateCopy(points),dirty:false,drag:null,version:0,
 draw(){}};
PLATE_EDITS.set(0,edit);
let calls=0;
async function queueReviewPreview(image) {image._plateMeta={...fresh};return true}
function plateSamePreviewSource(){return false}
function plateSameSourceFrame(){return false}
function plateCornersInsideCrop(){return true}
async function reviewRequest(url,options){
 const body=JSON.parse(options.body);calls++;
 if(calls===1)throw Object.assign(new Error("Stale preview"),{
  status:409,details:{conflict:"stale_preview"}});
 assert.equal(body.preview_token,fresh.preview_token);
 assert.equal(body.preview_key,fresh.key);
 return {data:{finding:{id:"saved",revision:1},preview:{...fresh}}};
}
(async()=>{
 await confirmFinding(0,"positive");
 assert.equal(calls,1,"Different source must never auto-reconfirm");
 assert.equal(CONFIRM_FAILED.size,1);
 assert.equal(CONFIRM_FAILED.get(0).status,409);
 assert.equal(CONFIRM_FAILED.get(0).beforeWrite,true);
 assert.match(CONFIRM_FAILED.get(0).message,/picture changed/i);
 assert.equal(edit.meta.key,"fresh","The new source is shown for inspection");
 await confirmFinding(0,"positive");
 assert.equal(calls,2,"Only the second human click can save new source");
 assert.equal(CONFIRM_FAILED.size,0);
 assert.equal(VLBL[0],"plate");
 assert.equal(FINDING_META[0].confirmed_finding_id,"saved");
})().catch(error=>{console.error(error);process.exitCode=1});
""")


def test_exact_frame_endpoint_replaces_borrowed_representative_for_confirmation(
    review_server
):
    """A borrowed cached source frame must not be silently relabelled as the
    detection's exact frame. A reviewer can request its own verified JPEG."""
    url, report = review_server
    doc = json.loads(report.read_text())
    # All scan-time previews were saved on frame 300. The modified finding is
    # now source frame 299 and shares a track with finding 1 (on frame 300).
    doc["detections"][0].update(
        frame_index=299, t_start=299 / 30, t_end=299 / 30,
        last_seen=299 / 30, track=1
    )
    report.write_text(json.dumps(doc))
    with web.app.test_client() as client:
        path = "/api/jobs/inline-fixture/finding-preview/0"
        borrowed = client.get(path + "?cache_only=1")
        assert borrowed.status_code == 200
        representative = json.loads(borrowed.headers["X-Finding-Geometry"])
        assert representative["match"] == "representative"
        assert representative["frame"] == 300
        assert representative["requested_frame"] == 299

        # Exact lookup must not return the borrowed frame.
        assert client.get(path + "?exact=1&cache_only=1").status_code == 204
        exact = client.get(path + "?exact=1")
        assert exact.status_code == 200, exact.get_data(as_text=True)
        meta = json.loads(exact.headers["X-Finding-Geometry"])
        assert meta["frame"] == meta["requested_frame"] == 299
        assert meta["key"] != representative["key"]
        assert meta["source_token"] != representative["source_token"]
        assert meta["preview_token"] != representative["preview_token"]
        assert client.get(path + "?exact=1&cache_only=1").status_code == 200

        result = client.post("/api/jobs/inline-fixture/confirm/0", json={
            "label": "positive",
            "preview_token": meta["preview_token"],
            "preview_key": meta["key"],
        })
        assert result.status_code == 200, result.get_data(as_text=True)
        confirmed = result.get_json()
        assert confirmed["finding"]["frame"] == 299
        assert confirmed["finding"]["label"] == "positive"


def test_review_loads_exact_source_frame_and_rebinds_clean_editor(
    review_server
):
    """End-to-end fix for a card showing neighboring frame 2332 for 2305."""
    sync_api = pytest.importorskip("playwright.sync_api")
    url, report = review_server
    doc = json.loads(report.read_text())
    doc["detections"][0].update(
        frame_index=299, t_start=299 / 30, t_end=299 / 30,
        last_seen=299 / 30, track=1
    )
    report.write_text(json.dumps(doc))
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
        page.wait_for_function("""() => {
          const m=document.querySelector("#det0 img")?._plateMeta;
          return m?.frame===300&&m.requested_frame===299;
        }""")
        button = card.get_by_role(
            "button", name="Load exact source frame", exact=True
        )
        button.wait_for(state="visible")
        assert "cached frame 300" in card.locator(".source-frame-note").inner_text()
        button.click()
        page.wait_for_function("""() => {
          const img=document.querySelector("#det0 img");
          return img?._plateMeta?.frame===299&&img._quadEdit?.meta?.frame===299;
        }""")
        assert button.is_hidden()
        assert page.evaluate("PLATE_EDITS.get(0).dirty") is False
        assert page.evaluate(
            "PLATE_EDITS.get(0).meta.preview_token"
            "===document.querySelector('#det0 img')._plateMeta.preview_token"
        )
        card.get_by_role("button", name="✓ Is a plate", exact=True).click()
        page.evaluate("CONFIRM_CHAIN")
        assert page.evaluate("CONFIRM_FAILED.size") == 0
        saved = web._load_job_report(web.JOBS["inline-fixture"])["detections"][0]
        assert saved["human_confirmation"]["label"] == "positive"
        items = web.app.test_client().get("/api/findings").get_json()["items"]
        assert any(item["frame"] == 299 for item in items)
        assert not errors, errors
        browser.close()


def test_repeated_stale_representative_conflict_recovers_by_loading_exact_frame(
    review_server, monkeypatch
):
    """A cached neighbor can remain unchanged through repeated stale-preview
    409s; requiring the exact source frame resolves the real-world dead end."""
    sync_api = pytest.importorskip("playwright.sync_api")
    from flask import jsonify, request
    url, report = review_server
    doc = json.loads(report.read_text())
    doc["detections"][0].update(
        frame_index=299, t_start=299 / 30, t_end=299 / 30,
        last_seen=299 / 30, track=1
    )
    report.write_text(json.dumps(doc))
    original = web.app.view_functions["finding_confirm"]
    requests = []

    def twice_stale(*args, **kwargs):
        if request.method == "POST":
            requests.append(request.get_json())
            if len(requests) <= 2:
                return jsonify(
                    error="This displayed picture is no longer a valid cached sample.",
                    conflict="stale_preview"
                ), 409
        return original(*args, **kwargs)

    monkeypatch.setitem(web.app.view_functions, "finding_confirm", twice_stale)
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
        page.wait_for_function("""() => {
          const m=document.querySelector("#det0 img")?._plateMeta;
          return m?.frame===300&&m.requested_frame===299;
        }""")
        card.get_by_role("button", name="✓ Is a plate", exact=True).click()
        page.evaluate("CONFIRM_CHAIN")
        assert page.evaluate("CONFIRM_FAILED.size") == 1
        assert len(requests) == 2
        assert page.locator("#confirmationSaveIssues").is_visible()
        button = card.get_by_role("button", name="Load exact source frame")
        button.wait_for(state="visible")
        button.click()
        page.wait_for_function(
            'document.querySelector("#det0 img")?._plateMeta?.frame===299'
        )
        assert page.evaluate("PLATE_EDITS.get(0).dirty") is False
        card.get_by_role("button", name="✓ Is a plate", exact=True).click()
        page.evaluate("CONFIRM_CHAIN")
        assert len(requests) == 3
        assert page.evaluate("CONFIRM_FAILED.size") == 0
        assert page.evaluate("saveAndRender(true)") is True
        assert web._load_job_report(web.JOBS["inline-fixture"])[
            "detections"][0]["human_confirmation"]["label"] == "positive"
        assert not errors, errors
        browser.close()
