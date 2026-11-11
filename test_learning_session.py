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


def _compact_archive_job(tmp_path, shape=True):
    import threading
    import confirmed_findings as cf
    from test_confirmed_findings import jpeg, video, finding
    jobdir=tmp_path/'job';jobdir.mkdir()
    job={'dir':jobdir,'video':str(tmp_path/'missing-source.mp4'),'cancel':threading.Event(),
         'log':[],'learning':{},'model_root':tmp_path/'models'}
    archive=tmp_path/'confirmed_findings'
    points=[[100,100],[280,100],[280,190],[100,190]]
    positive=cf.record(archive,video(),finding(frame=4,points=points if shape else None,
        shape_confirmed=shape),jpeg())
    negative=cf.record(archive,video(),finding(frame=2,label='negative'),jpeg())
    def row(frame,track,label,entry=None,propagated=False):
        result=dict(category='plate',frame_index=frame,t_start=frame/25.,t_end=(frame+1)/25.,
            cbox=[100,100,280,190],track=track,enabled=label=='positive',
            plate_quad=[[0,0],[1,0],[1,1],[0,1]] if label=='positive' else [],
            verified_label='plate' if label=='positive' else 'not_plate',
            human_confirmation=dict(label=label,source='explicit',propagated=propagated))
        if entry:
            result.update(confirmed_finding_id=entry['id'],confirmed_finding_revision=1)
        return result
    doc=dict(provenance=dict(input_sha256='b'*64),render_state=dict(fps=25.,cum=[[0.,0.]]*10),
        detections=[row(0,2,'negative',propagated=True),row(2,2,'negative',negative),
                    row(4,4,'positive',positive)])
    return job,doc,archive,positive,negative


def test_compact_confirmed_seed_crops_train_without_legacy_annotations_or_decoder(tmp_path):
    ls=session();job,doc,archive,positive,negative=_compact_archive_job(tmp_path)
    def forbidden(*args):pytest.fail('Stored confirmed crop reopened source video')
    data=ls.collect_feedback(job,doc,forbidden)
    assert len(data['samples'])==2
    by_label={s['label']:s for s in data['samples'].values()}
    assert by_label['positive']['quality']=='human_quad'
    assert by_label['positive']['frame']==4
    assert by_label['negative']['frame']==2
    assert by_label['positive']['archive_id']==positive['id']
    assert by_label['negative']['archive_id']==negative['id']
    assert np.allclose(by_label['positive']['points'],[[20/220,20/130],[200/220,20/130],
                                                    [200/220,110/130],[20/220,110/130]])


def test_current_archive_correction_and_revocation_override_stale_job_training_refs(tmp_path):
    import confirmed_findings as cf
    ls=session();job,doc,archive,positive,negative=_compact_archive_job(tmp_path)
    def forbidden(*args):pytest.fail('Archive correction reopened source video')
    ls.collect_feedback(job,doc,forbidden)
    corrected=cf.update_finding(archive,positive['id'],points=[[110,110],[270,110],[270,180],[110,180]],expected_revision=1)
    data=ls.collect_feedback(job,doc,forbidden)
    sample=next(s for s in data['samples'].values() if s['archive_id']==positive['id'])
    assert sample['archive_revision']==2
    assert sample['points'][0]==pytest.approx([30/220,30/130])
    cf.update_finding(archive,positive['id'],label='negative',expected_revision=corrected['revision'])
    data=ls.collect_feedback(job,doc,forbidden)
    assert all(s['label']=='negative' for s in data['samples'].values())
    cf.forget(archive,positive['id'],expected_revision=3)
    data=ls.collect_feedback(job,doc,forbidden)
    assert len(data['samples'])==1
    assert next(iter(data['samples'].values()))['archive_id']==negative['id']


def test_compact_unshaped_positive_explains_named_checker_instead_of_mask_training(tmp_path):
    ls=session();job,doc,*_=_compact_archive_job(tmp_path,shape=False)
    def forbidden(*args):pytest.fail('Unshaped positive reopened source video')
    with pytest.raises(ValueError,match='corners|named checker'):
        ls.collect_feedback(job,doc,forbidden)


