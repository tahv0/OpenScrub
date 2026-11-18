"""Prospective fix-round verification bytes; no product imports."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

root = Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README')
source = Path('/home/tahv0/.codex/worktrees/bde3/OpenScrub')
task = root/'runtime/task1001/fix1'
label = sys.argv[1]
config = json.loads((root/'runtime/task1001/package-complete-312.json').read_text())
paths = subprocess.check_output(['git','-c','gc.auto=0','-c','maintenance.auto=false','ls-files'],cwd=source,text=True).splitlines()
paths += [str(p.relative_to(source)) for p in source.glob('tests/test_exact*.py')]
files = {name:hashlib.sha256((source/name).read_bytes()).hexdigest() for name in sorted(set(paths)) if (source/name).is_file()}
config.update(task='task1001-fix1',scratch=str(task/'runs'),base='5acb655f98cc4699d4a05a5670e4e7ab33b477d6',head=subprocess.check_output(['git','-c','gc.auto=0','-c','maintenance.auto=false','rev-parse','HEAD'],cwd=source,text=True).strip(),policy='development' if label.startswith('dev') else 'frozen',files=files)
config['package']['sdist_files']=sorted(set(config['package']['sdist_files']+[name for name in files if name.startswith('tests/')]))
# Preserve exact prepared tool, interpreter, media and installed HTTP pins.
(task/(label+'-312.json')).write_text(json.dumps(config,indent=2)+'\n')
floor=json.loads(json.dumps(config));floor['python']='/tmp/openscrub-python39-20261117/venv/bin/python';floor['python_version']=[3,9,25]
floor['prerequisites']=[item for item in floor['prerequisites'] if not item['path'].endswith('venv-opencv4/bin/python')]
floor['prerequisites'].append(dict(path=floor['python'],sha256='84c920f304e265c53096e42d83309c6f7b829988f937a7dd15c24eebcb63f59a',executable=True))
(task/(label+'-39.json')).write_text(json.dumps(floor,indent=2)+'\n')
print(label,config['head'],len(files),'prospectively pinned files')
