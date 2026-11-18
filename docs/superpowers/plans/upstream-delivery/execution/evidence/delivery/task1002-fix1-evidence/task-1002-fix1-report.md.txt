# Task1002 fix round1 — generic strict native entry errors

Repair base: **285f4afd455ad6dc95a473995dee142421cdc87e**. Clean repaired head: **6fde5ad60c6d78d69dbbd8e049a9196f15e4095f**, on the same `pr/exact-tracker-seeds` branch. Commit `6fde5ad` addresses independent Important finding I1. Only the generic engine entry and the two strict test files changed. Fresh scoped review by the same reviewer is pending; nothing was published or adopted into C01/user data.

## Finding and narrow repair

I1 identified an incomplete typed strict API boundary: generic `VideoCapture` construction and the first `isOpened()` access could raise raw native exceptions. The web worker already caught them and returned done/added0/error. This repair does not claim to fix a previously observed leak, nearby fallback or publication failure.

The generic constructor now follows the existing person/primer precedence: preserve existing `ExactError` and `PipelineCancelled`; normalize other `Exception` values to `ExactError` with the original `__cause__`; leave `KeyboardInterrupt`/`SystemExit` untouched. Once construction returns a capture, the existing owner `try/finally` still releases it exactly once. The first strict open-state check now happens inside the existing indexed-prime error adapter. Legacy construction/open-state ordering, raw exception identities and false-open empty results remain unchanged. Strict false-open remains `ExactError`.

The production diff is15 lines in `track_manual_region`; person/primer behavior, optional interfaces, supplied pixels, source/timeline/operation/publication ownership, defaults, algorithms and package declarations are unchanged. `openscrub_web.py`/PAGE, the private seed/helper and `pyproject.toml` remain byte-identical to285. No UI/schema/dependency/model/training change was made.

## Genuine REDs and covering checks

Sixteen added cases cover generic constructor/open-state ordinary exceptions, original cause, strict `ExactError`/`PipelineCancelled`/BaseException identity, legacy native errors, strict/legacy false-open behavior and real-route cleanup/no-publication. Explicit short parameter IDs are used. The real-route cases fail the second capture after the short web verification capture has closed. They assert the actual stage: one earlier web factory-resolution hook, zero tracker/person initializer/fallback work, exactly-once releases of returned captures, source lease cleanup and unchanged raw report/committed epoch.

Before the fix, **fix1-red002:4 failed/12 passed/67 deselected**. Both direct generic ordinary-error cases escaped as raw `RuntimeError`, and both actual-route observers saw that raw type; the web done/added0/error behavior was already correct. After the narrow fix, **fix1-green004:16 passed/67 deselected**. Test bytes are identical across RED/GREEN/final runs.

Frozen covering scope is both entire strict modules plus the six existing actual legacy owners:

```text
-m pytest tests/test_strict_tracker_seed.py tests/test_strict_tracking_routes.py
 test_openscrub.py::test_track_manual_region
 test_openscrub.py::test_track_fail_closed_hold
 test_openscrub.py::test_track_person_detector_path
 test_openscrub.py::test_track_dormant_reacquisition
 test_openscrub.py::test_track_person_lookalike_veto
 test_openscrub.py::test_track_person_size_jump_handoff -q
```

The actual reviewed-launcher invocations use absolute source/test/config paths and unique owned scratch. [Complete command vectors/results](task1002-fix1-evidence/commands-results.json) retain them without changing prior inputs.

| Run | Final source / actual result |
|---|---|
| fix1-native007 |clean6fde5ad, Python3.12.16: **89 passed**,4.72s |
| fix1-floor008 |clean6fde5ad, Python3.9.25: **89 passed**,5.44s |
| fix1-package009 |clean6fde5ad: offline sdist→wheel-from-sdist, strict installed origins/defaults/CLI/web/actual HTTP/updater gate **exit0** |

