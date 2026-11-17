source /tmp/openscrub-python39-20261117/env.sh
export PYTHONPATH=/tmp/openscrub-task115/harness:${TASK115_SOURCE:-/home/tahv0/.codex/worktrees/c832/OpenScrub}
export PYTEST_PLUGINS=task115_isolation
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
export PYTEST_ADDOPTS="-o cache_dir=/tmp/openscrub-task115/cache39 --basetemp=/tmp/openscrub-task115/tmp/pytest39"
export TMPDIR=/tmp/openscrub-task115/tmp
export XDG_CACHE_HOME=/tmp/openscrub-task115/cache
export XDG_CONFIG_HOME=/tmp/openscrub-task115/config
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
