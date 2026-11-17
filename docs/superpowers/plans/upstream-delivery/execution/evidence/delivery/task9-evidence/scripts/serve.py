"""Actual source Flask routes; only test gates/instrumentation surround them."""
from pathlib import Path
import argparse,hashlib,json,sys,threading,time,os,subprocess
ROOT=Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README/runtime/task9')
p=argparse.ArgumentParser();p.add_argument('--base',action='store_true');p.add_argument('--counts',action='store_true');p.add_argument('--port',type=int,default=18509);opts=p.parse_args()
from task9_isolation import configure
w=configure('server-counts' if opts.counts else 'server-base' if opts.base else 'server-candidate')
import openscrub as o,cv2,numpy as np
from flask import request,has_request_context
from cheroot.wsgi import Server
assert Path(w.__file__).resolve()==Path(os.environ['TASK9_SOURCE'])/'openscrub_web.py'
label='counts' if opts.counts else 'base' if opts.base else 'candidate';data=ROOT/'runtime'/('server-'+label)
video=data/'synthetic.mp4';out=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*'mp4v'),10,(640,360))
y,x=np.indices((360,640));checker=(((x//2+y//2)%2)*180+30).astype('uint8');frame=np.stack([checker,np.roll(checker,1,0),checker],axis=2)
for _ in range(40):out.write(frame)
out.release()
encoded=data/'browser-readable.mp4'
subprocess.run(['ffmpeg','-y','-loglevel','error','-i',str(video),'-c:v','libx264','-pix_fmt','yuv420p',str(encoded)],check=True)
encoded.replace(video)
image=data/'synthetic.jpg';assert cv2.imwrite(str(image),frame[:90,:120])
manifest=[]
for jid,count in ([('warm',3),('cold',3)] if opts.counts else [('small',12),('beta',3),('cold',3),('empty',0)]+([] if opts.base else [('large',1200)])):
 job=w.new_job(str(video),{'mode':'box','pad':0,'face_expand':0,'face_shape':'rect','engine':'tesseract','device':'cpu','encoder':'x264','categories':['face','person','plate','email','mrn']},'Synthetic '+jid)
 w.JOBS.pop(job['id']);job.update(id=jid,phase='review',progress=1);w.JOBS[jid]=job
 rows=[]
 for g in range(count):
  n=1 if g%2==0 else 2
  cat=['face','person','plate','email','mrn'][min(4,g*5//max(1,count))]
  for m in range(n):
   xx=15+(g%12)*50;yy=15+(g//12%5)*60
   text='ordinary '+str(g)+(' variable text wraps naturally in this card with extra meaningful detail'*(g%5==0))
   rows.append(o.Detection(.1+.01*m,3.8+.01*m,(xx,yy,xx+24,yy+30),cat,text,.8+.1*m,(0,0),dense=n>1,track=g if n>1 else -1,person=g if cat=='person' else -1))
 state={'fps':10.,'cum':[(0,0)]*40,'bands':[(0,0)]*40,'detections':rows,'input_sha256':hashlib.sha256(video.read_bytes()).hexdigest()}
 report=Path(job['dir'])/'report.json';o.write_report(str(report),o.build_parser().parse_args([str(video)]),state)
 doc=json.loads(report.read_text())
 if count>2:
  doc['detections'][1]['enabled']=False
  # Two independent zone rows; person/track match ordinary intentionally.
  for i in range(2):
   d=dict(doc['detections'][i]);d.update(zone_dropped=True,enabled=False,text='outside zone '+str(i),cbox=[15+i*50,315,39+i*50,345]);doc['detections'].append(d)
 doc['audio_redactions']=[{'t0':.5,'t1':.7,'mode':'mute'}]
 report.write_text(json.dumps(doc,indent=1));(ROOT/'evidence'/('initial-'+label+'-'+jid+'.json')).write_text(json.dumps(doc,indent=1))
 if jid!='cold':
  for i in range(len(doc['detections'])):
   target=Path(job['dir'])/('thumb2_%d.jpg'%i)
   if not target.exists():os.link(image,target)
 manifest.append({'job':jid,'groups':count,'rows':len(doc['detections']),'bytes':report.stat().st_size,'sha256':hashlib.sha256(report.read_bytes()).hexdigest(),'dir':job['dir']})
(ROOT/'evidence'/('fixtures-'+label+'.json')).write_text(json.dumps(manifest,indent=2))
w.app.view_functions['update_check']=lambda:w.jsonify({'current':o.VERSION,'update_available':False})
events=[];decodes=[];gates={};held=set();lock=threading.Lock();render_gate=threading.Event();render_gate.set();save_gate=threading.Event();save_gate.set();save_status=200
orig_capture=cv2.VideoCapture
class Capture:
 def __new__(cls,*a,**kw):
  decodes.append({'args':str(a),'time':time.monotonic(),'route':request.path if has_request_context() else None});return orig_capture(*a,**kw)
cv2.VideoCapture=Capture
orig_thumb=w.app.view_functions['job_thumb']
def thumb(jid,i):
 entry={'job':jid,'i':i,'cache_before':(Path(w.JOBS[jid]['dir'])/('thumb2_%d.jpg'%i)).exists(),'entered':time.monotonic()}
 gate=threading.Event()
 with lock:
  events.append(entry);token=len(events);gates[token]=gate;request.environ['task9_thumb_token']=token
  if jid not in held:gate.set()
 try:
  response=orig_thumb(jid,i);entry['production_done']=time.monotonic();entry['released']=gate.wait(25);entry['returned']=time.monotonic()
  response.call_on_close(lambda:entry.update(completed=time.monotonic()))
  return response
 finally:
  with lock:gates.pop(token,None)
w.app.view_functions['job_thumb']=thumb
orig_save=w.app.view_functions['job_save_detections'] if 'job_save_detections' in w.app.view_functions else None
# Use route discovery because endpoint names are kept from the actual source.
for rule in w.app.url_map.iter_rules():
 if rule.rule=='/api/jobs/<jid>/detections' and 'POST' in rule.methods:
  name=rule.endpoint;original=w.app.view_functions[name]
  def save(jid,_original=original):
   save_gate.wait(25)
   if save_status!=200:return w.jsonify({'error':'controlled save failure'}),save_status
   result=_original(jid)
   (ROOT/'evidence'/('saved-'+label+'-'+jid+'.json')).write_bytes((Path(w.JOBS[jid]['dir'])/'report.json').read_bytes())
   return result
  w.app.view_functions[name]=save
orig_render=w.app.view_functions['job_render']
def render(jid):
 
 if not render_gate.wait(25):return w.jsonify({'error':'test render gate expired'}),409
 return orig_render(jid)
w.app.view_functions['job_render']=render
@w.app.route('/__qa__/state')
def state():
 return w.jsonify({'events':events,'decodes':decodes,'held':list(held),'pending':list(gates),'jobs':{j:{'phase':a['phase'],'dir':a['dir']} for j,a in w.JOBS.items()}})
@w.app.route('/__qa__/control',methods=['POST'])
def control():
 global save_status
 c=request.get_json()
 with lock:
  held.update(c.get('hold',[]))
  if c.get('release_all'):
   held.clear()
   for gate in gates.values():gate.set()
  for n in c.get('release',[]):
   if n in gates:gates[n].set()
 for key,gate in [('save',save_gate),('render',render_gate)]:
  if key in c:gate.set() if c[key] else gate.clear()
 save_status=c.get('save_status',save_status)
 return w.jsonify({'ok':True})
w.start_worker()
print(json.dumps({'label':label,'python':sys.version,'opencv':cv2.__version__,'source':w.__file__,'source_sha256':hashlib.sha256(Path(w.__file__).read_bytes()).hexdigest(),'page_sha256':hashlib.sha256(w.PAGE.encode()).hexdigest(),'fixtures':manifest}),flush=True)
class ObservedBody:
 def __init__(self,app):self.app=app
 def __call__(self,environ,start_response):
  body=self.app(environ,start_response)
  def stream():
   exhausted=False
   try:
    for chunk in body:yield chunk
    exhausted=True
   finally:
    if hasattr(body,'close'):body.close()
    token=environ.get('task9_thumb_token')
    if token:
     events[token-1]['body_exhausted']=exhausted
     events[token-1]['body_closed']=time.monotonic()
     if exhausted:events[token-1]['completed']=time.monotonic()
  return stream()
Server(('127.0.0.1',opts.port),ObservedBody(w.app),numthreads=16).start()
