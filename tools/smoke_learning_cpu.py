#!/usr/bin/env python3
"""Mechanical smoke with actual training, ONNX, scan engine and rendering.

Only the hardware guard/device and original proposal detector are substituted.
No test-result screenshot is real user footage. Production still requires CUDA.
"""
import sys,os,json,argparse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.update(YOLO_AUTOINSTALL='false',YOLO_VERBOSE='false')
import cv2,numpy as np,torch
from ultralytics import YOLO
from scripts import train_plate_seg as trainer
import video_learning as vl


def archive_named_examples(archive, originals, start=0, count=80):
 """Explicit synthetic crop evidence; no source video or detector labels."""
 import hashlib
 import confirmed_findings as findings
 originals.mkdir(parents=True,exist_ok=True)
 saved=[]
 for index in range(start,start+count):
  random=np.random.default_rng(9061+index)
  image=random.integers(0,220,(128,128,3),dtype=np.uint8)
  negative=index%4==0
  points=np.array([[.16,.32],[.80,.29],[.84,.63],[.15,.66]])
  points+=random.uniform(-.08,.08,(1,2))
  if not negative:
   cv2.fillPoly(image,[(points*128).astype(np.int32)],(235,238,240))
   cv2.putText(image,'%02d AB'%index,(24,66),cv2.FONT_HERSHEY_SIMPLEX,.4,(10,10,10),1)
  ok,encoded=cv2.imencode('.jpg',image,[cv2.IMWRITE_JPEG_QUALITY,65]);assert ok
  original=originals/('seed-%03d.jpg'%index);original.write_bytes(encoded.tobytes())
  identity=hashlib.sha256(('synthetic-confirmed-source-%d'%(index%2)).encode()).hexdigest()
  video=dict(sha256=identity,variant_sha256=identity,
   name='synthetic-confirmed-road-%d.avi'%(index%2),fps=10.,width=128,height=128,total_frames=1000)
  shaped=not negative and index%3==1
  finding=dict(category='plate',label='negative' if negative else 'positive',explicit=True,
   frame=index//2,box=[1,15,127,116],crop=[0,0,128,128],
   points=(points*128).tolist() if shaped else None,shape_confirmed=shaped,
   job_id='synthetic-confirmation-only')
  saved.append(findings.record(archive,video,finding,original.read_bytes()))
 return saved


