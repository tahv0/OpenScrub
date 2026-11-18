"""Task-owned real HTTP sample/save/render/fresh-interpreter reopen smoke."""
import copy
import hashlib
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import urllib.request

import cv2
from werkzeug.serving import make_server
import openscrub as engine
import openscrub_web as web

root=Path(os.environ['VERIFY_RUN'])
web.TOKEN=None

def serve():
    server=make_server('127.0.0.1',0,web.app,threaded=True)
    thread=threading.Thread(target=server.serve_forever)
    thread.start()
    return server,thread,'http://127.0.0.1:'+str(server.server_port)

def fetch(base,path,body=None):
    data=None if body is None else json.dumps(body).encode()
    req=urllib.request.Request(base+path,data=data,headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=20) as response:
        return response.status,json.loads(response.read()),dict(response.headers)

def pc(value,row=None):
    answer={key:value['sample'][key] for key in ('source_ref','timeline_eq','policy','index','width','height','offset')}
    answer['version']=1
    if row is not None:answer.update(row_context_eq=value['boxes'][row]['row_context_eq'],base=value['boxes'][row]['base'])
    return answer

if '--reopen' in sys.argv:
    _,_,folder,video,oldref=sys.argv
    web.JOBS={'reopen':dict(id='reopen',dir=folder,video=video,phase='review',options={},log=[])}
    web.FILES.initialize(web.JOBS['reopen'])
    server,thread,base=serve()
    try:
        _,value,headers=fetch(base,'/api/jobs/reopen/edit_sample?t=0.2')
        assert value['sample']['source_ref']!=oldref and len(value['boxes'])==3
        _,rows,_=fetch(base,'/api/jobs/reopen/detections')
        assert len(rows['detections'])==3 and rows['detections'][1]['enabled'] is False
        raw=json.loads((Path(folder)/'report.json').read_text())
        assert raw['detections'][0]['future']=={'keep':[None,False,'snow']}
        assert raw['detections'][2]['manual_id']=='http:draw'
        assert raw['audio_redactions']==[{'t0':0.,'t1':.4,'mode':'mute'}]
        assert headers['Cache-Control']=='private, no-store'
        print('FRESH_INTERPRETER_LISTENING_HTTP_REOPEN_OK',flush=True)
    finally:
        server.shutdown();thread.join(10);server.server_close();assert not thread.is_alive()
    assert web.FILES.count==0
    raise SystemExit(0)

manifest=json.loads(Path(os.environ['OPENSCRUB_EXACT_MEDIA']).read_text())
video=manifest['cfr5']['path']
assert hashlib.sha256(Path(video).read_bytes()).hexdigest()==manifest['cfr5']['sha256']
assert engine.build_parser().parse_args(['dummy.mp4']).mode=='blur'
job=web.new_job(video,dict(encoder='x264',mode='box',pad=0),'synthetic.mp4')
job.update(video=video,phase='review')
path=Path(job['dir'])/'report.json'
row=dict(t_start=0.,t_end=2.,last_seen=.5,cbox=[20,30,50,60],aoff=[0,0],category='manual',text='synthetic',enabled=True,confidence=1.,future={'keep':[None,False,'snow']})
doc=dict(provenance=dict(input=video,settings={}),render_state=dict(fps=5,cum=[[0,0]]*10,bands=[[0,0]]*10),detections=[row,dict(row,enabled=False)],future_top={'preserved':True})
path.write_text(json.dumps(doc))
server,thread,base=serve();worker=None
try:
    url='/api/jobs/'+job['id']
    status,value,headers=fetch(base,url+'/edit_sample?t=1.9')
    assert status==200 and value['sample']['index']==9
    assert headers['Cache-Control']=='private, no-store'
    first_ref=value['sample']['source_ref']
    # Inspect canonical .2 for the strict manual reference.
    _,value,_=fetch(base,url+'/edit_sample?t=0.2')
    edits=dict(geometry_preconditions={'0':pc(value,0)},box_overrides={'0':[22,32,52,62]},enabled={'1':False},audio=[{'t0':0,'t1':.4}],manual=[dict(manual_id='http:draw',t_start=0,t_end=1,t_ref=.2,screen_box=[70,30,90,60],sample_precondition=pc(value))])
    status,ack,_=fetch(base,url+'/detections',edits)
    assert status==200 and ack['geometry_rows']['0']['base']['cbox']==[22,32,52,62]
    assert fetch(base,url+'/detections',edits)[0]==200
    assert len(json.loads(path.read_text())['detections'])==3
    status,_,_=fetch(base,url+'/render',{})
    assert status==200
    web.WORK_Q.put(None)
    worker=threading.Thread(target=web.worker);worker.start();worker.join(30)
    assert not worker.is_alive() and job['phase']=='done',job
    assert Path(job['output']).is_file()
    cap=cv2.VideoCapture(job['output']);frames=0
    try:
        while True:
            ok,image=cap.read()
            if not ok:break
            frames+=1
    finally:cap.release()
    assert frames==10
    saved=json.loads(path.read_text())
    assert len(saved['detections'])==3 and saved['future_top']=={'preserved':True}
    child=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--reopen',job['dir'],video,first_ref],capture_output=True,text=True,timeout=30,check=True)
    (root/'logs/http-reopen.stdout').write_text(child.stdout)
    (root/'logs/http-reopen.stderr').write_text(child.stderr)
    assert 'FRESH_INTERPRETER_LISTENING_HTTP_REOPEN_OK' in child.stdout
    print('REAL_HTTP_SAMPLE_STRICT_SAVE_RENDER_REOPEN_OK',json.dumps(dict(rows=3,output_frames=frames,source=str(web.__file__),report_sha256=hashlib.sha256(path.read_bytes()).hexdigest())),flush=True)
finally:
    server.shutdown();thread.join(10);server.server_close();assert not thread.is_alive()
    if worker is not None:worker.join(10);assert not worker.is_alive()
assert web.FILES.count==0
