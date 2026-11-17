#!/bin/bash
set -eu
TASK_ROOT=/tmp/openscrub-python39-20261117
export UV_CACHE_DIR="$TASK_ROOT/uv-cache"
export UV_PYTHON_INSTALL_DIR="$TASK_ROOT/python"
export UV_PYTHON_BIN_DIR="$TASK_ROOT/python-bin"
export UV_NO_MODIFY_PATH=1
export UV_DEFAULT_INDEX=https://pypi.org/simple
export TMPDIR="$TASK_ROOT/tmp"
export XDG_CACHE_HOME="$TASK_ROOT/cache"
export XDG_CONFIG_HOME="$TASK_ROOT/config"
export PYTHONDONTWRITEBYTECODE=1
UV=/tmp/openscrub-baseline-20261116/bootstrap/bin/uv
case "${1:-}" in
  python) "$UV" python install 3.9 ;;
  venv) "$UV" venv --python 3.9 "$TASK_ROOT/venv" ;;
  install) "$UV" pip install --python "$TASK_ROOT/venv/bin/python" -c "$TASK_ROOT/validation-constraints.txt" "$TASK_ROOT/source" pytest build hatchling ;;
  *) echo 'Usage: setup.sh python|venv|install' >&2; exit 2 ;;
esac
