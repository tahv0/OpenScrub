# Task 90: B02a make the existing size-jump regression test reliable

## What, why and when

What: correct the existing synthetic test so it verifies that an engulfing look-alike cannot steal the tracked target, without requiring a diagnostic message intentionally suppressed while already held.
Why: unchanged Austin main at 5d3a15a has one remaining baseline failure in the compatible environment. Actual output is correct. Research proves a geometry/non-vacuity assertion passes the original tracker and fails when only the size-jump guard is disabled. This makes the regression meaningful and unblocks a truthful green suite without changing privacy behavior.
When: separate tiny upstream test-only PR after P01 implementation/review; before upstream submission/integration claims that require a green baseline. It is not part of Save As.

## Requirements

- Read `baseline-handoff-test-research.md` in this SDD directory first; it records the exact minimal diff and mutation evidence.
- Supervisor supplies a separate branch based on Austin 5d3a15a. Modify only `test_openscrub.py` unless a discovered necessity is reported. No production algorithm, threshold, logging policy, package constraints or model change.
- Retain real synthetic media and the existing tracker invocation. Remove the brittle `size jump` log assertion. Explicitly require post-occlusion samples, then retain the geometric area assertions that reject the larger target. Keep explanatory test text aligned with the observable safety contract.
- Reproduce existing RED on untouched test before edit. Run revised focused test GREEN. Validate its sensitivity by a temporary source-snapshot mutation disabling only the size-jump guard; it must fail on actual larger-box adoption. Reuse the recorded research method, not a second unrelated mock or assertion of source strings. Never leave a mutant in the active source.
- Run full root suite and full sdist→wheel build on the final tree. Environment: source `/tmp/openscrub-baseline-20261116/env-opencv4.sh`. Record versions and the known OpenCV5 dependency issue separately; do not pin product dependencies or hide baseline failures.
- Local commit and self-review, no remote publishing or subagents. Tests/fixtures remain synthetic; do not access user data. Native-worktree writes may need escalation.
- Full report to `task-90-report.md`, concise PR title/body to `task-90-pr.md` in this SDD directory. Include RED/GREEN/mutation/full-suite commands and results, changed lines, restored source proof, and limits.

## Review focus

The revised test must fail if the production size guard is removed; it cannot pass with zero post-occlusion samples or merely because an unrelated appearance veto held every frame. The original tracker must be byte-identical after any temporary experiment. No feature change travels in this patch.
