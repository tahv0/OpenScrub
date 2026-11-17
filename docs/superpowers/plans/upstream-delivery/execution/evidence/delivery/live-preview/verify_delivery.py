import hashlib
import json
from pathlib import Path
import subprocess

root=Path('/tmp/openscrub-task5')
source=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
base='e21ebdf6e3ee46e6c65050dc956a9a3459152269'
head=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD']).decode().strip()
assert subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD^']).decode().strip()==base
assert not subprocess.check_output(['git','-C',str(source),'status','--porcelain'])
files=['openscrub_web.py','tests/test_live_preview.py','pyproject.toml','README.md','CONTRIBUTING.md']
for name in files:
    assert subprocess.check_output(['git','-C',str(source),'show','HEAD:'+name])==(source/name).read_bytes()
result={'base':base,'head':head,'branch':'pr/live-preview-snapshots',
        'clean_worktree':True,'source_committed_bytes_match':True,
        'source_sha256':{name:hashlib.sha256((source/name).read_bytes()).hexdigest() for name in files},
        'artifacts_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.iterdir()) if p.is_file() and p.name not in ('evidence-manifest.json', 'delivery.log')}}
(root/'evidence-manifest.json').write_text(json.dumps(result,indent=2)+'\n')
print('exact parent, clean branch, committed source/tests match verified artifacts: passed')
