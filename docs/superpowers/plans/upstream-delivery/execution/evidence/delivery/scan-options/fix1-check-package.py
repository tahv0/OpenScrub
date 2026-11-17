import hashlib
import json
from pathlib import Path
import tarfile
import zipfile

root = Path('/tmp/openscrub-task108')
source = Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
with tarfile.open(root/'fix1-dist/openscrub-1.0.96.tar.gz') as archive:
    prefix = 'openscrub-1.0.96/'
    for name in ('openscrub_web.py', 'tests/test_scan_options.py', 'test_openscrub.py', 'pyproject.toml', 'README.md'):
        assert archive.extractfile(prefix+name).read() == (source/name).read_bytes(), name
    sdist_members = archive.getnames()
with zipfile.ZipFile(root/'fix1-dist/openscrub-1.0.96-py3-none-any.whl') as archive:
    assert archive.read('openscrub_web.py') == (source/'openscrub_web.py').read_bytes()
    assert not any(n.startswith('tests/') for n in archive.namelist())
    assert b'Requires-Python: >=3.9' in archive.read('openscrub-1.0.96.dist-info/METADATA')
    wheel_members = archive.namelist()
result = {'sdist_members':sdist_members, 'wheel_members':wheel_members,
          'artifacts':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (root/'fix1-dist').iterdir()},
          'source_and_test_bytes_match':True, 'requires_python':'>=3.9'}
(root/'fix1-package-evidence.json').write_text(json.dumps(result, indent=2)+'\n')
print('sdist contains exact active source/tests/config; wheel contains exact guarded source; Python >=3.9 preserved')
