"""Real Flask + Chromium review flow; no mocked images/geometry in the main test.

Run: pytest -q test_review_browser.py (requires Playwright and Chromium).
"""
import json
import hashlib
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
           'detections': rows,
           'source_identity': {'width':640, 'height':360, 'fps':30, 'total_frames':310},
           'provenance': {'input':str(video), 'input_sha256':hashlib.sha256(video.read_bytes()).hexdigest()}}
    report = job_dir / 'report.json'
    report.write_text(json.dumps(doc))
    job = dict(id='inline-fixture', dir=str(job_dir), video=str(video), name='Synthetic review fixture',
               phase='review', progress=1., error=None, stats={}, log=[], output=None,
               created=0, options={}, cancel=threading.Event(), stop=threading.Event())
    monkeypatch.setattr(web, 'JOBS_DIR', str(tmp_path))
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
        before_requests = sum('/finding-preview/0' in r for r in requests)
        assert sum('/finding-preview/' in r for r in requests) < 35
        drag_corner(page, card, release=False)
        assert not posts  # no requests during mousemove
        page.mouse.up()
        page.wait_for_function("document.querySelector('#det0 .quad-status').textContent.startsWith('Saved area')")
        moved = plate_points(card)
        assert moved[0] != initial[0] and moved[1:] == initial[1:]
        assert len(posts) == 1 and posts[0]['apply_track'] is True and posts[0]['autosave'] is True
        stored = json.loads(report.read_text())['detections'][0]
        assert len(stored['plate_quad']) == 4 and not stored.get('verified_label')
        with web.app.test_client() as client:
            assert client.get('/api/findings').get_json()['total'] == 0, 'An area adjustment alone is not explicit evidence'
        assert sum('/finding-preview/0' in r for r in requests) == before_requests
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
        page.wait_for_function("document.querySelector('#det0 .quad-status').textContent.startsWith('Saved area')")
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
    url, report = review_server
    # Keep cold0 first, warm1 second, and filler cards later in timeline order.
    # Distinct exact source frames make one JPEG warm while another stays cold.
    doc=json.loads(report.read_text())
    for row in doc['detections']:
        row.update(frame_index=301,t_start=301/30,t_end=301/30,last_seen=301/30)
    doc['detections'][0].update(frame_index=299,t_start=299/30,t_end=299/30,last_seen=299/30)
    doc['detections'][1].update(frame_index=300,t_start=10.,t_end=10.,last_seen=10.)
    report.write_text(json.dumps(doc))
    with web.app.test_client() as client:
        assert client.get('/api/jobs/inline-fixture/finding-preview/1').status_code == 200
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
            # Hold the warm card at fetch until the server's cold decoder is
            # definitely blocked. A warm image loaded earlier would not prove
            # that cached reads can complete concurrently with a cold decode.
            page.evaluate(r'''()=>{
              const original=window.fetch;
              window.__warmAllowed=new Promise(resolve=>window.__releaseWarm=resolve);
              window.fetch=async(url,options)=>{
                if(/\/finding-preview\/1(?:[?]|$)/.test(String(url)))await window.__warmAllowed;
                return original(url,options);
              };
            }''')
            page.get_by_role('link', name='Synthetic review fixture', exact=True).click()
            page.locator('#review').wait_for()
            page.locator('#det0').scroll_into_view_if_needed()
            assert entered.wait(5), 'the cold decoder never started'
            assert page.locator('#det1 img').evaluate('(img)=>img.naturalWidth') == 0
            page.evaluate('window.__releaseWarm()')
            page.wait_for_function(
                "document.querySelector('#det1 img').naturalWidth > 0", timeout=5000)
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
        page.wait_for_function("document.querySelector('#det0 .quad-status').textContent.startsWith('Saved area')")
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
        page.wait_for_function("document.querySelector('#det0 .quad-status').textContent.startsWith('Saved area')")
        assert plate_points(card)[0] != before[0]
        assert json.loads(report.read_text())['detections'][0].get('plate_quad')
        browser.close()


def sampled_track_page(page, url, report):
    """Even duplicate sampled indices must collapse into one track card."""
    doc = json.loads(report.read_text())
    doc['detections'][1]['track'] = 0
    doc['detections'][1]['frame_index'] = 301
    doc['detections'][1]['t_start'] = doc['detections'][1]['t_end'] = doc['detections'][1]['last_seen'] = 301/30
    report.write_text(json.dumps(doc))
    load_browser_page(page, url, [], [])
    page.get_by_role('link', name='Synthetic review fixture', exact=True).click()
    page.locator('#review').wait_for()
    page.evaluate('''async()=>{ LEARNING_SELECTION=new Set([0,1]);
        LEARNING_SELECTION_JOB=CUR;await loadReview();}''')
    page.locator('#det0').scroll_into_view_if_needed()
    page.wait_for_function('!!document.querySelector("#det0 img")._quadEdit')
    assert page.locator("#review .det:visible").count() == 1


def test_not_plate_updates_every_member_of_sampled_group(review_server):
    sync_api = pytest.importorskip('playwright.sync_api')
    url, report = review_server
    with sync_api.sync_playwright() as pw:
        browser = browser_instance(pw)
        page = browser.new_page(viewport={'width':1440,'height':1000})
        sampled_track_page(page, url, report)
        page.locator('#det0').get_by_role('button',name='✕ Not a plate',exact=True).click()
        page.evaluate('CONFIRM_CHAIN')
        card = page.locator('#det0')
        assert card.locator('.det-status').inner_text() == 'Will stay visible'
        assert card.get_by_role('button',name='Keep visible',exact=True).get_attribute('aria-pressed') == 'true'
        assert page.evaluate('TRKMEM[0]') == [0, 1]
        assert page.evaluate('[EN[0], EN[1]]') == [False, False]
        assert page.evaluate('saveAndRender(true)') is True
        assert all(not r['enabled'] for r in json.loads(report.read_text())['detections'][:2])
        browser.close()


