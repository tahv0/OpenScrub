"""Relocalized Is/Not review actions must not rewrite a huge report.json.

These tests use synthetic source video and report data, not user recordings.
They exercise archived source-frame evidence, the incremental journal, and
the distinct safety rules for explicitly confirmed vs. merely dragged corners.
"""
import json

import pytest

import confirmed_findings as library
import findings_web
import review_journal
import stop_review
import openscrub_web as web
from test_review_browser import review_server


def _rebound_fixture(review_server, human_corners=False):
    """Confirm the synthetic sample, publish it, then move only its scan row."""
    _, report = review_server
    job = web.JOBS["inline-fixture"]
    path = "/api/jobs/inline-fixture/finding-preview/0"
    with web.app.test_client() as client:
        first = client.get(path + "?exact=1")
        assert first.status_code == 200
        first_meta = json.loads(first.headers["X-Finding-Geometry"])
        assert first_meta["frame"] == 300
        value = {
            "label": "positive",
            "preview_key": first_meta["key"],
            "preview_token": first_meta["preview_token"],
        }
        if human_corners:
            x1, y1, x2, y2 = first_meta["box"]
            value["points"] = [[x1 + 8, y1 + 7], [x2 - 8, y1 + 7],
                               [x2 - 8, y2 - 7], [x1 + 8, y2 - 7]]
        saved = client.post("/api/jobs/inline-fixture/confirm/0", json=value)
        assert saved.status_code == 200, saved.get_data(as_text=True)
        original = saved.get_json()["finding"]
        assert original["label"] == "positive"
        assert original["frame"] == 300

    assert review_journal.publish(job["dir"]) is True
    document = json.loads(report.read_text())
    row = document["detections"][0]
    assert row["confirmed_finding_id"] == original["id"]
    # A later scan/reconciliation can choose a different actual source frame
    # and box. This cannot change the identity of an older saved example.
    row.update(frame_index=299, t_start=299 / 30, t_end=299 / 30,
               last_seen=299 / 30, cbox=[175, 116, 425, 224])
    stop_review.atomic_report(str(report), document)

    with web.app.test_client() as client:
        second = client.get(path + "?exact=1")
        assert second.status_code == 200, second.get_data(as_text=True)
        updated = json.loads(second.headers["X-Finding-Geometry"])
    assert updated["frame"] == updated["requested_frame"] == 299
    assert updated["preview_token"] != first_meta["preview_token"]
    assert updated["key"] != first_meta["key"]
    return report, job, original, updated


def test_rebound_explicit_confirmation_uses_journal_without_full_report_rewrite(
    review_server, monkeypatch
):
    report, job, original, metadata = _rebound_fixture(review_server)
    before_bytes = report.read_bytes()
    events = []
    monkeypatch.setattr(findings_web, "_CONFIRM_SLOW_TRACE_SECONDS", 0)
    monkeypatch.setattr(
        web.diagnostics, "event",
        lambda name, *args, **kwargs: events.append((name, kwargs))
    )

    def full_report_forbidden(*args, **kwargs):
        pytest.fail("A human reconfirmation must not publish/rewrite the 271k-row report")

    monkeypatch.setattr(web, "_review_journal_snapshot", full_report_forbidden)
    monkeypatch.setattr(web, "_load_job_report", full_report_forbidden)
    monkeypatch.setattr(stop_review, "atomic_report", full_report_forbidden)

    with web.app.test_client() as client:
        response = client.post("/api/jobs/inline-fixture/confirm/0", json={
            "label": "negative",  # explicit choice on the NEW source frame
            "preview_key": metadata["key"],
            "preview_token": metadata["preview_token"],
            "expected_revision": original["revision"],
        })
        assert response.status_code == 200, response.get_data(as_text=True)
        created = response.get_json()["finding"]
        assert created["frame"] == 299
        assert created["label"] == "negative"
        assert created["id"] != original["id"]

        # A repeat with the current receipt is idempotent. No surprise rebind
        # or silent overwrite of a newer human classification is allowed.
        second = client.post("/api/jobs/inline-fixture/confirm/0", json={
            "label": "negative",
            "preview_key": metadata["key"],
            "preview_token": response.get_json()["preview"]["preview_token"],
            "expected_revision": created["revision"],
        })
        assert second.status_code == 200, second.get_data(as_text=True)
        assert second.get_json()["finding"]["id"] == created["id"]
        assert second.get_json()["finding"]["revision"] == created["revision"]

    assert report.read_bytes() == before_bytes
    assert review_journal.has_changes(job["dir"])
    with web.app.test_client() as client:
        # The archive records are independently durable, with disjoint IDs.
        old = client.get("/api/findings/" + original["id"])
        new = client.get("/api/findings/" + created["id"])
        assert old.status_code == new.status_code == 200
        assert old.get_json()["finding"]["label"] == "positive"
        assert old.get_json()["finding"]["frame"] == 300
        assert new.get_json()["finding"]["label"] == "negative"
        assert new.get_json()["finding"]["frame"] == 299
    traces = [values for name, values in events
              if name == "review_confirmation_stages_slow"]
    assert len(traces) == 2
    assert traces[0]["mode"] == "journal_rebound"
    assert traces[1]["mode"] == "journal", (
        "After the first rebound the new source is already the trusted archive")
    assert all("save_full_report_ms" not in v for v in traces)


