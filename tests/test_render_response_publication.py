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


@pytest.mark.parametrize('managed_alias', [False, True])
@pytest.mark.parametrize('schedule', ['recovery', 'stable', 'stale-retry'])
def test_source_response_ownership_through_revalidation(store, monkeypatch,
                                                       managed_alias, schedule):
    """Real descriptors stay locally owned until validation transfers them.

    Retain every response, descriptor and recovery traceback. Production close
    assertions precede unconditional harness containment, so GC cannot pass RED.
    """
    from openscrub_internal import lifetimes
    from werkzeug.exceptions import HTTPException

    source_job = store.job
    payload = b'synthetic source generation' * 20000
    source_path = Path(source_job['video'])
    if managed_alias:
        source_path = Path(source_job['dir']) / 'output.mp4'
    source_path.write_bytes(payload)
    target_job = (web.new_job(str(source_path), {}, 'managed-alias.mp4')
                  if managed_alias else source_job)
    target_job['phase'] = 'review'
    source_state = web.FILES.initialize(source_job)
    target_state = web.FILES.initialize(target_job)
    expected_leases = 2 if managed_alias else 1
    streams, opened, real_closes = [], [], []
    descriptor_closes, response_closes, releases, retained_errors = [], [], [], []
    actual_send = web.send_file
    actual_open = web._send_open_file
    actual_validate = web._frame_source_current
    actual_release = lifetimes._Lease.release_locked

    def outside_shared_locks():
        assert not source_state.report_lock.locked()
        assert not target_state.report_lock.locked()
        assert not web.VAULT_LOCK.locked()
        assert not web.JOBS_LOCK.locked()

    def send(stream, **options):
        # Inspect the actual opened file passed to Flask, not a replacement
        # fake iterator or an inferred path-based response generation.
        assert os.fstat(stream.fileno()).st_size == len(payload)
        streams.append(stream)
        close = stream.close
        def close_descriptor():
            outside_shared_locks()
            descriptor_closes.append(stream)
            return close()
        monkeypatch.setattr(stream, 'close', close_descriptor)
        return actual_send(stream, **options)

    def open_response(path, **options):
        assert str(path) == str(source_path)
        if opened:
            # A stale first attempt must close before opening a new attempt,
            # while both attempts share the same admitted request lifetime.
            assert schedule == 'stale-retry'
            assert streams[0].closed
            assert response_closes == [opened[0]]
            assert web.FILES.count == expected_leases and not releases
        response = actual_open(path, **options)
        close = response.close
        real_closes.append(close)
        def close_response():
            outside_shared_locks()
            response_closes.append(response)
            return close()
        monkeypatch.setattr(response, 'close', close_response)
        opened.append(response)
        return response

    def validate(snapshot):
        outside_shared_locks()
        assert snapshot['source_job'] is source_job
        assert snapshot['source_state'] is source_state
        assert not streams[-1].closed
        if len(opened) == 1:
            with source_state.report_lock:
                if schedule == 'recovery':
                    source_state.recovery_required = True
                elif schedule == 'stale-retry':
                    source_state.output_epoch += 1
        try:
            return actual_validate(snapshot)
        except HTTPException as error:
            retained_errors.append(error)
            raise

    def release(lease):
        before = lease.released
        try:
            return actual_release(lease)
        finally:
            if not before and lease.released:
                releases.append(lease)

    monkeypatch.setattr(web, 'send_file', send)
    monkeypatch.setattr(web, '_send_open_file', open_response)
    monkeypatch.setattr(web, '_frame_source_current', validate)
    monkeypatch.setattr(lifetimes._Lease, 'release_locked', release)
    route_response = None
    with web.app.test_client() as client:
        try:
            route_response = client.get('/api/jobs/' + target_job['id'] + '/video',
                                        buffered=False)
            if schedule == 'recovery':
                assert route_response.status_code == 409
                assert b'render delivery requires recovery' in route_response.data
                assert len(retained_errors) == 1
                assert retained_errors[0].code == 409
                assert retained_errors[0].__traceback__ is not None
                assert len(opened) == 1
                assert all(stream.closed for stream in streams), (
                    'untransferred source descriptor remains open after recovery409')
                assert response_closes == opened
            else:
                assert route_response.status_code == 200
                assert not retained_errors
                assert len(opened) == (2 if schedule == 'stale-retry' else 1)
                assert not streams[-1].closed, 'validated stream closed before transfer'
                assert response_closes == opened[:-1]
                assert web.FILES.count == expected_leases and not releases
                chunk = next(iter(route_response.response))
                assert payload.startswith(chunk)
                assert not streams[-1].closed
                route_response.close()
                assert all(stream.closed for stream in streams)
            assert descriptor_closes == streams
            assert web.FILES.count == source_state.count == target_state.count == 0
            assert len(releases) == expected_leases
            assert len({id(lease) for lease in releases}) == expected_leases
            route_response.close()  # ordinary repeated response close is harmless
            assert descriptor_closes == streams
            assert len(releases) == expected_leases
        finally:
            # Containment only after production assertions, including on RED.
            if route_response is not None:
                route_response.close()
            for stream, close in zip(streams, real_closes):
                if not stream.closed:
                    close()
