from pathlib import Path
old=Path('/tmp/openscrub-task650/serve_browser.py').read_text().replace('task650','task651').replace('Task650','Task651').replace('18650','18651')
old=old.replace('import json','import json,threading,time\nfrom types import SimpleNamespace\nimport openscrub')
old=old.replace("ids={}\n", "ids={}\npublications=[]\n")
old=old.replace(" job.update(video=str(video),phase='done')", " job.update(video=str(video),phase='done')")
# Keep beta for streaming; alpha uses the complete ordinary mixed-row fixture after a real controlled-OCR scan.
a=old.index('real=web.atomic_report')
old=old[:a]+'''alpha=web.JOBS[ids['alpha']]
alpha['options'].update(categories='email',engine='tesseract',no_ner=True,no_memory=True,sample_interval=.2)
alpha['phase']='queued'
real_ocr=openscrub.make_ocr
openscrub.make_ocr=lambda *a,**kw:SimpleNamespace(read=lambda frame:[('one@example.invalid',(4,2,65,18),.99)])
web._run_job(alpha,'scan')
assert alpha['phase']=='review',alpha.get('error')
scanned=json.loads((Path(alpha['dir'])/'report.json').read_text())
Path('/tmp/openscrub-task651/actual-scan.json').write_text(json.dumps(scanned))
assert scanned['detections']
openscrub.make_ocr=real_ocr
# Controlled imported-report boundary; no detector quality claim.
doc=json.loads(Path('/tmp/openscrub-task20/synthetic-report.json').read_text())
for i,d in enumerate(doc['detections']):
 x=4+(i%7)*22;y=18+(i//7)*40
 d.update(cbox=[x,y,x+16,y+28],t_start=0,t_end=1.99,last_seen=0,future_row={'index':i,'preserved':[False,None,'雪']})
doc['provenance']={'input':alpha['video'],'settings':{},'future_provenance':{'keep':True}}
doc['render_state']={'fps':30,'cum':[[0,0]]*60,'bands':[[0,0]]*60,'future_state':{'keep':True}}
doc.update(audio_redactions=[{'t0':.2,'t1':.4,'mode':'mute','future':True}],audio_suggestions=[{'t0':.5,'t1':.7,'text':'synthetic','category':'name','future':True}],audio_transcript=[[0,1,'synthetic audio']],future_top={'keep':[False,None,'雪']})
(Path(alpha['dir'])/'report.json').write_text(json.dumps(doc,indent=1))
Path('/tmp/openscrub-task651/initial-report.json').write_text(json.dumps(doc))
real=web.atomic_report
from flask import has_request_context
def publish(path,doc):
 saving=has_request_context() and web.request.path.endswith('/detections')
 event={'saving':saving,'complete':False,'failed':False};publications.append(event)
 if saving and web.request.headers.get('X-Task651-Fail')=='yes':
  event['failed']=True
  Path('/tmp/openscrub-task651/publications.json').write_text(json.dumps(publications))
  raise OSError('injected report publication failure')
 result=real(path,doc);event['complete']=True
 Path('/tmp/openscrub-task651/publications.json').write_text(json.dumps(publications))
 return result
web.atomic_report=publish
web.app.view_functions['update_check']=lambda:web.jsonify({'current':web.openscrub.VERSION,'update_available':False})
Path('/tmp/openscrub-task651/browser-jobs.json').write_text(json.dumps(ids))
Path('/tmp/openscrub-task651/browser-paths.json').write_text(json.dumps({k:v['dir'] for k,v in web.JOBS.items()}))
threading.Thread(target=web.worker,daemon=True).start()
from cheroot.wsgi import Server
server=Server(('127.0.0.1',18651),web.app,numthreads=16)
# Real HTTP headers + initial body byte, then independently held body.
real_app=web.app
def gated_app(env,start):
 result=real_app(env,start)
 if env.get('HTTP_X_TASK651_HOLD')=='yes':
  def chunks():
   try:
    for chunk in result:
     yield chunk[:1]
     Path('/tmp/openscrub-task651/body-entered').write_text('entered')
     limit=time.monotonic()+25
     while not Path('/tmp/openscrub-task651/body-release').exists() and time.monotonic()<limit:time.sleep(.01)
     yield chunk[1:]
   finally:
    if hasattr(result,'close'):result.close()
  return chunks()
 return result
server.wsgi_app=gated_app
print('Task651 browser server ready',flush=True)
server.start()
'''
Path('/tmp/openscrub-task651/serve_browser.py').write_text(old)
