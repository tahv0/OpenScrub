source /tmp/openscrub-baseline-20261116/env-opencv4.sh
export PYTHONPATH=/tmp/openscrub-task119/harness:${TASK119_SOURCE:-/home/tahv0/.codex/worktrees/c832/OpenScrub}
export PYTEST_PLUGINS=task119_isolation
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
export PYTEST_ADDOPTS="-o cache_dir=/tmp/openscrub-task119/cache312 --basetemp=/tmp/openscrub-task119/tmp/pytest312"
export TMPDIR=/tmp/openscrub-task119/tmp
export XDG_CACHE_HOME=/tmp/openscrub-task119/cache
export XDG_CONFIG_HOME=/tmp/openscrub-task119/config
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1

export UV_CACHE_DIR=/tmp/openscrub-task119/cache/uv
export UV_PYTHON_INSTALL_DIR=/tmp/openscrub-task119/python
export OPENSCRUB_BASELINE_MODEL_DIR=/tmp/openscrub-task119/runtime/models
