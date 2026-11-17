import json,threading,urllib.request
from pathlib import Path
import baseline_isolation
art=Path('/tmp/openscrub-task652');baseline_isolation.ROOT=art
web=baseline_isolation.configure('browser-runtime-final')
assert web.__file__=='/home/tahv0/.codex/worktrees/c832/OpenScrub/openscrub_web.py'
r=json.loads((art/'browser-results.json').read_text());expected=json.loads(Path(r['reportPath']).read_text());web.rehydrate_jobs();assert r['ids']['alpha'] in web.JOBS
from cheroot import wsgi
server=wsgi.Server(('127.0.0.1',0),web.app,numthreads=4);server.prepare();thread=threading.Thread(target=server.serve);thread.start()
base='http://127.0.0.1:'+str(server.socket.getsockname()[1])+'/api/jobs/'+r['ids']['alpha']
try:
 with urllib.request.urlopen(base+'/report') as response:assert json.load(response)==expected
 payload={'manual':[{'manual_id':'batch652:replay','t_start':0,'t_end':1.99,'screen_box':[140,80,155,94]}]}
 request=urllib.request.Request(base+'/detections',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
 before=Path(r['reportPath']).read_bytes();stat=Path(r['reportPath']).stat()
 with urllib.request.urlopen(request) as response:assert json.load(response)['ok']
 assert Path(r['reportPath']).read_bytes()==before and Path(r['reportPath']).stat().st_ino==stat.st_ino
 with urllib.request.urlopen(base+'/detections') as response:rows=json.load(response)['detections']
 assert [d['i'] for d in rows]==list(range(14))
 assert [d['enabled'] for d in rows]==[d['enabled'] for d in expected['detections']]
 assert web.FILES.count==0
finally:
 server.stop();thread.join(8);assert not thread.is_alive()
print('fresh-process real HTTP complete14-row report, IDs, flags, replay no-op inode and owner release: passed')
