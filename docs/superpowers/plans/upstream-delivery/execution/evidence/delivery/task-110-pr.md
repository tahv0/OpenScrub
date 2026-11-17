# Stop ordinary manual tracking when cancellation is observed

Base: `12919c96c6f7558136b50d7b4d85e5e6b62f1971`
Head: `2004b22002b8317c26ea508ff8187acbcd0cfab2`
Branch: `pr/manual-tracker-cancellation`

Ordinary NCC tracking continued decoding, matching and appending held coverage after cancellation. Add cooperative checks at entry, helper/model handoffs, each NCC sample and held append, and successful generic returns; propagate the person helper's existing `PipelineCancelled` instead of falling back. Precancellation intentionally precedes unusable-input early returns and avoids capture creation.

Existing capture-finally, matching defaults, output arrays, source/operation lifetime and web publication ownership remain intact. In the synthetic completed-match schedule, subsequent work changes from13 grabs/19 reads/41 matches to0 grabs/0 reads/2 matches; the current constant scale sweep may finish. No native-interrupt or latency bound is claimed.

Validation: owning RED16 failures before implementation; relevant regressions158 passed; complete Python3.12 suite419 passed on unchanged final product; final focused25 passed; final actual Python3.9 owning168 passed; offline sdist→wheel exact source/tests/defaults and installed CLI/real HTTP web smoke passed. Final test portability/native-retry-count corrections were verified after the full run; the full suite uses the same final engine bytes. Actual Flask tracker/cancel/delete tests prove unchanged cancelled status/report, DELETE409 while work/capture cleanup owns source, capture closed before lease release, then DELETE200 and zero owners/work/threads. Full15-sample steady/loss arrays remain exactly equal, including cb=None equivalence.

Details, source/test identities, all harness corrections, commands and limits: [task-110-report.md](task-110-report.md). Local commit only; no PR has been published.
