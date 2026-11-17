"""Synthetic real-route server; imports only the explicit complete pinned export."""
import sys, os, json, hashlib
from pathlib import Path
ROOT=Path('/tmp/openscrub-editor-resize-baseline-20261117')
label, sha, port=sys.argv[1],sys.argv[2],int(sys.argv[3])
source=ROOT/label
sys.path.insert(0,str(source))
os.environ['OPENSCRUB_NO_AUTOFETCH']='1'
os.environ['PYTHONDONTWRITEBYTECODE']='1'
import numpy as np, cv2
import openscrub
runtime=ROOT/'runtime'/label
runtime.mkdir(parents=True,exist_ok=True)
models=runtime/'models'; models.mkdir(exist_ok=True)
openscrub._model_dir=lambda:str(models)
def deny_fetch(*args,**kwargs): raise RuntimeError('Research forbids model downloads')
openscrub._fetch_model=deny_fetch
import openscrub_web as web
assert Path(web.__file__).resolve()==source/'openscrub_web.py'
assert Path(openscrub.__file__).resolve()==source/'openscrub.py'
web._data_root=lambda:str(runtime)
for name in ('JOBS_DIR','ZONES_PATH','MODEL_SELECT_PATH','CERT_DIR','WEB_SETTINGS_PATH','CUSTOM_CATS_PATH'):
 setattr(web,name,str(runtime/Path(getattr(web,name)).name))
for name in ('CUSTOM_CERT','CUSTOM_KEY','AUTO_CERT','AUTO_KEY'):
 setattr(web,name,str(Path(web.CERT_DIR)/Path(getattr(web,name)).name))
Path(web.JOBS_DIR).mkdir(exist_ok=True)
video=runtime/'source.mp4'
frame=np.full((360,640,3),235,np.uint8)
# Detection target: corners at source coordinates (120,80), (320,220).
cv2.rectangle(frame,(120,80),(319,219),(255,255,0),-1)
cv2.rectangle(frame,(120,80),(320,220),(0,200,0),2)
for x,y in ((120,80),(320,80),(120,220),(320,220)):
 cv2.circle(frame,(x,y),4,(255,0,0),-1)
cv2.putText(frame,'SYNTHETIC 640x360',(350,45),cv2.FONT_HERSHEY_SIMPLEX,.55,(20,20,20),1)
cv2.putText(frame,'TARGET 120,80 - 320,220',(80,270),cv2.FONT_HERSHEY_SIMPLEX,.65,(20,20,20),1)
v=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*'mp4v'),10,(640,360))
assert v.isOpened()
for _ in range(20):v.write(frame)
v.release();cv2.imwrite(str(runtime/'source.png'),frame)
job=web.new_job(str(video),{'categories':'email','mode':'box','pad':0},'synthetic-resize.mp4')
web.JOBS.pop(job['id']);job['id']='resize';web.JOBS['resize']=job
report={'provenance':{'input':str(video),'settings':{'pad':0,'mode':'box'}},
 'render_state':{'fps':10,'cum':[[0,0]]*20,'bands':[[0,0]]*20},
 'detections':[{'t_start':0,'t_end':2,'last_seen':0,'cbox':[120,80,320,220],
 'aoff':[0,0],'category':'name','text':'Synthetic rectangular target','confidence':1,'enabled':True}],
 'audio_redactions':[]}
Path(job['dir'],'report.json').write_text(json.dumps(report))
job['phase']='review'
# Read-only network-independent replacement only for unrelated update metadata.
web.app.view_functions['update_check']=lambda:web.jsonify({'current':web.openscrub.VERSION,'update_available':False})
identity={'label':label,'sha':sha,'port':port,'cwd':os.getcwd(),'web_import':web.__file__,
 'engine_import':openscrub.__file__,'web_sha256':hashlib.sha256(Path(web.__file__).read_bytes()).hexdigest(),
 'runtime':str(runtime),'job_dir':job['dir'],'video':str(video),'pid':os.getpid(),
 'python':sys.version,'opencv':cv2.__version__,'model_downloads':'forbidden','scan_or_render_started':False}
(ROOT/(label+'-server-identity.json')).write_text(json.dumps(identity,indent=2))
from cheroot.wsgi import Server
print(json.dumps(identity),flush=True)
server=Server(('127.0.0.1',port),web.app,numthreads=8)
try:server.start()
finally:server.stop()
