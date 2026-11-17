"""Fix1 compact evidence archive; original task evidence is never rewritten."""
import hashlib,json,shutil,subprocess
from pathlib import Path
sdd=Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README');runtime=sdd/'runtime/task1631';root=runtime/'fix1';evidence=sdd/'task1631-fix1-evidence';evidence.mkdir(exist_ok=True)
assert not (runtime/'runs/.verification-active').exists()
for p in root.iterdir():
    if p.is_file() and p.suffix in {'.json','.log','.py'}:shutil.copyfile(p,evidence/p.name)
for run in sorted((runtime/'runs').glob('task1631-fix1-*')):
    dest=evidence/'runs'/run.name;dest.mkdir(parents=True,exist_ok=True)
    for p in run.iterdir():
        if p.is_file() and (p.name in {'owner.json','preflight.json','package-identities.json'} or p.name.startswith('runtime-')):shutil.copyfile(p,dest/p.name)
    if (run/'logs').exists():shutil.copytree(run/'logs',dest/'logs',dirs_exist_ok=True)
for name in ['adapters/task1631_fixture.py','listening_smoke.py']:
    dest=evidence/'adapters'/Path(name).name;dest.parent.mkdir(exist_ok=True);shutil.copyfile(runtime/name,dest)
config=json.loads((root/'final312.json').read_text());source=Path(config['source']);fixbase='7415e5a7526696a33f78a8c209bf062239a31d1c'
subprocess.run(['git','-C',str(source),'diff','--check',fixbase,config['head']],check=True)
assert not subprocess.check_output(['git','-C',str(source),'status','--porcelain'],text=True).strip()
diff=subprocess.check_output(['git','-C',str(source),'diff',fixbase,config['head']],text=True);(evidence/'fix.diff').write_text(diff)
files=['openscrub.py','tests/test_render_geometry.py','openscrub_web.py','pyproject.toml']
(evidence/'source-final.json').write_text(json.dumps(dict(base=config['base'],fix_base=fixbase,head=config['head'],files={name:dict(bytes=(source/name).stat().st_size,sha256=config['files'][name]) for name in files}),indent=2)+'\n')
shutil.copyfile(source/'tests/test_render_geometry.py',evidence/'owning-tests.py')
helper=Path('/home/tahv0/src/OpenScrub/docs/superpowers/plans/upstream-delivery/execution/tooling');identities={name:hashlib.sha256((helper/name).read_bytes()).hexdigest() for name in ['verify.py','verification_hook.py','sitecustomize.py','README.md']}
assert identities==json.loads((sdd/'task1631-evidence/helper-identities.json').read_text())
(evidence/'helper-identities.json').write_text(json.dumps(identities,indent=2)+'\n')
commands=[]
for p in sorted(root.glob('*.log')):
    for line in p.read_text().splitlines():
        if line.startswith('COMMAND '):commands.append(dict(log=p.name,argv=json.loads(line[8:])))
(evidence/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
manifest={str(p.relative_to(evidence)):dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(evidence.rglob('*')) if p.is_file() and p.name!='manifest.json'}
(evidence/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('FIX1_EVIDENCE',len(manifest),sum(v['bytes'] for v in manifest.values()))
print('CORE',config['files']['openscrub.py'],(source/'openscrub.py').stat().st_size)
