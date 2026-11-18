"""Strict optional admission/worker/publication on the real production routes."""
import copy
import json
import threading
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import openscrub as engine
import openscrub_web as web
from test_exact_samples import exact, sample, precondition, raw
from test_exact_media import retained, install, oracle
from test_job_lifecycle import store, request, start_call, finish


@pytest.fixture
def tracking(exact, monkeypatch):
    pc=precondition(sample(exact,.2),None)
    payload=dict(box=[8,8,40,40],t_ref=.2,t0=.1,t1=.3,seed=pc)
    threads, releases, models, calls = [], [], [], []
    original=web._start_owned_thread
    def start(target,lease):
        thread=original(target,lease); threads.append(thread); return thread
    def model(*args,**kwargs):
        models.append(True); return None
    def compute(video,box,t_ref,t0,t1,**kwargs):
        calls.append((video,box,t_ref,kwargs))
        return [(t_ref,box,.9)]
    monkeypatch.setattr(web,'_start_owned_thread',start)
    monkeypatch.setattr(engine,'PersonDetector',model)
    monkeypatch.setattr(engine,'track_manual_region',compute)
    result=SimpleNamespace(**locals())
    yield result
    for event in releases: event.set()
    for thread in threads:
        thread.join(8); assert not thread.is_alive(), 'tracking worker did not finish'


def launch(tracking, payload=None):
    response=request('post',tracking.exact.url+'/track_object',json=payload or tracking.payload)
    assert response.status_code == 200, response.get_data(as_text=True)
    return response


def joined(tracking):
    for thread in tracking.threads:
        thread.join(8); assert not thread.is_alive()
    return request('get',tracking.exact.url+'/track_status').json


def test_strict_launch_verifies_before_models(tracking,monkeypatch):
    before=tracking.exact.path.read_bytes()
    def fail(*args,**kwargs): raise web.exact.ExactError('decode oracle')
    monkeypatch.setattr(web.exact,'read_indexed_capture',fail)
    launch(tracking)
    status=joined(tracking)
    assert status == dict(state='done',added=0,error='decode oracle')
    assert tracking.models == [] and tracking.calls == []
    assert tracking.exact.path.read_bytes() == before


def test_strict_capture_closed_before_model_resolution(tracking,monkeypatch):
    captures=[]; original=web.cv2.VideoCapture
    class Capture:
        def __init__(self,*args): self.cap=original(*args);self.releases=0;captures.append(self)
        def __getattr__(self,key): return getattr(self.cap,key)
        def release(self): self.releases+=1; self.cap.release()
    def model(*a,**kw):
        assert len(captures)==1 and captures[0].releases==1
        tracking.models.append(True); return None
    monkeypatch.setattr(web.cv2,'VideoCapture',Capture)
    monkeypatch.setattr(engine,'PersonDetector',model)
    launch(tracking); status=joined(tracking)
    assert status['added']==1 and status['error'] is None
    assert tracking.models == [True]
    seed=tracking.calls[0][3]['strict_seed']
    assert seed.index==1 and seed.canonical_s==.2 and seed.count==10
    assert seed.pixels.shape==(48,64,3) and abs(float(seed.pixels.mean())-20)<3
    assert seed.source_selection is web.FILES.initialize(tracking.exact.job).current_source
    assert captures[0].releases == 1


@pytest.mark.parametrize('change',['source','timeline'],ids=['source','timeline'])
def test_strict_source_or_timeline_change_rejects_append(tracking,monkeypatch,change):
    entered,release=threading.Event(),threading.Event();tracking.releases.append(release)
    def compute(*args,**kwargs):
        entered.set(); assert release.wait(8)
        return [(.2,[8,8,40,40],.9)]
    monkeypatch.setattr(engine,'track_manual_region',compute)
    launch(tracking)
    try:
        assert entered.wait(5)
        if change=='source': Path(tracking.exact.job['video']).write_bytes(b'changed source')
        else:
            doc=raw(tracking.exact);doc['render_state']['cum'][1]=[99,98]
            tracking.exact.path.write_text(json.dumps(doc))
        before=tracking.exact.path.read_bytes()
    finally: release.set()
    status=joined(tracking)
    assert status['state']=='done' and status['added']==0 and status['error']
    assert tracking.exact.path.read_bytes()==before


