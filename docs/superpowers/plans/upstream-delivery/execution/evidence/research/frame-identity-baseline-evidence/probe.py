"""Pinned full-import, marked short-media frame identity research. No model fetch."""
from pathlib import Path
import os,sys,json,hashlib,subprocess,types,copy,shutil
ROOT=Path('/tmp/openscrub-frame-identity-baseline-20261117')
EVID=Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README/frame-identity-baseline-evidence')
RUNTIME=ROOT/'runtime'; RUNTIME.mkdir(exist_ok=True)
sys.path.insert(0,str(ROOT))
os.environ['OPENSCRUB_NO_AUTOFETCH']='1'
import cv2,numpy as np,openscrub
models=RUNTIME/'models';models.mkdir(exist_ok=True)
openscrub._model_dir=lambda:str(models)
def deny_fetch(*a,**k):raise RuntimeError('Research forbids model downloads')
openscrub._fetch_model=deny_fetch
import openscrub_web as web
assert Path(web.__file__).resolve()==ROOT/'openscrub_web.py'
assert Path(openscrub.__file__).resolve()==ROOT/'openscrub.py'
web._data_root=lambda:str(RUNTIME)
for name in ('JOBS_DIR','ZONES_PATH','MODEL_SELECT_PATH','CERT_DIR','WEB_SETTINGS_PATH','CUSTOM_CATS_PATH'):
 setattr(web,name,str(RUNTIME/Path(getattr(web,name)).name))
for name in ('CUSTOM_CERT','CUSTOM_KEY','AUTO_CERT','AUTO_KEY'):
 setattr(web,name,str(Path(web.CERT_DIR)/Path(getattr(web,name)).name))
Path(web.JOBS_DIR).mkdir(exist_ok=True)
def marker(frame):
 if frame is None:return None
 return sum((int(frame[14,14+12*k,0])>128)<<k for k in range(6))
def make_frame(i):
 a=np.full((180,320,3),45,np.uint8)
 for k in range(6):cv2.rectangle(a,(8+12*k,8),(19+12*k,20),(240,240,240) if i>>k&1 else (10,10,10),-1)
 cv2.putText(a,f'FRAME {i:02}',(100,28),cv2.FONT_HERSHEY_SIMPLEX,.6,(235,235,235),1)
 x=50+2*i;cv2.rectangle(a,(x,70),(x+40,110),(0,220,220),-1)
 cv2.line(a,(x,70),(x+40,110),(250,0,0),2)
 cv2.line(a,(x+40,70),(x,110),(0,250,0),2)
 return a
def create_clip(label,fps,n):
 raw=RUNTIME/(label+'.raw')
 raw.write_bytes(b''.join(make_frame(i).tobytes() for i in range(n)))
 path=RUNTIME/(label+'.mp4')
 cmd=['ffmpeg','-y','-loglevel','error','-f','rawvideo','-pixel_format','bgr24','-video_size','320x180','-framerate',str(fps),'-i',str(raw),'-c:v','libx264','-g',str(fps),'-pix_fmt','yuv420p',str(path)]
 subprocess.run(cmd,check=True);raw.unlink()
 return path,cmd
def install_job(label,path,fps,n,original=None):
 job=web.new_job(str(path),{'categories':'email','mode':'box','pad':0},'synthetic-'+label+'.mp4')
 web.JOBS.pop(job['id']);job['id']=label;web.JOBS[label]=job;job['phase']='review'
 report={'provenance':{'input':str(path),'original_input':str(original) if original else None,'vfr_normalized':bool(original),'settings':{'pad':0,'mode':'box'}},'render_state':{'fps':fps,'cum':[[2*i,0] for i in range(n)],'bands':[[0,0]]*n},'detections':[{'t_start':0,'t_end':n/fps,'last_seen':.2,'cbox':[50,70,90,110],'aoff':[0,0],'category':'name','text':'Synthetic moving target','confidence':1,'enabled':True}],'audio_redactions':[]}
 Path(job['dir'],'report.json').write_text(json.dumps(report));return job
COMMANDS=[]
for label,fps,n in [('cfr24',24,48),('cfr5',5,10)]:
 path,cmd=create_clip(label,fps,n);COMMANDS.append(cmd);install_job(label,path,fps,n)
