"""Pinned-source emitted UI with synthetic jobs and one gated HTTP body."""
import os, sys, json, threading, hashlib
from pathlib import Path
ROOT=Path('/tmp/openscrub-polling-baseline-20261117')
sys.path.insert(0,str(ROOT/'pinned'))
os.environ['OPENSCRUB_NO_AUTOFETCH']='1'
import openscrub, openscrub_web as web
from flask import request, Response
from cheroot.wsgi import Server
assert Path(web.__file__).resolve()==ROOT/'pinned/openscrub_web.py'
DATA=ROOT/'data'; DATA.mkdir(exist_ok=True)
for key in ('JOBS_DIR','ZONES_PATH','MODEL_SELECT_PATH','CERT_DIR','WEB_SETTINGS_PATH','CUSTOM_CATS_PATH'):
 setattr(web,key,str(DATA/Path(getattr(web,key)).name))
Path(web.JOBS_DIR).mkdir(exist_ok=True)
openscrub._model_dir=lambda:str(DATA/'models')
openscrub._fetch_model=lambda *a,**k: (_ for _ in ()).throw(RuntimeError('QA forbids model downloads'))
for jid in ('A','B'):
 j=web.new_job('',{},'synthetic job '+jid); web.JOBS.pop(j['id']);j['id']=jid
 j['phase']='queued';j['progress']=.2;j['log']=['log-'+jid];web.JOBS[jid]=j
web.app.view_functions['certinfo']=lambda:web.jsonify({'mode':'auto','https':False})
web.app.view_functions['update_check']=lambda:web.jsonify({'current':openscrub.VERSION,'update_available':False})
web.app.view_functions['job_delete']=lambda jid:web.jsonify({'ok':True})
# Confirm correct endpoint name without changing any product route code.
for rule in web.app.url_map.iter_rules():
 if rule.rule=='/api/jobs/<jid>' and 'DELETE' in rule.methods:
  web.app.view_functions[rule.endpoint]=lambda jid:web.jsonify({'ok':True})
web.app.view_functions['job_detections']=lambda jid:web.jsonify({'duration':10,'detections':[{'i':0,'category':'mrn','text':'review-'+jid,'enabled':True,'t_start':0.,'t_end':1.,'track':-1,'person':-1,'confidence':.9}]})
# Production endpoint is called job_detections; retain all emitted client code.
web.app.view_functions['job_mediainfo']=lambda jid:web.jsonify({'duration':10,'width':320,'height':180})
web.app.view_functions['job_report']=lambda jid:web.jsonify({'detections':[],'audio_redactions':[{'t0':1,'t1':2,'mode':'mute'}],'audio_suggestions':[],'audio_transcript':[]})
web.app.view_functions['job_boxes_at']=lambda jid:web.jsonify({'boxes':[]})
state={'stream_next':False,'stream_kind':'meta','entered':0,'released':0}; gate=threading.Event()
original_status=web.app.view_functions['job_status']
original_log=web.app.view_functions['job_log']
def streamed(jid,kind):
 original=original_status if kind=='meta' else original_log
 if not state['stream_next'] or state['stream_kind']!=kind:return original(jid)
 state['stream_next']=False; state['entered']+=1;gate.clear()
 payload=original(jid).get_data()
 def body():
  yield payload[:1]
  gate.wait(8)
  state['released']+=1
  yield payload[1:]
 return Response(body(),content_type='application/json',headers={'X-QA-Body-Gate':'true','Content-Length':str(len(payload))})
web.app.view_functions['job_status']=lambda jid:streamed(jid,'meta')
web.app.view_functions['job_log']=lambda jid:streamed(jid,'log')
@web.app.route('/__qa__/control',methods=['POST'])
def control():
 d=request.get_json()
 if d.get('stream_next'):state['stream_next']=True;state['stream_kind']=d.get('kind','meta')
 if d.get('release'):gate.set()
 if 'phase' in d:
  for j in web.JOBS.values():j['phase']=d['phase']
 return web.jsonify(state)
@web.app.route('/__qa__/state')
def qa_state():return web.jsonify(state)
(ROOT/'emitted.html').write_text(web.PAGE)
(ROOT/'app.js').write_text(web.APP_JS)
(ROOT/'server-identity.json').write_text(json.dumps({'pin':'92124753736e287ac800af91f0ac96f3e96c01be','web_file':web.__file__,'source_sha256':hashlib.sha256(Path(web.__file__).read_bytes()).hexdigest(),'page_sha256':hashlib.sha256(web.PAGE.encode()).hexdigest(),'app_js_sha256':hashlib.sha256(web.APP_JS.encode()).hexdigest(),'python':sys.version,'routes':[{ 'rule':r.rule,'endpoint':r.endpoint} for r in web.app.url_map.iter_rules() if r.rule.startswith('/api/jobs') ]},indent=2))
print('Pinned polling QA http://127.0.0.1:18513',flush=True)
Server(('127.0.0.1',18513),web.app,numthreads=16).start()
