import hashlib,json,subprocess,zipfile
from pathlib import Path
root=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub');art=Path('/tmp/openscrub-task651');head=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip();assert head=='ac6496810b03d8b062ab9da150aeea1e62285fed'
assert not subprocess.check_output(['git','-C',str(root),'status','--porcelain'],text=True)
manifest=json.loads((art/'verification-source.json').read_text())
for name,digest in manifest['files'].items():
 data=subprocess.check_output(['git','-C',str(root),'show',head+':'+name]);assert hashlib.sha256(data).hexdigest()==digest,name
 assert (root/name).read_bytes()==data,name
with zipfile.ZipFile(art/'dist-amended/openscrub-1.0.96-py3-none-any.whl') as wheel:
 for name in wheel.namelist():
  if name.endswith('.py'):
   data=subprocess.check_output(['git','-C',str(root),'show',head+':'+name]);assert wheel.read(name)==data,name
   assert (art/'installed/site-packages'/name).read_bytes()==data,name
refs={'pr/explicit-review-choices':'2ae3257b9752e2d976ff7a0d39955a13c133273a','pr/resilient-progress-polling':'6ae212a35b094fc9466f1616afb2c5bb5c0497f8','pr/unchanged-report-saves':'3457efac574d74a7d2377cbc0d44bb0b87462c3a','pr/opencv-fallback-compatibility':'a10e485962571a566f99225541735ab1ada1f4c0'}
for ref,sha in refs.items():assert subprocess.check_output(['git','-C',str(root),'rev-parse',ref],text=True).strip()==sha,ref
log=subprocess.check_output(['git','-C',str(root),'log','--format=%H%n%B','aa07a0664ec0b9d3d592adba19e5e1e473e906ac..HEAD'],text=True)
for sha in ['2ae3257b9752e2d976ff7a0d39955a13c133273a','6ae212a35b094fc9466f1616afb2c5bb5c0497f8','3457efac574d74a7d2377cbc0d44bb0b87462c3a','a4f064f1b12cb0a22e5090d7fddfa3fc6055b5d7','a10e485962571a566f99225541735ab1ada1f4c0']:assert '(cherry picked from commit '+sha+')' in log,sha
result={'base':'aa07a0664ec0b9d3d592adba19e5e1e473e906ac','head':head,'clean':True,'frozen_committed_files':len(manifest['files']),'wheel_installed_source_exact_commit':True,'candidate_refs':refs,'all_x_provenance_present':True,'artifacts':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (art/'dist-amended').glob('*')}}
(art/'committed-bytes.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
