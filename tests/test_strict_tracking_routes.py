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
    elif boundary=='commit': monkeypatch.setattr(web,'_publish_job_report_locked',fail)
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



def test_strict_snapshot_exception_releases_preparation(tracking,monkeypatch):
    errors=[]
    def policy(*a,**kw):
        error=RuntimeError('snapshot retained oracle');errors.append(error);raise error
    monkeypatch.setattr(web,'_exact_policy',policy)
    before=tracking.exact.path.read_bytes()
    response=request('post',tracking.exact.url+'/track_object',json=tracking.payload)
    assert response.status_code==500 and len(errors)==1
    assert tracking.models==[] and tracking.exact.path.read_bytes()==before
    assert web.FILES.count==0


def test_strict_publication_retains_integer_reference_offset(exact,monkeypatch):
    writer=web.cv2.VideoWriter(exact.job['video'],web.cv2.VideoWriter_fourcc(*'MJPG'),13,(64,48))
    assert writer.isOpened()
    try:
        for i in range(26):writer.write(np.full((48,64,3),i*8,dtype=np.uint8))
    finally:writer.release()
    doc=raw(exact);doc['render_state']=dict(fps=13,cum=[[i,-i] for i in range(26)])
    exact.path.write_text(json.dumps(doc))
    pc=precondition(sample(exact,1.16),None)
    assert pc['index']==15 and int((15/13)*13)==14
    threads=[];real_start=web._start_owned_thread
    def start(target,lease):
        thread=real_start(target,lease);threads.append(thread);return thread
    monkeypatch.setattr(web,'_start_owned_thread',start)
    monkeypatch.setattr(engine,'PersonDetector',lambda *a,**kw:None)
    monkeypatch.setattr(engine,'track_manual_region',lambda *a,**kw:[(15/13,[20,8,52,40],.9)])
    try:
        response=request('post',exact.url+'/track_object',json=dict(seed=pc,
            box=[20,8,52,40],t_ref=15/13,t0=1.15,t1=1.16))
        assert response.status_code==200
    finally:
        for thread in threads:thread.join(8);assert not thread.is_alive()
    assert request('get',exact.url+'/track_status').json['added']==1
    assert raw(exact)['detections'][-1]['aoff']==[15,-15]
    assert raw(exact)['detections'][-1]['cbox']==[5,23,37,55]



def test_fresh_strict_track_after_acknowledged_idle_cancel(tracking):
    files=web.FILES.initialize(tracking.exact.job)
    selected=files.current_source
    response=request('post',tracking.exact.url+'/cancel')
    assert response.status_code==200 and tracking.exact.job['cancel'].is_set()
    assert files.operation is None and files.current_source is selected
    assert files.source_status=='coherent'
    launch(tracking)
    status=joined(tracking)
    assert status['added']==1 and status['error'] is None,status
    assert tracking.calls[0][3]['strict_seed'].index==1



@pytest.mark.parametrize('hold_at',[1,2,3],ids=['installation','pre-model','preappend'])
def test_strict_cancel_during_context_read_never_advances(tracking,monkeypatch,hold_at):
    files=web.FILES.initialize(tracking.exact.job)
    if hold_at==1:
        # A real completed attempt supplies the Event cancelled before lock entry.
        legacy=copy.deepcopy(tracking.payload);del legacy['seed']
        launch(tracking,legacy);assert joined(tracking)['added']==1
        assert files.operation is not None and not files.operation.is_set()
        tracking.models.clear();tracking.calls.clear()
    entered,release,signalled=(threading.Event() for _ in range(3))
    tracking.releases.append(release)
    original=web._load_job_report;reads=[]
    def load(job):
        reads.append(True)
        if len(reads)==hold_at:
            entered.set();assert release.wait(8)
        return original(job)
    monkeypatch.setattr(web,'_load_job_report',load)
    before=tracking.exact.path.read_bytes()
    launch_call=cancel_call=None
    try:
        if hold_at==1:
            launch_call=start_call('post',tracking.exact.url+'/track_object',json=tracking.payload)
        else:launch(tracking)
        assert entered.wait(5),'actual context read was not held'
        operation=files.operation
        assert operation is not None
        original_set=operation.set
        def signal():
            original_set();signalled.set()
        monkeypatch.setattr(operation,'set',signal)
        cancel_call=start_call('post',tracking.exact.url+'/cancel')
        assert signalled.wait(5),'real cancel did not signal before report-lock entry'
    finally:
        release.set()
        if launch_call is not None:launch_response=finish(launch_call)
        if cancel_call is not None:cancel_response=finish(cancel_call)
        status=joined(tracking)
    assert cancel_response.status_code==200
    if hold_at==1:assert launch_response.status_code==409
    assert tracking.exact.path.read_bytes()==before,'cancelled strict work published rows'
    assert len(tracking.models)==(1 if hold_at==3 else 0),'model resolved after cancellation'
    assert len(tracking.calls)==(1 if hold_at==3 else 0)
    assert web.FILES.count==0



