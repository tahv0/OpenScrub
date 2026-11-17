### Spec Compliance

- ✅ Spec compliant for Task 4/P04 at `e21ebdf6e3ee46e6c65050dc956a9a3459152269..d129e23e5fe144edb8bbd5675809c1877cfe4d0f`. The unchanged progress expression preserves all stage mappings and five-decimal precision (`openscrub_web.py:395`). The estimator uses monotonic observations, the specified 120/5/20/3-second parameters, the bounded crossing predecessor, and 0.35/0.65 smoothing (`openscrub_web.py:364`, `openscrub_web.py:402`, `openscrub_web.py:418`, `openscrub_web.py:425`, `openscrub_web.py:436`).
- ✅ Numeric unavailable totals, nonfinite observations, completion, stage transitions, and counter regression clear published ETA and estimator state; a mature stalled window does not recover the historical startup rate (`openscrub_web.py:403`, `openscrub_web.py:410`, `openscrub_web.py:429`, `openscrub_web.py:440`). The existing progress input expression remains intact, consistent with the supplied numeric-zero-sentinel ruling (`openscrub_web.py:397`).
- ✅ Production changes remain local to the callback's private state and its explanatory UI comment. The other hunks provide test discovery, sdist test inclusion, and matching contributor commands (`openscrub_web.py:381`, `openscrub_web.py:2174`, `pyproject.toml:123`, `CONTRIBUTING.md:25`, `README.md:604`). No new runtime module, public rate field, dependency/version change, worker change, or inference/scheduling change appears in the packaged diff.
- ✅ Controlled timeline, callback/worker tests, Python 3.9 execution, packaging, installed entrypoint smoke, and real-route/browser transition evidence are recorded (`task-4-report.md:27`, `task-4-report.md:56`, `task-4-report.md:60`, `task-4-report.md:62`, `task-4-report.md:65`, `task-4-report.md:92`). The inspected browser evidence shows scan ETA, cleared ETA on render entry, a new render ETA, and cleared ETA at completion (`/tmp/openscrub-task4/browser-final.log:28`, `:53`, `:65`, `:77`).
- ⚠️ Unchanged upstream defaults and wider lifecycle behavior are not independently audited by this task diff. The controller should retain the separate whole-branch review; this task adds real worker-path tests for done/cancel/error and callback freshness rather than changing those paths (`tests/test_scan_eta.py:165`).

### Strengths

- The rate selection directly addresses the early-speed bias, while explicitly suppressing a mature zero-movement window instead of falling back to an optimistic whole-stage rate (`openscrub_web.py:425`, `openscrub_web.py:429`). The slow-tail test asserts a concrete estimate close to the known synthetic remaining duration and also checks the public progress value (`tests/test_scan_eta.py:19`).
- Retaining the last observed counter independently from retained samples catches same-stage restarts even between five-second samples (`openscrub_web.py:382`, `openscrub_web.py:411`, `openscrub_web.py:417`). The pruning loop keeps only the crossing predecessor and recent samples (`openscrub_web.py:422`).
- Tests exercise the actual callback with independent monotonic and wall clocks, and cover concrete smoothing values, bounded storage, invalid estimates, completion, phase changes, and terminal worker cleanup (`tests/test_scan_eta.py:10`, `tests/test_scan_eta.py:19`, `tests/test_scan_eta.py:165`). The inspected focused, full-suite, and Python 3.9 logs are clean: 25, 159, and 25 tests passed respectively (`/tmp/openscrub-task4/green.log:2`, `/tmp/openscrub-task4/full.log:4`, `/tmp/openscrub-task4/python39.log:2`).
- The report states the window/cadence responsiveness tradeoff, sparse-callback limitation, and independent client fallback behavior without claiming inference speed improvements (`task-4-report.md:43`, `task-4-report.md:113`). Packaging evidence records exact source/test identity and the unchanged Python floor (`/tmp/openscrub-task4/package.log:6`).

### Issues

#### Critical (Must Fix)

- None.

#### Important (Should Fix)

- None.

#### Minor (Nice to Have)

- `/tmp/openscrub-task4/browser-final.log:84`: final browser evidence contains four expected missing-preview 404 console warnings. This is disclosed and does not undermine the ETA assertions or indicate an ETA regression, but leaves noisy browser output. For future QA, provide a tiny synthetic preview fixture so unexpected failed requests remain conspicuous; no production preview behavior change is needed.
- `task-4-report.md:107`: the packaging/extraction harness emitted a future tar-filter deprecation warning. This is tooling noise, not a shipped runtime defect. Specify the appropriate explicit extraction filter in that temporary harness when the harness is next used.

### Assessment

**Task quality:** Approved.

**Reasoning:** The implementation meets the bounded recent-rate contract with a small, single-owner state machine and concrete tests for the main estimator and reset behavior. No blocking correctness or scope issue was found; the two minor findings concern disclosed validation-harness noise.

**Review evidence and limits:** Read the supplied brief, report, and packaged diff once; no Git commands, source/checkout/index/ref mutations, subagents, or test/build/browser reruns were performed. One focused evidence check investigated the named risk of non-pristine verification output by reading the existing `green.log`, `full.log`, `python39.log`, `package.log`, and `browser-final.log`; it confirmed clean pytest output and the disclosed preview warnings. A focused report search located the disclosed extraction warning. No code outside the packaged diff was inspected. The only write is this requested review artifact.
