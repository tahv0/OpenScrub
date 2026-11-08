"""Production Cheroot response races and paused-review save/refresh recovery.

All videos are synthetic. CI runs a real browser against Cheroot. The explicit
REVIEW_INPROCESS bridge only supports restricted local Chromium environments.
"""
import json
import os
from pathlib import Path
import threading
import urllib.request

import pytest
import openscrub_web as web
from test_review_browser import review_server, browser_instance, load_browser_page, drag_corner


@pytest.fixture
def cheroot_review(review_server, monkeypatch):
    from cheroot.wsgi import Server
    _, report = review_server
    logs = []
    server = Server(('127.0.0.1', 0), web.app, numthreads=8)
    server.error_log = lambda message='', **kw: logs.append(str(message))
    server.prepare()
    thread = threading.Thread(target=server.serve, daemon=True)
    thread.start()
    try:
        yield 'http://127.0.0.1:%d' % server.socket.getsockname()[1], report, logs
    finally:
        server.stop(); thread.join(timeout=5)


@pytest.mark.parametrize('kind', ['preview', 'report', 'thumb'])
def test_cheroot_mutable_file_has_consistent_content_length(cheroot_review, monkeypatch, kind):
    """Reproduce grow-after-header races at the actual Cheroot WSGI boundary."""
    url, report, logs = cheroot_review
    if kind == 'preview':
        name, route, endpoint = 'preview.jpg', '/preview.jpg', 'job_preview'
    elif kind == 'thumb':
        name, route, endpoint = 'thumb2_0.jpg', '/thumb/0', 'job_thumb'
        doc = json.loads(report.read_text()); doc['detections'][0]['category'] = 'name'
        report.write_text(json.dumps(doc))
    else:
        name, route, endpoint = 'report.json', '/report', 'job_report'
    path = report.parent / name
    initial = path.read_bytes() if kind == 'report' else b'\xff\xd8initial-preview\xff\xd9'
    path.write_bytes(initial)
    original = web.app.view_functions[endpoint]
    def grow_after_response(*args, **kwargs):
        response = original(*args, **kwargs)
        # Legacy send_file already advertised the smaller size, but has not
        # consumed the file. This write is what the live preview producer does.
        path.write_bytes(initial + b'X' * 20000)
        return response
    monkeypatch.setitem(web.app.view_functions, endpoint, grow_after_response)
    try:
        with urllib.request.urlopen(url+'/api/jobs/inline-fixture'+route, timeout=5) as r:
            body = r.read()
            assert r.status == 200
            assert int(r.headers['Content-Length']) == len(body)
            assert body == initial
    except urllib.error.HTTPError as error:
        pytest.fail('Cheroot rejected mutable-file response: HTTP %s: %s' % (error.code, error.read()))
    assert not any('Content-Length' in entry for entry in logs), logs


def _paused(report):
    job = web.JOBS['inline-fixture']; job['phase'] = 'paused'
    job.update(checkpoint_frame=310, checkpoint_total=600)
    doc = json.loads(report.read_text())
    doc['stop_review'] = {'state': 'paused', 'next_frame': 310, 'total_frames': 600, 'fps': 30}
    report.write_text(json.dumps(doc))


def _open(pw, url, width=1440, browser=None, storage=None):
    browser = browser or browser_instance(pw)
    page = browser.new_page(viewport={'width': width, 'height': 1000 if width > 400 else 844})
    page.set_default_timeout(12000)
    errors, dialogs = [], []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.on('dialog', lambda d: (dialogs.append(d.message), d.accept()))
    if os.environ.get('REVIEW_INPROCESS') == '1':
        # Explicit local-only storage stand-in: about:blank has an opaque origin.
        # CI does NOT use this; it reloads the real same-origin browser tab.
        page.evaluate('''data=>{const m=new Map(Object.entries(data));Object.defineProperty(window,'sessionStorage',{
          value:{getItem:k=>m.get(k)||null,setItem:(k,v)=>m.set(k,String(v)),removeItem:k=>m.delete(k),
            key:i=>[...m.keys()][i],get length(){return m.size}}});}''', storage or {})
    load_browser_page(page, url, [], [])
    page.get_by_role('link', name='Synthetic review fixture', exact=True).click()
    page.locator('#review').wait_for()
    return browser, page, errors, dialogs


