"""Long review sessions and fault recovery; synthetic media only.

Browser tests use production Flask HTTP in CI. REVIEW_INPROCESS=1 is only a
local sandbox fallback; it does not establish HTTP/network behavior.
"""
import json
import os
import random
from copy import deepcopy
from pathlib import Path

import pytest
import openscrub_web as web
from test_review_browser import review_server, browser_instance, load_browser_page, drag_corner
from test_plate_quad_editor import plate_job


@pytest.mark.timeout(180)
@pytest.mark.parametrize('viewport', [(1440, 1000), (390, 844)])
def test_large_report_mixed_review_save_reload_and_training_handoff(review_server, monkeypatch, tmp_path, viewport):
    """6,500 detections, 1,300 tracks; 180 decisions, edits, and repeated reloads."""
    url, report = review_server
    doc = json.loads(report.read_text())
    seed = doc['detections'][0]
    doc['detections'] = []
    for i in range(6500):
        row = deepcopy(seed)
        row.update(track=i//5, frame_index=300+i%5,
                   t_start=(300+i%5)/30, t_end=(300+i%5+.3)/30,
                   last_seen=(300+i%5)/30, confidence=.95-i%5*.01)
        doc['detections'].append(row)
    report.write_text(json.dumps(doc))
    queued = []
    monkeypatch.setattr(web.WORK_Q, 'put', queued.append)
    weights = tmp_path/'trusted-fixture.pt'; weights.write_bytes(b'not executed')
    monkeypatch.setenv('OPENSCRUB_TRAIN_WEIGHTS', str(weights))
    sync = pytest.importorskip('playwright.sync_api')
    rng = random.Random(731)
    tracks = rng.sample(range(1300), 180)
    with sync.sync_playwright() as pw:
        browser = browser_instance(pw)
        page = browser.new_page(viewport=dict(width=viewport[0], height=viewport[1]))
        page.set_default_timeout(15000)
        errors, requests = [], []
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.on('dialog', lambda d: d.accept())
        page.on('request', lambda r: requests.append(r.url))
        load_browser_page(page, url, requests, [])
        page.get_by_role('link', name='Synthetic review fixture', exact=True).click()
        page.wait_for_function('document.querySelectorAll("#review .det").length===1300')
        expected = {}
        for batch in range(3):
            for index, track in enumerate(tracks[batch*60:(batch+1)*60]):
                card = page.locator('#det%d' % (track*5))
                rejected = index % 4 != 0
                name = '✕ Not a plate' if rejected else '✓ Confirm plate'
                card.get_by_role('button', name=name, exact=True).click()
                assert card.locator('.det-status').inner_text() == (
                    'Will stay visible' if rejected else 'Will be blurred')
                expected[track] = 'not_plate' if rejected else 'plate'
            assert page.evaluate('saveAndRender(true)') is True
            # Verify all rows, not just representatives or the green DOM state.
            stored = json.loads(report.read_text())['detections']
            for i, row in enumerate(stored):
                label = expected.get(i//5)
                if label:
                    assert row.get('verified_label') == label, i
                    assert row['enabled'] == (label == 'plate'), i
                else:
                    assert row['enabled'] is True and not row.get('verified_label'), i
            # Re-open the job: renderer and preview queues must be disposed.
            page.get_by_role('link', name='Synthetic review fixture', exact=True).click()
            page.wait_for_function('document.querySelectorAll("#review .det").length===1300')
            page.wait_for_function('REVIEW_MEDIA.cacheActive<=3 && REVIEW_MEDIA.active<=1')
        card = page.locator('#det0'); card.scroll_into_view_if_needed()
        page.wait_for_function('!!document.querySelector("#det0 img")._quadEdit')
        drag_corner(page, card, dx=4, dy=2)
        assert page.evaluate('saveAndRender(true)') is True
        saved_points = json.loads(report.read_text())['detections'][0]['plate_quad']
        assert len(saved_points) == 4
        # New page removes ALL in-memory labels; loaded decisions must be on disk.
        page.close()
        page = browser.new_page(viewport=dict(width=viewport[0], height=viewport[1]))
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.on('dialog', lambda d: d.accept())
        load_browser_page(page, url, [], [])
        page.get_by_role('link', name='Synthetic review fixture', exact=True).click()
        page.locator('#review').wait_for()
        for track in tracks[-10:]:
            status = page.locator('#det%d .det-status' % (track*5))
            assert status.inner_text() == ('Will stay visible' if expected[track]=='not_plate' else 'Will be blurred')
        page.get_by_role('button', name='Review uncertain examples (10%)', exact=True).click()
        page.get_by_role('button', name='Show all findings', exact=True).wait_for()
        assert 0 < page.locator('#review .det').count() <= 650
        assert len(page.evaluate('Object.keys(EN)')) == 6500
        page.get_by_role('button', name='Train & rescan this video', exact=True).click()
        page.get_by_role('button', name='Cancel learning pass', exact=True).wait_for()
        assert queued == [('inline-fixture', 'learn')]
        final = json.loads(report.read_text())['detections']
        assert final[0]['plate_quad'] == saved_points
        for track, label in expected.items():
            assert all(r.get('verified_label')==label for r in final[track*5:track*5+5])
        assert not errors, errors
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        evidence = Path(os.environ.get('REVIEW_EVIDENCE_DIR', str(tmp_path)))
        evidence.mkdir(exist_ok=True, parents=True)
        page.screenshot(path=str(evidence/('large-review-%s.png' % viewport[0])))
        browser.close()


def test_committed_corner_response_lost_retry_preserves_one_sample(review_server, monkeypatch):
    """Server commits the write, but the response fails; Retry must be idempotent."""
    from flask import request, jsonify
    url, report = review_server
    original = web.app.view_functions['job_plate_quad']
    receipts = []
    def lost_response(*args, **kwargs):
        result = original(*args, **kwargs)
        if request.method == 'POST':
            receipts.append(request.get_json()['edit_id'])
            if len(receipts) == 1:
                return jsonify(error='Injected failure AFTER durable commit'), 502
        return result
    monkeypatch.setitem(web.app.view_functions, 'job_plate_quad', lost_response)
    sync = pytest.importorskip('playwright.sync_api')
    with sync.sync_playwright() as pw:
        browser = browser_instance(pw); page = browser.new_page()
        load_browser_page(page, url, [], [])
        page.get_by_role('link', name='Synthetic review fixture', exact=True).click()
        card=page.locator('#det0');card.scroll_into_view_if_needed()
        page.wait_for_function('!!document.querySelector("#det0 img")._quadEdit')
        drag_corner(page,card)
        card.get_by_role('button',name='Retry save',exact=True).wait_for()
        before=json.loads(report.read_text())['detections'][0]['plate_quad']
        card.get_by_role('button',name='Retry save',exact=True).click()
        page.wait_for_function('document.querySelector("#det0 .quad-status").textContent.startsWith("Saved")')
        assert receipts[0] == receipts[1] and len(receipts)==2
        assert json.loads(report.read_text())['detections'][0]['plate_quad']==before
        annotations=report.parent/'plate_annotations'/'annotations.jsonl'
        assert len(annotations.read_text().splitlines())==1
        assert page.evaluate('saveAndRender(true)') is True
        browser.close()


def test_reconfirming_a_rejected_example_revokes_stale_negative(plate_job):
    import learning_session as ls
    import openscrub
    client,jid,report,folder=plate_job
    job=web.JOBS[jid]
    endpoint='/api/jobs/%s/detections'%jid
    assert client.post(endpoint,json={'enabled':{'0':False},'verified_labels':{'0':'not_plate'}}).status_code==200
    def collect():
        doc=json.loads(report.read_text())
        doc['provenance']['input_sha256']=openscrub.sha256_file(job['video'])
        return ls.collect_feedback(job,doc,lambda i:web._read_exact_frame(job['video'],i))
    initial=collect();assert any(s['label']=='negative' for s in initial['samples'].values())
    assert client.post(endpoint,json={'enabled':{'0':True},'verified_labels':{'0':'plate'}}).status_code==200
    data=collect()
    assert not any(s['label']=='negative' for s in data['samples'].values()), 'Reconfirmed real plate still trains as a negative'
    assert not data['constraints']['negative_paths'], 'Old rejection still suppresses the reconfirmed track'


def test_clearing_label_revokes_previously_collected_training_evidence(plate_job):
    import learning_session as ls
    import openscrub
    client,jid,report,folder=plate_job;job=web.JOBS[jid]
    endpoint='/api/jobs/%s/detections'%jid
    assert client.post('/api/jobs/%s/plate_quad/0'%jid,json={
        'points':[[54,77],[126,74],[129,91],[52,94]],'autosave':True,'edit_id':'source'}).status_code==200
    def collect():
        doc=json.loads(report.read_text());doc['provenance']['input_sha256']=openscrub.sha256_file(job['video'])
        return ls.collect_feedback(job,doc,lambda i:web._read_exact_frame(job['video'],i))
    assert len(collect()['samples'])==1
    assert client.post(endpoint,json={'enabled':{'0':False},'verified_labels':{'0':'clear'}}).status_code==200
    data=collect()
    assert not data['samples'], 'Cleared/kept-visible label remained training evidence'


def test_reconfirmed_polygon_reuses_verified_pixels_after_label_reversal(plate_job):
    import learning_session as ls
    import openscrub
    client,jid,report,folder=plate_job;job=web.JOBS[jid]
    endpoint='/api/jobs/%s/detections'%jid
    points=[[54,77],[126,74],[129,91],[52,94]]
    assert client.post('/api/jobs/%s/plate_quad/0'%jid,json={
        'points':points,'autosave':True,'edit_id':'verified-shape'}).status_code==200
    def collect():
        doc=json.loads(report.read_text());doc['provenance']['input_sha256']=openscrub.sha256_file(job['video'])
        return ls.collect_feedback(job,doc,lambda i:web._read_exact_frame(job['video'],i))
    initial=collect();first=next(iter(initial['samples'].values()))
    assert client.post(endpoint,json={'enabled':{'0':False},'verified_labels':{'0':'not_plate'}}).status_code==200
    assert {s['label'] for s in collect()['samples'].values()}=={'negative'}
    assert client.post(endpoint,json={'enabled':{'0':True},'verified_labels':{'0':'plate'}}).status_code==200
    data=collect()
    assert len(data['samples'])==1
    restored=next(iter(data['samples'].values()))
    assert restored['label']=='positive'
    assert restored['points']==first['points'] and restored['image_sha256']==first['image_sha256']
    assert not data['constraints']['negative_paths']


@pytest.mark.parametrize('dash', ['\u2010','\u2011','\u2012','\u2013','\u2014','\u2212'])
def test_tesseract_dash_variants_do_not_silently_miss_numeric_identifiers(monkeypatch,dash):
    import re
    import numpy as np
    import openscrub
    ocr=openscrub.TesseractBackend()
    data={'text':['CLM'+dash+'1234567','123'+dash+'45'+dash+'6789'],
          'conf':['95','95'],'left':[5,250],'top':[5,5],'width':[210,210],'height':[30,30]}
    monkeypatch.setattr(ocr.pt,'image_to_data',lambda *a,**k:data)
    words=ocr.read(np.zeros((50,480,3),np.uint8))
    detections=openscrub.detect_phi(words,openscrub.group_lines(words),0,(0,0),None,None,
                                  [('claim',re.compile(r'CLM-\d+'))])
    assert {d.category for d in detections}>={'claim','ssn'}


def test_decision_save_network_failure_is_visible_and_retry_preserves_labels(review_server):
    url,report=review_server
    sync=pytest.importorskip('playwright.sync_api')
    with sync.sync_playwright() as pw:
        browser=browser_instance(pw);page=browser.new_page()
        dialogs=[];page.on('dialog',lambda d:(dialogs.append(d.message),d.accept()))
        load_browser_page(page,url,[],[])
        page.get_by_role('link',name='Synthetic review fixture',exact=True).click()
        page.locator('#det0').get_by_role('button',name='✕ Not a plate',exact=True).click()
        page.evaluate('''()=>{const original=window.fetch;let fail=true;
          window.fetch=(url,options={})=>{
           if(fail&&String(url).endsWith('/detections')&&options.method==='POST'){
            fail=false;return Promise.reject(new TypeError('Injected connection loss'));
           }return original(url,options);
          };}''')
        assert page.evaluate('saveAndRender(true)') is False
        assert dialogs and 'save' in dialogs[-1].lower()
        assert page.locator('#det0 .det-status').inner_text()=='Will stay visible'
        assert page.evaluate('saveAndRender(true)') is True
        assert json.loads(report.read_text())['detections'][0]['verified_label']=='not_plate'
        browser.close()


def test_tesseract_repeated_dash_in_numeric_identifier(monkeypatch):
    import numpy as np
    import openscrub
    ocr=openscrub.TesseractBackend()
    data={'text':['123\u2014-45-\u20146789'], 'conf':['25'],
          'left':[5],'top':[5],'width':[210],'height':[30]}
    monkeypatch.setattr(ocr.pt,'image_to_data',lambda *a,**k:data)
    words=ocr.read(np.zeros((50,240,3),np.uint8))
    found=openscrub.detect_phi(words,openscrub.group_lines(words),0,(0,0),None,None)
    assert any(d.category=='ssn' for d in found)


def test_current_label_overrides_old_training_identity_after_rescan(plate_job):
    import learning_session as ls
    import openscrub
    client,jid,report,folder=plate_job;job=web.JOBS[jid]
    doc=json.loads(report.read_text());doc['provenance']['input_sha256']=openscrub.sha256_file(job['video'])
    doc['detections'][0].update(verified_label='not_plate',enabled=False)
    read=lambda i:web._read_exact_frame(job['video'],i)
    old=ls.collect_feedback(job,doc,read)
    group=next(iter(old['samples'].values()))['group']
    changed=deepcopy(doc);same=changed['detections'][0]
    same.update(track=99,verified_label='plate',enabled=True,learning_group=group)
    other=deepcopy(same);other.update(cbox=[150,10,200,30],track=100,verified_label='not_plate',learning_group='unrelated')
    changed['detections']=[other,same]
    changed['learning']={'pass_id':'a-new-pass'}
    result=ls.collect_feedback(job,changed,read)
    assert all(s['group']!=group or s['label']!='negative' for s in result['samples'].values())
    assert all(p['group']!=group for p in result['constraints']['negative_paths'])
    assert any(s['group']=='unrelated' and s['label']=='negative' for s in result['samples'].values())


def test_cold_decoder_does_not_starve_production_server_review_writes(plate_job,monkeypatch):
    """Use the actual production WSGI server with only three worker threads."""
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor
    from urllib.request import Request,urlopen
    from urllib.error import HTTPError
    from cheroot.wsgi import Server
    client,jid,report,folder=plate_job;job=web.JOBS[jid]
    doc=json.loads(report.read_text())
    doc['detections']=[dict(doc['detections'][0],track=i) for i in range(40)]
    report.write_text(json.dumps(doc))
    meta=client.get('/api/jobs/%s/plate_quad/0'%jid).get_json()
    entered=threading.Event();release=threading.Event();original=web._frame_at
    def stalled(*args,**kwargs):
        entered.set()
        assert release.wait(15), 'test did not release its stalled decoder'
        return original(*args,**kwargs)
    monkeypatch.setattr(web,'_frame_at',stalled)
    server=Server(('127.0.0.1',0),web.app,numthreads=3,shutdown_timeout=2)
    server.prepare();thread=threading.Thread(target=server.serve,daemon=True);thread.start()
    base='http://127.0.0.1:%s'%server.socket.getsockname()[1]
    def call(path,data=None):
        request=Request(base+path,data=None if data is None else json.dumps(data).encode(),
                        headers={'Content-Type':'application/json','Connection':'close'})
        try:
            with urlopen(request,timeout=10) as response:return response.status,response.read()
        except HTTPError as error:return error.code,error.read()
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            cold=pool.submit(call,'/api/jobs/%s/thumb/39'%jid)
            assert entered.wait(3)
            start=time.monotonic()
            for i in range(1,31):
                status,_=call('/api/jobs/%s/detections'%jid,{
                    'enabled':{str(i):False},'verified_labels':{str(i):'not_plate'}})
                assert status==200
            status,_=call('/api/jobs/%s/plate_quad/0'%jid,{
                'points':[[54,77],[126,74],[129,91],[52,94]],
                'preview_token':meta['preview_token'],'autosave':True,'edit_id':'under-load'})
            assert status==200
            assert time.monotonic()-start<10 and not release.is_set()
            saved=json.loads(report.read_text())['detections']
            assert all(r['enabled'] is False and r['verified_label']=='not_plate' for r in saved[1:31])
            assert saved[0].get('plate_quad') and saved[39]['enabled'] is True
            release.set();assert cold.result(timeout=10)[0]==200
    finally:
        release.set();server.stop();thread.join(timeout=5)


def test_4k_h264_frame_corner_save_and_training_crop(plate_job):
    """Real 3840x2160 H.264 decode -> editor -> verified crop, not a GPU test."""
    import subprocess
    import cv2
    import openscrub
    import learning_session as ls
    client,jid,report,folder=plate_job;job=web.JOBS[jid]
    source=folder/'source-4k.mp4'
    subprocess.run(['ffmpeg','-y','-loglevel','error','-i',job['video'],
                    '-vf','scale=3840:2160','-frames:v','5','-c:v','libx264',
                    '-preset','ultrafast','-threads','2',str(source)],check=True,timeout=30)
    job['video']=str(source)
    doc=json.loads(report.read_text());doc['provenance']={'input':str(source),'input_sha256':openscrub.sha256_file(str(source))}
    doc['render_state']['cum']=[[0,0]]*5;doc['render_state']['bands']=[[0,0]]*5
    doc['detections'][0].update(cbox=[720,904,2192,1390],frame_index=2)
    report.write_text(json.dumps(doc))
    endpoint='/api/jobs/%s/plate_quad/0'%jid
    meta=client.get(endpoint).get_json()
    assert (meta['width'],meta['height'])==(3840,2160)
    points=[[800,1000],[2000,990],[2010,1230],[790,1240]]
    saved=client.post(endpoint,json={'points':points,'preview_token':meta['preview_token'],
                                   'autosave':True,'edit_id':'4k-verified'})
    assert saved.status_code==200,saved.get_data(as_text=True)
    feedback=ls.collect_feedback(job,json.loads(report.read_text()),lambda i:web._read_exact_frame(str(source),i))
    sample=next(iter(feedback['samples'].values()))
    image=cv2.imread(str(folder/'learning'/sample['image']))
    assert image is not None and image.shape[1]>1200
    assert len(sample['points'])==4 and all(0<=v<=1 for p in sample['points'] for v in p)


def test_duplicate_agreeing_detections_do_not_block_existing_feedback(plate_job):
    import learning_session as ls
    import openscrub
    client,jid,report,folder=plate_job;job=web.JOBS[jid]
    doc=json.loads(report.read_text());doc['provenance']['input_sha256']=openscrub.sha256_file(job['video'])
    row=doc['detections'][0];row.update(verified_label='not_plate',enabled=False)
    doc['detections'].append(dict(row,track=99))
    read=lambda i:web._read_exact_frame(job['video'],i)
    original=ls.collect_feedback(job,doc,read)
    repeated=ls.collect_feedback(job,doc,read)
    assert repeated['samples']==original['samples']
    assert repeated['fingerprint']==original['fingerprint']


def test_conflicting_overlapping_labels_do_not_overwrite_feedback(plate_job):
    import learning_session as ls
    import openscrub
    client,jid,report,folder=plate_job;job=web.JOBS[jid]
    doc=json.loads(report.read_text());doc['provenance']['input_sha256']=openscrub.sha256_file(job['video'])
    row=doc['detections'][0];row.update(verified_label='not_plate',enabled=False)
    read=lambda i:web._read_exact_frame(job['video'],i)
    ls.collect_feedback(job,doc,read)
    saved=(folder/'learning'/'feedback.json').read_bytes()
    doc['detections'].append(dict(row,track=99,verified_label='plate',enabled=True))
    with pytest.raises(ValueError,match='Ambiguous changed review labels'):
        ls.collect_feedback(job,doc,read)
    assert (folder/'learning'/'feedback.json').read_bytes()==saved
