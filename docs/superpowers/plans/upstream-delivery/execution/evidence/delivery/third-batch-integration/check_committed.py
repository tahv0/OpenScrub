import hashlib,json,subprocess,zipfile
from pathlib import Path
root=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub');art=Path('/tmp/openscrub-task652');head=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip();assert head=='4b9bd7e576a8ae30369672b4b4722fc9752e233f'
assert not subprocess.check_output(['git','-C',str(root),'status','--porcelain'],text=True)
manifest=json.loads((art/'verification-source.json').read_text())
for name,digest in manifest['files'].items():
 data=subprocess.check_output(['git','-C',str(root),'show',head+':'+name]);assert hashlib.sha256(data).hexdigest()==digest,name
 assert (root/name).read_bytes()==data,name
with zipfile.ZipFile(art/'dist/openscrub-1.0.96-py3-none-any.whl') as wheel:
 for name in wheel.namelist():
  if name.endswith('.py'):
   data=subprocess.check_output(['git','-C',str(root),'show',head+':'+name]);assert wheel.read(name)==data,name
   assert (art/'installed/site-packages'/name).read_bytes()==data,name
refs={'pr/readable-report-serialization':'4a62e49d2f0896b737081cc92e1f92e9bcaee93f','pr/hdr-decoder-cleanup':'ded411cbec308333d1416ae3d58b4f6e918d7849','pr/hdr-chroma-coverage':'0c648c2e7d3e40304dce9ae878d14709966b1fe1','pr/invalid-polygon-fallback':'a3c3193e8dff41ec0588e66443398048a5c15ece','pr/manual-tracker-cancellation':'2004b22002b8317c26ea508ff8187acbcd0cfab2'}
for ref,sha in refs.items():assert subprocess.check_output(['git','-C',str(root),'rev-parse',ref],text=True).strip()==sha,ref
log=subprocess.check_output(['git','-C',str(root),'log','--format=%H%n%B','ac6496810b03d8b062ab9da150aeea1e62285fed..HEAD'],text=True)
for sha in refs.values():assert '(cherry picked from commit '+sha+')' in log,sha
result={'base':'ac6496810b03d8b062ab9da150aeea1e62285fed','head':head,'clean':True,'frozen_committed_files':len(manifest['files']),'wheel_installed_source_exact_commit':True,'candidate_refs':refs,'all_x_provenance_present':True,'artifacts':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (art/'dist').glob('*')}}
(art/'committed-bytes.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
