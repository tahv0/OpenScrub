import json,threading,urllib.request,hashlib
from pathlib import Path
import cv2
from baseline_isolation import configure
web=configure('/tmp/openscrub-task631/browser-runtime')
assert web.__file__ == '/home/tahv0/.codex/worktrees/c832/OpenScrub/openscrub_web.py'
info=json.loads(Path('/tmp/openscrub-task631/browser-job.json').read_text())
path=Path(info['path']); before=path.read_bytes(); stat=path.stat()
web.TOKEN=None;web.rehydrate_jobs();job=web.JOBS[info['id']]
assert job['phase']=='done' and Path(job['output']).is_file()
cap=cv2.VideoCapture(job['output']);ok,frame=cap.read();cap.release()
assert ok and frame[20,20].mean()>150
from cheroot.wsgi import Server
ready=threading.Event();server=Server(('127.0.0.1',0),web.app,numthreads=2);original=server.prepare
def prepare():original();ready.set()
server.prepare=prepare
thread=threading.Thread(target=server.start);thread.start();assert ready.wait(10)
try:
 url='http://127.0.0.1:'+str(server.socket.getsockname()[1])+'/api/jobs/'+info['id']+'/detections'
 with urllib.request.urlopen(url,timeout=5) as response:
  report=json.load(response);assert report['detections'][0]['enabled'] is False
 req=urllib.request.Request(url,data=b'{"enabled":{"0":false}}',headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=5) as response:
  assert response.status==200 and json.load(response)=={'ok':True,'total':1,'suggest_allowlist':[]}
 assert path.read_bytes()==before and path.stat().st_ino==stat.st_ino and path.stat().st_mtime_ns==stat.st_mtime_ns
 assert json.loads(before)['custom']=={'preserved':True}
 assert web.FILES.count==0
finally:server.stop();thread.join(10);assert not thread.is_alive()
print(json.dumps({'fresh_process_HTTP_reopen':True,'same_value_publication_skipped':True,'output_decoded':True,'kept_region_mean':float(frame[20,20].mean()),'output_bytes':Path(job['output']).stat().st_size,'report_sha256':hashlib.sha256(before).hexdigest(),'active_source':web.__file__},indent=2))
