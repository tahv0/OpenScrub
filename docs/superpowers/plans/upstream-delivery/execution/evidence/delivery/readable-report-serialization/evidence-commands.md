# Task632 executed commands and boundaries

Native source: `/home/tahv0/.codex/worktrees/c832/OpenScrub`, independent branch
`pr/readable-report-serialization`, exact base3457efac574d74a7d2377cbc0d44bb0b87462c3a.
All entrypoints/scripts and generated fixtures below are task-local; no remote
publication, dependency/model download, container or browser run occurred.

## Bounded attribution (exclusive slot1)

From the original cwd, with no product imports from cwd except explicit native
`sys.path.insert` in the retained script:

```sh
. /tmp/openscrub-baseline-20261116/env-opencv4.sh
python /tmp/openscrub-task632/attribution.py 10000 > /tmp/openscrub-task632/attribution-10000.log 2>&1
```

Three warmups/five recorded publications per candidate, rotated candidate order.
The exact experimental candidate bodies are in `attribution.py`; these were
never installed in product code. Complete-byte SHA checks and GC occur outside
the publication timer. This is stdlib publication attribution, not HTTP latency.

## TDD and verification

`add_tests.py`, `implement.py`, `rename_test_counter.py`, `fix_tests.py` preserve
the exact edits applied. `red.log` is the exploratory one-method dispatch RED
(removed from delivered tests after self-review), plus16 passing compatibility
cases. It includes two read-only pytest cache warnings, later redirected.

The first focused invocation was launched from the original cwd with explicit
native PYTHONPATH. Python's leading cwd shadowed web/engine imports, and sandbox
denied loopback sockets. `focused.log` retains132failed/27passed/10errors; none
is treated as candidate product evidence. `task632_isolation.py` now inserts and
asserts all native module paths before test execution. Subsequent commands use
native cwd with the already-authorized escalation for local socket access.

The native, corrected focused command was:

```sh
. /tmp/openscrub-baseline-20261116/env-opencv4.sh
PYTHONPATH=/tmp/openscrub-task632:$PWD:$PYTHONPATH PYTEST_PLUGINS=task632_isolation python -m pytest -q -o cache_dir=/tmp/openscrub-task632/pytest-cache tests/test_report_serialization.py tests/test_large_report_io.py tests/test_report_transactions.py tests/test_manual_addition_replay.py tests/test_report_roundtrip.py tests/test_job_response_lifetime.py --basetemp /tmp/openscrub-task632/focused-active-tmp > /tmp/openscrub-task632/focused-active.log 2>&1
```

It produced168passed/1failure in test-only global JSONEncoder monkeypatching,
which intercepted request JSON before lock admission. The final test isolates
`reports.json` with a namespace. The same command then used `focused-final-tmp`
and `focused-final.log`, with168passed. `red.log`'s implementation-prescribing
test was removed, so final verification has16 new compatibility/failure cases.
The bounded baseline attribution is the owning performance RED; no compatibility
regression was claimed against baseline.

Full discovery, stable final source/test bytes:

```sh
. /tmp/openscrub-baseline-20261116/env-opencv4.sh
PYTHONPATH=/tmp/openscrub-task632:$PWD:$PYTHONPATH PYTEST_PLUGINS=task632_isolation python -m pytest -q -o cache_dir=/tmp/openscrub-task632/pytest-cache --basetemp /tmp/openscrub-task632/full-tmp > /tmp/openscrub-task632/full.log 2>&1
```

Actual Python3.9 affected checks:

```sh
. /tmp/openscrub-python39-20261117/env.sh
export PYTHONPATH=/tmp/openscrub-task632/floor-harness:$PWD
export PYTEST_PLUGINS=task632_floor
export TMPDIR=/tmp/openscrub-task632/tmp
export XDG_CACHE_HOME=/tmp/openscrub-task632/cache
export XDG_CONFIG_HOME=/tmp/openscrub-task632/config
python -m pytest -q -o cache_dir=/tmp/openscrub-task632/floor-cache tests/test_report_serialization.py tests/test_large_report_io.py tests/test_report_transactions.py tests/test_manual_addition_replay.py tests/test_report_roundtrip.py --basetemp /tmp/openscrub-task632/floor-tmp > /tmp/openscrub-task632/floor.log 2>&1
```

