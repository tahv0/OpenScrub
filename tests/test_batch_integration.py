"""Bounded combined-candidate checks; all media and OCR inputs are synthetic."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import cv2
import numpy as np
import werkzeug.wsgi

import openscrub
import openscrub_web as web
from test_job_lifecycle import store
from test_report_transactions import socket_api, run_worker, join
from test_report_roundtrip import review, assert_review_preserved


def idle():
    deadline = time.monotonic() + 8
    while web.FILES.count and time.monotonic() < deadline:
        time.sleep(.01)
    assert web.FILES.count == 0


def scan_setup(store, monkeypatch, source=None):
    if source is None:
        source = store.job['video']
        writer = cv2.VideoWriter(source, cv2.VideoWriter_fourcc(*'MJPG'), 30, (160,96))
        assert writer.isOpened()
        rng = np.random.default_rng(650)
        for _ in range(60):
            writer.write(rng.integers(100,220,(96,160,3),dtype=np.uint8))
        writer.release()
    store.job.update(video=str(source), phase='cancelled')
    store.job['options'].update(categories='email', engine='tesseract', no_ner=True,
                               no_memory=True, sample_interval=.1, encoder='x264', mode='box', pad=0)
    # Controlled OCR boundary only: run_scan, decoder, callbacks, report and render are real.
    monkeypatch.setattr(openscrub, 'make_ocr', lambda *a, **kw: SimpleNamespace(
        read=lambda frame: [('one@example.invalid',(4,2,65,18),.99)]))


def test_actual_scan_preview_cancel_retry_and_held_response_ownership(store, socket_api, monkeypatch):
    scan_setup(store, monkeypatch)
    store.enable()
    published = [threading.Event(), threading.Event()]
    resume = [threading.Event(), threading.Event()]
    acquired, transfer = threading.Event(), threading.Event()
    calls = []
    real_frame = web.WebCallbacks.scan_frame
    def frame(cb, pixels, t, found):
        cb._last_frame = 0
        real_frame(cb, pixels, t, found)
        calls.append(t)
        if len(calls) <= 2:
            index = len(calls)-1
            published[index].set()
            assert resume[index].wait(8)
    monkeypatch.setattr(web.WebCallbacks, 'scan_frame', frame)
    real_next = werkzeug.wsgi.FileWrapper.__next__
    held = []
    def next_chunk(wrapper):
        if not held:
            held.append(wrapper)
            acquired.set()
            assert transfer.wait(8)
        return real_next(wrapper)
    monkeypatch.setattr(werkzeug.wsgi.FileWrapper, '__next__', next_chunk)
    assert socket_api('POST',store.url+'/retry')[0] == 200
    worker = run_worker()
    try:
        assert published[0].wait(8)
        before = (Path(store.job['dir'])/'preview.jpg').read_bytes()
        with ThreadPoolExecutor(max_workers=1) as pool:
            response = pool.submit(socket_api,'GET',store.url+'/preview.jpg')
            try:
                assert acquired.wait(8)
                assert web.FILES.count >= 2
                resume[0].set()
                assert published[1].wait(8)
                assert (Path(store.job['dir'])/'preview.jpg').read_bytes() != before
                assert socket_api('POST',store.url+'/cancel')[0] == 200
                assert socket_api('DELETE',store.url)[0] == 409
                assert socket_api('POST','/api/vault/lock')[0] == 409
                assert socket_api('POST',store.url+'/retry')[0] == 409
                resume[1].set()
                join(worker)
                assert store.job['phase'] == 'cancelled'
                # The detached complete JPEG still follows the existing response lease.
                assert web.FILES.count == 1
                assert socket_api('DELETE',store.url)[0] == 409
                assert socket_api('POST','/api/vault/lock')[0] == 409
            finally:
                transfer.set()
                resume[0].set()
                resume[1].set()
            status, headers, body = response.result(timeout=8)
            assert status == 200 and body == before
            assert int(headers['Content-Length']) == len(before)
            assert headers['ETag'] == '"'+hashlib.sha256(before).hexdigest()+'"'
    finally:
        for event in resume: event.set()
        transfer.set()
        join(worker)
    idle()
    assert socket_api('POST','/api/vault/lock')[0] == 200
    assert socket_api('POST','/api/vault/unlock',{'password':'synthetic-password'})[0] == 200
    store.job = web.JOBS[store.job['id']]
    assert socket_api('POST',store.url+'/retry')[0] == 200
    join(run_worker())
    idle()
    assert store.job['phase'] == 'review', store.job.get('error')
    assert json.loads(store.path.read_text())['detections']


def fresh_reopen(store, expected, replay=None):
    code = r"""
