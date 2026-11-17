import json
import tarfile
import zipfile
from pathlib import Path
root=Path('/tmp/openscrub-task4')
source=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
sdist=root/'dist/openscrub-1.0.96.tar.gz'
wheel=root/'dist/openscrub-1.0.96-py3-none-any.whl'
with tarfile.open(sdist) as archive:
    prefix='openscrub-1.0.96/'
    for name in ['openscrub_web.py','test_openscrub.py','tests/test_scan_eta.py','pyproject.toml','README.md','CONTRIBUTING.md']:
        assert archive.extractfile(prefix+name).read() == (source/name).read_bytes(),name
    archive.extractall(root/'source')
    names=archive.getnames()
with zipfile.ZipFile(wheel) as archive:
    assert archive.read('openscrub_web.py') == (source/'openscrub_web.py').read_bytes()
    assert 'openscrub.py' in archive.namelist()
    assert not any(n.startswith('tests/') for n in archive.namelist())
    metadata=archive.read('openscrub-1.0.96.dist-info/METADATA').decode()
    assert 'Requires-Python: >=3.9' in metadata
    archive.extractall(root/'installed')
    installed=archive.namelist()
print(json.dumps({'sdist':str(sdist),'wheel':str(wheel),'sdist_files':len(names),'wheel_files':len(installed),'source_and_tests_match':True,'python_floor':'>=3.9'},indent=2))
