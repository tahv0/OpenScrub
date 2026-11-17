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

### P08A — invalidate stale thumbnail pixels and browser URLs

**What / why:** Give derived thumbnails an identity tied to their report, actual source and live job. Actual pinned routes return visibly stale blue/yellow/green/magenta crops after a box edit, same-size/same-mtime atomic report replacement, normalized-source selection and same-path source replacement. Their existing public one-hour HTTP cache can also retain a successful obsolete URL. This is a demonstrated correctness issue independent of report-cache speed.

**When:** Separate PR before P08B, with the necessary P06B lifecycle/publication interfaces declared as prerequisites. Avoid duplicating that coordination or depending on the complete assembled application.

- [ ] **E/S:** Preserve the actual-route baseline in the execution evidence: three warm hits perform zero JSON parses; four parallel cold misses parse four times. Inventory all crop inputs, report/source replacement and both demand/pre-generation producers. Decide a small derived identity and compatible unversioned-URL cache policy; file size or size+mtime alone is insufficient.
- [ ] **I:** Keep validated warm hits free of report parsing. Tie client URLs/HTTP validators to the requested revision, and reject/discard obsolete pending fills rather than serve new pixels under an old immutable identity. A coarse report revision may invalidate decision/audio-only updates initially; document that tradeoff. Remove obsolete derived files without creating a persistent plaintext history.
- [ ] **I:** Select the normalized source before launching pre-generation. Capture and revalidate source/report/job identity at publication, sharing the same contract with demand generation. Stage JPEG output and discard stale work through the lifecycle boundary; use bounded retry/metadata refresh. Unlinking a JPEG in the save route alone does not cover browser caches, external replacement or a late worker.
- [ ] **V/D:** Verify actual crop pixels after box/time/fps/cum/source/index changes, conditional HTTP responses and browser revisits. Interleave demand/pre-generation with publication, cancel/rescan, deletion/retention and vault transitions. Preserve defaults and warm-path parsing cost; report in-process/platform limits. No large-report throughput claim without measurements.

**Refined P08A interface contract:** The [current-interface research](execution/evidence/research/thumbnail-identity-contract-research.md), including its superseding identity amendment, binds an opaque per-incarnation generation to observed opened-file stamps, managed report/source epochs, operation ownership and recipe values. Do not hash an entire video or report merely to name the generation: hashing once per observed stamp does not strengthen subsequent warm verification, and a multi-GB first-thumbnail read is unjustified. Necessary cold report parsing remains; row-content fingerprints serve only safe browser equality checks, and JPEG bytes supply HTTP ETags. Fast reuse explicitly covers managed publication and observed file changes, not uncooperative external writes preserving every observed attribute.

- [ ] **S/I:** P06 already selects normalized source before pre-generation on the reviewed12919c9 pin; preserve that fix. Add the missing coherent source/report generation boundary, including scan's report-before-source-assignment interval. Prepare source ownership outside report lock, select/revalidate/publish under it, and keep long parse/decode/I/O and lease release outside. Reuse an established descriptor when its inputs match; concurrent discovery must not generate endless new versions.
- [ ] **I/V:** Serve versioned crop/lightbox URLs with private conditional revalidation after current-generation/lifecycle checks. Old matching ETags must not produce304 for obsolete input. Keep successful warm requests free of report parsing/full hashing. Invalid current report/source returns a current error rather than stale pixels. Stage producer bytes and reject obsolete tickets before publication.
- [ ] **I/V:** Keep any automatic thumbnail recovery bounded to one coalesced metadata attempt per mounted review. Patch image bindings only when the same indexed raw row is still equal; otherwise show unavailable/reopen status. Do not rebuild the editor, change pending choices/audio/manual IDs, or trigger saves/renders. A patched version does not replenish the automatic budget; persistent failures cannot create a fetch loop.
- [ ] **I/V:** Retire old derived files under existing job lifetime with actual active-reader cleanup and bounded failure backlog; no permanent plaintext generation archive. A private thumbnails helper is justified only for shared demand/pre-generation identity, staging and cleanup. Keep mutable transaction documents and conditional P08B parsing cache separate. Measure introduced cold/metadata/retention costs during delivery, including row fingerprints; no performance or filesystem-wide guarantee follows from this source-only design.

### P08B — retain measured read-only report snapshots within a budget

