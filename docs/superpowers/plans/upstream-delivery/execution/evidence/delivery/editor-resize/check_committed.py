import hashlib,json,subprocess,zipfile
from pathlib import Path
root=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub');art=Path('/tmp/openscrub-task164')
head=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()
assert head=='47e9f6d5614365e00d899c87df6c209cd7aaabf6'
assert not subprocess.check_output(['git','-C',str(root),'status','--porcelain'],text=True)
assert subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD^'],text=True).strip()=='92124753736e287ac800af91f0ac96f3e96c01be'
manifest=json.loads((art/'verification-source.json').read_text())
for name,digest in manifest['files'].items():
 data=subprocess.check_output(['git','-C',str(root),'show',head+':'+name]);assert hashlib.sha256(data).hexdigest()==digest,name
 assert data==(root/name).read_bytes(),name
red=json.loads((art/'final-red-binding.json').read_text())
for name,digest in red['test_files'].items():assert manifest['files'][name]==digest,name
with zipfile.ZipFile(next((art/'dist').glob('*.whl'))) as archive:
 for name in archive.namelist():
  if name.endswith('.py'):
   data=subprocess.check_output(['git','-C',str(root),'show',head+':'+name]);assert archive.read(name)==data,name
   assert (art/'installed/site-packages'/name).read_bytes()==data,name
result={'base':manifest['base'],'head':head,'clean':True,'committed_manifest_files':len(manifest['files']),'exact_final_test_bytes_fail_on_baseline':True,'wheel_and_installed_source_match_commit':True}
(art/'committed-bytes.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
