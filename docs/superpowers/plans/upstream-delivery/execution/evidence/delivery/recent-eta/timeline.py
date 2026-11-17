import ast
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
import openscrub_web as web
ROOT = Path('/tmp/openscrub-task4')
clock = SimpleNamespace(now=0)
fake_time = SimpleNamespace(time=lambda: clock.now, monotonic=lambda: clock.now)
source = subprocess.check_output(['git','show','e21ebdf6e3ee46e6c65050dc956a9a3459152269:openscrub_web.py'], text=True)
node = next(n for n in ast.parse(source).body if isinstance(n, ast.ClassDef) and n.name == 'WebCallbacks')
namespace = dict(vars(web), time=fake_time)
exec(compile(ast.Module(body=[node],type_ignores=[]),'<upstream callback>', 'exec'), namespace)
old = namespace['WebCallbacks']({})
web.time = fake_time
new = web.WebCallbacks({})
rows=[]
for t in range(0, 901, 5):
    clock.now=t
    cur=t*10 if t<=600 else 6000+t-600
    old.progress('scan',cur,10000)
    new.progress('scan',cur,10000)
    if t in [0,5,20,600,630,660,720,725,780,900]:
        rows.append(dict(t=t,cur=cur,old_eta=old.job['eta'],recent_eta=new.job['eta'],remaining_at_tail_rate=10000-cur if t>=600 else None,samples=len(new._rate_points)))
(ROOT/'timeline.json').write_text(json.dumps(rows,indent=2))
print(json.dumps(rows,indent=2))
