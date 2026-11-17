# Task115 verification commands and identities

All application execution used prepared actual Python3.12.16/OpenCV4.14.0 or actual Python3.9, never the bootstrap Python3.14 interpreter. Task-only harness and environment scripts are retained alongside these logs. Their source import assertion executes at pytest_configure before collection. All runtime data, profile expansion, models and writes are isolated beneath /tmp/openscrub-task115 by the task-only sitecustomize audit hook. No network install or model fetch was allowed.

Base export: `git archive e21ebdf6e3ee46e6c65050dc956a9a3459152269 | tar -x -C /tmp/openscrub-task115/base` (created using a temporary runner directory then renamed to base).

From empty `/tmp/openscrub-task115/runner`, source env312.sh and set TASK115_SOURCE=/tmp/openscrub-task115/base and PYTHONPATH=/tmp/openscrub-task115/harness:/tmp/openscrub-task115/base:

- RED: `python -m pytest /home/tahv0/.codex/worktrees/c832/OpenScrub/tests/test_first_scan_sanity.py -k first_low_word_scan -vv`
- Base unaffected controls: same file with `-k 'default_backtracking or three_word' -q`

From native `/home/tahv0/.codex/worktrees/c832/OpenScrub`, source env312.sh:

- Targeted: `python -m pytest tests/test_first_scan_sanity.py -vv`
- Owning: `python -m pytest test_openscrub.py tests/test_first_scan_sanity.py -k 'scan or reverse or backtrack or report' -q`
- Full discovered suite: `python -m pytest -q` (one sequential valid run, after invalid shared-basetemp attempt)

Build, all under /tmp/openscrub-task115:

- Install cached wheels into task/build-tools with prepared Python3.12 `python -m pip install --no-index --no-deps --target TASK/build-tools /tmp/openscrub-task620/build-wheelhouse/*.whl`; temporary bootstrapPYTHONPATH supplies pip only.
- Full exact-base export copied to task/build-source with exactly the three changed files overlaid. Task-local Hatch backend builds sdist through `hatchling.build.build_sdist(TASK/dist)`.
- Extract sdist into task/sdist. From extracted openscrub-1.0.96 only, `hatchling.build.build_wheel(TASK/dist)`.
- Prepared Python3.12 `python -m pip install --no-index --no-deps --target TASK/installed TASK/dist/openscrub-1.0.96-py3-none-any.whl` (temporary bootstrapPYTHONPATH supplies pip).
- Installed-only smoke from TASK/runtime: TASK115_INSTALLED_ONLY=1 TASK115_SOURCE=TASK/installed PYTHONPATH=TASK/harness:TASK/installed `python TASK/package-smoke.py`. Installed-only hook removes original checkout/native worktree/build-source/base paths from sys.path; no bootstrapPYTHONPATH retained. Package smoke compares full exact parser defaults to exported base; verifies changed source/test inclusion, installed module bytes, Requires-Python>=3.9, both installed CLI --help invocations, and five actual Flask test-client routes.

Floor (serial, native cwd): source env39.sh, then `python -m pytest test_openscrub.py tests/test_first_scan_sanity.py -k 'scan or reverse or backtrack or report' -q --basetemp=/tmp/openscrub-task115/tmp/floor39`.

Installed owning controls (serial, TASK/runtime cwd): source env312.sh; set TASK115_INSTALLED_ONLY=1 TASK115_SOURCE=TASK/installed PYTHONPATH=TASK/harness:TASK/installed; `python -m pytest TASK/sdist/openscrub-1.0.96/test_openscrub.py TASK/sdist/openscrub-1.0.96/tests/test_first_scan_sanity.py -k 'scan or reverse or backtrack or report' -q --basetemp=TASK/tmp/installed312`.

Self-review: `git diff --check`; full product diff inspected (six added local sanity-image lines, one replaced Canny input; one explicit sdist test inclusion; new seven-case test file). Parser, thresholds, warning text, backtracking state/buffers, normal decoder and cap.release flow remain unchanged. No benchmark, model-quality, throughput, browser/bound-port or broader-platform claims.
