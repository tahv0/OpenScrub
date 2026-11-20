"""Actual isolated OCR worker, timeout and child-process cleanup."""
import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

import pytest
import openscrub_web as web
from test_exact_samples import exact, sample, precondition
from test_job_lifecycle import store, request, start_call, finish
from test_plate_text_real_ocr import _clip

pytestmark = [pytest.mark.skipif(os.name != 'posix', reason='worker isolation is POSIX-only'),
              pytest.mark.skipif(not shutil.which('tesseract'), reason='local Tesseract unavailable')]


@pytest.fixture
def video_request(exact):
    _clip(Path(exact.job['video']))
    doc=json.loads(exact.path.read_text())
    doc['render_state']={'fps':4,'cum':[[0,0]]*4}
    doc['detections'][0].update(t_end=1,last_seen=.5)
    exact.path.write_text(json.dumps(doc))
    seed=precondition(sample(exact,0),None)
    return dict(seed=seed,query='JF5',mode='fragment',request_id='d'*32)


def test_actual_route_reads_detached_plate_without_sensitive_argv_or_residue(exact,video_request,monkeypatch,capsys):
    calls=[]
    original=subprocess.Popen
    def spawn(args,*a,**kw):
        calls.append((args,kw))
        return original(args,*a,**kw)
    monkeypatch.setattr(subprocess,'Popen',spawn)
    before=exact.path.read_bytes()
    response=request('post',exact.url+'/plate_search',json=video_request)
    assert response.status_code == 200, response.get_data(as_text=True)
    assert response.json['state'] == 'complete' and response.json['index'] == 0
    assert response.json['suggestions'] and all(row['match']=='fragment' and row['boundary']=='unknown'
                                                for row in response.json['suggestions'])
    full_request=dict(video_request, query='KJF572', mode='full', request_id='e'*32)
    full=request('post',exact.url+'/plate_search',json=full_request)
    assert full.status_code == 200 and full.json['suggestions']
    assert all(row['match']=='full_equal' for row in full.json['suggestions'])
    empty_request=dict(video_request,seed=precondition(sample(exact,.25),None),request_id='f'*32)
    empty=request('post',exact.url+'/plate_search',json=empty_request)
    assert empty.status_code == 200 and empty.json['state']=='complete' and empty.json['suggestions']==[]
    assert exact.path.read_bytes() == before
    assert not list(Path(exact.job['dir']).glob('.plate-search-*'))
    assert calls and all('JF5' not in str(args) and 'KJF572' not in str(args) for args,kw in calls)
    assert all('JF5' not in str(kw.get('env',{})) and 'KJF572' not in str(kw.get('env',{})) for args,kw in calls)
    assert 'JF5' not in response.get_data(as_text=True)
    output=capsys.readouterr(); assert 'JF5' not in output.out+output.err
    assert 'JF5' not in '\n'.join(exact.job['log'].snapshot()['lines'])


def slow_tesseract(exact,tmp_path,monkeypatch):
    binary_dir=tmp_path/'bin'; binary_dir.mkdir()
    binary=binary_dir/'tesseract'
    binary.write_text('#!/bin/sh\necho $$ > "$OPENSCRUB_TEST_MARKER"\nexec /bin/sleep 30\n')
    binary.chmod(0o700)
    marker=tmp_path/'tesseract-pid'
    monkeypatch.setenv('PATH',str(binary_dir)+os.pathsep+os.environ['PATH'])
    monkeypatch.setenv('OPENSCRUB_TEST_MARKER',str(marker))
    return marker


def _dead(pid):
    try:
        os.kill(pid,0)
    except ProcessLookupError:
        return True
    status=Path('/proc')/str(pid)/'stat'
    return status.exists() and status.read_text().split()[2] == 'Z'


def test_actual_worker_timeout_kills_descendants_and_cleans_job_temp(exact,video_request,tmp_path,monkeypatch):
    marker=slow_tesseract(exact,tmp_path,monkeypatch)
    monkeypatch.setattr(web,'_PLATE_SEARCH_DEADLINE',1.5)
    response=request('post',exact.url+'/plate_search',json=video_request)
    assert marker.exists(), 'OCR subprocess never started'
    assert response.status_code == 504 and response.json['state'] == 'timeout'
    assert 'suggestions' not in response.json
    assert _dead(int(marker.read_text()))
    assert not list(Path(exact.job['dir']).glob('.plate-search-*'))


def test_actual_worker_cancel_kills_descendants_and_cleans_job_temp(exact,video_request,tmp_path,monkeypatch):
    marker=slow_tesseract(exact,tmp_path,monkeypatch)
    call=start_call('post',exact.url+'/plate_search',json=video_request)
    try:
        deadline=time.monotonic()+5
        while not marker.exists() and time.monotonic()<deadline:
            time.sleep(.02)
        assert marker.exists(), 'OCR subprocess never started'
        assert request('post',exact.url+'/plate_search/cancel',
                       json={'request_id':video_request['request_id']}).status_code == 200
    finally:
        response=finish(call)
    assert response.status_code == 409 and response.json['state'] == 'cancelled'
    assert _dead(int(marker.read_text()))
    assert not list(Path(exact.job['dir']).glob('.plate-search-*'))