def test_rebound_confirmation_is_visible_after_journal_publish_and_restart(
    review_server
):
    report, job, original, metadata = _rebound_fixture(review_server)
    with web.app.test_client() as client:
        response = client.post("/api/jobs/inline-fixture/confirm/0", json={
            "label": "negative",
            "preview_key": metadata["key"],
            "preview_token": metadata["preview_token"],
            "expected_revision": original["revision"],
        })
        assert response.status_code == 200, response.get_data(as_text=True)
        new = response.get_json()["finding"]
    # Simulate a new process by rereading the immutable report and applying
    # the durable journal, before deliberately publishing its snapshot.
    recovered = review_journal.apply(job["dir"], json.loads(report.read_text()))
    assert recovered["detections"][0]["verified_label"] == "not_plate"
    assert recovered["detections"][0]["confirmed_finding_id"] == new["id"]
    assert recovered["detections"][0]["human_confirmation"]["label"] == "negative"
    assert review_journal.publish(job["dir"]) is True
    assert not review_journal.has_changes(job["dir"])
    published = json.loads(report.read_text())
    assert published["detections"][0]["verified_label"] == "not_plate"
    assert published["detections"][0]["confirmed_finding_id"] == new["id"]
    assert library.get_finding(findings_web.root(), original["id"])["frame"] == 300
    assert library.get_finding(findings_web.root(), new["id"])["frame"] == 299


def test_rebound_cannot_change_existing_archived_evidence_with_mismatched_video(
    review_server, monkeypatch
):
    report, job, original, metadata = _rebound_fixture(review_server)
    original_content = report.read_bytes()
    original_data = library.get_finding(findings_web.root(), original["id"])
    # The existing source-identity check is mandatory even in the fast path:
    # a different original video/timeline may not use the old archive link.
    forged = dict(original_data)
    forged["video"] = dict(forged["video"], sha256="f" * 64)
    real_read = library.get_finding

    def changed_archive(root, identity, **kwargs):
        value = real_read(root, identity, **kwargs)
        return forged if identity == original["id"] else value

    monkeypatch.setattr(library, "get_finding", changed_archive)
    with web.app.test_client() as client:
        response = client.post("/api/jobs/inline-fixture/confirm/0", json={
            "label": "negative",
            "preview_key": metadata["key"],
            "preview_token": metadata["preview_token"],
            "expected_revision": original["revision"],
        })
        assert response.status_code == 409
        assert "different source or timeline" in response.get_json()["error"]
    assert report.read_bytes() == original_content
    assert not review_journal.has_changes(job["dir"])


def test_rebound_does_not_transfer_old_human_corners_or_narrow_masks(
    review_server
):
    """Only a fresh explicit polygon may narrow the NEW frame's redaction."""
    report, job, original, metadata = _rebound_fixture(
        review_server, human_corners=True
    )
    old = library.get_finding(findings_web.root(), original["id"])
    assert old["frame"] == 300
    assert old["shape_confirmed"] is True
    assert len(old["points"]) == 4

    with web.app.test_client() as client:
        updated = client.post("/api/jobs/inline-fixture/confirm/0", json={
            "label": "positive",
            "preview_key": metadata["key"],
            "preview_token": metadata["preview_token"],
            "expected_revision": old["revision"],
        })
        assert updated.status_code == 200, updated.get_data(as_text=True)
        new = updated.get_json()["finding"]
        assert new["frame"] == 299
        assert new["id"] != old["id"]
        assert new["shape_confirmed"] is False
        assert new["points"] is None
    # The old example retains its independently verified four corners;
    # the new frame is protected by its full detector box until adjusted.
    persisted_old = library.get_finding(findings_web.root(), old["id"])
    assert persisted_old["points"] == old["points"]
    assert persisted_old["shape_confirmed"] is True
    recovered = review_journal.apply(job["dir"], json.loads(report.read_text()))
    current = recovered["detections"][0]
    assert current["verified_label"] == "plate"
    assert current["human_region_confirmed"] is False
    assert current["plate_quad"] == []
    assert current["poly"] == [] and current["poly_holes"] == []
    assert current["confirmed_finding_id"] == new["id"]
    assert current["enabled"] is True
