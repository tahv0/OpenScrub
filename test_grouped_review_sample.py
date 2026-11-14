"""The human review budget counts grouped findings, never per-frame sightings."""
from copy import deepcopy
import json
import math
import os
from pathlib import Path

import pytest
import openscrub_web as web
import video_learning as vl


def grouped_report(lengths):
    rows = []
    for track, length in enumerate(lengths):
        for frame in range(length):
            rows.append(dict(category='plate', track=track, person=-1,
                             frame_index=frame, t_start=frame / 30,
                             t_end=(frame + 1) / 30, confidence=.5,
                             cbox=[20, 20, 80, 45], enabled=True))
    return {'detections': rows, 'render_state': {'fps': 30}}


@pytest.mark.parametrize('lengths', [[100] * 100, [1] * 9 + [10000], [1, 1000, 250]])
def test_sample_budget_counts_tracks_not_their_frame_lengths(lengths):
    doc = grouped_report(lengths)
    before = deepcopy(doc)
    picks = vl.review_sample(doc, .1)
    assert len(picks) == math.ceil(len(lengths) * .1)
    assert len({doc['detections'][i]['track'] for i in picks}) == len(picks)
    assert doc == before, 'Sampling must not remove or merge rendering rows'


def test_full_fraction_still_has_only_one_representative_per_track():
    doc = grouped_report([80] * 10)
    picks = vl.review_sample(doc, 1)
    assert len(picks) == 10
    assert {doc['detections'][i]['track'] for i in picks} == set(range(10))


def test_long_track_does_not_change_selection_or_budget():
    short = grouped_report([2] * 100)
    for row in short['detections']:
        row['confidence'] = .9
        if row['track'] in (12, 38):
            row['learning_conflict'] = 'uncertain outline'
    long = deepcopy(short)
    long['detections'].extend(deepcopy(long['detections'][0]) for _ in range(6000))
    tracks = lambda doc: {doc['detections'][i]['track'] for i in vl.review_sample(doc)}
    assert tracks(short) == tracks(long)
    assert {12, 38} <= tracks(short), 'Retain group-level uncertainty priority'


def test_reviewed_and_zoned_rows_do_not_inflate_group_budget():
    doc = grouped_report([30] * 100)
    for row in doc['detections']:
        if row['track'] < 40:
            row['verified_label'] = 'plate'
        elif row['track'] < 60:
            row.update(verified_label='not_plate', enabled=False)
        elif row['track'] < 80:
            row['zone_dropped'] = True
    picks = vl.review_sample(doc)
    assert len(picks) == 2
    assert all(doc['detections'][i]['track'] >= 80 for i in picks)


def test_same_identity_groups_match_review_cards():
    doc = grouped_report([20] * 20)
    for row in doc['detections']:
        row['person'] = row['track'] // 2
    picks = vl.review_sample(doc, .1)
    assert len(picks) == 1, 'The normal review groups identity before track'


def test_unknown_tracks_are_not_merged_just_because_boxes_match():
    doc = grouped_report([1] * 20)
    for row in doc['detections']:
        row['track'] = -1
    assert len(vl.review_sample(doc, .1)) == 2
    assert len(vl.review_sample(doc, 1)) == 20


@pytest.mark.parametrize('fraction', [0, -1, 1.01, float('inf'), float('nan')])
def test_invalid_sample_fraction_is_rejected(fraction):
    with pytest.raises(ValueError, match='fraction'):
        vl.review_sample(grouped_report([1]), fraction)


def test_empty_sample_is_empty():
    assert vl.review_sample(grouped_report([])) == []


from test_plate_quad_editor import plate_job


def test_sample_api_reports_group_units_and_counts(plate_job):
    client, jid, path, _ = plate_job
    doc = json.loads(path.read_text())
    template = doc['detections'][0]
    doc['detections'] = [dict(deepcopy(template), track=t, person=-1)
                         for t in range(100) for _ in range(40)]
    path.write_text(json.dumps(doc))
    result = client.get('/api/jobs/%s/learning/review?fraction=0.1' % jid)
    assert result.status_code == 200
    data = result.get_json()
    assert len(data['indices']) == 10
    assert data['eligible_groups'] == 100
    assert data['selected_groups'] == 10 and data['unit'] == 'finding_group'
    assert json.loads(path.read_text()) == doc