def test_region_draft_and_propagated_classifications_do_not_create_training_seeds(tmp_path):
    ls=session();job,doc,*_=_compact_archive_job(tmp_path)
    for row in doc['detections']:
        row.pop('confirmed_finding_id',None);row.pop('confirmed_finding_revision',None)
        row['human_confirmation']['propagated']=True
    draft=doc['detections'][-1]
    draft.pop('human_confirmation');draft['human_region_confirmed']=True
    def forbidden(*args):pytest.fail('A draft or propagated decision became a training seed')
    assert ls.collect_feedback(job,doc,forbidden)['samples']=={}


def test_rescan_propagated_rows_cannot_reharvest_or_resurrect_archived_seed(tmp_path):
    import confirmed_findings as cf
    ls=session();job,doc,archive,positive,negative=_compact_archive_job(tmp_path)
    def forbidden(*args):pytest.fail('Propagated rescan row became a new training image')
    first=ls.collect_feedback(job,doc,forbidden)
    groups={s['archive_id']:s['group'] for s in first['samples'].values()}
    for row in doc['detections']:
        row.pop('human_confirmation',None);row.pop('confirmed_finding_id',None)
        row.pop('confirmed_finding_revision',None)
        row['learning_group']=groups[negative['id'] if row['track']==2 else positive['id']]
    second=ls.collect_feedback(job,doc,forbidden)
    assert len(second['samples'])==2
    cf.forget(archive,negative['id'],expected_revision=1)
    third=ls.collect_feedback(job,doc,forbidden)
    fourth=ls.collect_feedback(job,doc,forbidden)
    assert len(third['samples'])==len(fourth['samples'])==1
    assert next(iter(fourth['samples'].values()))['archive_id']==positive['id']


def test_legacy_archive_parent_then_named_correction_replaces_same_example(tmp_path):
    import confirmed_findings as cf
    import findings_training as ft
    from test_findings_training import trainer, make_job
    from test_learning_candidates import candidate_job, PASS_ID, VERSION
    import shutil
    ls=session();job,doc,archive,positive,negative=_compact_archive_job(tmp_path)
    def forbidden(*args):pytest.fail('Stored seed reopened source video')
    feedback=ls.collect_feedback(job,doc,forbidden)
    fixture_job,fixture_folder=candidate_job(tmp_path/'fixture')
    stage=job['dir']/'learning'/'passes'/PASS_ID
    folder=stage/'versions'/VERSION
    shutil.copytree(fixture_folder,folder)
    ls.export_dataset(job['dir']/'learning',feedback,stage/'dataset')
    splits=ls._load(stage/'dataset'/'split-groups.json')['groups']
    parent=ft.publish_session_candidate(job,stage,folder,feedback,
        {g for g,s in splits.items() if s=='train'},'Legacy parent')
    cf.update_finding(archive,positive['id'],label='negative',expected_revision=1)
    result=ft.run(make_job(tmp_path/'named'),archive,job['model_root'],
        {'name':'Named correction','parent_model_id':parent['id'],
         'example_ids':[positive['id']],'license_accepted':True},train=trainer)
    lineage=ft.resolve_parent(job['model_root'],result['model_id'])['lineage']
    same=[s for s in lineage['samples'].values() if s['source']['id']==positive['id']]
    assert len(same)==1
    assert same[0]['label']=='negative' and same[0]['source']['revision']==2
    assert len(lineage['samples'])==2


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


def _seed(plate_job, points=None):
    client,jid,path,folder=plate_job
    response=client.post('/api/jobs/%s/plate_quad/0'%jid,json={
        'points':points or [[54,77],[126,74],[129,91],[52,94]],'autosave':True,'edit_id':'seed'})
    assert response.status_code==200
    job=web.JOBS[jid];job.update(log=[],learning_request={'license_accepted':True})
    doc=json.loads(path.read_text())
    doc['provenance']['input_sha256']=openscrub.sha256_file(job['video'])
    path.write_text(json.dumps(doc))
    return job,doc,path,folder


