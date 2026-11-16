from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
import cv2
import numpy as np

worktree=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
sys.path.insert(0,str(worktree))
sys.path.insert(0,str(worktree/'benchmark'))
from dense_smoothing import load
before=load(Path('/tmp/openscrub-task111/before/openscrub.py'),'verify_before')
import openscrub as after
root=Path('/tmp/openscrub-task111')
results={}
rows_reference=None
frame_reference=None
for name,module in [('before',before),('after',after)]:
    dets=[module.Detection(t,t,(44,40,76,72),'face','synthetic',.95,dense=True,track=1,poly=()) for t in (6.,6.2,6.3)]
    returned=module.smooth_dense_tracks(dets,10,str(root/'marked.avi'))
    rows=[asdict(d) for d in dets]
    if rows_reference is None:
        rows_reference=rows
    assert rows==rows_reference
    args=module.build_parser().parse_args([str(root/'marked.avi')])
    assert (args.mode,args.pad,args.face_shape)==('blur',8,'ellipse')
    output=root/(name+'-default-masks.mp4')
    module.render(str(root/'marked.avi'),str(output),dets,[(0.,0.)]*130,[(0.,0.)]*130,10.,
                  pad=args.pad,mode=args.mode,preview=False,encoder='x264')
    cap=cv2.VideoCapture(str(output))
    decoded=[]
    try:
        while True:
            ok,frame=cap.read()
            if not ok:
                break
            decoded.append(frame)
    finally:
        cap.release()
    assert len(decoded)==130
    hashes=[hashlib.sha256(frame.tobytes()).hexdigest() for frame in decoded]
    if frame_reference is None:
        frame_reference=hashes
    assert hashes==frame_reference
    results[name]=dict(returned=returned,rows=len(rows),decoded_frames=len(decoded),
                       decoded_sha256=hashlib.sha256(''.join(hashes).encode()).hexdigest())
# A real Tesseract scan/report/default render through the complete engine.
source=root/'engine-ssn.mp4'
writer=cv2.VideoWriter(str(source),cv2.VideoWriter_fourcc(*'mp4v'),10,(640,360))
assert writer.isOpened()
frame=np.full((360,640,3),245,np.uint8)
cv2.putText(frame,'SSN: 123-45-6789',(40,180),cv2.FONT_HERSHEY_SIMPLEX,1.,(20,20,20),2)
for _ in range(20):
    writer.write(frame)
writer.release()
parser=after.build_parser()
args=after._prep_args(parser.parse_args([str(source),'--engine','tesseract','--categories','ssn',
    '--encoder','x264','--output',str(root/'engine-redacted.mp4'),'--report',str(root/'engine-report.json')]),parser)
after.run_pipeline(args)
report=json.loads((root/'engine-report.json').read_text())
assert any(d['category']=='ssn' for d in report['detections'])
cap=cv2.VideoCapture(str(root/'engine-redacted.mp4'))
try:
    count=int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
finally:
    cap.release()
assert count==20
results['pipeline']=dict(engine='tesseract',selected_categories='ssn',report_rows=len(report['detections']),decoded_frames=count)
(root/'evidence/runtime-results.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps(results,indent=2))
