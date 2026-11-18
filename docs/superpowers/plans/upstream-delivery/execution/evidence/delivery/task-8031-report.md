# Task 8031 — isolated literal plate-text matcher

Status: implementation and applicable local gates complete. Independent spec and quality review remain required before adoption. No upstream PR, push, publication, merge or acceptance claim was made.

## Source and footprint

- Branch: `optional/plate-text-matching`.
- Exclusive source: `/home/tahv0/src/OpenScrub/.superpowers/sdd/README/worktrees/plate-text-matching`.
- Base: `6fde5ad60c6d78d69dbbd8e049a9196f15e4095f`.
- Final head: `3547f82c027323dba8e69e8aef7be62c88438d8b`; clean after final gates and evidence inspection.
- Exactly three added files: `openscrub_internal/plate_search/__init__.py`, `openscrub_internal/plate_search/matching.py`, `tests/test_plate_text_matching.py`.
- All 132 preexisting tracked files match the accepted base byte-for-byte. Per-file Git blob IDs and SHA-256 values, the exact addition allowlist, and clean status are recorded in [source-footprint.json](task8031-evidence/source-footprint.json). Existing app imports, defaults, schemas, dependencies, package metadata/version, updater and Docker files are unchanged.

The package initializer is an inert docstring. The matcher uses Python 3.9-compatible frozen dataclasses and stdlib imports only. It validates bounded ASCII literals before conversion, prepares stable ordered query batches, distinguishes full equality from explicit entire-query fragment containment, and emits all matching unique `(mode, text)` pairs. Invalid observations produce no match after query validation. Complete original observation mappings and nested evidence remain caller-owned and are retained by identity. Text fields are excluded from default representations; validation errors contain rules, and matching produces no output or logs.

No worker, jobs, UI, OCR/discovery, selection/tracking, redaction, geometry or report integration was added. A match supplies no mask coordinates and has no effect on ordinary redaction.

## Actual verification

Native interpreter: `/tmp/openscrub-baseline-20261116/venv-opencv4/bin/python`, actual **3.12.16**. Floor interpreter: `/tmp/openscrub-python39-20261117/venv/bin/python`, actual **3.9.25**. The canonical verification controller and startup hooks were retained. No environment, dependency, model, browser or tool download/install was introduced; only the built product wheel was installed without dependencies into a task-owned target.

[commands-results.json](task8031-evidence/commands-results.json) records exact product controller/workload argv, actual interpreter, config and file-manifest identities, source policy/head, exits, log hashes and all 14 executed verification runs. Full preflight/config/runtime records and owning raw logs are retained for every attempt. Product workload children retain startup hooks; no isolated or altered-environment child bypass was used.

| Gate | Exact source attribution | Actual result |
| --- | --- | --- |
| Genuine RED, native focused | Base head with test-only development manifest; matcher absent | **13 failed**, exit 1; expected missing module |
| Initial GREEN, native focused | Development manifests at base, followed by first clean implementation commit `32a6f034e588384c8d6ee5459ff06af6c17c67c1` | **13 passed**, exit 0 |
| Final native focused import-window correction | Development manifest declared head `46f91fddb7e0f529cac4a247a96b4c894a9f6827`; test bytes equal final `3547f82` | **13 passed**, exit 0 |
| Final actual 3.9 matcher floor | Frozen final `3547f82c027323dba8e69e8aef7be62c88438d8b` | **13 passed**, exit 0 |
| Final actual 3.12 full regression | Frozen final `3547f82c027323dba8e69e8aef7be62c88438d8b` | **573 passed**, exit 0, 106.26 seconds |
| Offline native package and installed exercise | Frozen final `3547f82c027323dba8e69e8aef7be62c88438d8b` | sdist, wheel from extracted sdist, no-deps install and installed native exercise all exit 0 |
| Actual 3.9 installed-wheel exercise | Exact native-built installed target; source paths excluded | full/fragment and stdlib import exercise exit 0 |

Focused and floor configurations use `configure_app=false`. Their fresh child import blocker rejects attempted app/third-party imports, including cached app modules, and other internal packages. Concrete negative controls reject a cached app, the Jython probe from a non-copy caller, and a forged copy filename. CPython 3.9's exact optional `org.python.core` probe from the resolved actual stdlib `copy.py` receives the normal `ModuleNotFoundError` it catches. Stdlib `io`/`contextlib` are prepared before the blocker; stdout/stderr are captured only around helper import and exercise and must remain empty. The separate privacy test checks matching output and logs directly.

The native full gate uses `configure_app=true` and all 12 runtime module-origin bindings. It preimports the app through the startup hook and is **not** a whole-process stdlib-only claim. Its exact existing fixture recipe is recorded in argv: `-o pythonpath=...` plus `-p task1631_fixture -p roundtrip_stdout_selected`. The first fixture stages the SHA-verified existing YuNet into the run. The second preserves and validates only the exact fresh-route child's two startup records before presenting its JSON payload to the preexisting test; no general stdout suppression is used.