from test_review_browser import review_server, browser_instance, load_browser_page


def test_pinned_representative_survives_new_exact_cache_sample(review_server):
    """An in-flight thumbnail fill must not invalidate a human save token.

    The browser showed frame 300, then another request cached exact frame 100
    for the same track. Only a source-bound opaque key plus the original
    preview token may authorize writing the image the reviewer actually saw.
    """
    import numpy as np

    _, path = review_server
    doc = json.loads(path.read_text())
    row = dict(doc['detections'][0], frame_index=100, t_start=100/30,
               t_end=101/30, last_seen=100/30)
    doc['detections'] = [row]
    path.write_text(json.dumps(doc))
    job = web.JOBS['inline-fixture']
    with web.app.test_client() as client:
        old = client.get('/api/jobs/inline-fixture/finding-preview/0?cache_only=1')
        assert old.status_code == 200
        shown = json.loads(old.headers['X-Finding-Geometry'])
        assert shown['frame'] == 300 and shown['match'] == 'representative'
        # An unrelated viewer now saves a verified exact-frame preview.
        box = [180, 120, 420, 220]
        crop = [100, 60, 500, 280]
        web.finding_previews.store(
            job['dir'], row, doc['render_state'],
            dict(frame=100, width=640, height=360, crop=crop, box=box,
                 source={'timing':'frame', 'sha256':doc['provenance']['input_sha256']}),
            np.full((220, 400, 3), 128, np.uint8))
        newer = client.get('/api/jobs/inline-fixture/finding-preview/0?cache_only=1')
        assert newer.status_code == 200
        latest = json.loads(newer.headers['X-Finding-Geometry'])
        assert latest['frame'] == 100 and latest['preview_token'] != shown['preview_token']
        # Without its pinned key the old token no longer matches: fail closed.
        rejected = client.post('/api/jobs/inline-fixture/confirm/0', json={
            'label':'negative','preview_token':shown['preview_token']})
        assert rejected.status_code == 409
        # With its original key, source and crop validation bind the JPEG.
        accepted = client.post('/api/jobs/inline-fixture/confirm/0', json={
            'label':'negative','preview_token':shown['preview_token'],
            'preview_key':shown['key']})
        assert accepted.status_code == 200, accepted.get_data(as_text=True)[:500]
        assert accepted.get_json()['finding']['frame'] == 300
        saved = web._load_job_report(job)['detections'][0]
        assert saved['verified_label'] == 'not_plate' and not saved['enabled']



def test_source_frame_proof_distinguishes_legacy_null_video_hashes():
    """No cross-video frame rebinding when old reports store a null source."""
    import findings_web as fw

    row = dict(category='plate', cbox=[180, 120, 420, 220], plate_quad=[])
    document = dict(
        compact_preview_source=None,
        provenance=dict(input_sha256='source-video-a'),
        render_state=dict(fps=30, cum=[[0, 0]]))
    before = fw._token(document, row, 0, None)
    assert fw._source_hash(document) == 'source-video-a'
    document['provenance']['input_sha256'] = 'different-source-video-b'
    assert fw._token(document, row, 0, None) != before
    document['provenance'].clear()
    assert fw._source_hash(document) is None


