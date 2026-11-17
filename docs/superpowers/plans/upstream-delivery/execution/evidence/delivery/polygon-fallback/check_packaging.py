import ast
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import zipfile
root=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
art=Path('/tmp/openscrub-task162')
files=[n for n in subprocess.check_output(['git','ls-files'],cwd=root,text=True).splitlines() if (root/n).is_file()]
files.append('tests/test_polygon_fallback.py')
manifest={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in sorted(set(files))}
(art/'tested-source-sha256.json').write_text(json.dumps(manifest,indent=2)+'\n')
names=['openscrub.py','openscrub_web.py','zones_ui.py','openscrub_setup.py','openscrub_update.py','openscrub_vault.py']
with tarfile.open(next((art/'dist').glob('*.tar.gz'))) as archive:
    prefix=archive.getnames()[0].split('/')[0]
    for name in names+['pyproject.toml','test_openscrub.py','tests/test_polygon_fallback.py','CONTRIBUTING.md','README.md']:
        assert archive.extractfile(prefix+'/'+name).read()==(root/name).read_bytes(),name
with zipfile.ZipFile(next((art/'dist').glob('*.whl'))) as wheel:
    for name in names:
        assert wheel.read(name)==(root/name).read_bytes(),name
        ast.parse(wheel.read(name),feature_version=(3,9))
    assert not any(n.startswith('tests/') for n in wheel.namelist())
ast.parse((root/'tests/test_polygon_fallback.py').read_text(),feature_version=(3,9))
result={'sdist_source_tests_guidance_bytes':True,'wheel_source_bytes':True,'python39_grammar':True,'frozen_files':len(manifest),'engine_sha256':manifest['openscrub.py'],'test_sha256':manifest['tests/test_polygon_fallback.py']}
(art/'packaging.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
