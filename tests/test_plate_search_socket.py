"""Loopback check of the actual HTTP route and stock OCR worker."""
import json
import os
import shutil
from pathlib import Path

import pytest
from test_exact_samples import exact, sample, precondition
from test_job_lifecycle import store
from test_report_transactions import socket_api
from test_plate_text_real_ocr import _clip

pytestmark = [pytest.mark.skipif(os.name != 'posix', reason='worker isolation is POSIX-only'),
              pytest.mark.skipif(not shutil.which('tesseract'), reason='local Tesseract unavailable')]


def test_loopback_search_uses_real_ocr_without_report_mutation(exact,socket_api):
    _clip(Path(exact.job['video']))
    doc=json.loads(exact.path.read_text())
    doc['render_state']={'fps':4,'cum':[[0,0]]*4}
    exact.path.write_text(json.dumps(doc))
    seed=precondition(sample(exact,0),None)
    body={'seed':seed,'query':'JF5','mode':'fragment','request_id':'a'*32}
    before=exact.path.read_bytes()
    status,headers,data=socket_api('POST',exact.url+'/plate_search',body)
    result=json.loads(data)
    assert status == 200 and result['state'] == 'complete' and result['index'] == 0
    assert result['suggestions'] and all(row['match']=='fragment' for row in result['suggestions'])
    assert headers['Cache-Control'] == 'private, no-store'
    assert b'JF5' not in data and exact.path.read_bytes() == before
    assert not list(Path(exact.job['dir']).glob('.plate-search-*'))


def test_loopback_sampled_search_reports_only_examined_frames(exact,socket_api):
    _clip(Path(exact.job['video']))
    doc=json.loads(exact.path.read_text())
    doc['render_state']={'fps':4,'cum':[[0,0]]*4}
    exact.path.write_text(json.dumps(doc))
    body={'seed':precondition(sample(exact,0),None),'query':'JF5','mode':'fragment',
          'request_id':'a'*32,'scope':'sampled'}
    before=exact.path.read_bytes()
    status,headers,data=socket_api('POST',exact.url+'/plate_search',body)
    result=json.loads(data)
    assert status == 200 and result['state'] == 'complete'
    assert result['frame_count'] == 4
    assert [f['index'] for f in result['frames']] == [0,1,2,3]
    assert [f['time_s'] for f in result['frames']] == [0,.25,.5,.75]
    assert result['frames'][0]['matches']>0 and result['frames'][2]['matches']>0
    assert result['frames'][1]['matches']==result['frames'][3]['matches']==0
    assert headers['Cache-Control']=='private, no-store' and b'JF5' not in data
    assert exact.path.read_bytes()==before
    assert not list(Path(exact.job['dir']).glob('.plate-search-*'))
