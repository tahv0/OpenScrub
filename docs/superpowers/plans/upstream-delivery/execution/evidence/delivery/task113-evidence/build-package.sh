set -euo pipefail
source /tmp/openscrub-task113/env.sh
python - <<'PY'
import sys
assert sys.version_info[:2] == (3, 12), sys.version
from pathlib import Path
import shutil
root=Path('/tmp/openscrub-task113')
native=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
shutil.copytree(root/'base',root/'build-source',dirs_exist_ok=True)
for name in ['openscrub.py','pyproject.toml','benchmark/README.md','benchmark/reverse_recall.py','tests/test_reverse_recall_index.py']:
 target=root/'build-source'/name
 target.parent.mkdir(exist_ok=True,parents=True)
 shutil.copyfile(native/name,target)
PY
PYTHONPATH=/tmp/openscrub-baseline-20261116/bootstrap/lib/python3.14/site-packages python -m pip install --no-index --find-links /tmp/openscrub-task620/build-wheelhouse --target /tmp/openscrub-task113/build-tools hatchling
export PYTHONPATH=/tmp/openscrub-task113/harness:/tmp/openscrub-task113/build-tools
python -m build --sdist --no-isolation --outdir /tmp/openscrub-task113/dist /tmp/openscrub-task113/build-source
python - <<'PY'
from pathlib import Path
import tarfile
root=Path('/tmp/openscrub-task113')
(root/'sdist-source').mkdir(exist_ok=True)
with tarfile.open(root/'dist/openscrub-1.0.96.tar.gz') as archive:
 archive.extractall(root/'sdist-source',filter='data')
PY
python -m build --wheel --no-isolation --outdir /tmp/openscrub-task113/dist /tmp/openscrub-task113/sdist-source/openscrub-1.0.96
PYTHONPATH=/tmp/openscrub-baseline-20261116/bootstrap/lib/python3.14/site-packages python -m pip install --no-index --no-deps --target /tmp/openscrub-task113/installed /tmp/openscrub-task113/dist/openscrub-1.0.96-py3-none-any.whl
