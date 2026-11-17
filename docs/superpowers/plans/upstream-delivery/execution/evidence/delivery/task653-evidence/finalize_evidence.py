import hashlib,json,os
from pathlib import Path
root=Path(__file__).resolve().parent
scratch=root.parent/'runtime/task653/runs'
assert not (scratch/'.verification-active').exists()
actual=sorted(p.name for p in scratch.iterdir() if p.is_dir())
assert actual==sorted(['collect-312','discovery-312','acceptance-312','acceptance-39']),actual
active=[]
for proc in Path('/proc').iterdir():
    if not proc.name.isdigit() or int(proc.name)==os.getpid():continue
    try: command=(proc/'cmdline').read_bytes().replace(b'\0',b' ').decode()
    except (OSError,UnicodeError):continue
    # Match actual prepared Python children/controller arguments, not shell
    # source text merely mentioning this task's path.
    exe=command.split(' ',1)[0]
    if 'python' in Path(exe).name and (str(scratch) in command or ('verify.py' in command and 'task653-evidence/config-' in command)):
        active.append(dict(pid=int(proc.name),command=command))
assert not active,active
status=dict(lock_absent=True,active_task_workloads=active,runs=actual,final_runtime_state='idle; retained owned artifacts')
(root/'runtime-status.json').write_text(json.dumps(status,indent=2)+'\n')
files=sorted(p for p in root.rglob('*') if p.is_file() and p.name!='SHA256SUMS')
(root/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p.relative_to(root))+'\n' for p in files))
for line in (root/'SHA256SUMS').read_text().splitlines():
    digest,name=line.split('  ',1);assert hashlib.sha256((root/name).read_bytes()).hexdigest()==digest
print(json.dumps(dict(evidence_files=len(files),evidence_bytes=sum(p.stat().st_size for p in files),runtime=status),indent=2))
