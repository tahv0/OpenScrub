# Large-Video Performance Implementation Plan

> **For agentic workers:** Use `superpowers:executing-plans` when implementation is requested. Keep each demonstrated problem in its own PR; checkboxes are future work.

**Goal:** Make long/large-video work measurably more responsive and reliable while preserving exact frames, decisions and upstream defaults.

**Architecture:** Measure the existing save/report/thumbnail/decoder paths before extracting focused fixes. Keep caches and queues bounded and job-scoped. Reuse upstream's existing disk thumbnail cache and improved PhiMemory implementation.

**Tech stack:** Python >=3.9, Flask, OpenCV/FFmpeg, embedded browser UI; deterministic synthetic reports and media under `benchmark/` / `tests/`.

**Spec:** [Decisions and research](decisions-and-research.md), R05–R09; [delivery cycle](README.md). P06/P07 are detailed in [core reliability](01-core-ux-and-reliability.md).

## Global constraints

Performance must not come from fewer requested frames, weaker masks, lost edits, bypassed privacy checks or replacing correct pixels with a cached different frame. No permanent Findings library, SQLite review index or new training dependency. Generated large media/results remain outside Git; fixture recipes and concise measurements accompany their owning PR.

## Shared measurement contract

Planned tool: `benchmark/review_io.py`. Proposed CLI: `--scenario saves|reports|thumbnails|decode|scan`, `--rows 1000 10000 100000`, `--video PATH`, `--output PATH`; only arguments needed by the selected scenario are required. Emit JSON with base SHA, fixture seed/size, software/hardware, samples, aggregate metrics and correctness results. Add scenarios as the owning PR needs them, rather than building a framework before fixing anything.

Use three warm-up operations and five measured repetitions for short cases; expensive long scans may use fewer runs but must say how many. Report median and individual values; use p95 only with enough observations to make it meaningful. Separate application-cache cold/warm state from filesystem cache state. Do not drop the machine's global caches or require privileged tuning for ordinary reproduction.

### S01 — large reports and saves

**What:** Generate upstream-format reports at 1k/10k/100k rows, with an optional 250k stress case, realistic cumulative motion history and ordinary manual/audio/groups.

**Why:** The earlier minimal probe and the fork's custom-label report are different workloads. The upstream regression must exercise fields Austin actually maintains.

**When:** B03/W0, then P06/P07 E/V. Include the minimal relevant generator with those PRs.

- [ ] **E:** Record JSON bytes, rows, duration/frame count, motion-history size and sparse/no-op/bulk payload bytes. Use fixed synthetic identifiers; exclude training labels, journal materialization and private footage.
- [ ] **V:** Measure real route latency, parses, serializations, writes, process memory and browser save behavior. Include failed/overlapping saves and no-op retries. Compare identical inputs/settings before and after.
- [ ] **D:** Keep the source-isolated 100k result (~1.074 seconds here) labeled separately from production HTTP results. Describe the bottleneck actually measured, even if it differs from the fork's original explanation.

### S02 — report reads and thumbnail cache states

**What:** Exercise existing warm disk thumbnails, multiple cold misses, parallel misses and a report/geometry replacement.

**Why:** Warm upstream JPEG hits already skip JSON parsing. Optimizing an imagined warm-hit parse would misrepresent the benefit.

**When:** W0 baseline, P08 E/V and combined P08/P10 verification.

- [ ] **E:** Count report reads/parses and source decoder opens for each state; include same-size atomic report replacement and source replacement.
- [ ] **V:** Measure first visible group latency, repeated requests, memory retention and invalidation. Assert changed geometry cannot reuse a stale thumbnail solely because its numeric row index stayed the same.
- [ ] **D:** Report warm-hit and cold-miss results separately, with source/report identity rules and retained-cache limits.

### S03 — browser scheduling and large review lists

**What:** Populate many independent and grouped sightings, then open review, jump several screens, filter, edit and switch jobs.

**Why:** DOM/card construction and request bursts can dominate interaction even when a warm JPEG is fast.

**When:** P09/P15 E/V; a small deterministic browser fixture belongs in tests, larger runs in the benchmark.

- [ ] **E:** Record mounted card count, outstanding requests, queue age, first visible completion, main-thread stalls and memory. Keep group counts, not only raw detection counts.
- [ ] **V:** Assert every saved/hidden choice survives paging, filtering and scroll jumps, and obsolete requests cannot repopulate another job. Measure visible latency under background load.
- [ ] **D:** State whether the change bounds DOM/images only or also reduces metadata payload; do not claim full pagination of a still-complete JSON response.

