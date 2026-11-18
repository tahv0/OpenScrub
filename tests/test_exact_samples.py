"""Production exact-sample/save owners with bounded synthetic inputs."""
import copy
import json
import math
import os
import threading
from pathlib import Path

import cv2
import numpy as np
import pytest
import openscrub_web as web
from test_job_lifecycle import store, request, start_call, finish


@pytest.fixture
def exact(store):
    writer = cv2.VideoWriter(store.job['video'], cv2.VideoWriter_fourcc(*'MJPG'), 5, (64, 48))
    assert writer.isOpened()
    try:
        for i in range(10):
            writer.write(np.full((48, 64, 3), 20*i, dtype=np.uint8))
    finally:
        writer.release()
    store.doc['render_state'] = {'fps': 5, 'cum': [[i, -i] for i in range(10)]}
    store.doc['detections'][0].update(t_end=2, last_seen=.5)
    store.doc['detections'].append(dict(store.doc['detections'][0], enabled=False, text='disabled'))
    store.path.write_text(json.dumps(store.doc))
    return store


def sample(exact, t=.2):
    response = request('get', exact.url+'/edit_sample?t='+str(t))
    assert response.status_code == 200, response.get_data(as_text=True)
    assert response.headers['Cache-Control'] == 'private, no-store'
    return response.json


def precondition(value, row=0):
    result = {key:value['sample'][key] for key in (
        'source_ref','timeline_eq','policy','index','width','height','offset')}
    result['version'] = 1
    if row is not None:
        box = next(b for b in value['boxes'] if b['i'] == row)
        result.update(row_context_eq=box['row_context_eq'], base=box['base'])
    return result


def post(exact, **edits):
    return request('post', exact.url+'/detections', json=edits)


def raw(exact):
    return json.loads(exact.path.read_text())


def test_exact_image_rows_offsets_and_final_interval(exact):
    import base64
    value = sample(exact, 1.9)
    assert value['sample']['index'] == 9
    assert value['sample']['canonical_s'] == 1.8
    assert value['sample']['requested_s'] == 1.9
    assert value['sample']['observed_s'] == pytest.approx(1.8)
    assert value['sample']['offset'] == [9, -9]
    assert [r['i'] for r in value['boxes']] == [0, 1]
    assert value['boxes'][1]['enabled'] is False
    assert value['boxes'][0]['box'] == [10,-7,17,0]
    pixels = cv2.imdecode(np.frombuffer(base64.b64decode(value['image']['base64']), np.uint8), 1)
    assert pixels.shape == (48, 64, 3) and abs(float(pixels.mean())-180) < 3
    assert sample(exact, 2)['sample']['index'] == 9


@pytest.mark.parametrize('time', ['NaN','Infinity','-Infinity','true','false','null','[]','-1','2.001','x',''])
def test_bad_time_is_400(exact, time):
    response = request('get', exact.url+'/edit_sample?t='+time)
    assert response.status_code == 400
    assert response.json['error'] == 'invalid_sample_request'


def test_row_context_canonical_opaque_values_and_exclusions():
    from openscrub_internal.exact_samples import row_context_eq
    row = {'text':'\ud800', 'opaque':{'b':[float('nan'),float('inf'),-float('inf')],'a':1},
           'enabled':True,'cbox':[1,2,3,4],'t_start':0,'t_end':1,'last_seen':0}
    digest = row_context_eq(row)
    parsed = json.loads(json.dumps(row))
    parsed['opaque'] = dict(reversed(list(parsed['opaque'].items())))
    parsed.update(enabled=False, cbox=[8,9,10,11], t_start=2, t_end=3, last_seen=2)
    assert row_context_eq(parsed) == digest
    for old, new in [(1,1.0),(0.0,-0.0),(float('nan'),'NaN'),(float('inf'),'Infinity')]:
        assert row_context_eq({'x':old}) != row_context_eq({'x':new})


