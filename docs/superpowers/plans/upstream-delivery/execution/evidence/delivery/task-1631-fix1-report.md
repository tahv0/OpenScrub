# Task 1631 fix1 — I1 frame-count compatibility

Final clean candidate head: `83af23b5fd3c5922d0d476ba2a6ae21a3598ced2` on `pr/render-geometry-validation`, native source `/home/tahv0/.codex/worktrees/c832/OpenScrub`. Fix base is `7415e5a7526696a33f78a8c209bf062239a31d1c`; upstream contribution base remains `e21ebdf6e3ee46e6c65050dc956a9a3459152269`. Commit `83af23b` changes one runtime condition and adds owning metadata controls. No publication, new dependency, broader scope or shared-tool/environment edit.

## Review finding and correction

Independent review I1 correctly identified `total < 0` as a new progress/control policy. A finite negative `CAP_PROP_FRAME_COUNT` converts to an integer and does not make positive dimensions unusable for allocation/decoding/encoder setup. Existing count consumers use it for progress/logging, with the existing divisor/completion handling; those consumers are unchanged.

The runtime fix removes only `or total < 0` from `_geometry_metadata`. Positive usable dimensions and finite numeric metadata/conversion checks remain. No normalization, replacement count or new count-sign policy was introduced. This does not assert how often any real backend returns a negative count.

Covering tests in `tests/test_render_geometry.py` observe the public SDR/HDR renderer boundary, not just the condition. `test_renderer_admits_finite_negative_frame_count` supplies positive dimensions and either positive-count control or count -1, and expects a deliberate marker at the next native acquisition boundary (SDR encoder selection; HDR decoder creation with its dimension-derived buffer size). Its HDR observation also verifies release of metadata capture. A `finally` releases the deliberately interrupted SDR fake capture as test-harness ownership; this makes no new R cleanup claim. `test_renderer_rejects_unusable_metadata` retains positive-dimension requirements and nonfinite/unusable count conversions at both renderer boundaries, asserting rejection before native acquisition and capture release. These are metadata admission controls with controlled captures, not actual negative-count-backend/media-frequency evidence.

## RED, GREEN and acceptance

The owning RED selected 20 cases against unchanged 741 runtime bytes under explicit D01 development policy: both negative-count cases raised the newly disallowed `ValueError` instead of reaching native acquisition; **2 failed, 18 passed, 109 deselected**. The positive-count and unusable-metadata controls already passed, so the regression is at the intended sign-policy boundary. The same test bytes are retained in the final Git object and evidence.

After removing that condition, all **129 geometry cases passed** in development. The corrected clean Git object was frozen before acceptance, with caller-selected hashes for all 114 tracked files and the same six explicit product-module inventory entries. Final guarded gates:

| Gate | Result | Run |
| --- | --- | --- |
| Actual Python 3.12.16 targeted geometry file | **129 passed** | `task1631-fix1-589748b0202843e09075e8b5ad857085` |
| Actual Python 3.9.25 targeted geometry file | **129 passed** | `task1631-fix1-703ac65354c14ce18870936f2d91723b` |
| Final-byte offline sdist → extracted source → wheel → installed target | **Passed**, including installed defaults and CLI help | `task1631-fix1-1472ad5c24424a208491cb6199d3fbba` |
| Actual installed listening web smoke | `/api/jobs` HTTP 200 `[]`; `/` HTTP 200 OpenScrub; owned server terminated/reaped, rc0 | same package run, `http://127.0.0.1:38813` |

The package helper compared selected runtime/test/pyproject bytes through the sdist and extraction, built the wheel from the extracted sdist, compared all six runtime modules in the wheel/installed target, and checked exact `Requires-Python: >=3.9`. Direct CLI/server Python children retained strict installed source guards, bootstrap paths excluded. Loopback permission was explicit at the package invocation; the earlier setup socket failure was not repeated. No new setup/harness failure occurred in this fix round.

