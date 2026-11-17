import ast
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import zipfile

root = Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
art = Path('/tmp/openscrub-task109')
base = 'e21ebdf6e3ee46e6c65050dc956a9a3459152269'
files = [x for x in subprocess.check_output(['git', 'ls-files'], cwd=root, text=True).splitlines() if (root / x).is_file()]
files.append('tests/test_hdr_decoder_cleanup.py')
manifest = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in sorted(set(files))}
(art / 'tested-source-sha256.json').write_text(json.dumps(manifest, indent=2) + '\n')
engine = (root / 'openscrub.py').read_bytes()
baseline = subprocess.check_output(['git', 'show', base + ':openscrub.py'], cwd=root)
assert engine.replace(b'                else:\n                    pr.stdout.close()\n', b'', 1) == baseline
with tarfile.open(next((art / 'dist').glob('*.tar.gz'))) as archive:
    prefix = archive.getnames()[0].split('/')[0]
    names = ['openscrub.py', 'openscrub_web.py', 'zones_ui.py', 'openscrub_setup.py', 'openscrub_update.py', 'openscrub_vault.py', 'pyproject.toml', 'test_openscrub.py', 'tests/test_hdr_decoder_cleanup.py', 'CONTRIBUTING.md']
    for name in names:
        assert archive.extractfile(prefix + '/' + name).read() == (root / name).read_bytes(), name
with zipfile.ZipFile(next((art / 'dist').glob('*.whl'))) as wheel:
    for name in ['openscrub.py', 'openscrub_web.py', 'zones_ui.py', 'openscrub_setup.py', 'openscrub_update.py', 'openscrub_vault.py']:
        assert wheel.read(name) == (root / name).read_bytes(), name
        ast.parse(wheel.read(name), feature_version=(3, 9))
    assert not any(name.startswith('tests/') for name in wheel.namelist())
for name in ('openscrub.py', 'tests/test_hdr_decoder_cleanup.py'):
    ast.parse((root / name).read_text(), feature_version=(3, 9))
result = {'base': base, 'engine_sha256': manifest['openscrub.py'],
          'source_delta_only_decoder_close': True, 'unchanged_encoder_defaults_and_other_engine_bytes': True,
          'sdist_source_tests_contributor_bytes': True, 'wheel_source_bytes': True,
          'python39_grammar': True, 'frozen_files': len(manifest)}
(art / 'packaging.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
