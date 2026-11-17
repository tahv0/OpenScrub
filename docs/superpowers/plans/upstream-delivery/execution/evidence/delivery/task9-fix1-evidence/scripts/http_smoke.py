from pathlib import Path
import json,hashlib,urllib.request,os,sys
from task9_isolation import configure
w=configure('fix1-installed-client')
r=Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README/runtime/task9/fix1')
assert Path(w.__file__).resolve()==r/'installed/openscrub_web.py'
expected=json.loads((r/'evidence/source-identities.json').read_text())
assert hashlib.sha256(Path(w.__file__).read_bytes()).hexdigest()==expected['openscrub_web.py']
assert not any('/home/tahv0/.codex/worktrees/' in p or p=='/home/tahv0/src/OpenScrub' for p in sys.path),sys.path
results=[]
for route in ['/', '/api/jobs']:
 with urllib.request.urlopen('http://127.0.0.1:18514'+route) as response:
  body=response.read();assert response.status==200
  if route=='/':assert w.APP_JS.encode() in body;assert b'orderNodes(parent,nodes,active)' in body;assert b'dispose({suspend:true})' in body
  else:assert json.loads(body)==[]
  results.append({'route':route,'status':response.status,'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest()})
record={'web':w.__file__,'source_sha256':expected['openscrub_web.py'],'PAGE_sha256':hashlib.sha256(w.PAGE.encode()).hexdigest(),'APP_JS_sha256':hashlib.sha256(w.APP_JS.encode()).hexdigest(),'HTTP_embedded_APP_JS_exact':True,'responses':results}
(r/'evidence/installed-http.json').write_text(json.dumps(record,indent=2));print(json.dumps(record))