The prior **243-test full discovered suite remains exact evidence for 7415e5a**, and was not repeated or relabeled as final-83 evidence. This follows the explicitly scoped review instructions for the one-condition correction. No new broad media/P16B matrix, throughput/memory measurement, timing gate or unrelated gate was run. The targeted geometry file includes its existing tiny actual SDR/preview controls; the new metadata cases remain controlled-boundary tests.

## Commands, configuration and artifact identities

`task1631-fix1-evidence` retains complete outputs, all fix-run preflight/runtime configs, exact frozen caller configs, the covering test artifact, one-condition/code-test diff, helper identities, adapter copies and emitted child arguments (`commands.json`). The existing task fixture/plugin and loopback listener adapter were reused unchanged. Scratch remains the supervisor-owned `runtime/task1631/runs`; fix configurations/logs are under `runtime/task1631/fix1`. Every test invocation is serial supported `-m pytest` with helper-owned unique cwd/basetemp/cache. No arbitrary pytest wrapper, guard weakening, downloads or prepared-environment writes occurred. Helper code/README hashes match the original adoption evidence exactly; the original evidence directory remains unchanged.

Final caller invocations (actual child argv and build/install commands are retained in `commands.json`):

```bash
python3 /home/tahv0/src/OpenScrub/docs/superpowers/plans/upstream-delivery/execution/tooling/verify.py --config /home/tahv0/src/OpenScrub/.superpowers/sdd/README/runtime/task1631/fix1/final312.json preflight
python3 /home/tahv0/src/OpenScrub/docs/superpowers/plans/upstream-delivery/execution/tooling/verify.py --config /home/tahv0/src/OpenScrub/.superpowers/sdd/README/runtime/task1631/fix1/final312.json run -- -m pytest /home/tahv0/.codex/worktrees/c832/OpenScrub/tests/test_render_geometry.py -q --tb=short -o pythonpath=/home/tahv0/src/OpenScrub/.superpowers/sdd/README/runtime/task1631/adapters -p task1631_fixture
python3 /home/tahv0/src/OpenScrub/docs/superpowers/plans/upstream-delivery/execution/tooling/verify.py --config /home/tahv0/src/OpenScrub/.superpowers/sdd/README/runtime/task1631/fix1/final39.json run -- -m pytest /home/tahv0/.codex/worktrees/c832/OpenScrub/tests/test_render_geometry.py -q --tb=short -o pythonpath=/home/tahv0/src/OpenScrub/.superpowers/sdd/README/runtime/task1631/adapters -p task1631_fixture
python3 /home/tahv0/src/OpenScrub/docs/superpowers/plans/upstream-delivery/execution/tooling/verify.py --config /home/tahv0/src/OpenScrub/.superpowers/sdd/README/runtime/task1631/fix1/final312.json package
```

The final group, including package/listening invocation, used authorized escalation for loopback socket permission. Workloads still used the reviewed isolation helper and declared source/guard configuration. Actual executables and versions are in preflight/log records. The exact caller development config used for RED is also retained in that run's `runtime-*.json`; its expected source hash selects unchanged 741 core plus the added covering tests.

Final sdist: `openscrub-1.0.96.tar.gz`, **529486 bytes**, SHA-256 `73678177d058852137104e7f0bf069459e5b460a0adb4896524134b29fb2a687`.
Final wheel: `openscrub-1.0.96-py3-none-any.whl`, **435680 bytes**, SHA-256 `8a73db845bf1ad986de66451403e716ed5afc546a29ebdbb288b979faa91ed79`.
`source-final.json` records exact core/test/web/pyproject bytes; the helper's complete `package-identities.json` binds the final artifacts and inventory. Original task evidence, including its previous artifact identities and failures, was preserved.

Self-review confirms the runtime diff is only that condition removal, the native checkout is clean and the guarded checks above pass. No remaining I1 concern is known; the supervisor owns scoped re-review. Earlier R/P/P06D/C01 and platform/native/cooperative-isolation limits remain unchanged, as do the public-wrapper/private-body boundary and linear preflight/diagnostic-map costs. No publication, full-suite-final-source or performance claim is made.
