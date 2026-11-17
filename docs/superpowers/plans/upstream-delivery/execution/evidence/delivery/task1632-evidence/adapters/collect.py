import ast,hashlib,json,pathlib,shutil,subprocess
root=pathlib.Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README')
e=root/'task1632-evidence'; runs=root/'runtime/task1632/runs'
record={}
for run in sorted(p for p in runs.iterdir() if p.is_dir()):
 target=e/'runs'/run.name; target.mkdir(parents=True,exist_ok=True)
 for path in list(run.glob('*.json'))+list((run/'logs').glob('*.log')):
  if path.is_file():
   relative=path.relative_to(run); dest=target/relative;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,dest)
 logs=[]
 for log in sorted((target/'logs').glob('*.log')):
  text=log.read_text(errors='replace')
  results=[line for line in text.splitlines() if (' passed' in line or ' failed' in line or line.startswith('SERVER_CLEANUP'))]
  logs.append({'file':str(log.relative_to(e)),'bytes':log.stat().st_size,'sha256':hashlib.sha256(log.read_bytes()).hexdigest(),'results':results[-4:]})
 record[run.name]=logs
(e/'run-index.json').write_text(json.dumps(record,indent=2)+'\n')
s=pathlib.Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=s,text=True).strip()
assert head=='8e70af446caa5ed37e0e36c029925d5caf08f943'
assert not subprocess.check_output(['git','status','--porcelain'],cwd=s,text=True).strip()
c=json.loads((e/'frozen.json').read_text())
for name,expected in c['files'].items():
 assert hashlib.sha256((s/name).read_bytes()).hexdigest()==expected
 assert hashlib.sha256(subprocess.check_output(['git','show',head+':'+name],cwd=s)).hexdigest()==expected
full=json.loads((e/'full-frozen.json').read_text())
original = subprocess.check_output(['git','show',full['head']+':openscrub.py'],cwd=s,text=True)
assert original.count('                if path:\n                    try:\n                        os.remove(path)') == 2
restored = original.replace('                if path:\n                    try:\n                        os.remove(path)', '                if path and os.path.exists(path):\n                    try:\n                        os.remove(path)')
assert restored == (s/'openscrub.py').read_text()
changed=subprocess.check_output(['git','diff','--name-only',full['head'],head],cwd=s,text=True).splitlines()
assert changed==['openscrub.py','tests/test_render_resources.py']
subprocess.run(['git','diff','--check'],cwd=s,check=True)
(e/'final-check.json').write_text(json.dumps({'head':head,'base':c['base'],'clean':True,'selected_committed_file_hashes_equal':len(c['files']),'production_sha256':c['files']['openscrub.py'],'full_suite_head':full['head'],'full_suite_production_equal':False,'full_suite_production_delta_only_two_legacy_exists_guards':True,'later_changed_files':changed,'public_source_checks':json.loads((e/'static-contract.json').read_text())},indent=2)+'\n')
print('final source identity and compact evidence recorded')
