"""Retain compact authorized Task1001 source/runtime evidence; no media/installs."""
import ast
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import zipfile

root=Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README')
task=root/'runtime/task1001';out=root/'task1001-evidence'
source=Path('/home/tahv0/.codex/worktrees/bde3/OpenScrub')
base='12919c96c6f7558136b50d7b4d85e5e6b62f1971'
head='5acb655f98cc4699d4a05a5670e4e7ab33b477d6'
def git(*args):return subprocess.check_output(['git','-c','gc.auto=0','-c','maintenance.auto=false',*args],cwd=source)
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
assert git('rev-parse','HEAD').decode().strip()==head
assert not git('status','--porcelain')
config=json.loads((task/'final-312.json').read_text())
for name,digest in config['files'].items():
    assert sha(source/name)==digest
    assert hashlib.sha256(git('show',head+':'+name)).hexdigest()==digest
refs=[]
for line in (task/'base-refs.txt').read_text().splitlines():
    ref,old=line.split()
    actual=git('rev-parse',ref).decode().strip()
    assert actual==old,(ref,old,actual)
    refs.append(dict(ref=ref,expected=old,actual=actual))

def literals(text):
    result={}
    for node in ast.parse(text).body:
        if isinstance(node,ast.Assign):
            for target in node.targets:
                if isinstance(target,ast.Name) and target.id in ('APP_JS','APP_CSS'):
                    result[target.id]=ast.literal_eval(node.value)
    return result
assert literals(git('show',base+':openscrub_web.py').decode())==literals((source/'openscrub_web.py').read_text())
static=dict(base=base,head=head,files=len(config['files']),runtime_modules=config['modules'],
    unchanged_editor_literals=['APP_JS','APP_CSS'],unchanged_files=['openscrub.py','pyproject.toml','openscrub_internal/reports.py'],preserved_refs=refs,
    packaging_source_checks=dict(docker=['Dockerfile:63','Dockerfile.cuda:135','Dockerfile.intel:97'],
      updater='update_source iterates non-preserved sdist file paths including openscrub_internal/exact_samples.py',
      frozen='windows/openscrub.spec analyzes openscrub_web.py; its direct private import is statically visible; no Windows build/runtime claimed'))
for name in static['unchanged_files']:
    assert git('show',base+':'+name)==(source/name).read_bytes()
(out/'static-integrity.json').write_text(json.dumps(static,indent=2)+'\n')
run_exits={'red-003':1,'green-005':1,'focused-007':1,'media-009':0,'holds-011':0,'adoption-red-013':1,'adoption-green-015':0,'strict-source-red-017':1,'strict-source-green-019':0,'freeze-check-021':0,'full-023':0,'floor-024':0,'recovery-red-026':1,'recovery-green-028':0,'final-full-030':0,'final-floor-031':0,'native-http-032':0,'package-034':0,'costs-035':0}
records=[]
for name,exit_code in run_exits.items():
    run=task/'runs'/name;destination=out/'runs'/name;destination.mkdir(parents=True,exist_ok=True)
    preflight=json.loads((run/'preflight.json').read_text())
    shutil.copyfile(run/'preflight.json',destination/'preflight.json')
    runtimes=sorted(run.glob('runtime-*.json'))
    for p in runtimes:shutil.copyfile(p,destination/p.name)
    for p in sorted((run/'logs').iterdir()):
        assert p.is_file() and p.suffix in ('.log','.json','.stdout','.stderr'),p
        shutil.copyfile(p,destination/p.name)
    if (run/'package-identities.json').exists():shutil.copyfile(run/'package-identities.json',destination/'package-identities.json')
    command=run/'logs/command.log'
    text=command.read_text() if command.exists() else ''
    summary=next((line for line in reversed(text.splitlines()) if re.search(r'\d+ (passed|failed)',line)),None)
    records.append(dict(run=name,observed_exit=exit_code,head=preflight['head'],policy=preflight['policy'],
      python=preflight['python'],summary=summary,runtime_configs=[p.name for p in runtimes],log_sha256=sha(command) if command.exists() else None))
(out/'commands-results.json').write_text(json.dumps(records,indent=2)+'\n')
for name in ['interface-proposal.md','media.json','http_smoke.py','costs.py','finalize.py','final-312.json','final-39.json','package-complete-312.json','costs-312.json','base-refs.txt']:
    shutil.copyfile(task/name,out/name)
package=json.loads((task/'runs/package-034/package-identities.json').read_text())
with tarfile.open(package['sdist']['file']) as archive:
    sdist_regular=sum(member.isfile() for member in archive.getmembers())
with zipfile.ZipFile(package['wheel']['file']) as archive:
    wheel_regular=sum(not name.endswith('/') for name in archive.namelist())
(out/'package-counts.json').write_text(json.dumps(dict(validated_sdist_files=len(package['sdist_files']),validated_wheel_files=len(package['wheel_files']),total_sdist_regular_files=sdist_regular,total_wheel_regular_files=wheel_regular,requires_python=package['requires_python'],sdist=package['sdist'],wheel=package['wheel']),indent=2)+'\n')
print('verified source/ref/editor/package identities and retained',len(records),'run records; package totals',sdist_regular,wheel_regular)