def named_training_smoke(output_root, initial_checkpoint):
 """Two actual one-epoch runs through the production named-training orchestration."""
 import shutil
 import threading
 import zipfile
 import io
 import confirmed_findings as findings
 import findings_training as named
 import learned_models as models
 import learning_candidates as candidates

 workspace=output_root/'named-workflow';workspace.mkdir()
 archive=workspace/'confirmed_findings';model_root=workspace/'models'
 originals=workspace/'original-evidence'
 saved=archive_named_examples(archive,originals)
 passes=[]
 def actual_cpu_train(dataset,versions,checkpoint,job,settings):
  assert settings['verifier_training'] is True
  report=trainer.validate_dataset(dataset,allow_confirmed_regions=True)
  assert report['supervision']=='confirmed_regions' and report['mask_eligible'] is False
  before=YOLO(str(checkpoint)).model.state_dict()['model.0.conv.weight'].clone()
  arguments=argparse.Namespace(dataset=dataset,weights=Path(checkpoint),versions_dir=versions,
   device='cpu',accept_ultralytics_license=True,epochs=1,batch=4,imgsz=128,workers=0,
   patience=0,seed=71+len(passes),min_mask_map50=0.,min_train_positive=12,
   min_val_positive=4,min_negative_per_split=1,allow_confirmed_regions=True)
  metadata=trainer.train(arguments,report)
  trained=versions/metadata['version']
  after=YOLO(str(trained/'weights.pt')).model.state_dict()['model.0.conv.weight']
  change=float((after-before).abs().sum());assert change>0,'named training did not update weights'
  for filename in ('weights.pt','model.onnx'):
   assert trainer.sha256_file(trained/filename)==metadata['artifacts'][filename]
  passes.append(dict(name=settings['name'],epochs=1,device='cpu',dataset=report,
   source_checkpoint_sha256=trainer.sha256_file(checkpoint),
   backbone_weight_change_L1=change,artifacts=metadata['artifacts']))
  return trained,metadata
 def job(name):
  folder=workspace/name;folder.mkdir()
  return dict(dir=folder,cancel=threading.Event(),learning={},log=[],kind='model_training',
   video=str(workspace/'source-video-was-never-created.avi'))
 def inference_evidence(result,label):
  inference_job=workspace/('inference-'+label)
  models.snapshot_model(model_root,result['model_id'],inference_job,mode='review')
  assert models.load_selection(inference_job)=='review'
  checker=vl.CropRefiner(inference_job/'plate_model'/'model.onnx',providers=['CPUExecutionProvider'])
  image=cv2.imread(str(findings.image_path(archive,saved[1]['id'])))
  mask,score=checker.predict(image)
  assert checker.calls==1 and np.isfinite(score)
  if mask is not None:assert mask.shape==image.shape[:2]
  return dict(onnx_calls=checker.calls,score=float(score),mask_present=mask is not None,selection_mode='review')

 previous_weights=os.environ.get('OPENSCRUB_TRAIN_WEIGHTS')
 try:
  os.environ['OPENSCRUB_TRAIN_WEIGHTS']=str(initial_checkpoint)
  first_job=job('first-training-job')
  first=named.run(first_job,archive,model_root,
   dict(name='Synthetic confirmed roads',example_ids=[e['id'] for e in saved],
    expected_revisions={e['id']:e['revision'] for e in saved},license_accepted=True),
   log=lambda message:print(message,flush=True),train=actual_cpu_train)
  assert first['model']['schema']==2 and first['name']=='Synthetic confirmed roads'
  first_candidate=candidates.load_candidate(first_job['dir'],first['candidate_id'])
  assert first_candidate['mask_assessment']['status']=='failed'
  assert first_candidate['assessment']==first['assessment']
  first_inference=inference_evidence(first,'first')
  parent=named.resolve_parent(model_root,first['model_id'])
  parent_hash=trainer.sha256_file(parent['weights'])
  parent_manifest=(model_root/first['model_id']/'manifest.json').read_bytes()
  parent_onnx_hash=trainer.sha256_file(model_root/first['model_id']/'model.onnx')
  assert len(parent['lineage']['samples'])==len(saved)
  assert parent['lineage']['training_groups'] and parent['lineage']['training_exposure']
  assert Path(parent['weights']).is_file()
  shutil.rmtree(first_job['dir']);shutil.rmtree(originals)
  os.environ.pop('OPENSCRUB_TRAIN_WEIGHTS',None)
  assert not first_job['dir'].exists() and not originals.exists()
  assert not Path(first_job['video']).exists()

  corrected=findings.update_finding(archive,saved[1]['id'],label='negative',expected_revision=1)
  added=archive_named_examples(archive,workspace/'new-evidence',start=80,count=1)[0]
  second_job=job('second-training-job')
  second=named.run(second_job,archive,model_root,
   dict(name='Synthetic confirmed roads continuation',parent_model_id=first['model_id'],
    example_ids=[added['id']],expected_revisions={added['id']:added['revision']},license_accepted=True),
   log=lambda message:print(message,flush=True),train=actual_cpu_train)
  second_candidate=candidates.load_candidate(second_job['dir'],second['candidate_id'])
  assert second_candidate['mask_assessment']['status']=='failed'
  assert second_candidate['assessment']==second['assessment']
  child=named.resolve_parent(model_root,second['model_id'])
  assert child['lineage']['parent_model_id']==first['model_id']
  assert len(child['lineage']['samples'])==len(saved)+1
  assert child['lineage']['split_history'][:1]==parent['lineage']['split_history']
  assert len(child['lineage']['split_history'])==2
  assert set(parent['lineage']['training_groups'])<=set(child['lineage']['training_groups'])
  assert all(row in child['lineage']['training_exposure'] for row in parent['lineage']['training_exposure'])
  revised=[s for s in child['lineage']['samples'].values() if s['source']['id']==corrected['id']]
  assert len(revised)==1 and revised[0]['label']=='negative' and revised[0]['source']['revision']==2
  assert passes[1]['source_checkpoint_sha256']==parent_hash
  assert trainer.sha256_file(parent['weights'])==parent_hash
  assert (model_root/first['model_id']/'manifest.json').read_bytes()==parent_manifest
  assert trainer.sha256_file(model_root/first['model_id']/'model.onnx')==parent_onnx_hash
  assert second['name']=='Synthetic confirmed roads continuation'
  for result in (first,second):
   assert {p.name for p in (model_root/result['model_id']).iterdir()}=={'model.onnx','manifest.json'}
   with zipfile.ZipFile(io.BytesIO(models.export_model(model_root,result['model_id']))) as portable:
    assert set(portable.namelist())=={'model.onnx','manifest.json'}
  second_inference=inference_evidence(second,'second')
  return dict(scope='Actual one-epoch CPU fine tuning twice through findings_training.run; synthetic mechanical coverage only.',
   additional_epochs=2,initial_examples=len(saved),cumulative_examples=len(child['lineage']['samples']),
   source_videos=2,first_model_id=first['model_id'],second_model_id=second['model_id'],
   first_name=first['name'],second_name=second['name'],parent_model_id=child['lineage']['parent_model_id'],
   first_source_job_deleted=True,original_evidence_deleted=True,source_video_required=False,
   continued_without_configured_base=True,parent_checkpoint_sha256=parent_hash,
   first_inference=first_inference,second_inference=second_inference,
   corrected_example_id=corrected['id'],corrected_revision=2,new_example_id=added['id'],
   split_history_entries=2,prior_training_exposure_preserved=True,parent_model_unchanged=True,
   mask_accepted=False,selection_mode='review',accuracy_guarantee=False,
   first_assessment=first['assessment'],second_assessment=second['assessment'],training_passes=passes)
 finally:
  if previous_weights is None:os.environ.pop('OPENSCRUB_TRAIN_WEIGHTS',None)
  else:os.environ['OPENSCRUB_TRAIN_WEIGHTS']=previous_weights


