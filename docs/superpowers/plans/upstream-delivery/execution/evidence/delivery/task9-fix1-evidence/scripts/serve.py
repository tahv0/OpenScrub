"""Fix1 actual PAGE/metadata/thumbnail routes; warm-only bounded structure fixture."""
from pathlib import Path
import hashlib,json,os,sys
from task9_isolation import configure
w=configure('fix1-server')
import openscrub as o,cv2,numpy as np
from cheroot.wsgi import Server
ROOT=Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README/runtime/task9/fix1')
assert Path(w.__file__).resolve()==Path(os.environ['TASK9_SOURCE'])/'openscrub_web.py'
(ROOT/'runtime').mkdir(exist_ok=True)
image=ROOT/'runtime/fixture.jpg';assert cv2.imwrite(str(image),np.full((70,110,3),120,dtype=np.uint8))
job=w.new_job(str(image),{},'Fix1 ordinary cards');w.JOBS.pop(job['id']);job.update(id='order',phase='review',progress=1);w.JOBS['order']=job
rows=[o.Detection(.1+i/1000,3.8,(5,5,35,35),'face','ordinary '+str(i)+(' variable text for a natural taller card'*(i%5==0)),.8,(0,0)) for i in range(180)]
state={'fps':10.,'cum':[(0,0)]*40,'bands':[(0,0)]*40,'detections':rows}
report=Path(job['dir'])/'report.json';o.write_report(str(report),o.build_parser().parse_args([str(image)]),state)
doc=json.loads(report.read_text());doc['detections'].extend([dict(doc['detections'][i],zone_dropped=True) for i in range(2)]);report.write_text(json.dumps(doc,indent=1))
for i in range(182):os.link(image,Path(job['dir'])/('thumb2_%d.jpg'%i))
w.app.view_functions['update_check']=lambda:w.jsonify({'current':o.VERSION,'update_available':False})
identity={'web':w.__file__,'web_sha256':hashlib.sha256(Path(w.__file__).read_bytes()).hexdigest(),'PAGE_sha256':hashlib.sha256(w.PAGE.encode()).hexdigest(),'rows':182,'ordinary_groups':180,'zones':2,'cache':'all actual cached JPEG hits; no cold decoder work','port':18513}
(ROOT/'evidence/server-identity.json').write_text(json.dumps(identity,indent=2));print(json.dumps(identity),flush=True)
Server(('127.0.0.1',18513),w.app,numthreads=8).start()
