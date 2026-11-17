# Task1632 fix round 1: preserve finalization errors

Status: DONE — implemented, self-reviewed, committed and scoped acceptance verified; ready for supervisor scoped re-review. No publication or nested agents. Fresh scoped re-review belongs to the supervisor.

## Source and review requirements

Fix base: `8e70af446caa5ed37e0e36c029925d5caf08f943`, the exact reviewed candidate. Fix commit/final head: `70ec464ca70b5e49751d778890f56029dced0b8a` (`fix: preserve render-local finalization failures`). Worktree/branch remain `/home/tahv0/.codex/worktrees/c832/OpenScrub`, `pr/render-resource-cleanup`. Only `openscrub.py` and `tests/test_render_resources.py` change. The read review is `task-1632-review.md`, with two Important findings: ambient caller exception state could swallow a renderer cleanup failure, and normal stdin-close handling discarded independent errors after a zero encoder exit.

The fix uses the review-reception, systematic-debugging, test-driven-development and verification workflows. The review's explanations were checked against the actual local code, and product regressions were observed before implementation. No new architecture, geometry/publication/deletion policy, dependency, API, or unrelated subprocess behavior is introduced.

## Changes

Each renderer initializes `primary = None` before its owned work. Its own `except BaseException` records only an exception raised by that work and immediately re-raises the same object. Finally uses that local value instead of `sys.exc_info()`. A render that completes inside a caller's currently handled exception therefore still raises a real cleanup error, and the unrelated caller exception remains unannotated. Existing callback/cancellation/setup identities and tracebacks stay intact; existing finally cleanup and secondary diagnostics remain in place.

Normal successful stdin close keeps the existing unbounded healthy encoder wait. A known `OSError` from that owned close instead waits at most two seconds for encoder status. An independently observed nonzero exit keeps `_ffmpeg_failure` stderr/status as primary, with the close error retained in secondary diagnostics. An observed zero exit re-raises the actual independent close error. If status waiting times out, the existing bounded owned shutdown helper runs and the original close error remains primary: a process terminated by this abort is not mislabeled as an encoder-caused failure. Another ordinary status-wait error is retained as secondary to the known close error. No unbounded status wait follows a known close failure, including when EOF was never delivered.

The child shutdown helper and its ordering/fallback remain unchanged. Removal flags remain activated only by the original true cancellation checkpoints and encoder-write exception handlers; no flag is set in the new primary-recording handler. Both legacy existence guards and the prior-output scope remain unchanged. Normal defaults, signatures, encoder/painting/audio calls and successful completion semantics are preserved.

## Genuine RED and GREEN

New/expanded controls use real SDR/HDR encoders, captures, actual stdin/stderr handles, retained exception objects and tracebacks, and production-state assertions before unconditional harness containment. They inject only exact owned close/wait operations.

- The stderr-close test now covers both caller-except states and both actual render-primary states. Otherwise-successful rendering inside a caller `except ValueError` must raise the exact cleanup failure; the caller exception must have no `render_cleanup_errors`. When the callback sentinel is primary it remains the same object in either caller state.
- The stdin-close test calls the real endpoint close, then reports a one-shot OSError. Real encoder exit zero must still raise that same close-error object. A separate actual FFmpeg output-path rejection proves nonzero status/useful stderr remain primary and the close error remains secondary. All close-error status waits are bounded.
- Undelivered-EOF controls raise on the exact first owned close before releasing the pipe. An exact owned wait guard fails fast if production attempts an unbounded wait, preventing the regression test itself from hanging. Actual subsequent waits and shutdown are real. A variant injects one exact bounded status-wait error and proves that error stays secondary while the close error remains primary. Forced process exit codes are recorded as abort outcomes, not encoder causes.

The new cases add twelve applicable controls: four caller-context combinations, four after-real-close/encoder-status combinations, and four undelivered-EOF/status-wait combinations. Complete structured state records accompany the successful scoped runs.

Development gates, in order:

1. `fix1-red`, unchanged reviewed product: **8 failed / 6 passed / 37 deselected**. Failures are the two swallowed caller-except cleanup errors, two swallowed zero-exit stdin-close errors, two unbounded waits on the real nonzero-encoder close-error path, and two undelivered-EOF attempts at unbounded status waiting. This is genuine product RED, not setup/collection error. Exact RED test bytes are preserved in `covering-tests-red.py` and product bytes are the Git base.
2. `fix1-primary-green`, only local-primary change implemented: **8 passed / 43 deselected**. This isolates finding 1 before fixing finding 2.
3. `fix1-covering-green`, both fixes: **14 passed / 37 deselected**. Later test-only additions record actual states and cover a secondary bounded-wait error.
4. `fix1-focused312`: affected resource/N09/renderer controls on actual Python 3.12, **64 passed / 126 deselected**, no skips. This includes all existing N09, normal success/unbounded-wait, real write/nonzero diagnostics, primary-error/cancellation, and prior-output controls. The exact development bytes subsequently match the frozen commit.

No failure or setup warning was discarded, and no whole-suite repeat was performed. The historical 174-pass full suite remains at its exact earlier source/test identity in `task1632-evidence`; it is not relabeled as current-source full coverage.

## Acceptance and provenance

The frozen actual Python 3.9 run `fix1-focused39` passed **64 / 126 deselected**, with no skips. The development actual Python 3.12 run passed the same **64 / 126 deselected**, with no skips; its exact engine/test bytes match the final Git commit. Both runs retained actual primary-identity, caller-annotation, encoder-status and pipe/wait records. In both interpreters, zero-exit close-error controls have actual encoder rc 0 and the original close-error object as primary; actual encoder rejection retains rc 254 and its missing-output-path stderr; undelivered-EOF/status-wait-error controls retain the original close error with owned abort return codes recorded separately. Every asserted capture, pipe, child and stderr state is checked before harness containment.