**What / why:** Share parsing among the demonstrated cold/read-only consumers while retaining fresh mutable documents for edits/tracking/render transactions. Repeated parse counts establish work, but not enough latency or memory benefit to justify a cache by themselves.

**When:** After representative cold-consumer timing/RSS evidence, and after the required lifecycle/transaction interfaces. It may close without implementation if admission overhead outweighs useful reuse.

- [ ] **E/S:** Measure identical 1k/10k/100k report workloads before/after, including parallel cold metadata/thumbnail requests. Select only useful read-only consumers. Do not globally replace `_load_job_report` with a shared mutable tree.
- [ ] **I:** Single-flight by verified opened-report/source/job identity; fence fills before and after parsing. Keep retained nested data immutable and transaction documents independent. Surface corrupt-current-report errors rather than silently returning an older revision. Oversized entries bypass retention correctly; bound concurrent fills and active-reader lifetime separately.
- [ ] **I:** Define the proposed 128 MiB limit as an owned retained-object admission budget, including cache metadata, not raw JSON bytes or process RSS. An identity-deduplicated size walk of the final retained representation can occur once at admission; charge its cost to the cold path, cache the result and avoid per-hit deep walks. Explain conservative cross-entry shared-object accounting. Transient parse/freeze buffers, active readers and allocators still require separate RSS measurement.
- [ ] **V/D:** Preserve warm-no-parse, same-size replacement, mutation isolation, corrupt-report recovery, eviction/oversized bypass and vault invalidation regressions. An evicted entry may remain referenced by active work; lifecycle ownership must drain it before a successful transition. Publish measured cold benefit and admission/memory costs with exact SHAs; no RSS-ceiling or secure heap-erasure claim.

## P09 — visible-first thumbnail scheduling

**What:** Limit mounted cards/image requests and prioritize the current viewport while preserving complete group decisions.

**Why:** Building all cards and warming too far ahead can spend resources on images the user never sees, especially after a large scroll jump.

**When:** W2 after S03; independent of P08 where possible. Donors: `d265c34`, `aeb24ce`, `312d91f`, `52274f32`.

**Files / contract:** `loadReview`, existing group metadata and thumbnail UI in `openscrub_web.py`; `tests/test_thumbnail_scheduling.py`. One queue per active review view, tagged with job/view generation. Proposed initial limits: mount pages of 64 groups, up to four browser thumbnail requests in flight, and prefetch one viewport ahead. Tune only with recorded evidence; these are internal starting values, not new user-facing controls.

**Local completion:** Independently reviewed `pr/visible-first-thumbnails` at `fe20dff7b73efb5afdbf3130e75a19c8b35ecba3`, based on P02/P07a. The initial candidate passed 212 full-suite tests and actual large/small UI, hidden-choice save/fresh-reopen and render checks. Final local corrections passed 82 scoped checks on each of Python 3.12/3.9, focused Chromium DOM/Tab/focus/restoration/retry/anchor checks, rebuilt package bindings and installed HTTP. The [report](execution/evidence/delivery/task-9-report.md) and [scoped approval](execution/evidence/delivery/task-9-fix1-review.md) distinguish the initial and final tested sources. The 64 normal + one focus exception/four unsettled-operation contract is retained; no latency, whole-memory or actual-BFCache claim is made. P06D/P16D and combined ownership checks remain C01.

**Confirmed baseline:** Actual pinned UI/routes mount and request all 1k/10k ordinary groups. Ten thousand groups comprise 15,000 rows and a 2,460,605-byte metadata response; bounding cards does not paginate that response. Six warm Flask responses held at a controlled boundary occupy the observed browser connections. After a bottom jump, the next flight in the 10k case contains zero visible groups; after switching jobs, 9,994 old thumbnail requests remain outstanding and new metadata waits for connections. Chromium sometimes reprioritizes visible images, so this is not a strict FIFO claim. Old images did not repopulate the new job's DOM. P07a already preserves the tested pending mixed-group choice across a revisit; reuse that ownership. These are ordering/count findings, not measured speedups.

