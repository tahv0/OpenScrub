# Task901 commands

Working directory for evidence/config/export commands: `/home/tahv0/src/OpenScrub`. Tooling source/test/commit directory: `/home/tahv0/.codex/worktrees/c832/OpenScrub`. Each actual command used explicit paths; the variables below abbreviate those same paths for replay. A replay needs new run IDs and an empty/new export location; existing runs are intentionally preserved.

```bash
TOOL=/home/tahv0/.codex/worktrees/c832/OpenScrub/docs/superpowers/plans/upstream-delivery/execution/tooling
ROOT=/home/tahv0/src/OpenScrub/.superpowers/sdd/README/runtime/task901
EVIDENCE=/home/tahv0/src/OpenScrub/.superpowers/sdd/README/task901-evidence
PY312=/tmp/openscrub-baseline-20261116/venv-opencv4/bin/python
PY39=/tmp/openscrub-python39-20261117/venv/bin/python

# Initial test-first gate: verify.py absent, 11 expected failing behavior checks.
VERIFICATION_TEST_ROOT="$ROOT" PYTHONDONTWRITEBYTECODE=1 "$PY312" -m unittest discover -s "$TOOL/tests" -v
# Final focused suites, serial, with permission to create a socket.
VERIFICATION_TEST_ROOT="$ROOT" PYTHONDONTWRITEBYTECODE=1 "$PY312" -m unittest discover -s "$TOOL/tests" -v
VERIFICATION_TEST_ROOT="$ROOT" PYTHONDONTWRITEBYTECODE=1 "$PY39" -m unittest discover -s "$TOOL/tests" -v

# Caller-owned export/config generation; pins git archive f44e0b7, never the docs branch app.
python3 "$EVIDENCE/prepare_smoke.py"
# Initial source312 attempt exposed overly strict helper default assertion (retained).
"$PY312" "$TOOL/verify.py" --config "$ROOT/product312.json" --run-id source312 preflight
# Final package invocation, after import-inspection correction. Actual commands, outputs and results are in package312-final.log.
"$PY312" "$TOOL/verify.py" --config "$ROOT/product312.json" --run-id package312-final package
# Final native/floor source gates.
"$PY312" "$TOOL/verify.py" --config "$ROOT/product312.json" --run-id source312-final preflight
"$PY39" "$TOOL/verify.py" --config "$ROOT/product39.json" --run-id source39-final preflight
# installed39 config selects package312's byte-identical installed target with actual3.9.
"$PY39" "$TOOL/verify.py" --config "$ROOT/installed39.json" --run-id installed39-final run -- "$ROOT/product-runs/package312/site-packages/bin/openscrub" --help

# Self-review/staged whitespace and commit, on tools/local-verification only.
git -C /home/tahv0/.codex/worktrees/c832/OpenScrub diff --cached --check
git -C /home/tahv0/.codex/worktrees/c832/OpenScrub commit -m 'tools: centralize isolated local verification setup'
```

`package312.log` is the earlier successful integration before the nested-parent inspection correction. `package312-final.log` repeats only that affected integration with the final guard. Source/floor/installed final logs use the final guard; floor installed uses the earlier byte-identical target, not bootstrap imports. No broad product suite or timed work ran.

`source-default-red.log` preserves one real setup-default regression after its new fixture was added; `parent-import-red.log` preserves one nested-parent execution regression before the fix. `green312.log` and `green312-final.log` (earlier contents replaced only during final iteration) are distinguished in the report; the final files are authoritative for final counts. The first green attempt's socket permission failure remains in `green312.log`; the later single stderr assertion failure is described in the report. `installed39-first.log` preserves the caller's failed relative adapter path. Existing scratch retains all invocation directories and their complete command logs.
