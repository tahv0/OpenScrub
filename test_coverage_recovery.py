"""Completed candidates have a bounded, inspectable recovery, never a bypass."""
from copy import deepcopy
import json
from pathlib import Path
import shutil

import cv2
import numpy as np
import pytest

import learning_session as ls
import video_learning as vl
import openscrub_web as web
from test_plate_quad_editor import plate_job
from test_plate_seg_training import dataset
from test_learning_session import _seed


@pytest.fixture
def calibration_data(tmp_path):
    root = tmp_path / 'dataset'
    (root/'images/val').mkdir(parents=True)
    (root/'labels/val').mkdir(parents=True)
    rows = []
    for i in range(4):
        image = np.full((120,120,3), 130, np.uint8)
        cv2.imwrite(str(root/f'images/val/{i}.png'), image)
        (root/f'labels/val/{i}.txt').write_text('0 .25 .25 .75 .25 .75 .75 .25 .75\n')
        rows.append(dict(image=f'images/val/{i}.png', split='val', label='positive',
                         detection_index=100+i, baseline_box=[0,0,1,1]))
    (root/'manifest.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
    return root


class Predictor:
    def __init__(self, start=33, end=88):
        self.start, self.end, self.calls = start, end, 0
    def predict(self, image):
        self.calls += 1
        if self.start is None:
            return None, .1
        mask = np.zeros(image.shape[:2],np.uint8)
        mask[self.start:self.end,self.start:self.end] = 1
        return mask, .91


def test_small_shortfall_uses_bounded_margin_not_lower_coverage(calibration_data):
    model = Predictor()
    gate = ls.calibrate(model, calibration_data)
    assert 0 < gate['margin_fraction'] <= .05
    assert gate['minimum_known_coverage'] == .995
    assert gate['accepted'] == 4 and gate['excess_pixels_removed'] > 0
    assert model.calls == 4  # No inference per padding/threshold candidate.
    raw,_ = model.predict(np.zeros((120,120,3),np.uint8))
    _,covered = vl.conservative_quad(raw, margin_fraction=gate['margin_fraction'])
    assert covered[30:91,30:91].mean() >= .995


@pytest.mark.parametrize('start,end,reason', [(45,75,'undercoverage'),(None,None,'no_accepted_predictions')])
def test_real_failures_get_measurements_without_acceptance(calibration_data,tmp_path,start,end,reason):
    path = tmp_path/'coverage.json'
    with pytest.raises(ValueError, match='coverage|Coverage'):
        ls.calibrate(Predictor(start,end), calibration_data, report_path=path)
    report = json.loads(path.read_text())
    assert report['decision'] == 'rejected'
    assert any(a['reason'] == reason for a in report['attempts'])
    assert {e['frame'] for e in report['examples']} == {100,101,102,103}
    assert report['minimum_known_coverage'] == .995
    assert report['previews'] and len(report['previews']) <= 6
    for row in report['previews']:
        assert cv2.imread(str(path.parent/row['image'])) is not None


def test_no_tightening_is_not_called_an_improvement(calibration_data,tmp_path):
    rows=[json.loads(s) for s in (calibration_data/'manifest.jsonl').read_text().splitlines()]
    for row in rows: row['baseline_box']=[.25,.25,.75,.75]
    (calibration_data/'manifest.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
    with pytest.raises(ValueError):
        ls.calibrate(Predictor(29,92),calibration_data,report_path=tmp_path/'coverage.json')
    assert any(a['reason']=='no_tightening' for a in json.loads((tmp_path/'coverage.json').read_text())['attempts'])


@pytest.mark.parametrize('value', [-.01,.051,float('nan'),float('inf')])
def test_margin_bounds_fail_closed(value):
    with pytest.raises(ValueError, match='margin'):
        vl.conservative_quad(np.ones((10,10),np.uint8), margin_fraction=value)


def test_cancellation_during_calibration_does_not_publish_report(calibration_data,tmp_path):
    with pytest.raises(InterruptedError):
        ls.calibrate(Predictor(),calibration_data,report_path=tmp_path/'coverage.json',cancelled=lambda:True)
    assert not (tmp_path/'coverage.json').exists()


def test_saved_candidate_reuse_checks_dataset_source_and_artifacts(dataset,tmp_path):
    original,_ = dataset
    report = ls._validate_snapshot(original)
    root = tmp_path/'learning'
    stage = root/'passes/pass-123456789abc'
    folder = stage/'versions/v20261110T120000Z-12345678'
    folder.mkdir(parents=True)
    shutil.copytree(original, stage/'dataset')
    (stage/'before-report.json').write_text(json.dumps({'provenance':{'input_sha256':'a'*64}}))
    for name in ('weights.pt','model.onnx'): (folder/name).write_bytes(b'fixture; not executed')
    meta = dict(version=folder.name,status='candidate',dataset=report,
                artifacts={n:ls.sha256(folder/n) for n in ('weights.pt','model.onnx')})
    (folder/'manifest.json').write_text(json.dumps(meta))
    found,got = ls._reuse_candidate(root,report,'a'*64)
    assert found==folder and got==meta
    with pytest.raises(ValueError,match='compatible'):
        ls._reuse_candidate(root,report,'b'*64)
    changed=deepcopy(report); changed['dataset_sha256']='0'*64
    with pytest.raises(ValueError,match='compatible'):
        ls._reuse_candidate(root,changed,'a'*64)
    (folder/'model.onnx').write_bytes(b'corrupted')
    with pytest.raises(ValueError,match='integrity|checksum'):
        ls._reuse_candidate(root,report,'a'*64)


def test_recheck_queue_does_not_require_training_checkpoint(plate_job,monkeypatch):
    client,jid,path,_ = plate_job
    monkeypatch.delenv('OPENSCRUB_TRAIN_WEIGHTS',raising=False)
    queued=[];monkeypatch.setattr(web.WORK_Q,'put',queued.append)
    response=client.post(f'/api/jobs/{jid}/learning',json={'reuse_candidate':True})
    assert response.status_code==200,response.get_data(as_text=True)
    assert web.JOBS[jid]['learning_request']['reuse_candidate'] is True
    assert queued==[(jid,'learn')]


def test_recheck_worker_never_requires_cuda_training_preflight(plate_job,monkeypatch):
    _,jid,_,_ = plate_job; job=web.JOBS[jid]
    job.update(learning_previous_phase='review',learning_request={'reuse_candidate':True},log=[])
    monkeypatch.setattr(ls,'preflight',lambda:pytest.fail('Not retraining: CUDA trainer must not run'))
    def rejected(*args,**kwargs): raise ValueError('Coverage remains insufficient')
    monkeypatch.setattr(ls,'run_session',rejected)
    web.perform_learning(job)
    assert job['phase']=='review' and job['error']=='Coverage remains insufficient'


def test_session_reuses_candidate_without_train_and_forwards_margin(plate_job,tmp_path,monkeypatch):
    job,old,path,folder = _seed(plate_job)
    job['learning_request']['reuse_candidate']=True
    monkeypatch.setattr(ls,'_validate_snapshot',lambda path: {'dataset_sha256':'fixture'})
    monkeypatch.setattr(ls,'_reuse_candidate',lambda *args:(tmp_path,{'version':'fixture','artifacts':{'model.onnx':'fixture'}}))
    seen={}
    def refine(video,doc,model,threshold,cancelled,**kw):
        seen.update(kw); return doc,dict(refined=1,model_calls=1)
    monkeypatch.setattr(vl,'refine_report',refine)
    result=ls.run_session(job,lambda i:web._read_exact_frame(job['video'],i),
        lambda p:deepcopy(old),lambda result:None,
        train=lambda *a:pytest.fail('Recheck must not train'),refiner=lambda *a:object(),
        calibration=lambda m,d:{'threshold':.5,'margin_fraction':.03})
    assert seen['margin_fraction']==.03
    assert result['learning']['version']=='fixture'


def test_coverage_endpoints_are_job_scoped_and_do_not_train(plate_job,tmp_path):
    client,jid,path,folder=plate_job
    root=folder/'learning'; stage=root/'passes/pass-123456789abc';stage.mkdir(parents=True)
    ls.atomic_json(root/'last-coverage.json',{'pass_id':stage.name})
    ls.atomic_json(stage/'coverage.json',{'decision':'rejected','examples':[{'frame':1}]})
    cv2.imwrite(str(stage/'coverage-0.jpg'),np.zeros((40,80,3),np.uint8))
    r=client.get(f'/api/jobs/{jid}/learning/coverage')
    assert r.status_code==200 and r.json['decision']=='rejected'
    assert client.get(f'/api/jobs/{jid}/learning/coverage/{stage.name}/0.jpg').status_code==200
    assert client.get(f'/api/jobs/{jid}/learning/coverage/{stage.name}/900.jpg').status_code==404
    ls.atomic_json(root/'last-coverage.json',{'pass_id':'../outside'})
    assert client.get(f'/api/jobs/{jid}/learning/coverage').status_code==404


def test_refinement_uses_the_same_padded_outline_as_calibration(tmp_path):
    from test_video_learning import report,row
    video=tmp_path/'fixture.avi'
    writer=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*'MJPG'),10,(160,120))
    for _ in range(10):writer.write(np.full((120,160,3),128,np.uint8))
    writer.release()
    doc=report([row(2,[30,30,100,95])])
    class Model:
        def predict(self,image):
            h,w=image.shape[:2];m=np.zeros((h,w),np.uint8);m[35:65,35:75]=1
            self.raw=m;return m,.95
    model=Model();updated,stats=vl.refine_report(video,doc,model,.5,margin_fraction=.05)
    points,_=vl.conservative_quad(model.raw,margin_fraction=.05)
    x1,y1,_,_=vl.crop_bounds([30,30,100,95],(120,160,3))
    actual=np.array(updated['detections'][0]['plate_quad'])*[70,65]+[30,30]
    assert np.allclose(actual,points+[x1,y1])
    assert stats['refined']==1


