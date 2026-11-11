# Persistent runtime error logging

Goal: make overnight worker failures diagnosable without changing training,
model selection, section approvals or redaction policy. Publish through Git
to integration/all-prs; main is not a target.

Base: 08f432b6160d2fc22e51456020df929de6717e16 (sections/progress/model library).
Adapt the earlier local logging-only patch; do not replace newer source files.
Use a stdlib rotating file sink plus independent stderr, native-fault dumps,
an unclean-exit marker and bounded-frequency progress sampling.

- [x] Recover existing logging implementation and regression tests.
- [x] Confirm pre-fix failure on the current integration snapshot.
- [x] Integrate without removing telemetry parsing, section ranges or library code.
- [x] Reproduce and fix two integration regressions: actual telemetry must reach
      the watchdog; resumed scan records must not use a prior failed-learning stage.
- [x] Run local logging/progress checks (29 passed).
- [ ] Run current-source GitHub Python 3.10 suite and build/browser checks.
- [ ] Publish verified logging source through a PR to integration/all-prs.

Review focus: disk-write fallback, token redaction, subprocess final output,
HTTP traceback context, clean shutdown vs forced termination, per-frame overhead.
No frame decoding for diagnostics; only existing counters are sampled.
No request bodies, headers, query strings or environment dumps are added.
Logs may contain private paths and exception text and are outside the vault.

Limits: SIGKILL/OOM/power loss or storage failure can prevent a final message.
No Windows/CUDA/user-footage test or diagnosis of the prior overnight failure.
No independent reviewer agent available; direct source review and regression
checks are required. Validation results belong in the PR, including failures.