output=RUNTIME/'cfr24-preview-output.mp4';shutil.copyfile(web.JOBS['cfr24']['video'],output);web.JOBS['cfr24']['output']=str(output)
# Short VFR from repeated marker PNGs with irregular durations; normalize via actual function.
seq=RUNTIME/'vfr-sequence';seq.mkdir(exist_ok=True)
durations=[.04,.12,.08,.04,.16,.04,.08,.12,.04,.08,.04,.12]
for i in range(len(durations)):cv2.imwrite(str(seq/f'{i}.png'),make_frame(i))
concat=seq/'concat.txt';concat.write_text(''.join(f"file '{i}.png'\nduration {dt}\n" for i,dt in enumerate(durations))+f"file '{len(durations)-1}.png'\n")
vfr=RUNTIME/'vfr.mp4';cmd=['ffmpeg','-y','-loglevel','error','-f','concat','-safe','0','-i',str(concat),'-fps_mode','vfr','-c:v','libx264','-pix_fmt','yuv420p',str(vfr)]
subprocess.run(cmd,check=True);COMMANDS.append(cmd)
logs=[]
args=types.SimpleNamespace(video=str(vfr),output=str(RUNTIME/'vfr-output.mp4'),encoder='x264',vfr='auto',no_vfr_fix=False)
cb=types.SimpleNamespace(log=logs.append,cancelled=lambda:False)
input_probe=openscrub.probe_vfr(str(vfr));openscrub.normalize_vfr(args,cb)
cap=cv2.VideoCapture(args.video);fps=cap.get(cv2.CAP_PROP_FPS);n=int(cap.get(cv2.CAP_PROP_FRAME_COUNT));cap.release()
normalized_job=install_job('normalized',args.video,fps,n,original=vfr)
# Geometry follows actual marked pixels, including resampling duplicates.
cap=cv2.VideoCapture(args.video); normalized_markers=[]
while True:
 ok,fr=cap.read()
 if not ok:break
 normalized_markers.append(marker(fr))
cap.release()
p=Path(normalized_job['dir'],'report.json');doc=json.loads(p.read_text())
doc['render_state']['cum']=[[2*i,0] for i in normalized_markers];p.write_text(json.dumps(doc))
normalization={'input_probe':input_probe,'args':vars(args),'logs':logs,'fps':fps,'n':n}
REAL_CAPTURE=cv2.VideoCapture
TRACES=[];FAIL_SCHEDULE=[]
class TraceCapture:
 def __init__(self,path):self.cap=REAL_CAPTURE(path);self.path=str(path);self.seeks=[];self.released=False;TRACES.append(self)
 def set(self,key,value):self.seeks.append({'property':int(key),'value':value});return self.cap.set(key,value)
 def get(self,key):return self.cap.get(key)
 def read(self):
  if FAIL_SCHEDULE:
   fail=FAIL_SCHEDULE.pop(0)
   if fail:
    self.seeks[-1]['read']={'injected_failure':True};return False,None
  ok,fr=self.cap.read()
  if self.seeks:self.seeks[-1]['read']={'ok':bool(ok),'marker':marker(fr) if ok else None}
  return ok,fr
 def release(self):self.released=True;self.cap.release()
cv2.VideoCapture=TraceCapture
# Independent sequential decoded pixels; never infer identity from seeks.
REFERENCES={}
for label,j in web.JOBS.items():
 c=REAL_CAPTURE(j['video']);frames=[]
 while True:
  ok,fr=c.read()
  if not ok:break
  frames.append(fr)
 c.release();REFERENCES[label]=frames
