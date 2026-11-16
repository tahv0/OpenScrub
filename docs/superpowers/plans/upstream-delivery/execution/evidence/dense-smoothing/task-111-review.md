### Spec Compliance

- ✅ Spec compliant for Task111/P11A at `e21ebdf6e3ee46e6c65050dc956a9a3459152269..f19be5fe3b9176e568ea7bf761493bd267fee95e`. The only runtime changes are capture ownership and sequential `read()`/`grab()` selection in `openscrub.py:1440` and `openscrub.py:1471`. No seek, shared positioning state, worker, policy, dependency or unrelated performance feature was introduced.
- ✅ `openscrub.py:1473` checks cancellation at the same logical positions, advances the index exactly once after a successful operation, and retains the common EOF sentinel on either failed operation. The needed-frame predicate is the existing span membership; grayscale cache contents, tolerance, eviction, matching, interpolation and grace logic remain unchanged in the diff. The original capture remains owned even when opening fails, and its `finally` covers normal return, EOF, cancellation and exceptions.
- ✅ Meaningful actual-module regressions accompany the change (`tests/test_dense_smoothing_io.py:1`), including real lossless marked video and complete baseline Detection hashing (`tests/test_dense_smoothing_io.py:226`). README/CONTRIBUTING discovery and sdist test inclusion are the limited supporting changes requested by the brief.
- ✅ Benchmark implementation uses complete imported modules, fresh per-call captures/detections, operation/frame auditing, three warm-ups/five alternating samples, and separate cancellation observations (`benchmark/dense_smoothing.py:82`, `benchmark/dense_smoothing.py:130`). Retained measurements support the exact-commit, low-resolution claims; codec prefix decoding is explicitly retained (`task-111-report.md:85`).
- ⚠️ Public PR accompaniment is outside this local review: the fixture generator/commands and detailed measurements currently reside in SDD evidence (`late-window-research.md:252`, `task-111-report.md:169`), while `benchmark/dense_smoothing.py:4` points to that evidence. Preserve/attach these materials when publishing the owning PR so the benchmark remains reproducible for its reviewers. No publication was requested or performed here.

### Strengths

- `openscrub.py:1440` separates the owned capture from the optional usable capture, fixing failed-open cleanup without changing the unavailable-video behavior.
- `openscrub.py:1471` keeps both advance mechanisms under the existing cancellation, failure and frame-index bookkeeping. It cannot silently resume after a failed operation and label later pixels with the failed frame's index.
- `tests/test_dense_smoothing_io.py:1` tests frame identities and observable output, failures/EOF, checkpoint counts, real matching and ownership rather than only asserting that `grab()` was invoked. The real-media assertions include all Detection fields and no positioning calls.
- `benchmark/dense_smoothing.py:82` records function-owned release counts before harness cleanup, so baseline cancellation leaks are neither hidden nor allowed to contaminate later samples.
- `task-111-report.md:133` clearly limits whole-process peak RSS, and `task-111-report.md:169` preserves the rejected seek's cancellation evidence and avoids 4K/VFR/platform or native decode attribution claims.

### Issues

#### Critical (Must Fix)

- None found.

#### Important (Should Fix)

- None found.

#### Minor (Nice to Have)

- None requiring a code change.

### Checks

- Read the supplied task brief, implementer report, review-method template and prepared diff. The initial combined tool output was truncated, so the previously cut-off benchmark/runtime portion was retrieved in bounded sections; no changed source file was separately opened, and no Git command or product/Git-state mutation was performed.
- Focused evidence check — risk: reported timings/counts might describe the earlier AST experiment rather than the submitted implementation. Inspected `task111-evidence/source-identity.json:1`, the benchmark loader/timing code, and parsed `task111-evidence/timing-results.json:1`. The retained source hashes agree across identity and timing records; every recorded run has the stated counts, no positioning/state, one explicit normal release, the same 38-row hash and reference markers 17872–18000. Medians are 5.530690→1.797305 s and 5.479827→1.386866 s, matching the report. Cancellation records preserve multiples-of-90 advances and explicit after-version release. This is evidence inspection, not a new timing run.
- Focused evidence check — risk: equal Detection records alone might conceal changed rendered masks. Inspected `task111-evidence/verify_runtime.py:19` and `task111-evidence/runtime-results.json:1`: the harness renders the complete before/after modules with parser-default blur/padding/face shape, decodes and compares every one of 130 output frames, and records matching hashes. The separate Tesseract path exercises scan/report/render; its 20-frame result is obtained from capture metadata, not an additional decoded-frame equality comparison.
- Focused evidence check — risk: successful summaries might conceal failed/noisy required checks. Read retained RED, owning, full-suite and build logs. RED ends at 17 failures/3 passes; owning is 20 passes; final suite is 154 passes; full isolated sdist→wheel build succeeds. Final owning/suite/build logs contain no warnings. No tests, build, render or timing experiments were repeated.
- Checked retained fixture encoder commands (`late-window-research-evidence/generation-commands.json:1`) and the rejected-seek cancellation rationale (`late-window-research.md:103`). The source-level checkpoint preservation and recorded observations justify the sequential choice without claiming that codec prefix decoding is skipped.

### Assessment

**Task quality:** Approved.

**Reasoning:** The runtime change is small and preserves the existing frame/cache/matching state machine while adding deterministic decoder ownership. The tests and retained actual-module/media evidence substantiate the focused optimization; no blocking spec or quality defect was found, with public evidence attachment remaining a publication check.
