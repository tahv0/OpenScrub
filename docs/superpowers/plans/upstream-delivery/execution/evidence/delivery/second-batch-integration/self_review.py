import ast,hashlib,json,subprocess
from pathlib import Path
root=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub');art=Path('/tmp/openscrub-task651')
def old(ref,name):return subprocess.check_output(['git','-C',str(root),'show',ref+':'+name],text=True)
def fn(src,name):return next(n for n in ast.parse(src).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name==name)
web=(root/'openscrub_web.py').read_text();base='aa07a0664ec0b9d3d592adba19e5e1e473e906ac'
assert (root/'openscrub.py').read_text()==old(base,'openscrub.py')
for n in ['_same_json_value','job_save_edits']:
 assert ast.dump(fn(web,n))==ast.dump(fn(old('3457efa','openscrub_web.py'),n)),n
for n in ['_run_job','worker','_prepare_work','job_report','job_preview','job_render','job_retry']:
 try:assert ast.dump(fn(web,n))==ast.dump(fn(old(base,'openscrub_web.py'),n)),n
 except StopIteration:print('no function',n);raise
assert (root/'openscrub_internal/opencv_compat.py').read_text()==old('a10e485','openscrub_internal/opencv_compat.py')
for name in ['openscrub_setup.py','install.py','requirements.txt']:
 assert (root/name).read_text()==old('a10e485',name),name
assert '<<<<<<<' not in web
subprocess.run(['git','-C',str(root),'diff','--check'],check=True)
files=subprocess.check_output(['git','-C',str(root),'ls-files','*.py','*.toml','requirements.txt','README.md','CONTRIBUTING.md','benchmark/README.md'],text=True).splitlines()
manifest={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in files}
(art/'verification-source.json').write_text(json.dumps({'files':manifest},indent=2))
(art/'self-review.json').write_text(json.dumps({'engine_bytes_unchanged':True,'reviewed_save_route_exact_AST':True,'base_work_lifetime_preview_routes_exact_AST':True,'corrected_helper_exact_bytes':True,'core_consumers_exact_candidate_bytes':True,'frozen_files':len(files)},indent=2))
print('self-review and frozen source passed',len(files))
