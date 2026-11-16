# Keep review saves attached to their job and edit snapshot

A rejected or delayed save could clear newer edits, render after failure, or use a newly selected job ID. Both save buttons now capture their job/view and submitted enabled, manual, box, time and audio values before requests. They require a successful acknowledgement and clear only unchanged submitted edits. Newer drafts remain pending; an acknowledged save followed by render failure does not append its manual regions again on retry.

Pending choices are separate from loaded display values. Explicit choices submit once, including same-value actions; untouched rows are omitted. Job switches retain pending work, while revisits refresh clean server data, including audio spans even when another kind of edit is pending. Clean inactive data is released. Drafts live only in the current page and do not survive browser reload or close.

Validation:

- Original implementation: 172 tests, 18 Chromium scenarios, full build, evaluated JavaScript and package-byte checks passed. A real HTTP save and x264 render verified submitted fields and output pixels.
- Final audio-ownership follow-up: 62 focused JavaScript tests and 12 browser scenarios passed, with rebuilt wheel/sdist and matching source bytes. It covers fresh audio alongside unrelated drafts, dirty audio, and undo during an unacknowledged audio save.
- Chromium/Linux was exercised; Python 3.9 grammar was checked using the Python 3.12 runtime. Other browser/OS runtimes were not tested.

Server transaction coordination and lost-save-acknowledgement manual IDs remain separate work. The latter is still needed to make an unacknowledged manual addition safe to retry. P06A/P06D independently address the known server report-write and render-roundtrip defects.

Local branch: `pr/review-save-snapshots`. Base: `e21ebdf6e3ee46e6c65050dc956a9a3459152269`. Commits: `786990d9102d41c0ec698d6f31fe798de66a049a`, `92124753736e287ac800af91f0ac96f3e96c01be`. No publication.

Local readiness note: align CONTRIBUTING's root-only test command with default discovery before submission. The separate editor live-resize observation remains a P16 reproduction gate.
