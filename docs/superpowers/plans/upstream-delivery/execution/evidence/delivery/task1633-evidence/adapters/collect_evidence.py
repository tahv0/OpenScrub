"""Copy only task-owned compact identity/log records, never runtime/media trees."""
import hashlib,json,shutil,subprocess
from pathlib import Path
home=Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README');runtime=home/'runtime/task1633';out=home/'task1633-evidence';repo=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
for run in sorted((runtime/'runs').glob('task1633-*')):
 if not run.is_dir():continue
 destination=out/'runs'/run.name;destination.mkdir(parents=True,exist_ok=True)
 for path in list(run.glob('*.json'))+list((run/'logs').glob('*')):
  if path.is_file():
   target=destination/('logs' if path.parent.name=='logs' else 'metadata');target.mkdir(exist_ok=True)
   shutil.copyfile(path,target/path.name)
for path in (runtime/'config').glob('*.json'):shutil.copyfile(path,out/path.name)
for path in (runtime/'adapters').glob('*.py'):shutil.copyfile(path,out/'adapters'/path.name)
shutil.copyfile(home/'task1631-evidence/adapters/task1631_fixture.py',out/'adapters/task1631_fixture.py')
head=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD']).decode().strip()
base='8768e86dc1cd57720fd1c22eb6b539ae6bda6cde'
for args,name in [(['diff','--binary',base,head],'contribution.diff'),(['log','--format=fuller',base+'..'+head],'commits.txt')]:
 (out/name).write_bytes(subprocess.check_output(['git','-C',str(repo),*args]))
commands={}
for path in out.glob('*.log'):
 records=[]
 for line in path.read_text(errors='replace').splitlines():
  for prefix in ['PREFLIGHT ','COMMAND ','RESULT ','SETUP ERROR: ']:
   if line.startswith(prefix):
    body=line[len(prefix):]
    try:value=json.loads(body)
    except ValueError:value=body
    records.append(dict(kind=prefix.strip(),value=value))
 if records:commands[path.name]=records
(out/'commands-and-results.json').write_text(json.dumps(commands,indent=2)+'\n')
manifest={str(p.relative_to(out)):dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(out.rglob('*')) if p.is_file() and p.name!='evidence-manifest.json'}
(out/'evidence-manifest.json').write_text(json.dumps(dict(base=base,head=head,files=manifest),indent=2)+'\n')
print(head,len(manifest),'compact evidence files',sum(v['bytes'] for v in manifest.values()),'bytes')
