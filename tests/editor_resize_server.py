"""Synthetic real-route server; imports only the explicitly selected source tree."""
import sys, os, json, hashlib, subprocess
from pathlib import Path
source=Path(sys.argv[1]).resolve()
runtime=Path(sys.argv[2]).resolve()
port=int(sys.argv[3])
assert Path.cwd()==source
label='candidate';sha=os.environ.get('OPENSCRUB_TEST_SOURCE_REVISION','unspecified; see web_sha256')
sys.path.insert(0,str(source))
os.environ['OPENSCRUB_NO_AUTOFETCH']='1'
os.environ['PYTHONDONTWRITEBYTECODE']='1'
import numpy as np, cv2
import openscrub
runtime.mkdir(parents=True,exist_ok=True)
models=runtime/'models'; models.mkdir(exist_ok=True)
openscrub._model_dir=lambda:str(models)
def deny_fetch(*args,**kwargs): raise RuntimeError('Resize QA forbids model downloads')
openscrub._fetch_model=deny_fetch
import openscrub_web as web
assert Path(web.__file__).resolve()==source/'openscrub_web.py'
assert Path(openscrub.__file__).resolve()==source/'openscrub.py'
if os.environ.get('OPENSCRUB_HDR_PROOF_WEB_FIXTURE')=='1':
 # Keep real multipart admission while leaving scans queued for this UI test.
 web.enqueue=lambda *args,**kwargs:None
web._data_root=lambda:str(runtime)
for name in ('JOBS_DIR','ZONES_PATH','MODEL_SELECT_PATH','CERT_DIR','WEB_SETTINGS_PATH','CUSTOM_CATS_PATH'):
 setattr(web,name,str(runtime/Path(getattr(web,name)).name))
for name in ('CUSTOM_CERT','CUSTOM_KEY','AUTO_CERT','AUTO_KEY'):
 setattr(web,name,str(Path(web.CERT_DIR)/Path(getattr(web,name)).name))
Path(web.JOBS_DIR).mkdir(exist_ok=True)
video=runtime/'source-mp4v.mp4'
frame=np.full((360,640,3),235,np.uint8)
# Content cbox [120,80,320,220] plus source offset [20,12].
cv2.rectangle(frame,(140,92),(339,231),(255,255,0),-1)
cv2.rectangle(frame,(140,92),(340,232),(0,200,0),2)
for x,y in ((140,92),(340,92),(140,232),(340,232)):
 cv2.circle(frame,(x,y),4,(255,0,0),-1)
cv2.putText(frame,'SYNTHETIC 640x360',(350,45),cv2.FONT_HERSHEY_SIMPLEX,.55,(20,20,20),1)
cv2.putText(frame,'SOURCE TARGET 140,92 - 340,232',(80,270),cv2.FONT_HERSHEY_SIMPLEX,.65,(20,20,20),1)
v=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*'mp4v'),10,(640,360))
assert v.isOpened()
for _ in range(20):v.write(frame)
v.release();cv2.imwrite(str(runtime/'source.png'),frame)
encoded=runtime/'source.mp4'
subprocess.run(['ffmpeg','-nostdin','-y','-loglevel','error','-i',str(video),'-c:v','libx264','-pix_fmt','yuv420p',str(encoded)],check=True)
video=encoded
job=web.new_job(str(video),{'categories':'email','mode':'box','pad':0},'synthetic-resize.mp4')
web.JOBS.pop(job['id']);new_dir=Path(web.JOBS_DIR)/'resize';os.rename(job['dir'],new_dir);job['dir']=str(new_dir);job['id']='resize';web.JOBS['resize']=job
report={'provenance':{'input':str(video),'settings':{'pad':0,'mode':'box'}},
 'render_state':{'fps':10,'cum':[[20,12]]*20,'bands':[[0,0]]*20},
 'detections':[{'t_start':0,'t_end':2,'last_seen':0,'cbox':[120,80,320,220],
 'aoff':[0,0],'category':'name','text':'Synthetic rectangular target','confidence':1,'enabled':True}],
 'audio_redactions':[]}
Path(job['dir'],'report.json').write_text(json.dumps(report))
job['phase']='review'
other=web.new_job(str(video),{'categories':'email','mode':'box','pad':0},'synthetic-other.mp4')
web.JOBS.pop(other['id']);new_dir=Path(web.JOBS_DIR)/'other';os.rename(other['dir'],new_dir);other['dir']=str(new_dir);other['id']='other';web.JOBS['other']=other
Path(other['dir'],'report.json').write_text(json.dumps(report));other['phase']='review'
# Native SDR plate with its actual scan-input digest; no detector/model is run.
plate=web.new_job(str(video),{'categories':'plate','mode':'box','pad':0,'encoder':'x264'},'synthetic-plate.mp4')
web.JOBS.pop(plate['id']);new_dir=Path(web.JOBS_DIR)/'plate';os.rename(plate['dir'],new_dir)
plate.update(dir=str(new_dir),id='plate',phase='review');web.JOBS['plate']=plate
plate_report={'provenance':{'input':str(video),'input_sha256':hashlib.sha256(video.read_bytes()).hexdigest(),
 'settings':{'pad':0,'mode':'box'}},
 'render_state':{'fps':10,'cum':[[0,0]]*20,'bands':[[0,0]]*20},
 'detections':[{'t_start':0,'t_end':2,'last_seen':0,'cbox':[140,92,340,232],
 'aoff':[0,0],'category':'plate','text':'synthetic plate','confidence':1,'enabled':True,'opaque':{'keep':True}},
 {'t_start':0,'t_end':2,'last_seen':0,'cbox':[10,10,30,30],
 'aoff':[0,0],'category':'name','text':'other','confidence':1,'enabled':False}],
 'audio_redactions':[]}