def test_strict_unrelated_choice_audio_merge(tracking,monkeypatch):
    entered,release=threading.Event(),threading.Event();tracking.releases.append(release)
    def compute(*a,**kw): entered.set();assert release.wait(8);return [(.2,[8,8,40,40],.9)]
    monkeypatch.setattr(engine,'track_manual_region',compute)
    doc=raw(tracking.exact);doc['future']={'retained':[1,'x']}
    doc['detections'][0]['manual_id']='existing:immutable'
    doc['detections'][0]['manual_creation']={'opaque':'preserved'}
    doc['detections'][1]['track']=17
    tracking.exact.path.write_text(json.dumps(doc))
    launch(tracking)
    try:
        assert entered.wait(5)
        r=request('post',tracking.exact.url+'/detections',json={'enabled':{'0':False},'audio':[{'t0':0,'t1':.4}]})
        assert r.status_code==200
        before=raw(tracking.exact)
    finally: release.set()
    assert joined(tracking)['added']==1
    after=raw(tracking.exact)
    assert after['detections'][:2]==before['detections']
    assert after['future']==before['future'] and after['audio_redactions']==before['audio_redactions']
    assert after['detections'][2]['track']==18
    assert after['detections'][2]['cbox']==[7,9,39,41]


def test_strict_window_rejects_uncanonical_reference(tracking):
    p=copy.deepcopy(tracking.payload);p.update(t_ref=.21,t0=.205,t1=.3)
    response=request('post',tracking.exact.url+'/track_object',json=p)
    assert response.status_code==400
    assert tracking.models==[] and tracking.threads==[]


@pytest.mark.parametrize('field,value', [('seed',None),('seed',{}),('t_ref',True),
    ('t0',False),('t1',float('inf')),('box',[8,8,65,40]),('box',[True,8,40,40])],
    ids=['null-seed','empty-seed','bool-reference','bool-start','infinite-end','outside-box','bool-box'])
def test_invalid_explicit_seed_is_not_legacy(tracking,field,value):
    p=copy.deepcopy(tracking.payload);p[field]=value
    before=tracking.exact.path.read_bytes()
    response=request('post',tracking.exact.url+'/track_object',json=p)
    assert response.status_code==400
    assert tracking.models==[] and tracking.threads==[]
    assert tracking.exact.path.read_bytes()==before


@pytest.mark.parametrize('field,value',[('index',9),('width',65),('offset',[4,5]),
    ('timeline_eq','0'*64),('source_ref','stale')],ids=['index','width','offset','timeline','source'])
def test_strict_stale_precondition_rejected_before_launch(tracking,field,value):
    p=copy.deepcopy(tracking.payload);p['seed'][field]=value
    response=request('post',tracking.exact.url+'/track_object',json=p)
    assert response.status_code in (400,409)
    assert tracking.models==[] and tracking.threads==[]


def test_strict_timeline_change_during_decode_prevents_models(tracking,monkeypatch):
    entered,release=threading.Event(),threading.Event();tracking.releases.append(release)
    original=web.exact.read_indexed_capture
    def decode(*args,**kwargs):
        decoded=original(*args,**kwargs)
        entered.set();assert release.wait(8);return decoded
    monkeypatch.setattr(web.exact,'read_indexed_capture',decode)
    launch(tracking)
    try:
        assert entered.wait(5)
        doc=raw(tracking.exact);doc['render_state']['cum'][1]=[3,4]
        tracking.exact.path.write_text(json.dumps(doc));before=tracking.exact.path.read_bytes()
    finally: release.set()
    status=joined(tracking)
    assert status['added']==0 and status['error']
    assert tracking.models==[] and tracking.calls==[]
    assert tracking.exact.path.read_bytes()==before


def test_legacy_route_uses_unchanged_tracker_call(tracking,monkeypatch):
    def fail(*a,**kw): pytest.fail('legacy exact decode')
    monkeypatch.setattr(web.exact,'read_indexed_capture',fail)
    p=copy.deepcopy(tracking.payload);del p['seed']
    launch(tracking,p);assert joined(tracking)['added']==1
    assert 'strict_seed' not in tracking.calls[0][3]



def test_strict_cancel_after_snapshot_rejects_install(tracking,monkeypatch):
    original=web._exact_snapshot
    def snapshot(job):
        result=original(job)
        job['cancel'].set()
        return result
    monkeypatch.setattr(web,'_exact_snapshot',snapshot)
    before=tracking.exact.path.read_bytes()
    response=request('post',tracking.exact.url+'/track_object',json=tracking.payload)
    assert response.status_code==409
    assert tracking.models==[] and tracking.calls==[] and tracking.threads==[]
    assert tracking.exact.path.read_bytes()==before


@pytest.mark.parametrize('boundary',['tracker','commit','thread'],ids=['tracker','commit','thread-start'])
def test_strict_errors_retain_failure_and_release_owners(tracking,monkeypatch,boundary):
    before=tracking.exact.path.read_bytes()
    files=web.FILES.initialize(tracking.exact.job);epoch=files.committed_report_epoch
    errors=[]
    def fail(*a,**kw):
        error=RuntimeError(boundary+' retained oracle');errors.append(error);raise error
    if boundary=='tracker': monkeypatch.setattr(engine,'track_manual_region',fail)
    elif boundary=='commit': monkeypatch.setattr(web,'atomic_report',fail)
    else: monkeypatch.setattr(web.threading.Thread,'start',fail)
    response=request('post',tracking.exact.url+'/track_object',json=tracking.payload)
    assert response.status_code==(500 if boundary=='thread' else 200)
    status=joined(tracking)
    assert status['state']=='done' and status['added']==0 and status['error']
    assert len(errors)==1 and str(errors[0])==boundary+' retained oracle'
    assert tracking.exact.path.read_bytes()==before
    assert files.committed_report_epoch==epoch and web.FILES.count==0


