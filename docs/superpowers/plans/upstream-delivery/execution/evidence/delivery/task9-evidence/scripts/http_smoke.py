from pathlib import Path
import json,urllib.request,hashlib,os,sys
r=Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README/runtime/task9')
# This client executes under the task's actual sitecustomize loopback/write guard.
assert 'sitecustomize' in sys.modules
records=[]
for path in ['/', '/api/jobs']:
 with urllib.request.urlopen('http://127.0.0.1:18511'+path) as response:
  body=response.read();assert response.status==200
  if path=='/':assert b'OpenScrub' in body and b'class ReviewScheduler' in body
  else:assert json.loads(body)==[]
  records.append({'path':path,'status':response.status,'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest()})
(r/'evidence/installed-http.json').write_text(json.dumps(records,indent=2));print(json.dumps(records))
