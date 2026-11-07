"""Transactional review -> train -> full scan -> learned refinement orchestration."""
import importlib.util
import json
from pathlib import Path
from copy import deepcopy
import numpy as np
import pytest
from test_plate_quad_editor import plate_job
import openscrub_web as web
import openscrub


def session():
    assert importlib.util.find_spec('learning_session'), 'Learning session is missing'
    import learning_session
    return learning_session


def test_existing_corner_annotations_are_collected_as_source_bound_training_data(plate_job):
    ls=session();client,jid,report,folder=plate_job
    meta=client.get('/api/jobs/%s/plate_quad/0'%jid).get_json()
    points=[[54,77],[126,74],[129,91],[52,94]]
    response=client.post('/api/jobs/%s/plate_quad/0'%jid,json={
        'points':points,'preview_token':meta['preview_token'],'autosave':True,'edit_id':'seed'})
    assert response.status_code==200
    doc=json.loads(report.read_text());doc['provenance']['input_sha256']=openscrub.sha256_file(web.JOBS[jid]['video'])
    report.write_text(json.dumps(doc))
    data=ls.collect_feedback(web.JOBS[jid],doc,lambda i:web._read_exact_frame(web.JOBS[jid]['video'],i))
    assert len(data['samples'])==1
    sample=next(iter(data['samples'].values()))
    assert sample['quality']=='human_quad' and sample['frame']==2
    assert Path(folder/'learning'/sample['image']).is_file()
    assert data['constraints']['source_sha256']==doc['provenance']['input_sha256']


def test_source_changes_refuse_learning_without_mutating_report(plate_job):
    ls=session();client,jid,path,folder=plate_job
    doc=json.loads(path.read_text());doc['provenance']['input_sha256']='0'*64
    before=path.read_bytes()
    with pytest.raises(ValueError,match='source'):
        ls.verify_source(web.JOBS[jid],doc)
    assert path.read_bytes()==before


def test_no_new_feedback_is_detected_before_retraining():
    ls=session()
    records={'a':{'image_sha256':'1','label':'positive','points':[[0,0]],'group':'track-a'}}
    a=ls.feedback_fingerprint(records)
    assert a==ls.feedback_fingerprint(deepcopy(records))
    records['a']['points']=[[.1,0]]
    assert a!=ls.feedback_fingerprint(records)


def test_new_explicit_negative_replaces_old_positive_sample(plate_job):
    ls=session();client,jid,path,folder=plate_job
    endpoint='/api/jobs/%s/plate_quad/0'%jid
    meta=client.get(endpoint).get_json()
    assert client.post(endpoint,json={'points':[[54,77],[126,74],[129,91],[52,94]],
        'preview_token':meta['preview_token'],'autosave':True,'edit_id':'seed'}).status_code==200
    job=web.JOBS[jid];doc=json.loads(path.read_text())
    doc['provenance']['input_sha256']=openscrub.sha256_file(job['video'])
    data=ls.collect_feedback(job,doc,lambda i:web._read_exact_frame(job['video'],i))
    assert any(s['label']=='positive' for s in data['samples'].values())
    doc['detections'][0].update(verified_label='not_plate',enabled=False)
    data=ls.collect_feedback(job,doc,lambda i:web._read_exact_frame(job['video'],i))
    assert all(s['label']=='negative' for s in data['samples'].values())


def test_training_action_rejects_missing_setup_without_starting_a_scan(plate_job,monkeypatch):
    client,jid,path,_=plate_job
    monkeypatch.delenv('OPENSCRUB_TRAIN_WEIGHTS',raising=False)
    before=path.read_bytes()
    response=client.post('/api/jobs/%s/learning'%jid,json={'license_accepted':True})
    assert response.status_code==503
    assert 'checkpoint' in response.get_json()['error'].lower()
    assert web.JOBS[jid]['phase']=='review' and path.read_bytes()==before


def test_training_action_queues_learning_not_resume(plate_job,monkeypatch,tmp_path):
    client,jid,path,_=plate_job
    weights=tmp_path/'trusted-seg.pt';weights.write_bytes(b'test fixture, not executed')
    monkeypatch.setenv('OPENSCRUB_TRAIN_WEIGHTS',str(weights))
    queued=[];monkeypatch.setattr(web.WORK_Q,'put',queued.append)
    response=client.post('/api/jobs/%s/learning'%jid,json={'license_accepted':True})
    assert response.status_code==200,response.get_data(as_text=True)
    assert queued==[(jid,'learn')]
    assert web.JOBS[jid]['phase']=='learning'
    assert client.post('/api/jobs/%s/detections'%jid,json={'enabled':{}}).status_code==409


