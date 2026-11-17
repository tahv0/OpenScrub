from pathlib import Path
import sys,json,threading,time,os
ROOT=Path('/tmp/openscrub-task20');SOURCE=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
sys.path.insert(0,str(SOURCE))
from baseline_isolation import configure
w=configure('task20-bootstrap')
data=ROOT/'runtime';data.mkdir(exist_ok=True)
w._data_root=lambda:str(data)
for name in ('JOBS_DIR','ZONES_PATH','MODEL_SELECT_PATH','CERT_DIR','WEB_SETTINGS_PATH','CUSTOM_CATS_PATH'):
 setattr(w,name,str(data/Path(getattr(w,name)).name))
for name in ('CUSTOM_CERT','CUSTOM_KEY','AUTO_CERT','AUTO_KEY'):
 setattr(w,name,str(Path(w.CERT_DIR)/Path(getattr(w,name)).name))
Path(w.JOBS_DIR).mkdir(exist_ok=True)
import cv2,numpy as np
video=ROOT/'synthetic.mp4';out=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*'mp4v'),10,(320,180))
y,x=np.indices((180,320));checker=(((x//2+y//2)%2)*180+30).astype('uint8');frame=np.stack([checker,np.roll(checker,1,0),checker],axis=2)
for _ in range(40):out.write(frame)
out.release()
doc=json.loads((ROOT/'synthetic-report.json').read_text())
for i,d in enumerate(doc['detections']):
 x=12+(i%7)*42;y=20+(i//7)*70
 d.update(cbox=[x,y,x+24,y+30],t_start=0,t_end=4,last_seen=0)
doc['render_state']['bands']=[[0,0] for _ in range(40)]
doc.update(audio_redactions=[{'t0':.5,'t1':.7,'mode':'mute'}],provenance={'input':str(video),'synthetic':'task20'},settings={})
(ROOT/'initial-report.json').write_text(json.dumps(doc,indent=2))
job=w.new_job(str(video),{'mode':'box','pad':0,'face_expand':0,'face_shape':'rect','engine':'tesseract','device':'cpu','encoder':'x264','categories':['face','person','plate','email']},'Synthetic output choices')
w.JOBS.pop(job['id']);job.update(id='qa',phase='review');w.JOBS['qa']=job
report=Path(job['dir'])/'report.json';report.write_text(json.dumps(doc,indent=2));(ROOT/'report-path.txt').write_text(str(report))
w.start_worker()
w.app.run(host='127.0.0.1',port=18520,debug=False,use_reloader=False,threaded=True)
