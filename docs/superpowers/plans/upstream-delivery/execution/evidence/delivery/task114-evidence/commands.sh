#!/usr/bin/env bash
# Command record, not an unattended timing entry point.
# Exact exports were made from clean native pr/merge-candidate-discovery.
# git archive e21ebdf6e3ee46e6c65050dc956a9a3459152269 -o /tmp/openscrub-task114/base.tar
# Python tarfile extraction + 113-file SHA manifest occurred before imports.
. /tmp/openscrub-baseline-20261116/env-opencv4.sh
# Working directory for all application/test invocations:
# /tmp/openscrub-task114/work
# Source assertions are inside each retained script, before module execution.
# 1. Untimed validation (measure_merge.py at original 5ee7d18f... identity):
# python /tmp/openscrub-task114/evidence/measure_merge.py validate > evidence/validation.log
# 2. Root-granted exclusive baseline slot:
# python /tmp/openscrub-task114/evidence/measure_merge.py baseline > evidence/baseline.log
# Original script is retained as benchmark/baseline_measure_merge.py unchanged.
# Explicit slot release followed ALL source-line instrumentation.
# 3. Disposable candidate generation (before comparison timing):
# python3 /tmp/openscrub-task114/evidence/make_candidate.py
# 4. Exploratory controls, retained but NOT counted as isolated acceptance:
# PYTEST_PLUGINS= TASK114_MODULE=<actual module path> TASK114_MODULE_SHA=<hash>
# python -m pytest -q /tmp/openscrub-task114/work/tests --basetemp=<distinct dir>
# Initial 36 controls then stabilized40 per base/head; see logs/identity records.
# 5. Root-granted exclusive comparison slot (final harness ab85aeb3...):
# python /tmp/openscrub-task114/evidence/measure_merge.py compare \
#   --head /tmp/openscrub-task114/candidate/openscrub.py \
#   --head-sha 0d3c47ac3a6a30867c7678145275ee72cd5765d9674aaa016f754881e58d88ea \
#   > /tmp/openscrub-task114/evidence/comparison.log
# Explicit release followed ALL work/profile/allocation instrumentation.
# 6. Corrected focused gate, serial actual commands (40 each, exit0):
export PYTHONPATH=/tmp/openscrub-task114/hooks:/tmp/openscrub-task114/base
export OPENSCRUB_BASELINE_MODEL_DIR=/tmp/openscrub-task114/synthetic-data/models
# PYTEST_PLUGINS=baseline_isolation inherited from prepared environment.
TASK114_MODULE=/tmp/openscrub-task114/base/openscrub.py TASK114_MODULE_SHA=0e4f0f9a7846080f591038d021aaf3ca6f01201d83ac32bbdc273f53d5067ee7 python -m pytest -q /tmp/openscrub-task114/work/tests --basetemp=/tmp/openscrub-task114/pytest-base-isolated
TASK114_MODULE=/tmp/openscrub-task114/candidate/openscrub.py TASK114_MODULE_SHA=0d3c47ac3a6a30867c7678145275ee72cd5765d9674aaa016f754881e58d88ea python -m pytest -q /tmp/openscrub-task114/work/tests --basetemp=/tmp/openscrub-task114/pytest-candidate-isolated
# 7. Derived summary (not a timing rerun):
# python3 /tmp/openscrub-task114/evidence/summarize.py > evidence/summary.log
# Native final source/status: git rev-parse HEAD; git status --short;
# git diff --stat e21ebdf6e3ee46e6c65050dc956a9a3459152269
