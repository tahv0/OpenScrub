from pathlib import Path
import json,cv2,numpy as np
root=Path('/tmp/openscrub-task20');doc=json.loads((root/'saved-before-render.json').read_text());rp=Path((root/'report-path.txt').read_text());out=rp.parent/'output.mp4'
def frame(path):
 c=cv2.VideoCapture(str(path));c.set(cv2.CAP_PROP_POS_MSEC,1500);ok,f=c.read();c.release();assert ok;return f
src=frame(root/'synthetic.mp4');red=frame(out);results=[]
for i,d in enumerate(doc['detections']):
 x1,y1,x2,y2=d['cbox'];a=src[y1+3:y2-3,x1+3:x2-3];b=red[y1+3:y2-3,x1+3:x2-3]
 error=float(np.abs(a.astype(float)-b).mean());level=float(b.mean())
 if d['enabled']:assert level<6,(i,error,level)
 else:assert error<6,(i,error,level)
 results.append(dict(i=i,enabled=d['enabled'],mean_absolute_error=error,output_mean=level))
a=src[150:175,260:300];b=red[150:175,260:300];assert np.abs(a.astype(float)-b).mean()<6
cv2.imwrite(str(root/'decoded-original.png'),src);cv2.imwrite(str(root/'decoded-output.png'),red)
post=json.loads(rp.read_text());(root/'post-render-report.json').write_text(json.dumps(post,indent=2))
summary={'regions':results,'unrelated_region_unchanged':True,'before_rows':len(doc['detections']),'after_rows':len(post['detections']),'known_P06D_disabled_row_loss_observed':len(post['detections'])<len(doc['detections'])}
(root/'output-check.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))
