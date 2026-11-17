"""Exact fix1 distribution/source checks; no application import or workload."""
import hashlib
import json
import os
from pathlib import Path
import tarfile
import zipfile

root = Path(os.environ['TASK1203_ROOT'])
source = Path(os.environ['TASK1203_SOURCE'])
prior = root.parent
required = list(json.loads((prior/'package-identities.json').read_text())['source_files'])
required.append('tests/test_browser_log_benchmark.py')
sdist = next((root/'dist').glob('*.tar.gz'))
wheel = next((root/'wheel').glob('*.whl'))
record = {'source_files': {}, 'sdist': {}, 'wheel': {}}
with tarfile.open(sdist) as archive:
    prefix = archive.getnames()[0].split('/')[0] + '/'
    for relative in required:
        raw = archive.extractfile(prefix+relative).read()
        assert raw == (source/relative).read_bytes(), relative
        assert raw == (root/'extracted'/prefix/relative).read_bytes(), relative
        record['source_files'][relative] = hashlib.sha256(raw).hexdigest()
with zipfile.ZipFile(wheel) as archive:
    for relative in ('openscrub.py', 'openscrub_web.py', 'zones_ui.py',
                     'openscrub_internal/__init__.py', 'openscrub_internal/job_logs.py'):
        assert archive.read(relative) == (source/relative).read_bytes(), relative
    metadata = archive.read(next(name for name in archive.namelist() if name.endswith('/METADATA'))).decode()
    assert 'Requires-Python: >=3.9' in metadata
for label, path in (('sdist', sdist), ('wheel', wheel)):
    record[label] = {'file': path.name, 'bytes': path.stat().st_size,
                     'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
old_wheel = next((prior/'wheel').glob('*.whl'))
record['wheel_identical_to_reviewed_candidate'] = wheel.read_bytes() == old_wheel.read_bytes()
assert record['wheel_identical_to_reviewed_candidate']
assert record['source_files']['openscrub_web.py'] == '04af11cce1eaf4be0dc157ba5b4d78783a85bcbbb17596078c75d9df79f46c93'
record['limits'] = 'Exact source/recipe/test sdist inclusion and identical runtime wheel; no suite/browser/timing/startup rerun.'
(root/'package-identities.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record,indent=2))