**Source handoff:** Use reviewed P02/P07a `2ae3257b9752e2d976ff7a0d39955a13c133273a`; P03 is a parallel source line, not a P02-inclusive prerequisite. Derive complete ordered group/zone descriptors before constructing cards, retaining P02's `TRKMEM`/`ROWCARD` and P07a's decision owner. Current variable-height category grids need measured row spacers and preserved scroll anchors. Start with one global 64-card window, at most one additional focused card, a contained 112px thumbnail well and native previous/next range controls so omitted groups remain keyboard reachable. These are provisional internal layout choices requiring actual desktop/mobile/zoom evidence, not tuned values. Preserve full text, actions, category/zone bulk scope and the active editor. Numeric metadata/row heights/selected IDs and category shells remain proportional to report size.

**Queue ownership:** Four slots cover actual unsettled browser fetch/body operations, including drain of the previous review instance; abort is not proof that server decoding ended. Every continuation checks job/view, review-instance token and the connected image binding. Preserve 600/1200/1800ms retries with a finite budget across unmount/remount, revoke retired object URLs, and let image failure leave editing usable. Scrolling, resizing and local queue refresh never save, refetch metadata or remount the editor. The [source handoff](execution/evidence/research/review-scheduling-contract-research.md) records exact owners, keyboard/focus/selection rules and unrun validation. P03 polling, P01 streaming Save As, P06 lifetimes/complete report preservation, P08A image generations and P15 filters each retain their separate C01 gates.

- [x] **E/I:** Verify current-view priority, hidden group choices, stale job/view responses and the full-body request bound with emitted-JS tests and actual browser scenarios, including empty/grouped/zone-dropped states.
- [x] **I:** Keep choices and whole-category/zone action scope in complete metadata. Preserve person-before-track grouping and row-local editor semantics; abort obsolete browser work while waiting for actual settlement, with finite retries and usable failed-image states.
- [x] **I:** Keep scrolling/resize local and provide the complete-ID filter seam. Correct DOM/Tab ordering and owned layout/retry restoration through the scoped review loop; preserve active editor and pending saves.
- [x] **V/D/R — local:** Retain the exact initial/full and final/focused test identities, warm/cold route and visible-completion counts, actual hidden-choice output evidence, package checks and independent review. A latency comparison was not run or claimed; full metadata and native/browser memory remain separate costs.
- [ ] **V/R/L — combined and publication:** Validate P03/P01/P06/P08A/P15/P16D interactions on C01, including full post-render rows and ordinary Play startup. Publish only when requested and update dependent branches after actual upstream acceptance.

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

### P10A — bind editable pixels and geometry to the same source sample

**What / why:** Separate exact geometry requests from tolerant representative/compare previews. Actual upstream editor interactions show three concrete mismatches: at 24 fps, 0.2s displays frame 5 while geometry uses frame 4; the valid 5 fps slider endpoint 1.9s naturally falls back to frame 8 while geometry uses frame 9; an actually normalized VFR source has the same timestamp/index disagreement. The editor permits pointer edits in each case. These are correctness findings, not decode-cost measurements.

**When:** A focused prerequisite before new plate/shape editing relies on source coordinates. It can precede P10B's worker/resource optimization, with necessary lifecycle interfaces declared. P16 resize and mask rasterization stay separate.

The [bounded decoder feasibility study](execution/evidence/research/exact-sample-feasibility-research.md) exercises the exact existing reader body on pinned12919c9:22 successful reads/clamps match independent sequential pixels and FFprobe PTS, six natural EOF reads fail, and all28 captures release. Integer-index reading resolves all three known cases on the tested CFR/normalized H.264/FFmpeg subset; no new FFmpeg extractor is justified yet. This is not integrated route/UI evidence or certification of raw VFR, arbitrary metadata, fractional time origins, HDR mapping or other backends.

Deliver backend exact-sample/optional geometry-precondition support first, the optional strict tracking-seed adapter next, then switch the ordinary editor and Track action together. Intermediate PRs preserve existing UI and legacy callers. Do not expose a partly migrated editor with Track disabled while waiting for a later PR. These can be two or three dependent changes according to the actual diff; source/field spellings remain provisional.

The [refined source handoff](execution/evidence/research/exact-editor-contract-research.md) selects exact `12919c9` for the backend and keeps a shared observed-source owner inside it. Geometry compares source/timeline and target-row context independently of whole-report thumbnail generations, so unrelated output/audio saves remain legal. Explicit box/span baselines support already-equal retries; one owned submitted snapshot can be confirmed after a lost acknowledgement before newer geometry advances. P07b identical manual replay is recognized before new freshness validation. Strict tracking supplies verified pixels to every initializer while each tracker retains its existing capture owner. Pending normalized-source adoption uses the existing post-scan call site with explicit failed/unavailable recovery. Existing reports have a metadata-qualified, sample-verified compatibility path; its backend/time tolerance and support claims require actual acceptance before migration. P16D must precede the ordinary UI switch. These are source-backed directions, not implemented or tested behavior.

