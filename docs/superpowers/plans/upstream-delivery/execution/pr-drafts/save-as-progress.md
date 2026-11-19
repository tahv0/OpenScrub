# Add streaming Save As with byte progress for exports

After rendering, users can choose a destination for a redacted video or audit report and see progress while it saves. This builds on Tuomas Aho's Save As work in `2900930f`, where the control showed a static “Saving…” message during a transfer. Existing streaming download routes and actual-container filename behavior are preserved.

Progress counts bytes only after the destination accepts each write, rather than bytes merely fetched. A trustworthy response length gives a total and approximate remaining time; absent, encoded or invalid lengths remain indeterminate. During a stall the UI shows waiting and removes stale estimates. At end of stream it shows Finalizing, and reports Saved only after the destination closes successfully. Errors provide retry or direct-download guidance; cancelling the picker starts no export request. Progress stays attached to the chosen job through polling and job switches.

Save As requires a supporting browser on HTTPS or localhost. Direct Download remains available and reports that the browser download started, without claiming the local save is complete. This change adds feedback and destination selection; it does not claim faster transfers or change redaction behavior.

Validation:

- Current focused behavior tests: 24 passed on Python 3.12.16 and 24 passed on actual Python 3.9.25. They cover attachment names and lengths, accepted writes, known and unknown totals, cancellation, waiting, finalizing, failures and job switching.
- Earlier checks at this same candidate: 24 focused passes; required combined suite and default discovery each had 157 passed and one failure in the unchanged `test_track_person_size_jump_handoff` tracker-log assertion. Its separate test correction is already in HDR #23 and is not included here. Evaluated embedded JavaScript syntax and the sdist-to-wheel build passed in that earlier run.
- Earlier headless Chromium testing used real HTTP to an OPFS writable with a controlled picker. A 256 MiB transfer saved exactly 268,435,456 bytes, had one write in flight and at most 2 MiB read by the application beyond what the destination had accepted, showed waiting and finalizing, and waited for close before Saved. Sampled JavaScript heap plus backing storage peaked at about 84.8 MiB; total browser RSS was not measured.

OS-native picker interaction, Windows permissions, other browser engines, multi-GB exports, physical disk durability and OpenCV 5 compatibility remain unverified. No new runtime dependency or version change is included.

Private delivery status: reviewed ca0f2ce on Austin5d3a15a; [current readiness](../evidence/delivery/save-as-pr-readiness.md). Wait for Austin’s feedback or invitation on HDR#23 before another submission.
