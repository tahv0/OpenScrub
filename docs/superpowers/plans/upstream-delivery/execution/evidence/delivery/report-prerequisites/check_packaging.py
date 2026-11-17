import ast
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import tomllib
import zipfile

ROOT = Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
ART = Path('/tmp/openscrub-task620')
BASE = '7063082ef2a2ff5e56d9aafacff9bd43363b05b3'
def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])
def digest(data):
    return hashlib.sha256(data).hexdigest()

tree = ast.parse((ROOT / 'openscrub_web.py').read_text(), feature_version=(3, 9))
js = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
    and any(isinstance(t, ast.Name) and t.id == 'APP_JS' for t in n.targets))
(ART / 'evaluated-app.js').write_text(js)
subprocess.run(['node', '--check', str(ART / 'evaluated-app.js')], check=True)
for name in ('VIEW_GEN', 'REVIEW_DRAFTS', 'audioInFlight', 'acknowledgeAdds', 'saveAndRender'):
    assert name in js
sources = ['openscrub.py', 'openscrub_web.py', 'openscrub_internal/__init__.py',
           'openscrub_internal/reports.py']
tests = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / 'tests').glob('test_*.py'))
with tarfile.open(ART / 'dist/openscrub-1.0.96.tar.gz') as tf:
    members = {n.split('/', 1)[1]: n for n in tf.getnames() if '/' in n}
    for p in sources + tests + ['test_openscrub.py', 'pyproject.toml', 'README.md']:
        assert tf.extractfile(members[p]).read() == (ROOT / p).read_bytes(), p
    sdist_names = sorted(members)
with zipfile.ZipFile(ART / 'dist/openscrub-1.0.96-py3-none-any.whl') as z:
    wheel_names = sorted(z.namelist())
    for p in sources:
        assert z.read(p) == (ROOT / p).read_bytes(), p
    for p in z.namelist():
        if p.endswith('.py'):
            ast.parse(z.read(p).decode(), filename=p, feature_version=(3, 9))
with tarfile.open('/tmp/openscrub-task64-dist/openscrub-1.0.96.tar.gz') as tf:
    old_sdist_names = {n.split('/', 1)[1] for n in tf.getnames() if '/' in n}
with zipfile.ZipFile('/tmp/openscrub-task64-dist/openscrub-1.0.96-py3-none-any.whl') as z:
    old_wheel_names = set(z.namelist())
sdist_added = sorted(set(sdist_names) - old_sdist_names)
wheel_added = sorted(set(wheel_names) - old_wheel_names)
assert sdist_added == ['tests/test_review_save_failures.py'], sdist_added
assert wheel_added == [], wheel_added
current = tomllib.loads((ROOT / 'pyproject.toml').read_text())
old = tomllib.loads(git('show', BASE + ':pyproject.toml').decode())
for section in ('project', 'build-system'):
    assert current[section] == old[section]
def imports(src):
    return sorted(ast.dump(n) for n in ast.walk(ast.parse(src))
                  if isinstance(n, (ast.Import, ast.ImportFrom)))
assert imports((ROOT / 'openscrub_web.py').read_text()) == imports(git('show', BASE + ':openscrub_web.py').decode())
assert git('diff', '--name-only', BASE, 'HEAD').decode().splitlines() == [
    'README.md', 'openscrub_web.py', 'pyproject.toml', 'tests/test_review_save_failures.py']
result = {'head': git('rev-parse', 'HEAD').decode().strip(),
 'python39_grammar_all_packaged_python': True, 'evaluated_app_js_node_parse': True,
 'sdist_exact_bytes': sources + tests + ['test_openscrub.py', 'pyproject.toml', 'README.md'],
 'wheel_exact_bytes': sources, 'sdist_added_vs_p06d_build': sdist_added,
 'wheel_added_vs_p06d_build': wheel_added, 'project_and_build_requirements_unchanged': True,
 'web_python_imports_unchanged': True,
 'source_sha256': {p: digest((ROOT / p).read_bytes()) for p in sources},
 'sdist_files': sdist_names, 'wheel_files': wheel_names}
(ART / 'packaging.json').write_text(json.dumps(result, indent=2))
print(json.dumps({k:v for k,v in result.items() if k not in ('sdist_files','wheel_files')}, indent=2))