client=web.app.test_client()
def sample(label,t,src=None,fail=None,route='frame_at'):
 TRACES.clear();FAIL_SCHEDULE[:]=fail or []
 url=f'/api/jobs/{label}/{route}'+(f'?t={t}' if route in ('frame_at','boxes_at') else '')+(f'&src={src}' if src else '')
 r=client.get(url);img=cv2.imdecode(np.frombuffer(r.data,np.uint8),cv2.IMREAD_COLOR) if r.status_code==200 else None
 rs=web._load_job_report(web.JOBS[label])['render_state']
 box=client.get(f'/api/jobs/{label}/boxes_at?t={t}&all=1').json
 matching=[i for i,fr in enumerate(REFERENCES[label]) if cv2.imencode('.jpg',fr,[cv2.IMWRITE_JPEG_QUALITY,82])[1].tobytes()==r.data] if route=='frame_at' and r.status_code==200 else []
 result={'matching_sequential_source_indices':matching,'job':label,'url':url,'status':r.status_code,'content_type':r.content_type,'headers':dict(r.headers),'marker':marker(img) if route!='thumb/0' else None,'requested_time':t,'geometry_frame':min(int(t*rs['fps']),len(rs['cum'])-1),'boxes':box,'capture_traces':[{'path':c.path,'seeks':copy.deepcopy(c.seeks),'released':c.released} for c in TRACES],'schedule':fail or 'natural'}
 if route=='thumb/0' and r.status_code==200:
  matching_crops=[]
  doc=web._load_job_report(web.JOBS[label]);d=doc['detections'][0]
  for idx,reference in enumerate(REFERENCES[label]):
   ox,oy=rs['cum'][idx];pad=24;h,w=reference.shape[:2]
   x1=max(0,int(d['cbox'][0]+ox)-pad);y1=max(0,int(d['cbox'][1]+oy)-pad)
   x2=min(w,int(d['cbox'][2]+ox)+pad);y2=min(h,int(d['cbox'][3]+oy)+pad)
   crop=reference[y1:y2,x1:x2].copy()
   cv2.rectangle(crop,(pad,pad),(crop.shape[1]-pad,crop.shape[0]-pad),(0,0,255),2)
   if cv2.imencode('.jpg',crop,[cv2.IMWRITE_JPEG_QUALITY,80])[1].tobytes()==r.data:matching_crops.append(idx)
  result['matching_sequential_source_crops']=matching_crops
 if img is not None:cv2.imwrite(str(EVID/(label+'-'+route.replace('/','-')+'-'+str(t)+('-injected' if fail else '')+'.jpg')),img)
 return result
if __name__=='__main__':
 if len(sys.argv)>1 and sys.argv[1]=='serve':
  web.app.view_functions['update_check']=lambda:web.jsonify({'current':openscrub.VERSION,'update_available':False})
  from cheroot.wsgi import Server
  server=Server(('127.0.0.1',18571),web.app,numthreads=4)
  try:server.start()
  finally:server.stop()
 else:
  results={'source_sha':'e21ebdf6e3ee46e6c65050dc956a9a3459152269','imports':{'web':web.__file__,'engine':openscrub.__file__},'source_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ['openscrub.py','openscrub_web.py']},'opencv':cv2.__version__,'python':sys.version,'commands':COMMANDS,'normalization':normalization,'sequential_reference':{label:[{'index':i,'marker':marker(fr),'sha256_decoded':hashlib.sha256(fr.tobytes()).hexdigest()} for i,fr in enumerate(frames)] for label,frames in REFERENCES.items()},'samples':[]}
  for label,ts in [('cfr24',[0,.2,.9,1.9,2]),('cfr5',[0,.2,.9,1.8,1.9,2]),('normalized',[0,.2,.5,(n-1)/fps,n/fps])]:
   for t in ts:results['samples'].append(sample(label,t))
  for t in [.2,2]:results['samples'].append(sample('cfr24',t,src='output'))
  for route in ['detframe/0','thumb/0']:results['samples'].append(sample('cfr24',.2,route=route))
  for fail in [[True,False],[True,True,True,True]]:
   results['samples'].append(sample('cfr24',.9,fail=fail))
  for route in ['detframe/0','thumb/0']:
   Path(web.JOBS['cfr24']['dir'],'thumb2_0.jpg').unlink(missing_ok=True)
   results['samples'].append(sample('cfr24',.2,fail=[True,False],route=route))
  results['media']={}
  for label,j in web.JOBS.items():
   p=Path(j['video']);cmd=['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=codec_name,width,height,r_frame_rate,avg_frame_rate,time_base,nb_frames,duration','-of','json',str(p)]
   results['media'][label]={'path':str(p),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'probe':json.loads(subprocess.check_output(cmd)),'frames':json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_frames','-show_entries','frame=pts_time,best_effort_timestamp_time,pict_type','-of','json',str(p)]))}
  (EVID/'results.json').write_text(json.dumps(results,indent=2))
  print(json.dumps({'samples':[(s['job'],s['url'],s['status'],s['marker'],s['geometry_frame'],s['schedule']) for s in results['samples']],'normalization':normalization},indent=2))
