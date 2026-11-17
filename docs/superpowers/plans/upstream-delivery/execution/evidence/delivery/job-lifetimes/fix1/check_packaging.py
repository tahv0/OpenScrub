import ast
import copy
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import tarfile
import zipfile

ROOT=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
ART=Path('/tmp/openscrub-task621/fix1')
FIX_BASE='4479b57612f4e5c463d31900f76277a5fcebb8a9'
BASE='3795d49f6293baf7b8c35534862a4881447e1b16'
def git(*args):
    return subprocess.check_output(['git','-C',str(ROOT),*args])
def old(name):
    return git('show',FIX_BASE+':'+name).decode()
def dump(node):
    return ast.dump(node,include_attributes=False)
def function(tree,name):
    return next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
sources=['openscrub.py','openscrub_web.py']+sorted(p.relative_to(ROOT).as_posix() for p in (ROOT/'openscrub_internal').glob('*.py'))
tests=sorted(p.relative_to(ROOT).as_posix() for p in (ROOT/'tests').glob('test_*.py'))
with tarfile.open(next((ART/'dist').glob('*.tar.gz'))) as archive:
    members={n.split('/',1)[1]:n for n in archive.getnames() if '/' in n}
    for name in sources+tests+['test_openscrub.py','pyproject.toml','README.md']:
        assert archive.extractfile(members[name]).read()==(ROOT/name).read_bytes(),name
    for name,member in members.items():
        if name.endswith('.py'):
            ast.parse(archive.extractfile(member).read().decode(),filename=name,feature_version=(3,9))
    sdist_names=sorted(members)
with zipfile.ZipFile(next((ART/'dist').glob('*.whl'))) as archive:
    for name in sources:
        assert archive.read(name)==(ROOT/name).read_bytes(),name
    for name in archive.namelist():
        if name.endswith('.py'):
            ast.parse(archive.read(name).decode(),filename=name,feature_version=(3,9))
    wheel_names=sorted(archive.namelist())
# Engine: only the private source-selection pin and its settings exclusion.
engine=ast.parse((ROOT/'openscrub.py').read_text())
old_engine=ast.parse(old('openscrub.py'))
settings=function(engine,'_settings_dict')
settings.body[0].value.elts=[n for n in settings.body[0].value.elts if not(isinstance(n,ast.Constant) and n.value=='_report_input')]
assert dump(settings)==dump(function(old_engine,'_settings_dict'))
pipe=function(engine,'run_pipeline')
old_pipe=function(old_engine,'run_pipeline')
branch=next(n for n in pipe.body if isinstance(n,ast.If) and ast.unparse(n.test)=="getattr(args, 'from_report', None)")
old_branch=next(n for n in old_pipe.body if isinstance(n,ast.If) and ast.unparse(n.test)=="getattr(args, 'from_report', None)")
idx=next(i for i,n in enumerate(branch.body) if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id=='selected_input')
old_idx=next(i for i,n in enumerate(old_branch.body) if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id=='orig')
assert ast.unparse(branch.body[idx])=="selected_input = getattr(args, '_report_input', None)"
condition=branch.body[idx+1]
assert ast.unparse(condition.test)=='selected_input is not None'
assert [ast.unparse(n) for n in condition.body]==['args.video = selected_input']
assert [dump(n) for n in condition.orelse]==[dump(n) for n in old_branch.body[old_idx:old_idx+2]]
branch.body[idx:idx+2]=copy.deepcopy(old_branch.body[old_idx:old_idx+2])
assert dump(engine)==dump(old_engine), 'unrelated engine behavior changed'
# JS: precisely four allowlist consumer functions, no save/poll/UI changes.
web=ast.parse((ROOT/'openscrub_web.py').read_text())
old_web=ast.parse(old('openscrub_web.py'))
def js(tree):
    return next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='APP_JS' for t in n.targets))
current_js,base_js=js(web),js(old_web)
start,end=base_js.index('async function loadPersist(){'),base_js.index('async function loadCertInfo(){')
new_start,new_end=current_js.index('function persistFailure(error){'),current_js.index('async function loadCertInfo(){')
new_segment=current_js[new_start:new_end]
assert current_js==base_js[:start]+new_segment+base_js[end:]
assert re.findall(r'^(?:async )?function (\w+)\(',new_segment,re.M)==['persistFailure','loadPersist','clearPersist','rmPersist']
(ART/'evaluated-app.js').write_text(current_js)
subprocess.run(['node','--check',str(ART/'evaluated-app.js')],check=True)
allowed={'_source_job_locked','_reserve_files_locked','_select_render_input','_reserve_queue_locked','enqueue','_run_job','enforce_vault_lock','allowlist','job_render'}
def filtered(tree):
    return ast.Module(body=[n for n in tree.body if not(isinstance(n,ast.FunctionDef) and n.name in allowed)
        and not(isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='APP_JS' for t in n.targets))],type_ignores=[])
assert dump(filtered(web))==dump(filtered(old_web)), 'unrelated web Python changed'
assert (ROOT/'pyproject.toml').read_bytes()==git('show',BASE+':pyproject.toml')
for docker in ['Dockerfile','Dockerfile.cuda','Dockerfile.intel']:
    assert 'COPY openscrub_internal/ openscrub_internal/' in (ROOT/docker).read_text()
assert 'openscrub_web.py' in (ROOT/'windows/openscrub.spec').read_text()
import openscrub_update as update
update.HERE=str(ART/'updated-source')
blob=next((ART/'dist').glob('*.tar.gz')).read_bytes()
update.urllib.request.urlopen=lambda *a,**k:io.BytesIO(blob)
update.update_source({'version':'1.0.96','sdist_url':'https://synthetic.invalid/source.tar.gz','sha256':hashlib.sha256(blob).hexdigest()},lambda text:None)
for name in sources:
    assert (ART/'updated-source'/name).read_bytes()==(ROOT/name).read_bytes()
result={'reviewed_base':BASE,'fix_base':FIX_BASE,'head':git('rev-parse','HEAD').decode().strip(),
    'python39_grammar_all_packaged_python':True,'exact_packaged_source_and_test_bytes':True,
    'engine_only_private_input_pin_and_settings_exclusion':True,
    'unchanged_default_engine_source_selection_branch':True,
    'js_changed_functions':['persistFailure','loadPersist','clearPersist','rmPersist'],
    'other_js_exactly_unchanged':True,'web_python_changed_functions':sorted(allowed),
    'project_and_build_metadata_unchanged':True,'actual_source_updater_inclusion':True,
    'static_container_and_frozen_inclusion':True,
    'source_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in sources},
    'sdist_tests':tests,'sdist_files':sdist_names,'wheel_files':wheel_names}
(ART/'packaging.json').write_text(json.dumps(result,indent=2))
print(json.dumps({k:v for k,v in result.items() if k not in ['sdist_files','wheel_files']},indent=2))
