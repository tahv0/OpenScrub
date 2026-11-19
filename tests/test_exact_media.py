"""Optional retained tiny-media production endpoint gates, independent pixels/PTS.

Set OPENSCRUB_EXACT_MEDIA to the pinned fixture manifest. Ordinary CI without
those research inputs skips this specific compatibility gate.
"""
import base64
from fractions import Fraction
import hashlib
import json
import os
import subprocess
from pathlib import Path

import cv2
import numpy as np
import pytest
import openscrub_web as web
from test_job_lifecycle import store,request
from test_exact_samples import sample


@pytest.fixture
def retained():
    manifest=os.environ.get('OPENSCRUB_EXACT_MEDIA')
    if not manifest:pytest.skip('retained exact media manifest not supplied')
    values=json.loads(Path(manifest).read_text())
    for value in values.values():
        assert hashlib.sha256(Path(value['path']).read_bytes()).hexdigest()==value['sha256']
    return values


def install(store,path,fps,count,normalized=False):
    store.job['video']=str(path)
    store.doc['provenance'].update(input=str(path),vfr_normalized=normalized,
        original_input=str(path)+'.original' if normalized else None)
    store.doc['render_state']=dict(fps=fps,cum=[[i*2,-i] for i in range(count)])
    store.doc['detections'][0].update(t_end=count/fps,last_seen=0)
    store.doc['detections'].append(dict(store.doc['detections'][0],enabled=False,text='disabled'))
    store.path.write_text(json.dumps(store.doc))


def oracle(path):
    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0',
        '-show_frames','-show_entries','frame=pts:stream=time_base','-of','json',str(path)],timeout=15))
    pts=[Fraction(row['pts'])*Fraction(probe['streams'][0]['time_base']) for row in probe['frames']]
    cap=cv2.VideoCapture(str(path));pixels=[]
    try:
        while True:
            ok,frame=cap.read()
            if not ok:break
            pixels.append(frame)
            assert len(pixels)<=60
    finally:cap.release()
    assert len(pixels)==len(pts)
    return pixels,pts


def marker(frame):
    return sum((int(frame[14,14+12*k,0])>128)<<k for k in range(6))


@pytest.mark.parametrize('label,times,indices',[
    ('cfr24',[.2],[4]),('cfr5',[1.9,2.],[9,9]),
    ('normalized',[.5,2/13,3/13,14/13],[6,2,3,13])])
def test_old_report_production_pixels_and_independent_pts(store,retained,monkeypatch,label,times,indices):
    value=retained[label];path=Path(value['path']);fps={'cfr24':24,'cfr5':5,'normalized':13}[label]
    refs,pts=oracle(path);install(store,path,fps,len(refs),label=='normalized')
    actual=[];real=web.exact.read_indexed_capture
    def read(*a,**kw):
        result=real(*a,**kw);actual.append(result);return result
    monkeypatch.setattr(web.exact,'read_indexed_capture',read)
    results=[]
    for t,index in zip(times,indices):
        response=sample(store,t);decoded=actual[-1]
        assert decoded.index==response['sample']['index']==index
        assert np.array_equal(decoded.pixels,refs[index])
        assert abs(decoded.observed_s-float(pts[index]))<1e-12
        shown=cv2.imdecode(np.frombuffer(base64.b64decode(response['image']['base64']),np.uint8),1)
        assert marker(shown)==marker(refs[index])
        assert response['sample']['offset']==[index*2,-index]
        assert [box['i'] for box in response['boxes']]==[0,1]
        results.append(dict(t=t,index=index,marker=marker(shown),pts=str(pts[index]),observed_s=decoded.observed_s,
            canonical_s=decoded.canonical_s,tolerance_s=web.exact.precision_bound(web.FILES.initialize(store.job).current_source['facts'],fps,len(refs))))
    output=Path(os.environ['VERIFY_RUN'])/'logs'/('media-'+label+'.json')
    output.write_text(json.dumps(dict(input=value,results=results),indent=2)+'\n')


def test_native_coarse_timebase_production_pixels_pts(store,retained,tmp_path):
    path=tmp_path/'coarse.mkv'
    subprocess.run(['ffmpeg','-v','error','-i',retained['cfr24']['path'],'-map','0:v:0','-c','copy',str(path)],check=True,timeout=15)
    refs,pts=oracle(path);install(store,path,24,len(refs))
    value=sample(store,.2);index=value['sample']['index']
    shown=cv2.imdecode(np.frombuffer(base64.b64decode(value['image']['base64']),np.uint8),1)
    facts=web.FILES.initialize(store.job).current_source['facts']
    bound=web.exact.precision_bound(facts,24,len(refs))
    assert facts['tick_s']==.001 and not facts['grid_aligned']
    assert index==4 and marker(shown)==marker(refs[index])
    assert value['sample']['observed_s']==pytest.approx(float(pts[index]),abs=1e-12)
    assert 1e-4<abs(float(pts[index])-index/24)<bound<.25/24
    (Path(os.environ['VERIFY_RUN'])/'logs'/'media-coarse.json').write_text(json.dumps(dict(
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),index=index,pts=str(pts[index]),
        sample=value['sample'],bound_s=bound,facts=facts),indent=2)+'\n')
