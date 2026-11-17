"""Run a wheel-installed console script with an isolated synthetic profile."""
import os
import runpy
import sys
from pathlib import Path
root=Path('/tmp/openscrub-task4')
profile=root/'installed-profile'
profile.mkdir(exist_ok=True)
original_expanduser=os.path.expanduser
os.path.expanduser=lambda path: str(profile) if path=='~' else original_expanduser(path)
sys.path.insert(0,str(root/'site'))
import openscrub
import openscrub_web
assert Path(openscrub.__file__).resolve().parent == root/'site'
assert Path(openscrub_web.__file__).resolve().parent == root/'site'
print('Installed modules:',openscrub.__file__,openscrub_web.__file__,flush=True)
entry=sys.argv.pop(1)
sys.argv[0]=str(root/'site/bin'/entry)
runpy.run_path(sys.argv[0],run_name='__main__')
