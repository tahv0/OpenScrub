"""Detached plate discovery uses the exact source and existing file owners."""
import threading
from pathlib import Path

import pytest
import openscrub_web as web
from test_exact_samples import exact, sample, precondition
from test_job_lifecycle import store, request, start_call, finish


@pytest.fixture
def search_request(exact):
    return dict(seed=precondition(sample(exact, .2), None), query='KJF572',
                mode='fragment', request_id='a'*32)


def _result():
    return {'complete': True, 'truncated': False,
            'suggestions': [{'box':[10,10,50,30], 'match':'fragment', 'boundary':'unknown'}]}


def test_exact_search_is_ephemeral_and_report_unchanged(exact,search_request,monkeypatch):
    calls=[]
    def run(payload, directory, cancelled, timeout):
        calls.append((payload,directory,cancelled))
        return _result()
    monkeypatch.setattr(web, '_run_plate_search_child', run)
    before=exact.path.read_bytes()
    response=request('post', exact.url+'/plate_search', json=search_request)
    assert response.status_code == 200
    assert response.headers['Cache-Control'] == 'private, no-store'
    assert response.json == {'state':'complete','index':1,'truncated':False,
                             'suggestions':_result()['suggestions']}
    assert calls[0][0]['index'] == 1 and calls[0][0]['path'] == exact.job['video']
    assert calls[0][1] == exact.job['dir']
    assert exact.path.read_bytes() == before
    assert 'KJF572' not in repr(response.json)
    assert 'KJF572' not in '\n'.join(exact.job['log'].snapshot()['lines'])


@pytest.mark.parametrize('change', [
    {'query':'?'}, {'mode':'implicit'}, {'seed':{}}, {'request_id':'bad'}, {'query':''},
])
def test_invalid_input_rejected_before_child(exact,search_request,monkeypatch,change):
    search_request.update(change)
    monkeypatch.setattr(web, '_run_plate_search_child', lambda *a: pytest.fail('child started'))
    before=exact.path.read_bytes()
    response=request('post',exact.url+'/plate_search',json=search_request)
    assert response.status_code == 400
    assert exact.path.read_bytes() == before
    assert 'KJF572' not in response.get_data(as_text=True)


def test_source_or_report_change_rejects_inflight_result(exact,search_request,monkeypatch):
    entered, release=threading.Event(),threading.Event()
    def run(payload,directory,cancelled,timeout):
        entered.set(); assert release.wait(5); return _result()
    monkeypatch.setattr(web,'_run_plate_search_child',run)
    call=start_call('post',exact.url+'/plate_search',json=search_request)
    try:
        assert entered.wait(3)
        assert request('delete',exact.url).status_code == 409
        assert request('post','/api/vault/lock').status_code == 409
        assert request('post',exact.url+'/render').status_code == 409
        Path(exact.job['video']).write_bytes(b'replaced')
    finally:
        release.set(); response=finish(call)
    assert response.status_code == 409
    assert response.json['error'] == 'sample_conflict'
    assert 'suggestions' not in response.json


def test_explicit_cancel_is_not_a_negative_and_releases_ownership(exact,search_request,monkeypatch):
    entered,release=threading.Event(),threading.Event()
    def run(payload,directory,cancelled,timeout):
        entered.set(); assert release.wait(5)
        assert cancelled()
        return _result()
    monkeypatch.setattr(web,'_run_plate_search_child',run)
    call=start_call('post',exact.url+'/plate_search',json=search_request)
    try:
        assert entered.wait(3)
        wrong=request('post',exact.url+'/plate_search/cancel',json={'request_id':'b'*32})
        assert wrong.status_code == 200
        assert request('post',exact.url+'/plate_search/cancel',json={'request_id':'a'*32}).status_code == 200
    finally:
        release.set(); response=finish(call)
    assert response.status_code == 409 and response.json['state'] == 'cancelled'
    assert 'suggestions' not in response.json


def test_cancel_before_admission_is_not_lost(exact,search_request,monkeypatch):
    assert request('post',exact.url+'/plate_search/cancel',json={'request_id':'a'*32}).status_code == 200
    monkeypatch.setattr(web, '_run_plate_search_child', lambda *a: pytest.fail('cancelled child started'))
    response=request('post',exact.url+'/plate_search',json=search_request)
    assert response.status_code == 409 and response.json['state'] == 'cancelled'


