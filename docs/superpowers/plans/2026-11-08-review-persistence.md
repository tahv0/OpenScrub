# Review persistence and Cheroot response-race repair

Reported behavior: Save review edits followed by page refresh loses decisions;
Train & rescan does nothing. Docker logs also report a response larger than its
Content-Length. Do not assert that the two symptoms have a single cause or that
unsent choices from an already-refreshed old client can be reconstructed.

Reproductions against b62523e:
- A still-positive corner fails with 409, then 50 findings are marked Not a
  plate. Save returns false during the corner flush before POSTing any choices;
  Train exits through the same guard. The overall save status did not exist.
- In-place growth of a live preview/thumbnail after send_file chooses its
  Content-Length causes the exact Cheroot error. Test through real Cheroot.
- A failed decision request has no same-tab reload recovery.

Repair boundaries:
- Save independent decisions before flushing pending corners. Partial saves
  explicitly say decisions saved, corners NOT saved, training/rendering NOT
  started. No bypass of failed geometry for training or rendering.
- Save/failed/busy status is visible at both ends of review, including paused
  jobs. Source-bound sessionStorage drafts preserve only review decisions and
  completed corner gestures (no image pixels, OCR text, or audio/manual edits).
- Restore only when source and ordered frame/coordinate identities match;
  mismatched drafts are retained for download, never applied to another scan.
  A server write with a stale identity is rejected. No automatic posting of
  recovered corners; show the outline and require explicit retry.
- Purge these browser drafts on detected vault lock and after job deletion.
  Storage denial must produce a warning, never a claim of a durable backup.
- Publish JPEGs by atomic replacement; serve mutable JPEG/report bytes from an
  immutable in-memory snapshot. Preserve HEAD/Range support and real length.
  Do not disable Cheroot's length checking or buffer multi-GB video streams.

Verification:
- New tests in test_save_persistence.py reproduce the original failures before
  repair. Cover both viewports, actual Save and Train clicks, refresh, failed
  positive corners, lost receipts, changed identity, late edits, rehydration,
  atomic publication and HEAD/Range behavior. CI uses actual Cheroot HTTP.
- Restricted local Chromium uses an explicit in-process Flask/storage stand-in;
  that is not represented as production browser networking. Python HTTP tests
  still use actual Cheroot locally.
- Rerun prior editor, cache, stop/review, learning and release regressions and
  audit the full suite without suppressing the known baseline OCR failures.

Recovery: inspect current report.json, plate_annotations/annotations.jsonl and
learning pass before-report snapshots without modifying them. Existing on-disk
samples are not deleted. New browser recovery cannot recreate a draft that was
never persisted by an earlier version before the page was refreshed.