def test_candidate_dataset_edits_are_detected_even_when_metadata_matches(dataset,tmp_path):
    original,_=dataset;report=ls._validate_snapshot(original)
    stage=tmp_path/'learning/passes/pass-123456789abc';folder=stage/'versions/v20261110T120000Z-12345678'
    folder.mkdir(parents=True);shutil.copytree(original,stage/'dataset')
    (stage/'before-report.json').write_text(json.dumps({'provenance':{'input_sha256':'a'*64}}))
    for n in ('model.onnx','weights.pt'):(folder/n).write_bytes(b'fixture')
    meta=dict(version=folder.name,status='candidate',dataset=report,artifacts={n:ls.sha256(folder/n) for n in ('model.onnx','weights.pt')})
    (folder/'manifest.json').write_text(json.dumps(meta))
    label=next((stage/'dataset/labels/train').glob('*.txt'));label.write_text('0 .1 .1 .9 .1 .9 .9 .1 .9\n')
    with pytest.raises(ValueError):ls._reuse_candidate(tmp_path/'learning',report,'a'*64)


@pytest.mark.parametrize('value',['true',1,[],{}])
def test_reuse_flag_is_strict_boolean_not_a_fallthrough_to_training(plate_job,value):
    client,jid,_,_=plate_job
    r=client.post(f'/api/jobs/{jid}/learning',json={'reuse_candidate':value,'license_accepted':True})
    assert r.status_code==400
