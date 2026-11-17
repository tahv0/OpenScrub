## Task 109: close decoder stdout on existing HDR partial-cleanup paths

### Global constraints

Preserve Austin defaults, Python>=3.9, ordinary render/cancellation/error semantics, geometry and encoder behavior. No training/workbench/sections, dependency/version changes, native-call deadline, broad renderer rewrite or new root helper. Tests under `tests/`; synthetic media and existing tools only. No original-checkout/user-data changes, external publication or subagents.

### What, why and when

On ordinary HDR cancellation and real encoder-write failure, children are reaped but decoder stdout remains open while a caller retains the exception traceback. The generic donor close makes that owned descriptor deterministic. This is a small separate N09 PR, independent of broader P16C output/exception lifecycle. Read `hdr-decoder-cleanup-baseline-research.md` and its bounded actual-module recipe; do not repeat its entire baseline or import section behavior from `08f432b6160d2fc22e51456020df929de6717e16`.

The supervisor will create `pr/hdr-decoder-cleanup` in the native worktree from exact Austin-plus-test-only `e21ebdf6e3ee46e6c65050dc956a9a3459152269` before dispatch.

1. In existing ordinary `render_hdr.cleanup_partial`, explicitly close owned decoder stdout alongside encoder stdin before completing the existing termination/wait cleanup. Keep the production diff as small as the demonstrated boundary permits. Preserve normal success, raised `PipelineCancelled`/encoder-write error, existing checkpoints, child commands and output paths.
2. Do not broaden this patch to final encoder-wait failure, temporary stderr lifetime, arbitrary compute exceptions, short-read semantics or prior-output atomicity. Those have explicit P16C ownership. Do not claim an unreaped child, permanent leak, arbitrary native interruption or cancellation-speed improvement.
3. Add actual `run_render`→`render_hdr` regressions in `tests/test_hdr_decoder_cleanup.py`: frame-zero cancellation and real first encoder-write failure using only the task's own encoder child. Retain raised exception/traceback and controlled process/pipe references while asserting both owned pipes closed and both children waited/reaped; do not rely on GC. Keep observation effects explicit and give the harness unconditional cleanup after assertions.
4. Use the existing tiny three-frame64×64 PQ/BT.2020 ten-bit fixture and actual FFmpeg. Preserve a successful decode/frame/tag control and before/after output comparison with the same settings. Check source/pre-encoder bytes separately from lossy decoded output; do not call lossy output bit-identical to source. No models/inference or large benchmark is needed.

Observe owning RED→GREEN at the actual boundary, then run relevant render/new checks and the full discovered suite once at stabilized source. Build sdist then wheel, verify source/test packaging and clean installed CLI/web startup; run focused actual cases on the existing Python3.9 interpreter with active-source assertions. Include only necessary branch-local test discovery/contributor metadata, not a CI/build overhaul. Use `/tmp/openscrub-task109` and existing isolated tools. Linux CPU evidence does not certify Windows/GPU/native-call cancellation.

Self-review, commit and write `task-109-report.md` / `task-109-pr.md` in this SDD workspace with exact base/head, source provenance, retained-exception trigger, child/pipe evidence, commands/results, changed files and limits. No publication or nested agents.

Tooling: `/tmp/openscrub-baseline-20261116/env-opencv4.sh`, `/tmp/openscrub-python39-20261117/env.sh`, existing offline build recipes. Native local edits/Git commits may require already-authorized `require_escalated`.
