import json
from pathlib import Path
import subprocess
import sys
import tarfile
import zipfile

root = Path('/tmp/openscrub-task61')
checkout = Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
dist = root / 'fix1-dist'
wheel = next(dist.glob('*.whl'))
sdist = next(dist.glob('*.tar.gz'))
with zipfile.ZipFile(wheel) as archive:
    assert archive.read('openscrub_vault.py') == (checkout / 'openscrub_vault.py').read_bytes()
    assert archive.read('openscrub_internal/reports.py') == (checkout / 'openscrub_internal/reports.py').read_bytes()
with tarfile.open(sdist) as archive:
    for name in ('openscrub_vault.py', 'tests/test_vault_cleanup.py', 'tests/test_large_report_io.py'):
        member = next(m for m in archive.getmembers() if m.name.endswith('/' + name))
        assert archive.extractfile(member).read() == (checkout / name).read_bytes()
installed = root / 'fix1-installed'
subprocess.run(['/tmp/openscrub-baseline-20261116/bootstrap/bin/python', '-m', 'pip',
                'install', '--no-deps', '--no-cache-dir', '--target', str(installed), str(wheel)], check=True)
sys.path.insert(0, str(installed))
import openscrub_vault
from openscrub_internal import reports
assert Path(openscrub_vault.__file__).parent == installed
assert Path(reports.__file__).parent.parent == installed
print(json.dumps({'wheel_vault_matches_source': True, 'wheel_report_helper_unchanged': True,
                  'sdist_vault_and_focused_tests_match_source': True,
                  'installed_vault': openscrub_vault.__file__,
                  'installed_report_helper': reports.__file__}, indent=2))