@pytest.mark.parametrize('kind', ['box','span','both'])
def test_strict_cas_baseline_and_already_equal_replay(exact, kind):
    value = sample(exact)
    pc = precondition(value)
    edits = {'geometry_preconditions': {'0':pc}, 'enabled':{'1':True},
             'audio':[{'t0':0,'t1':.4}]}
    if kind in ('box','both'): edits['box_overrides'] = {'0':[3,4,10,11]}
    if kind in ('span','both'): edits['time_overrides'] = {'0':[.7,1.7]}
    for _ in range(2):
        response = post(exact, **edits)
        assert response.status_code == 200, response.get_data(as_text=True)
        committed = response.json['geometry_rows']['0']
        assert committed['base']['cbox'] == ([3,4,10,11] if kind != 'span' else pc['base']['cbox'])
        assert committed['base']['span'] == ([.7,1.7,.7] if kind != 'box' else pc['base']['span'])
    assert raw(exact)['detections'][1]['enabled'] is True


@pytest.mark.parametrize('kind', ['box','span','both'])
def test_strict_cas_non_target_or_mixed_conflict_is_atomic(exact, kind):
    pc = precondition(sample(exact))
    edits = {'geometry_preconditions': {'0':pc}, 'enabled':{'1':True}}
    if kind in ('box','both'): edits['box_overrides'] = {'0':[3,4,10,11]}
    if kind in ('span','both'): edits['time_overrides'] = {'0':[.7,1.7]}
    doc = raw(exact)
    if kind == 'box': doc['detections'][0]['t_end'] = 1.8
    else: doc['detections'][0]['cbox'] = [3,4,10,11]
    exact.path.write_text(json.dumps(doc))
    before = exact.path.read_bytes()
    assert post(exact, **edits).status_code == 409
    assert exact.path.read_bytes() == before


def test_choices_audio_unrelated_metadata_do_not_invalidate_geometry(exact):
    pc = precondition(sample(exact))
    doc = raw(exact); doc['detections'][1]['text']='other'; doc['future']={'x':float('nan')}
    doc['detections'][0]['future'] = {'nested':[float('nan'),'Infinity','\ud800']}
    exact.path.write_text(json.dumps(doc))
    pc = precondition(sample(exact))
    assert post(exact, enabled={'0':False}, audio=[{'t0':0,'t1':.3}]).status_code == 200
    assert post(exact, geometry_preconditions={'0':pc}, box_overrides={'0':[2,3,9,10]}).status_code == 200
    assert raw(exact)['detections'][0]['enabled'] is False


def test_manual_replay_precedes_current_source_and_timeline(exact):
    pc = precondition(sample(exact), None)
    manual = {'manual_id':'strict:lost','t_start':0,'t_end':1,'t_ref':.2,
              'screen_box':[3,4,10,11], 'sample_precondition':pc}
    assert post(exact, manual=[manual]).status_code == 200
    assert post(exact, box_overrides={'2':[8,9,12,13]}, time_overrides={'2':[.3,1.4]}).status_code == 200
    doc=raw(exact); doc['render_state']['cum'] = [[100,100]]
    exact.path.write_text(json.dumps(doc)); Path(exact.job['video']).unlink()
    assert post(exact, manual=[manual], enabled={'0':False}).status_code == 200
    assert raw(exact)['detections'][2]['cbox'] == [8,9,12,13]


