# Add streaming Save As progress for exports

After rendering, users can choose a destination for a redacted video or audit report and see progress while it saves. This builds on Tuomas Aho's Save As work in `2900930f`, where the control showed a static “Saving…” message during a transfer. Existing streaming download routes and actual-container filename behavior are preserved.

Progress counts bytes after the destination accepts each write. A valid unencoded response length gives a total and approximate remaining time; absent, encoded or invalid lengths remain indeterminate. A stall shows waiting and removes stale estimates. At end of stream the UI shows Finalizing, and reports Saved only after the destination closes successfully. Errors offer retry or direct-download guidance; cancelling the picker starts no export request. Progress stays attached to its job across polling and job switches.

Save As requires a supporting browser on HTTPS or localhost. Direct Download remains available and reports that the browser download started. This change adds feedback and destination selection without changing redaction behavior.

Validation against v1.0.97:

- Python 3.12.16/OpenCV 4 full discovery: 161 passed, including all three HDR cleanup regressions, with no skips.
- Actual Python 3.9.25: all 24 Save As cases passed. Evaluated joined embedded JavaScript passed Node syntax validation.
- Fresh offline sdist-to-wheel build and isolated installation: version 1.0.97, Python >=3.9 metadata, archive contents and RECORD verified. Installed CLI help, web startup and shutdown, and video/report download routes passed with a synthetic job.
- Earlier headless Chromium testing at the original equivalent Save As source used real loopback HTTP to an OPFS writable with a controlled picker. A 256 MiB transfer saved exactly 268,435,456 bytes, had one write in flight and at most 2 MiB delivered to the app reader beyond completed destination writes, showed waiting and finalizing, and waited for close before Saved. Sampled JavaScript heap plus backing storage peaked at about 84.8 MiB; total browser RSS was not measured.

Native picker interaction, Windows permissions, other browser engines, multi-GB exports, physical disk durability and OpenCV 5 compatibility remain unverified. Python 3.9 execution covered the focused suite, not the full application or installed package.

Private delivery status: specification, quality and description approved at 9d494e6510028bbb5db08756ab183ba579a12cc7 on Austin 50c5a9e/v1.0.97. [Current readiness and source attribution](../evidence/delivery/save-as-pr-readiness.md). No second push/PR, C01 or working-version adoption has occurred.
