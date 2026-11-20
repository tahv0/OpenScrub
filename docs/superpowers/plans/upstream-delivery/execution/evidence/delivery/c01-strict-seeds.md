# Strict tracker seeds in the clean OpenScrub build

The reviewed local staging branch `integration/upstream-focused-strict-seeds` is at `514159d358f4beb4ef661c71b1dc2cdad56c0ec8`. It composes the [accepted tracker adapter](task-1002-final-acceptance.md) through `6fde5ad` on the [exact-frame backend checkpoint](c01-exact-backend.md) at `7e19159`. The clean application reviewed before this staging sequence is `b4fc209`.

An explicit Track seed now initializes person, Vit and NCC tracking from the inspected integer frame and verified pixels. The route retains the selected file and its containing job through decode, model resolution and publication. It rejects source, operation or report-input changes before they can append a track. The append uses the current report publisher and preserves unrelated edits, including Keep choices and audio. Calls without a seed continue through the existing Track path. The current browser still sends the legacy request.

Independent review caught cancellation after a successful indexed prime, source recovery during model loading, and malformed or missing latest reports during admission. Seven cases reproduced these review findings before the fixes. The scoped follow-up approved the final commit. The source check after model resolution adds one source stat without another timeline traversal.

| Verification | Result |
| --- | --- |
| Python 3.12.16 and Python 3.9.25 | 295 checks passed on each. This selection includes strict and legacy trackers, exact sampling and recovery, held cancellation, report transactions, file owners, and real HTTP tests. |
| Real media | Regenerated marked 24 fps and 5 fps files and a VFR input passed through the production normalizer. The checks compared inspected pixels and timing against sequential decoding and FFprobe. |
| Offline package and installed HTTP | Built the sdist and built the wheel from the extracted sdist. Compared 97 sdist files and 20 wheel files to Git and verified 23 hashed wheel RECORD entries and their installed bytes. The installed tests checked exact frame 9 at 1.8 seconds, capture release, coordinate offsets, preserved report fields, and legacy tracking. |
| Shipped JavaScript | 58 Node checks passed for thumbnail scheduling, review filters and polling. Six shipped page assignments were also checked byte-for-byte against `7e19159`. |

The fixture and test logs are in `.superpowers/sdd/README/runtime/c01-strict-seeds/`. The restored environments used OpenCV 4.14.0 and FFmpeg `N-129130-gcd39c36377`. The regenerated fixtures have new hashes. The installed route exercises actual capture and tracking initialization with a deterministic model boundary. Combined release, model quality, long-video performance and native Windows remain separate gates.

The next local assembly stage is [vault/source continuity](vault-source-continuity-acceptance.md), followed by thumbnail coherence and validation reuse. The ordinary editor and Track switch follows on the combined stack.
