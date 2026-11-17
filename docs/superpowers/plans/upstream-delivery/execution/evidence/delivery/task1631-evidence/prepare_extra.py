"""Controller setup only, selected Git source and external adapter hashes."""
import hashlib, io, json
from pathlib import Path
import subprocess, tarfile
root=Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README/runtime/task1631')
config=json.loads((root/'frozen312.json').read_text())
for name in ['task1631_fixture.py','test_numpy_wrap.py']:
    path=root/'adapters'/name
    config['prerequisites'].append(dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
(root/'frozen312-seeded.json').write_text(json.dumps(config,indent=2)+'\n')
config39=dict(config,python='/tmp/openscrub-python39-20261117/venv/bin/python',python_version=[3,9,25])
(root/'frozen39-seeded.json').write_text(json.dumps(config39,indent=2)+'\n')
source=root/'base-export';source.mkdir()
base=config['base'];repo=config['source']
archive=subprocess.check_output(['git','-C',repo,'archive',base])
with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
    tar.extractall(source,filter='data')
paths=subprocess.check_output(['git','-C',repo,'ls-tree','-r','--name-only',base],text=True).splitlines()
config.update(source=str(source),source_kind='export',head=base,
              files={p:hashlib.sha256(subprocess.check_output(['git','-C',repo,'show',base+':'+p])).hexdigest() for p in paths})
(source/'.verification-source.json').write_text(json.dumps(dict(base=base,head=base))+'\n')
(root/'baseline.json').write_text(json.dumps(config,indent=2)+'\n')
