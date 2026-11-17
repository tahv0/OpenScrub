"""Static recipe/floor inspection only, no container/frozen-runtime claim."""
import ast,hashlib,json,subprocess
from pathlib import Path
root=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
head=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD']).decode().strip()
files=subprocess.check_output(['git','-C',str(root),'ls-tree','-r','--name-only',head]).decode().splitlines()
def blob(path):return subprocess.check_output(['git','-C',str(root),'show',head+':'+path])
records={}
for path in files:
 if path.startswith('openscrub') and path.endswith('.py'):
  data=blob(path);ast.parse(data.decode(),feature_version=(3,9));records[path]=hashlib.sha256(data).hexdigest()
recipes=[p for p in files if p.startswith('Dockerfile') or p in ['docker/Dockerfile.opencv-cuda','windows/openscrub.spec','pyproject.toml','openscrub_update.py']]
for path in [p for p in recipes if p.startswith('Dockerfile')]:assert b'openscrub_internal' in blob(path),path
assert b'openscrub_internal.render_delivery' in blob('openscrub.py')
assert b'openscrub_internal.render_delivery' in blob('openscrub_vault.py')
assert b'from .reports import _staged_report' in blob('openscrub_internal/render_delivery.py')
print(json.dumps(dict(head=head,python39_grammar=records,recipes={p:hashlib.sha256(blob(p)).hexdigest() for p in recipes},frozen='static imports reachable; runtime unrun',updater='existing nested relative-path extraction retained'),indent=2))
