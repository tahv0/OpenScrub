"""Optional real-model web scan, rehydration and native SDR render evidence."""
import hashlib
import io
import json
import os
from pathlib import Path
import threading

import cv2
import numpy as np
import pytest
import openscrub
import openscrub_web as web
from test_job_lifecycle import store, request


def _run_queue():
    web.WORK_Q.put(None)
    thread=threading.Thread(target=web.worker)
    thread.start();thread.join(45)
    assert not thread.is_alive(), 'web worker did not finish'


def _glyph_mask():
    mask=np.zeros((360,640),np.uint8)
    x,y,w,h=204,149,232,62
    tw,th=cv2.getTextSize('QZ 27 KTX',cv2.FONT_HERSHEY_SIMPLEX,1.12,2)[0]
    cv2.putText(mask,'QZ 27 KTX',(x+(w-tw)//2,y+(h+th)//2),
                cv2.FONT_HERSHEY_SIMPLEX,1.12,255,2,cv2.LINE_AA)
    return mask>230


def _output_pixels(path,mask):
    cap=cv2.VideoCapture(str(path));coverage=[];paper=[]
    try:
        while True:
            ok,frame=cap.read()
            if not ok:break
            coverage.append(int((frame[mask].mean(1)<10).sum()))
            paper.append(float(frame[154,210].mean()))
    finally:cap.release()
    return coverage,paper


def _replace_source_with_changed_frames(path):
    """Simulate a later transcode without changing the plate's position."""
    path=Path(path);temporary=path.with_name('transcoded.mp4')
    source=cv2.VideoCapture(str(path))
    target=cv2.VideoWriter(str(temporary),cv2.VideoWriter_fourcc(*'mp4v'),10,(640,360))
    assert source.isOpened() and target.isOpened()
    count=0
    try:
        while True:
            ok,frame=source.read()
            if not ok:break
            frame[:40,:40]=255
            target.write(frame);count+=1
    finally:
        source.release();target.release()
    assert count==4
    os.replace(temporary,path)
    source=cv2.VideoCapture(str(path));digests=[]
    try:
        while True:
            ok,frame=source.read()
            if not ok:break
            digests.append(openscrub._frame_sha256(frame))
    finally:source.release()
    return digests


def test_real_web_scan_reopen_and_render_with_stock_models(store,monkeypatch,tmp_path):
    textdir=os.environ.get('OPENSCRUB_TEST_PPDET_DIR')
    platepath=os.environ.get('OPENSCRUB_TEST_PLATE_MODEL')
    inputpath=os.environ.get('OPENSCRUB_TEST_LETTERING_VIDEO')
    if not all((textdir,platepath,inputpath)):
        pytest.skip('set stock PP detector, plate model and positive synthetic clip paths')
    ort=pytest.importorskip('onnxruntime')
    assert hashlib.sha256((Path(textdir)/'text_detection_ppocrv5_mobile.onnx').read_bytes()).hexdigest()=='a431985659dc921974177a95adcfbb90fd9e51989a5e04d70d0b75f597b6e61d'
    assert hashlib.sha256(Path(platepath).read_bytes()).hexdigest()=='c3c1026ca7d0585dd88084d68182dd897113712fa734ae1557ca70174440c076'
    assert hashlib.sha256(Path(inputpath).read_bytes()).hexdigest()=='0884add6fbd7db1ecf6b65dc1e4f96368f8f9fdb6f0464f75ddbe009157c7a8c'
    monkeypatch.setattr(openscrub,'_model_dir',lambda:str(textdir))
    def cpu_session(path):
        options=ort.SessionOptions();options.intra_op_num_threads=options.inter_op_num_threads=1
        return ort.InferenceSession(path,sess_options=options,providers=['CPUExecutionProvider'])
    monkeypatch.setattr(openscrub,'_ort_session',cpu_session)
    monkeypatch.setattr(web,'load_model_select',lambda:{'plate':'plate_yolov9_640'})
    monkeypatch.setattr(web,'find_model_file',lambda name:str(platepath) if name=='plate_yolov9_640.onnx' else None)
    monkeypatch.setenv('OPENSCRUB_NO_AUTOFETCH','1')
    threads=[];start=web._start_owned_thread
    def own(target,lease):
        thread=start(target,lease);threads.append(thread);return thread
    monkeypatch.setattr(web,'_start_owned_thread',own)
    options={'categories':'plate','plate_coverage':'narrow','plate_threshold':.10,
             'mode':'box','pad':0,'encoder':'x264','scan_speed':'thorough'}
    response=request('post','/api/jobs',data={'video':(io.BytesIO(Path(inputpath).read_bytes()),'fixture.mp4'),
        'options':json.dumps(options)},content_type='multipart/form-data')
    assert response.status_code==200
    jid=response.json['jobs'][0];job=web.JOBS[jid];report=Path(job['dir'])/'report.json'
    _run_queue()
    for thread in threads:thread.join(10);assert not thread.is_alive()
    assert job['phase']=='review',job['log'].snapshot()['lines']
    doc=json.loads(report.read_text())
    assert doc['provenance']['settings']['plate_coverage']=='narrow'
    rows=[row for row in doc['detections'] if row.get('category')=='plate']
    assert len(rows)==4 and [r['narrow_plate']['frame_index'] for r in rows]==[0,1,2,3]
    assert any(row['poly'] for row in rows) and any(row['narrow_plate']['fallback'] for row in rows)
    assert web.FILES.initialize(job).count==0
    web.JOBS.pop(jid);web.rehydrate_jobs();job=web.JOBS[jid]
    assert job['phase']=='review' and job['options']['plate_coverage']=='narrow'
    # Saved report is authoritative even if an unrelated in-memory setting differs.
    job['options']['plate_coverage']='full'
    assert request('post','/api/jobs/'+jid+'/render').status_code==200
    _run_queue()
    assert job['phase']=='done',job['log'].snapshot()['lines']
    rendered=json.loads(report.read_text())
    assert rendered['provenance']['settings']['plate_coverage']=='narrow'
    assert [r['narrow_plate'] for r in rendered['detections'] if r.get('category')=='plate']==[r['narrow_plate'] for r in rows]
    mask=_glyph_mask();assert int(mask.sum())==1080
    coverage,paper=_output_pixels(job['output'],mask)
    assert coverage==[1080]*4
    for row,pixel in zip(rows,paper):
        assert pixel>150 if row['poly'] else pixel<50

    # A later transcode changes the pixels inspected at scan time. Saved
    # polygons must not be reused for the altered source, even after reopen.
    changed=_replace_source_with_changed_frames(job['video'])
    assert len(changed)==len(rows)
    assert all(digest!=row['narrow_plate']['frame_sha256'] for digest,row in zip(changed,rows))
    assert request('post','/api/jobs/'+jid+'/render').status_code==200
    _run_queue()
    assert job['phase']=='done',job['log'].snapshot()['lines']
    coverage,paper=_output_pixels(job['output'],mask)
    assert coverage==[1080]*4
    assert len(paper)==4 and all(pixel<50 for pixel in paper)
    assert any('frame or geometry evidence unavailable' in line
               for line in job['log'].snapshot()['lines'])
