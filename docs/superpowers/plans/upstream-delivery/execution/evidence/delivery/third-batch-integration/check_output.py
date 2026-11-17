from pathlib import Path
import json,cv2
art=Path('/tmp/openscrub-task652');r=json.loads((art/'browser-results.json').read_text());doc=json.loads(Path(r['reportPath']).read_text());cap=cv2.VideoCapture(r['output']);frames=0;stats={str(i):[] for i in range(14)}
while True:
 ok,frame=cap.read()
 if not ok:break
 for i,row in enumerate(doc['detections']):
  x1,y1,x2,y2=row['cbox'];x=int((x1+x2)/2);y=int((y1+y2)/2);mean=float(frame[y-1:y+2,x-1:x+2].mean());stats[str(i)].append(mean)
  assert mean<25 if row['enabled'] else mean>130,(frames,i,row['enabled'],mean)
 frames+=1
cap.release();assert frames==60
out={'frames':frames,'all_selected_kept_region_centers_every_frame':True,'rows':{k:{'min':min(v),'max':max(v)} for k,v in stats.items()}}
(art/'output-check.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
