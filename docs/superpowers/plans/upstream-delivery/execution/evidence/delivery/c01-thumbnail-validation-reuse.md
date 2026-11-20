# Thumbnail validation reuse in the clean OpenScrub build

The reviewed local staging branch `integration/upstream-focused-thumbnail-reuse` is at `d31939a127385b6488f1690696e1147dab03c81f`, directly on [thumbnail coherence](c01-thumbnail-coherence.md) `681d82c`. It composes the accepted [validation-reuse changes](p08b-validation-reuse-acceptance.md) through `9bfb9d9`.

Repeated metadata and cold-thumbnail requests still parse a fresh report. On eligible POSIX filesystems, they can reuse validation of the exact current report and source generation. This avoids rescanning every row and timeline offset when the same document has already been checked.

The composed path keeps the source reservation alive while checking the proof and accepting the request. Publication by the source's containing job or a recovery transition invalidates the proof. A reused proof cannot create a replacement generation. The full path still handles first discovery, changed or weak file stamps, and platforms outside the POSIX assumption. Pre-generation validates its private snapshot and remains bound to its selected generation. Warm JPEG requests retain their parse-free path.

## Verification

| Scope on `d31939a` | Result |
| --- | --- |
| Python 3.12.16 | 829 selected checks passed, including real Flask and Chromium, thumbnail and report owners, exact and strict tracking, vault, and browser polling. |
| Python 3.9.25 | 816 selected checks passed, including the new validation and source-owner interleavings. |
| Offline sdist and installed wheel | Matched 110 Git-backed sdist members, 21 Git-backed wheel members and 24 hashed wheel RECORD entries. |
| Installed HTTP | Repeat metadata and the first crop reused validation. Foreign-source recovery refused the stale validator, and publication forced fresh validation before serving the next generation. Current conditional and fresh-image controls returned 304 and 200. |

Independent source review approved the composed proof and selection guards. Regressions cover foreign publication as proof is selected, recovery before a cold fill and reuse after a fresh generation is established. The fixture-only change in the thumbnail checkpoint also ran in this combined selection.

Exact commands, package receipts and the installed probe are in `.superpowers/sdd/README/runtime/c01-thumbnail-validation-reuse/`. This checkpoint verifies correctness and validation calls on the tested Linux/WSL filesystem. The published standalone timing measurements keep their original source attribution. The full release gate still needs its complete dependency environment, current upstream baseline and representative scale workloads.

This closes the thumbnail assembly stages. The next stage is the ordinary exact editor and Track transition on the current review scheduler.
