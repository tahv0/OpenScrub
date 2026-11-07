"""Real Flask + Chromium review flow; no mocked images/geometry in the main test.

Run: pytest -q test_review_browser.py (requires Playwright and Chromium).
"""
import json
import base64
from urllib.parse import urlsplit
import os
from pathlib import Path
import shutil
import threading

import cv2
import numpy as np
import pytest
from werkzeug.serving import make_server

import openscrub_web as web


@pytest.fixture
def review_server(tmp_path, monkeypatch):
    job_dir = tmp_path / 'inline-fixture'
    job_dir.mkdir()
    video = job_dir / 'review.mp4'
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*'mp4v'), 30, (640, 360))
    assert writer.isOpened()
    for i in range(310):
        frame = np.full((360, 640, 3), (65, 92, 118), np.uint8)
        cv2.rectangle(frame, (180, 120), (420, 220), (220, 230, 240), -1)
        cv2.putText(frame, 'DEMO', (207, 180), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (25, 30, 40), 3)
        cv2.putText(frame, 'Synthetic review fixture', (25, 40), cv2.FONT_HERSHEY_SIMPLEX, .7, (240, 240, 240), 1)
        writer.write(frame)
    writer.release()
    rows = [dict(t_start=10., t_end=10., last_seen=10., frame_index=300,
                 cbox=[180, 120, 420, 220], aoff=[0, 0], category='plate',
                 text='DEMO (synthetic)', confidence=.95, enabled=True,
                 dense=True, track=i, person=-1) for i in range(90)]
    doc = {'render_state': {'fps': 30, 'cum': [[0, 0]]*310, 'bands': [[0, 0]]*310},
           'detections': rows, 'provenance': {'input': str(video)}}
    report = job_dir / 'report.json'
    report.write_text(json.dumps(doc))
    job = dict(id='inline-fixture', dir=str(job_dir), video=str(video), name='Synthetic review fixture',
               phase='review', progress=1., error=None, stats={}, log=[], output=None,
               created=0, options={}, cancel=threading.Event(), stop=threading.Event())
    monkeypatch.setattr(web, 'JOBS', {job['id']: job})
    monkeypatch.setattr(web, 'TOKEN', None)
    monkeypatch.setattr(web, 'openscrub_update', None)  # No external update check in offline QA.
    server = make_server('127.0.0.1', 0, web.app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield 'http://127.0.0.1:%s' % server.server_port, report
    server.shutdown(); thread.join(timeout=5)


def browser_instance(playwright):
    executable = os.environ.get('CHROMIUM_EXECUTABLE') or shutil.which('chromium')
    return playwright.chromium.launch(headless=True, executable_path=executable,
                                      args=['--no-sandbox'])


def load_browser_page(page, url, requests, posts):
    if os.environ.get('REVIEW_INPROCESS') == '1':
        # Restricted local Chromium blocks loopback; CI uses real HTTP.
        def serve(input_url, options):
            requests.append(input_url)
            split = urlsplit(input_url)
            path = split.path if split.path.startswith('/') else '/'+split.path
            if split.query: path += '?'+split.query
            if options.get('method') == 'POST' and '/plate_quad/' in path:
                posts.append(json.loads(options['body']))
            with web.app.test_client() as client:
                r = client.open(path, method=options.get('method') or 'GET',
                                data=options.get('body'), headers=options.get('headers') or {})
                return dict(status=r.status_code, headers=dict(r.headers),
                            body=base64.b64encode(r.data).decode())
        page.expose_function('__flaskFetch', serve)
        page.evaluate("""() => {window.fetch=async(url,options={})=>{
          const r=await window.__flaskFetch(String(url),{method:options.method,body:options.body,headers:options.headers});
          return new Response(r.status===204?null:Uint8Array.from(atob(r.body),c=>c.charCodeAt(0)),{status:r.status,headers:r.headers});
        };}""")
        with web.app.test_client() as client:
            page.set_content(client.get('/').get_data(as_text=True), wait_until='domcontentloaded')
    else:
        page.goto(url)


def plate_points(card):
    return card.locator('img').evaluate('(img)=>img._quadEdit.points.map(p=>p.slice())')


def drag_corner(page, card, index=0, dx=9, dy=5, release=True):
    handle = card.locator('img').evaluate('''(img,k) => {
      const q=img._quadEdit,c=q.meta.crop,r=q.cv.getBoundingClientRect(),p=q.points[k];
      return {x:r.left+(p[0]-c[0])*r.width/(c[2]-c[0]),
              y:r.top+(p[1]-c[1])*r.height/(c[3]-c[1])};
    }''', index)
    page.mouse.move(handle['x'], handle['y']);page.mouse.down()
    page.mouse.move(handle['x']+dx, handle['y']+dy, steps=6)
    if release: page.mouse.up()


@pytest.mark.parametrize('viewport', [(1440, 1000), (390, 844)])
def test_real_direct_corner_autosave_and_lazy_loading(review_server, viewport, tmp_path):
    sync_api = pytest.importorskip('playwright.sync_api')
    url, report = review_server
    with sync_api.sync_playwright() as pw:
        browser = browser_instance(pw)
        page = browser.new_page(viewport={'width': viewport[0], 'height': viewport[1]})
        page.set_default_timeout(10000)
        errors, requests, posts = [], [], []
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.on('request', lambda r: requests.append(r.url))
        page.on('request', lambda r: posts.append(r.post_data_json) if r.method=='POST' and '/plate_quad/' in r.url else None)
        load_browser_page(page,url,requests,posts)
        assert page.title() == 'OpenScrub'
        page.get_by_role('link', name='Synthetic review fixture', exact=True).click()
        page.locator('#review').wait_for()
        assert page.locator('#review .det').count() == 90
        card = page.locator('#det0')
        card.scroll_into_view_if_needed()
        page.wait_for_function("document.querySelector('#det0 img').naturalWidth > 0")
        assert card.get_by_role('button', name='Edit 4 corners', exact=True).count() == 0
        assert page.locator('#qSave,#qClose,#qTrack,#qRotateRight,#plateQuadEditor').count() == 0
        page.wait_for_function("!!document.querySelector('#det0 img')._quadEdit")
        initial, size = plate_points(card), card.bounding_box()
        before_requests = sum('/thumb/0' in r for r in requests)
        assert sum('/thumb/' in r for r in requests) < 35
        drag_corner(page, card, release=False)
        assert not posts  # no requests during mousemove
        page.mouse.up()
        page.wait_for_function("document.querySelector('#det0 .quad-status').textContent.startsWith('Saved')")
        moved = plate_points(card)
        assert moved[0] != initial[0] and moved[1:] == initial[1:]
        assert len(posts) == 1 and posts[0]['apply_track'] is True and posts[0]['autosave'] is True
        stored = json.loads(report.read_text())['detections'][0]
        assert len(stored['plate_quad']) == 4 and stored['verified_label'] == 'plate'
        assert sum('/thumb/0' in r for r in requests) == before_requests
        assert not any('/plate_quad/' in r and r.endswith('/frame') for r in requests)
        assert abs(card.bounding_box()['width']-size['width']) < 1
        assert not card.evaluate('(el)=>el.classList.contains("editing") || el.classList.contains("selected")')
        assert page.locator('.marq').count() == 0
        # Escape cancels an unfinished drag, not the last saved geometry.
        drag_corner(page, card, index=1, dx=-4, dy=3, release=False)
        page.keyboard.press('Escape');page.mouse.up()
        assert plate_points(card) == moved
        assert len(posts) == 1
        # Keyboard access needs no edit-mode click either.
        card.locator('canvas').focus();page.keyboard.press('3');page.keyboard.press('ArrowLeft')
        page.wait_for_function("document.querySelector('#det0 .quad-status').textContent.startsWith('Saved')")
        latest = plate_points(card)
        assert latest[2][0] < moved[2][0]
        card.get_by_role('button', name='Keep visible', exact=True).click()
        assert page.evaluate('EN[0]') is False
        card.get_by_role('button', name='Blur', exact=True).click()
        assert page.evaluate('EN[0]') is True
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        evidence = Path(os.environ.get('REVIEW_EVIDENCE_DIR', str(tmp_path)))
        evidence.mkdir(parents=True, exist_ok=True)
        card.screenshot(path=str(evidence/('direct-corners-%s.png' % viewport[0])))
        # A different finding can be edited immediately; reopening persists both.
        other = page.locator('#det1');other.scroll_into_view_if_needed()
        page.wait_for_function("!!document.querySelector('#det1 img')._quadEdit")
        drag_corner(page, other)
        # Navigation flushes the debounce instead of asking for Save/Done.
        old_review = page.locator('#review').element_handle()
        page.get_by_role('link', name='Synthetic review fixture', exact=True).click()
        page.wait_for_function('(old)=>!old.isConnected', arg=old_review)
        page.locator('#review').wait_for()
        page.locator('#det0').scroll_into_view_if_needed()
        page.wait_for_function("!!document.querySelector('#det0 img')._quadEdit")
        assert max(abs(a-b) for p,q in zip(plate_points(page.locator('#det0')),latest) for a,b in zip(p,q)) < .001
        assert json.loads(report.read_text())['detections'][1].get('plate_quad')
        assert not errors, errors
        browser.close()


def test_cached_card_loads_while_another_preview_is_decoding(review_server, monkeypatch, tmp_path):
    """A cold card must not block a ready card behind it in browser or server."""
    sync_api = pytest.importorskip('playwright.sync_api')
    url, _ = review_server
    with web.app.test_client() as client:
        assert client.get('/api/jobs/inline-fixture/thumb/1').status_code == 200
    entered, release = threading.Event(), threading.Event()
    original = web._frame_at
    calls = []
    def slow(*args, **kwargs):
        calls.append(True)
        entered.set()
        assert release.wait(15), 'test failed to release the decoder'
        return original(*args, **kwargs)
    monkeypatch.setattr(web, '_frame_at', slow)
    try:
        with sync_api.sync_playwright() as pw:
            browser = browser_instance(pw)
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.goto(url)
            page.get_by_role('link', name='Synthetic review fixture', exact=True).click()
            page.locator('#review').wait_for()
            page.locator('#det0').scroll_into_view_if_needed()
            page.wait_for_function(
                "document.querySelector('#det1 img').naturalWidth > 0", timeout=5000)
            assert entered.wait(2)
            assert not release.is_set()
            assert page.locator('#det0 img').evaluate('(img)=>img.naturalWidth') == 0
            card = page.locator('#det1')
            page.wait_for_function("!!document.querySelector('#det1 img')._quadEdit")
            before = plate_points(card)
            drag_corner(page, card)
            assert plate_points(card) != before
            assert len(calls) == 1
            assert not errors
            evidence = Path(os.environ.get('REVIEW_EVIDENCE_DIR', str(tmp_path)))
            evidence.mkdir(parents=True, exist_ok=True)
            page.locator('#review').screenshot(path=str(evidence/'cached-while-decoding.png'))
            release.set()
            page.wait_for_function("document.querySelector('#det0 img').naturalWidth > 0")
            browser.close()
    finally:
        release.set()


def test_autosave_failure_keeps_draft_and_blocks_render_until_retry(review_server, monkeypatch):
    sync_api = pytest.importorskip('playwright.sync_api')
    url, report = review_server
    from flask import request, jsonify
    original = web.app.view_functions['job_plate_quad']
    attempts = []
    def flaky(*args, **kwargs):
        if request.method == 'POST':
            attempts.append(request.get_json())
            if len(attempts) == 1:
                return jsonify(error='Injected save failure'), 500
        return original(*args, **kwargs)
    monkeypatch.setitem(web.app.view_functions, 'job_plate_quad', flaky)
    with sync_api.sync_playwright() as pw:
        browser = browser_instance(pw)
        page = browser.new_page(viewport={'width':1440,'height':1000})
        load_browser_page(page,url,[],[])
        page.get_by_role('link', name='Synthetic review fixture', exact=True).click()
        card = page.locator('#det0');card.scroll_into_view_if_needed()
        page.wait_for_function("!!document.querySelector('#det0 img')._quadEdit")
        drag_corner(page,card)
        moved = plate_points(card)
        card.get_by_role('button',name='Retry save',exact=True).wait_for()
        assert plate_points(card) == moved
        assert page.evaluate('saveAndRender(true)') is False
        assert not json.loads(report.read_text())['detections'][0].get('plate_quad')
        assert page.evaluate("() => {const e=new Event('beforeunload',{cancelable:true});window.dispatchEvent(e);return e.defaultPrevented;}")
        card.get_by_role('button',name='Retry save',exact=True).click()
        page.wait_for_function("document.querySelector('#det0 .quad-status').textContent.startsWith('Saved')")
        assert attempts[0]['edit_id'] == attempts[1]['edit_id']
        assert json.loads(report.read_text())['detections'][0].get('plate_quad')
        # Crossing corners and cancelled touch/pointer gestures never get saved.
        before = plate_points(card)
        drag_corner(page,card,index=0,dx=140,dy=25)
        assert plate_points(card) == before
        assert page.evaluate('flushPlateSaves()') is True
        assert len(attempts) == 2
        drag_corner(page,card,index=0,release=False)
        pointer_id = card.locator('img').evaluate('img=>img._quadEdit.drag.id')
        card.locator('canvas').dispatch_event('pointercancel',{'pointerId':pointer_id})
        page.mouse.up()
        assert plate_points(card) == before and len(attempts) == 2
        browser.close()


def test_touch_corner_drag_autosaves(review_server):
    sync_api = pytest.importorskip('playwright.sync_api')
    url, report = review_server
    with sync_api.sync_playwright() as pw:
        browser = browser_instance(pw)
        page = browser.new_page(viewport={'width':390,'height':844},has_touch=True,is_mobile=True)
        load_browser_page(page,url,[],[])
        page.get_by_role('link', name='Synthetic review fixture', exact=True).click()
        card=page.locator('#det0');card.scroll_into_view_if_needed()
        page.wait_for_function("!!document.querySelector('#det0 img')._quadEdit")
        before = plate_points(card)
        point = card.locator('img').evaluate('''img=>{
          const q=img._quadEdit,c=q.meta.crop,r=q.cv.getBoundingClientRect(),p=q.points[0];
          return {x:r.left+(p[0]-c[0])*r.width/(c[2]-c[0]),
                  y:r.top+(p[1]-c[1])*r.height/(c[3]-c[1])};}''')
        cdp = page.context.new_cdp_session(page)
        cdp.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[point]})
        cdp.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[{'x':point['x']+12,'y':point['y']+7}]})
        cdp.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]})
        page.wait_for_function("document.querySelector('#det0 .quad-status').textContent.startsWith('Saved')")
        assert plate_points(card)[0] != before[0]
        assert json.loads(report.read_text())['detections'][0].get('plate_quad')
        browser.close()
