import ast,json,subprocess
from pathlib import Path
root=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
def source(rev,name):return subprocess.check_output(['git','-C',str(root),'show',rev+':'+name],text=True)
def function(s,name):return next(n for n in ast.parse(s).body if isinstance(n,ast.FunctionDef) and n.name==name)
web=(root/'openscrub_web.py').read_text();engine=(root/'openscrub.py').read_text()
checks={}
for rev,file,name in [('f19be5fe3b9176e568ea7bf761493bd267fee95e','openscrub.py','smooth_dense_tracks'),('ca0f2ce7458347afd2e6156a97df580b6623767a','openscrub_web.py','export_filenames'),('b70d42011168192cdf7a9ef93a5e9419a92a1cdb','openscrub_web.py','_publish_preview_jpeg'),('b70d42011168192cdf7a9ef93a5e9419a92a1cdb','openscrub_web.py','job_preview')]:
 assert ast.dump(function((root/file).read_text(),name))==ast.dump(function(source(rev,file),name)),name
 checks[name+'_matches_reviewed_candidate']=True
eta=source('d129e23e5fe144edb8bbd5675809c1877cfe4d0f','openscrub_web.py')
def method(s,name):
 c=next(n for n in ast.parse(s).body if isinstance(n,ast.ClassDef) and n.name=='WebCallbacks')
 return next(n for n in c.body if isinstance(n,ast.FunctionDef) and n.name==name)
assert ast.dump(method(web,'progress'))==ast.dump(method(eta,'progress'))
checks['eta_progress_matches_reviewed_candidate']=True
start='// Save As exports stay bound';end='async function refresh()'
original=source('ca0f2ce7458347afd2e6156a97df580b6623767a','openscrub_web.py')
assert web[web.index(start):web.index(end)]==original[original.index(start):original.index(end)]
checks['save_as_js_matches_reviewed_candidate']=True
for fn in ['_finish_file_response','_release_failed_request','enforce_vault_lock','job_render','job_retry']:
 assert ast.dump(function(web,fn))==ast.dump(function(source('12919c96c6f7558136b50d7b4d85e5e6b62f1971','openscrub_web.py'),fn)),fn
checks['base_lifetime_admission_response_hooks_render_retry_preserved']=True
assert 'with FILES.initialize(job).report_lock:' in ast.get_source_segment(web,function(web,'job_report'))
assert 'if(!ownsView(id,gen))return;\n EXPORT_NAMES=' in web
checks['report_lock_and_refresh_generation_guards_retained']=True
for file in ['openscrub_web.py','openscrub.py','pyproject.toml','CONTRIBUTING.md','README.md']:
 assert '<<<<<<< HEAD' not in (root/file).read_text()
checks['no_conflict_markers']=True
Path('/tmp/openscrub-task650/self-review.json').write_text(json.dumps(checks,indent=2));print(json.dumps(checks,indent=2))