def test_evicted_displayed_image_can_be_reloaded_and_saved_with_same_frame_binding(review_server):
    """A preloaded JPEG can be evicted before the human saves four corners.

    The old opaque key must fail closed. A freshly decoded source frame can
    safely authorize a new request only if the backend proves the same
    immutable source frame and original detection geometry.
    """
    import sqlite3

    _, path = review_server
    job = web.JOBS['inline-fixture']
    with web.app.test_client() as client:
        initial = client.get('/api/jobs/inline-fixture/finding-preview/0?cache_only=1')
        assert initial.status_code == 200
        shown = json.loads(initial.headers['X-Finding-Geometry'])
        assert shown['key'] and shown['frame_source_token']
        stale_body = dict(compact=True, autosave=True, edit_id='evicted-draft',
                          points=[[185, 125], [415, 125], [415, 215], [185, 215]],
                          preview_key=shown['key'],
                          preview_token=shown['preview_token'])
        database = Path(job['dir']) / 'compact_previews' / 'index.sqlite3'
        with sqlite3.connect(database) as db:
            assert db.execute('DELETE FROM previews WHERE key=?',
                              (shown['key'],)).rowcount == 1
            db.commit()
        refused = client.post('/api/jobs/inline-fixture/plate_quad/0', json=stale_body)
        assert refused.status_code == 409
        assert refused.get_json()['conflict'] == 'stale_preview'
        assert not web._load_job_report(job)['detections'][0].get('plate_quad')

        refreshed = client.get('/api/jobs/inline-fixture/finding-preview/0')
        assert refreshed.status_code == 200, refreshed.get_data(as_text=True)[:150]
        current = json.loads(refreshed.headers['X-Finding-Geometry'])
        assert current['frame_source_token'] == shown['frame_source_token']
        assert current['frame'] == shown['frame'] and current['box'] == shown['box']

        stale_body.update(preview_key=current['key'],
                          preview_token=current['preview_token'],
                          edit_id='rebound-source-verified')
        saved = client.post('/api/jobs/inline-fixture/plate_quad/0', json=stale_body)
        assert saved.status_code == 200, saved.get_data(as_text=True)[:300]
        assert saved.get_json()['ok']
        assert web._load_job_report(job)['detections'][0]['human_region_confirmed']


def test_large_group_single_http_confirmation_has_stable_preview_token(review_server):
    """Regression for 409 when a 10k-row review uses a scan-time representative.

    Distinct tracks intentionally share geometry: the confirmed archive is
    source/frame/box-bound, while the output choice fans out by track.
    """
    _, path = review_server
    doc = json.loads(path.read_text())
    first = doc['detections'][0]
    doc['detections'] = [
        dict(deepcopy(first), track=t, frame_index=f, t_start=f / 30,
             t_end=(f + 1) / 30, last_seen=f / 30)
        for t in range(100) for f in range(100, 200)
    ]
    path.write_text(json.dumps(doc))
    with web.app.test_client() as client:
        listing = client.get('/api/jobs/inline-fixture/detections')
        assert listing.status_code == 200, listing.get_data(as_text=True)[:500]
        image = client.get('/api/jobs/inline-fixture/finding-preview/0')
        assert image.status_code == 200, image.get_data(as_text=True)[:500]
        meta = json.loads(image.headers['X-Finding-Geometry'])
        saved = client.post('/api/jobs/inline-fixture/confirm/0', json={
            'label': 'negative', 'preview_token': meta['preview_token']})
        assert saved.status_code == 200, saved.get_data(as_text=True)[:500]
        assert web._load_job_report(web.JOBS['inline-fixture'])['detections'][99]['verified_label'] == 'not_plate'
        assert not web._load_job_report(web.JOBS['inline-fixture'])['detections'][100].get('verified_label')