def test_review_sample_route_and_real_ui_action_exist(plate_job):
    client,jid,path,_=plate_job
    response=client.get('/api/jobs/%s/learning/review?fraction=0.1'%jid)
    assert response.status_code==200 and response.get_json()['indices']==[0]
    assert 'Train &amp; rescan' in web.APP_JS
    assert 'trainAndRescan' in web.APP_JS


def test_failed_learning_run_keeps_report_and_phase(plate_job,monkeypatch):
    client,jid,path,folder=plate_job;job=web.JOBS[jid]
    job.update(log=[],learning_previous_phase='review',phase='learning',output=None)
    before=path.read_bytes()
    import learning_session as ls
    def fail(*a,**k):raise ValueError('candidate failed validation')
    monkeypatch.setattr(ls,'preflight',lambda:{'ready':True,'problems':[]})
    monkeypatch.setattr(ls,'run_session',fail)
    web.perform_learning(job)
    assert job['phase']=='review' and 'failed validation' in job['error']
    assert path.read_bytes()==before


def _seed(plate_job):
    client,jid,path,folder=plate_job
    response=client.post('/api/jobs/%s/plate_quad/0'%jid,json={
        'points':[[54,77],[126,74],[129,91],[52,94]],'autosave':True,'edit_id':'seed'})
    assert response.status_code==200
    job=web.JOBS[jid];job.update(log=[],learning_request={'license_accepted':True})
    doc=json.loads(path.read_text())
    doc['provenance']['input_sha256']=openscrub.sha256_file(job['video'])
    path.write_text(json.dumps(doc))
    return job,doc,path,folder


