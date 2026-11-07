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
(root/'result.json').write_text(json.dumps(evidence,indent=2))
print('REAL_LEARNING_SMOKE',json.dumps(evidence),flush=True)