def test_report_commit_overlapping_encode_conflicts_and_releases(exact, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    real = web.cv2.imencode
    def encode(*a, **kw):
        entered.set(); assert release.wait(8)
        return real(*a, **kw)
    monkeypatch.setattr(web.cv2, 'imencode', encode)
    call = start_call('get', exact.url+'/edit_sample?t=0.2')
    try:
        assert entered.wait(5)
        assert post(exact, enabled={'0':False}).status_code == 200
    finally:
        release.set(); response = finish(call)
    assert response.status_code == 409
    assert web.FILES.count == 0


def test_observed_source_replacement_retires_pair_until_scan_adoption(exact):
    first = sample(exact)['sample']['source_ref']
    source = Path(exact.job['video'])
    replacement = source.with_name('replacement.avi')
    replacement.write_bytes(source.read_bytes())
    os.replace(replacement, source)
    assert request('get',exact.url+'/edit_sample?t=0.2').status_code == 422
    assert web.FILES.initialize(exact.job).source_retired
    assert request('get',exact.url+'/edit_sample?t=0.2').status_code == 422
    assert post(exact,enabled={'0':False}).status_code == 200
    assert web.FILES.initialize(exact.job).current_source is None


def test_concurrent_discovery_converges_and_probes_once_reused(exact, monkeypatch):
    barrier = threading.Barrier(2)
    real = web._probe_exact_source
    probes=[]
    def probe(path):
        probes.append(path); barrier.wait(5)
        return real(path)
    monkeypatch.setattr(web,'_probe_exact_source',probe)
    a=start_call('get',exact.url+'/edit_sample?t=0.2')
    b=start_call('get',exact.url+'/edit_sample?t=0.4')
    x,y=finish(a),finish(b)
    assert x.status_code == y.status_code == 200
    assert x.json['sample']['source_ref'] == y.json['sample']['source_ref']
    assert len(probes) == 2
    monkeypatch.setattr(web,'_probe_exact_source',lambda p: pytest.fail('reused descriptor probed'))
    assert sample(exact)['sample']['source_ref'] == x.json['sample']['source_ref']


@pytest.mark.parametrize('change', ['context','reorder','timeline'])
def test_strict_context_reorder_and_timeline_conflicts(exact, change):
    pc=precondition(sample(exact)); doc=raw(exact)
    if change=='context': doc['detections'][0]['future']={'changed':True}
    elif change=='reorder': doc['detections'].reverse()
    else: doc['render_state']['cum'][9][1] += 1
    exact.path.write_text(json.dumps(doc)); before=exact.path.read_bytes()
    assert post(exact,geometry_preconditions={'0':pc},box_overrides={'0':[2,3,10,11]},enabled={'1':True}).status_code == 409
    assert exact.path.read_bytes() == before


def test_identical_duplicates_are_semantically_indistinguishable_and_missing_last_seen_preserved(exact):
    doc=raw(exact); del doc['detections'][0]['last_seen']
    doc['detections'][1]=dict(doc['detections'][0],enabled=False)
    exact.path.write_text(json.dumps(doc)); pc=precondition(sample(exact))
    doc['detections'].reverse(); exact.path.write_text(json.dumps(doc))
    assert post(exact,geometry_preconditions={'0':pc},box_overrides={'0':[2,3,10,11]}).status_code == 200
    assert 'last_seen' not in raw(exact)['detections'][0]
    assert raw(exact)['detections'][0]['enabled'] is False


@pytest.mark.parametrize('field,value', [('index',True),('version',True),('width',1.5),('offset',[False,0]),('base',{'cbox':[1,2,3,float('nan')],'span':[0,1,0]})])
def test_strict_precondition_shape_rejects_consumed_boolean_nonfinite(exact,field,value):
    pc=precondition(sample(exact));pc[field]=value;before=exact.path.read_bytes()
    assert post(exact,geometry_preconditions={'0':pc},box_overrides={'0':[2,3,10,11]}).status_code==400
    assert exact.path.read_bytes()==before


def test_encoder_failure_cleanup_and_retained_exception(exact,monkeypatch):
    errors=[];caps=[];real=web.cv2.VideoCapture
    class Capture:
        def __init__(self,*a): self.cap=real(*a);self.released=False;caps.append(self)
        def __getattr__(self,k): return getattr(self.cap,k)
        def release(self): self.released=True;self.cap.release()
    def encode(*a):
        try: raise RuntimeError('retained encoding failure')
        except RuntimeError as error: errors.append(error);raise
    monkeypatch.setattr(web.cv2,'VideoCapture',Capture)
    monkeypatch.setattr(web.cv2,'imencode',encode)
    response=request('get',exact.url+'/edit_sample?t=0.2')
    assert response.status_code==500 and response.json['error']=='sample_encode_failed'
    assert errors and all(c.released for c in caps) and web.FILES.count==0


@pytest.mark.parametrize('defect', ['eof','adjacent','zero_time','dimensions','backend','count'])
def test_decoded_evidence_unavailable_without_walkback(exact,monkeypatch,defect):
    real=web.cv2.VideoCapture;caps=[]
    class Capture:
        def __init__(self,*a): self.cap=real(*a);self.released=False;self.reads=0;caps.append(self)
        def __getattr__(self,k): return getattr(self.cap,k)
        def getBackendName(self): return 'OTHER' if defect=='backend' else self.cap.getBackendName()
        def get(self,p):
            if p==cv2.CAP_PROP_FRAME_COUNT and defect=='count':return 9
            if p==cv2.CAP_PROP_POS_MSEC:
                if defect=='zero_time':return 0
                if defect=='adjacent':return self.cap.get(p)+200
            return self.cap.get(p)
        def read(self):
            self.reads+=1
            ok,pixels=self.cap.read()
            if defect=='eof':return False,None
            if defect=='dimensions':pixels=pixels[:20]
            return ok,pixels
        def release(self):self.released=True;self.cap.release()
    monkeypatch.setattr(web.cv2,'VideoCapture',Capture)
    response=request('get',exact.url+'/edit_sample?t=0.4')
    assert response.status_code==422
    assert all(c.released and c.reads<=1 for c in caps)


def test_precision_policy_coarse_ticks_and_exact_rational_grid():
    from openscrub_internal import exact_samples as e
    facts=dict(rate=24.,tick_s=.001,grid_aligned=False,count=48)
    assert .001 <= e.precision_bound(facts,24.,48) < .001001
    facts.update(rate=5.,tick_s=.2,grid_aligned=True,count=10)
    assert 0 < e.precision_bound(facts,5.,10) < 1e-10
    facts.update(tick_s=.1,grid_aligned=False)
    with pytest.raises(e.ExactError):e.precision_bound(facts,5.,10)


@pytest.mark.parametrize('stage',['decode','encode'])
def test_source_replaced_during_sample_cannot_publish(exact,monkeypatch,stage):
    entered,release=threading.Event(),threading.Event()
    module,name=(web.exact,'read_indexed_capture') if stage=='decode' else (web.cv2,'imencode')
    real=getattr(module,name)
    def hold(*a,**kw):
        result=real(*a,**kw);entered.set();assert release.wait(8);return result
    monkeypatch.setattr(module,name,hold)
    call=start_call('get',exact.url+'/edit_sample?t=0.2')
    try:
        assert entered.wait(5)
        source=Path(exact.job['video']);replacement=source.with_name('new.avi')
        replacement.write_bytes(source.read_bytes());os.replace(replacement,source)
        assert request('post','/api/vault/lock').status_code==409
    finally:release.set();response=finish(call)
    assert response.status_code==409 and web.FILES.count==0
    assert request('get',exact.url+'/edit_sample?t=0.2').status_code==422


def test_save_reloads_after_source_preparation_and_rejects_atomic_conflict(exact,monkeypatch):
    pc=precondition(sample(exact));entered,release=threading.Event(),threading.Event();real=web._prepare_observed_source
    def hold(*a):
        result=real(*a);entered.set();assert release.wait(8);return result
    monkeypatch.setattr(web,'_prepare_observed_source',hold)
    call=start_call('post',exact.url+'/detections',json=dict(geometry_preconditions={'0':pc},box_overrides={'0':[3,4,9,10]},enabled={'1':True},audio=[{'t0':0,'t1':.5}]))
    try:
        assert entered.wait(5)
        doc=raw(exact);doc['detections'][0]['text']='replacement';exact.path.write_text(json.dumps(doc));before=exact.path.read_bytes()
        assert post(exact,enabled={'0':False}).status_code==200
        before=exact.path.read_bytes()
    finally:release.set();response=finish(call)
    assert response.status_code==409 and exact.path.read_bytes()==before


def test_manual_replay_does_not_exempt_other_stale_strict_geometry(exact):
    value=sample(exact);pc=precondition(value);manual=dict(manual_id='lost:combined',t_start=0,t_end=1,t_ref=.2,screen_box=[3,4,10,11],sample_precondition=precondition(value,None))
    assert post(exact,manual=[manual]).status_code==200
    doc=raw(exact);doc['detections'][0]['aoff']=[3,4];exact.path.write_text(json.dumps(doc));before=exact.path.read_bytes()
    assert post(exact,manual=[manual],geometry_preconditions={'0':pc},box_overrides={'0':[3,4,9,10]},enabled={'1':True}).status_code==409
    assert exact.path.read_bytes()==before


@pytest.mark.parametrize('defect',['fps_bool','fps_nan','empty','bad_offset','bool_offset','bad_box','bad_span'])
def test_consumed_invalid_report_values_unavailable(exact,defect):
    doc=raw(exact)
    if defect=='fps_bool':doc['render_state']['fps']=True
    elif defect=='fps_nan':doc['render_state']['fps']=float('nan')
    elif defect=='empty':doc['render_state']['cum']=[]
    elif defect=='bad_offset':doc['render_state']['cum'][0]=[0]
    elif defect=='bool_offset':doc['render_state']['cum'][0]=[False,0]
    elif defect=='bad_box':doc['detections'][0]['cbox'][0]=float('inf')
    else:doc['detections'][0]['last_seen']=False
    exact.path.write_text(json.dumps(doc))
    response=request('get',exact.url+'/edit_sample?t=0.2')
    assert response.status_code==422 and 'image' not in response.json


@pytest.mark.parametrize('defect',['missing','failed','ambiguous','origin','rotation','rate','count','bypass'])
def test_unsupported_successful_or_failed_metadata_is_unavailable(exact,monkeypatch,defect):
    real=web._probe_exact_source
    if defect in ('missing','failed'):
        def probe(path):raise web.exact.ExactError('probe '+defect)
    else:
        def probe(path):
            facts=real(path)
            if defect=='count':facts['count']=9
            elif defect=='rate':facts['rate']=6
            elif defect not in ('bypass',):raise web.exact.ExactError('unsupported '+defect)
            return facts
    monkeypatch.setattr(web,'_probe_exact_source',probe)
    if defect=='bypass':
        doc=raw(exact);doc['provenance']['settings']['no_vfr_fix']=True;exact.path.write_text(json.dumps(doc))
    response=request('get',exact.url+'/edit_sample?t=0.2')
    assert response.status_code==422
    assert web.FILES.initialize(exact.job).source_status=='coherent'
    assert post(exact,enabled={'0':False}).status_code==200


def test_metadata_validation_actual_small_probe_shapes():
    from openscrub_internal import exact_samples as e
    stream=dict(index=0,width=64,height=48,r_frame_rate='24/1',avg_frame_rate='24/1',time_base='1/1000',start_pts=0,start_time='0.000',nb_frames='48')
    assert e.metadata_facts({'streams':[stream]})['tick_s']==.001
    for change in [dict(start_pts=1),dict(start_time='.01'),dict(avg_frame_rate='23/1'),dict(tags={'rotate':'90'}),dict(side_data_list=[{'rotation':0}]),dict(width=True)]:
        with pytest.raises(e.ExactError):e.metadata_facts({'streams':[{**stream,**change}]})
    with pytest.raises(e.ExactError):e.metadata_facts({'streams':[stream,stream]})
    with pytest.raises(e.ExactError):e.metadata_facts({'streams':[]})


@pytest.mark.parametrize('change',['missing','replaced'])
def test_strict_source_freshness_failure_is_atomic_409(exact,change):
    pc=precondition(sample(exact));source=Path(exact.job['video'])
    if change=='missing':source.unlink()
    else:
        replacement=source.with_name('changed.avi');replacement.write_bytes(source.read_bytes());replacement.replace(source)
    before=exact.path.read_bytes()
    response=post(exact,geometry_preconditions={'0':pc},box_overrides={'0':[2,3,10,11]},enabled={'1':True})
    assert response.status_code==409
    assert response.json['error']=='geometry_conflict'
    assert exact.path.read_bytes()==before


def test_legacy_publication_file_error_is_not_strict_source_conflict(store,monkeypatch):
    before=store.path.read_bytes()
    def fail(*a):raise FileNotFoundError('controlled legacy publication failure')
    monkeypatch.setattr(web,'atomic_report',fail)
    assert request('post',store.url+'/detections',json={'enabled':{'0':False}}).status_code==500
    assert store.path.read_bytes()==before
