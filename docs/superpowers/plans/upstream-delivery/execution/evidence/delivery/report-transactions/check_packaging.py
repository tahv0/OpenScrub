import ast
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import zipfile

root=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
art=Path('/tmp/openscrub-task622')
base='c697d5a686d4dccbdf4f474567628d5d24e75a03'
def old(name):
    return subprocess.check_output(['git','-C',str(root),'show',base+':'+name]).decode()
sources=['openscrub.py','openscrub_web.py']+sorted(p.relative_to(root).as_posix() for p in (root/'openscrub_internal').glob('*.py'))
tests=sorted(p.relative_to(root).as_posix() for p in (root/'tests').glob('test_*.py'))
with tarfile.open(next((art/'dist').glob('*.tar.gz'))) as archive:
    names={n.split('/',1)[1]:n for n in archive.getnames() if '/' in n}
    for name in sources+tests+['test_openscrub.py','README.md','pyproject.toml']:
        assert archive.extractfile(names[name]).read()==(root/name).read_bytes(), name
    for name, member in names.items():
        if name.endswith('.py'):
            ast.parse(archive.extractfile(member).read().decode(),filename=name,feature_version=(3,9))
with zipfile.ZipFile(next((art/'dist').glob('*.whl'))) as archive:
    for name in sources:
        assert archive.read(name)==(root/name).read_bytes(), name
    for name in archive.namelist():
        if name.endswith('.py'):
            ast.parse(archive.read(name).decode(),filename=name,feature_version=(3,9))
# Explicitly verify unchanged public setup/defaults, pinned selection, and JS.
def fn(source,name):
    return next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name==name)
for name in ['build_parser','run_pipeline','_settings_dict']:
    assert ast.dump(fn((root/'openscrub.py').read_text(),name))==ast.dump(fn(old('openscrub.py'),name)),name
assert ast.dump(fn((root/'openscrub_web.py').read_text(),'build_args'))==ast.dump(fn(old('openscrub_web.py'),'build_args'))
def js(source):
    return next(ast.literal_eval(n.value) for n in ast.parse(source).body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='APP_JS' for t in n.targets))
assert js((root/'openscrub_web.py').read_text())==js(old('openscrub_web.py'))
(art/'app.js').write_text(js((root/'openscrub_web.py').read_text()))
subprocess.run(['node','--check',str(art/'app.js')],check=True)
assert (root/'pyproject.toml').read_text()==old('pyproject.toml')
for name in ['Dockerfile','Dockerfile.cuda','Dockerfile.intel']:
    assert 'COPY openscrub_internal/ openscrub_internal/' in (root/name).read_text()
assert 'openscrub_web.py' in (root/'windows/openscrub.spec').read_text()
result={'base':base,'head':subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD']).decode().strip(),
        'exact_sdist_source_and_tests':True,'exact_wheel_source':True,'all_packaged_python39_grammar':True,
        'unchanged_cli_defaults_web_build_args_source_pin_and_js':True,'node_syntax':True,
        'unchanged_project_metadata':True,'static_container_frozen_inclusion':True,
        'sha256':{name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in sources}}
(art/'packaging.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
