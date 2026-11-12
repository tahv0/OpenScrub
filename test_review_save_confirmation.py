"""Production Cheroot response and interrupted-review persistence regressions."""
import http.client
import json
import os
from pathlib import Path
import threading

import cv2
import numpy as np
import pytest

import openscrub_web as web
from test_review_browser import review_server, browser_instance, load_browser_page, drag_corner


@pytest.fixture
def production_server(review_server):
    """Use the production WSGI implementation, not Werkzeug's test server."""
    from cheroot.wsgi import Server
    errors = []
    hooks = {}
    def application(environ, start_response):
        response = web.app(environ, start_response)
        hook = hooks.pop(environ['PATH_INFO'], None)
        if hook:
            hook()
        return response
    server = Server(('127.0.0.1', 0), application, numthreads=8)
    server.error_log = lambda msg='', level=20, traceback=False: errors.append(str(msg))
    server.prepare()
    port = server.socket.getsockname()[1]
    thread = threading.Thread(target=server.serve, daemon=True)
    thread.start()
    yield 'http://127.0.0.1:%d' % port, review_server[1], errors, hooks
    server.stop()
    thread.join(5)


def _jpeg(noisy=False):
    image = (np.random.default_rng(91).integers(0, 256, (120, 240, 3), dtype=np.uint8)
             if noisy else np.zeros((120, 240, 3), np.uint8))
    ok, encoded = cv2.imencode('.jpg', image)
    assert ok
    return encoded.tobytes()


def test_live_preview_cheroot_content_length_survives_file_growth(production_server):
    url, report, errors, hooks = production_server
    initial, replacement = _jpeg(), _jpeg(True)
    assert len(replacement) > len(initial)
    path = report.parent / 'preview.jpg'
    path.write_bytes(initial)
    endpoint = '/api/jobs/inline-fixture/preview.jpg'
    # Exactly the old race: headers/file length were chosen, then the scanner
    # rewrites this same file before Cheroot consumes the response iterable.
    hooks[endpoint] = lambda: path.write_bytes(replacement)
    conn = http.client.HTTPConnection('127.0.0.1', int(url.rsplit(':', 1)[1]), timeout=5)
    try:
        conn.request('GET', endpoint)
        response = conn.getresponse()
        body = response.read()
        assert response.status == 200, (response.status, body)
        assert int(response.getheader('Content-Length')) == len(body)
        assert body == initial
        assert not errors, errors
    finally:
        conn.close()


def test_scan_preview_does_not_mutate_open_reader(review_server):
    _, report = review_server
    path = report.parent / 'preview.jpg'
    initial = _jpeg()
    path.write_bytes(initial)
    callback = web.WebCallbacks(web.JOBS['inline-fixture'])
    # A reader opened before publication must retain a complete old image.
    with path.open('rb') as reader:
        callback.scan_frame(np.random.default_rng(8).integers(0, 256, (360,640,3), dtype=np.uint8), 0, [])
        assert reader.read() == initial, "Preview publication mutated an already-open reader"
    assert cv2.imread(str(path)) is not None


@pytest.mark.parametrize('width', [1440, 390])
def test_save_choices_despite_failed_corner_then_refresh(production_server, monkeypatch, width, tmp_path):
    from flask import jsonify, request
    url, report, server_errors, _ = production_server
    web.JOBS['inline-fixture']['phase'] = 'paused'
    original = web.app.view_functions['job_plate_quad']
    def reject(*args, **kwargs):
        if request.method == 'POST':
            return jsonify(error='Injected stale corner conflict'), 409
        return original(*args, **kwargs)
    monkeypatch.setitem(web.app.view_functions, 'job_plate_quad', reject)
    queued = []
    monkeypatch.setattr(web.WORK_Q, 'put', queued.append)
    api = pytest.importorskip('playwright.sync_api')
    with api.sync_playwright() as pw:
        browser = browser_instance(pw)
        page = browser.new_page(viewport={'width': width, 'height': 1000 if width>400 else 844})
        page.set_default_timeout(10000)
        errors, dialogs = [], []
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.on('dialog', lambda d: (dialogs.append(d.message), d.accept()))
        load_browser_page(page, url, [], [])
        assert page.title() == 'OpenScrub'
        page.get_by_role('link', name='Synthetic review fixture', exact=True).click()
        page.locator('#review').wait_for()
        card = page.locator('#det0')
        card.scroll_into_view_if_needed()
        page.wait_for_function('!!document.querySelector("#det0 img")._quadEdit')
        drag_corner(page, card)
        page.wait_for_function('!!document.querySelector("#det0 img")._quadEdit.error')
        for i in range(1, 6):
            page.locator('#det%d' % i).get_by_role('button', name='✕ Not a plate', exact=True).click()
            page.evaluate('CONFIRM_CHAIN')
        page.get_by_role('button', name='Save review edits', exact=True).click()
        page.wait_for_function('PLATE_REVIEW_BUSY===false')
        saved = json.loads(report.read_text())['detections']
        assert all(not saved[i]['enabled'] and saved[i]['verified_label']=='not_plate' for i in range(1,6))
        assert not saved[0].get('plate_quad'), 'Failed geometry must not be advertised as saved'
        status = page.locator('#reviewSaveStatus')
        assert '1 corner' in status.inner_text() and 'not saved' in status.inner_text().lower()
        assert page.evaluate('plateEditsPending()')
        page.get_by_role('button', name='Train & rescan this video', exact=True).click()
        page.wait_for_function('PLATE_REVIEW_BUSY===false')
        assert not queued, queued
        assert 'blocked' in status.inner_text().lower()
        evidence=Path(os.environ.get('REVIEW_EVIDENCE_DIR',str(tmp_path)));evidence.mkdir(parents=True,exist_ok=True)
        status.scroll_into_view_if_needed();page.screenshot(path=str(evidence/('partial-save-%s.png'%width)))
        # Discard only this injected failed browser-only geometry, as a refresh
        # would. Recreate the view from disk and verify saved decisions remain.
        page.evaluate('''()=>{for(const s of PLATE_EDITS.values()){s.pending=null;s.drag=null;s.dirty=false;s.error=null;}
            closePlateQuad();}''')
        if os.environ.get('REVIEW_INPROCESS')!='1':
            page.reload()
        page.evaluate('openJob("inline-fixture")')
        page.locator('#review').wait_for()
        for i in range(1,6):
            assert page.locator('#det%d .det-status'%i).inner_text()=='Will stay visible'
        assert not errors, errors
        assert not server_errors, server_errors
        browser.close()