def _reload(pw, browser, page, url, width):
    if os.environ.get('REVIEW_INPROCESS') == '1':
        store = page.evaluate('Object.fromEntries(Array.from({length:sessionStorage.length},(_,i)=>{const k=sessionStorage.key(i);return [k,sessionStorage.getItem(k)]}))')
        page.close()
        _, page, _, _ = _open(pw, url, width, browser, store)
    else:
        page.reload()
        page.get_by_role('link', name='Synthetic review fixture', exact=True).click()
        page.locator('#review').wait_for()
    return page


def _fail_corners(monkeypatch):
    from flask import request, jsonify
    original = web.app.view_functions['job_plate_quad']
    def fail(*args, **kwargs):
        if request.method == 'POST':
            return jsonify(error='Injected conflict on a still-positive finding'), 409
        return original(*args, **kwargs)
    monkeypatch.setitem(web.app.view_functions, 'job_plate_quad', fail)
    return original


@pytest.mark.parametrize('width', [1440, 390])
def test_paused_save_keeps_fifty_decisions_despite_failed_positive_corner(cheroot_review, monkeypatch, tmp_path, width):
    url, report, logs = cheroot_review; _paused(report)
    _fail_corners(monkeypatch)
    api = pytest.importorskip('playwright.sync_api')
    with api.sync_playwright() as pw:
        browser, page, errors, dialogs = _open(pw, url, width)
        card = page.locator('#det0'); card.scroll_into_view_if_needed()
        page.wait_for_function('!!document.querySelector("#det0 img")._quadEdit')
        drag_corner(page, card)
        page.wait_for_function('!!document.querySelector("#det0 img")._quadEdit.error')
        for i in range(1, 51):
            page.locator('#det%d' % i).get_by_role('button', name='✕ Not a plate', exact=True).click()
        page.get_by_role('button', name='Save review edits', exact=True).click()
        page.wait_for_function('!PLATE_REVIEW_BUSY')
        stored = json.loads(report.read_text())['detections']
        assert all(r['enabled'] is False and r.get('verified_label') == 'not_plate' for r in stored[1:51]), 'A failed positive corner blocked all 50 decisions'
        status = page.locator('#reviewSaveStatus').inner_text()
        assert 'decisions saved' in status.lower() and 'corner' in status.lower() and 'not saved' in status.lower()
        assert not stored[0].get('plate_quad'), 'A failed corner must not be reported as persisted'
        page.get_by_role('button', name='Train & rescan this video', exact=True).click()
        page.wait_for_function('!PLATE_REVIEW_BUSY')
        assert web.JOBS['inline-fixture']['phase'] == 'paused'
        assert 'not started' in page.locator('#reviewSaveStatus').inner_text().lower()
        page = _reload(pw, browser, page, url, width)
        for i in range(1, 51):
            assert page.locator('#det%d .det-status' % i).inner_text() == 'Will stay visible'
        assert 'recover' in page.locator('#reviewSaveStatus').inner_text().lower()
        assert not errors, errors
        out = Path(os.environ.get('REVIEW_EVIDENCE_DIR', str(tmp_path))); out.mkdir(exist_ok=True, parents=True)
        page.screenshot(path=str(out/('saved-decisions-failed-corner-%d.png' % width)))
        browser.close()
    assert not logs, logs


def test_failed_decision_request_survives_full_page_refresh(cheroot_review, monkeypatch):
    from flask import request, jsonify
    url, report, _ = cheroot_review; _paused(report)
    original = web.app.view_functions['job_save_edits']
    monkeypatch.setitem(web.app.view_functions, 'job_save_edits', lambda **kw: (jsonify(error='Injected offline save'), 502))
    api = pytest.importorskip('playwright.sync_api')
    with api.sync_playwright() as pw:
        browser, page, errors, _ = _open(pw, url)
        page.locator('#det5').get_by_role('button', name='✕ Not a plate', exact=True).click()
        page.get_by_role('button', name='Save review edits', exact=True).click()
        page.wait_for_function('!PLATE_REVIEW_BUSY')
        assert json.loads(report.read_text())['detections'][5]['enabled'] is True
        page = _reload(pw, browser, page, url, 1440)
        assert page.locator('#det5 .det-status').inner_text() == 'Will stay visible', 'Reload lost the unsent decision'
        assert 'recover' in page.locator('#reviewSaveStatus').inner_text().lower()
        monkeypatch.setitem(web.app.view_functions, 'job_save_edits', original)
        page.get_by_role('button', name='Save review edits', exact=True).click()
        page.wait_for_function('!PLATE_REVIEW_BUSY')
        assert json.loads(report.read_text())['detections'][5]['verified_label'] == 'not_plate'
        assert 'saved' in page.locator('#reviewSaveStatus').inner_text().lower()
        assert not errors, errors
        browser.close()


