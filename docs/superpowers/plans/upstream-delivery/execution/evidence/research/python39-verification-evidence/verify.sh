#!/bin/bash
set -eu
source /tmp/openscrub-python39-20261117/env.sh
TASK_ROOT=/tmp/openscrub-python39-20261117
cd "$TASK_ROOT/runtime"
openscrub --help > "$TASK_ROOT/logs/installed-cli-help.log" 2>&1
openscrub-web --help > "$TASK_ROOT/logs/installed-web-help.log" 2>&1
python "$TASK_ROOT/harness/smoke.py" installed > "$TASK_ROOT/logs/installed-api-smoke.log" 2>&1
PYTHONPATH="$TASK_ROOT/harness:$TASK_ROOT/source" python "$TASK_ROOT/source/openscrub.py" --help > "$TASK_ROOT/logs/source-cli-help.log" 2>&1
PYTHONPATH="$TASK_ROOT/harness:$TASK_ROOT/source" python "$TASK_ROOT/source/openscrub_web.py" --help > "$TASK_ROOT/logs/source-web-help.log" 2>&1
PYTHONPATH="$TASK_ROOT/harness:$TASK_ROOT/source" python "$TASK_ROOT/harness/smoke.py" source > "$TASK_ROOT/logs/source-api-smoke.log" 2>&1
python -m build --no-isolation --outdir "$TASK_ROOT/dist" "$TASK_ROOT/source" > "$TASK_ROOT/logs/build.log" 2>&1
ffmpeg -version > "$TASK_ROOT/logs/ffmpeg-version.log" 2>&1
tesseract --version > "$TASK_ROOT/logs/tesseract-version.log" 2>&1