@pytest.mark.parametrize('boundary',['constructor','open-state'],ids=['constructor','open-state'])
def test_strict_generic_entry_error_keeps_web_cleanup_and_no_publication(exact,monkeypatch,boundary):
    pc=precondition(sample(exact,.2),None)
    before=exact.path.read_bytes();files=web.FILES.initialize(exact.job)
    epoch=files.committed_report_epoch
    captures=[];threads=[];models=[];observed=[]
    native=RuntimeError('generic web '+boundary+' retained oracle')
    real_capture=web.cv2.VideoCapture;real_track=engine.track_manual_region
    real_start=web._start_owned_thread;attempts=[]
    class Capture:
        def __init__(self,video):
            attempts.append(video)
            if len(attempts)==2 and boundary=='constructor':raise native
            self.cap=real_capture(video);self.releases=0
            captures.append(self)
        def __getattr__(self,key):return getattr(self.cap,key)
        def isOpened(self):
            if len(captures)==2 and self is captures[1] and boundary=='open-state':raise native
            return self.cap.isOpened()
        def release(self):self.releases+=1;self.cap.release()
    def model(*a,**kw):
        assert captures and captures[0].releases==1
        models.append(True);return None
    def track(*a,**kw):
        try:return real_track(*a,**kw)
        except BaseException as error:observed.append(error);raise
    def start(target,lease):
        thread=real_start(target,lease);threads.append(thread);return thread
    monkeypatch.setattr(web.cv2,'VideoCapture',Capture)
    monkeypatch.setattr(engine,'PersonDetector',model)
    monkeypatch.setattr(engine,'track_manual_region',track)
    monkeypatch.setattr(engine,'_vittrack_factory',lambda log:pytest.fail('generic initializer fallback after source entry error'))
    monkeypatch.setattr(engine,'_track_person_dense',lambda *a,**kw:pytest.fail('person fallback after generic source entry error'))
    monkeypatch.setattr(web,'_start_owned_thread',start)
    try:
        response=request('post',exact.url+'/track_object',json=dict(seed=pc,
            box=[8,8,40,40],t_ref=.2,t0=.199,t1=.201))
        assert response.status_code==200
    finally:
        for thread in threads:thread.join(8);assert not thread.is_alive()
    status=request('get',exact.url+'/track_status').json
    assert status['state']=='done' and status['added']==0 and 'retained oracle' in status['error']
    assert models==[True], 'web factory resolution is before generic capture entry'
    assert len(observed)==1 and isinstance(observed[0],web.exact.ExactError)
    assert observed[0].__cause__ is native
    assert len(attempts)==2
    assert [cap.releases for cap in captures]==([1] if boundary=='constructor' else [1,1])
    assert exact.path.read_bytes()==before and files.committed_report_epoch==epoch
    assert web.FILES.count==0