def test_decision_draft_is_not_applied_to_changed_report(cheroot_review):
    url, report, _ = cheroot_review; _paused(report)
    api = pytest.importorskip('playwright.sync_api')
    with api.sync_playwright() as pw:
        browser, page, errors, _ = _open(pw, url)
        page.locator('#det5').get_by_role('button', name='✕ Not a plate', exact=True).click()
        doc=json.loads(report.read_text()); doc['detections'][5]['frame_index']=299
        report.write_text(json.dumps(doc))
        page = _reload(pw, browser, page, url, 1440)
        assert page.locator('#det5 .det-status').inner_text() == 'Will be blurred'
        assert 'different' in page.locator('#reviewSaveStatus').inner_text().lower()
        assert 'not applied' in page.locator('#reviewSaveStatus').inner_text().lower()
        assert not errors, errors
        browser.close()


def test_old_review_identity_refuses_write_without_mutating_report(cheroot_review):
    _, report, _ = cheroot_review
    with web.app.test_client() as client:
        identity = client.get('/api/jobs/inline-fixture/detections').json['review_identity']
        doc = json.loads(report.read_text()); doc['detections'][0]['frame_index'] = 299
        report.write_text(json.dumps(doc)); before = report.read_bytes()
        response = client.post('/api/jobs/inline-fixture/detections', json={
            'review_identity': identity, 'enabled': {'0': False}, 'verified_labels': {'0': 'not_plate'}})
    assert response.status_code == 409
    assert report.read_bytes() == before


def test_preview_publication_preserves_open_reader_snapshot(cheroot_review):
    import cv2
    import numpy as np
    _, report, _ = cheroot_review
    path = report.parent/'preview.jpg'
    path.write_bytes(b'old-in-flight-preview')
    with path.open('rb') as old:
        web._publish_preview_jpeg(str(path), np.zeros((50, 80, 3), np.uint8), 70)
        assert old.read() == b'old-in-flight-preview'
    assert cv2.imread(str(path)).shape[:2] == (50, 80)


def test_snapshot_head_and_range_keep_correct_length(cheroot_review):
    url, report, logs = cheroot_review
    data=b'0123456789'*100
    (report.parent/'preview.jpg').write_bytes(data)
    with urllib.request.urlopen(urllib.request.Request(url+'/api/jobs/inline-fixture/preview.jpg',method='HEAD')) as r:
        assert int(r.headers['Content-Length']) == len(data) and r.read() == b''
    req=urllib.request.Request(url+'/api/jobs/inline-fixture/preview.jpg',headers={'Range':'bytes=10-24'})
    with urllib.request.urlopen(req) as r:
        assert r.status == 206 and r.read() == data[10:25]
        assert int(r.headers['Content-Length']) == 15
    assert not logs


def test_recovered_corner_can_be_retried_and_training_can_be_queued(cheroot_review, monkeypatch, tmp_path):
    url, report, _=cheroot_review;_paused(report)
    original = _fail_corners(monkeypatch)
    weights=tmp_path/'test-seg.pt';weights.write_bytes(b'fixture not executed')
    monkeypatch.setenv('OPENSCRUB_TRAIN_WEIGHTS',str(weights))
    queued=[];monkeypatch.setattr(web.WORK_Q,'put',queued.append)
    api=pytest.importorskip('playwright.sync_api')
    with api.sync_playwright() as pw:
        browser,page,errors,_=_open(pw,url)
        card=page.locator('#det0');card.scroll_into_view_if_needed()
        page.wait_for_function('!!document.querySelector("#det0 img")._quadEdit')
        drag_corner(page,card)
        page.wait_for_function('!!document.querySelector("#det0 img")._quadEdit.error')
        wanted=card.locator('img').evaluate('img=>img._quadEdit.points')
        page.get_by_role('button',name='Save review edits',exact=True).click()
        page.wait_for_function('!PLATE_REVIEW_BUSY')
        page=_reload(pw,browser,page,url,1440)
        page.wait_for_function('!!document.querySelector("#det0 img")._quadEdit')
        card=page.locator('#det0')
        assert card.locator('img').evaluate('img=>img._quadEdit.points') == wanted
        monkeypatch.setitem(web.app.view_functions,'job_plate_quad',original)
        card.get_by_role('button',name='Retry save',exact=True).click()
        page.wait_for_function('!document.querySelector("#det0 img")._quadEdit.dirty')
        page.get_by_role('button',name='Train & rescan this video',exact=True).click()
        page.wait_for_function('!document.getElementById("review")')
        assert ('inline-fixture','learn') in queued
        assert not errors,errors
        browser.close()


