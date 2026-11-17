import ast
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import zipfile
import tomllib
root=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
art=Path('/tmp/openscrub-task652')
base='ac6496810b03d8b062ab9da150aeea1e62285fed'
def old(name):return subprocess.check_output(['git','-C',str(root),'show',base+':'+name]).decode()
sources=[n for n in tomllib.loads((root/'pyproject.toml').read_text())['tool']['hatch']['build']['targets']['wheel']['include'] if n.endswith('.py')]+sorted(p.relative_to(root).as_posix() for p in (root/'openscrub_internal').glob('*.py'))
tests=sorted(p.relative_to(root).as_posix() for p in (root/'tests').glob('test_*.py'))
with tarfile.open(next((art/'dist').glob('*.tar.gz'))) as archive:
 names={n.split('/',1)[1]:n for n in archive.getnames() if '/' in n}
 for name in sources+tests+['benchmark/review_io.py','benchmark/README.md','test_openscrub.py','README.md','CONTRIBUTING.md','pyproject.toml','requirements.txt']:
  assert archive.extractfile(names[name]).read()==(root/name).read_bytes(),name
 for name,member in names.items():
  if name.endswith('.py'):ast.parse(archive.extractfile(member).read().decode(),filename=name,feature_version=(3,9))
 # Explicit supported archive filter for this extraction evidence.
 archive.extractall(art/'sdist-extracted',filter='data')
with zipfile.ZipFile(next((art/'dist').glob('*.whl'))) as archive:
 for name in sources:assert archive.read(name)==(root/name).read_bytes(),name
 assert 'Requires-Dist: opencv-python<5' in archive.read(next(n for n in archive.namelist() if n.endswith('.dist-info/METADATA'))).decode()
 for name in archive.namelist():
  if name.endswith('.py'):ast.parse(archive.read(name).decode(),filename=name,feature_version=(3,9))
 metadata=archive.read(next(n for n in archive.namelist() if n.endswith('.dist-info/METADATA'))).decode()
 assert 'Requires-Python: >=3.9' in metadata
 project=tomllib.loads((root/'pyproject.toml').read_text())['project']
 previous=tomllib.loads(old('pyproject.toml'))['project']
 previous['dependencies']=[d.replace('opencv-python', 'opencv-python<5') if d=='opencv-python' else d for d in previous['dependencies']]
 assert project==previous
 for marker in ['workbench','findings','journal','section','train']:
  assert not any(marker in name.lower() for name in archive.namelist()),marker
for name in ['requirements.txt']:
 assert (root/name).read_text()==old(name).replace('opencv-python\n','opencv-python<5\n')
def fn(source,name):return next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name==name)
for name in ['build_parser','run_pipeline','_settings_dict']:
 assert ast.dump(fn((root/'openscrub.py').read_text(),name))==ast.dump(fn(old('openscrub.py'),name)),name
assert ast.dump(fn((root/'openscrub_web.py').read_text(),'build_args'))==ast.dump(fn(old('openscrub_web.py'),'build_args'))
def routes(source):
 return [(n.name,[ast.dump(d) for d in n.decorator_list if isinstance(d,ast.Call) and isinstance(d.func,ast.Attribute) and d.func.attr=='route']) for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and any(isinstance(d,ast.Call) and isinstance(d.func,ast.Attribute) and d.func.attr=='route' for d in n.decorator_list)]
assert routes((root/'openscrub_web.py').read_text())==routes(old('openscrub_web.py'))
expected_internal=sorted(subprocess.check_output(['git','-C',str(root),'ls-tree','--name-only',base+':openscrub_internal'],text=True).splitlines())
assert sorted(p.name for p in (root/'openscrub_internal').glob('*.py'))==expected_internal
js=next(ast.literal_eval(n.value) for n in ast.parse((root/'openscrub_web.py').read_text()).body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='APP_JS' for t in n.targets))
(art/'app.js').write_text(js);subprocess.run(['node','--check',str(art/'app.js')],check=True)
manifest=json.loads((art/'verification-source.json').read_text())
for name,digest in manifest['files'].items():assert hashlib.sha256((root/name).read_bytes()).hexdigest()==digest,name
result={'base':base,'exact_sdist_sources_tests_docs_metadata':True,'exact_wheel_sources':True,'packaged_python39_grammar':True,'metadata_python_floor':'>=3.9','opencv_bound': 'opencv-python<5','unchanged_project_dependencies_entrypoints_and_defaults':True,'unchanged_web_routes_internal_modules':True,'no_removed_system_in_wheel':True,'node_syntax':True,'supported_archive_filter':'data','frozen_manifest_matched':True,'source_count':len(sources),'focused_test_files':len(tests)}
(art/'packaging.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