Path(plate['dir'],'report.json').write_text(json.dumps(plate_report))
# Retained media: expected ordinals/PTS/pixels come from sequential native decode
# and FFprobe, independent of edit_sample and the embedded editor state.
manifest=os.environ.get('OPENSCRUB_EXACT_MEDIA')
if manifest:
 from fractions import Fraction
 values=json.loads(Path(manifest).read_text());oracles={}
 for key,fps,want in [('cfr24',24,4),('cfr5',5,9),('normalized',13,6)]:
  value=values[key];path=Path(value['path']);assert hashlib.sha256(path.read_bytes()).hexdigest()==value['sha256']
  probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_frames',
   '-show_entries','frame=pts:stream=time_base','-of','json',str(path)],timeout=15))
  pts=[Fraction(v['pts'])*Fraction(probe['streams'][0]['time_base']) for v in probe['frames']]
  capture=cv2.VideoCapture(str(path));frames=[]
  try:
   while True:
    ok,pixels=capture.read()
    if not ok:break
    frames.append(pixels)
  finally:capture.release()
  assert len(frames)==len(pts)
  selected=frames[want];marker=sum((int(selected[14,14+12*k,0])>128)<<k for k in range(6))
  oracles[key]=dict(input=value,index=want,pts=str(pts[want]),canonical=want/fps,marker=marker,
   shape=list(selected.shape),source_box=[20+2*want,30-want,80+2*want,70-want])
  fixture=web.new_job(str(path),{'categories':'email','mode':'box','pad':0},'exact-'+key+'.mp4')
  web.JOBS.pop(fixture['id']);fixture['id']=key;web.JOBS[key]=fixture
  row=dict(t_start=0,t_end=len(frames)/fps,last_seen=0,cbox=[20,30,80,70],aoff=[0,0],category='name',text='exact target',confidence=1,enabled=True)
  doc=dict(provenance=dict(input=str(path),vfr_normalized=key=='normalized',settings=dict(pad=0,mode='box')),
   render_state=dict(fps=fps,cum=[[2*i,-i] for i in range(len(frames))],bands=[[0,0]]*len(frames)),
   detections=[row,dict(row,text='disabled raw row',enabled=False,opaque={'kept':[1,2,3]})],audio_redactions=[])
  Path(fixture['dir'],'report.json').write_text(json.dumps(doc));fixture['phase']='review'
 (runtime/'media-oracles.json').write_text(json.dumps(oracles,indent=2))
# Deterministic engine fake only: real strict route, source decode, background
# ownership and atomic report append remain in use; no tracking-quality claim.
def deterministic_track(video,box,t_ref,t0,t1,**kwargs):
 seed=kwargs['strict_seed'];assert seed.index==round(t_ref*seed.fps)
 (runtime/'track-seed.json').write_text(json.dumps(dict(index=seed.index,canonical=seed.canonical_s,
  box=box,t_ref=t_ref,t0=t0,t1=t1,source_shape=list(seed.pixels.shape))))
 return [(t_ref,list(box),1.0)]
openscrub.track_manual_region=deterministic_track
class NoPersonModel:
 net=None;ort=None
openscrub.PersonDetector=lambda *a,**kw:NoPersonModel()
# Optional second process restores the exact report written by the first UI.
# Keep its real selected media path; generated startup fixtures never replace it.
reopened=None
if len(sys.argv)>4:
 saved_path=Path(sys.argv[4]);selected_id=sys.argv[5];saved=json.loads(saved_path.read_text())
 selected_job=web.JOBS[selected_id];selected_job['video']=saved['provenance']['input']
 Path(selected_job['dir'],'report.json').write_text(json.dumps(saved));selected_job['phase']='review'
 reopened=dict(report=str(saved_path),job=selected_id,video=selected_job['video'])
# Read-only network-independent replacement only for unrelated update metadata.
web.app.view_functions['update_check']=lambda:web.jsonify({'current':web.openscrub.VERSION,'update_available':False})
identity={'label':label,'sha':sha,'port':port,'cwd':os.getcwd(),'web_import':web.__file__,
 'engine_import':openscrub.__file__,'web_sha256':hashlib.sha256(Path(web.__file__).read_bytes()).hexdigest(),
 'runtime':str(runtime),'job_dir':job['dir'],'video':str(video),'pid':os.getpid(),
 'reopened':reopened,'python':sys.version,'opencv':cv2.__version__,'model_downloads':'forbidden','scan_started':False,'real_render_worker':True}
(runtime/'server-identity.json').write_text(json.dumps(identity,indent=2))
web.start_worker()
from cheroot.wsgi import Server
print(json.dumps(identity),flush=True)
server=Server(('127.0.0.1',port),web.app,numthreads=8)
try:server.start()
finally:server.stop()
