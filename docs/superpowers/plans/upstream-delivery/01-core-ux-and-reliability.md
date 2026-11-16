# Core UX and Reliability Implementation Plan

> **For agentic workers:** Use `superpowers:executing-plans` when implementation is requested; delegated execution requires the selected workflow. Checkboxes below are future work.

**Goal:** Deliver P01–P07 as small upstream contributions, with report correctness prioritized by the new research evidence.

**Architecture:** Retain upstream endpoints and ordinary review state. Improve the existing owners first; introduce a private report helper only when the transaction code earns a coherent boundary. No training, Findings, journal or optional-mode dependency.

**Tech stack:** Existing Flask, Python >=3.9, embedded browser JavaScript, OpenCV and standard-library file I/O.

**Spec:** [Decisions and research](decisions-and-research.md), especially R02–R06; [delivery waves and E–L cycle](README.md).

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

## P02 — explicit, idempotent Blur / Keep controls

**What:** Separate an output action from the displayed current state, using explicit setters.

**Why:** Repeated clicks should not accidentally toggle a confirmed choice, and grouped sightings should remain understandable without adding a classification system.

**When:** W1 after B01/B02; independent of P01 and optional policy. Explicitly welcomed. Donor: `39b4ed83`.

**Files / contract:** Existing `applyDet(i, enabled)`, group membership and `enabled` fields in `openscrub_web.py`; `tests/test_review_choices.py`. Labels describe output, not plate identity or training evidence.

- [ ] **E:** Capture existing grouped/person/zone-dropped behavior and keyboard semantics so the wording change preserves upstream's scope.
- [ ] **I:** Add `test_repeated_blur_is_idempotent`, `test_keep_updates_existing_group_members` and `test_bulk_choice_preserves_unselected_groups`; assert repeat actions have the same result and unrelated rows remain unchanged.
- [ ] **I:** Replace ambiguous toggle controls with explicit actions/current state, accessible names and pressed/selected state. Reuse current group propagation; keep zone-dropped rules and existing protection choices.
- [ ] **V:** Run `python -m pytest test_openscrub.py tests/test_review_choices.py -q`, build and browser keyboard/bulk/save/reopen checks. Render a small synthetic case to confirm the chosen `enabled` values drive output.
- [ ] **D/R/L:** Describe the concrete repeated-click/group example, screenshots using synthetic data if useful, and no report migration. Keep future filters in P15 rather than growing this PR.

## P03 — resilient progress polling

**What:** Bound metadata/log requests and reject stale responses after job/view changes.

**Why:** Long scans should remain observable after a suspended tab or failed request, and a late response from job A must not populate job B.

**When:** W1; independent of P04 and new report APIs. Donor: polling subset of `08f432b6`; upstream path verified in R03.

**Files / contract:** `openJob`, `refresh`, polling/log state in `openscrub_web.py`; `tests/test_job_polling_node.py`, `tests/test_job_polling_browser.py`. Requests capture `(job_id, view_generation)`; publication requires both still match. At most one polling cycle per active view is in flight.

- [ ] **E:** Reproduce deferred job/log responses, a response body that never finishes, tab suspension and switching/deleting a job. Record current request overlap and DOM effects.
- [ ] **I:** Add regressions asserting no cross-job publication, no duplicate timer/request growth and recovery after the next successful cycle. Include body parsing in the deadline, not only response headers.
- [ ] **I:** Add a request helper local to the existing UI if reused; initial proposal is a 15-second metadata/log deadline and bounded retry capped at 10 seconds. Keep the existing healthy polling cadence. Abort/ignore obsolete requests and reset log cursors from the server response. Do not apply this deadline to save/download/scan operations.
- [ ] **V:** Run `python -m pytest test_openscrub.py tests/test_job_polling_node.py tests/test_job_polling_browser.py -q`, build and a browser suspend/resume/job-switch exercise. Confirm polling recovery does not trigger rescans or duplicate render actions.
- [ ] **D/R/L:** Report the actual trigger and bounded request behavior, with failure/recovery evidence. Exclude video sections and learning progress from the donor.

## P04 — recent-rate ETA

**What:** Base long-running stage ETA on a bounded recent throughput window with a startup fallback.

**Why:** A fast early scan prefix currently dominates a whole-stage average even after throughput changes; the estimate should reflect the work currently happening.

**When:** W1 whenever the fake-clock scenario is established; independent of P03, logging and preview caching. Donors: `0b2e3d1d`, `367148d`.

**Files / contract:** `WebCallbacks.progress`, existing additive public `eta`, `tests/test_scan_eta.py`. Proposed donor-derived parameters: 120-second window, samples no more often than every 5 seconds except completion, recent-rate preference after 20 seconds. Use monotonic elapsed time; reset on stage changes and terminal states.

