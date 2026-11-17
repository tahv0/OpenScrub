"""Retain compact owning records; exclude media/build/install/environment trees."""
import hashlib,json,shutil,subprocess
from pathlib import Path
out=Path(__file__).resolve().parent.parent
scratch=out.parent/'runtime/task16330/runs'
for run in scratch.iterdir():
 if not run.is_dir():continue
 dest=out/'runs'/run.name;dest.mkdir(parents=True,exist_ok=True)
 for p in run.glob('*.json'):shutil.copyfile(p,dest/p.name)
 if (run/'logs').exists():shutil.copytree(run/'logs',dest/'logs',dirs_exist_ok=True)
repo=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
for filename,args in [('assembly.diff',['diff','4a62e49d2f0896b737081cc92e1f92e9bcaee93f','8768e86dc1cd57720fd1c22eb6b539ae6bda6cde']),('resolved-packaging.diff',['diff','bce3cc327c29071d6c6c856d0f6f9a45520bfa1e^','bce3cc327c29071d6c6c856d0f6f9a45520bfa1e','--','CONTRIBUTING.md','pyproject.toml']),('commit-provenance.txt',['log','--format=fuller','4a62e49d2f0896b737081cc92e1f92e9bcaee93f..8768e86dc1cd57720fd1c22eb6b539ae6bda6cde'])]:
 (out/filename).write_bytes(subprocess.check_output(['git','-C',str(repo),*args]))
old=out.parent/'task1632-evidence/adapters/environment.py'
shutil.copyfile(old,out/'adapters/environment-collection.py')
manifest={str(p.relative_to(out)):{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(out.rglob('*')) if p.is_file() and p.name!='evidence-manifest.json'}
(out/'evidence-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(len(manifest),'compact evidence files;',sum(v['bytes'] for v in manifest.values()),'bytes')