### S04 — long-GOP, 4K and source-frame correctness

**What:** Generate clips with visible frame IDs and machine-readable markers at multiple positions, including long GOP and normalized VFR.

**Why:** Decoder speed is useful only when the returned frame/crop matches the request. Duration, resolution, bitrate and GOP affect different parts of the workload.

**When:** P10/P16/P17 E/V, and O02 later. CI uses short clips; opt-in measurement uses long 4K/high-bitrate files.

- [ ] **E:** Record codec, FPS/time base, duration, GOP, dimensions, file bytes and normalization path. Seek near start/middle/end and distinguish exact editing reads from tolerant compare previews.
- [ ] **V:** Check actual frame markers, PTS/source coordinates, crop mapping, cancellation and deadline cleanup. Track decoder RSS/concurrency and whether an expensive request delays unrelated saves.
- [ ] **D:** Publish the recipe and measured hardware limits, not the large media. Do not equate successful `CAP_PROP_POS_*` setting with verified frame identity.

### S05 — progressive scan work

**What:** Compare early/middle/late scan costs with increasing OCR history/detections, at fixed frame content and settings where possible.

**Why:** PhiMemory is already fixed upstream; remaining history-dependent work must be demonstrated before porting fork-only preview-cache code.

**When:** P11 E/V, initially W0/W2 investigation. It may close without a PR.

- [ ] **E:** Profile detector/OCR time separately from callbacks, report aggregation and preview publication; count repeated work rather than relying on ETA alone.
- [ ] **V/D:** Record a reproducer only for an actual upstream growth pattern. If the cost is solely in removed `finding_previews.py`, mark it removed-system-only and preserve the finding's history.

### S06 — lifecycle and resource release

**What:** Delete/lock/cancel/restart jobs while reads, cache fills or decodes are pending.

**Why:** A fast cache or worker becomes a reliability/privacy regression if it publishes stale data or retains plaintext after the job lifecycle ends.

**When:** Every P08–P10 V stage and C01 integration; reuse the smallest relevant test fixture.

- [ ] **V:** Assert cache eviction and worker cleanup, no publication after source/job invalidation, bounded retries, and preserved legitimate decisions after restart.
- [ ] **D:** Record the lifecycle tested and platform limits. Do not add a permanent diagnostics/crop database to measure these cases.

## P08 — bounded report snapshots and thumbnail invalidation

**What:** Avoid repeated parsing for concurrent cold-miss/report consumers and invalidate derived thumbnails correctly when their source/geometry changes.

**Why:** R07 shows repeated cold paths, while existing warm JPEGs are already cheap. The useful optimization is sharing a valid snapshot, not caching every layer indiscriminately.

**When:** W2 after S02 establishes a benefit. Declare dependency on P06 publication notifications if used; otherwise target upstream directly with independently verified identity handling.

**Files / contract:** `_load_job_report` read-only consumers, `job_detections`, `job_thumb`, lifecycle hooks; `tests/test_thumbnail_io.py`; benchmark reports/thumbnails scenarios. Keep mutation paths on fresh transaction documents. If substantial, extract `ReportSnapshotCache` into `openscrub_internal/reports.py` or a cohesive `report_cache.py`, not a generic cache framework.

Proposed contract: `get_snapshot(job_id, report_path, source_identity) -> (document, revision)`; callers do not mutate shared data. `invalidate(job_id)` clears retained/derived state. Identity includes actual report publication/file identity and source identity, not file size alone. Initial proposed retained-memory budget is 128 MiB across cached snapshots, with single-flight parsing per key and no caching of an entry exceeding the budget. Account for retained objects, not only JSON byte length; benchmark total process RSS separately.

- [ ] **E/S:** Complete S02 and list read-only versus mutating callers. Audit all writers and browser cache keys; decide which geometry/source changes require new thumbnail identities.
- [ ] **I:** Add `test_warm_disk_thumbnail_does_not_parse_report`, `test_parallel_cold_reads_share_one_snapshot`, `test_same_size_replace_invalidates_snapshot`, `test_writer_cannot_mutate_cached_snapshot` and `test_vault_lock_evicts_report_data`.
- [ ] **I:** Introduce bounded snapshot reuse and invalidation only for measured consumers. A failed parse/publication does not poison the last valid cache state or mask a corrupt report. Bypass retention for oversized entries without changing response correctness; do not introduce a persistent row index to force a benchmark win.
- [ ] **V:** Run `python -m pytest test_openscrub.py tests/test_thumbnail_io.py -q`, relevant P06 tests if a dependency, build, and planned benchmark `--scenario reports` / `--scenario thumbnails`. Exercise S06 and confirm no new personal-data lifetime.
- [ ] **D/R/L:** PR body distinguishes cold gains from unchanged warm behavior, lists memory/correctness limits, and provides the exact before/after report sizes. If accurate snapshot identity requires a shared prerequisite, declare it instead of silently stacking on the full integration branch.

