# Executed acceptance commands and binding

Native cwd `/home/tahv0/.codex/worktrees/c832/OpenScrub`; source identity assertions shown below were run before pytest. Full retained scripts/harnesses accompany this file. All acceptance runtime artifacts are under `/tmp/openscrub-task112`. This is a record, not a request to rerun measurements.

## Base attribution before implementation

```bash
mkdir -p /tmp/openscrub-task112/base /tmp/openscrub-task112/evidence /tmp/openscrub-task112/runtime
git archive e21ebdf6e3ee46e6c65050dc956a9a3459152269 | tar -xf - -C /tmp/openscrub-task112/base
source /tmp/openscrub-baseline-20261116/env-opencv4.sh
python /tmp/openscrub-task112/attribution.py
```

`baseline-attribution.py` retains the exact script. It inserts/asserts the base source path, creates fresh inputs before timing, keeps normal GC, records 3 warmups then 5 samples, and traces a separate call. Full exported-file Git-blob verification is in base-identity.json.

## Coordinated paired comparison

```bash
source /tmp/openscrub-task112/env.sh
python benchmark/tail_history.py --base-source /tmp/openscrub-task112/base --head-source /home/tahv0/.codex/worktrees/c832/OpenScrub --output /tmp/openscrub-task112/evidence/final-comparison.json > /tmp/openscrub-task112/evidence/final-comparison.log 2>&1
```

That original run used script `299dbe5…` (retained tail_history-original.py), not the later fixture. After the detector-consistency check in sparse-detector-boundary.log, the authorized complete repeat used script `027f588…`:

```bash
source /tmp/openscrub-task112/env.sh
python benchmark/tail_history.py --base-source /tmp/openscrub-task112/base --head-source /home/tahv0/.codex/worktrees/c832/OpenScrub --output /tmp/openscrub-task112/evidence/final-comparison-detector-consistent.json > /tmp/openscrub-task112/evidence/final-comparison-detector-consistent.log 2>&1
```

Both use complete modules, four fixed cases, normal GC, 3 warmups/5 alternating recorded pairs; all timing finishes before instrumentation. Source hashes, all samples/warmups, full final records and equality digests are in each JSON. No further run was performed.

## Active-source pytest

```python
import pathlib, openscrub, pytest
assert pathlib.Path.cwd() == pathlib.Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
assert pathlib.Path(openscrub.__file__).resolve() == pathlib.Path.cwd() / 'openscrub.py'
raise SystemExit(pytest.main(['tests/test_tail_history_index.py', 'test_openscrub.py',
                             '-k', 'tail or merge or bridge or detector_only_scan', '-q']))
```

With `source /tmp/openscrub-task112/env.sh`, final focused output was 27 passed, 127 deselected. The single full discovery run used the same assertions followed by `pytest.main(['-q'])` and passed 153 before the named test-only correction (old tail-test SHA ecfae9cb…). Final test SHA58157819… adds generator coverage and strengthens existing malformed/fuzz-disabled cases; there is no full154 claim.

For actual3.9, sourced `/tmp/openscrub-python39-20261117/env.sh`, then overrode `PYTHONPATH=/tmp/openscrub-task112/harness:/home/tahv0/.codex/worktrees/c832/OpenScrub`, `PYTEST_PLUGINS=task112_isolation`, pytest cache/basetemp and TMPDIR into task112, and ran that same assertion/selection wrapper with an additional `assert sys.version_info[:2] == (3, 9)`. Final output 27 passed, 127 deselected.

Base controls ran from `/tmp/openscrub-task112/runtime`, with `PYTHONPATH=/tmp/openscrub-task112/harness:/tmp/openscrub-task112/base`, asserted the actual base core path, then `pytest.main(['/home/tahv0/.codex/worktrees/c832/OpenScrub/tests/test_tail_history_index.py', '-q'])`. Final output 20 passed. The earlier native-cwd shadow assertion failure is preserved separately.

## Offline build and installed smoke

Build source started from the full base export with the six changed files overlaid, then updated only the amended test/benchmark bytes. Before final identity checks all sdist inclusions were compared byte-for-byte to native files. Initial backend-missing failure is retained.

```bash
source /tmp/openscrub-task112/env.sh
PYTHONPATH=/tmp/openscrub-task112/harness:/tmp/openscrub-baseline-20261116/bootstrap/lib/python3.14/site-packages python -m pip install --no-index --no-deps --no-compile --target /tmp/openscrub-task112/build-tools /tmp/openscrub-task620/build-wheelhouse/*.whl
PYTHONPATH=/tmp/openscrub-task112/harness:/tmp/openscrub-task112/build-tools python -m build --no-isolation --outdir /tmp/openscrub-task112/dist /tmp/openscrub-task112/build-source
PYTHONPATH=/tmp/openscrub-task112/harness:/tmp/openscrub-baseline-20261116/bootstrap/lib/python3.14/site-packages python -m pip install --no-index --no-deps --no-compile --target /tmp/openscrub-task112/installed /tmp/openscrub-task112/dist/openscrub-1.0.96-py3-none-any.whl
```

Only prepared3.12 executes these commands. The3.14 path temporarily supplies pure-Python pip; no3.14 interpreter runs. Final build log and package-fixture-final-identity.json reflect the benchmark-fixture-only correction. Wheel bytes remained identical to the installed/smoked wheel, so no repeated startup was needed after packaged test/benchmark changes.

Installed smoke cwd was `/tmp/openscrub-task112/runtime`:

```bash
TASK112_INSTALLED_ONLY=1 PYTHONPATH=/tmp/openscrub-task112/harness:/tmp/openscrub-task112/installed python /tmp/openscrub-task112/package-smoke.py
```

The retained package-smoke.py asserts installed paths, excludes native checkout paths, checks byte-for-byte runtime/control inclusions, compares parser defaults to the complete base module, runs actual installed entry-point help subprocesses, and checks five Flask endpoints through the test client. Initial editable-path assertion and corrected passing logs are separate.

Final Git checks were `git diff --check`, content SHA256/Git-blob verification, explicit `git add` of the six owning files, and commits e96deb5 and benchmark-only952af20. Final status is clean. No push or published PR.
