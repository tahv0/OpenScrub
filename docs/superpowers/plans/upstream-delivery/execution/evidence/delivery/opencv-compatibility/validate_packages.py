import ast
import email
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import zipfile

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

root = Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
art = Path('/tmp/openscrub-task91')
candidate = Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README/opencv-resolution-evidence/core-candidate.in')
assert hashlib.sha256(candidate.read_bytes()).hexdigest() == 'a953b90959297225f8b361917b7e1e733262b128e7b0275fd126b13cf86463ca'
def normalized(values):
    return sorted((canonicalize_name(r.name), str(r.specifier)) for r in map(Requirement, values))
expected = normalized(candidate.read_text().splitlines())
# Read declarations independently without requiring tomllib on the floor runtime.
project = (root / 'pyproject.toml').read_text()
core_section = project.split('dependencies = [', 1)[1].split('\n]', 1)[0]
source_deps = [ast.literal_eval(line.split('#',1)[0].strip().rstrip(',')) for line in core_section.splitlines()
               if line.strip().startswith('"')]
assert normalized(source_deps) == expected
requirements = [l.strip() for l in (root/'requirements.txt').read_text().splitlines() if l.strip() and not l.startswith('#')]
assert normalized(requirements) == sorted(expected + [('spacy', '')])
installer_ast = ast.parse((root/'install.py').read_text())
core = next(ast.literal_eval(n.value) for n in installer_ast.body if isinstance(n, ast.Assign) and
            any(isinstance(t, ast.Name) and t.id == 'CORE_PKGS' for t in n.targets))
assert normalized(core) == [('cryptography', ''), ('flask', ''), ('opencv-python', '<5'), ('pillow', ''), ('pytesseract', ''), ('pyyaml', ''), ('rapidfuzz', '')]
wheel = next((art/'dist').glob('*.whl'))
sdist = next((art/'dist').glob('*.tar.gz'))
with zipfile.ZipFile(wheel) as z:
    names = z.namelist()
    wheel_meta = email.message_from_bytes(z.read(next(n for n in names if n.endswith('/METADATA'))))
    assert {'openscrub_internal/__init__.py', 'openscrub_internal/opencv_compat.py', 'plate_models.json',
            'face_models.json', 'person_models.json', 'openscrub.ico', 'openscrub_THIRD_PARTY_NOTICES.md'} <= set(names)
    assert not any(n.endswith(('.onnx', '.xml', '.pt')) for n in names)
with tarfile.open(sdist) as tar:
    snames = tar.getnames()
    sdist_meta = email.message_from_bytes(tar.extractfile(next(n for n in snames if n.endswith('/PKG-INFO'))).read())
    assert any(n.endswith('/openscrub_internal/opencv_compat.py') for n in snames)
    assert any(n.endswith('/tests/test_opencv_compat.py') for n in snames)
    assert any(n.endswith('/tests/test_install_opencv_compat.py') for n in snames)
for meta in (wheel_meta, sdist_meta):
    assert meta['Requires-Python'] == '>=3.9'
    deps = meta.get_all('Requires-Dist')
    assert normalized(d for d in deps if Requirement(d).marker is None) == expected
    assert len([d for d in deps if Requirement(d).marker is not None]) == 2
    assert all(Requirement(d).name == 'spacy' for d in deps if Requirement(d).marker is not None)

# Existing source updater: real built release and local file:// transport.
spec = importlib.util.spec_from_file_location('task91_updater', root/'openscrub_update.py')
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)
synthetic = art/'synthetic-update'
synthetic.mkdir(exist_ok=True)
preserved = {}
for name in ('models/local.onnx', 'certs/local.key', 'openscrub_jobs/job/synthetic.txt', 'zones.json', 'allowlist.txt'):
    p = synthetic/name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b'synthetic-local-data\n')
    preserved[name] = hashlib.sha256(p.read_bytes()).hexdigest()
old_helper = synthetic/'openscrub_internal/opencv_compat.py'
old_helper.parent.mkdir(exist_ok=True)
old_helper.write_text('old helper\n')
registry = json.loads((root/'plate_models.json').read_text())
entries = registry if isinstance(registry, list) else registry['models']
pinnable = next(m for m in entries if not m.get('sha256'))
pinnable['sha256'] = 'a'*64
(synthetic/'plate_models.json').write_text(json.dumps(registry))
updater.HERE = str(synthetic)
updater.current_version = lambda: 'synthetic-old'
def forbidden(*args, **kwargs):
    raise AssertionError('source updater must not invoke subprocess/pip')
original_run = subprocess.run
subprocess.run = forbidden
try:
    logs = []
    updater.update_source(dict(sdist_url=sdist.as_uri(), sha256=hashlib.sha256(sdist.read_bytes()).hexdigest()), logs.append)
finally:
    subprocess.run = original_run
assert old_helper.read_bytes() == (root/'openscrub_internal/opencv_compat.py').read_bytes()
assert next((synthetic/'backups').glob('*/openscrub_internal/opencv_compat.py')).read_text() == 'old helper\n'
assert all(hashlib.sha256((synthetic/n).read_bytes()).hexdigest() == h for n,h in preserved.items())
updated = json.loads((synthetic/'plate_models.json').read_text())
updated_entries = updated if isinstance(updated,list) else updated['models']
assert next(m for m in updated_entries if m['id'] == pinnable['id'])['sha256'] == 'a'*64

# Preserve provider/default/source files byte-for-byte against the exact base.
base = 'e21ebdf6e3ee46e6c65050dc956a9a3459152269'
unchanged = ['openscrub.py', 'openscrub_web.py', 'openscrub_gui.py', 'openscrub_update.py',
             'docker/Dockerfile.opencv-cuda', 'windows/openscrub.spec', '.github/workflows/opencv-cuda-base.yml',
             'plate_models.json', 'face_models.json', 'person_models.json', 'THIRD_PARTY_NOTICES.md', 'assets/openscrub.ico']
for name in unchanged:
    assert (root/name).read_bytes() == subprocess.check_output(['git','show',base+':'+name], cwd=root)
# Standalone provider function and Docker CUDA steps stay identical; only helper COPY added to images.
old_install = subprocess.check_output(['git','show',base+':install.py'], cwd=root).decode()
def function_source(source, name):
    tree = ast.parse(source)
    return ast.dump(next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name))
assert function_source(old_install, 'step_paddle') == function_source((root/'install.py').read_text(), 'step_paddle')
for name in ('Dockerfile','Dockerfile.cuda','Dockerfile.intel'):
    old = subprocess.check_output(['git','show',base+':'+name], cwd=root).decode()
    new = (root/name).read_text().replace('COPY openscrub_internal/ openscrub_internal/\n','')
    assert old == new
result = dict(candidate_sha256=hashlib.sha256(candidate.read_bytes()).hexdigest(), source_declarations=source_deps,
              wheel=str(wheel), sdist=str(sdist), requires_python=wheel_meta['Requires-Python'], requires_dist=wheel_meta.get_all('Requires-Dist'),
              wheel_files=names, sdist_files=snames, updater_logs=logs, preserved_hashes=preserved,
              unchanged_source_provider_files=unchanged, standalone_paddle_ast_identical=True, docker_only_helper_copy=True)
(art/'package-updater-evidence.json').write_text(json.dumps(result, indent=2))
print('PASS: candidate/source/built metadata, payloads, synthetic nested updater/local-data/pins/nonmutation, provider/default preservation')