## P09 — visible-first thumbnail scheduling

**What:** Limit mounted cards/image requests and prioritize the current viewport while preserving complete group decisions.

**Why:** Building all cards and warming too far ahead can spend resources on images the user never sees, especially after a large scroll jump.

**When:** W2 after S03; independent of P08 where possible. Donors: `d265c34`, `aeb24ce`, `312d91f`, `52274f32`.

**Files / contract:** `loadReview`, existing group metadata and thumbnail UI in `openscrub_web.py`; `tests/test_thumbnail_scheduling.py`. One queue per active review view, tagged with job/view generation. Proposed initial limits: mount pages of 64 groups, up to four browser thumbnail requests in flight, and prefetch one viewport ahead. Tune only with recorded evidence; these are internal starting values, not new user-facing controls.

- [ ] **E/I:** Add browser tests `test_scroll_jump_prioritizes_current_view`, `test_paging_preserves_hidden_group_choices`, `test_switch_job_discards_old_thumbnail_results` and a request-count bound. Include empty/grouped/zone-dropped states.
- [ ] **I:** Store choices independently of mounted cards; use metadata to count/filter all groups. Cancel obsolete fetches or ignore their results, and remove them from the active queue. Retry transient failures with a bounded budget; failed images must not prevent editing other cards.
- [ ] **I:** Prefer local view changes over save/refetch cycles. Integrate P15 filters only through a small documented queue-refresh hook if that feature is present; do not copy the learning sampler or similarity UI.
- [ ] **V:** Run `python -m pytest test_openscrub.py tests/test_thumbnail_scheduling.py -q`, build and S03/S06 browser measurements. Validate both warm and cold server responses; report the remaining full-metadata cost honestly.
- [ ] **D/R/L:** Include large-group counts, mounted/request bounds, visible-latency results and preservation of hidden choices. No new review database or inference semantics.

## P10 — bounded, source-correct frame decoding

**What:** Bound costly thumbnail/exact-edit decoding and carry trustworthy source/time metadata to callers that need it.

**Why:** Long-GOP 4K seeks may be expensive; an earlier fallback frame can also be mistaken for the selected frame when editing. Speed and source correctness need one explicit decoder contract.

**When:** W2 after S04 and a demonstrated upstream cost/identity problem. It need not depend on P08/P09; state any shared scheduler dependency. Donor: selected `5d55f8ea` and follow-ups, not the confirmation-repair protocol.

**Files / contract:** `_frame_at`, `job_thumb`, exact-frame callers, appropriate existing FFmpeg helpers; `tests/test_thumbnail_decode.py`. If a separate worker is justified, keep it under `openscrub_internal/frame_decode.py` with no Flask/global job import. Internal `FrameSample` carries pixels, source identity, requested time, actual time/frame and whether the exact contract was satisfied; failures are explicit.

- [ ] **E/S:** Distinguish tolerant compare preview from exact geometry/edit requests. Confirm normalized/source paths and coordinate transforms; retain intentional compare fallback without labeling it exact.
- [ ] **I:** Add `test_exact_frame_matches_burned_in_marker`, `test_vfr_normalized_coordinates_match`, `test_timeout_releases_decoder`, `test_source_change_discards_pending_result` and a concurrent-save responsiveness case.
- [ ] **I:** Reuse an existing subprocess/FFmpeg path where it can be interrupted and verified. Proposed initial budget is 10 seconds for a normal cold decode and at most 60 seconds for an explicit retry, matching the donor's bounded retry intent; no unbounded background retries. A thread whose native decoder keeps running is not considered cancelled merely because HTTP stopped waiting.
- [ ] **I:** Bound active decoder work (initial proposal: two shared workers) and queued obsolete work. Crop/resize before unnecessary large image transport when the source coordinates are known. Return actual frame evidence; refuse exact-mode success on an unverified fallback.
- [ ] **V:** Run `python -m pytest test_openscrub.py tests/test_thumbnail_decode.py -q`, build, planned `benchmark/review_io.py --scenario decode --video <synthetic-clip>`, and S04/S06. Verify cleanup on supported Windows/Linux paths; do not assert a universal 4K latency target from one machine.
- [ ] **D/R/L:** Describe the exact cold-seek trigger, resource bounds, source-frame contract and measured tradeoffs. Keep 409/503 corner-confirmation leases out; any ordinary timeout response must have a corresponding small upstream UI handling change.