@pytest.mark.parametrize('width', [1440, 390])
def test_human_sample_shows_ten_groups_not_hundreds_of_frames(review_server, width, tmp_path):
    url, path = review_server
    doc = json.loads(path.read_text())
    template = doc['detections'][0]
    # 100 physical tracks, each observed for 100 adjacent source frames.
    doc['detections'] = [dict(deepcopy(template), track=t, frame_index=f,
                             t_start=f/30, t_end=(f+1)/30, last_seen=f/30)
                         for t in range(100) for f in range(100, 200)]
    path.write_text(json.dumps(doc))
    api = pytest.importorskip('playwright.sync_api')
    with api.sync_playwright() as pw:
        browser = browser_instance(pw)
        page = browser.new_page(viewport={'width': width, 'height': 1000 if width > 400 else 844})
        page.set_default_timeout(12000)
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('dialog', lambda dialog: dialog.accept())
        load_browser_page(page, url, [], [])
        assert page.title() == 'OpenScrub'
        page.get_by_role('link', name='Synthetic review fixture', exact=True).click()
        page.locator('#review').wait_for()
        assert page.locator('#review .det:visible').count() == 100
        page.get_by_role('button', name='Review 10% of plate groups', exact=True).click()
        page.get_by_role('button', name='Show all findings', exact=True).wait_for()
        assert page.locator('#review .det:visible').count() == 10
        assert '10 of 100' in page.locator('#reviewSampleSummary').inner_text()
        assert 'group' in page.locator('#reviewSampleSummary').inner_text()
        assert len(page.evaluate('Object.keys(EN)')) == 10000
        cards = page.locator('#review .det:visible')
        card = cards.first
        index = int(card.get_attribute('id')[3:])
        members = page.evaluate('(i)=>TRKMEM[i]', index)
        assert len(members) == 100
        assert '100 frames' in card.inner_text(), 'Keep the full grouped span in the sampled card'
        card.scroll_into_view_if_needed()
        page.wait_for_function('(i)=>!!document.querySelector("#det"+i+" img")._quadEdit', arg=index)
        # A cached scan-time representative can be a different exact source
        # frame from this synthetic interpolated detection row. Its real
        # picture/frame, not the guessed report-row frame, becomes evidence.
        displayed = card.locator('img').evaluate(
            '(img)=>({frame:img._plateMeta.frame,key:img._plateMeta.key})')
        card.get_by_role('button', name='✕ Not a plate', exact=True).click()
        page.evaluate('CONFIRM_CHAIN')
        page.wait_for_function('(i)=>document.getElementById("vlabel"+i).textContent.includes("Saved") || document.getElementById("vlabel"+i).textContent.includes("Not saved")',arg=index)
        assert 'Saved' in page.locator('#vlabel%d' % index).inner_text(), page.locator('#vlabel%d' % index).inner_text()
        assert page.evaluate('CONFIRM_FAILED.size') == 0
        assert card.locator('.det-status').inner_text() == 'Will stay visible'
        assert page.evaluate('saveAndRender(true)') is True
        saved = json.loads(path.read_text())['detections']
        assert all(saved[i]['verified_label'] == 'not_plate' and not saved[i]['enabled'] for i in members)
        assert len(saved) == 10000
        chosen=set(members)
        assert all(not row.get('verified_label') and row['enabled'] for i,row in enumerate(saved) if i not in chosen)
        with web.app.test_client() as client:
            archived=client.get('/api/findings').get_json()
        assert archived['total']==1, 'One confirmed group stores one representative, not 100 frame examples'
        assert archived['items'][0]['label']=='negative'
        assert archived['items'][0]['frame']==displayed['frame']
        evidence = Path(os.environ.get('REVIEW_EVIDENCE_DIR', str(tmp_path)))
        evidence.mkdir(parents=True, exist_ok=True)
        page.locator('#reviewSampleSummary').scroll_into_view_if_needed()
        # Browser evidence should not wait for a queued 4K source decode of
        # an unrelated, offscreen card. Cancel optional preview prefetch after
        # verifying the committed sample; decisions and visible cards persist.
        page.evaluate('clearReviewPreviews()')
        page.locator('#reviewSampleSummary').screenshot(
            path=str(evidence / ('grouped-sample-%s.png' % width)), timeout=10000)
        page.get_by_role('button', name='Show all findings', exact=True).click()
        page.wait_for_function('document.querySelectorAll("#review .det:not([hidden])").length===100')
        assert page.locator('#det%d .det-status' % (index//100*100)).inner_text() == 'Will stay visible'
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        assert not errors, errors
        browser.close()


def test_sample_spreads_groups_instead_of_taking_first_tenth():
    doc = grouped_report([30] * 100)
    # Non-overlapping appearances, ordered along the video's timeline.
    for row in doc['detections']:
        row['t_start'] += row['track'] * 5
    picks = vl.review_sample(doc)
    assert [doc['detections'][i]['track'] for i in picks] == list(range(0, 100, 10))
    # Within each ten-group batch, select the most useful uncertain example.
    for row in doc['detections']:
        if row['track'] == 17:
            row['learning_conflict'] = 'model disagreement'
    tracks = [doc['detections'][i]['track'] for i in vl.review_sample(doc)]
    assert tracks == [0, 17, 20, 30, 40, 50, 60, 70, 80, 90]
