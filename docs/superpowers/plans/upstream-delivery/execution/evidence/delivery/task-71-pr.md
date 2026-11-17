# Bind review saves to the initiating job view and edit snapshot

Local PR draft only. Branch `pr/review-save-snapshots`; head `92124753736e287ac800af91f0ac96f3e96c01be` (initial implementation `786990d9102d41c0ec698d6f31fe798de66a049a` plus separate reviewed fix); base `e21ebdf6e3ee46e6c65050dc956a9a3459152269`. No publication.

A save that waited for HTTP/allowlist responses could use a newly selected job's ID, clear newer edits, or render after a rejected save. The box-editor button also removed the editor after failure. Both buttons now capture their job/view and cloned submitted edits, check HTTP/JSON/body success, and reconcile only acknowledged unchanged edits.409 / 423 / 500/network/JSON failures retain actionable drafts; duplicate in-flight submissions are guarded. Newer edits stay visible and prevent a render from appearing to include unsubmitted work.

Pending enabled choices are distinct from loaded display state: untouched rows are omitted, while explicit choices (including choices equal to the loaded value) submit once. A monotonic `VIEW_GEN` distinguishes A→B→A. Page-memory drafts restore on revisit; clean inactive display data is released, deleted jobs are removed, and narrow editor/load/playback publication guards keep responses attached to their view. Clean audio is reloaded independently of unrelated pending drafts; dirty audio and in-flight or failed-save toggle-back intent remain pending for deliberate whole-list retry. Allowlist suggestions retain their existing interaction.

An acknowledged save followed by render failure no longer re-appends committed manual additions on retry. **Lost save acknowledgements still require P07b's additive stable manual IDs and server replay contract; no IDs/schema/server deduplication are included here.** Legacy API payload shape and server behavior remain unchanged. P06A report-write corruption and P06D disabled-row/audio metadata loss during render are independent known baseline defects, not fixed or hidden in this branch.

Validation:

- Initial reviewed full discovery: 172 passed (134 baseline + 38 actual evaluated embedded-JavaScript regressions), 58.76s. Latest narrow fix: 62 save-state regressions pass, including 24 additional fresh/dirty/in-flight audio cases; the broad suite was not repeated for this fix as dispatched.
- Initial 18 isolated Chromium scenarios on full UI, including both buttons and409 / 423 / 500/network/invalid-JSON/body errors, deferred newer edits, double submission, A→B→A, allowlist await and render-failure retry; no page exceptions.
- Real HTTP save + real x264 engine render on synthetic footage. Pre-render report verifies enabled/manual/box/time/audio edits. Downloaded output masks the submitted textured manual ROI (mean/std 0/0), preserving an unrelated clear region.
- Latest fix: 12 focused Chromium revisit/audio scenarios pass with no page exceptions; injected 423/network errors only.
- Rebuilt wheel/sdist, exact final module/test bytes in artifacts, Python3.9 grammar checks, evaluated JavaScript parse and `git diff --check` pass. Minimal documented root+tests discovery and sdist test inclusion added; no dependencies/CI added.

Browser plugin unavailable, so authorized isolated Playwright fallback was used. Chromium/Linux only. Drafts survive job switches within the page, not browser reload/close. Live mobile-resize overlay scaling was observed; regression status is unverified, with exact steps/screenshots retained for P16 and no resize change included. Raw commands/evidence and detailed limits: [task-71-report.md](task-71-report.md); task artifacts `/tmp/openscrub-task71/`.
