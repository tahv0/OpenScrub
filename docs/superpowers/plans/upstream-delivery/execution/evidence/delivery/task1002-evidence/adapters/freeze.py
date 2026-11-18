from pathlib import Path
import json, hashlib, subprocess, sys
root=Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README')
source=Path('/home/tahv0/.codex/worktrees/bde3/OpenScrub')
d=json.loads((root/'runtime/task1001/package-312.json').read_text())
d.update(task='task1002',scratch=str(root/'runtime/task1002/runs'),source=str(source),source_kind='git',base='335435e1e1120de9e6773656b7dfdfabf220e27b',head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip(),policy='development')
paths=subprocess.check_output(['git','ls-files'],cwd=source,text=True).splitlines()
paths += ['tests/test_strict_tracker_seed.py']
if (source/'tests/test_strict_tracking_routes.py').exists(): paths += ['tests/test_strict_tracking_routes.py']
d['files']={p:hashlib.sha256((source/p).read_bytes()).hexdigest() for p in sorted(set(paths)) if (source/p).is_file()}
d['modules']={k:v for k,v in d['modules'].items() if (source/v).is_file()}
d.pop('package',None)
d['prerequisites']=[p for p in d['prerequisites'] if Path(p['path']).exists() and 'installed' not in p['path']]
name=sys.argv[1]
p=root/'runtime/task1002'/name
p.write_text(json.dumps(d,indent=2)+'\n')
print(p, len(d['files']),len(d['modules']))