- [ ] **E/I:** Add fake-clock tests for startup, a slow tail after a fast prefix, zero progress, backward wall-clock adjustment, stage transitions and completion. Assert finite nonnegative estimates only when a useful rate exists and bounded sample count.
- [ ] **I:** Keep progress stage mapping and existing public field compatibility; replace only the rate estimate. Do not import donor diagnostics hooks or change scan scheduling to improve the displayed number.
- [ ] **V:** Run `python -m pytest test_openscrub.py tests/test_scan_eta.py -q`, build and inspect a synthetic stage transition in the UI. Compare estimates with controlled progress; no claim that ETA itself speeds up inference.
- [ ] **D/R/L:** Describe the misleading early-average example, chosen window/startup tradeoff and measured estimator behavior. Keep parameters easy to review in one component.

## P05 — stable live-preview publication

**What:** Publish complete JPEG snapshots while a browser may be reading the previous one.

**Why:** Writing a served path in place can expose inconsistent bytes; this is independent of expensive per-detection thumbnail generation.

**When:** W1 after an actual HTTP reproduction; independent PR. Donors: preview subset of `90e67b6` / `5e967404`; R04 identifies the current producer/consumer.

**Files / contract:** `WebCallbacks.scan_frame`, `job_preview`, a small `_publish_preview_jpeg(path, image, quality) -> bool` in `openscrub_web.py`, `tests/test_live_preview.py`. Retain the preview's existing scale/rate limits and serve a stable response snapshot.

- [ ] **E/I:** Add a controlled writer/reader regression through the production WSGI path. Assert each response decodes as one complete JPEG and its declared length equals its bytes. Add failed-encode/publication cases that retain the prior complete preview.
- [ ] **I:** Encode before publication, write a same-directory temporary snapshot and replace or use another verified bounded snapshot method. Never publish an empty/partial encoding. Keep the change local unless P06 provides an actually useful byte-publication helper; do not create a generic storage framework.
- [ ] **V:** Run `python -m pytest test_openscrub.py tests/test_live_preview.py -q`, build and concurrent real HTTP requests. Check Windows replacement/read behavior on Windows before claiming it; record unavailable platform coverage.
- [ ] **D/R/L:** Include the observed race/reproduction, publication mechanism, memory bound and failure behavior. Do not bundle corner-save state fixes into this preview PR.

## P06 — report correctness and measured save cost

**What:** Separate atomic publication, overlapping-edit preservation and serialization performance into reviewable changes.

**Why:** R05/R06 show concrete correctness problems, while the original fork throughput explanation does not directly describe upstream. A correct report is more valuable than merely acknowledging the request sooner.

**When:** Begin regressions in W1, deliver in W2 as ready. P06A/B/C are potential separate PRs within the P06 family. P06C is conditional on measured benefit. P07 may follow the shared transaction contract.

**Files / contract:** `job_save_edits` and all actual report writers it can overlap; `tests/test_large_report_io.py`; `benchmark/review_io.py`. Keep a one-owner helper local initially. When shared, use `openscrub_internal.reports.atomic_report(path, report) -> None`: same-directory publication, raise on failure, never acknowledge incomplete persistence. A per-job transaction covers **read → apply → publish**, not just the final write. Do not introduce a database, training fields or a general repository layer.

**B03 extraction follow-ups:** Include ordinary tracking publication in the writer inventory: mixed section donor `08f432b` reloads the latest report before appending tracked rows, but allocates a track ID earlier, so collision/revision tests still matter. Also reproduce scan → Keep some detections → render → reopen: training donor `db9a142` restores original review rows after rendering, while upstream's load/render/write path may discard disabled rows and stable indices. Preserve that generic requirement under a separate report-round-trip fix if confirmed; do not import `learning_session` to obtain it.

### P06A — atomic report publication

**What / why / when:** Prevent an interrupted write from replacing a valid report with partial JSON; first P06 correctness PR after the full handler reproducer exists.

- [ ] **E/I:** Port the probe into real Flask/HTTP tests `test_failed_report_write_preserves_previous_bytes` and `test_save_acknowledges_only_after_publish`. Inject encoding, write, flush and replace failures; assert the previous report remains parseable/unchanged where publication has not succeeded, and the client sees failure.
- [ ] **I:** Implement same-directory temporary writing, explicit flush/fsync policy and replacement with cleanup. Preserve existing report fields and deterministic JSON meaning. Document Windows/filesystem limits; rename atomicity alone is not a blanket power-loss guarantee.
- [ ] **V/D:** Run `python -m pytest test_openscrub.py tests/test_large_report_io.py -q`, full build and restart/rehydration after injected failure. PR lead: interrupted review save should preserve the last complete report. Include the probe only as initial evidence; report actual route-test results.

