from pathlib import Path
import hashlib
import json
import re
import socket
import tarfile
import threading
import urllib.request
import zipfile
import openscrub
import openscrub_web as web
from cheroot.wsgi import Server
root=Path('/tmp/openscrub-task3')
source=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
assert Path(web.__file__).resolve()==root/'installed/openscrub_web.py'
assert Path(openscrub.__file__).resolve()==root/'installed/openscrub.py'
assert (root/'installed/openscrub_web.py').read_bytes()==(source/'openscrub_web.py').read_bytes()
with tarfile.open(next((root/'dist').glob('*.tar.gz'))) as archive:
 names=archive.getnames()
 for file in ('tests/test_job_polling_node.py','tests/test_job_polling_browser.py','tests/test_review_save_failures.py','openscrub_web.py'):
  assert any(name.endswith('/'+file) for name in names),file
with zipfile.ZipFile(next((root/'dist').glob('*.whl'))) as archive:
 assert archive.read('openscrub_web.py')==(source/'openscrub_web.py').read_bytes()
for name in ('JOBS_DIR','ZONES_PATH','MODEL_SELECT_PATH','CERT_DIR','WEB_SETTINGS_PATH','CUSTOM_CATS_PATH'):
 setattr(web,name,str(root/'installed-runtime'/Path(getattr(web,name)).name))
Path(web.JOBS_DIR).mkdir(parents=True,exist_ok=True)
openscrub._fetch_model=lambda *a,**k:(_ for _ in ()).throw(RuntimeError('No model downloads'))
job=web.new_job('',{},'synthetic installed job');job['log']=['installed line'];job['phase']='queued'
with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
server=Server(('127.0.0.1',port),web.app,numthreads=4)
server.prepare();thread=threading.Thread(target=server.serve,daemon=True);thread.start()
try:
 base='http://127.0.0.1:'+str(port)
 for path in ('/','/api/jobs','/api/jobs/'+job['id'],'/api/jobs/'+job['id']+'/log?from=0'):
  with urllib.request.urlopen(base+path,timeout=3) as r:
   data=r.read();assert r.status==200
   if path=='/':assert b'pollStatus' in data and 'no-store' in r.headers['Cache-Control']
   else:json.loads(data)
   print('GET',path,'200')
 root.joinpath('installed-evaluated-page.js').write_text('\n'.join(re.findall(r'<script>(.*?)</script>',web.PAGE,re.S)))
 print('Installed source:',web.__file__)
 print('sdist includes all tests; wheel/installed source match active source')
finally:
 server.stop();thread.join(timeout=3)
