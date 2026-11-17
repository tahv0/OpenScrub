# Exact command recipes

Original evidence cwd: `/home/tahv0/src/OpenScrub`. Native tooling cwd: `/home/tahv0/.codex/worktrees/c832/OpenScrub`. Variables abbreviate the absolute paths used in the executed commands; replay needs new run IDs/directories. Complete outputs are retained beside this file.

```bash
TOOL=/home/tahv0/.codex/worktrees/c832/OpenScrub/docs/superpowers/plans/upstream-delivery/execution/tooling
ROOT=/home/tahv0/src/OpenScrub/.superpowers/sdd/README/runtime/task901
PY312=/tmp/openscrub-baseline-20261116/venv-opencv4/bin/python
PY39=/tmp/openscrub-python39-20261117/venv/bin/python

# Before implementation: updated local tests against unchanged afbd207 helper.
VERIFICATION_TEST_ROOT="$ROOT" PYTHONDONTWRITEBYTECODE=1 "$PY312" -m unittest discover -s "$TOOL/tests" -v
VERIFICATION_TEST_ROOT="$ROOT" PYTHONDONTWRITEBYTECODE=1 "$PY39" -m unittest discover -s "$TOOL/tests" -v
# After I1 only, six real file/child/module source/installed scenarios.
VERIFICATION_TEST_ROOT="$ROOT" PYTHONDONTWRITEBYTECODE=1 "$PY312" -m unittest discover -s "$TOOL/tests" -k keeps_ -v
VERIFICATION_TEST_ROOT="$ROOT" PYTHONDONTWRITEBYTECODE=1 "$PY39" -m unittest discover -s "$TOOL/tests" -k keeps_ -v
# After I2, full small tooling suite on each actual interpreter.
VERIFICATION_TEST_ROOT="$ROOT" PYTHONDONTWRITEBYTECODE=1 "$PY312" -m unittest discover -s "$TOOL/tests" -v
VERIFICATION_TEST_ROOT="$ROOT" PYTHONDONTWRITEBYTECODE=1 "$PY39" -m unittest discover -s "$TOOL/tests" -v

# Final expected-module-path assertions were made explicit in the module fixture.
# Copied verify.py, verification_hook.py, sitecustomize.py from git show afbd207:<path>
# into ROOT/fix1/red-baseline-tooling, beside the identical final test bytes.
# No native source/branch swap was used.
VERIFICATION_TEST_ROOT="$ROOT" PYTHONDONTWRITEBYTECODE=1 "$PY312" -m unittest discover -s "$ROOT/fix1/red-baseline-tooling/tests" -v
VERIFICATION_TEST_ROOT="$ROOT" PYTHONDONTWRITEBYTECODE=1 "$PY39" -m unittest discover -s "$ROOT/fix1/red-baseline-tooling/tests" -v
VERIFICATION_TEST_ROOT="$ROOT" PYTHONDONTWRITEBYTECODE=1 "$PY312" -m unittest discover -s "$TOOL/tests" -v
VERIFICATION_TEST_ROOT="$ROOT" PYTHONDONTWRITEBYTECODE=1 "$PY39" -m unittest discover -s "$TOOL/tests" -v
```

All suites ran serially. Socket permission was granted for the existing tiny isolation test. Negative ownership/unsupported-prefix cases call the real stdlib command builder and assert rejection; they never launch a worker or an interpreter with bypass options. Positive prefixed pytest and file/module/child checks execute actual isolated fixture processes.

The six actual product startup commands are recorded as complete arrays and exits in `runtime-commands.json`. For each interpreter, in sequence they invoke:

```bash
"$PY312" "$TOOL/verify.py" --config "$ROOT/fix1/source312.json" --run-id source312 preflight
"$PY312" "$TOOL/verify.py" --config "$ROOT/fix1/installed312.json" --run-id cli312 run -- -B "$ROOT/product-runs/package312-final/site-packages/bin/openscrub" --help
"$PY312" "$TOOL/verify.py" --config "$ROOT/fix1/installed312.json" --run-id http312 run -- /home/tahv0/src/OpenScrub/.superpowers/sdd/README/task901-evidence/listening_smoke.py "$ROOT/product-runs/package312-final/site-packages"
# Then the same three commands with actual PY39 and source39/installed39/cli39/http39.
```

Configs are copies of the caller's existing frozen product config, with only assigned fix scratch and installed target/mode set. The existing target is used directly; all selected runtime bytes are rechecked by preflight/startup. Existing sdist/wheel SHA-256 values were rechecked before those commands. No package build/install, full product suite, browser/media workload or measurement was performed.

Final self-review ran `git diff --check`, then `git diff --cached --check`; commit command was `git commit -m 'tools: preserve selected imports and pytest ownership'` on `tools/local-verification`. Final working-tree cleanliness and helper bytes are independently bound to that commit by `identities.json` generation checks.
