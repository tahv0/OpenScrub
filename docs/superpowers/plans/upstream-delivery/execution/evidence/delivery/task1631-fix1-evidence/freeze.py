"""Freeze fix1 from a clean Git object; never execute application code."""
import hashlib,json,subprocess
from pathlib import Path
root=Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README/runtime/task1631');config=json.loads((root/'final312.json').read_text());repo=config['source']
def git(*a):return subprocess.check_output(['git','-C',repo,*a])
assert not git('status','--porcelain').strip()
head=git('rev-parse','HEAD').decode().strip();paths=git('ls-tree','-r','--name-only',head).decode().splitlines()
config.update(task='task1631-fix1',head=head,policy='frozen',files={p:hashlib.sha256(git('show',head+':'+p)).hexdigest() for p in paths})
(root/'fix1/final312.json').write_text(json.dumps(config,indent=2)+'\n')
config39=dict(config,python='/tmp/openscrub-python39-20261117/venv/bin/python',python_version=[3,9,25])
(root/'fix1/final39.json').write_text(json.dumps(config39,indent=2)+'\n')
print('FIX1_FROZEN',head)
