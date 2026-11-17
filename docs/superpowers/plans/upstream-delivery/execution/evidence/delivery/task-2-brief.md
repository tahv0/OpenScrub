# Task 2: P01 streaming Save As with byte progress

## Global constraints

Preserve upstream defaults, report compatibility, entry points, existing face margins and job/vault lifecycle. New tests go in `tests/`. Every PR runs the existing suite and full build plus its own tests. Research probes are not production regressions. Package a new runtime module in every applicable distribution in the owning PR.


## P01 — streaming Save As

**What:** Add explicit destination selection for redacted video/audit downloads with a progress bar, bytes written out of total, elapsed time and an estimated remaining time when meaningful. Retain direct browser download.

**Why:** The user reports that the donor's Save As works well, but its static “Saving…” label gives no indication of progress on large files. Preserve that working streaming behavior and make its progress visible. Upstream already streams downloads and computes real file extensions; preserve those behaviors too.

**When:** W1, after B01/B02; progress belongs in the first self-contained Save As PR, not a later performance or optional-assistance task. Independent of P04's scan ETA. Austin welcomed Save As in #22; the progress requirement comes from the user's follow-up. Donor: `2900930f`.

**Files / contract:** `openscrub_web.py`, concise README text, `tests/test_export_save_as.py`. Add `export_filenames(job) -> tuple[str, str]` and additive public job metadata; retain `job_download`/`job_report`. Browser `saveExportAs(kind, button)` captures job ID/name/type before awaiting. Do not add a general download framework.

**Progress contract:** Show an accessible progress bar and status such as `Saving video — 1.2 GB / 4.8 GB (25%) · 32 MB/s · about 2 min left`, plus elapsed time. Count bytes after each destination write resolves, not merely when fetched. Treat the count as bytes accepted by the file stream; the final destination is not complete until close succeeds. Use consistent byte units for numerator, denominator and rate.

For ordinary file responses, use the valid response `Content-Length` matching the bytes being written. Do not use an old job size, a compressed transfer length against decoded bytes, or a fabricated total. If no reliable total is available, show bytes written, elapsed time and an indeterminate bar without a percentage/countdown. This is a fallback; normal video/report routes must be tested to provide the correct total.

**Proposed UI timing:** Refresh at most every 250ms, with a lightweight timer keeping elapsed time visible while awaiting data/write completion. Estimate remaining time from a rolling 10-second write-rate window after at least 3 seconds of observations. After 5 seconds without an accepted write, show `Waiting for data or disk…` and hide the stale ETA; do not advance the byte count artificially. After the final chunk show `Finalizing…` until close succeeds, then `Saved`. Direct-download fallback reports `Download started — see browser downloads`; it cannot claim an observed local save or invent in-app byte progress.

