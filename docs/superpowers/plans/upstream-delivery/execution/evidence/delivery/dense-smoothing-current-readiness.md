# Dense-smoothing readiness on Austin v1.0.97

The private topic `pr/dense-smoothing-upstream-1097` is at `66e7c105f1b1dfaf33fed1375fc2695cd2c47520`, directly on Austin main `50c5a9e03564983ea0bc2a7841824b1fffaf35e0`. The original topic `pr/dense-smoothing-prefix` at `f19be5fe` is preserved.

## What and why

For long videos with late dense detections, advance sequentially but retrieve pixel data only inside the existing gray-cache spans. A capture owner releases the decoder even after failed opening, an exception, or cancellation. Frame selection, detection fields and cancellation checkpoints remain intact.

The refreshed change touches four files. The smoother, owning tests and benchmark are identical to the accepted implementation. The engine's differences from the old accepted topic are Austin's version update and separate HDR pipe cleanup. Austin's test discovery, version and sdist configuration remain in place. The benchmark driver is available in the topic checkout, outside the shipped package.

## Current verification

- All 157 native tests passed on Python 3.12.16 with no skips, including 20 smoothing cases and all three HDR cleanup cases. All 20 smoothing cases also passed on actual Python 3.9.25.
- The lossless marked-video regression checks every needed frame marker and every detection field against the baseline. The installed wheel reproduced the same check with a real 130-frame FFV1 fixture. It converted markers 16–60, made 45 reads and 16 grabs, released the capture once, and matched the baseline's complete 10 detection records.
- Fresh offline sdist, wheel built from its extracted source and isolated installation passed. The audit matched 27 Git-backed sdist members, 13 Git-backed wheel members including licenses, 16 hashed RECORD entries and its self-entry. Installed CLI and web help passed. The smoothing check ran against the installed engine. Tests and contributor instructions are distribution source material.
- Independent source and evidence review passed. The original 174 refs and checkout status were preserved, with only the new private topic added before documentation.

## Historical timing and delivery

The earlier study compared `e21ebdf6` and `f19be5fe` on two generated 610-second 256×144 H.264 clips. GOP 30 went from 5.531 to 1.797 seconds and single keyframe went from 5.480 to 1.387 seconds. Both medians use five alternating measured pairs after three warm-up pairs per clip. Each comparison used 18,001 sequential advances and preserved all 129 needed markers and 38 detection records. Native prefix decode still occurs. These synthetic shared-machine results describe their original environment. [Original timing and correctness evidence](../dense-smoothing/task-111-report.md).

Frame identities and detection records are freshly verified at `66e7c10`. The [private PR draft](../../pr-drafts/dense-smoothing-prefix.md) contains the fixture generator and benchmark command so the timing can be reproduced from a source checkout. Publication is a separate delivery step.
