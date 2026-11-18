"""Reuse approved evaluated JS/default audit, plus actual floor grammar."""
import ast
import json
import os
from pathlib import Path
import runpy
runpy.run_path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README/task654-evidence/adapters/audit.py',run_name='__main__')
cfg=json.loads(Path(os.environ['VERIFY_CONFIG']).read_text())
root=Path(cfg['source'])
files=[name for name in cfg['files'] if name.endswith('.py')]
for name in files:
    ast.parse((root/name).read_text(),filename=name,feature_version=(3,9))
record={'floor_grammar':'Python3.9','files':files,'count':len(files)}
(Path(os.environ['VERIFY_RUN'])/'logs/grammar.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record))
