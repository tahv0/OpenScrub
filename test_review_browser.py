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


@pytest.mark.parametrize('viewport', [(1440, 1000), (390, 844)])
def test_real_inline_edit_save_cancel_and_lazy_loading(review_server, viewport, tmp_path):
    sync_api = pytest.importorskip('playwright.sync_api')
    url, report = review_server
    with sync_api.sync_playwright() as pw:
        browser = browser_instance(pw)
        page = browser.new_page(viewport={'width': viewport[0], 'height': viewport[1]})
        page.set_default_timeout(15000)
        errors, requests = [], []
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.on('request', lambda r: requests.append(r.url))
        if os.environ.get('REVIEW_INPROCESS') == '1':
            # Optional offline transport: actual Flask routes and actual video,
            # but no network sockets. The default/CI path below uses real HTTP.
            def serve(input_url, options):
                requests.append(input_url)
                split = urlsplit(input_url)
                path = split.path if split.path.startswith('/') else '/'+split.path
                if split.query: path += '?'+split.query
                with web.app.test_client() as client:
                    response = client.open(path, method=options.get('method') or 'GET',
                                           data=options.get('body'), headers=options.get('headers') or {})
                    return dict(status=response.status_code, headers=dict(response.headers),
                                body=base64.b64encode(response.data).decode())
            page.expose_function('__flaskFetch', serve)
            page.evaluate("""() => {window.fetch=async(url,options={})=>{
              const r=await window.__flaskFetch(String(url),{method:options.method,body:options.body,headers:options.headers});
              return new Response(Uint8Array.from(atob(r.body),c=>c.charCodeAt(0)),{status:r.status,headers:r.headers});
            };}""")
            with web.app.test_client() as client:
                page.set_content(client.get('/').get_data(as_text=True), wait_until='domcontentloaded')
        else:
            page.goto(url)
        assert page.title() == 'OpenScrub'
        page.get_by_role('link', name='Synthetic review fixture', exact=True).click()
        page.locator('#review').wait_for()
        assert page.locator('#review .det').count() == 90
        card = page.locator('#det0')
        card.scroll_into_view_if_needed()
        page.wait_for_function("document.querySelector('#det0 img').naturalWidth > 0")
        before_requests = sum('/thumb/0' in r for r in requests)
        assert sum('/thumb/' in r for r in requests) < 30  # not all 90 findings
        card.get_by_role('button', name='Edit 4 corners', exact=True).click()
        page.locator('#qSave').wait_for()
        assert page.locator('#plateQuadOverlay').count() == 0
        assert card.locator('#plateQuadEditor').is_visible()
        assert card.get_by_role('button', name='Keep visible', exact=True).is_visible()
        assert sum('/thumb/0' in r for r in requests) == before_requests
        assert not any('/plate_quad/' in r for r in requests)  # no second fetch to open
        initial = page.evaluate('QEDIT.points.map(p=>p.slice())')
        handle = page.evaluate('''() => {
         const q=QEDIT,c=q.crop,r=document.getElementById('qCv').getBoundingClientRect();
         return {x:r.left+(q.points[0][0]-c[0])*r.width/(c[2]-c[0]),
                 y:r.top+(q.points[0][1]-c[1])*r.height/(c[3]-c[1])};
        }''')
        page.mouse.move(handle['x'], handle['y']);page.mouse.down()
        page.mouse.move(handle['x']+16, handle['y']+9, steps=5);page.mouse.up()
        moved = page.evaluate('QEDIT.points.map(p=>p.slice())')
        assert moved[0] != initial[0] and moved[1:] == initial[1:]
        page.locator('#qRotateRight').click()
        assert all(a != b for a, b in zip(moved, page.evaluate('QEDIT.points')))
        page.locator('#qClose').click()
        assert page.locator('#plateQuadEditor').count() == 0
        assert 'plate_quad' not in json.loads(report.read_text())['detections'][0]
        photo_box = card.locator('img').bounding_box()
        outline_box = card.locator('.plate-outline').bounding_box()
        assert abs(photo_box['width']-outline_box['width']) < 1
        assert abs(photo_box['height']-outline_box['height']) < 1
        card.get_by_role('button', name='Edit 4 corners', exact=True).click()
        page.locator('#qSave').wait_for()
        assert page.evaluate('QEDIT.points') == initial
        page.locator('#qRotateRight').click()
        before_save = page.evaluate('QEDIT.points.map(p=>p.slice())')
        page.locator('#qSave').click()
        page.wait_for_function("document.getElementById('qStatus').textContent.startsWith('Saved ')")
        stored = json.loads(report.read_text())['detections'][0]
        assert len(stored['plate_quad']) == 4
        assert stored['verified_label'] == 'plate'
        assert not page.evaluate('QEDIT.dirty')
        # Blur/Keep remains explicit and idempotent while editing in place.
        card.get_by_role('button', name='Keep visible', exact=True).click()
        assert page.evaluate('EN[0]') is False
        card.get_by_role('button', name='Blur', exact=True).click()
        assert page.evaluate('EN[0]') is True
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        evidence = Path(os.environ.get('REVIEW_EVIDENCE_DIR', str(tmp_path)))
        evidence.mkdir(parents=True, exist_ok=True)
        card.screenshot(path=str(evidence / ('inline-%s.png' % viewport[0])))
        page.locator('#qClose').click()
        card.get_by_role('button', name='Edit 4 corners', exact=True).click()
        page.locator('#qSave').wait_for()
        reopened = page.evaluate('QEDIT.points')
        assert max(abs(a-b) for p,q in zip(reopened,before_save) for a,b in zip(p,q)) < .001
        assert not errors, errors
        browser.close()
