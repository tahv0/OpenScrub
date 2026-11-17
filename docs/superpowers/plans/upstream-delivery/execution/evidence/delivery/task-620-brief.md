## Task 620: combine reviewed report and browser prerequisites

### Global constraints

Preserve Austin upstream defaults, Python >=3.9, report/API compatibility, source-frame accuracy, privacy/vault behavior and distribution paths. No custom training, Findings/journal/sections workbench, dependency/version changes or new root helpers. Use synthetic data and isolated runtime paths. Do not change the original checkout or user runtime data. No remote publication or subagents.

### What, why and when

Prepare the explicit local prerequisite base for P06B.1/P06B.2. Combine reviewed P06A atomic publication, P06D complete review round-trip, and P07a browser acknowledgement/draft handling. The latter is needed before new server busy responses; content/publication fixes must survive the lifecycle integration. This is local prerequisite assembly, not a new umbrella upstream PR or the complete C01 application.

The supervisor will create `integration/report-prerequisites` at reviewed P06D `7063082ef2a2ff5e56d9aafacff9bd43363b05b3`. This already includes P06A `66787aa09a958154e81e75f9bdc54d9788feb843` and the test-only baseline fix `e21ebdf6e3ee46e6c65050dc956a9a3459152269`. Cherry-pick the two reviewed P07a commits in order: `786990d9102d41c0ec698d6f31fe798de66a049a`, `92124753736e287ac800af91f0ac96f3e96c01be`. Do not apply Save As or P11A, and do not cherry-pick donor integration history.

### Work

1. Verify branch, exact base and clean worktree. Read task-64-report.md and task-71-report.md (including its appended fix evidence), plus task-71-fix1-review.md, only for relevant integration contracts/evidence; no need to repeat their independent full investigations.
2. Apply the reviewed commits with provenance. Resolve only genuine integration conflicts, preserving both intended changes. Keep contributor/default pytest discovery including root and tests/, and tests in source distributions. Record any manual resolutions and why. No new server transaction/lifecycle/replay behavior.
3. Run the full combined suite in `/tmp/openscrub-baseline-20261116/env-opencv4.sh`, build sdist then wheel, parse the evaluated embedded JS and check changed packaged source bytes. Prior branch counts imply 230 tests before any justified integration-only additions; report the actual collected count rather than forcing a number.
4. Exercise one combined synthetic save → render → fresh reopen route: full original review row order and disabled/manual/audio metadata survive; browser snapshot code remains present/executable. The existing Task64 real render/reopen fixture and Task71 route/browser harness can be reused with source pointed to this exact branch. Avoid repeating every standalone Chromium scenario without an integration concern. Do not use old user jobs or download models.
5. Check no newly included custom-training/workbench files/imports/dependencies; record exact final head and clean state. Report untested platforms honestly. Preserve individual PR branches and reports unchanged.

Write `task-620-report.md` in this SDD workspace, including commit range, cherry-pick provenance, resolutions, exact commands/counts/log paths and remaining limits. No external PR or publication. This base will receive its own scoped integration review before lifecycle implementation starts.