@pytest.mark.parametrize('points', [
    [[54,77],[126,74],[129,91],[52,94]],
    [[54,18],[126,21],[129,91],[52,94]],
])
def test_successful_session_calls_full_scan_and_model_then_commits_constraints(plate_job,tmp_path,points):
    ls=session();job,old,path,folder=_seed(plate_job,points)
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
        assert job['learning']['stage']=='refining'
        assert job['learning']['done']==job['learning']['total']==len(old['render_state']['cum'])
        assert job['learning']['unit']=='frames'
        events.append('publish');ls.atomic_json(path,result)
    result=ls.run_session(job,lambda i:web._read_exact_frame(job['video'],i),scan,publish,
        train=train,refiner=Model,calibration=lambda m,d:{'threshold':.5})
    assert events==['train','scan','publish']
    assert result['learning']['inference']['model_calls']==1
    assert result['learning']['needs_render'] is True
    assert result['provenance']['original_input']=='/local/original.mov'
    row=result['detections'][0];b=row['cbox']
    restored=np.array(row['plate_quad'])*[b[2]-b[0],b[3]-b[1]]+b[:2]
    assert np.allclose(restored,points,atol=.001)
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


def test_named_failed_mask_candidate_is_saved_with_independent_checker_assessment(plate_job,tmp_path):
    from test_findings_training import trainer
    import learned_models as models
    import learning_candidates
    import findings_training
    ls=session();job,old,path,folder=_seed(plate_job);before=path.read_bytes()
    job['learning_request']['name']='Evening plates'
    job['model_root']=tmp_path/'models'
    weights=tmp_path/'base.pt';weights.write_bytes(b'trusted weights')
    def local_train(dataset,versions,weight_path,job,settings):
        return trainer(dataset,versions,weights,job,dict(settings,verifier_training=True))
    def rejected(*args):raise ls.CoverageRejected('Mask too small')
    with pytest.raises(ls.CoverageRejected):
        ls.run_session(job,lambda i:web._read_exact_frame(job['video'],i),
            lambda *a:pytest.fail('Rejected mask cannot rescan'),
            lambda *a:pytest.fail('Rejected mask cannot publish a report'),
            train=local_train,refiner=lambda *a:object(),calibration=rejected)
    assert path.read_bytes()==before
    saved=models.list_models(job['model_root'])
    assert len(saved)==1 and saved[0]['name']=='Evening plates' and saved[0]['schema']==2
    assert findings_training.training_info(job['model_root'],saved[0]['id'])['trainable']
    candidate=learning_candidates.list_candidates(job['dir'])[0]
    assert candidate['name']=='Evening plates'
    assert candidate['mask_assessment']['status']=='failed'
    assert candidate['assessment'] is not None


def test_accepted_legacy_continuation_uses_detached_parent_checkpoint_and_retains_lineage(plate_job,tmp_path,monkeypatch):
    from test_findings_training import trainer
    import findings_training as ft
    ls=session();job,old,path,folder=_seed(plate_job)
    job['model_root']=tmp_path/'models'
    job['learning_request']['name']='First pass'
    base=tmp_path/'base.pt';base.write_bytes(b'base')
    monkeypatch.setenv('OPENSCRUB_TRAIN_WEIGHTS',str(base))
    seen=[]
    def local_train(dataset,versions,weights,job,settings):
        seen.append(Path(weights))
        return trainer(dataset,versions,weights,job,dict(settings,verifier_training=True))
    monkeypatch.setattr(ls.vl,'refine_report',lambda video,fresh,*a,**kw:
        (deepcopy(fresh),{'model_calls':1,'refined':1}))
    def execute():
        return ls.run_session(job,lambda i:web._read_exact_frame(job['video'],i),
            lambda destination:json.loads(path.read_text()),lambda result:ls.atomic_json(path,result),
            train=local_train,refiner=lambda *a:object(),calibration=lambda *a:{'threshold':.5})
    first=execute();parent_id=first['learning']['library_model_id']
    assert first['learning']['active']['model_id']==parent_id
    parent=ft.resolve_parent(job['model_root'],parent_id)
    # The previous transient checkpoint and configured base can disappear;
    # continuing the accepted model uses its verified independent local copy.
    Path(first['learning']['active']['weights']).unlink();base.unlink()
    changed=json.loads(path.read_text());changed['detections'][0].update(verified_label='not_plate',enabled=False)
    path.write_text(json.dumps(changed));job['learning_request']['name']='Second pass'
    second=execute();child_id=second['learning']['library_model_id']
    child=ft.resolve_parent(job['model_root'],child_id)
    assert seen[-1]==Path(parent['weights'])
    assert child['lineage']['parent_model_id']==parent_id
    assert all(item in child['lineage']['training_exposure'] for item in parent['lineage']['training_exposure'])
    assert second['learning']['active']['model_id']==child_id


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
    before['verification']={'schema':1,'model_sha256':'c'*64,'mode':'filter',
                            'stats':{'checked':2,'suppressed':1}}
    before['verification_history']=[dict(deepcopy(before['verification']),frame_range=[0,2])]
    rendered=deepcopy(before)
    rendered['detections']=[{'category':'plate','enabled':True}]
    rendered.pop('learning')
    rendered.pop('verification')
    rendered.pop('verification_history')
    rendered['provenance']['output_sha256']='b'*64
    result=ls.preserve_render_review(before,rendered)
    assert result['detections']==before['detections']
    assert result['learning']['needs_render'] is False
    assert result['learning']['active']==before['learning']['active']
    assert result['verification']==before['verification']
    assert result['verification'] is not before['verification']
    assert result['verification_history']==before['verification_history']
    result['verification_history'][0]['stats']['checked']=99
    assert before['verification_history'][0]['stats']['checked']==2
    assert result['provenance']['output_sha256']=='b'*64
    assert before['learning']['needs_render'] is True


