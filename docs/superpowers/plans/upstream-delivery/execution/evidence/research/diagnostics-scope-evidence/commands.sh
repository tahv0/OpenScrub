#!/bin/bash
set -eu
. /tmp/openscrub-baseline-20261116/env-opencv4.sh
scope_root=/tmp/openscrub-diagnostics-scope-20261117
scope_evidence=/home/tahv0/src/OpenScrub/.superpowers/sdd/README/diagnostics-scope-evidence
export PYTHONPATH="$scope_root/12919c96c6f7558136b50d7b4d85e5e6b62f1971"
unset PYTEST_PLUGINS
export XDG_CACHE_HOME="$scope_root/runtime/cache"
export XDG_CONFIG_HOME="$scope_root/runtime/config"
export UV_CACHE_DIR="$scope_root/runtime/uv-cache"
export MPLCONFIGDIR="$scope_root/runtime/matplotlib"
export PYTHONDONTWRITEBYTECODE=1
python "$scope_evidence/probe_lifecycle.py" worker > "$scope_evidence/worker.stdout" 2> "$scope_evidence/worker.stderr"
python "$scope_evidence/probe_lifecycle.py" restart > "$scope_evidence/restart.stdout" 2> "$scope_evidence/restart.stderr"
set +e
python -u "$scope_evidence/probe_lifecycle.py" startup_failure > "$scope_evidence/startup_failure.stdout" 2> "$scope_evidence/startup_failure.stderr"
printf '%s\n' "$?" > "$scope_evidence/startup_failure.exit"
python -u "$scope_evidence/probe_lifecycle.py" sigterm > "$scope_evidence/sigterm.stdout" 2> "$scope_evidence/sigterm.stderr"
printf '%s\n' "$?" > "$scope_evidence/sigterm.exit"
