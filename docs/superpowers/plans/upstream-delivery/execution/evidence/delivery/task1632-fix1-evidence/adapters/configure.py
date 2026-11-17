"""Task-owned identities only; canonical verification owns execution/isolation."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

root = Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README')
evidence = root / 'task1632-fix1-evidence'
source = Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
policy = sys.argv[1] if len(sys.argv) > 1 else 'development'
head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip()
for label, template in [('development', 'frozen'), ('floor-development', 'floor'), ('package-development', 'package')]:
    config = json.loads((root / 'task1632-evidence' / (template + '.json')).read_text())
    config.update(task='task1632-fix1', base='8e70af446caa5ed37e0e36c029925d5caf08f943', head=head, policy=policy)
    for name in config['files']:
        data = (source / name).read_bytes()
        if policy == 'frozen':
            selected = subprocess.check_output(['git', 'show', head + ':' + name], cwd=source)
            assert data == selected
            data = selected
        config['files'][name] = hashlib.sha256(data).hexdigest()
    if policy == 'frozen':
        label = {'development': 'frozen', 'floor-development': 'floor', 'package-development': 'package'}[label]
    (evidence / (label + '.json')).write_text(json.dumps(config, indent=2) + '\n')