def test_successful_session_calls_full_scan_and_model_then_commits_constraints(plate_job,tmp_path):
    ls=session();job,old,path,folder=_seed(plate_job)
    old['provenance'].update(original_input='/local/original.mov',vfr_normalized=True,hdr_tonemapped=False)
    path.write_text(json.dumps(old));before=path.read_bytes();events=[]
    class Model:
        def __init__(self,*a):self.calls=0
        def predict(self,crop):
            self.calls+=1
            mask=np.zeros(crop.shape[:2],np.uint8);h,w=mask.shape
            mask[h//3:2*h//3,w//3:2*w//3]=1
            return mask,.99
    def train(dataset,versions,weights,job,settings):
        events.append('train');assert (dataset/'manifest.jsonl').is_file()
        versions.mkdir();(versions/'model.onnx').write_bytes(b'injected test model')
        (versions/'weights.pt').write_bytes(b'injected test weights')
        return versions,{'version':'test-v1','artifacts':{'model.onnx':ls.sha256(versions/'model.onnx')}}
    def scan(destination):
        events.append('scan');assert path.read_bytes()==before
        fresh=deepcopy(old);fresh['provenance'].pop('original_input')
        fresh['detections'][0].update(track=99,cbox=[40,60,140,110],plate_quad=[],verified_label='')
        return fresh
    def publish(result):
        events.append('publish');ls.atomic_json(path,result)
    result=ls.run_session(job,lambda i:web._read_exact_frame(job['video'],i),scan,publish,
        train=train,refiner=Model,calibration=lambda m,d:{'threshold':.5})
    assert events==['train','scan','publish']
    assert result['learning']['inference']['model_calls']==1
    assert result['learning']['needs_render'] is True
    assert result['provenance']['original_input']=='/local/original.mov'
    row=result['detections'][0];b=row['cbox']
    points=np.array(row['plate_quad'])*[b[2]-b[0],b[3]-b[1]]+b[:2]
    assert np.allclose(points,[[54,77],[126,74],[129,91],[52,94]],atol=.001)
    assert row['verified_label']=='plate'
    assert Path(result['learning']['previous_report']).read_bytes()==before or json.loads(Path(result['learning']['previous_report']).read_text())==old
    # Unchanged feedback must be refused before running training again.
    with pytest.raises(ValueError,match='No new'):
        ls.run_session(job,lambda i:web._read_exact_frame(job['video'],i),scan,publish,
            train=lambda *a:pytest.fail('unchanged training repeated'))


def test_validation_failure_does_not_start_full_scan_or_replace_report(plate_job,tmp_path):
    ls=session();job,old,path,folder=_seed(plate_job);before=path.read_bytes()
    def gate(*a):raise ValueError('candidate undercovers plate pixels')
    with pytest.raises(ValueError,match='undercovers'):
        ls.run_session(job,lambda i:web._read_exact_frame(job['video'],i),
            lambda *a:pytest.fail('rejected model must not start scan'),
            lambda *a:pytest.fail('rejected model must not publish'),
            train=lambda *a:(tmp_path,{'version':'rejected'}),refiner=lambda *a:object(),calibration=gate)
    assert path.read_bytes()==before


def test_annotation_group_remains_identical_after_rescan_ids_change(plate_job):
    ls=session();job,doc,path,folder=_seed(plate_job)
    feedback=ls.collect_feedback(job,doc,lambda i:web._read_exact_frame(job['video'],i))
    sample=next(iter(feedback['samples'].values()))
    assert feedback['constraints']['anchors'][0]['group']==sample['group']


def test_hdr_match_learning_is_rejected_before_training(plate_job,monkeypatch,tmp_path):
    client,jid,path,folder=plate_job
    doc=json.loads(path.read_text());doc['provenance']['hdr_output']=True
    path.write_text(json.dumps(doc))
    weights=tmp_path/'model.pt';weights.write_bytes(b'fixture')
    monkeypatch.setenv('OPENSCRUB_TRAIN_WEIGHTS',str(weights))
    response=client.post('/api/jobs/%s/learning'%jid,json={'license_accepted':True})
    assert response.status_code==409
    assert 'HDR' in response.get_json()['error']
    assert web.JOBS[jid]['phase']=='review'


def test_rollback_restores_previous_report_without_losing_training_files(plate_job):
    ls=session();client,jid,path,folder=plate_job
    old=json.loads(path.read_text());old['provenance']['input_sha256']='a'*64
    archived=folder/'learning/passes/accepted/before-report.json'
    ls.atomic_json(archived,old)
    current=deepcopy(old);current['detections'][0]['cbox']=[1,1,20,20]
    current['learning']={'previous_report':str(archived),'needs_render':True,'active':{'pass_id':'new'}}
    path.write_text(json.dumps(current))
    keep=folder/'learning/feedback.json';keep.write_text('{"retained":true}')
    response=client.post('/api/jobs/%s/learning/rollback'%jid)
    assert response.status_code==200,response.get_data(as_text=True)
    restored=json.loads(path.read_text())
    assert restored['detections']==old['detections'] and restored['learning']['needs_render']
    assert keep.read_text()=='{"retained":true}'


def test_rollback_refuses_arbitrary_report_path(plate_job,tmp_path):
    client,jid,path,folder=plate_job
    doc=json.loads(path.read_text());doc['learning']={'previous_report':str(tmp_path/'outside.json')}
    path.write_text(json.dumps(doc));before=path.read_bytes()
    response=client.post('/api/jobs/%s/learning/rollback'%jid)
    assert response.status_code in (400,409) and path.read_bytes()==before


def test_render_rejects_learning_busy_instead_of_claiming_to_start(plate_job):
    client,jid,_,_=plate_job;web.JOBS[jid]['phase']='learning'
    response=client.post('/api/jobs/%s/render'%jid)
    assert response.status_code==409


def test_render_round_trip_retains_review_rows_and_annotation_identities(plate_job):
    ls=session();_,_,path,_=plate_job
    before=json.loads(path.read_text())
    before['provenance']['input_sha256']='a'*64
    before['detections'][0].update(verified_label='plate',learning_anchor='stable-anchor',
                                  learning_group='stable-object',frame_index=2)
    denied=deepcopy(before['detections'][0]);denied.update(enabled=False,verified_label='not_plate',track=33)
    before['detections'].insert(0,denied)
    before['learning']={'needs_render':True,'active':{'pass_id':'accepted'}}
    rendered=deepcopy(before)
    rendered['detections']=[{'category':'plate','enabled':True}]
    rendered.pop('learning')
    rendered['provenance']['output_sha256']='b'*64
    result=ls.preserve_render_review(before,rendered)
    assert result['detections']==before['detections']
    assert result['learning']['needs_render'] is False
    assert result['learning']['active']==before['learning']['active']
    assert result['provenance']['output_sha256']=='b'*64
    assert before['learning']['needs_render'] is True


def test_render_round_trip_refuses_changed_source(plate_job):
    ls=session();_,_,path,_=plate_job
    before=json.loads(path.read_text());before['provenance']['input_sha256']='a'*64
    rendered=deepcopy(before);rendered['provenance']['input_sha256']='c'*64
    with pytest.raises(ValueError,match='source'):
        ls.preserve_render_review(before,rendered)
