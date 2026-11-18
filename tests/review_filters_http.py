"""Finite real HTTP/report/render fixture, launched with task-owned output paths."""
from pathlib import Path
import hashlib,json,os,subprocess,threading
import cv2
import numpy as np
import openscrub as o
import openscrub_web as w
from flask import request
from cheroot.wsgi import Server

root=Path(os.environ['VERIFY_RUN'])
y,x=np.indices((180,640));checker=(((x//2+y//2)%2)*180+30).astype('uint8')
frame=np.stack([checker,np.roll(checker,1,0),checker],axis=2)
video=root/'synthetic.mp4';raw=root/'raw.mp4'
writer=cv2.VideoWriter(str(raw),cv2.VideoWriter_fourcc(*'mp4v'),10,(640,180))
for _ in range(30):writer.write(frame)
writer.release()
subprocess.run(['ffmpeg','-y','-loglevel','error','-i',str(raw),'-c:v','libx264','-pix_fmt','yuv420p',str(video)],check=True)
flags=[True,False,True,True,False,False,True,False,False,True]
categories=['face']*4+['plate']*3+['email','face','plate']
boxes=[(20+i*50,20,44+i*50,44) for i in range(8)]+[(20,100,44,124),(70,100,94,124)]
for jid,n in [('A',10),('B',1),('empty',0)]:
 job=w.new_job(str(video),dict(mode='box',pad=0,face_expand=0,face_shape='rect',engine='tesseract',device='cpu',encoder='x264',categories=['face','plate','email']),'Synthetic '+jid)
 w.JOBS.pop(job['id']);job.update(id=jid,phase='review',progress=1);w.JOBS[jid]=job
 detections=[o.Detection(.1,2.8,boxes[i],categories[i],'synthetic '+str(i),.9 if i in (0,4) else .5,(0,0),dense=i in (0,1,2,4,5),track=4 if i in (4,5,9) else -1,person=0 if i in (0,1,2,8) else -1) for i in range(n)]
 report=Path(job['dir'])/'report.json'
 seed=root/('seed-'+jid+'.json')
 o.write_report(str(seed),o.build_parser().parse_args([str(video)]),dict(fps=10.,cum=[(0,0)]*30,bands=[(0,0)]*30,detections=detections,input_sha256=hashlib.sha256(video.read_bytes()).hexdigest()))
 doc=json.loads(seed.read_text())
 for i,r in enumerate(doc['detections']):r.update(enabled=flags[i],zone_dropped=i>=8)
 doc['audio_redactions']=[]
 for i,r in enumerate(doc['detections']):r['unknown_fixture']={'raw_index':i,'retained':[False,'unknown',None]}
 doc['unknown_fixture']={'retained':'full document'}
 doc['render_state']['unknown_fixture']={'retained':'render state'}
 doc['provenance']['unknown_fixture']={'retained':'provenance'}
 with w.VAULT_LOCK:lease=w.FILES.reserve(job)
 with lease:
  with w.FILES.initialize(job).report_lock:w._publish_job_report_locked(job,str(report),doc)
 if jid=='A':(root/'initial-report.json').write_text(json.dumps(doc,indent=2))
render_gate=threading.Event();render_gate.set();original=w.app.view_functions['job_render']
def gated_render(jid):
 if not render_gate.wait(60):return w.jsonify(error='fixture render gate expired'),409
 return original(jid)
w.app.view_functions['job_render']=gated_render
@w.app.route('/__qa__/control',methods=['POST'])
def control():
 render_gate.set() if request.json['render'] else render_gate.clear()
 return w.jsonify(ok=True)
w.app.view_functions['update_check']=lambda:w.jsonify(current=o.VERSION,update_available=False)
w.start_worker();server=Server(('127.0.0.1',18551),w.app,numthreads=8)
thread=threading.Thread(target=server.start,daemon=True);thread.start()
try:
 result=subprocess.run(['node',str(Path(__file__).with_name('review_filters_http.cjs'))],check=False)
 assert result.returncode==0,'real HTTP browser fixture failed'
 job=w.JOBS['A'];assert job['phase']=='done',job
 def at(path):
  cap=cv2.VideoCapture(str(path));cap.set(cv2.CAP_PROP_POS_MSEC,1500);ok,image=cap.read();cap.release();assert ok,str(path);return image
 source,output=at(video),at(job['output']);regions=[]
 for name,box,blurred in [('moved-selected0',(30,30,44,44),True),('kept-member1',(75,25,89,39),False),('selected-member2',(125,25,139,39),True),('kept-B',(175,25,189,39),False),('kept-C',(225,25,239,39),False),('selected-zone8',(25,105,39,119),True),('kept-zone9',(75,105,89,119),False),('manual',(505,105,525,125),True),('unrelated',(600,140,620,160),False)]:
  x1,y1,x2,y2=box;a=source[y1:y2,x1:x2];b=output[y1:y2,x1:x2];mae=float(np.abs(a.astype(float)-b.astype(float)).mean());mean=float(b.mean())
  assert mean<8 if blurred else mae<10,(name,mae,mean)
  regions.append(dict(name=name,blurred=blurred,mae=mae,mean=mean))
 saved=json.loads((root/'pre-render-report.json').read_text());post=json.loads((Path(job['dir'])/'report.json').read_text())
 assert {k:v for k,v in post.items() if k!='provenance'}=={k:v for k,v in saved.items() if k!='provenance'}
 assert post['provenance']['unknown_fixture']==saved['provenance']['unknown_fixture']
 assert post['provenance']['input_sha256']==hashlib.sha256(video.read_bytes()).hexdigest()
 assert post['provenance']['output_sha256']==hashlib.sha256(Path(job['output']).read_bytes()).hexdigest()
 summary=dict(regions=regions,pre_render_rows=len(saved['detections']),post_render_rows=len(post['detections']),output_bytes=Path(job['output']).stat().st_size,post_render_boundary='All raw rows, disabled/zone/manual/audio/unknown fields preserved after real render and fresh HTTP reopen.')
 (root/'output-check.json').write_text(json.dumps(summary,indent=2));cv2.imwrite(str(root/'decoded-output.png'),output);print(json.dumps(summary),flush=True)
finally:
 render_gate.set();server.stop();thread.join(10);assert not thread.is_alive()