def test_report_edit_during_search_rejects_stale_suggestions(exact,search_request,monkeypatch):
    entered, release=threading.Event(),threading.Event()
    def run(payload,directory,cancelled,timeout):
        entered.set(); assert release.wait(5); return _result()
    monkeypatch.setattr(web,'_run_plate_search_child',run)
    call=start_call('post',exact.url+'/plate_search',json=search_request)
    try:
        assert entered.wait(3)
        assert request('post',exact.url+'/detections',json={'enabled':{'0':False}}).status_code == 200
    finally:
        release.set(); response=finish(call)
    assert response.status_code == 409 and response.json['error'] == 'sample_conflict'
    assert 'suggestions' not in response.json


def test_job_cancel_signals_search(exact,search_request,monkeypatch):
    entered, release=threading.Event(),threading.Event()
    def run(payload,directory,cancelled,timeout):
        entered.set(); assert release.wait(5); assert cancelled(); return _result()
    monkeypatch.setattr(web,'_run_plate_search_child',run)
    call=start_call('post',exact.url+'/plate_search',json=search_request)
    try:
        assert entered.wait(3)
        assert request('post',exact.url+'/cancel').status_code == 200
    finally:
        release.set(); response=finish(call)
    assert response.status_code == 409 and response.json['state'] == 'cancelled'


def test_invalid_child_geometry_is_not_exposed(exact,search_request,monkeypatch):
    value=_result(); value['suggestions'][0]['box']=[0,0,65,48]
    monkeypatch.setattr(web,'_run_plate_search_child',lambda *args:value)
    response=request('post',exact.url+'/plate_search',json=search_request)
    assert response.status_code == 503 and response.json['state'] == 'error'
    assert 'suggestions' not in response.json


def test_delayed_job_cancel_does_not_cancel_a_newer_search(exact,search_request,monkeypatch):
    first_enter, second_enter, release_second = threading.Event(),threading.Event(),threading.Event()
    cancel_blocked, release_cancel = threading.Event(),threading.Event()
    def run(payload,directory,cancelled,timeout):
        if payload['query'] == 'KJF572':
            first_enter.set()
            assert _wait_until(cancelled)
        else:
            second_enter.set(); assert release_second.wait(5)
        return _result()
    monkeypatch.setattr(web,'_run_plate_search_child',run)
    first=start_call('post',exact.url+'/plate_search',json=search_request)
    second=cancel_call=None
    try:
        assert first_enter.wait(3)
        marker=web.FILES.initialize(exact.job).plate_search
        event=marker['cancel']; set_event=event.set
        def hold_cancel():
            set_event(); cancel_blocked.set(); assert release_cancel.wait(5)
        monkeypatch.setattr(event,'set',hold_cancel)
        cancel_call=start_call('post',exact.url+'/cancel')
        assert cancel_blocked.wait(3)
        first_response=finish(first)
        assert first_response.json['state']=='cancelled'
        next_request=dict(search_request,query='ABC123',request_id='b'*32)
        second=start_call('post',exact.url+'/plate_search',json=next_request)
        assert second_enter.wait(3)
        release_cancel.set()
        assert finish(cancel_call).status_code == 200
    finally:
        release_cancel.set(); release_second.set()
        if cancel_call is not None and cancel_call[0].is_alive(): finish(cancel_call)
        if first[0].is_alive(): finish(first)
        second_response=finish(second) if second is not None else None
    assert second_response.status_code == 200
    assert second_response.json['state'] == 'complete'


def _wait_until(predicate):
    import time
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        if predicate(): return True
        time.sleep(.01)
    return False


def test_job_cancel_only_signals_the_operation_it_captured(exact,search_request,monkeypatch):
    entered, release=threading.Event(),threading.Event()
    def run(payload,directory,cancelled,timeout):
        entered.set(); assert release.wait(5); return _result()
    monkeypatch.setattr(web,'_run_plate_search_child',run)
    call=start_call('post',exact.url+'/plate_search',json=search_request)
    try:
        assert entered.wait(3)
        files=web.FILES.initialize(exact.job); marker=files.plate_search
        with files.report_lock:
            files.operation=threading.Event()  # a newer, distinct operation
        assert request('post',exact.url+'/cancel').status_code == 200
        assert not marker['cancel'].is_set()
    finally:
        release.set(); finish(call)


def test_request_body_is_bounded_before_json_parsing(exact,monkeypatch):
    from flask import Request
    original=Request.get_json
    def forbidden(*args,**kwargs):
        pytest.fail('unbounded JSON parser was used')
    monkeypatch.setattr(Request,'get_json',forbidden)
    response=request('post',exact.url+'/plate_search',
                     data=b' '*4097, content_type='application/json')
    assert response.status_code == 400
