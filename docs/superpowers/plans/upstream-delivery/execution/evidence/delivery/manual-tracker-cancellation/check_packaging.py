import ast
import hashlib
import inspect
import json
from pathlib import Path
import subprocess
import tarfile
import zipfile

root=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
art=Path('/tmp/openscrub-task110')
base='12919c96c6f7558136b50d7b4d85e5e6b62f1971'
files=[n for n in subprocess.check_output(['git','ls-files'],cwd=root,text=True).splitlines() if (root/n).is_file()]
files.append('tests/test_manual_tracker_cancel.py')
manifest={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in sorted(set(files))}
(art/'tested-source-sha256.json').write_text(json.dumps(manifest,indent=2)+'\n')
# Compare every packaged Python source/test against active checkout bytes.
with tarfile.open(next((art/'dist').glob('*.tar.gz'))) as archive:
    prefix=archive.getnames()[0].split('/')[0]
    sd_names=[n[len(prefix)+1:] for n in archive.getnames()
              if n.endswith('.py') or n.endswith('/pyproject.toml') or n.endswith('/README.md')]
    for n in sd_names:
        assert archive.extractfile(prefix+'/'+n).read()==(root/n).read_bytes(),n
    assert 'tests/test_manual_tracker_cancel.py' in sd_names
    assert all(n in sd_names for n in files if n.startswith('tests/') and n.endswith('.py'))
with zipfile.ZipFile(next((art/'dist').glob('*.whl'))) as wheel:
    wh_names=[n for n in wheel.namelist() if n.endswith('.py')]
    for n in wh_names:
        assert wheel.read(n)==(root/n).read_bytes(),n
        ast.parse(wheel.read(n),feature_version=(3,9))
    assert not any(n.startswith('tests/') for n in wheel.namelist())
    assert 'Requires-Python: >=3.9' in wheel.read('openscrub-1.0.96.dist-info/METADATA').decode()
for n in sd_names:
    if n.endswith('.py'):
        ast.parse((root/n).read_text(),feature_version=(3,9))
# Entire pyproject unchanged: dependencies, supported Python, build defaults.
assert subprocess.check_output(['git','show',base+':pyproject.toml'],cwd=root)==(root/'pyproject.toml').read_bytes()
old=ast.parse(subprocess.check_output(['git','show',base+':openscrub.py'],cwd=root))
new=ast.parse((root/'openscrub.py').read_text())
old_def=next(n for n in old.body if isinstance(n,ast.FunctionDef) and n.name=='track_manual_region')
new_def=next(n for n in new.body if isinstance(n,ast.FunctionDef) and n.name=='track_manual_region')
assert ast.dump(old_def.args)==ast.dump(new_def.args)
# Product edits confined to this function; other engine definitions byte-identical.
def excluding_tracker(data):
    start=data.index(b'def track_manual_region(');end=data.index(b'\ndef group_persons(',start)
    return data[:start]+data[end:]
assert excluding_tracker(subprocess.check_output(['git','show',base+':openscrub.py'],cwd=root))==excluding_tracker((root/'openscrub.py').read_bytes())
result={'base':base,'sdist_exact_files':len(sd_names),'wheel_exact_python_files':len(wh_names),
        'all_python39_grammar':True,'unchanged_pyproject_and_tracker_signature_defaults':True,
        'engine_delta_confined_to_track_manual_region':True,'frozen_files':len(manifest),
        'engine_sha256':manifest['openscrub.py'],'test_sha256':manifest['tests/test_manual_tracker_cancel.py']}
(art/'packaging.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