- [ ] **E/S:** Specify one source/timeline resolver and a coherent final-frame boundary policy for image selection, offsets and geometry. Exact samples carry actual source identity, frame/time, dimensions and requested time; choose a decoder method whose output identity can be verified. A successful seek setter or a capture-position value alone is not verification.
- [ ] **S/I:** Resolve and retain the integer once; for valid times through report duration, clamp only the final interval to `N-1`. Use one coherent admitted source/report snapshot for pixels, offsets and boxes, with finite dimensions and observed decoded-time checks under the supported backend policy. Decode outside the report lock and revalidate current source/report ownership before publication. Keep requested, canonical scan and observed decoded times distinct; do not round-trip the selected index through seconds or fabricate integer PTS. No per-scrub full-video hash/prefix scan is required.
- [ ] **I:** Bind the editor's image and boxes to that same sample before enabling geometry gestures. Handle late/out-of-order image and boxes responses, missing/changed sources and failed exact reads without making an older visible frame editable under a new timestamp. Keep ordinary pending edits and report coordinates intact.
- [ ] **I:** Geometry drafts capture their source/sample/row precondition when created and carry it through the existing latest-report transaction and P07a snapshots. Unrelated output/audio choices need no image sample. Preserve idempotent already-published manual replay and avoid a blanket report revision gate; invalid source/row changes retain pending drafts. Reuse existing P06 ownership and the shared observed source contract with P08A, without a parallel identity store or long-lived corner-confirmation lease.
- [ ] **I:** Add a narrow optional exact seed input/adapter across person/Vit/NCC initialization. The exact editor must initialize from its inspected source/index/pixels, without rounded or nearby-frame substitution. Legacy callers without that input keep their current behavior; subsequent tracking algorithms/thresholds and O02 loss/keyframe policy remain separate. Source-bind launch before model work and preserve existing publication/lifetime gates.
- [ ] **I:** Preserve intentional compare walk-back and thumbnail representative search. Where a time is displayed, distinguish the actual sample/fallback from the requested time; do not silently redefine a thumbnail's representative cache index as exact frame provenance.
- [ ] **V/D:** Retain the three natural browser cases, independent sequential frame markers/PTS, normalized duplicate-frame limits, start/middle/end and odd-coordinate crop comparisons. Verify source/content/crop coordinate round trips and blocked edits while the sample is unverified. Run relevant suite/build/browser paths; make no general 4K or decoder-latency claim from short clips.

### P10B — bound demonstrated expensive decoding work

**What / why / when:** Implement the parent P10 resource/deadline/queue contract only after actual cold long-GOP/4K workloads justify the mechanism. Keep exact-frame correctness from P10A. The proposed 10-second normal budget, explicit retry up to 60 seconds and two shared workers remain starting proposals, not measured optimal settings or already-implemented behavior.

- [ ] **E/I/V:** Measure source/frame correctness and cost separately; use an interruptible existing FFmpeg/subprocess path if justified. Prove deadline/cancel terminates and reaps real decoder work, releases slots, rejects obsolete source results and leaves unrelated saves responsive. A stopped HTTP waiter with a live native thread does not pass. Report memory/concurrency and platform limits, preserving all parent P10 gates.

### P10C — cancellation polling in ordinary manual tracking

**What / why:** Stop repeated NCC matching and held-coverage work once cancellation is observed. The [actual full-module baseline](execution/evidence/research/tracker-cancel-baseline-research.md) on reviewed12919c9 shows41 additional native matches,13 frame grabs and19 reads after cancellation at match1; natural target-loss coverage also keeps appending. The existing web route correctly suppresses publication and holds ownership until cleanup, so this is a separate compute-cancellation defect. The adjacent person-helper catch also swallows PipelineCancelled in a controlled handoff test.

**When:** Small upstream reliability follow-up on the reviewed capture-finally/operation contract. No new tracker, optional model or O02 feature is needed. Native decoding/model/match interruption remains P10B, not a claim from Python polling.

