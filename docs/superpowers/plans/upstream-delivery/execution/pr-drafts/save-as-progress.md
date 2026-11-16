# Add streaming Save As with byte progress for exports

After rendering, users can choose a destination for the redacted video or audit
report and see accepted bytes, elapsed time and an approximate remaining time.
This builds on Tuomas Aho's Save As implementation in `2900930f`; its static
“Saving…” feedback was the usability trigger. Upstream's streaming downloads and
actual-container filename behavior are preserved through shared filename metadata.

Each destination write completes before its bytes count toward progress. The
rolling ETA starts after three seconds, disappears during a five-second stall,
and gives way to Finalizing until close succeeds. Unknown/encoded response sizes
remain indeterminate. Errors retain retry/download guidance, and picker cancellation
starts no network request. Progress remains bound to the clicked job through
polling and job switches.

Save As requires a supporting browser on HTTPS/localhost. Direct Download links
remain available and report only that the browser download started. This is a
feedback/destination feature, not a transfer-speed claim.

Validation:

- 24 new behavior cases pass, including actual MP4/MKV/audit attachment names and
  HTTP lengths, delayed writes/close, cancellation, captured job targets,
  invalid/encoded/mismatched totals, failures and announcement timing.
- Required root + feature suite and default discovery: 157 passed; the same
  pre-existing `test_track_person_size_jump_handoff` log assertion fails. No
  skip, xfail or tracker/test fix is included. OpenCV-4-compatible baseline
  environment was used; current unconstrained OpenCV 5 compatibility is separate.
- Full sdist→wheel build and evaluated combined embedded-JS syntax pass. Focused
  tests ship in the sdist; contributor instructions collect root and `tests/`.
- Chromium rendered QA at 1365×950 and 390×844: cancellation, network/write/close
  errors, retries, polling/switching and direct fallback pass. A throttled 256 MiB
  real HTTP→OPFS export saved exactly 268,435,456 bytes, held one write at a time,
  showed waiting/finalizing feedback and waited for close before Saved. `.blob()`
  was blocked; maximum fetched-ahead data was one 2 MiB chunk. Sampled JS heap plus
  backing storage peaked at ~84.8 MiB; total browser RSS was not measured.

The picker boundary was controlled in headless Chromium and wrote to real OPFS;
OS-native Save As dialogs, Windows permissions, other browser engines and multi-GB
files were not exercised. No runtime dependency, release/version or default
redaction/review change is included.

Local candidate commit: `ca0f2ce7458347afd2e6156a97df580b6623767a`.
