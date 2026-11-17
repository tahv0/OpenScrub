"""Declare exact composed package members and read-only offline backend identities."""
import hashlib,json,subprocess
from pathlib import Path
out=Path(__file__).resolve().parent.parent
cfg=json.loads((out/'frozen312.json').read_text())
repo=Path(cfg['source']);head=cfg['head']
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def git(*args):return subprocess.check_output(['git','-C',str(repo),*args])
tracked=git('ls-tree','-r','--name-only',head).decode().splitlines()
extras=['plate_models.json','face_models.json','person_models.json','assets/openscrub.ico','README.md','LICENSE','NOTICE','THIRD_PARTY_NOTICES.md','install.py','requirements.txt']
recipes=[p for p in tracked if p.startswith('Dockerfile') or p in ['docker/Dockerfile.opencv-cuda','windows/openscrub.spec']]
for p in extras+recipes: cfg['files'][p]=hashlib.sha256(git('show',head+':'+p)).hexdigest()
sdist=[p for p in cfg['files'] if p not in recipes]
assert len(sdist)==len(set(sdist))
wheel=sorted(set(cfg['modules'].values())|{'plate_models.json','face_models.json','person_models.json'})
tools=out.parent/'runtime/task16330/build-tools'
bootstrap=Path('/tmp/openscrub-baseline-20261116/bootstrap/lib/python3.14/site-packages')
for p in [tools/'hatchling/build.py',bootstrap/'pip/__main__.py',Path(__file__)]+list(Path('/tmp/openscrub-task620/build-wheelhouse').glob('*.whl')):
 cfg['prerequisites'].append(dict(path=str(p),sha256=sha(p)))
cfg['package']=dict(tool_paths=[str(tools),str(bootstrap)],sdist_files=sorted(sdist),wheel_files=wheel,requires_python='>=3.9',installed_commands=[['{target}/bin/openscrub','--help'],[str(out/'adapters/listening_smoke.py'),'{target}']])
cfg['excluded_paths']=['/home/tahv0/src/OpenScrub','/home/tahv0/.codex/worktrees/c832/OpenScrub']
(out/'package.json').write_text(json.dumps(cfg,indent=2)+'\n')
(out/'package-recipes.json').write_text(json.dumps({p:dict(sha256=cfg['files'][p],unchanged_from_base=git('show',head+':'+p)==git('show',cfg['base']+':'+p)) for p in recipes},indent=2)+'\n')
print(len(cfg['files']),'source identities;',len(sdist),'sdist;',len(wheel),'wheel members;',len(recipes),'static recipes')
