# Executed verification/measurement recipe; prepared environments are reused read-only.
source /tmp/openscrub-task113/env.sh
# Initial actual-base attribution, retained as a pending-STOPWORD control:
python /tmp/openscrub-task113/attribution.py
# Both exclusive matrix runs used this exact benchmark hash/settings; first head was
# the initial full-module prototype, second the final native owner:
python /tmp/openscrub-task113/compare.py --base /tmp/openscrub-task113/base --head /tmp/openscrub-task113/candidate --output /tmp/openscrub-task113/evidence/comparison.json
python /tmp/openscrub-task113/compare.py --base /tmp/openscrub-task113/base --head /home/tahv0/.codex/worktrees/c832/OpenScrub --output /tmp/openscrub-task113/evidence/comparison-corrected.json
# Native cwd /home/tahv0/.codex/worktrees/c832/OpenScrub:
python -m pytest -q tests/test_reverse_recall_index.py test_openscrub.py -k 'reverse or memory or merge_tail or dense_hold or mixed_dense'
python -m pytest -q
source /tmp/openscrub-task113/env39.sh
python -m pytest -q tests/test_reverse_recall_index.py test_openscrub.py -k 'reverse or memory or merge_tail or dense_hold or mixed_dense'
# Runtime cwd /tmp/openscrub-task113/runtime:
bash /tmp/openscrub-task113/build-package.sh
source /tmp/openscrub-task113/env.sh
TASK113_INSTALLED_ONLY=1 TASK113_SOURCE=/tmp/openscrub-task113/installed PYTHONPATH=/tmp/openscrub-task113/harness:/tmp/openscrub-task113/installed python /tmp/openscrub-task113/package-smoke.py
TASK113_INSTALLED_ONLY=1 TASK113_SOURCE=/tmp/openscrub-task113/installed PYTHONPATH=/tmp/openscrub-task113/harness:/tmp/openscrub-task113/installed python -m pytest -q --import-mode=importlib /tmp/openscrub-task113/sdist-source/openscrub-1.0.96/tests/test_reverse_recall_index.py
