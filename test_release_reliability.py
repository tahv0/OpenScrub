"""Release-level mixed review sessions and failed-request recovery.

Uses synthetic private-local video and real Flask endpoints. CI uses real HTTP;
REVIEW_INPROCESS is only the existing restricted-local browser bridge.
"""
from copy import deepcopy
import json
import os
from pathlib import Path
import random
import threading

import pytest
import confirmed_findings
import openscrub_web as web
from test_review_browser import (review_server, browser_instance,
                                 load_browser_page, drag_corner, plate_points)


def _start(pw, url, width=1440):
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
    return browser, page, errors


def _save(page):
    assert page.evaluate('saveAndRender(true)') is True


def _confirmations_saved(page):
    page.evaluate('CONFIRM_CHAIN')
    assert page.evaluate('CONFIRM_PENDING.size===0&&CONFIRM_FAILED.size===0')


def _archive(report):
    return report.parent.parent/'confirmed_findings'


def _distinct_box(row,index):
    # Tracks in the shared fixture overlap exactly. Give independent findings
    # distinct source geometry so opposite labels do not target one archive ID.
    box=row['cbox'];shift=index/10.
    return [box[0]+shift,box[1],box[2]+shift,box[3]]


@pytest.mark.parametrize('width', [1440, 390])
@pytest.mark.timeout(150)
def test_large_mixed_review_survives_sampling_and_reopen(review_server, width, tmp_path):
    """7,000 rows, 350 tracks, 210 real clicks, 6 saves and multiple reopens."""
    url, report = review_server
    doc = json.loads(report.read_text())
    row = doc['detections'][0]
    doc['detections'] = [dict(deepcopy(row), track=i // 20,cbox=_distinct_box(row,i//20)) for i in range(7000)]
    report.write_text(json.dumps(doc))
    rng = random.Random(2319)
    chosen = rng.sample(range(350), 210)
    actions = [('✕ Not a plate', False, 'not_plate'), ('✓ Is a plate', True, 'plate'),
               ('Keep visible', False, ''), ('Blur', True, '')]
    expected = {}
    api = pytest.importorskip('playwright.sync_api')
    with api.sync_playwright() as pw:
        browser, page, errors = _start(pw, url, width)
        assert page.locator('#review .det').count() == 350
        assert len(page.evaluate('Object.keys(EN)')) == 7000
        for step, track in enumerate(chosen):
            name, enabled, label = actions[step % len(actions)]
            card = page.locator('#det%d' % (track * 20))
            if label:
                card.scroll_into_view_if_needed()
                page.wait_for_function('(i)=>!!document.getElementById("thumb"+i)?._plateMeta',arg=track*20)
            card.get_by_role('button', name=name, exact=True).click()
            if label:
                _confirmations_saved(page)
            expected[track] = enabled, label
            assert card.locator('.det-status').inner_text() == ('Will be blurred' if enabled else 'Will stay visible')
            if (step + 1) % 35 == 0:
                _save(page)
                saved = json.loads(report.read_text())['detections']
                for t, (on, verified) in expected.items():
                    assert all(r['enabled'] is on for r in saved[t*20:(t+1)*20]), t
                    assert saved[t*20].get('verified_label', '') == verified, t
                # Rebuild all cards from the real persisted report, not old DOM.
                page.evaluate('loadReview()')
                page.locator('#review .det').first.wait_for()
                card = page.locator('#det%d' % (track * 20))
                assert card.locator('.det-status').inner_text() == ('Will be blurred' if enabled else 'Will stay visible')
        page.get_by_role('button', name='Review 10% of plate groups', exact=True).click()
        page.get_by_role('button', name='Show all findings', exact=True).wait_for()
        page.get_by_role('button', name='Show all findings', exact=True).click()
        page.wait_for_function('document.querySelectorAll("#review .det").length===350')
        _save(page)
        final = json.loads(report.read_text())['detections']
        for t, (on, verified) in expected.items():
            assert all(r['enabled'] is on for r in final[t*20:(t+1)*20]), t
            assert final[t*20].get('verified_label', '') == verified, t
        saved_examples=confirmed_findings.list_findings(_archive(report),limit=200)
        assert saved_examples['total']==sum(bool(label) for _,label in expected.values())
        assert not errors, errors
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        evidence = Path(os.environ.get('REVIEW_EVIDENCE_DIR', str(tmp_path)))
        evidence.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(evidence / ('mixed-7000-rows-%d.png' % width)))
        browser.close()


def test_lost_corner_response_retry_and_newer_gesture_preserve_latest(review_server, monkeypatch):
    """Write commits but the response is lost; a new drag must not be discarded."""
    from flask import jsonify, request
    url, report = review_server
    original = web.app.view_functions['job_plate_quad']
    received = []
    def lose_first_response(*args, **kwargs):
        result = original(*args, **kwargs)
        if request.method == 'POST':
            received.append(request.get_json())
            if len(received) == 1:
                return jsonify(error='Injected lost response AFTER the write committed'), 502
        return result
    monkeypatch.setitem(web.app.view_functions, 'job_plate_quad', lose_first_response)
    api = pytest.importorskip('playwright.sync_api')
    with api.sync_playwright() as pw:
        browser, page, errors = _start(pw, url)
        card = page.locator('#det0'); card.scroll_into_view_if_needed()
        page.wait_for_function('!!document.querySelector("#det0 img")._quadEdit')
        drag_corner(page, card)
        page.wait_for_function('!!document.querySelector("#det0 img")._quadEdit.error')
        assert json.loads(report.read_text())['detections'][0].get('plate_quad')
        drag_corner(page, card, index=2, dx=-7, dy=-4)
        latest = plate_points(card)
        assert page.evaluate('flushPlateSaves()') is True
        assert len(received) == 3, received
        assert received[0]['edit_id'] == received[1]['edit_id']
        assert received[2]['edit_id'] != received[1]['edit_id']
        assert received[2]['points'] == latest
        assert confirmed_findings.list_findings(_archive(report))['total']==0
        assert not (report.parent/'plate_annotations').exists()
        card.get_by_role('button',name='✓ Is a plate',exact=True).click()
        _confirmations_saved(page)
        saved=confirmed_findings.list_findings(_archive(report))
        assert saved['total']==1
        entry=saved['items'][0]
        assert entry['label']=='positive' and entry['revision']==1 and entry['shape_confirmed']
        assert [v for pt in entry['points'] for v in pt]==pytest.approx(
            [v for pt in latest for v in pt],abs=.001)
        assert confirmed_findings.image_path(_archive(report),entry['id']).is_file()
        _save(page)
        page.evaluate('loadReview()')
        page.locator('#det0').scroll_into_view_if_needed()
        page.wait_for_function('!!document.querySelector("#det0 img")._quadEdit')
        assert [v for pt in plate_points(page.locator('#det0')) for v in pt] == pytest.approx(
            [v for pt in latest for v in pt], abs=.001)
        assert not errors, errors
        browser.close()


def test_failed_decision_save_is_reported_and_retry_preserves_decisions(review_server, monkeypatch):
    """A broken network must not silently strand Save or discard the draft."""
    url, report = review_server
    api = pytest.importorskip('playwright.sync_api')
    with api.sync_playwright() as pw:
        browser, page, errors = _start(pw, url)
        card = page.locator('#det0')
        # Output-only choices remain drafts until Save; explicit Is / Not is a
        # separate asynchronous archive transaction that commits immediately.
        card.get_by_role('button', name='Keep visible', exact=True).click()
        # Inject a network failure at the actual browser fetch boundary.
        page.evaluate('''() => {window.__workingFetch=window.fetch;
          window.fetch=(url,opts={})=>String(url).endsWith('/detections')&&opts.method==='POST'
            ?Promise.reject(new TypeError('Injected network failure')):window.__workingFetch(url,opts); }''')
        result = page.evaluate('''async()=>{try{return {ok:await saveAndRender(true)}}
           catch(e){return {unhandled:e.message}}}''')
        assert result == {'ok': False}, result
        assert page.evaluate('PLATE_REVIEW_BUSY') is False
        assert card.locator('.det-status').inner_text() == 'Will stay visible'
        assert json.loads(report.read_text())['detections'][0]['enabled'] is True
        page.evaluate('window.fetch=window.__workingFetch')
        _save(page)
        saved = json.loads(report.read_text())['detections'][0]
        assert saved['enabled'] is False and not saved.get('verified_label')
        assert confirmed_findings.list_findings(_archive(report))['total']==0
        assert not errors, errors
        browser.close()


def test_switching_jobs_cannot_render_wrong_job_during_save(review_server, monkeypatch):
    """Changing CUR while a save is in flight must not render the new job."""
    url, report = review_server
    first = web.JOBS['inline-fixture']
    folder = report.parent.parent / 'second-job'; folder.mkdir()
    (folder / 'report.json').write_text(report.read_text())
    second = dict(first, id='second-job', dir=str(folder), name='Second job',
                  cancel=threading.Event(), stop=threading.Event())
    web.JOBS['second-job'] = second
    queued = []; monkeypatch.setattr(web.WORK_Q, 'put', queued.append)
    api = pytest.importorskip('playwright.sync_api')
    with api.sync_playwright() as pw:
        browser, page, errors = _start(pw, url)
        card=page.locator('#det0');card.scroll_into_view_if_needed()
        page.wait_for_function('!!document.querySelector("#det0 img")._plateMeta')
        card.get_by_role('button', name='✕ Not a plate', exact=True).click()
        _confirmations_saved(page)
        page.evaluate('''() => {window.__workingFetch=window.fetch;
          window.fetch=async(url,opts={})=>{
            const r=await window.__workingFetch(url,opts);
            if(String(url).endsWith('/detections')&&opts.method==='POST')
              await new Promise(resolve=>window.__releaseDecision=resolve);
            return r;
          };window.__saveResult=saveAndRender();}''')
        page.wait_for_function('typeof window.__releaseDecision==="function"')
        # This is a real job navigation while the first response is delayed.
        page.get_by_role('link', name='Second job', exact=True).click()
        page.evaluate('window.__releaseDecision()')
        page.evaluate('window.__saveResult')
        assert ('second-job','render') not in queued, queued
        assert json.loads((folder/'report.json').read_text())['detections'][0]['enabled'] is True
        assert not errors, errors
        browser.close()


def test_decision_save_timeout_keeps_draft_and_allows_retry(review_server):
    """Headers arrive, body stalls: the save-only deadline still bounds the body.

    Accelerate only the 120s save timer; do not make the suite sleep two minutes.
    The separate slow-save case crosses 15s with actual wall-clock waiting.
    """
    url, report = review_server
    api = pytest.importorskip('playwright.sync_api')
    with api.sync_playwright() as pw:
        browser, page, errors = _start(pw, url)
        page.locator('#det0').get_by_role('button', name='Keep visible', exact=True).click()
        page.evaluate('''() => {window.__workingFetch=window.fetch;
          window.fetch=async(url,opts={})=>{
            if(String(url).endsWith('/detections')&&opts.method==='POST')
              return {ok:true,json:()=>new Promise((resolve,reject)=>{
                opts.signal?.addEventListener('abort',()=>reject(new DOMException('Timed out','AbortError')),{once:true});
              })};
            return window.__workingFetch(url,opts);
          };}''')
        page.evaluate('''()=>{window.__workingReviewRequest=reviewRequest;window.__saveTimers=[];
         reviewRequest=(url,options={},type='json')=>{
          if(String(url).endsWith('/detections')&&options.method==='POST'){
           __saveTimers.push(options.timeoutMs);
           return __workingReviewRequest(url,{...options,timeoutMs:150},type);
          }
          return __workingReviewRequest(url,options,type);
         };}''')
        result = page.evaluate('''async()=>{const start=Date.now();
          return {ok:await saveAndRender(true),elapsed:Date.now()-start};}''')
        assert result['ok'] is False
        assert page.evaluate('__saveTimers')==[120000]
        assert 120 <= result['elapsed'] < 5000, result
        page.evaluate('reviewRequest=window.__workingReviewRequest')
        assert page.evaluate('PLATE_REVIEW_BUSY') is False
        assert page.locator('#det0 .det-status').inner_text() == 'Will stay visible'
        assert json.loads(report.read_text())['detections'][0]['enabled'] is True
        page.evaluate('window.fetch=window.__workingFetch')
        _save(page)
        saved=json.loads(report.read_text())['detections'][0]
        assert saved['enabled'] is False and not saved.get('verified_label')
        assert confirmed_findings.list_findings(_archive(report))['total']==0
        assert not errors, errors
        browser.close()


def test_saved_geometry_and_decisions_survive_server_rehydration(review_server, monkeypatch):
    """Throw away in-memory jobs, recover from disk, then open a fresh browser view."""
    url, report = review_server
    doc=json.loads(report.read_text())
    for i,row in enumerate(doc['detections']):row['cbox']=_distinct_box(row,i)
    report.write_text(json.dumps(doc))
    api = pytest.importorskip('playwright.sync_api')
    with api.sync_playwright() as pw:
        browser, page, errors = _start(pw, url)
        card = page.locator('#det0'); card.scroll_into_view_if_needed()
        page.wait_for_function('!!document.querySelector("#det0 img")._quadEdit')
        drag_corner(page, card)
        assert page.evaluate('flushPlateSaves()') is True
        geometry = json.loads(report.read_text())['detections'][0]['plate_quad']
        card.get_by_role('button',name='✓ Is a plate',exact=True).click()
        _confirmations_saved(page)
        for i in range(1, 31):
            card=page.locator('#det%d' % i);card.scroll_into_view_if_needed()
            page.wait_for_function('(i)=>!!document.getElementById("thumb"+i)?._plateMeta',arg=i)
            card.get_by_role('button', name='✕ Not a plate', exact=True).click()
            _confirmations_saved(page)
        _save(page)
        before = report.read_bytes()
        archived_before=confirmed_findings.list_findings(_archive(report),limit=200)
        assert archived_before['total']==31
        images_before={entry['id']:confirmed_findings.image_path(_archive(report),entry['id']).read_bytes()
                       for entry in archived_before['items']}
        assert not (report.parent/'plate_annotations').exists()
        # Same disk rehydration entry point used at real process startup.
        monkeypatch.setattr(web, 'JOBS', {})
        monkeypatch.setattr(web, 'JOBS_DIR', str(report.parent.parent))
        web.rehydrate_jobs()
        recovered = web.JOBS['inline-fixture']
        assert recovered['phase'] == 'review'
        assert report.read_bytes() == before
        assert confirmed_findings.list_findings(_archive(report),limit=200)==archived_before
        assert all(confirmed_findings.image_path(_archive(report),identity).read_bytes()==jpeg
                   for identity,jpeg in images_before.items())
        if os.environ.get('REVIEW_INPROCESS') != '1':
            page.reload()
        # The in-process bridge cannot register its binding twice; rebuild the
        # actual job view against the recovered server registry in both modes.
        page.evaluate('openJob("inline-fixture")')
        page.locator("#det0").scroll_into_view_if_needed()
        page.wait_for_function('!!document.querySelector("#det0 img")?._quadEdit')
        assert json.loads(report.read_text())['detections'][0]['plate_quad'] == geometry
        for i in range(1, 31):
            assert page.locator('#det%d .det-status' % i).inner_text() == 'Will stay visible'
        assert not errors, errors
        browser.close()