@pytest.mark.parametrize('change,boundary', [
    ('publication', 'admission'), ('recovery', 'admission'),
    ('publication', 'decode'), ('recovery', 'decode'),
    ('publication', 'compute'), ('recovery', 'compute'),
    ('publication', 'model'), ('recovery', 'model'),
    ('stable', None),
])
def test_strict_track_refuses_changed_containing_source(tracking, monkeypatch, change, boundary):
    source = web.new_job('', {}, 'source.avi')
    foreign = Path(source['dir']) / 'output.avi'
    foreign.write_bytes(Path(tracking.exact.job['video']).read_bytes())
    source.update(video=str(foreign), phase='review')
    tracking.exact.job['video'] = str(foreign)
    doc = raw(tracking.exact)
    doc['provenance']['input'] = str(foreign)
    tracking.exact.path.write_text(json.dumps(doc))
    # The fixture previously sampled its own file. Set up a fresh observation
    # of the containing job's file for the strict request.
    files = web.FILES.initialize(tracking.exact.job)
    files.current_source = None
    tracking.payload['seed'] = precondition(sample(tracking.exact), None)
    before = tracking.exact.path.read_bytes()
    epoch = files.output_epoch, files.committed_report_epoch
    owner = web.FILES.initialize(source)
    report = Path(source['dir']) / 'report.json'
    report.write_text('{}')

    def change_owner():
        with owner.report_lock:
            if change == 'publication':
                web._publish_job_report_locked(source, str(report), {'updated': True})
            else:
                owner.recovery_required = True

    if boundary == 'admission':
        original = web._own_files

        def reserve(job=None, work=False):
            lease = original(job, work)
            if work:
                change_owner()
            return lease

        monkeypatch.setattr(web, '_own_files', reserve)
    elif boundary == 'decode':
        original = web.exact.read_indexed_capture

        def decode(*args, **kwargs):
            decoded = original(*args, **kwargs)
            change_owner()
            return decoded

        monkeypatch.setattr(web.exact, 'read_indexed_capture', decode)
    elif boundary == 'model':
        def resolve_model(*args, **kwargs):
            tracking.models.append(True)
            change_owner()
            return None

        monkeypatch.setattr(engine, 'PersonDetector', resolve_model)
    elif boundary == 'compute':
        def compute(*args, **kwargs):
            tracking.calls.append(True)
            change_owner()
            return [(0.2, [8, 8, 40, 40], 0.9)]

        monkeypatch.setattr(engine, 'track_manual_region', compute)

    if change == 'stable':
        launch(tracking)
        assert joined(tracking) == {'state': 'done', 'added': 1, 'error': None}
        assert len(tracking.models) == len(tracking.calls) == 1
        assert raw(tracking.exact)['detections'][-1]['aoff'] == [1, -1]
        assert (files.output_epoch, files.committed_report_epoch) == tuple(value + 1 for value in epoch)
        assert files.work == owner.count == web.FILES.count == 0
        return
    if boundary == 'admission':
        response = request('post', tracking.exact.url + '/track_object', json=tracking.payload)
        assert response.status_code == 409
        assert response.json['error'] == 'sample_conflict'
        assert not tracking.threads
    else:
        launch(tracking)
        status = joined(tracking)
        assert status['state'] == 'done' and status['added'] == 0
        assert 'containing source' in status['error']
    assert len(tracking.models) == int(boundary in ('model', 'compute'))
    assert len(tracking.calls) == int(boundary == 'compute')
    assert tracking.exact.path.read_bytes() == before
    assert (files.output_epoch, files.committed_report_epoch) == epoch
    assert files.work == owner.count == web.FILES.count == 0


def test_strict_track_refuses_new_report_input_with_same_timeline(tracking, monkeypatch):
    replacement = Path(tracking.exact.job['dir']) / 'replacement.avi'
    replacement.write_bytes(Path(tracking.exact.job['video']).read_bytes())
    doc = raw(tracking.exact)
    doc['provenance']['input'] = str(replacement)
    replaced = json.dumps(doc).encode()

    def compute(*args, **kwargs):
        tracking.exact.path.write_bytes(replaced)
        return [(0.2, [8, 8, 40, 40], 0.9)]

    monkeypatch.setattr(engine, 'track_manual_region', compute)
    launch(tracking)
    status = joined(tracking)
    assert status['added'] == 0 and 'report input' in status['error']
    assert tracking.exact.path.read_bytes() == replaced
    assert web.FILES.count == 0


@pytest.mark.parametrize('replacement', [b'[]', b'{', None], ids=['list', 'invalid-json', 'missing'])
def test_strict_track_reports_invalid_latest_report_during_admission(tracking, monkeypatch, replacement):
    reserve = web._own_files

    def replace_before_admission(job=None, work=False):
        lease = reserve(job, work)
        if work:
            if replacement is None:
                tracking.exact.path.unlink()
            else:
                tracking.exact.path.write_bytes(replacement)
        return lease

    monkeypatch.setattr(web, '_own_files', replace_before_admission)
    response = request('post', tracking.exact.url + '/track_object', json=tracking.payload)
    assert response.status_code == 409
    assert response.json['error'] == 'sample_conflict'
    assert not tracking.threads and web.FILES.count == 0
