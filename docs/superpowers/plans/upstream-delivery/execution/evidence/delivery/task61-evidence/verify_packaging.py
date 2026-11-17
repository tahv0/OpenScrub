import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import zipfile

ROOT = Path('/tmp/openscrub-task61')
DIST = ROOT / 'dist'
wheel = next(DIST.glob('*.whl'))
sdist = next(DIST.glob('*.tar.gz'))
package = {'openscrub_internal/__init__.py', 'openscrub_internal/reports.py'}
with zipfile.ZipFile(wheel) as archive:
    assert package <= set(archive.namelist())
    assert not any(name.startswith('tests/') for name in archive.namelist())
with tarfile.open(sdist) as archive:
    names = {name.split('/', 1)[-1] for name in archive.getnames()}
    assert package | {'tests/test_large_report_io.py'} <= names
    # Every path was produced by our local build; extract only to task scratch.
    archive.extractall(ROOT / 'source')
source = next((ROOT / 'source').glob('openscrub-*'))
installed = ROOT / 'installed'
subprocess.run(['/tmp/openscrub-baseline-20261116/bootstrap/bin/python', '-m', 'pip',
                'install', '--no-deps', '--no-cache-dir', '--upgrade', '--target',
                str(installed), str(wheel)], check=True)
results = {'wheel_package': sorted(package), 'sdist_tests': True, 'startup': {}}
for name, location in [('wheel', installed), ('source', source)]:
    env = dict(os.environ, PYTHONPATH=str(location) + os.pathsep + os.environ.get('PYTHONPATH', ''))
    for module in ('openscrub', 'openscrub_web'):
        result = subprocess.run([sys.executable, '-m', module, '--help'], cwd=ROOT,
                                env=env, capture_output=True, text=True, check=True)
        assert 'usage:' in result.stdout
    code = "import openscrub,openscrub_web,openscrub_internal.reports as r; print(openscrub.__file__); print(openscrub_web.__file__); print(r.__file__)"
    result = subprocess.run([sys.executable, '-c', code], cwd=ROOT, env=env,
                            capture_output=True, text=True, check=True)
    assert all(str(location) in line for line in result.stdout.splitlines())
    results['startup'][name] = result.stdout.splitlines()
# Exercise the real source updater with the locally built archive, no network.
sys.path.insert(0, str(source))
import openscrub_update as updater
uproot = ROOT / 'update-target'
uproot.mkdir(exist_ok=True)
sentinels = {'openscrub_jobs/synthetic/report.json': b'{"local": true}',
             'models/synthetic.onnx': b'synthetic placeholder, not a model',
             'certs/key.pem': b'synthetic placeholder, not a key',
             'zones.json': b'{"local": []}', 'allowlist.txt': b'synthetic'}
for name, value in sentinels.items():
    path = uproot / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value)
updater.HERE = str(uproot)
blob = sdist.read_bytes()
updater.urllib.request.urlopen = lambda *a, **kw: io.BytesIO(blob)
updater.update_source({'sdist_url': 'local-synthetic', 'sha256': hashlib.sha256(blob).hexdigest()}, print)
assert all((uproot / name).read_bytes() == value for name, value in sentinels.items())
assert all((uproot / name).read_bytes() == (source / name).read_bytes() for name in package)
results['updater'] = {'nested_package_installed': True, 'preserved_synthetic_sentinels': sorted(sentinels)}
(ROOT / 'packaging-results.json').write_text(json.dumps(results, indent=2))
print(json.dumps(results, indent=2))
