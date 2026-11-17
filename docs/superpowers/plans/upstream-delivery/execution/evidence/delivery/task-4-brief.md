## Task 4: estimate stage completion from bounded recent progress

### Global constraints

Preserve Austin upstream defaults, Python>=3.9, existing stage progress mapping/precision and public nullable `eta` in seconds. No training/workbench, inference/scheduling change, diagnostics system, dependencies/version or new runtime module for one owner's small state. New tests under `tests/`; synthetic fixtures and existing tools only. No original-checkout/user-data changes, publication or subagents.

### What, why and when

The current `WebCallbacks.progress` uses a whole-stage wall-clock average and EMA, so a fast early prefix continues to dominate the remaining-time estimate after a sustained slowdown. Extract the donor's recent-rate idea as a focused P04 PR, independent of polling/preview/save changes. Preserve donor `0b2e3d1d` and `367148d` as provenance only; their diagnostics and removed preview-cache changes do not belong here.

The supervisor will create `pr/recent-stage-eta` in `/home/tahv0/.codex/worktrees/c832/OpenScrub` from exact Austin-plus-test-only base `e21ebdf6e3ee46e6c65050dc956a9a3459152269` before dispatch. Read only this brief and the corresponding original callback/donor ETA hunks. Establish the controlling fake-clock RED before implementing; no standalone full research task is needed.

### Implementation contract

1. Keep scan progress `(base=0,span=0.45)`, post `(0.45,0.05)`, other/render `(0.5,0.5)` and5-decimal public progress unchanged. Only the rate/ETA calculation and its private callback state change. Preserve nullable seconds and existing `job_public`/UI consumption.
2. Use monotonic time for elapsed throughput observations. Retain a bounded recent window of120seconds, sampling no more often than every5seconds except completion. Retain at most one predecessor sample before the cutoff if needed for the interval rate; do not retain the stage's entire history. Constants belong next to this single owner.
3. Use whole-stage rate only for startup after at least3seconds with positive progress. Prefer recent rate once its observation span reaches20seconds. Use the donor follow-up smoothing weights0.35previous/0.65new estimate. A mature recent window with no positive progress must not silently fall back to an optimistic historical rate. ReturnNone when no useful finite positive rate exists; never publish negative/nonfinite ETA.
4. Reset samples and smoothing on stage change, completion and current-counter restart/regression. Existing terminal job paths already clear published ETA; verify the callback/worker interaction without widening into the P06 lifecycle implementation. A fresh attempt has fresh estimator state. No new timer thread or UI polling owner.
5. Do not import removed diagnostics/activity fields, preview caching or training stages. Existing client fallback remains a separate consumer; update misleading average-only comments if touched, but do not redesign ETA rendering or add public rate fields.

### Evidence and delivery

- Actual `WebCallbacks` tests in `tests/test_scan_eta.py` using a controlled monotonic clock: startup, long fast prefix followed by sustained slow tail, steady rate, zero progress, repeated/subsample calls, backward wall-clock change, same-stage counter regression, stage changes, completion, unavailable/zero totals and bounded sample storage. Assert concrete estimates/ranges tied to the selected calculation, stage progress compatibility and finite output, not just private field names.
- Record a before/after controlled timeline showing why recent ETA better reflects the slow tail; it is an estimator comparison, not an inference-speed benchmark or promise of prediction accuracy.
- Exercise actual job metadata and emitted browser ETA rendering during a small synthetic controlled stage transition, using the existing browser fallback and real route where practical. No scanning models or large video are needed. Keep P03 request races outside this change.
- Run focused RED→GREEN, full discovered suite once after stabilization, sdist→wheel/source/tests inclusion and installed CLI/web smoke. Use the prepared Python3.12 environment and focused Python3.9 active-source checks; no dependency changes. Generated evidence stays under `/tmp/openscrub-task4`.
- Self-review and commit. Write `task-4-report.md` and `task-4-pr.md` under this SDD workspace with exact base/head, timeline, parameter tradeoff, commands/results, changed files and limits. Lead with long scans' early speed bias; no claimed inference improvement or upstream acceptance.

Use `/tmp/openscrub-baseline-20261116/env-opencv4.sh` and `/tmp/openscrub-python39-20261117/env.sh`, asserting active-source imports. Browser plugin unavailable: existing Playwright/Chromium under `/tmp/openscrub-save-as-20261116/{node_modules,browsers,tools}` is the fallback. Native worktree/Git writes may require already-authorized `require_escalated`. No nested agents.
