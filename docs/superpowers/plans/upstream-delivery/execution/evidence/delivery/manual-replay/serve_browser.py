import json
from pathlib import Path
import cv2, numpy as np
from baseline_isolation import configure
web=configure('/tmp/openscrub-task72/browser-runtime')
identities={}
for identity in ['ack','lost']:
    job=web.new_job('',{},'synthetic.avi'); job['phase']='review'; identities[identity]=job['id']
    video=Path(job['dir'])/'input.avi'
    writer=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*'MJPG'),30,(160,120))
    for _ in range(180):writer.write(np.full((120,160,3),180,dtype=np.uint8))
    writer.release();job['video']=str(video)
    doc={'provenance':{'input':str(video),'settings':{}},'render_state':{'fps':30,'cum':[[0,0]]*180,'bands':[[0,0]]*180},'detections':[], 'custom':{'preserved':True}}
    (Path(job['dir'])/'report.json').write_text(json.dumps(doc))
Path('/tmp/openscrub-task72/browser-jobs.json').write_text(json.dumps(identities))
web.app.view_functions['update_check']=lambda:web.jsonify({'current':web.openscrub.VERSION,'update_available':False})
from cheroot.wsgi import Server
print('ready',flush=True)
Server(('127.0.0.1',18472),web.app,numthreads=8).start()
