"""Short reads validate managed publication epochs; streams own real descriptors."""
import os
from pathlib import Path

import numpy as np
import pytest

import openscrub_web as web
from test_job_lifecycle import store, request


@pytest.mark.parametrize('overlap', ['constructor','read','constructor-error','read-error'])
def test_frame_retries_commit_during_constructor_or_read(store, monkeypatch, overlap):
    output=Path(store.job['dir'])/'output.mp4';output.write_bytes(b'old')
    store.job['output']=str(output)
    files=web.FILES.initialize(store.job)
    handles=[]
    class Capture:
        def __init__(self,path):
            assert not files.report_lock.locked()
            self.closed=False;handles.append(self)
            if len(handles)==1 and overlap.startswith('constructor'):
                with files.report_lock:
                    files.output_epoch += 1
                    output.write_bytes(b'new')
                if overlap.endswith('error'): raise OSError('overlapped constructor')
        def set(self,*args): pass
        def read(self):
            assert not files.report_lock.locked()
            if len(handles)==1 and overlap.startswith('read'):
                with files.report_lock:
                    files.output_epoch += 1
                    output.write_bytes(b'new')
                if overlap.endswith('error'): raise OSError('overlapped read')
            return True,np.full((8,8,3),20 if len(handles)==1 else 200,dtype=np.uint8)
        def release(self): self.closed=True
    monkeypatch.setattr(web.cv2,'VideoCapture',Capture)
    response=request('get',store.url+'/frame_at?src=output')
    assert response.status_code==200,response.data
    assert len(handles)==2
    # A constructor which raises did not return ownership; every acquired
    # capture is released by production before this assertion.
    assert all(h.closed for h in handles[(1 if overlap=='constructor-error' else 0):])
    frame=web.cv2.imdecode(np.frombuffer(response.data,np.uint8),1)
    assert frame.mean()>150


def test_frame_two_invalidations_returns_explicit_stale(store, monkeypatch):
    files=web.FILES.initialize(store.job); handles=[]
    class Capture:
        def __init__(self,path): self.closed=False;handles.append(self)
        def set(self,*args): pass
        def read(self):
            with files.report_lock: files.output_epoch += 1
            return False,None
        def release(self): self.closed=True
    monkeypatch.setattr(web.cv2,'VideoCapture',Capture)
    response=request('get',store.url+'/frame_at?src=output')
    assert response.status_code==409,response.data
    assert b'output changed during frame read; retry' in response.data
    assert len(handles)==2 and all(h.closed for h in handles)


def test_frame_rejects_failed_attempt_and_successful_rollback_aba(store, monkeypatch):
    from openscrub_internal.render_delivery import _RenderDelivery
    output=Path(store.job['dir'])/'output.mp4';output.write_bytes(b'old')
    store.job['output']=str(output);files=web.FILES.initialize(store.job)
    report_before=store.path.read_bytes();handles=[]
    class Capture:
        def __init__(self,path): handles.append(self);self.closed=False
        def set(self,*args): pass
        def read(self):
            if len(handles)==1:
                with _RenderDelivery(str(output),str(store.path)) as owned:
                    Path(owned.video_stage).write_bytes(b'new');owned.prepare_report({'new':True});owned.prepare_rollback()
                    def mutate(): files.output_epoch += 1
                    def fail(): raise OSError('terminal assignment')
                    with files.report_lock,pytest.raises(OSError): owned.commit(before_mutation=mutate,publish_success=fail)
                assert output.read_bytes()==b'old' and store.path.read_bytes()==report_before
            return True,np.full((8,8,3),len(handles)*70,np.uint8)
        def release(self): self.closed=True
    monkeypatch.setattr(web.cv2,'VideoCapture',Capture)
    assert request('get',store.url+'/frame_at?src=output').status_code==200
    assert len(handles)==2 and files.output_epoch==4 and all(h.closed for h in handles)


def test_frame_stable_error_and_postvalidation_commit(store,monkeypatch):
    class Capture:
        def __init__(self,path): pass
        def set(self,*args): pass
        def read(self): return False,None
        def release(self): pass
    monkeypatch.setattr(web.cv2,'VideoCapture',Capture)
    assert request('get',store.url+'/frame_at').status_code==404


def test_managed_source_alias_uses_source_owner(store,monkeypatch):
    source=store.job
    output=Path(source['dir'])/'output.mp4';output.write_bytes(b'old')
    target=web.new_job(str(output),{},'alias.mp4');target['phase']='review'
    source_files=web.FILES.initialize(source);target_files=web.FILES.initialize(target)
    handles=[]
    class Capture:
        def __init__(self,path):
            assert path==str(output);handles.append(self);self.closed=False
        def set(self,*args): pass
        def read(self):
            assert not source_files.report_lock.locked() and not target_files.report_lock.locked()
            if len(handles)==1:
                with source_files.report_lock: source_files.output_epoch += 1
            return True,np.ones((8,8,3),np.uint8)
        def release(self): self.closed=True
    monkeypatch.setattr(web.cv2,'VideoCapture',Capture)
    assert request('get','/api/jobs/'+target['id']+'/frame_at').status_code==200
    assert len(handles)==2 and all(h.closed for h in handles)
