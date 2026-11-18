from pathlib import Path
import json,hashlib,subprocess,copy,sys
root=Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README')
rt=root/'runtime/task1002/fix1';source=Path('/home/tahv0/.codex/worktrees/bde3/OpenScrub')
label=sys.argv[1];policy=sys.argv[2];version=sys.argv[3]
prior=root/'runtime/task1002'/('floor-39.json' if version=='39' else 'package-312.json')
d=json.loads(prior.read_text())
d.update(task='task1002-fix1',scratch=str(rt/'runs'),source=str(source),base='285f4afd455ad6dc95a473995dee142421cdc87e',head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip(),policy=policy)
paths=subprocess.check_output(['git','ls-files'],cwd=source,text=True).splitlines()
d['files']={p:hashlib.sha256((source/p).read_bytes()).hexdigest() for p in paths if (source/p).is_file()}
native=json.loads((rt/('native-'+version+'.json')).read_text())
for value in (native['opencv']['native'],native['numpy']['multiarray_umath'],native['opencv']['loader'],native['numpy']['loader']):
 entry=dict(path=value['path'],sha256=value['sha256'])
 if all(p['path']!=entry['path'] for p in d['prerequisites']):d['prerequisites'].append(entry)
d['prerequisites'].append(dict(path=str(rt/('native-'+version+'.json')),sha256=hashlib.sha256((rt/('native-'+version+'.json')).read_bytes()).hexdigest()))
if label.startswith('package'):
 pass
else:d.pop('package',None)
p=rt/label;assert not p.exists();p.write_text(json.dumps(d,indent=2)+'\n')
print(p,len(d['files']),len(d['modules']))