def test_render_round_trip_refuses_changed_source(plate_job):
    ls=session();_,_,path,_=plate_job
    before=json.loads(path.read_text());before['provenance']['input_sha256']='a'*64
    rendered=deepcopy(before);rendered['provenance']['input_sha256']='c'*64
    with pytest.raises(ValueError,match='source'):
        ls.preserve_render_review(before,rendered)


@pytest.mark.parametrize('box,points', [
    ([45,67,137,103], [[54,18],[126,21],[129,91],[52,94]]),
    ([45,67,137,103], [[54,77],[126,74],[129,153],[52,156]]),
    ([82,76,98,86], [[55,65],[125,66],[122,97],[56,96]]),
    ([45,67,137,103], [[70,16],[143,88],[102,129],[30,54]]),
])
@pytest.mark.parametrize('offset', [(0,0),(13,-9)])
def test_training_crop_follows_saved_corners_beyond_detector_box(plate_job, box, points, offset):
    """Use the real autosave path: these valid review edits used to fail collection."""
    import cv2
    import video_learning as vl
    from scripts.train_plate_seg import _quad_valid
    ls=session();client,jid,path,folder=plate_job;job=web.JOBS[jid]
    doc=json.loads(path.read_text());ox,oy=offset
    doc['detections'][0]['cbox']=[box[0]-ox,box[1]-oy,box[2]-ox,box[3]-oy]
    doc['render_state']['cum']=[list(offset)]*10
    doc['provenance']['input_sha256']=openscrub.sha256_file(job['video'])
    path.write_text(json.dumps(doc))
    endpoint='/api/jobs/%s/plate_quad/0'%jid
    meta=client.get(endpoint).get_json()
    response=client.post(endpoint,json={'points':points,'preview_token':meta['preview_token'],
                                       'autosave':True,'edit_id':'expanded-correction'})
    assert response.status_code==200, response.get_data(as_text=True)
    doc=json.loads(path.read_text());source=web._read_exact_frame(job['video'],2)
    old=vl.crop_bounds(box,source.shape)
    p=np.asarray(points)
    assert (p[:,0].min()<old[0] or p[:,1].min()<old[1]
            or p[:,0].max()>old[2] or p[:,1].max()>old[3])
    report_before=path.read_bytes()
    annotation_before={p.name:p.read_bytes() for p in (folder/'plate_annotations').iterdir()}
    calls=[]
    def read_frame(index):
        calls.append(index)
        return source.copy()
    feedback=ls.collect_feedback(job,doc,read_frame)
    assert calls==[2]
    assert len(feedback['samples'])==1
    sample=next(iter(feedback['samples'].values()))
    crop=cv2.imread(str(folder/'learning'/sample['image']))
    h,w=crop.shape[:2]
    origin=np.array(box[:2])-np.array(sample['baseline_box'][:2])*[w,h]
    restored=np.array(sample['points'])*[w,h]+origin
    assert np.allclose(restored,points,atol=.0001,rtol=0), 'Correction was clipped or shifted'
    assert np.all(np.array(sample['points'])>=0) and np.all(np.array(sample['points'])<=1)
    assert sample['box']==box, 'Original proposal identity changed'
    x,y=np.rint(origin).astype(int)
    assert np.array_equal(crop,source[y:y+h,x:x+w]), 'Pixels and labels refer to different crops'
    records=ls.export_dataset(folder/'learning',feedback,folder/'dataset')
    label_path=folder/'dataset'/'labels'/records[0]['split']/(Path(records[0]['image']).stem+'.txt')
    values=label_path.read_text().split()
    assert values[0]=='0' and _quad_valid(values[1:])
    assert path.read_bytes()==report_before
    assert annotation_before=={p.name:p.read_bytes() for p in (folder/'plate_annotations').iterdir()}
    again=ls.collect_feedback(job,doc,lambda i:pytest.fail('Imported sample decoded again'))
    assert again['fingerprint']==feedback['fingerprint'] and len(again['samples'])==1