- [ ] **E/S:** Compare the donor's naming logic with current routes; share one filename calculation so picker suggestions and HTTP headers agree for MP4/MKV/audit output.
- [ ] **E:** Capture the current static “Saving…” state during a throttled large export, and verify video/report response sizes. Record this as the usability trigger, separate from any throughput claim.
- [ ] **I:** Add tests `test_save_as_uses_actual_output_suffix`, `test_picker_cancel_does_not_fetch` and `test_job_switch_keeps_original_export_target`. Assert the real source extension, no network request after cancellation, and all requests remain bound to the clicked job.
- [ ] **I:** Add delayed-write tests `test_save_progress_counts_completed_writes`, `test_save_progress_unknown_total`, `test_save_progress_waiting_and_finalizing` and `test_save_progress_stays_with_original_job`. Assert monotonic accepted-byte counts, correct known totals, no premature success while close is pending, elapsed/waiting status during a pause, hidden stale ETA and no progress displayed against a different job. Cover zero-byte output, invalid/encoded length, a reliable total mismatch, failed writes and failed close.
- [ ] **I:** Invoke the picker from the user gesture when supported; then fetch the captured route, check response status/body, and stream to the writable destination with backpressure. Await each write before increasing progress, validate a reliable total before finalizing, then await close before success. On failure cancel the reader/abort the writable as applicable, clear timers and retain an actionable failed state. Use existing direct download in unsupported browsers/contexts.
- [ ] **I:** Keep progress state scoped to the captured job/export and preserve it through ordinary UI polling; late callbacks must not overwrite another job's view. Add the accessible bar and byte/time status in the existing export controls without a new UI framework or root helper file. Throttle live announcements separately from visual updates.
- [ ] **V:** Run `python -m pytest test_openscrub.py tests/test_export_save_as.py -q` and `python -m build`. Browser-test picker cancellation, write/network failure, fallback and a synthetic large transfer with throttled data/writes and a delayed final close. Assert correct byte totals and final file size, responsive progress, no `.blob()` path and bounded buffering; record observed memory behavior. Verify the controls survive polling, switching away/back and repeated exports.
- [ ] **D/R/L:** Prepare a single feature PR; include before/after progress feedback, browser support/fallback limits and the large-file scenario. Record observed UI responsiveness/memory, not an assumed download speedup. After merge, retain Austin's filename/API shape when rebasing later UX work.

**PR description material:** Lead with destination selection and visible byte progress for large exports; describe streaming, approximate ETA, finalization, unknown-total/native-download fallback, actual browser coverage and cancellation behavior. Attribute the missing progress feedback to the donor's current UX, not an existing upstream Save As regression. Do not claim to fix extension handling already present upstream.


## Supervisor rulings / execution context

- Worktree `/home/tahv0/.codex/worktrees/c832/OpenScrub`, branch `pr/save-as-progress`, baseline `5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f`. Original checkout holds the plan/ledger; do not edit product files there.
- Environment path and baseline evidence are in `task-1-report.md` in this directory; read that before running tests. Use explicit workdir/path everywhere. Native worktree may require escalation for writes.
- This is the first actual implementation. Read relevant CONTRIBUTING.md/CLAUDE.md instructions; no release/version bump, no custom training/workbench. Upstream default redaction/review semantics unchanged.
- Donor `2900930f` added tests to root `test_openscrub.py` (not tests/test_export_save_as.py); adapt meaningful tests into the new tests path. Do not cherry-pick the whole integration branch.
- Tests must execute actual changed Python/JavaScript behavior. Static string assertions alone do not prove streaming/progress/job-state semantics. Node harnesses may control real async operations/clocks; use actual browser/HTTP validation for the rendered flow.
- First owning PR updates the contributor test command to collect root test_openscrub.py plus tests/, and includes new tests in sdist. Upstream has no test CI job to extend; do not introduce a new CI workflow in P01. Keep existing root test file and avoid an unrelated packaging rewrite.
- Browser plugin is absent from available tools/skills. Use regular Playwright for actual browser validation and record that fallback. Install any necessary dev/browser tooling into isolated /tmp paths, without adding runtime dependencies or new frontend framework.
- Proposed P01 timing values are the starting contract. Backpressure and count-after-write/close semantics are required; record any necessary proposal adjustment with evidence. Scope stays Save As, no broad download service or P03 polling fix.
- Build a reviewable feature with focused test-first evidence, full suite/build once before commit, evaluated embedded-JS syntax check and real rendered interaction validation. Keep screenshots/large generated files outside committed source.
- Preserve human-readable donor attribution in commit/body; commit only task-owned product/tests/docs paths, never this entire private planning bundle. Git local commits are authorized; no remote pushes, external comments/PR publication, or subagents.
- Write the full implementation report to `task-2-report.md` in this SDD directory, with RED/GREEN evidence, commands/results, changed files, self-review, browser URL/viewport/console/interaction/screenshot evidence and limitations. Write a concise PR title/body draft to `task-2-pr.md` based on actual results. Return only status, commit IDs, one-line tests and concerns/report path.
