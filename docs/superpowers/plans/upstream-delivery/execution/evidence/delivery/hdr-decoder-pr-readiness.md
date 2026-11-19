# HDR decoder cleanup: PR readiness

Candidate: pr/hdr-decoder-cleanup at ded411cbec308333d1416ae3d58b4f6e918d7849.

On 2026-11-19 at 09:11:26 UTC, the [upstream main API](https://api.github.com/repos/austinmabry/OpenScrub/branches/main) still identified 5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f. Refresh that observation before submission. The candidate code is unchanged from its [independent source approval](task-109-review.md); the current readiness evidence and PR description also pass independent specification/quality review.

## What and why

During ordinary HDR cancellation or encoder-write failure, the children were already reaped, but the decoder pipe could remain open while a retained traceback kept its owner alive. The two added production lines close decoder stdout in the existing partial-cleanup path. The tests retain the real exception and process owners through the pipe/reaping assertions and preserve a successful synthetic HDR render.

The shared prerequisite e21ebdf6 changes only two added/two deleted test lines in the existing tracking handoff test. It requires post-occlusion samples and keeps geometric rejection. It has its own [test-only description](../../pr-drafts/tracker-handoff-regression.md). The HDR-owned e21-to-ded diff touches four files; the pinned-main-to-ded comparison includes both separate commits and five files. The prerequisite remains visibly separate for the submission decision.

## Current checks

| Check at unchanged ded411cb | Result |
| --- | --- |
| Python 3.12.16: three HDR cases plus shared handoff test | Four passed, zero skips |
| Actual Python 3.9.25: same cases | Four passed, zero skips |
| Native loaded-engine/source/prerequisite identities | Matched |
| Current tracked source compared with Git and prior tested manifest | All 114 files matched |
| Retained sdist archive | 26 source-mapped members matched; one generated PKG-INFO |
| Retained wheel archive | 13 source-mapped members matched; four generated metadata/record entries |
| Candidate and other preserved refs | Unchanged |

The real tests cover frame-zero cancellation, a real encoder broken pipe and successful three-frame 64×64 ten-bit PQ/BT.2020 output. Six pairs of logged child observations show waits and closed pipes; reaping assertions precede harness cleanup. The source/pre-encoder byte equality and equality of baseline/candidate decoded lossy output are separate observations. Lossy output differs from raw source.

The existing archive identities matched the original recorded builds:

- Sdist SHA-256: a50a1bf62929f25d83edb1aebfbefc133e637307d1b8141cda3fede3ae1995de.
- Wheel SHA-256: 071e640fcf897d698a54ef39f6e889355980b047755fc1262b8e71d51a1937ce.

Historical full 137, 11 focused cases on each interpreter, build and installed CLI/web startup remain evidence on the same candidate in the [original report](task-109-report.md). Those checks were not rerun for this unchanged-source refresh; the new archive audit is not a new installed-startup claim.

## Reproduce and deliver

With project dependencies, FFmpeg/ffprobe with libx265 and the POSIX child-observation facilities available:

    python -m pytest tests/test_hdr_decoder_cleanup.py test_openscrub.py::test_track_person_size_jump_handoff -q

Run on both supported interpreter environments. These observations require real children; missing prerequisites can skip the optional controls, which does not establish readiness.

This is the first privately prepared submission candidate. Keep the next candidate private while Austin reviews it; wait for initial feedback or an invitation before adding another. Publication and the shared prerequisite's submission disposition remain separate. No remaining optional feature or final combined application gate is needed to prepare this independent contribution.

The evidence covers Linux CPU and POSIX/libx265. It establishes no Windows/GPU encoder, arbitrary native-interruption, cancellation-speed, permanent-leak or broader lifecycle/geometry/output-policy guarantee. Defaults and output handling remain preserved.

[PR description](../../pr-drafts/hdr-decoder-cleanup.md).