### P06B — serialize report transactions

**What / why / when:** Preserve two independent overlapping edits; follow P06A if it shares the writer. Atomic replacement by itself cannot prevent a later stale document overwriting another change.

- [ ] **E/S:** Inventory scan completion, tracking additions, manual edits, render preparation, checkpointing, deletion and vault interactions before choosing lock ownership/order. Current serving is threaded; state explicitly if the implemented lock is in-process only.
- [ ] **I:** Add `test_overlapping_sparse_saves_preserve_both_choices` and a tracking/manual-edit overlap case with controlled interleaving. A per-job lock must encompass loading the latest committed report, applying the payload and publication. Coordinate every relevant writer rather than protecting only one endpoint.
- [ ] **V/D:** Verify no deadlock during cancellation/deletion/vault operations and no loss of audio/manual/time edits. Run the P06 suite/build and concurrent HTTP cases. PR lead: independent review updates should survive overlapping requests; explain writer scope and concurrency limitations.

### P06C — reduce demonstrated save work

**What / why / when:** Reduce serialization/request work that remains costly on realistic large reports; only after S01 baseline and P06 correctness are stable.

- [ ] **E:** Measure sparse/no-op/bulk saves through HTTP with realistic motion history. Count parses/serializations/writes; upstream already does one parse/write and supports sparse `enabled` keys. Preserve the original 20.5s/8.8s fork numbers as history, not the before/after table.
- [ ] **I:** Add a no-op regression preserving report bytes/revision and one sparse-change preservation case. Use batched serialization/compact output only if it improves the recorded workload without excessive temporary memory. Do not avoid necessary persistence or silently drop fields for speed.
- [ ] **V/D:** Run `python -m pytest test_openscrub.py tests/test_large_report_io.py -q`, `python benchmark/review_io.py --scenario saves --rows 1000 10000 100000`, full build and relevant browser checks. The benchmark CLI is a planned interface, not an existing command. PR body reports timings, bytes, memory, samples and environment at exact before/after SHAs; close this candidate if no worthwhile upstream gain exists.

## P07 — preserve choices and make retry safe

**What:** Bind saving/rendering to the initiating job and edit snapshot, preserve newer drafts, and avoid duplicating manual regions after a lost response.

**Why:** R03 shows mutable globals across awaits; R06 demonstrates replay appends the same manual addition twice. A timeout or failed response must not become lost work, duplicate work or rendering the wrong job.

**When:** Reproduce in W1; deliver independently or after P06B's transaction contract in W2. Split browser-state and replay changes into two PRs if they are independently reviewable. Donors: ordinary save subset of `90e67b6`, `5e967404`, `test_release_reliability.py`.

**Files / contract:** `saveAndRender`, current edit arrays/maps and `job_save_edits`; `tests/test_review_save_failures.py`. Capture job/view plus submitted values; clear only acknowledged edits that have not changed since submission. Proposed replay contract: a stable per-addition `manual_id` generated once by the new UI and persisted additively in the detection. A retry with that ID and identical geometry is a no-op; incompatible reuse is an explicit error. Legacy clients without IDs retain their existing schema behavior. No journal/database or inference label.

- [ ] **E/I:** Add `test_job_switch_during_save_never_renders_new_job`, `test_newer_edits_survive_save_ack` and `test_failed_save_keeps_manual_and_audio_drafts`. Assert no render follows a failed save and no stale response clears the current job's edits.
- [ ] **E/I:** Add `test_manual_addition_retry_after_lost_response_is_idempotent` through real HTTP, including restart/reload and different IDs with intentionally identical geometry. Do not deduplicate legitimate additions merely because their coordinates match.
- [ ] **I:** Check HTTP status before treating JSON as success. Keep pending/error status within existing controls and retry only the captured operation. If newer edits exist when a save completes, retain them visibly instead of silently rendering a result that appears to include them. Do not add P03's short polling deadline to saves or claim aborting a request cancels an already committed server write.
- [ ] **V:** Run `python -m pytest test_openscrub.py tests/test_review_save_failures.py tests/test_large_report_io.py -q` for files present on this branch, build, browser failure/retry cases and an actual save/render on synthetic footage.
- [ ] **D/R/L:** PR material identifies the exact lost-response/job-switch trigger, before/after state, additive ID compatibility and evidence. Exclude the fork's unrelated confirmation-preview leases and custom corner 409 recovery.

## Review focus

Capture immutable job identity before awaits; distinguish request failure from server commit; serialize all overlapping report writers; keep cached/public metadata additive; include new modules and tests in actual distributions/commands. These checks belong to the relevant task's V stage, not a later cleanup PR.
