from pathlib import Path
import json
from task9_isolation import configure
configure('decode-output')
import cv2,numpy as np
r=Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README/runtime/task9');f=next(x for x in json.loads((r/'evidence/fixtures-candidate.json').read_text()) if x['job']=='small');job=Path(f['dir']);video=job.parent.parent/'synthetic.mp4';saved=json.loads((r/'evidence/pre-render-verified.json').read_text())
def frame(path):
 c=cv2.VideoCapture(str(path));c.set(cv2.CAP_PROP_POS_MSEC,1500);ok,im=c.read();c.release();assert ok,path;return im
src=frame(video);out=frame(job/'output.mp4');results=[]
for name,rect,blur in [('kept-ordinary0',[20,20,34,39],False),('kept-hidden-member1',[70,20,80,38],False),('selected-moved-member2',[91,29,103,47],True),('selected-zone18',[20,320,34,339],True),('kept-zone19',[70,320,84,339],False),('additive-manual',[558,288,582,302],True),('unrelated',[605,320,625,340],False)]:
 x1,y1,x2,y2=rect;a=src[y1:y2,x1:x2];b=out[y1:y2,x1:x2];error=float(np.abs(a.astype(float)-b.astype(float)).mean());mean=float(b.mean())
 assert mean<6 if blur else error<7,(name,error,mean)
 results.append({'region':name,'blurred':blur,'mean_absolute_error':error,'output_mean':mean})
post=json.loads((job/'report.json').read_text());(r/'evidence/post-render-report.json').write_text(json.dumps(post,indent=2));cv2.imwrite(str(r/'evidence/decoded-original.png'),src);cv2.imwrite(str(r/'evidence/decoded-output.png'),out)
summary={'regions':results,'pre_render_rows':len(saved['detections']),'after_render_rows':len(post['detections']),'known_P06D_row_loss':len(post['detections'])<len(saved['detections']),'output_bytes':(job/'output.mp4').stat().st_size}
(r/'evidence/output-check.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))
