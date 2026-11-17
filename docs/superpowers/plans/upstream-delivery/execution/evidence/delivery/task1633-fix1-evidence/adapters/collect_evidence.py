"""Archive only compact fix-owned records; never alter prior task evidence."""
import hashlib,json,shutil
from pathlib import Path
sdd=Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README')
root=sdd/'runtime/task1633/fix1';out=sdd/'task1633-fix1-evidence'
for path in (root/'config').glob('*.json'):shutil.copyfile(path,out/path.name)
shutil.copyfile(root/'adapters/freeze.py',out/'adapters/freeze.py')
shutil.copyfile(sdd/'runtime/task1633/adapters/listening_publication.py',out/'adapters/listening_publication.py')
for run in sorted((sdd/'runtime/task1633/runs').glob('task1633-fix1-*')):
 if not run.is_dir():continue
 destination=out/'runs'/run.name;destination.mkdir(parents=True,exist_ok=True)
 for path in list(run.glob('*.json'))+list((run/'logs').glob('*')):
  if path.is_file():
   target=destination/('logs' if path.parent.name=='logs' else 'metadata');target.mkdir(exist_ok=True)
   shutil.copyfile(path,target/path.name)
records={}
for path in out.glob('*.log'):
 values=[]
 for line in path.read_text(errors='replace').splitlines():
  for prefix in ['PREFLIGHT ','COMMAND ','RESULT ','SETUP ERROR: ']:
   if line.startswith(prefix):
    body=line[len(prefix):]
    try:value=json.loads(body)
    except ValueError:value=body
    values.append(dict(kind=prefix.strip(),value=value))
 if values:records[path.name]=values
(out/'commands-and-results.json').write_text(json.dumps(records,indent=2)+'\n')
package=next(json.loads(line) for line in reversed((out/'package312.log').read_text().splitlines()) if line.startswith('{"requires_python"'))
(out/'package-result.json').write_text(json.dumps(package,indent=2)+'\n')
manifest={str(p.relative_to(out)):dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(out.rglob('*')) if p.is_file() and p.name!='evidence-manifest.json'}
(out/'evidence-manifest.json').write_text(json.dumps(dict(base='64647f22e303af259f2cd7372fd1dc7c3be6e02a',head='a132081f1e609ed19deb4477044ee1c9b77871cc',files=manifest),indent=2)+'\n')
print(len(manifest),'compact fix records',sum(v['bytes'] for v in manifest.values()),'bytes')
