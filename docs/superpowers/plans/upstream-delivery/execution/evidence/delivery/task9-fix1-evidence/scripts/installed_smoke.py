from pathlib import Path
import os,json,hashlib,sys
from task9_isolation import configure
w=configure('fix1-installed-http')
import openscrub as o
r=Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README/runtime/task9/fix1')
assert Path(o.__file__).resolve()==r/'installed/openscrub.py'
assert Path(w.__file__).resolve()==r/'installed/openscrub_web.py'
assert not any('/home/tahv0/.codex/worktrees/' in p or p=='/home/tahv0/src/OpenScrub' for p in sys.path),sys.path
source=json.loads((r/'evidence/source-identities.json').read_text())
assert hashlib.sha256(Path(w.__file__).read_bytes()).hexdigest()==source['openscrub_web.py']
args=vars(o.build_parser().parse_args(['synthetic.mp4']));(r/'evidence/installed-defaults.json').write_text(json.dumps(args,sort_keys=True,default=str,indent=2))
print(json.dumps({'source':o.__file__,'web':w.__file__,'python':sys.version,'sys_path':sys.path,'PAGE_sha256':hashlib.sha256(w.PAGE.encode()).hexdigest(),'defaults_count':len(args)}),flush=True)
from cheroot.wsgi import Server
Server(('127.0.0.1',18514),w.app,numthreads=4).start()
