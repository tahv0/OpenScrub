source /tmp/openscrub-baseline-20261116/env-opencv4.sh
export PYTHONPATH=/tmp/openscrub-task112/harness:/home/tahv0/.codex/worktrees/c832/OpenScrub
export PYTEST_PLUGINS=task112_isolation
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
export PYTEST_ADDOPTS='-o cache_dir=/tmp/openscrub-task112/cache --basetemp=/tmp/openscrub-task112/tmp/pytest'
export TMPDIR=/tmp/openscrub-task112/tmp
export XDG_CACHE_HOME=/tmp/openscrub-task112/cache
export XDG_CONFIG_HOME=/tmp/openscrub-task112/config
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