`prepare_checks.py` retains how existing isolated3.9 helpers were copied with
task-local audit/data roots. Existing cached model only; no new model.

Offline packaging and smoke:

```sh
. /tmp/openscrub-baseline-20261116/env-opencv4.sh
PIP_NO_INDEX=1 PIP_FIND_LINKS=/tmp/openscrub-task620/build-wheelhouse python -m build --outdir /tmp/openscrub-task632/dist > /tmp/openscrub-task632/build.log 2>&1
python /tmp/openscrub-task632/check_packaging.py > /tmp/openscrub-task632/packaging.log 2>&1
```

The runtime has no pip module (`install.log`), so first trying existing bootstrap
pip installed correctly but generated entrypoints with its dependency-less
Python3.14 shebang (`install-bootstrap.log`, `installed-startup-final.log`).
The attempted smoke failures are tooling failures retained verbatim. Corrected
installation executes that same existing pip code through the prepared3.12
runtime; it installs only the local wheel, without dependencies/network:

```sh
. /tmp/openscrub-baseline-20261116/env-opencv4.sh
PYTHONPATH=/tmp/openscrub-baseline-20261116/bootstrap/lib/python3.14/site-packages python -m pip install --no-index --no-deps --upgrade --target /tmp/openscrub-task632/installed/site-packages /tmp/openscrub-task632/dist/openscrub-1.0.96-py3-none-any.whl > /tmp/openscrub-task632/install-runtime.log 2>&1
python /tmp/openscrub-task632/check_installed.py > /tmp/openscrub-task632/installed-startup-runtime.log 2>&1
```

`freeze.py` records all127 final source blob hashes after source stabilization,
and `check_evidence.py` compares them against the final commit. Full tests/build
were before the commit; byte identity, rather than relabelled command metadata,
binds them to the tested candidate.

Tiny separate work-count smoke used prepared3.12, native cwd:

```sh
python /tmp/openscrub-task632/count_smoke.py > /tmp/openscrub-task632/count-smoke.log 2>&1
```

## Final comparison (exclusive slot2)

All own suites, browser/server/build/install processes had ended first. Supervisor
confirmed no competing agent workload; only source/docs IO elsewhere. Host
user/system activity, storage and scheduler remain uncontrolled.

```sh
. /tmp/openscrub-baseline-20261116/env-opencv4.sh
python benchmark/review_io.py --scenario saves --rows 10000 100000 --repository /home/tahv0/.codex/worktrees/c832/OpenScrub --before-ref 3457efac574d74a7d2377cbc0d44bb0b87462c3a --after-ref 4a62e49d2f0896b737081cc92e1f92e9bcaee93f --before-noop-publications 0 --evidence-dir /tmp/openscrub-task632/measurement --output /tmp/openscrub-task632/measurement/results.json > /tmp/openscrub-task632/measurement.log 2>&1
```

Timing workers are uninstrumented. The same driver then creates fresh separate
counted workers, never mixing their timings into HTTP latency distributions.
Historical defaults remain before-noop-publications1 for before12919c9; exact
before3457efa explicitly uses0. Every Git blob is verified before import and
after all measurements; actual module file paths and hashes are asserted.

## After timing

The retained `large_token_memory.py` is a separate fresh-process1ms sampled RSS
probe through the real pinned publishers; it claims no HTTP latency. Token-size
counting occurs after the publication observation window. `check_evidence.py`
retains actual expected full reports, performs byte-by-byte comparisons, validates
all108 main HTTP statuses/work counts and per-request inode behavior, then checks
all frozen committed blobs and clean native HEAD. Actual final commands/results
are additionally recorded in the Task632 report.