import json, os, threading, urllib.request
from pathlib import Path
import openscrub_web as web
from cheroot import wsgi
assert web.__file__ == os.environ['BATCH_SOURCE']
web._data_root=lambda:os.environ['BATCH_ROOT']
web.JOBS_DIR=os.environ['BATCH_JOBS']; web.TOKEN=None
web.rehydrate_jobs()
ready=threading.Event(); servers=[]
real=wsgi.Server.prepare
def prepare(server):
    real(server);servers.append(server);ready.set()
wsgi.Server.prepare=prepare
thread=threading.Thread(target=lambda:web._serve('127.0.0.1',0,None));thread.start()
try:
    assert ready.wait(8)
    base='http://127.0.0.1:'+str(servers[0].socket.getsockname()[1])+os.environ['BATCH_URL']
    payload=json.loads(os.environ['BATCH_REPLAY'])
    if payload:
        request=urllib.request.Request(base+'/detections', data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(request,timeout=8) as response: assert response.status==200
    with urllib.request.urlopen(base+'/report',timeout=8) as response:
        assert response.status==200
        assert json.load(response)==json.loads(Path(os.environ['BATCH_EXPECTED']).read_text())
finally:
    for server in servers:server.stop()
    thread.join(8);assert not thread.is_alive()
assert web.FILES.count==0
print('fresh-process real HTTP report/replay/lease release: passed')
"""
    expected_path=store.root/'expected-batch.json'
    expected_path.write_text(json.dumps(expected))
    env=dict(os.environ,BATCH_SOURCE=str(Path(web.__file__).resolve()),BATCH_ROOT=str(store.root),
             BATCH_JOBS=str(store.jobs),BATCH_URL=store.url,BATCH_REPLAY=json.dumps(replay),
             BATCH_EXPECTED=str(expected_path))
    result=subprocess.run([sys.executable,'-c',code],env=env,text=True,capture_output=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
    print(result.stdout)


def test_actual_scan_review_save_render_export_and_fresh_reopen(store, socket_api, monkeypatch, review):
    scan_setup(store,monkeypatch,review.video)
    assert socket_api('POST',store.url+'/retry')[0]==200
    join(run_worker());idle()
    assert store.job['phase']=='review',store.job.get('error')
    scanned=json.loads(store.path.read_text())
    assert scanned['detections'] and (Path(store.job['dir'])/'preview.jpg').is_file()
    # Seed the ordinary imported report boundary with mixed kept/selected rows and additive/audio fields.
    doc=copy.deepcopy(review.doc)
    doc['detections'] += scanned['detections']
    web.atomic_report(str(store.path),doc)
    payload={'enabled':{str(i):False for i in range(10,len(doc['detections']))},
             'manual':[{'manual_id':'batch650:replay','t_start':0,'t_end':1,'screen_box':[70,2,90,15]}]}
    # Discard the committed acknowledgement, then retry through real HTTP.
    assert socket_api('POST',store.url+'/detections',payload)[0]==200
    assert socket_api('POST',store.url+'/detections',payload)[0]==200
    saved=json.loads(store.path.read_text())
    assert len(saved['detections'])==len(doc['detections'])+1
    assert saved['detections'][:10]==doc['detections'][:10]
    assert socket_api('POST',store.url+'/render')[0]==200
    join(run_worker());idle()
    assert store.job['phase']=='done',store.job.get('error')
    rendered=json.loads(store.path.read_text())
    assert_review_preserved(saved,rendered)
    status,headers,body=socket_api('GET',store.url+'/report')
    assert status==200 and json.loads(body)==rendered
    assert '_audit.json' in headers['Content-Disposition']
    status,headers,body=socket_api('GET',store.url+'/download')
    assert status==200 and body==Path(store.job['output']).read_bytes()
    assert '_redacted.mp4' in headers['Content-Disposition']
    idle()
    cap=cv2.VideoCapture(store.job['output']);ok,frame=cap.read();cap.release()
    assert ok and frame[40,24].mean()<20 and frame[40,8].mean()>140
    fresh_reopen(store,rendered,payload)
    assert json.loads(store.path.read_text())==rendered


def test_thousand_row_actual_http_save_and_fresh_reopen(store,socket_api):
    doc=copy.deepcopy(store.doc)
    doc['detections']=[dict(copy.deepcopy(doc['detections'][0]),text='synthetic-%04d'%i,
                            future_row={'index':i}) for i in range(1000)]
    doc['audio_transcript']=[[0,1,'synthetic']]
    doc['audio_suggestions']=[{'t0':0,'t1':1,'future':True}]
    web.atomic_report(str(store.path),doc)
    assert socket_api('POST',store.url+'/detections',{'enabled':{'999':False}})[0]==200
    saved=json.loads(store.path.read_text())
    assert len(saved['detections'])==1000 and saved['detections'][999]['enabled'] is False
    assert saved['detections'][:999]==doc['detections'][:999]
    assert saved['audio_transcript']==doc['audio_transcript']
    assert saved['audio_suggestions']==doc['audio_suggestions']
    fresh_reopen(store,saved)
    idle()