parser=argparse.ArgumentParser(description='Real synthetic CPU training/export/rescan/render smoke; not CUDA or real-footage accuracy')
parser.add_argument('--checkpoint',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
options=parser.parse_args()
root=options.output.resolve();root.mkdir(parents=True,exist_ok=True)
data=root/'dataset';records=[]
rng=np.random.default_rng(433)
for split,count in [('train',14),('val',6)]:
 (data/'images'/split).mkdir(parents=True,exist_ok=True)
 (data/'labels'/split).mkdir(parents=True,exist_ok=True)
 for i in range(count):
  negative=i>=count-2
  image=rng.integers(0,220,(128,128,3),dtype=np.uint8)
  points=np.array([[.16,.32],[.80,.29],[.84,.63],[.15,.66]])
  if not negative:
   dx,dy=rng.uniform(-.08,.08,2); points+=np.array([dx,dy])
   cv2.fillPoly(image,[(points*128).astype(np.int32)],(235,238,240))
   cv2.putText(image,str(i)+' AB',(int(27+dx*128),int(68+dy*128)),cv2.FONT_HERSHEY_SIMPLEX,.45,(10,10,10),1)
  name=f'{split}-{i}'
  cv2.imwrite(str(data/'images'/split/(name+'.png')),image)
  (data/'labels'/split/(name+'.txt')).write_text('' if negative else '0 '+' '.join(map(str,points.ravel()))+'\n')
  records.append(dict(image=f'images/{split}/{name}.png',
   label='negative' if negative else 'positive',
   quality='human_hard_negative' if negative else 'human_quad',
   split=split,job=name,track=0,detection_index=i,baseline_box=[.01,.12,.99,.9]))
(data/'manifest.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in records))
(data/'data.yaml').write_text('path: '+str(data)+'\ntrain: images/train\nval: images/val\nnames:\n  0: plate\n')
weights=options.checkpoint.resolve()
original=YOLO(str(weights)).model.state_dict()['model.0.conv.weight'].clone()
torch.set_num_threads(2)
# Explicit CPU adapter for a mechanical test only; production remains CUDA gated.
trainer._cuda_info=lambda device:{'torch':torch.__version__,'cuda':None,'gpu':'CPU mechanical smoke only'}
args=argparse.Namespace(dataset=data,weights=weights,versions_dir=root/'versions',device='cpu',
 accept_ultralytics_license=True,epochs=40,batch=4,imgsz=128,workers=0,patience=0,seed=42,
 min_mask_map50=0.,min_train_positive=12,min_val_positive=4,min_negative_per_split=1)
report=trainer.validate_dataset(data)
meta=trainer.train(args,report)
folder=args.versions_dir/meta['version']
learned=YOLO(str(folder/'weights.pt')).model.state_dict()['model.0.conv.weight']
difference=float((learned-original).abs().sum())
assert difference>0,'training did not update shared backbone weights'
model=vl.CropRefiner(folder/'model.onnx',providers=['CPUExecutionProvider'])
image=cv2.imread(str(data/records[0]['image']))
mask,score=model.predict(image)
evidence=dict(version=meta['version'],training_device='cpu',epochs=40,
 backbone_weight_change_L1=difference,onnx_calls=model.calls,score=score,
 mask_present=mask is not None,validation=meta['validation'],
 scope='Real synthetic CPU training and ONNX execution; not user-footage quality or CUDA validation.')


import learning_session as ls
import openscrub
from copy import deepcopy

gate=ls.calibrate(model,data)
video=root/'synthetic.avi'
writer=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*'FFV1'),10,(128,128))
assert writer.isOpened()
for record in records:writer.write(cv2.imread(str(data/record['image'])))
writer.release()
class Proposals:
    INPUT=640
    def __init__(self,*a,**kw):pass
    def available(self):return True
    def find(self,*a,**kw):return [(1,15,127,116,.95)]