def test_decision_only_draft_has_unload_warning(production_server):
    url, _, _, _ = production_server
    api=pytest.importorskip('playwright.sync_api')
    with api.sync_playwright() as pw:
        browser=browser_instance(pw);page=browser.new_page()
        page.on('dialog',lambda d:d.accept())
        load_browser_page(page,url,[],[])
        page.get_by_role('link',name='Synthetic review fixture',exact=True).click()
        page.locator('#review').wait_for()
        page.locator('#det1').get_by_role('button',name='Keep visible',exact=True).click()
        pending=page.evaluate('''()=>{const e=new Event("beforeunload",{cancelable:true});window.dispatchEvent(e);return e.defaultPrevented;}''')
        assert pending is True
        assert page.evaluate('reviewFindingLabel(1)') == '', 'An output draft is not a human classification'
        assert page.evaluate('saveAndRender(true)') is True
        assert 'saved' in page.locator('#reviewSaveStatus').inner_text().lower()
        pending=page.evaluate('''()=>{const e=new Event("beforeunload",{cancelable:true});window.dispatchEvent(e);return e.defaultPrevented;}''')
        assert pending is False
        browser.close()


def test_preview_failed_publication_preserves_previous(review_server, monkeypatch):
    _, report = review_server
    target = report.parent/'preview.jpg';old=_jpeg();target.write_bytes(old)
    def fail(*args): raise OSError('Injected full disk / failed publication')
    monkeypatch.setattr(web.os, 'replace', fail)
    with pytest.raises(OSError, match='publication'):
        web.WebCallbacks(web.JOBS['inline-fixture']).scan_frame(np.ones((90,160,3),np.uint8),0,[])
    assert target.read_bytes()==old
    assert list(report.parent.glob('*.jpg'))==[target]


def test_new_decision_during_save_remains_unsaved(production_server):
    url, report, _, _ = production_server
    api=pytest.importorskip('playwright.sync_api')
    with api.sync_playwright() as pw:
        browser=browser_instance(pw);page=browser.new_page()
        page.on('dialog',lambda d:d.accept())
        load_browser_page(page,url,[],[])
        page.get_by_role('link',name='Synthetic review fixture',exact=True).click()
        card=page.locator('#det0');card.scroll_into_view_if_needed()
        page.wait_for_function('!!document.querySelector("#det0 img")._quadEdit')
        page.evaluate('''()=>{window.savedFetch=window.fetch;
         window.fetch=async(url,opts={})=>{const r=await window.savedFetch(url,opts);
          if(String(url).endsWith('/detections')&&opts.method==='POST')
            await new Promise(resolve=>window.releaseSaveResponse=resolve);return r;};
         window.saveOutcome=saveAndRender(true);}''')
        page.wait_for_function('typeof window.releaseSaveResponse==="function"')
        page.locator('#det1').get_by_role('button',name='Keep visible',exact=True).click()
        page.evaluate('window.releaseSaveResponse()')
        assert page.evaluate('window.saveOutcome') is False
        assert 'not saved' in page.locator('#reviewSaveStatus').inner_text().lower()
        assert page.evaluate('reviewChoicesPending()') is True
        assert json.loads(report.read_text())['detections'][1]['enabled'] is True
        page.evaluate('window.fetch=window.savedFetch')
        assert page.evaluate('saveAndRender(true)') is True
        assert json.loads(report.read_text())['detections'][1]['enabled'] is False
        assert not json.loads(report.read_text())['detections'][1].get('verified_label')
        page.evaluate('clearReviewPreviews();if(POLL)clearTimeout(POLL);')
        browser.close()
