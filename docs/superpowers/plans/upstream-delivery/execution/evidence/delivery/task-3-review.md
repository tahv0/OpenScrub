# Task 3 / P03 review

## Spec compliance

- ✅ Spec compliant for the implementation visible in packaged base `92124753736e287ac800af91f0ac96f3e96c01be` → head `6ae212a35b094fc9466f1616afb2c5bb5c0497f8`; no blocking missing, extra, or misunderstood behavior found.
- ✅ `openscrub_web.py:2092`, `openscrub_web.py:2126`: stop invalidates the logical slot before cancellation; cycle identity and existing view ownership gate completion, errors, cleanup, and scheduling. Ordinary overlapping refresh calls coalesce.
- ✅ `openscrub_web.py:2108`: the metadata/log helper races fetch, HTTP validation, and JSON consumption against deadline/cancellation, requests abort, and removes deadline/listener state. Publication remains outside the losing operation. The implementation and report correctly distinguish logical release from forced transport termination or suspended-JavaScript wall-clock guarantees.
- ✅ `openscrub_web.py:2126`, `openscrub_web.py:2152`: success chains a 900 ms timer after completion; retry delays cap at 10000 ms; opening resets failures; lifecycle wakes coalesce through an owned immediate timer and replace pending work. The new paths initiate no job mutation.
- ✅ `openscrub_web.py:2264`, `openscrub_web.py:2306`: validation precedes shell insertion, status failures are caught, valid progress/log DOM is retained, empty length is authoritative, shrink resets/refetches the existing log route, and initial last-400/stick behavior remains. Poll feedback is separate from save feedback.
- ✅ `openscrub_web.py:2369`, `openscrub_web.py:2883`: automatic review is outside cycle occupancy; phase eligibility survives same-phase polls, expires on observed exit/return, and combines with review-initiation supersession and the inherited view fence. Failure returns initialization to retryable idle state; manual done-phase reopening retains its publication path.
- ✅ `CLAUDE.md:1025`, `CONTRIBUTING.md:25`: contributor verification now discovers `tests/`, as explicitly requested. The remaining P07a test-harness edit only supplies the newly used window event-listener boundary.
- ⚠️ Cannot verify from this diff alone: all unchanged Austin defaults, help/preview/editor/audio/save behavior, all P07a draft/ACK guarantees, and Python compatibility across the whole application. No conflicting product changes appear in the package; recorded focused/full/Python 3.9 results support those preservation claims but this task gate is not a whole-branch review.
- ⚠️ Cannot verify native OS suspension timing or other browsers; controlled visibility/events and Chromium held bodies do not establish those properties. The report states this limitation accurately.

## Strengths

- `tests/test_job_polling_node.py:62`, `tests/test_job_polling_node.py:74`, `tests/test_job_polling_node.py:100`, `tests/test_job_polling_node.py:108`: tests execute actual emitted APP_JS and assert request counts, completion cadence, ignore-abort logical release, bounded backoff, and obsolete-finally ownership. These check behavior rather than reproducing polling logic.
- `tests/test_job_polling_node.py:119`, `tests/test_job_polling_node.py:130`, `tests/test_job_polling_node.py:143`, `tests/test_job_polling_node.py:152`: cursor reset, review phase/initialization semantics, and lifecycle replacement receive focused deterministic schedules.
- `tests/test_job_polling_browser.py:150`, `tests/test_job_polling_browser.py:162`: separate real HTTP headers/held-body paths exercise deadlines and view switching using production route payloads, alongside full-PAGE interaction cases. Optional existing tooling introduces no mandatory frontend dependency.

## Issues

### Critical

- None found.

### Important

- None found.

### Minor

- `tests/test_job_polling_browser.py:139`, `tests/test_job_polling_browser.py:141`: the universal console filter treats every message containing `net::ERR_FAILED` or `503` as an expected injection, including in healthy scenarios, then labels the entire console list `expectedInjectedConsole`. This is weaker than the report's claim that all unrelated errors are rejected: an unrelated resource failure with either substring would pass. Track each scenario's expected injected diagnostics and assert their counts/types; require no such diagnostics in scenarios without injections. This is a test-evidence precision gap, not an observed product failure.

## Evidence and review boundaries

- Read the task brief, implementer report, baseline research, and packaged diff. The initial batched tool response truncated the package/report, so their unread/truncated content was retrieved in bounded chunks; changed source files were not separately reread. A later mechanical package scan returned line numbers only.
- Named unchanged-code risk: whether shrink recovery matches the existing route's `from` contract. Focused check of `openscrub_web.py:1066` confirms the route returns the requested offset, sliced lines, and current total length; the new `from=0` recovery is compatible.
- Named unchanged-code risk: whether automatic `loadReview` introduces a different panel-selection side effect. Focused check of `openscrub_web.py:2843` confirms its existing `showPanel("review")` behavior; the task preserves that call and confines the new publication gate to automatic review.
- Inspected existing `/tmp/openscrub-task3/final-focused.log` (**84 passed**), `final-full.log` (**218 passed**), `final-python39.log` (**86 passed / 131 deselected**), `source-identity.log` (native worktree module), `final-build.log` (sdist → wheel), `final-install.log`, and `installed-smoke.log` (HTTP success, source equality, tests inclusion). These contain no unexpected warnings or failures.
- Inspected RED evidence: `red-node.log` ends **18 failed / 2 passed**; `red-online.log` demonstrates missing cancellation; `red-browser.log` demonstrates baseline overlap **5 versus 1** requests. These support the report's distinction between new fixes and inherited passing fences.
- Inspected `browser-summary.log`: **18 schedules**, empty page-error arrays; injected network/503 diagnostics are recorded. Interpretation is subject to the minor filter gap above.
- No suites, browser runs, builds, Git commands, or product mutations were performed. Existing result logs are evidence read, not independently repeated execution; frozen-head cleanliness and execution provenance beyond the supplied package/logs were not independently established. The evaluated-JS artifacts exist, but a parse command's exit status was not independently reproduced.

## Assessment

**Task quality: Approved.**

The implementation is narrowly scoped and uses explicit cycle/timer identities with the existing view owner, rather than adding a second generation or rewriting unrelated async behavior. Meaningful emitted-JS and full-PAGE schedules cover the principal failure and ownership cases; the minor console-accounting follow-up does not block this task gate.
