# Close the HDR decoder pipe during existing partial cleanup

Base: `e21ebdf6e3ee46e6c65050dc956a9a3459152269`  
Head: `ded411cbec308333d1416ae3d58b4f6e918d7849`  
Branch: `pr/hdr-decoder-cleanup`. Draft description only; not published.

Ordinary HDR cancellation or a real encoder-write error already reaps both children, but decoder stdout stays open while the caller retains the raised exception traceback. Close that owned pipe alongside encoder stdin in the existing partial-cleanup path. The production change is two lines; existing primary errors, success, child commands, defaults and output handling are preserved.

Add actual `run_render` → `render_hdr` regressions using only synthetic three-frame 64×64 PQ/BT.2020 ten-bit media and real FFmpeg children. Keep the raised exception/traceback and diagnostic process owners alive while asserting both pipes closed and both children waited/reaped. Inject encoder failure by killing only the test's actual encoder child, so its first write raises a real `BrokenPipeError`. Harness cleanup always runs after assertions. Ship the regressions in the sdist and document full test discovery.

Validation:

- Owning RED: cancellation/write cases each fail only on open decoder stdout; success passes. GREEN: 3 passed.
- Full discovered suite: 137 passed. Relevant render/HDR/codec cases: 11 passed on prepared Python 3.12 and 11 passed on actual Python 3.9, with native import paths/SHA asserted.
- Tiny PQ success: exact source/pre-encoder bytes; before/after decoded output bytes and PQ/BT.2020 tags equal. Lossy decoded output is distinct from raw source.
- Offline sdist→wheel build, exact packaged runtime/source/test checks, clean installed CLI/web startup and shutdown passed. All 114 frozen source hashes match committed bytes; native worktree clean.

Broader P16C exception/geometry/output-publication handling, final encoder-wait failure and temporary stderr ownership are separate work. No cancellation-speed, native-interruption, permanent-leak, Windows or GPU claim. Evidence, full commands, failure states, source provenance and limits: [task-109-report.md](task-109-report.md); artifacts `/tmp/openscrub-task109`.
