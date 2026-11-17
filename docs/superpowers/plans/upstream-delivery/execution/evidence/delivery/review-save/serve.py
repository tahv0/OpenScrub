import sys, json, shutil
from pathlib import Path
import numpy as np
import cv2
import baseline_isolation
baseline_isolation.ROOT=Path('/tmp/openscrub-task71')
web=baseline_isolation.configure('runtime')
root=Path('/tmp/openscrub-task71')
video=str(root/'synthetic-input.mp4')
v=cv2.VideoWriter(video,cv2.VideoWriter_fourcc(*'mp4v'),10,(640,360))
frame=np.full((360,640,3),235,np.uint8)
for y in range(40,200,8):
 for x in range(30,250,8):
  if (x+y)//8%2:frame[y:y+8,x:x+8]=20
cv2.putText(frame,'SYNTHETIC QA',(285,90),cv2.FONT_HERSHEY_SIMPLEX,0.7,(30,30,30),2)
for _ in range(20):v.write(frame)
v.release()
for name in ('alpha','beta'):
 job=web.new_job(video,{'categories':'email','engine':'tesseract','device':'cpu','encoder':'x264','mode':'box','no_ner':True,'no_memory':True,'pad':0},'synthetic-'+name+'.mp4')
 web.JOBS.pop(job['id']);job['id']=name;web.JOBS[name]=job
 args=web.build_args(job)
 state=web.openscrub.run_scan(args,web.WebCallbacks(job))
 web.openscrub.write_report(str(Path(job['dir'])/'report.json'),args,state)
 path=Path(job['dir'])/'report.json';doc=json.loads(path.read_text())
 doc['detections']=[{'t_start':0,'t_end':2,'last_seen':0,'cbox':[30,40,130,140],'aoff':[0,0],'category':'name','text':'Synthetic QA','confidence':1,'enabled':True},
 {'t_start':0,'t_end':2,'last_seen':0,'cbox':[150,40,250,140],'aoff':[0,0],'category':'name','text':'Synthetic Other','confidence':1,'enabled':True}]
 doc['audio_redactions']=[{'t0':0,'t1':0.3,'mode':'mute'}]
 path.write_text(json.dumps(doc));job['phase']='review'
web.app.view_functions['update_check']=lambda:web.jsonify({'current':web.openscrub.VERSION,'update_available':False})
web.start_worker()
from cheroot.wsgi import Server
print('Task71 synthetic QA http://127.0.0.1:18487',flush=True)
Server(('127.0.0.1',18487),web.app,numthreads=16).start()
