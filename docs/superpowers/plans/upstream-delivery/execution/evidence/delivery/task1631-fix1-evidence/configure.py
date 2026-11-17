"""Fix1 controller-only source inventory; no application execution."""
import hashlib,json,subprocess
from pathlib import Path
root=Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README/runtime/task1631')
config=json.loads((root/'final312.json').read_text());repo=Path(config['source'])
config.update(task='task1631-fix1',head=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip(),policy='development')
config['files']={name:hashlib.sha256((repo/name).read_bytes()).hexdigest() for name in config['files']}
(root/'fix1/development312.json').write_text(json.dumps(config,indent=2)+'\n')