**Local completion:** Independently reviewed `pr/manual-tracker-cancellation` at `2004b22002b8317c26ea508ff8187acbcd0cfab2`, based on reviewed `12919c9`. Fifteen lines add cooperative checkpoints and preserve cancellation through the person-helper fallback. The actual forward-match fixture reduces later work from 13 grabs/19 reads/41 matches to zero grabs/reads and two remaining matches in the current scale sweep. Complete uncancelled sample arrays remain equal. Actual Flask cancellation prevents publication and keeps deletion blocked until capture cleanup and lease release. The [report](execution/evidence/delivery/task-110-report.md) and [review](execution/evidence/delivery/task-110-review.md) retain full 419 tests at unchanged runtime bytes, final focused 25/actual Python 3.9 owning 168, rebuilt packaging/installed checks and the test-only portability corrections. No native interruption or wall-clock speed claim; combined C01 remains pending.

- [ ] **I:** Poll before acquisition, NCC sampling-loop work, each held append and successful return; propagate person-helper cancellation without generic fallback, and observe cancellation after helper/model resolution. Keep ordinary failure fallback, existing Vit checks and uncancelled defaults. Entry cancellation deliberately takes precedence over invalid/unreadable input, raising PipelineCancelled rather than returning an empty successful result.
- [ ] **V:** Reuse complete steady/loss sample arrays, real match/log/append cancellation gates and controlled helper boundaries. Preserve all uncancelled samples and exactly-once capture cleanup. A fixed three-scale sweep can finish its current sample before the next outer checkpoint; no further frame work follows observation.
- [ ] **V/D:** Actual Flask cancellation must preserve cancelled status/no publication, deletion refusal through cleanup, capture release before lease release and zero remaining owners/threads. Run relevant/full/build/floor checks. Report deterministic work avoided and exact checkpoints, with no general latency/native interrupt or inference-throughput claim.

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

### P11B — skip irrelevant early OCR history during tail extension

**What / why:** `merge_detections` currently restarts at the first OCR scan for each merged text region, even when earlier timestamps cannot support its tail. Actual full-module controlled histories of 10/50/100 unique ordinary email detections cause 64/1,324/5,149 timestamp visits. Repeated content is linear. This is final aggregation work, not a per-frame inference or preview slowdown.

**When:** A separate W2 performance PR after representative cost measurement, independent of P11A and optional modes. It is the smallest finalization candidate identified by S05; no removed preview cache is required.

- [ ] **E/S:** Retain the full-module work-count recipe and measure representative history sizes on identical inputs before/after. Separate controlled OCR-history input from real pretrained inference throughput; account for index construction and memory.
- [ ] **I:** Build one chronological timestamp index and begin each tail walk strictly after the existing `last_seen + .01` boundary without copying a full-history slice per region. Preserve duplicate timestamps, ordered support/stopping rules, confidence/box/fuzzy thresholds, bridge gaps and every Detection field. Nonchronological or unsupported timestamp input needs a semantics-preserving fallback.
- [ ] **V/D:** Verify complete before/after output equality, deterministic work bounds, chronological/repeated/duplicate/unordered inputs and relevant merge/scan regressions, full suite/build and a real synthetic report roundtrip. Describe measured finalization savings only. Contradiction-window indexing is a separate extension, unexercised by this baseline.

**Local completion:** P11B is independently reviewed at `952af20da205133886ba69799e134b86d1654137`. The [report](execution/evidence/delivery/task-112-report.md) and [review](execution/evidence/delivery/task-112-review.md) bind unchanged runtime bytes to semantic/base controls, actual controlled-OCR scan/report, package/default checks and both measured fixtures. The corrected 10,000-history/30-detection case lowers complete merge time from 12.272 to 3.384 ms, including index construction, with 85,176 bytes of list references. Original repeated-control regression and small-case variability remain explicit. This does not claim inference, all-finalization or whole-video acceleration; next combined acceptance remains separate.

### P11C — index eligible reverse-recall candidates

**What / why:** Forward PhiMemory is already indexed/batched, but `reverse_pass` still walks remembered keys for historical words. The controlled 10/50/100 unique-history probe records 155/3,775/15,050 visits; a benign unmatched token accounts for a quadratic component. This is post-scan reverse recall.

**When:** Separate W2 investigation/PR after P11B or independently when a safe equivalence contract and representative benefit are demonstrated. Do not bundle it with a timestamp-only optimization.