## P11 — remaining scan overhead investigation

**What:** Identify upstream scan/preview work that grows unnecessarily with accumulated history or decodes an unused prefix, beyond the already-fixed PhiMemory implementation.

**Why:** The user wants the long-scan improvements retained, but `a11a3926` optimizes a cache that upstream does not have. Reintroducing that system would defeat the cleanup.

**When:** Start S05 in W0/W2; only create a PR after an upstream hot path is identified. No dependency on adding a cache or optional features.

**Files / contract:** Initially benchmark/profile evidence only. Candidate owners are existing scan callbacks/preview publication and `run_scan`; implementation files/tests are named after the demonstrated function, not a new subsystem in advance.

- [ ] **E:** Preserve the generic requirement behind the `smooth_dense_tracks` initial-seek hunk hidden in mixed donor `ccff62f`: avoid unnecessary work before a late processing window. The B03 source-isolated probe observed 17,873 reads before useful processing at a 600-second start versus one after a simulated successful seek; that is operation-count evidence. Real-video research found the seek fast but cancellation-delaying on a single-keyframe file, so do not port that mechanism unchanged. P11A below evaluates the smaller sequential alternative. Preserve the validated benefit when P18 resumes a long scan.
- [ ] **E:** Profile fixed-content early/middle/late intervals and separate OCR/model work from callback/report costs. Compare against Austin's current indexed/batched PhiMemory behavior.
- [ ] **S/I:** If a specific growing operation exists, write a deterministic work-count regression and extract only the constant/bounded-work change. If not, close P11 as already fixed or removed-system-only with source/profile evidence.
- [ ] **V/D:** Run the owning function's tests, full suite/build and the same scan workload. State actual model/provider/settings and coverage. Do not describe improved ETA as throughput improvement.
- [ ] **R/L:** Submit only a concrete measured fix; otherwise update the preservation ledger so the historical optimization remains accounted for without extra production code.

### P11A — skip retrieval of unused dense-smoothing frames

**What:** Keep sequential decoding but use `VideoCapture.grab()` for frames outside every needed gray-cache span, retrieving pixels only for frames the onset matching actually uses. Release the decoder on all exits.

**Why:** Current smoothing retrieves and allocates every prefix frame even when a detection first appears ten minutes into a video. Real 610-second, 256×144 CFR short-GOP and single-keyframe experiments found identical source markers and all Detection fields with the sequential alternative. Unlike the initial-seek candidate, it retains the existing periodic cancellation checks during prefix processing. The research results are evidence for implementation, not a shipped improvement or a general 4K guarantee.

**When:** Independent W2 performance PR after the real-video baseline; may target Austin plus the test-only prerequisite without P06 or optional modes. The broader P11/S05 investigation remains open.

- [ ] **E/S:** Pin the source and record short-GOP/single-keyframe before/after samples, actual read/grab/seek counts, source markers, complete detection equality and timed cancellation. Keep the rejected seek's cancellation result as the reason for choosing sequential decoding; do not claim to skip codec prefix decoding.
- [ ] **I:** Add meaningful regressions under `tests/test_dense_smoothing_io.py`, then change only the existing sequential cache fill and necessary decoder cleanup. Keep logical frame indices, cache spans/eviction, matching thresholds, margins, interpolation, grace padding, report schema and default policies unchanged. A failed grab/read must stop consistently without mislabeling later frames.
- [ ] **I:** Preserve cancellation checkpoints through skipped frames and release the capture in `finally` on success, EOF, cancellation and exceptions. Do not add seek state, a decoder subprocess, new dependency or a background thread to this focused change.
- [ ] **V/D:** Run the owning tests, existing suite, full build and marked real-video comparisons. Include a small repeatable recipe/measurement tool under `benchmark/` only as needed for this scenario. Report operation counts separately from wall time and codec work, with resolution/GOP/frame identity, three warm-ups/five samples and memory/cleanup limits. Keep generated video outside Git.
- [ ] **R/L:** PR lead: late dense-track smoothing should avoid retrieving frames it never uses. Cite measured results at exact before/after commits and retain cancellation/frame-correctness evidence. Keep broader scan-history, ETA and stop/review changes separate.

## Review focus

Report identity can change without changing file size; warm and cold cache behavior differ; queues must release obsolete work; exact frame claims require actual pixels/PTS; report and source snapshots must expire with the job. Measure each at the owning task's V stage and again for combined changes in C01.