def test_not_plate_cancels_failed_corner_draft_without_blocking_decision_save(review_server, monkeypatch):
    from flask import jsonify, request
    url, report = review_server
    original = web.app.view_functions['job_plate_quad']
    def conflict(*args, **kwargs):
        if request.method == 'POST':return jsonify(error='This finding changed. Reload its preview before saving.'),409
        return original(*args, **kwargs)
    monkeypatch.setitem(web.app.view_functions, 'job_plate_quad', conflict)
    sync_api = pytest.importorskip('playwright.sync_api')
    with sync_api.sync_playwright() as pw:
        browser=browser_instance(pw)
        page=browser.new_page(viewport={'width':1440,'height':1000})
        load_browser_page(page,url,[],[])
        page.get_by_role('link',name='Synthetic review fixture',exact=True).click()
        card=page.locator('#det0');card.scroll_into_view_if_needed()
        page.wait_for_function('!!document.querySelector("#det0 img")._quadEdit')
        drag_corner(page,card)
        page.wait_for_function('!!document.querySelector("#det0 img")._quadEdit.error')
        card.get_by_role('button',name='✕ Not a plate',exact=True).click()
        page.evaluate('CONFIRM_CHAIN')
        assert card.locator('.det-status').inner_text() == 'Will stay visible'
        assert page.evaluate('saveAndRender(true)') is True, 'obsolete corners blocked the explicit rejection'
        saved=json.loads(report.read_text())['detections'][0]
        assert saved['verified_label']=='not_plate' and saved['enabled'] is False
        browser.close()


def test_editing_another_representative_after_track_save_does_not_conflict(review_server):
    sync_api=pytest.importorskip('playwright.sync_api')
    url,report=review_server
    with sync_api.sync_playwright() as pw:
        browser=browser_instance(pw);page=browser.new_page(viewport={'width':1440,'height':1000})
        sampled_track_page(page,url,report)
        for i in (0,1):
            if i == 1:
                # A later selection uses another frame, not two duplicate cards.
                page.evaluate('async()=>{LEARNING_SELECTION=new Set([1]);await loadReview();}')
                page.locator('#det1').scroll_into_view_if_needed()
                page.wait_for_function('!!document.querySelector("#det1 img")._quadEdit')
            card=page.locator('#det%d'%i);card.scroll_into_view_if_needed()
            drag_corner(page,card)
            page.wait_for_function('(i)=>{const s=document.querySelector("#det"+i+" img")._quadEdit;return !s.dirty||s.error}',arg=i)
            assert card.locator('img').evaluate('(img)=>img._quadEdit.error && img._quadEdit.error.message') is None
            assert card.locator('.quad-status').inner_text().startswith('Saved area')
        browser.close()


@pytest.mark.parametrize('viewport',[(1440,1000),(390,844)])
def test_sixty_rejections_keep_working_after_failed_save(review_server, monkeypatch, tmp_path, viewport):
    from flask import jsonify, request
    url,report=review_server
    original=web.app.view_functions['job_plate_quad']
    posted=[]
    def busy_save(*args,**kwargs):
        if request.method=='POST':
            posted.append(request.get_json())
            return jsonify(error='Another preview is decoding. Retry this finding.'),503
        return original(*args,**kwargs)
    monkeypatch.setitem(web.app.view_functions,'job_plate_quad',busy_save)
    sync_api=pytest.importorskip('playwright.sync_api')
    with sync_api.sync_playwright() as pw:
        browser=browser_instance(pw)
        page=browser.new_page(viewport={'width':viewport[0],'height':viewport[1]})
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        load_browser_page(page,url,[],[])
        page.get_by_role('link',name='Synthetic review fixture',exact=True).click()
        card=page.locator('#det0');card.scroll_into_view_if_needed()
        page.wait_for_function('!!document.querySelector("#det0 img")._quadEdit')
        drag_corner(page,card)
        page.wait_for_function('document.querySelector("#det0 .quad-status").textContent.includes("Waiting")')
        for i in range(60):
            card=page.locator('#det%d'%i)
            card.get_by_role('button',name='✕ Not a plate',exact=True).click()
            page.evaluate('CONFIRM_CHAIN')
            assert card.locator('.det-status').inner_text()=='Will stay visible',i
            assert card.get_by_role('button',name='Keep visible',exact=True).get_attribute('aria-pressed')=='true'
        assert len(posted)==1,'rejected corner drafts must not retry in the background'
        assert page.evaluate('saveAndRender(true)') is True
        stored=json.loads(report.read_text())['detections']
        assert all(r['enabled'] is False and r['verified_label']=='not_plate' for r in stored[:60])
        assert all(r['enabled'] is True for r in stored[60:])
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        assert not errors,errors
        evidence=Path(os.environ.get('REVIEW_EVIDENCE_DIR',str(tmp_path)))
        evidence.mkdir(parents=True,exist_ok=True)
        page.screenshot(path=str(evidence/('sixty-rejections-%d.png'%viewport[0])))
        browser.close()
