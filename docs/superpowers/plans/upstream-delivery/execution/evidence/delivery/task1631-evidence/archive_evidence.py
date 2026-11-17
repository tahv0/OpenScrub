"""Retain compact task-owned evidence only; never copy media/env/install trees."""
import ast,hashlib,json,shutil
from pathlib import Path
root=Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README/runtime/task1631')
evidence=Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README/task1631-evidence')
assert not (root/'runs/.verification-active').exists()
config=json.loads((root/'final312.json').read_text());src=Path(config['source'])
for path in root.iterdir():
    if path.is_file() and path.suffix in {'.json','.log','.py'}:
        shutil.copyfile(path,evidence/path.name)
shutil.copytree(root/'adapters',evidence/'adapters',dirs_exist_ok=True)
for run in sorted((root/'runs').iterdir()):
    if not run.is_dir():continue
    target=evidence/'runs'/run.name;target.mkdir(parents=True,exist_ok=True)
    for path in run.iterdir():
        if path.is_file() and (path.name in {'owner.json','preflight.json','package-identities.json'} or path.name.startswith('runtime-')):
            shutil.copyfile(path,target/path.name)
    if (run/'logs').exists():shutil.copytree(run/'logs',target/'logs',dirs_exist_ok=True)
# Recover the exact first RED/GREEN test artifact from its unchanged prefix,
# reversing only the later tight-coverage parametrization, and verify the pin.
source=(src/'tests/test_render_geometry.py').read_text()
node=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='test_actual_frame_derived_overflow')
initial=''.join(source.splitlines(True)[:node.end_lineno])
initial=initial.replace('if where.startswith("run"):', 'if where == "run":').replace('encoder="cpu", coverage=("tight" if where == "run_tight" else "concealed"))','encoder="cpu", coverage="concealed")').replace('["run", "run_tight", "sdr", "hdr"]','["run", "sdr", "hdr"]')
first=next((root/'runs/task1631-cf317cc67d7c44b6bff73f9a0a42675f').glob('runtime-*.json'))
expected=json.loads(first.read_text())['files']['tests/test_render_geometry.py']
assert hashlib.sha256(initial.encode()).hexdigest()==expected
(evidence/'initial-owning-tests.py').write_text(initial)
keys=['openscrub.py','openscrub_web.py','pyproject.toml','test_openscrub.py','tests/test_render_geometry.py']
(evidence/'source-final.json').write_text(json.dumps(dict(base=config['base'],head=config['head'],files={p:dict(bytes=(src/p).stat().st_size,sha256=config['files'][p]) for p in keys}),indent=2)+'\n')
helper=Path('/home/tahv0/src/OpenScrub/docs/superpowers/plans/upstream-delivery/execution/tooling')
(evidence/'helper-identities.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [helper/'verify.py',helper/'verification_hook.py',helper/'sitecustomize.py',helper/'README.md']},indent=2)+'\n')
commands=[]
for path in sorted(root.glob('*.log')):
    for line in path.read_text().splitlines():
        if line.startswith('COMMAND '):commands.append(dict(log=path.name,argv=json.loads(line[8:])))
for run,options in [('task1631-cf317cc67d7c44b6bff73f9a0a42675f',[]),('task1631-9f04bb15f9584106b0bbd2a575380d55',['--tb=short'])]:
    commands.append(dict(log='runs/'+run+'/logs/command.log',argv=[config['python'],'-m','pytest',str(src/'tests/test_render_geometry.py'),'-q',*options,'--basetemp='+str(root/'runs'/run/'pytest'),'-o','cache_dir='+str(root/'runs'/run/'cache/pytest')]))
(evidence/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
# Complete compact evidence manifest, excluding itself.
manifest={str(p.relative_to(evidence)):dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(evidence.rglob('*')) if p.is_file() and p.name!='manifest.json'}
(evidence/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('EVIDENCE',len(manifest),'files',sum(p['bytes'] for p in manifest.values()),'bytes')
