# Task 61 / P06A independent task review

## Spec compliance

- **Issues found:** atomic publication, all three publishers, distribution inclusion, JSON options, and real failure regressions meet the brief. The requirement to preserve the existing vault lifecycle has one Important regression: successful publication can now abort vault encryption when its snapshot contains the staging name (`openscrub_internal/reports.py:23`, `openscrub_internal/reports.py:32`; details below).
- Scope is otherwise appropriate: the helper is stdlib-only; engine and web entry points remain; document construction and `indent=1` remain; no transaction locking, training, dependency/version bump, or render retention work appears in the supplied diff (`openscrub_internal/reports.py:2`, `openscrub_internal/reports.py:28`, `openscrub.py:6330`, `openscrub_web.py:1336`, `openscrub_web.py:1426`).
- **Cannot verify:** actual Docker, Windows, frozen/PyInstaller, network-filesystem and power-loss behavior. The report explicitly disclaims these. Existing overlapping-edit and render-retention defects remain outside this task; atomic replacement does not resolve them (`openscrub_internal/reports.py:10`).

## Strengths

- Small, cohesive publication boundary stages beside the destination with restrictive permissions, flushes and file-fsyncs, closes before replacement, propagates failure, and cleans up without masking the original publication error (`openscrub_internal/reports.py:23`, `openscrub_internal/reports.py:29`, `openscrub_internal/reports.py:32`, `openscrub_internal/reports.py:33`). Its durability and Windows limitations are stated accurately (`openscrub_internal/reports.py:10`).
- Real registered-route tests cover encode/write/flush/fsync/replace failures, byte preservation, rehydration and failed acknowledgements; the gated replacement test verifies complete old/new visibility and response timing. Engine and actual asynchronous tracking publication are also covered (`tests/test_large_report_io.py:46`, `tests/test_large_report_io.py:67`, `tests/test_large_report_io.py:92`, `tests/test_large_report_io.py:147`, `tests/test_large_report_io.py:175`). Tracking inference substitution does not replace persistence.
- Packaging changes include the runtime package in wheel/sdist and all three applicable Dockerfiles; test collection and sdist test inclusion are minimal (`pyproject.toml:92`, `pyproject.toml:104`, `pyproject.toml:122`; the three Dockerfile COPY additions; `CONTRIBUTING.md:25`). Raw packaging results and the inspected verification script support installed/source imports and updater preservation of synthetic data.

## Findings

### Critical

None.

### Important — newly transient report stages can abort vault locking

**Location:** `openscrub_internal/reports.py:23` and `openscrub_internal/reports.py:32`, interacting with unchanged `openscrub_vault.py:167`–`169` and `openscrub_web.py:3245`–`3246`.

`encrypt_tree` materializes its file list, then unconditionally removes every listed `.tmp`. The new helper introduces a live `.report-*.tmp` that disappears on a successful replacement. If the vault snapshots that file and the publisher completes before the vault processes it, the vault's `os.remove` raises `FileNotFoundError`. This aborts the entire encryption pass; `_vault_lock_now` never reaches its key reset. Remaining files can stay plaintext. Autolock suppresses the exception (`openscrub_web.py:3227`), and shutdown can finish with plaintext leftovers after reporting its failure (`openscrub_web.py:3261`). No concurrent failed report write is required.

This is distinct from the implementer's documented opposite ordering, in which the vault removes a still-active stage and the report save fails. It also differs from preexisting direct-write/vault races: direct writes did not introduce a transient snapshot entry whose ordinary successful disappearance aborts the vault pass. Deferring complete transaction/lifecycle coordination to P06B does not remove this new regression.

**Focused evidence:** one synthetic scheduling check, using the supplied environment and the actual helper plus actual `encrypt_tree`, paused report replacement, captured the vault snapshot, completed publication, then let the vault process that snapshot. `.tmp` was ordered first, a permitted `os.walk` order. A baseline direct-write control used the same snapshot-before-write schedule. The result was:

```json
{
  "baseline_direct_write": {
    "encrypted": 2,
    "vault_result": "success",
    "publication": {"ok": true},
    "remaining_plaintext": []
  },
  "atomic_report": {
    "vault_result": "FileNotFoundError",
    "publication": {"ok": true},
    "remaining_plaintext": ["report.json", "synthetic-input"]
  }
}
```

The controlled snapshot iterator only selected a valid enumeration order and interleaving; production encryption and publication ran unchanged. The check used temporary synthetic files, cleaned them up, disabled bytecode writes, and modified no product/Git files.

**Required resolution:** make vault crash cleanup tolerate a `.tmp` entry that disappeared since enumeration, and add a focused regression for this ordering, or revise the slice to provide equivalent lifecycle safety. Limit any missing-file tolerance to the transient cleanup case so failures opening ordinary files remain visible. Full overlapping-edit and vault coordination can remain in P06B.

### Minor — packaging verification emits a deprecation warning

**Location:** `.superpowers/sdd/README/task61-evidence/verify_packaging.py:23`; observed in `task61-evidence/packaging.log:1`.

`archive.extractall(ROOT / 'source')` omits an explicit extraction filter and emits Python's upcoming-default-change warning. This is an evidence-harness issue, not a runtime vulnerability finding: the archive is locally built. Specify the intended filter and rerun only that focused packaging check if clean verification output is required. The final pytest and build logs themselves are clean.

## Evidence and review boundaries

- Reviewed the supplied package once: base `e21ebdf6e3ee46e6c65050dc956a9a3459152269`, head `c7cf1f02d98742e93a728e4b1e94d8c6bd02c318`. No Git commands ran; no changed function needed a cut-off-hunk reread.
- The only product-source inspection outside the diff addressed the named temporary-file/vault risk: vault file enumeration/encrypt/decrypt implementation and web lock/unlock/autolock/shutdown consumers. This established the precise error and lifecycle impact above; it was not a broader branch review.
- Inspected raw `red.log`, `green2.log`, `final.log`, `build-final.log`, `runtime.log`, `runtime-results.json`, `packaging.log`, `packaging-results.json`, both verification scripts, and the isolation plugin. Baseline route failures show zero/partial JSON; final evidence records 13 focused passes, 147 full passes, and successful sdist-to-wheel build. Socket failures preserved bytes and fresh-process rehydration; synthetic scan/render recorded 60 frames and one report row; package startup paths point outside the checkout and updater sentinel checks pass.
- Did not rerun full tests/build or packaging/runtime probes. The only additional execution was the focused vault ordering/control check above. Its command sourced `/tmp/openscrub-baseline-20261116/env-opencv4.sh`, ran `PYTHONDONTWRITEBYTECODE=1 python` from the review checkout, imported the actual helper/vault, used bounded threading events and `TemporaryDirectory`, and checked the stated outcomes.
- No Docker/Windows build, browser interaction, physical interruption, or exhaustive concurrent-lifecycle validation was performed. The existing synthetic engine run uses fallback Tesseract after unavailable/model-download-blocked optional OCR backends; its expected injected HTTP 500 tracebacks are consistent with the test purpose.

## Quality verdict

**Needs fixes.** The publication helper and regressions are well scoped and maintainable, and the recorded build/runtime/package evidence is substantive. The new successful-save/vanished-stage ordering must stop aborting vault encryption before this task is accepted.