class Quiet(openscrub.Callbacks):
    def log(self,message):print(message,flush=True)
p=openscrub.build_parser()
scan_args=openscrub._prep_args(p.parse_args([str(video),'--categories','plate',
    '--no-backtrack','--scroll-track','off','--encoder','x264']),p)
scan_args.plate_learning_exact=True
old_detector=openscrub.PlateDetector
try:
    openscrub.PlateDetector=Proposals
    state=openscrub.run_scan(scan_args,Quiet())
finally:
    openscrub.PlateDetector=old_detector
assert len(state['cum'])==len(records)
raw=root/'raw-report.json';openscrub.write_report(str(raw),scan_args,state)
doc=json.loads(raw.read_text())
old=deepcopy(doc)
positive=deepcopy(next(r for r in doc['detections'] if r['frame_index']==0))
negative=deepcopy(next(r for r in doc['detections'] if r['frame_index']==13))
pts=np.asarray([float(v) for v in (data/'labels/train/train-0.txt').read_text().split()[1:]]).reshape(4,2)*128
b=positive['cbox']
positive.update(verified_label='plate',track=77,plate_quad=((pts-b[:2])/[b[2]-b[0],b[3]-b[1]]).tolist())
negative.update(verified_label='not_plate',enabled=False,track=88)
old['detections']=[negative,positive]  # deliberately different order/track IDs
constraints=vl.capture_constraints(old)
refined,stats=vl.refine_report(video,doc,model,threshold=gate['threshold'])
corrected=vl.apply_constraints(refined,constraints)
seed=next(r for r in corrected['detections'] if r['frame_index']==0)
assert np.allclose(seed['plate_quad'],positive['plate_quad'])
assert all(not r['enabled'] for r in corrected['detections'] if r['frame_index']==13)
assert stats['model_calls']==len(records) and stats['refined']>0
report_path=root/'learned-report.json';ls.atomic_json(report_path,corrected)
output=root/'redacted.mp4'
render_args=openscrub._prep_args(p.parse_args([str(video),'--from-report',str(report_path),
    '--categories','plate','--mode','box','--pad','0','--encoder','x264','-o',str(output)]),p)
result=openscrub.run_pipeline(render_args,Quiet())
assert Path(result['output']).is_file()
cap=cv2.VideoCapture(str(output));frames=[]
while True:
    ok,frame=cap.read()
    if not ok:break
    frames.append(frame)
cap.release();assert len(frames)==len(records)
x,y=np.rint(pts.mean(axis=0)).astype(int)
assert frames[0][y,x].max()<20,'human-corrected plate was not redacted'
original_negative=cv2.imread(str(data/records[13]['image']))
# H.264 chroma subsampling changes RGB noise even without redaction; compare luma.
assert float(np.mean(np.abs(cv2.cvtColor(frames[13],cv2.COLOR_BGR2GRAY).astype(float)-cv2.cvtColor(original_negative,cv2.COLOR_BGR2GRAY))))<10,'rejected finding was redacted'
evidence.update(coverage_gate=gate,inference=stats,rendered_frames=len(frames),
    human_positive_preserved=True,human_negative_preserved=True,
    original_proposal_detector='deterministic fixture; actual scan loop and renderer')
evidence['named_confirmed_workflow']=named_training_smoke(root,folder/'weights.pt')
(root/'result.json').write_text(json.dumps(evidence,indent=2))
print('REAL_LEARNING_SMOKE',json.dumps(evidence),flush=True)
