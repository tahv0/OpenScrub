# Add streaming Save As progress for exports

After a render, users can choose where to save the redacted video or audit report and see how far the save has progressed.

The progress bar counts bytes after each destination write completes. When the response includes a usable total, the UI shows written and total bytes, transfer speed and an approximate time remaining. On a stall it shows Waiting. When all bytes have been written it shows Finalizing, then Saved once the file closes. Canceling the picker starts no transfer. Direct Download is available, including in browsers without the file picker.

The video and report controls align side by side when there is room. On narrow screens each download link sits below its Save As button, with the review tools on a separate row.

## Validation

- Full suite on Python 3.12: 161 passed with no skips, including the three HDR cleanup regressions. The 24 Save As tests also passed on Python 3.9.
- The export tests check accepted writes, stalls, cancel and failure behavior, job switches, and completion after close. The Chromium check reproduced a split download label at 1120 px and uneven link placement at 390 px. It passed at 1120, 390 and 320 px after the layout fix. A synthetic 18.9 MB save exercised progress, finalization and completion with a controlled file picker. The direct-download fallback passed.
- The offline sdist and wheel built successfully. The installed web entry point served both export routes and shut down cleanly. Tests and contributor instructions are included in the sdist.
- An earlier 256 MiB Chromium transfer exercised the same streaming logic with real local HTTP and an origin-private file. The application kept one destination write in flight.

Submitted as [Save As PR #24](https://github.com/austinmabry/OpenScrub/pull/24) from 0da66d1. [Verification and source attribution](../evidence/delivery/save-as-pr-readiness.md).
