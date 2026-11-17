## Task 110: stop ordinary tracker work at its existing Python boundaries

### Global constraints

Preserve Python>=3.9, uncancelled default matching/scale/cadence/padding/coverage/order, report fields and existing P06 job/source/operation ownership. No model/training/optional policy, new decoder workers/deadlines, dependency/version changes, native interrupt promise or broad tracking refactor. Tests under tests/, synthetic media only. No original-checkout/user-data changes, publication or subagents.

### What, why and when

Read `tracker-cancel-baseline-research.md` and its reproducible evidence. Full actual NCC tracking ignores cancellation: after match1 it still performs41matches/13grabs/19reads, and natural hold coverage continues appending. A neighboring person-helper catch also swallows PipelineCancelled. The existing web route suppresses cancelled report publication and retains/release ownership correctly; this task fixes repeated compute observation, not the web publication system.

Supervisor creates `pr/manual-tracker-cancellation` from reviewed `12919c96c6f7558136b50d7b4d85e5e6b62f1971` in the native worktree before dispatch. This explicit prerequisite supplies capture-finally and operation/lifetime contracts; no copying their code into the small diff. P10A exact frames, P10B bounded native workers and optional O02 stay separate.

### Implementation contract

1. Use existing PipelineCancelled for cancellation, not [] or successful partial samples. Add a local cooperative check before capture acquisition: cancellation takes precedence over unusable input. Precanceled missing/small/valid requests therefore raise before opening a capture; uncancelled invalid/unreadable inputs retain their [] behaviour. Do not add another capture-release owner.
2. In the person-helper handoff, re-raise PipelineCancelled before the existing generic failure fallback. Check after a normal helper return before accepting its successful samples or starting generic fallback. Ordinary non-cancellation helper failures still use the existing fallback. Check after model factory resolution before generic seed work to observe cancellation arriving there; resolution itself remains uninterrrupted.
3. Poll at every NCC forward/backward sampling-loop head before time evaluation or _gray, analogous to existing Vit loop checks; poll before every _hold_rest append; check common successful returns for both generic backends. Keep existing Vit polling. A constant3-scale sweep may finish the current sample before the next outer checkpoint; no need to alter native match calls or geometry. A final successful-return check is cooperative, not an atomic publication guard.
4. Preserve Task621 cap.release exactly once after every path that actually opens a capture. Existing actual web tracker Event, captured operation validation and owned-thread cleanup should require no changes. Do not return a partially tracked result after observing cancellation.

### Evidence and delivery

Add meaningful actual-function regressions in `tests/test_manual_tracker_cancel.py`. Use the retained31frame96×96 marked steady/natural-loss media, default step_frames2/thr.55/scale.5 and complete stored15sample arrays. Natural NCC selection uses the actual missing-model fallback with downloads blocked. Compare all uncancelled times/boxes/scores and cb=None/nevercancelled equivalence. Establish owning RED before edits.

Control cancellation only at actual completed-match/log/append boundaries: forward/backward match, hold start/after first append/final backward append. Allow only remaining scale work in the current sample, no later frame grab; require exact PipelineCancelled and cleanup. Controlled person-helper exception/normal-return and ordinary failure controls are explicitly boundary tests, not person inference. Precancelled inputs must create no capture; uncancelled early returns, unexpected compute errors and successes must release existing captures once.

Retain an actual Flask tracker/cancel schedule: cancelled status and no report publication, deletion409 while work/cleanup owns source, capture closed before lease release, then deletion200 and zero owner/work/thread counts. No AST-mini route or replacement tracker. Use bounded gates with unconditional harness cleanup; work counts are not wall-clock/native interrupt guarantees.

Run focused RED→GREEN, relevant manual/ownership regressions, one full discovered suite after stabilization, sdist→wheel/exact source/tests/defaults and installed CLI/web smoke; focused active-source Python3.9 checks. No new models or broad inference, benchmark, dependency installs or browser UI run. Artifacts `/tmp/openscrub-task110`; reuse existing env-opencv4.sh, Python3.9 env and offline build tooling. Native worktree/Git writes may use already-authorized require_escalated.

Self-review and commit; write `task-110-report.md` / `task-110-pr.md` here with exact base/head, concrete cancellation work saved, intentionally clarified entry semantics, full output/ownership controls, commands/results and platform/native-call limitations. Keep report/title about ordinary tracking cancellation, not optional object-following or inference speed. No publication or nested agents.