The 13 meaningful public-interface test names are in [test-names.json](task8031-evidence/test-names.json). They cover exact raw/normalized/batch/count bounds, ASCII-before-case validation, full equality, explicit fragments, no fuzzy/substitution, stable order and modes, query-validation priority, malformed observations, separate-region handling, complete evidence identity, detector-independent observations, distinct original mappings, repr/error privacy and clean import behavior. No test was skipped.

## Retained failures and corrections

1. `floor-39` at `32a6f03`: **12 passed, 1 failed**, actual 3.9, exit 1. `test_matcher_import_is_stdlib_only` raised `AssertionError` on stdlib `copy.py`'s optional Jython import. The production matcher behavior passed; only the test blocker changed.
2. `floor-final-39` at `086ad444c4447d36bcab8905c17225441c739140`: **12 passed, 1 failed**, actual 3.9, exit 1. The exact caller check compared a lexical filename with a resolved directory across the prepared interpreter's symlink. Both paths are now resolved; the negative controls remain. `floor-final2-39` at `46f91fd` then passed all 13.
3. `full-final2-312` at `46f91fd`: **570 passed, 3 failed**, exit 1, 107.61 seconds. Exact failures were `test_face_model_unions_with_yunet` (existing cached model fixture not activated), `test_matcher_import_is_stdlib_only` (successful child rejected for startup `DEFAULT_PATHS` metadata), and `test_real_render_and_fresh_route_reopen_keep_all_ten_rows` (existing JSON-only test saw startup metadata because its exact adapter was not activated). The accepted existing fixtures were restored, and the new test now captures only its product import/exercise window. Final `full-release-312` passed 573.
4. `package-release-39` at final `3547f82`: controller exit **78**, sdist workload exit **1**, before producing an archive. The cached build-tool bundle selects `pluggy 1.7.0`, requiring Python >=3.10, whose `typing.TypeAlias` import fails under actual 3.9. No product or test changed. The established actual 3.12 build recipe succeeded, and the resulting installed wheel was separately exercised under actual 3.9.

The production matcher file's SHA-256 `2f3a8182dcc66b61e03400d11a6451575cfb4775705cc2338be0e1a00af4ee03` stayed unchanged through every test-harness correction. Old commits, input configs, preflight data and raw failure logs remain attributed to their actual source, never relabeled as final passes. The native archive extraction also emitted the existing controller's Python tar-filter deprecation warning; explicit member safety checks and selected byte comparisons passed. No controller code was changed.

## Distribution and retained evidence

- sdist: `openscrub-1.0.96.tar.gz`, **601740 bytes**, SHA-256 `e328ceb1f2c2e8888b83f4d304c9bbadb12955f7bf917838fff24c9df41d3955`.
- Wheel built from the extracted exact sdist: `openscrub-1.0.96-py3-none-any.whl`, **459590 bytes**, SHA-256 `3ca2abf0aacd8e1404eab0e71687077c339a92b2b07a5fc37073bf54b63ae6a9`.
- Existing `Requires-Python: >=3.9` retained.
- Existing private package initializer and both new package files have exact source/sdist/wheel/installed bytes. The new test has exact source/sdist bytes. [artifact-binding.json](task8031-evidence/artifact-binding.json) records every selected hash and the actual 3.9 installed config/log binding.
- No-deps install target: `/home/tahv0/src/OpenScrub/.superpowers/sdd/README/runtime/task8031/runs/package-native-release-312/site-packages`.
- Actual 3.9 import/exercise cwd: separate `runs/installed-release-39`, outside the checkout. Startup output proves all three declared module origins point into that installed target with exact source hashes; checkout and tool/bootstrap paths are excluded from installed imports.

Unchanged `pyproject.toml` includes the whole private package in wheel/sdist and the tests directory in sdist. Unchanged `openscrub_update.py` creates nested destination parents and handles nested archive paths. All three unchanged Dockerfiles copy `openscrub_internal/` as a directory. These were inspected against the new packaged paths; no network updater or Docker build was run solely for the dormant helper.

Compact evidence contains configs, preflight/runtime manifests, raw owning logs, adapter sources and hashes. It contains no source exports, installed trees, environments, media or archive binaries. Full runtime artifacts remain in assigned task runtime for review. Source/runtime ownership is released after actual report completion; future work requires supervisor scheduling.

## Limits and handoff

This slice proves literal matching and original evidence retention only. OCR discovery, spatial grouping, detached-plate search success, frame/source validity, cancellation/stale publication, selection/tracking, geometry/mask support, blur quality and query/privacy lifecycle belong to later consuming integrations. Caller-owned nested evidence has no lifetime or thread-safety guarantee. Windows frozen-package availability remains unverified until consuming integration. Browser/video/model/Docker/updater exercises beyond the required existing full regression were not added for this unreachable helper.

Fresh independent spec/quality review is pending. Root chooses any later integration or upstream draft timing. The local PR notes describe only this optional prerequisite and actual validation.