The89 cases comprise83 strict cases and six real legacy trackers. They include the retained actual native/normalized pixel/PTS/priming cases and existing cancellation/cleanup controls. Both interpreters execute the same89 IDs; no fixture or selection was shrunk. No broad full, PAGE, old feasibility/cost matrix or extra source HTTP gate was replayed.

## New prospective native identities

Before NEW repair gates, each actual interpreter inspected NumPy/OpenCV versions, loader origins, the used native extensions, OpenCV build information and the retained source's actual FFMPEG backend metadata. Discovery used `-B -I`, no product import, no dependency/environment mutation and no model download. New frozen verification prerequisites pin the actual cv2 extension and `numpy._core._multiarray_umath` extension, plus loader bytes and the discovery record. External libraries were not added to the ten PRODUCT module-origin entries or the shared launcher.

| Interpreter | OpenCV | NumPy | Used extension SHA prefixes |
|---|---|---|---|
|3.12.16|4.14.0|2.5.5|cv2`8ed76bb37221`; multiarray`1650f5b6a42b`|
|3.9.25|4.14.0|2.0.2|cv2`8ed76bb37221`; multiarray`eced012ddb86`|

[Full paths/hashes/build metadata](task1002-fix1-evidence/native-identity-scope.json) point to the complete records. These pins apply prospectively only to repair gates. **The original544/269 runs did not have run-specific OpenCV/NumPy binary identities; the new observations do not retroactively supply them.** This is not full transitive native-library, OS, GPU or platform certification.

One fail-fast preparation step attempted a gate-config filename already reserved for a native observation. It exited1 before overwrite or workload; the clean commit had succeeded. The immutable observation was preserved and new `owning-312`/`owning-39` config names were used. This was preparation metadata, not a product RED or test failure. Its original inputs/attribution remain retained.

## Final offline package and installed behavior

Sdist **596226B**, SHA `480557d37c7b21954f3011c1cb53f8bdd7a4ba3da7af5a0a38c6662bd3afbff5`; wheel **457336B**, SHA `976df7bcaeb677b2c82e2bc8e0f959c0564404289837a3c14b965ecd64b66750`. The wheel is built from the verified safely extracted sdist. Assertions cover **37 selected sdist/13 wheel files**, within **44/21 total regular files**, including both expanded test files and exact engine/web/private-seed/helper bytes. Python>=3.9 is unchanged.

All ten installed origins/profile defaults, CLI/web help and the unchanged listening HTTP adapter pass from the installed wheel. Actual strict verification/priming/initializer arrays and counts remain correct; legacy payload has no seed; null400 and stale-offset409 make no model/publication. The actual updater copies engine/web/private helper and both expanded tests from the verified sdist into an isolated fixture with matching bytes. The unchanged shared helper's tar extraction warning remains an accepted tooling Minor.

## Preservation, self-review and limits

All260 original evidence payloads and original indexes are byte-identical. The original16316-byte report prefix/SHA and original1810-byte PR snapshot/SHA remain preserved; the repair is appended and the live PR is rewritten for the final candidate. All157 prior refs remain unchanged. Compact new configs/logs/IDs/native metadata/package identities and exact RED test bytes are under [fix1 evidence](task1002-fix1-evidence/README.md); media, binaries, environments, installed/source-export trees and local execution controls are excluded.

Author self-review checked I1's direct API/cause/precedence, returned-capture ownership, real-route stage/cleanup, unchanged legacy behavior, identical RED/GREEN tests, frozen native pins and package bytes. No known new fix breakage remains; this does not replace the same reviewer's scoped re-review.

Original544 full/269 affected/PAGE results remain attributed to285, with their native-identity limitation explicit. This repair adds89 owning checks on each actual interpreter and a new final package gate, not a relabelled full suite. Declared CFR/observed-stamp/O(N) limits, real-model quality, UI/P16D/C01/P17/HDR and native-interruption gates remain separate.
