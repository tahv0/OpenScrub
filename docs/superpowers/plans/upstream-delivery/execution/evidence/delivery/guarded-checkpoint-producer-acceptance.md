# Guarded producer for paused scan reports

`pr/guarded-checkpoint-producer` at `ad87ca0e2a677faafe54d3d9c32d4421f190ad5c` follows the [verified CFR decoder](checkpoint-cfr-decoder-acceptance.md). It provides a synchronous engine operation for a caller with exclusive source ownership and the report publication lock.

| What | Why | When to deliver |
| --- | --- | --- |
| Run supported scanning, publish an atomic paused report, and resume from a verified overlap with an exact completed-frame count. | Long scans need a reusable prefix and a verified suffix after a restart. | As the first actual producer after the verified decoder, before web or CLI wiring. |
| Bind source bytes and effective settings. Reuse one source hash per attempt. Revalidate the latest report and preserve edits before publication. | A resumed scan needs the same source and settings, and user choices can change while the engine works. | Test held publication, late edits and cancellations on synthetic encoded clips alongside ordinary scan controls. |

The frozen source passed 248 selected checks on each of Python 3.12 and 3.9, including loopback lifecycle checks. The installed wheels passed 158 checks on each version. A separate-process test paused at frame 9, saved review edits, and finished all 24 frames in a new process with the edited raw data preserved. The supported scan is native progressive 8-bit H.264 CFR with QR detection or manual-only categories and no scrolling, backtracking, normalization, setup tracks or audio analysis. A raw FFmpeg pipe stall can still delay cancellation. The app owner, common detector settings, reliable live cancellation, and user controls remain subsequent work.
