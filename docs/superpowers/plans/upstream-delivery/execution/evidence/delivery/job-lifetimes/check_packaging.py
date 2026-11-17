import ast
import copy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tomllib
import zipfile

ROOT = Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
ART = Path('/tmp/openscrub-task621')
BASE = '3795d49f6293baf7b8c35534862a4881447e1b16'
def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])
sources = ['openscrub.py', 'openscrub_web.py'] + sorted(
    p.relative_to(ROOT).as_posix() for p in (ROOT/'openscrub_internal').glob('*.py'))
tests = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT/'tests').glob('test_*.py'))
wheel = next((ART/'dist').glob('*.whl'))
sdist = next((ART/'dist').glob('*.tar.gz'))
with tarfile.open(sdist) as tf:
    members = {n.split('/',1)[1]:n for n in tf.getnames() if '/' in n}
    for name in sources + tests + ['test_openscrub.py','pyproject.toml','README.md']:
        assert tf.extractfile(members[name]).read() == (ROOT/name).read_bytes(), name
    for name, member in members.items():
        if name.endswith('.py'):
            ast.parse(tf.extractfile(member).read().decode(), filename=name, feature_version=(3,9))
    sdist_names=sorted(members)
with zipfile.ZipFile(wheel) as z:
    for name in sources:
        assert z.read(name) == (ROOT/name).read_bytes(), name
    for name in z.namelist():
        if name.endswith('.py'):
            ast.parse(z.read(name).decode(), filename=name, feature_version=(3,9))
    wheel_names=sorted(z.namelist())
with zipfile.ZipFile('/tmp/openscrub-task620/dist/openscrub-1.0.96-py3-none-any.whl') as z:
    wheel_added=sorted(set(wheel_names)-set(z.namelist()))
assert wheel_added == ['openscrub_internal/lifetimes.py'], wheel_added
old_engine=ast.parse(git('show',BASE+':openscrub.py').decode())
engine=ast.parse((ROOT/'openscrub.py').read_text())
def tracker(tree):
    return next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='track_manual_region')
old_tracker,new_tracker=tracker(old_engine),tracker(engine)
class RemoveRelease(ast.NodeTransformer):
    def visit_Expr(self,node):
        if (isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Attribute)
            and isinstance(node.value.func.value,ast.Name)
            and node.value.func.value.id=='cap' and node.value.func.attr=='release'):
            return None
        return node
old_body=RemoveRelease().visit(copy.deepcopy(old_tracker))
assert ast.dump(ast.Module(body=old_body.body[3:],type_ignores=[])) == ast.dump(
    ast.Module(body=new_tracker.body[3].body,type_ignores=[]))
engine.body[engine.body.index(new_tracker)]=old_tracker
assert ast.dump(engine) == ast.dump(old_engine), 'unrelated engine behavior changed'
web=ast.parse((ROOT/'openscrub_web.py').read_text())
old_web=ast.parse(git('show',BASE+':openscrub_web.py').decode())
def app_js(tree):
    return next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign)
        and any(isinstance(t,ast.Name) and t.id=='APP_JS' for t in n.targets))
assert app_js(web)==app_js(old_web)
(ART/'evaluated-app.js').write_text(app_js(web))
subprocess.run(['node','--check',str(ART/'evaluated-app.js')],check=True)
assert (ROOT/'pyproject.toml').read_bytes() == git('show',BASE+':pyproject.toml')
for docker in ['Dockerfile','Dockerfile.cuda','Dockerfile.intel']:
    assert 'COPY openscrub_internal/ openscrub_internal/' in (ROOT/docker).read_text()
# Static PyInstaller analysis follows the web entrypoint's direct import.
assert any(isinstance(n,ast.ImportFrom) and n.module=='openscrub_internal.lifetimes' for n in web.body)
assert 'openscrub_web.py' in (ROOT/'windows/openscrub.spec').read_text()
# Exercise the actual source updater against the locally built, hash-verified sdist.
import openscrub_update as update
update.HERE=str(ART/'updated-source')
blob=sdist.read_bytes()
update.urllib.request.urlopen=lambda *a,**k: io.BytesIO(blob)
update.update_source({'version':'1.0.96','sdist_url':'https://synthetic.invalid/source.tar.gz',
    'sha256':hashlib.sha256(blob).hexdigest()},lambda text:None)
for name in sources:
    assert (ART/'updated-source'/name).read_bytes()==(ROOT/name).read_bytes()
result={'base':BASE,'head':git('rev-parse','HEAD').decode().strip(),
        'python39_grammar_all_packaged_python':True,'unchanged_app_js':True,
        'engine_ast_only_capture_finally':True,'project_build_requirements_unchanged':True,
        'wheel_added_vs_task620':wheel_added,'exact_source_bytes':sources,
        'sdist_tests':tests,'static_container_and_frozen_inclusion':True,
        'actual_source_updater_installed_helper':True,
        'source_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sources},
        'sdist_files':sdist_names,'wheel_files':wheel_names}
(ART/'packaging.json').write_text(json.dumps(result,indent=2))
print(json.dumps({k:v for k,v in result.items() if k not in ('sdist_files','wheel_files')},indent=2))
