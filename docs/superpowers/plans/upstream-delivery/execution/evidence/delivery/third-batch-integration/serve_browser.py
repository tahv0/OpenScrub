import json,threading,time
from types import SimpleNamespace
import openscrub
from pathlib import Path
import cv2,numpy as np
import baseline_isolation
baseline_isolation.ROOT=Path('/tmp/openscrub-task652')
web=baseline_isolation.configure('browser-runtime-final')
assert web.__file__=='/home/tahv0/.codex/worktrees/c832/OpenScrub/openscrub_web.py'
ids={}
publications=[]
for name in ['alpha','beta']:
 job=web.new_job('',{'encoder':'x264','mode':'box','pad':0},'synthetic-'+name+'.avi')
 video=Path(job['dir'])/'input.avi'
 writer=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*'MJPG'),30,(160,96))
 assert writer.isOpened()
 for _ in range(60):writer.write(np.full((96,160,3),180,np.uint8))
 writer.release()
 job.update(video=str(video),phase='done')
 output=Path(job['dir'])/'output.mp4';output.write_bytes(bytes(range(256))*16384)
 job['output']=str(output)
 doc={'provenance':{'input':str(video),'settings':{}},'render_state':{'fps':30,'cum':[[0,0]]*60,'bands':[[0,0]]*60},'detections':[{'t_start':0,'t_end':1.9,'last_seen':0,'cbox':[10+50*i,10,40+50*i,50],'aoff':[0,0],'category':'email','text':'synthetic-'+str(i)+'@example.invalid','confidence':1,'enabled':True} for i in range(2)],'audio_transcript':[[0,1,'synthetic']],'audio_suggestions':[],'future_top':{'preserved':True}}
 (Path(job['dir'])/'report.json').write_text(json.dumps(doc))
 web.WebCallbacks(job).scan_frame(np.full((96,160,3),180,np.uint8),0,2)
 ids[name]=job['id']
alpha=web.JOBS[ids['alpha']]
# Reuse the reviewed second-batch mixed raw fixture at an explicit imported-input boundary.
doc=json.loads(Path('/tmp/openscrub-task651/initial-report.json').read_text())
doc['provenance']['input']=alpha['video']
(Path(alpha['dir'])/'report.json').write_text(json.dumps(doc,indent=1))
Path('/tmp/openscrub-task652/initial-report.json').write_text(json.dumps(doc))
alpha['phase']='done'
real=web.atomic_report
from flask import has_request_context
def publish(path,doc):
 saving=has_request_context() and web.request.path.endswith('/detections')
 event={'saving':saving,'complete':False,'failed':False};publications.append(event)
 if saving and web.request.headers.get('X-Task652-Fail')=='yes':
  event['failed']=True
  Path('/tmp/openscrub-task652/publications.json').write_text(json.dumps(publications))
  raise OSError('injected report publication failure')
 result=real(path,doc);event['complete']=True
 Path('/tmp/openscrub-task652/publications.json').write_text(json.dumps(publications))
 return result
web.atomic_report=publish
web.app.view_functions['update_check']=lambda:web.jsonify({'current':web.openscrub.VERSION,'update_available':False})
Path('/tmp/openscrub-task652/browser-jobs.json').write_text(json.dumps(ids))
Path('/tmp/openscrub-task652/browser-paths.json').write_text(json.dumps({k:v['dir'] for k,v in web.JOBS.items()}))
threading.Thread(target=web.worker,daemon=True).start()
from cheroot.wsgi import Server
server=Server(('127.0.0.1',18652),web.app,numthreads=16)
print('Task652 browser server ready',flush=True)
server.start()