def test_training_crop_tolerates_only_saved_coordinate_roundoff_at_frame_edge(plate_job):
    import cv2
    ls=session();client,jid,path,folder=plate_job;job=web.JOBS[jid]
    doc=json.loads(path.read_text());doc['detections'][0]['cbox']=[46,67,139,103]
    doc['provenance']['input_sha256']=openscrub.sha256_file(job['video'])
    path.write_text(json.dumps(doc))
    points=[[0,50],[134,51],[134,95],[0,94]]
    response=client.post('/api/jobs/%s/plate_quad/0'%jid,json={
        'points':points,'autosave':True,'edit_id':'frame-edge'})
    assert response.status_code==200
    doc=json.loads(path.read_text())
    q=np.array(doc['detections'][0]['plate_quad'])
    assert -0.0001 < (q[:,0]*93+46).min() < 0, 'Fixture must exercise serialization roundoff'
    data=ls.collect_feedback(job,doc,lambda i:web._read_exact_frame(job['video'],i))
    sample=next(iter(data['samples'].values()))
    crop=cv2.imread(str(folder/'learning'/sample['image']));h,w=crop.shape[:2]
    origin=np.array([46,67])-np.array(sample['baseline_box'][:2])*[w,h]
    assert np.allclose(np.array(sample['points'])*[w,h]+origin,points,atol=.0001,rtol=0)
    assert np.all(np.array(sample['points'])>=0)


@pytest.mark.parametrize('quad,reason', [
    ([[-4,0],[1,0],[1,1],[-4,1]], 'outside the source frame'),
    ([[0,0],[1,1],[0,1],[1,0]], 'convex'),
    ([[0,0],[1,0],[1,1]], 'four finite'),
    ([[float('nan'),0],[1,0],[1,1],[0,1]], 'four finite'),
])
def test_invalid_training_polygon_is_diagnosable_and_preserves_saved_feedback(plate_job, quad, reason):
    ls=session();job,doc,path,folder=_seed(plate_job);client,jid,_,_=plate_job
    ls.collect_feedback(job,doc,lambda i:web._read_exact_frame(job['video'],i))
    saved_feedback=(folder/'learning/feedback.json').read_bytes()
    assert client.post('/api/jobs/%s/plate_quad/0'%jid,json={
        'points':[[55,76],[125,75],[128,92],[53,93]],'autosave':True,'edit_id':'second'}).status_code==200
    doc=json.loads(path.read_text());doc['detections'][0]['plate_quad']=quad
    before=path.read_bytes();manifest=(folder/'plate_annotations/annotations.jsonl').read_bytes()
    with pytest.raises(ValueError,match='finding 0, frame 2.*'+reason):
        ls.collect_feedback(job,doc,lambda i:web._read_exact_frame(job['video'],i))
    assert path.read_bytes()==before
    assert (folder/'plate_annotations/annotations.jsonl').read_bytes()==manifest
    assert (folder/'learning/feedback.json').read_bytes()==saved_feedback
