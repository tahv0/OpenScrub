import json
from pathlib import Path
import cv2,numpy as np
import baseline_isolation
baseline_isolation.ROOT=Path('/tmp/openscrub-task650')
web=baseline_isolation.configure('browser-runtime')
assert web.__file__=='/home/tahv0/.codex/worktrees/c832/OpenScrub/openscrub_web.py'
ids={}
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
real=web.atomic_report
def publish(path,doc):
 if web.has_request_context() and web.request.headers.get('X-Task650-Fail')=='yes':raise OSError('injected report publication failure')
 return real(path,doc)
# Flask exports has_request_context separately.
from flask import has_request_context
web.has_request_context=has_request_context
web.atomic_report=publish
web.app.view_functions['update_check']=lambda:web.jsonify({'current':web.openscrub.VERSION,'update_available':False})
Path('/tmp/openscrub-task650/browser-jobs.json').write_text(json.dumps(ids))
from cheroot.wsgi import Server
print('Task650 browser server ready',flush=True)
Server(('127.0.0.1',18650),web.app,numthreads=16).start()
