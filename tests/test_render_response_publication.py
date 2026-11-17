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


@pytest.mark.parametrize("failure", ["first", "terminal"])
def test_frame_rejects_failed_attempt_and_successful_rollback_aba(store, monkeypatch, failure):
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
                    real_replace=os.replace
                    def replace(src,dst):
                        if failure=='first' and str(src)==owned.video_stage: raise OSError('first attempt no change')
                        return real_replace(src,dst)
                    with monkeypatch.context() as patch:
                        patch.setattr(os,'replace',replace)
                        with files.report_lock,pytest.raises(OSError): owned.commit(before_mutation=mutate,publish_success=fail)
                assert output.read_bytes()==b'old' and store.path.read_bytes()==report_before
            return True,np.full((8,8,3),len(handles)*70,np.uint8)
        def release(self): self.closed=True
    monkeypatch.setattr(web.cv2,'VideoCapture',Capture)
    assert request('get',store.url+'/frame_at?src=output').status_code==200
    assert len(handles)==2 and files.output_epoch==(2 if failure=="first" else 4) and all(h.closed for h in handles)


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


from test_report_transactions import socket_api


@pytest.mark.parametrize('endpoint',['download','report','video','server'])
def test_download_report_range_metadata_matches_open_generation(store,socket_api,monkeypatch,endpoint):
    import email.utils
    from urllib.parse import quote
    output=Path(store.job['dir'])/'output.mp4';payload=bytes(range(128))*4
    output.write_bytes(payload);Path(store.job['video']).write_bytes(payload)
    store.job.update(output=str(output),phase='done')
    if endpoint=='report': payload=store.path.read_bytes()
    url=('/api/server_video?path='+quote(str(output)) if endpoint=='server' else store.url+'/'+endpoint)
    # The response helper must pin its descriptor even if path offload was set.
    monkeypatch.setitem(web.app.config,'USE_X_SENDFILE',True)
    status,headers,body=socket_api('GET',url)
    assert status==200 and body==payload and 'X-Sendfile' not in headers
    assert int(headers['Content-Length'])==len(payload)
    etag=headers['ETag'];modified=headers['Last-Modified']
    assert email.utils.parsedate_to_datetime(modified)
    for value,expected in [('bytes=3-9',payload[3:10]),('bytes=-5',payload[-5:])]:
        status,headers,body=socket_api('GET',url,headers={'Range':value})
        assert status==206 and body==expected and int(headers['Content-Length'])==len(expected)
        assert headers['ETag']==etag
    status,headers,body=socket_api('GET',url,headers={'Range':'bytes=999999-1000000'})
    assert status==416 and headers['Content-Range']=='bytes */%d'%len(payload)
    for condition in [{'If-None-Match':etag},{'If-Modified-Since':modified}]:
        status,headers,body=socket_api('GET',url,headers=condition)
        assert status==304 and body==b''
    status,headers,body=socket_api('GET',url,headers={'Range':'bytes=3-9','If-Range':etag})
    assert status==206 and body==payload[3:10]
    status,headers,body=socket_api('GET',url,headers={'Range':'bytes=3-9','If-Range':modified})
    assert status==206 and body==payload[3:10]
    status,headers,body=socket_api('GET',url,headers={'Range':'bytes=3-9','If-Range':'"older-generation"'})
    assert status==200 and body==payload
    status,headers,body=socket_api('HEAD',url)
    assert status==200 and body==b'' and int(headers['Content-Length'])==len(payload)
    assert web.FILES.count==0


@pytest.mark.parametrize('rollback',[False,True])
def test_open_old_stream_survives_new_commit_or_rollback(store,monkeypatch,rollback):
    from openscrub_internal.render_delivery import _RenderDelivery
    output=Path(store.job['dir'])/'output.mp4';payload=b'old generation'*20000;output.write_bytes(payload)
    store.job.update(output=str(output),phase='done')
    files=web.FILES.initialize(store.job)
    with web.app.test_client() as client:
        response=client.get(store.url+'/download',buffered=False)
        try:
            assert web.FILES.count==1
            with _RenderDelivery(str(output),str(store.path)) as owned:
                Path(owned.video_stage).write_bytes(b'new generation')
                owned.prepare_report({'new':True});owned.prepare_rollback()
                def mutate(): files.output_epoch+=1
                def terminal():
                    if rollback: raise OSError('terminal failure')
                with files.report_lock:
                    if rollback:
                        with pytest.raises(OSError): owned.commit(before_mutation=mutate,publish_success=terminal)
                    else: owned.commit(before_mutation=mutate,publish_success=terminal)
            assert not files.report_lock.locked()
            assert response.get_data()==payload
        finally: response.close()
    assert web.FILES.count==0


def test_managed_alias_stream_keeps_source_lease_until_close(store):
    output=Path(store.job['dir'])/'output.mp4';output.write_bytes(b'source generation'*20000)
    target=web.new_job(str(output),{},'alias.mp4');target['phase']='review'
    source_files=web.FILES.initialize(store.job)
    with web.app.test_client() as client:
        response=client.get('/api/jobs/'+target['id']+'/video',buffered=False)
        try:
            assert source_files.count==1 and web.FILES.count==2
            assert not source_files.report_lock.locked()
            assert request('delete',store.url).status_code==409
        finally: response.close()
    assert source_files.count==0 and web.FILES.count==0


def test_detached_frame_can_return_after_successful_validation_then_commit(store,monkeypatch):
    handles=[];files=web.FILES.initialize(store.job)
    class Capture:
        def __init__(self,path): self.closed=False;handles.append(self)
        def set(self,*args): pass
        def read(self): return True,np.full((8,8,3),170,np.uint8)
        def release(self): self.closed=True
    monkeypatch.setattr(web.cv2,'VideoCapture',Capture)
    real=web._frame_source_current
    def validate(snapshot):
        current=real(snapshot)
        assert handles[-1].closed
        with files.report_lock: files.output_epoch+=1
        return current
    monkeypatch.setattr(web,'_frame_source_current',validate)
    response=request('get',store.url+'/frame_at')
    assert response.status_code==200 and len(handles)==1
    assert web.cv2.imdecode(np.frombuffer(response.data,np.uint8),1).mean()>150