The [source contract research](execution/evidence/research/scan-index-contract-research.md) proposes a local index rebuilt from actual memory insertion order: numeric keys at the same length; nonnumeric keys within ±2 lengths merged by original insertion serial. Keep the existing predicate authoritative, including first eligible fuzzy match before a later exact key. Do not reuse forward recall or persistent caches with different semantics. Construction is O(M) retained references; same-length and early-winner histories remain explicit cost controls. No generic hook-purity or plugin-dispatch framework is required.

- [x] **E/S/I:** Preserve reverse pass's lower lenient thresholds, numeric same-length/two-digit tolerance, name-sighting gates, category/allowlist filtering and first eligible insertion-order match. Reusing forward recall unchanged is not equivalent. Identify a bounded candidate index that preserves those semantics before implementation.
- [x] **V/D:** Compare every resulting detection and order, including unmatched words, ambiguous eligible keys, numeric/name cases and filtering. Measure index construction plus lookup work on fixed histories, run relevant/full tests and build. Leave the candidate open or close without code if meaningful benefit cannot be established safely.

**Local completion:** P11C is independently reviewed at `9d888708d08cccf6e5f0ec8c9cf81740d3868fa1`. The [report](execution/evidence/delivery/task-113-report.md) and [review](execution/evidence/delivery/task-113-review.md) preserve both complete comparisons, priority/output/error compatibility and actual controlled-OCR scan/report/package checks. The final heterogeneous reverse-plus-merge median is 51.924→9.248 ms, while repeated input costs an additional 0.166 ms (+6.0%) and the initial same-length regression remains disclosed. O(M) storage, same-length worst-case work and all-finalization/inference/platform limits remain explicit; combined acceptance is separate.

### P11D — reduce irrelevant merge candidate visits

**What / why:** Distinct text regions leave a growing `mergeable` list. The same controlled 10/50/100 unique histories visit 55/1,275/5,050 prior candidates, separate from the tail-history and reverse-pass work.

**When:** A later separate W2 candidate because candidate ordering and geometric verification make this riskier than skipping timestamps. Source/work-count evidence alone is not a shipped improvement.

The same source research rules out category-only indexing as a fix for the demonstrated all-email traversal; it leaves those candidate counts unchanged, and existing code already skips cross-category geometry calls. A dynamic spatial candidate filter remains conditional. Preserve newest region-birth priority (not latest observation), inclusive12px box slack, growing union boxes, actual input-object mutations and callback order. Partial-ratio/empty-text bypass makes naive exact-text or length pruning unsafe. Include maintenance, prefix traversal and order-restoration cost before adopting any index; do not add category scaffolding for an unproven later optimization.

- [x] **E/S:** Measure realistic distinct-region workloads and identify an index that retains reverse candidate priority, overlapping-box/union behavior and visual long-gap verification. An arbitrary age cutoff would drop intentionally mergeable verified gaps and is not acceptable.
- [x] **I/V/D — closed without code:** The proposed sorted-left index passed 40 bounded complete-module controls but failed all eight total-cost cases. No runtime change was adopted. Complete measurements, mutations/identities, memory costs and isolation limits are retained; conditional actual scan/source-frame/full/floor/package acceptance was not reached. Any new approach needs a new evidence gate.

**Local outcome:** Independent [review](execution/evidence/delivery/task-114-review.md) approves the [no-adoption decision](execution/evidence/delivery/task-114-report.md). Email-grid480 went from 26.820 to 37.257 ms despite fewer final predicate visits; every other declared case also regressed, and Python allocation peaks increased. Base/head remain `e21ebdf6e3ee46e6c65050dc956a9a3459152269` with no product diff. This closes the tested proposal, while the remaining merge-history cost stays documented. P11B/C adoption is unaffected.

The S05 probe also confirms the `a11a3926` preview-cache donor is removed-system-only. Actual tested callbacks append logs/update scalar progress/publish the current frame without walking growing history; sampled scan-loop calls stay fixed. This scoped result does not establish constant cost for every fuzzy-memory bucket or default inference workload. The [retained research](execution/evidence/research/scan-history-baseline-research.md) records the exact source, computational OCR stub, operation counts, output checks and untested cases.

## Review focus

Report identity can change without changing file size; warm and cold cache behavior differ; queues must release obsolete work; exact frame claims require actual pixels/PTS; report and source snapshots must expire with the job. Measure each at the owning task's V stage and again for combined changes in C01.
