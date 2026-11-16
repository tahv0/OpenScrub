"""Recover an expired Review confirmation token without reclassifying a new frame.

A 409 caused by a stale JPEG key or preview revision is a pre-write rejection,
unlike an archive-revision conflict. The browser may automatically resubmit
the same explicit label only after it proves the same displayed source pixels.
"""
import json

import pytest

import findings_web
import learning_session
import openscrub_web as web
import stop_review
import review_journal
from test_plate_quad_editor import plate_job
from test_review_browser import review_server, browser_instance, load_browser_page


@pytest.mark.parametrize('modern_journal', [False, True])
def test_confirm_token_revision_conflict_has_machine_readable_recovery(
        plate_job, monkeypatch, tmp_path, modern_journal):
    client, jid, report, job_dir = plate_job
    monkeypatch.setattr(findings_web, 'root', lambda: tmp_path / 'archives')
    doc = json.loads(report.read_text(encoding='utf-8'))
    if modern_journal:
        sha = learning_session.sha256(web.JOBS[jid]['video'])
        doc['provenance']['input_sha256'] = sha
        doc['source_identity'] = dict(input_sha256=sha, width=240,
                                      height=160, fps=10, total_frames=10)
        doc['detections'][0].update(frame_index=2, aoff=[0, 0])
        stop_review.atomic_report(str(report), doc)
    shown = client.get(f'/api/jobs/{jid}/finding-preview/0')
    assert shown.status_code == 200, shown.get_data(as_text=True)[:500]
    meta = json.loads(shown.headers['X-Finding-Geometry'])
    original = report.read_bytes()
    stale = client.post(f'/api/jobs/{jid}/confirm/0', json=dict(
        label='positive', preview_key=meta['key'],
        preview_token='0' * 64))
    assert stale.status_code == 409
    body = stale.get_json()
    assert body == dict(
        error='The finding changed. Reload its picture.',
        conflict='stale_preview', reason='preview_token_changed')
    assert report.read_bytes() == original
    assert not review_journal.has_changes(job_dir)
    assert client.get('/api/findings').get_json()['total'] == 0

    # The source identity is still correct; the user's original click can
    # be retried after safe picture recovery without silently changing labels.
    accepted = client.post(f'/api/jobs/{jid}/confirm/0', json=dict(
        label='positive', preview_key=meta['key'],
        preview_token=meta['preview_token']))
    assert accepted.status_code == 200, accepted.get_data(as_text=True)[:600]
    assert accepted.get_json()['finding']['label'] == 'positive'


def test_real_browser_auto_retries_typed_same_picture_conflict_once(
        review_server, monkeypatch):
    """An explicit Is-a-plate click needs no second click for token-only 409."""
    sync_api = pytest.importorskip('playwright.sync_api')
    from flask import jsonify, request
    url, report = review_server
    original = web.app.view_functions['finding_confirm']
    submissions = []

    def first_expired_token(*args, **kwargs):
        if request.method == 'POST':
            submissions.append(request.get_json())
            if len(submissions) == 1:
                return jsonify(
                    error='The finding changed. Reload its picture.',
                    conflict='stale_preview',
                    reason='preview_token_changed'), 409
        return original(*args, **kwargs)

    monkeypatch.setitem(web.app.view_functions, 'finding_confirm',
                        first_expired_token)
    with sync_api.sync_playwright() as pw:
        browser = browser_instance(pw)
        page = browser.new_page(viewport={'width': 1440, 'height': 950})
        page.set_default_timeout(30000)
        errors = []
        page.on('pageerror', lambda exc: errors.append(str(exc)))
        load_browser_page(page, url, [], [])
        page.get_by_role('link', name='Synthetic review fixture',
                         exact=True).click()
        card = page.locator('#det0')
        card.scroll_into_view_if_needed()
        page.wait_for_function(
            "!!document.querySelector('#det0 img')._plateMeta")
        card.get_by_role('button', name='✓ Is a plate', exact=True).click()
        page.evaluate('CONFIRM_CHAIN')
        assert len(submissions) == 2
        assert submissions[0]['label'] == submissions[1]['label'] == 'positive'
        assert page.evaluate('CONFIRM_FAILED.size') == 0
        assert page.locator('#confirmationSaveIssues').is_hidden()
        assert web._load_job_report(web.JOBS['inline-fixture'])[
            'detections'][0]['human_confirmation']['label'] == 'positive'
        assert not errors, errors
        browser.close()



def test_evicted_jpeg_409_is_still_structured_with_full_server_message():
    """Never regress the existing long-message prefix into an HTML 409."""
    from flask import abort
    from werkzeug.exceptions import Conflict

    def error_result(message):
        @findings_web._guard
        def simulated():
            abort(409, description=message)
        with web.app.test_request_context():
            return simulated()

    message = ('This displayed picture is no longer a valid cached sample. '
               'Reload its preview.')
    response, status = error_result(message)
    assert status == 409
    assert response.get_json() == dict(error=message,
                                       conflict='stale_preview',
                                       reason='cache_evicted')
    with pytest.raises(Conflict):
        error_result('Unrelated source video or archive revision changed.')
