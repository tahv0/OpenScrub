"""Final caller freeze from the clean corrected Git object; no product execution."""
import hashlib,json,subprocess
from pathlib import Path
root=Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README/runtime/task1631')
config=json.loads((root/'frozen312-seeded.json').read_text());repo=config['source']
def git(*args): return subprocess.check_output(['git','-C',repo,*args])
assert not git('status','--porcelain').strip()
head=git('rev-parse','HEAD').decode().strip()
paths=git('ls-tree','-r','--name-only',head).decode().splitlines()
config.update(head=head,files={p:hashlib.sha256(git('show',head+':'+p)).hexdigest() for p in paths})
for name in ['adapters/test_coverage_rounding.py','environment.py']:
    path=root/name;config['prerequisites'].append(dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
(root/'final312.json').write_text(json.dumps(config,indent=2)+'\n')
config39=dict(config,python='/tmp/openscrub-python39-20261117/venv/bin/python',python_version=[3,9,25])
(root/'final39.json').write_text(json.dumps(config39,indent=2)+'\n')
print('FINAL_FREEZE',head,len(paths))