def test_strict_cancel_during_decode_makes_zero_model_calls(tracking,monkeypatch):
    original=web.exact.read_indexed_capture
    def decode(*a,**kw):
        decoded=original(*a,**kw)
        tracking.exact.job['cancel'].set()
        return decoded
    monkeypatch.setattr(web.exact,'read_indexed_capture',decode)
    before=tracking.exact.path.read_bytes()
    launch(tracking);joined(tracking)
    assert tracking.models==[] and tracking.calls==[]
    assert tracking.exact.path.read_bytes()==before and web.FILES.count==0


def test_strict_model_resolution_failure_keeps_seed_for_generic(tracking,monkeypatch):
    errors=[]
    def model(*a,**kw):
        error=RuntimeError('model retained oracle');errors.append(error);raise error
    monkeypatch.setattr(engine,'PersonDetector',model)
    launch(tracking)
    assert joined(tracking)['added']==1
    assert len(errors)==1
    assert tracking.calls[0][3]['strict_seed'].index==1


def test_strict_cancel_during_compute_cannot_publish(tracking,monkeypatch):
    def compute(*a,**kw):
        tracking.exact.job['cancel'].set()
        return [(.2,[8,8,40,40],.9)]
    monkeypatch.setattr(engine,'track_manual_region',compute)
    before=tracking.exact.path.read_bytes();launch(tracking);joined(tracking)
    assert tracking.exact.path.read_bytes()==before and web.FILES.count==0


@pytest.mark.parametrize('label,times,indices',[
    ('cfr24',[.2],[4]),('cfr5',[1.9],[9]),
    ('normalized',[.5,2/13,3/13],[6,2,3])],ids=['native24','native5-last','normalized-duplicates'])
def test_retained_strict_route_and_actual_engine_priming(store,retained,monkeypatch,label,times,indices):
    value=retained[label];path=Path(value['path'])
    fps={'cfr24':24,'cfr5':5,'normalized':13}[label]
    refs,pts=oracle(path);install(store,path,fps,len(refs),label=='normalized')
    threads,initializers,reads=[],[],[]
    real_start=web._start_owned_thread;real_read=web.exact.read_indexed_capture
    def start(target,lease):
        thread=real_start(target,lease);threads.append(thread);return thread
    def read(cap,index,**kwargs):
        decoded=real_read(cap,index,**kwargs);reads.append(decoded);return decoded
    class Tracker:
        def init(self,frame,box):initializers.append(frame.copy())
    monkeypatch.setattr(web,'_start_owned_thread',start)
    monkeypatch.setattr(web.exact,'read_indexed_capture',read)
    monkeypatch.setattr(engine,'PersonDetector',lambda *a,**kw:None)
    monkeypatch.setattr(engine,'_vittrack_factory',lambda log:Tracker)
    results=[]
    try:
        for requested,index in zip(times,indices):
            pc=precondition(sample(store,requested),None)
            reads.clear();initializers.clear()
            canonical=index/fps
            body=dict(seed=pc,box=[8,8,40,40],t_ref=canonical,
                      t0=max(0,canonical-.001),t1=canonical+.001)
            response=request('post',store.url+'/track_object',json=body)
            assert response.status_code==200,response.get_data(as_text=True)
            threads[-1].join(8);assert not threads[-1].is_alive()
            status=request('get',store.url+'/track_status').json
            assert status['added']==1 and status['error'] is None,status
            assert [r.index for r in reads]==[index,index]
            assert len(initializers)==2
            for decoded in reads:
                np.testing.assert_array_equal(decoded.pixels,refs[index])
                assert abs(decoded.observed_s-float(pts[index]))<1e-12
                assert decoded.canonical_s==canonical
            expected=web.cv2.resize(refs[index],None,fx=.5,fy=.5)
            for frame in initializers:np.testing.assert_array_equal(frame,expected)
            results.append(dict(requested_s=requested,index=index,canonical_s=canonical,
                independent_pts=str(pts[index]),observed_s=reads[0].observed_s,
                indexed_reads=len(reads),vit_initializers=len(initializers)))
    finally:
        for thread in threads:
            thread.join(8);assert not thread.is_alive()
    import os
    (Path(os.environ['VERIFY_RUN'])/'logs'/('strict-media-'+label+'.json')).write_text(
        json.dumps(dict(source=value,results=results),indent=2)+'\n')