def test_lost_corner_response_then_refresh_does_not_duplicate_sample(cheroot_review, monkeypatch):
    from flask import request, jsonify
    url, report, _=cheroot_review;_paused(report)
    original=web.app.view_functions['job_plate_quad'];writes=[]
    def lose_reply(*args,**kwargs):
        result=original(*args,**kwargs)
        if request.method=='POST':
            writes.append(request.get_json())
            return jsonify(error='Injected lost receipt after commit'),502
        return result
    monkeypatch.setitem(web.app.view_functions,'job_plate_quad',lose_reply)
    api=pytest.importorskip('playwright.sync_api')
    with api.sync_playwright() as pw:
        browser,page,errors,_=_open(pw,url)
        page.locator('#det0').scroll_into_view_if_needed()
        page.wait_for_function('!!document.querySelector("#det0 img")._quadEdit')
        drag_corner(page,page.locator('#det0'))
        page.wait_for_function('!!document.querySelector("#det0 img")._quadEdit.error')
        assert json.loads(report.read_text())['detections'][0].get('plate_quad')
        page=_reload(pw,browser,page,url,1440)
        page.wait_for_function('!!document.querySelector("#det0 img")._quadEdit')
        assert page.evaluate('!plateEditsPending()')
        assert len(writes)==1
        assert len((report.parent/'plate_annotations'/'annotations.jsonl').read_text().splitlines())==1
        page.get_by_role('button',name='Save review edits',exact=True).click()
        page.wait_for_function('!PLATE_REVIEW_BUSY')
        assert page.evaluate('!reviewHasDraft()')
        assert not errors,errors
        browser.close()


def test_new_decision_during_save_remains_recoverable_and_blocks_render(cheroot_review):
    url, report, _=cheroot_review;_paused(report)
    api=pytest.importorskip('playwright.sync_api')
    with api.sync_playwright() as pw:
        browser,page,errors,_=_open(pw,url)
        page.locator('#det1').get_by_role('button',name='✕ Not a plate',exact=True).click()
        page.evaluate('''()=>{window.__goodFetch=window.fetch;window.fetch=async(url,opts={})=>{
          const r=await __goodFetch(url,opts);
          if(String(url).endsWith('/detections')&&opts.method==='POST')await new Promise(ok=>window.__releaseSave=ok);
          return r;};}''')
        page.get_by_role('button',name='Save review edits',exact=True).click()
        page.wait_for_function('typeof __releaseSave==="function"')
        page.locator('#det2').get_by_role('button',name='✕ Not a plate',exact=True).click()
        page.evaluate('__releaseSave()')
        page.wait_for_function('!PLATE_REVIEW_BUSY')
        stored=json.loads(report.read_text())['detections']
        assert stored[1]['enabled'] is False and stored[2]['enabled'] is True
        assert 'newer changes' in page.locator('#reviewSaveStatus').inner_text().lower()
        page=_reload(pw,browser,page,url,1440)
        assert page.locator('#det2 .det-status').inner_text()=='Will stay visible'
        assert page.evaluate('reviewHasDraft()')
        assert not errors,errors
        browser.close()


def test_failed_corner_and_saved_decisions_survive_rehydration(cheroot_review, monkeypatch):
    url, report, _=cheroot_review;_paused(report)
    _fail_corners(monkeypatch)
    api=pytest.importorskip('playwright.sync_api')
    with api.sync_playwright() as pw:
        browser,page,errors,_=_open(pw,url)
        page.locator('#det0').scroll_into_view_if_needed()
        page.wait_for_function('!!document.querySelector("#det0 img")._quadEdit')
        drag_corner(page,page.locator('#det0'))
        page.wait_for_function('!!document.querySelector("#det0 img")._quadEdit.error')
        page.locator('#det1').get_by_role('button',name='✕ Not a plate',exact=True).click()
        page.get_by_role('button',name='Save review edits',exact=True).click()
        page.wait_for_function('!PLATE_REVIEW_BUSY')
        snapshot=report.read_bytes()
        monkeypatch.setattr(web,'JOBS',{})
        monkeypatch.setattr(web,'JOBS_DIR',str(report.parent.parent))
        web.rehydrate_jobs()
        assert report.read_bytes()==snapshot
        # The recovered name is the source basename, unlike the synthetic title.
        web.JOBS['inline-fixture']['name']='Synthetic review fixture'
        page=_reload(pw,browser,page,url,1440)
        assert page.locator('#det1 .det-status').inner_text()=='Will stay visible'
        assert not errors,errors
        browser.close()