Final-byte `fix1-package` completed before the interruption: all six phases exited zero (sdist, wheel from extracted sdist, offline no-deps install, installed identity/defaults, installed CLI help, actual listening HTTP adapter). Resume inspection verified those retained results rather than rebuilding or restarting. The original listening adapter served `/api/jobs` as HTTP 200 with an empty list and `/` as HTTP 200 containing OpenScrub, then terminated/reaped the actual installed server with rc 0. The explicitly selected plain-HTTP startup notice is expected. Installed imports resolve to the task-installed target and default jobs/models paths belong to the owned profile.

Sdist: 534037 bytes / SHA256 `755c0f147dbb3d2eaa915471f591bd92c42b07fe9335841ef98d3edd631eac81`. Wheel: 435567 bytes / SHA256 `153237d7023b13f3b1372cc93feba9b20f9be52916e2a74709e9fdb78fbdb6a8`. All 11 selected sdist members, six wheel runtime members and six installed runtime files match the frozen source hashes. Python requirement stays `>=3.9`. The wheel was built from the extracted sdist, with cached task-local tools and no dependency installation or download.

`final-check.json` binds all 23 selected source files to clean final Git objects, engine SHA256 `9365c47bdc74bf5fc7496ffca62600861367fd968530664dc58f6710ca00037d`, and test SHA256 `0d93b9eec719a73cc30a36332ef0758af767c604f6518e7f1c945cdb52a44607`. AST checks show only the two renderer bodies changed in runtime code; the child shutdown helper, selected original encoder/mask/audio calls, public arguments/defaults, removal blocks/guards and both original removal-activation sites remain unchanged. Reviewed shared-tooling bytes also match. `retained-acceptance-check.json` verifies all 12 indexed logs, all six package phase exit codes, package/installed selected bytes, the exact RED test snapshot hash and absence of an active runtime lock. No product execution was repeated after resume.

The existing prepared read-only interpreters/tools and reviewed canonical verification helper were used; no new model/download/install of dependencies/shared environment edit. Fix runtime stays under the assigned `runtime/task1632/runs`, with unique `fix1-*` owned run names. Compact fix evidence is `task1632-fix1-evidence`, separate from all prior evidence.

The original pinned fixture plugin remains declared but these scoped resource cases require no new inference/model. The original listening adapter is reused unchanged; package/listening execution uses the already authorized loopback escalation. No shared helper edit or guard bypass. Offline backend cache-warning polish remains deferred; the existing task-local backend is reused.

## Commands

Paths are absolute in the retained launch logs. Here `controller` is `/home/tahv0/src/OpenScrub/docs/superpowers/plans/upstream-delivery/execution/tooling/verify.py`, `evidence` is `/home/tahv0/src/OpenScrub/.superpowers/sdd/README/task1632-fix1-evidence`, and `source` is `/home/tahv0/.codex/worktrees/c832/OpenScrub`. Each run retains the exact hashes/config it used, including deliberately changing development revisions.

```sh
python3 "$controller" --config "$evidence/development.json" --run-id fix1-red run -- -m pytest "$source/tests/test_render_resources.py" -k 'stderr_close or stdin_close' -q
python3 "$controller" --config "$evidence/development.json" --run-id fix1-primary-green run -- -m pytest "$source/tests/test_render_resources.py" -k stderr_close -q
python3 "$controller" --config "$evidence/development.json" --run-id fix1-covering-green run -- -m pytest "$source/tests/test_render_resources.py" -k 'stderr_close or stdin_close' -q
python3 "$controller" --config "$evidence/development.json" --run-id fix1-focused312 run -- -m pytest "$source/tests/test_render_resources.py" "$source/tests/test_hdr_decoder_cleanup.py" "$source/test_openscrub.py" -k 'render or hdr or codec' -q -s
python3 "$controller" --config "$evidence/floor.json" --run-id fix1-focused39 run -- -m pytest "$source/tests/test_render_resources.py" "$source/tests/test_hdr_decoder_cleanup.py" "$source/test_openscrub.py" -k 'render or hdr or codec' -q -s
python3 "$controller" --config "$evidence/package.json" --run-id fix1-package package
```

Complete outputs and each run's exact preflight/runtime config are under `task1632-fix1-evidence/runs/<run>/logs` and its parent directory; top-level `*-launch.log` files retain exact command arrays, outputs and exit records. `run-index.json` records log sizes/hashes. `covering-tests-red.py` retains the original failing-test bytes. `frozen.json`, `floor.json` and `package.json` retain final expected source/import/environment inventories. The earlier main-task evidence is untouched. Compact evidence excludes media, source exports, installed trees and prepared environments.

Self-review checked the final two-file diff, exact close-error branches, local-primary initialization/capture, continued primary identity and caller isolation, unchanged helper/deletion boundaries, actual healthy unbounded waits and exceptional bounded waits, retained diagnostics and assertions before harness cleanup. Final native HEAD is `70ec464ca70b5e49751d778890f56029dced0b8a` and `git status --short` is empty. The interrupted work was report/evidence finalization; the 64-case runs and package acceptance had already completed and were reused exactly.

## Limits

Only the dispatched two findings and directly affected controls are changed. No new full-suite, browser, geometry, performance, native-interruption, Windows or GPU claim is made. Healthy finalization has no added timeout; bounded exceptional waits do not interrupt blocked native calls. Prior-video/report preservation remains P16C-P work. All previous failure/evidence identities are retained; independent scoped re-review remains pending.
