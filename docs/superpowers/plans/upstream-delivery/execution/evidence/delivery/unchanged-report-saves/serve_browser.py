import json, threading
from pathlib import Path
import cv2, numpy as np
from baseline_isolation import configure
web=configure('/tmp/openscrub-task631/browser-runtime')
assert web.__file__ == '/home/tahv0/.codex/worktrees/c832/OpenScrub/openscrub_web.py'
job=web.new_job('',{},'synthetic.avi'); job['phase']='review'
video=Path(job['dir'])/'input.avi'
writer=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*'MJPG'),30,(96,64))
assert writer.isOpened()
for _ in range(30): writer.write(np.full((64,96,3),180,dtype=np.uint8))
writer.release();job['video']=str(video)
job['options'].update(encoder='x264',mode='box',pad=0)
doc={'provenance':{'input':str(video),'settings':{}},'render_state':{'fps':30,'cum':[[0,0]]*30,'bands':[[0,0]]*30},
 'detections':[dict(t_start=0.,t_end=.8,cbox=[10.,10.,30.,30.],category='manual',text='synthetic',confidence=1.,aoff=[0,0],last_seen=.5,enabled=False)],
 'custom':{'preserved':True}}
path=Path(job['dir'])/'report.json';path.write_text(json.dumps(doc))
Path('/tmp/openscrub-task631/browser-job.json').write_text(json.dumps({'id':job['id'],'path':str(path)}))
real=web.atomic_report
events=[]
def publish(path,doc):
 from flask import has_request_context, request
 saving=has_request_context() and request.path.endswith('/detections')
 events.append({'save_route':saving,'failed':saving and Path('/tmp/openscrub-task631/fail-next').exists()})
 Path('/tmp/openscrub-task631/browser-publications.json').write_text(json.dumps(events))
 if saving and Path('/tmp/openscrub-task631/fail-next').exists():
  Path('/tmp/openscrub-task631/fail-next').unlink()
  raise OSError('injected real save publication failure')
 result=real(path,doc)
 events[-1]['complete']=True
 Path('/tmp/openscrub-task631/browser-publications.json').write_text(json.dumps(events))
 return result
web.atomic_report=publish
Path('/tmp/openscrub-task631/browser-publications.json').write_text('[]')
web.app.view_functions['update_check']=lambda:web.jsonify({'current':web.openscrub.VERSION,'update_available':False})
threading.Thread(target=web.worker,daemon=True).start()
from cheroot.wsgi import Server
print('ready',flush=True)
Server(('127.0.0.1',18463),web.app,numthreads=8).start()
