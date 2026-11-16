# Upstream-focused OpenScrub extraction plan

**Detailed delivery documentation:** [Start here](upstream-delivery/README.md) for the researched task plans, what/why/when for every contribution, delivery dependencies, conversation decisions and PR-description evidence template. This outline remains the scope/donor reference; the detailed plans refine implementation and validation where the outline is less specific.

> **For agentic workers:** Use `superpowers:executing-plans` to implement approved tasks individually; use `superpowers:subagent-driven-development` only if that execution approach is selected. Checkboxes below describe future work, not completed implementation.

**Goal:** Replace the experimental fork as the working application with current upstream plus small, independently useful fixes; remove custom training and the expanded review workbench from that application.

**Architecture:** Start new feature branches from current upstream and selectively port behavior and regression tests. Preserve the existing integration branch as a reference. Keep optional lettering-only redaction in a separate downstream branch on top of the cleaned application. Retain plate-number search as a separate training-free feature; evaluate off-the-shelf pretrained boundary refinement without making it a prerequisite for cleanup. User-selected candidates become tracked targets over a chosen interval, with explicit loss/drift handling rather than isolated frame edits.

**Tech stack:** Existing Python 3.9+, Flask/embedded JavaScript, OpenCV, FFmpeg and ONNX inference. Existing pretrained YOLO, OCR and text-region models; additional published pretrained OCR/segmentation tools may be evaluated. No custom models, training, fine-tuning or training stack.

**Scope/spec:** The user's requests in this conversation, including pretrained inference and the later clarification that full/partial plate-number search must find plates on the ground or displayed on a wall without a detected car or plate. This is a proposed implementation plan, not approval to publish PRs, replace branches, or delete runtime data.

**Terminology:** **Upstream** always means [austinmabry/OpenScrub](https://github.com/austinmabry/OpenScrub), whose current main branch supplies the clean baseline. The user's **remote** means their fork, [tahv0/OpenScrub](https://github.com/tahv0/OpenScrub), currently configured locally as `origin`. `integration/all-prs` is the donor branch from that fork. These names do not imply changing Git remote configuration.

**Default and user priority:** Upstream's current behavior must stay the default. The proposed assistance workflow is an explicit option. When selected, its purpose is to reduce editing work and unnecessary blur: uncertain detections are suggestions, and extra boxes, excessive mask area and brief false-positive flashes count against success. The user does not want uncertainty to trigger more automatic coverage or an obligation to review every weak proposal. Aggressive Blur uncertain remains a separate choice. No automatic migration of existing jobs or change to upstream's default policy is implied.

**PR breakdown and preservation ledger:** [Upstream PR map](2026-11-16-upstream-pr-map.md) assigns focused contribution boundaries, maps all 28 donor commits referenced in issue #22, and specifies long/large-video measurements. Performance, reliability and generic UX fixes are primary deliverables. The optional assistance/search/masking work must not become a prerequisite for contributing them.

## Evidence and current state

Inspected on 2026-11-16:

- `integration/all-prs`: `b4d0c75f25d91510fe1692f901d11853dc7db005`.
- Current checkout: clean `develop`, pointing to the same commit. No need to switch branches for this assessment.
- Upstream `main`, verified through GitHub: `5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f`, engine version 1.0.96. Local `main` matches it.
- Common ancestor: `8d486c00432459e88a08a9b8026440c89b2cb375` (1.0.88).
- Since that ancestor, integration adds 45,836 lines and removes 708 across 174 files; 500 commits are integration-only by ancestry. Upstream has 18 commits not in integration by ancestry. Some changes are equivalent or superseded, so these counts are not counts of unique features.
- Direct comparison with current upstream changes 177 files, with 45,908 insertions and 2,084 deletions. Copying the integration versions of shared files would lose newer upstream behavior.

Read both issues and all their comments:

- [#21: maintainer's scope and reservations](https://github.com/austinmabry/OpenScrub/issues/21).
- [#22: findings inventory](https://github.com/austinmabry/OpenScrub/issues/22).
- [#22: confirmed upstream fixes and requested next steps](https://github.com/austinmabry/OpenScrub/issues/22#issuecomment-6903629797).

The maintainer welcomes separate PRs for Save As, explicit review decisions, four-corner masks, and Stop & Review without the new review database. Large-report saves and long-4K thumbnail costs need upstream reproductions. The custom review conflict recovery, journal and off-frame repair system are not requested upstream.

This assessment inspected history, implementation, packaging, tests and recorded evidence. Follow-up research added [source-isolated upstream report probes](upstream-delivery/decisions-and-research.md#r06--actual-source-isolated-report-probes), showing interrupted-write, overlapping-save and manual-replay behavior, with a minimal-report baseline. It did not run the full application suite, GPU inference or footage benchmarks. Historical fork test counts/timings and the new isolated timings are not validation of a future extraction.

## Scope and constraints

1. Preserve upstream's scan → human review → render flow, manual box editing, model registry, ordinary inference, CPU/Intel/NVIDIA support, and existing privacy defaults. “Remove my review system” is interpreted as removing the added workbench, not upstream review itself.
2. Remove custom model creation, fine-tuning, training datasets, saved learned-model management, secondary learned checkers, correction-driven rescans, and their UI/API/packaging dependencies.
3. Remove the persistent Findings library, custom classification/crop infrastructure, similarity grouping, SQLite review journal/index and source-repair workflow. **Keep plate-number OCR/search**, decoupled from those systems. A small improvement to upstream's existing controls does not require retaining that architecture.
4. Prefer upstream's existing pretrained models; evaluate published pretrained tools for OCR and automatic boundary refinement where they add value. Do not create, train or fine-tune a model. Exporting an existing checkpoint to an inference format does not train it, but still requires reproducible conversion and numerical checks. No extra training dependencies in the app.
5. Preserve both requested tighter-mask ideas where the existing models support them, but keep their limitations explicit:
   - The three registered YOLOv9 exports provide bounding boxes and scores. They do not provide plate corners or letter masks.
   - Tighter **whole-plate** quadrilaterals can use YOLO detection plus manual geometry editing initially. Automatic refinement requires a separate pretrained segmentation tool or classical image processing; it is not supplied by the current YOLO exports. Evaluate it independently as Task 7b. Box tracking must not be presented as corner tracking.
   - Automatic **lettering-only** mode already uses YOLO localization plus PP-OCRv5 text-region detection (`TextRegionDetector.find_plate`), without recognizing plate characters. The user permits this existing pretrained detector.
   - Lettering-only is a downstream option, not an upstream candidate under the maintainer's stated policy. Fallbacks address localization uncertainty; they do not resolve his concern about recoverable character geometry. Full-plate coverage remains the default.
6. Keep report extensions additive, Python >=3.9 compatibility, current upstream security/privacy fixes, and existing face-redaction margins. No blanket reduction of padding across categories.
7. New caches belong to the job and follow its deletion, retention and vault lifecycle. Do not recreate a permanent collection of unredacted crops.
8. Removing code is separate from deleting existing videos, jobs, datasets, weights, volumes or logs. Do not delete those as part of extraction.
9. Use small synthetic fixtures and actual behavior tests. No real personal footage, screenshots, model artifacts or experiment histories in upstream PRs.
10. Preserve upstream release/version ownership. Avoid the fork's conflicting `1.0.89`; any downstream build identifier must be distinct and compatible with the updater.
11. Plate-number search must have an independent whole-frame text detection/recognition path. Neither a vehicle detection nor a YOLO plate detection may gate that path. Ground, wall/display, rotated and partly obscured plates are required evaluation cases. Exact-number matches, explicit fragment matches and uncertain OCR readings must remain distinct.
12. Search is an opt-in local feature with job-scoped data. It must not silently suppress plates that fail OCR or do not match a query. Upstream acceptance is unresolved: #21 raises concerns about reading plate numbers as well as retaining them, so removing training alone does not establish acceptance.
13. Add an optional confidence-based assistance policy: a detection/candidate floor, a separate adjustable automatic-blur threshold, and two ways to handle retained uncertain candidates. **Review uncertain** leaves them unblurred as suggestions the user can act on; it must reduce unwanted automatic work rather than create a mandatory review queue. Automatic blur also needs usable geometry and temporal support, not just a high score on one frame. **Blur uncertain** favors additional coverage and accepts false positives, including brief blur flashes. Explicit human choices override either policy. Keep upstream's existing behavior when the option is not selected; neither policy replaces that default. Scores from detection, OCR and segmentation remain separate rather than being presented as one calibrated probability.
14. In the optional assistance workflow, manual selection/correction must support tracking a plate, text region or arbitrary object forward and backward from the exact inspected frame over a chosen interval, including when no detector knows that object. Keep identity/output intent separate from per-frame geometry reliability. On loss/drift, stop applying unsupported masks and mark the gap for optional correction; do not automatically widen, freeze or jump to another object. Preserve the chosen target and offer correction, trimming or an explicit broader region. Gap status remains visible and saved; it does not create a new compulsory export gate in this workflow. Existing upstream behavior stays unchanged when the option is off.
15. Account for every relevant long/large-video performance improvement, bug fix and generic UX change in the PR ledger. Assign a proposed PR, already-upstream, downstream-only, removed-system-only or needs-investigation disposition with a reason. Split useful behavior out of mixed commits; do not discard it solely because the donor also touches the workbench. Complete the remaining history/file inventory before cutover, with unresolved applicability explicitly recorded.
16. Improve structure locally when justified by the work. Follow the PR map's placement rules: new tests under `tests/`, measurements under upstream's existing `benchmark/`, developer utilities under `tools/`, and substantial new runtime helpers under one proposed private namespace, `openscrub_internal/`. Keep small one-owner helpers in their existing component. Preserve entry points, avoid mass moves/formatting and speculative layers, and include packaging/test-discovery changes with each extraction. Donor root paths in this document describe the old branch, not a requirement to recreate that layout.

## Approach

**Recommended: extract onto current upstream.** The old branch is a donor library, not a merge source. Small early commits can sometimes be cherry-picked with conflicts resolved against upstream; later combined commits need selective reimplementation. Each PR includes its own tests and concise relevant documentation.

**Alternative: remove features in place.** This preserves the integrated history but requires untangling thousands of lines in `openscrub_web.py`, packaging and report handling, while also incorporating upstream fixes. It produces a much larger review and makes omitted dependencies harder to detect. Use only if preserving that branch's identity becomes a requirement.

Suggested branch layout during execution:

- An archive ref for the exact integration snapshot, retaining the original branch until the replacement is accepted.
- `upstream/<topic>` branches based directly on upstream `main`, or on a clearly declared small dependency.
- `integration/upstream-focused` to test the selected changes together, never as a monolithic upstream PR.
- `optional/lettering-only` on the cleaned integration for the requested downstream mode.
- A separate plate-search feature branch, retained downstream unless upstream accepts its opt-in behavior; a boundary-refinement research branch until quality/runtime evidence warrants a production feature.

Planning documents stay local/in the fork's planning history; do not include them in functional upstream PRs.

## Inventory: preserve, extract, exclude

| Area | Decision | Evidence / donor | Extraction boundary |
| --- | --- | --- | --- |
| OCR-memory slowdown | Already upstream; keep upstream version | `eed37e6` and follow-up `1f01433` | Upstream batches fuzzy matches; do not restore the older per-item loop. |
| OCR punctuation and localized text changes | Already upstream; keep upstream version | `a0b50a5`, issue #22 response | Upstream normalization covers all OCR engines and transcripts, more broadly than the fork's Tesseract-only change. Do not cherry-pick the originally double-escaped `d6e9efc5`. |
| Queue freeze, plate-threshold setting, later privacy fixes | Preserve current upstream | `4f863f3`, `c276e07`, `f2573f2`, `9f71cd2` | Do not replace the newer worker, option sanitization, regex validation or close-up face margins. |
| Streaming Save As | Extract first | `2900930f` | `export_filenames`, streaming browser picker, direct-download fallback; independent of training/review additions. |
| Clear Blur / Keep visible controls | Extract small upstream UI change | `39b4ed83` | Idempotent actions, visible current state, accessible controls, existing groups. No findings library or training labels. |
| View-only review filters and local filtering | Assess as a small independent upstream feature | `64afc3cc`, `c3a8c7a5`, `8209a82`, `a80a85d` | Type/output filtering without saving, refetching or losing drafts/hidden choices; keep upstream's default view. No training sampler, journal statuses or similarity system. |
| Adjustable automatic-blur confidence and uncertainty policy | Small new optional policy on existing review | Upstream `c276e07` supplies the detection floor; user requests manual handling or aggressive blur that permits flashes | Separate candidate retention from output decisions. Offer Review uncertain / Blur uncertain using the same candidates and tracker; preserve manual choices. |
| User-seeded target tracking and corrections | Required for the completed assisted workflow | Upstream `track_manual_region`, `job_track_object`, existing Track object UI; extend cautiously | Start from the selected frame, follow both directions, keep per-frame geometry and expose lost spans. Reuse pretrained VitTrack/template tracking for boxes; validate perspective/mask propagation separately. |
| Progress/log recovery and recent-rate ETA | Extract selected pieces | `08f432b6`, `0b2e3d1d`; `test_job_polling_*` | Drop learning counters and section UI from the donor. Bound requests/logs and prevent stale responses from changing another job. |
| Atomic live-preview publication | Extract as a bugfix | `90e67b6` / `5e967404`; `_publish_preview_jpeg` | Complete JPEG publication plus consistent HTTP snapshots, independent of corner saves. |
| Large-report saving | Reproduce on upstream, then extract minimal fix | `4fd88af9`, `stop_review.atomic_report` | Sparse edits, one report read/write, durable atomic publication. No journal/database. Upstream already accepts sparse `enabled` keys; frontend and write-path costs are the relevant candidates. |
| Slow/failed save and job-switch reliability | Reproduce and extract separately where applicable | `90e67b6`, `5e967404`, `test_release_reliability.py` | Preserve newer choices/drafts through failures, retries and switches; no false success. Separate from custom corner 409 recovery. |
| Thumbnail/report performance | Reproduce on upstream, then extract incrementally | `d15c69f`, `d265c34`, `d9e5d124`, `52274f32`, `5d55f8ea` | Bounded report caching and visible-thumbnail scheduling before new indexing/capture architecture. Establish exact frame/coordinate correctness first. |
| Scan-time crop cache / progressive scan overhead | Exclude fork-only implementation; retain an explicit investigation | `a11a3926` edits `finding_previews.py` only; cache subset of `0b2e3d1d` | Its known constant-cost optimization fixes a cache the fork introduced. Profile remaining upstream scan/preview costs before proposing code; do not recreate the removed cache just to optimize it. |
| Persistent diagnostics | Extract a reduced, privacy-conscious subset | `50e3816`, `openscrub_logging.py` | Runtime failures and bounded job activity; strip learning hooks and avoid persisting raw PII-bearing callback text. |
| Docker build speed / Windows GPU inference | Extract separately | `9f63f6e`, `36636c4`; `tests/test_docker_build_cache.py` | Build-context exclusions, pip caches, layer ordering, inference-only Compose and real provider checks. Do not import trainer overlays/dependency-image machinery wholesale. |
| Whole-plate four-corner masks | Later focused upstream feature | `617c9ac7`, early `test_plate_quad.py`, `5c0782f` | Minimal geometry editing in upstream review, additive reports, SDR/HDR fidelity; no example collection. |
| Automatic plate boundaries | Evaluate pretrained/classical candidates separately | EfficientViT-SAM, SAM 2, OpenCV; prior `research/precise-backend-candidates` results | Candidate masks from YOLO or OCR-discovered regions; no custom training and no claim that generic segmentation reliably finds every plate boundary. |
| Known full/partial plate-number search | Retain and decouple | `plate_text_hints.py`, `plate_text_web.py`, `plate_text_subprocess.py` | Keep existing training-free OCR/matching; replace learning/report/gallery dependencies. Whole-frame OCR must work without YOLO hits and support explicit fragments. |
| General mask/review fidelity | Retain useful subset with geometry work | `8697c28`, `539432c`, `a056dff`, `c79cb29`, `4a6675f`, `e15c5eb`, `98c3231`, `77755f0` | Shared render/review coverage, correct frame alignment, safe edit behavior. Compound holes/disconnected shapes require a separate demonstrated use case; not a mandatory new subsystem. |
| Lettering-only masks and guard optimization | Preserve on optional downstream branch | `1fe4e34`, `a6419cc`; `docs/narrow-performance.md` | Existing pretrained text detector, per-frame masks, fallback behavior; no training/review workbench. Historical guard speedups are not whole-video speedups. |
| Stop & Review / resume | Later standalone upstream feature | `72efeb02`, `ffb4ed9e`, `stop_review.py` | Checkpoint + original review + resume; no learned checker, journal, findings, sections or training. |
| Confirm plate / Not a plate | Optional later proposal, not a core dependency | `a3520d7e` and issue #21 | If wanted, retain only a job-local human label; output choice stays distinct. No permanent examples or implied training. |
| Approved sections / section rescans | Exclude from first cleaned application | `video_sections.py`, `section_workflow.py`, `08f432b6` | Larger workflow, much of it tied to learned rescans. Upstream's existing detection windows, trimming and audio controls stay. |
| Custom training/review recovery/performance | Exclude only behavior specific to removed systems | Feature-specific hunks from later integration merges | Mixed commits still need a generic-fix assessment. Keep every applicable improvement in its own PR entry. |

### Modules and assets absent from the clean application

Do not copy these from integration:

- `video_learning.py`, `learning_session.py`, `learning_candidates.py`, `learned_models.py`, `plate_verifier.py`.
- `confirmed_findings.py`, `findings_training.py`, `findings_web.py`, `findings_ui.py`, `review_similarity_ui.py`.
- `review_journal.py`, `review_preview_index.py`, and the current expanded `finding_previews.py`.
- `video_sections.py`, `section_workflow.py` in the initial scope.
- `requirements.training.txt`, `scripts/train_plate_seg.py`, `scripts/prepare_plate_dataset.py`, `scripts/download_training_checkpoint.py`, `compose.windows-training.yml`, and their package entry points.
- Learning/model/Findings/review-journal/section-only tests, workflows and manuals. Retain only extracted behavioral regressions with simplified fixtures.
- The extra generated `Dockerfile.cuda.inference`, inference-preview/audit/shared-training architecture and wrapper machinery as a bundle. Upstream is already an inference application; port independently justified build fixes instead of maintaining two inference images.

Do not copy the entire integration `openscrub.py`, `openscrub_web.py`, `pyproject.toml`, Dockerfiles, README or test suite. Those are the principal coupling points.

**Retain/refactor rather than delete:** `plate_text_hints.py` is already a Tesseract/OpenCV inference-and-matching module without training imports. `plate_text_web.py` and `plate_text_subprocess.py` currently import learning helpers, sections and custom preview infrastructure; replace those orchestration dependencies. Preserve applicable source validation, cancellation, bounded subprocess and failure-recovery behavior without retaining the learning modules.

## Delivery sequence and acceptance criteria

Task numbers group implementation work; the [PR map](2026-11-16-upstream-pr-map.md) defines submission boundaries. Start long/large-video baseline reproductions alongside the first small fixes. Confirmed performance and reliability fixes can ship independently of the optional feature work; they do not wait for Task 2a or Tasks 7a–7c. Task 7c's seeded tracking/loss handling is required before presenting the optional features as a complete select-once-and-follow workflow. Task 7b's automatic segmentation remains optional; validated box tracking and manual geometry correction must work without it.

### 0. Establish the clean baseline and protect existing work

**Files/state:** Git refs/worktree, upstream checkout; no application changes.

- [ ] Refresh the upstream SHA at execution time and record it alongside the donor SHA above. Create an archive ref and a separate worktree from upstream; leave the original integration branch available.
- [ ] Run the upstream contribution checks: `python -m pytest test_openscrub.py -q` and `python -m build`. Record existing failures separately rather than attributing them to extracted patches.
- [ ] Use a separate test data root. Do not automatically rehydrate experimental jobs into the clean app: ignored training/geometry fields or previously suppressed detections can change redaction meaning. Preserve old jobs/outputs in the old environment; rescan originals or explicitly validate a migration on copies.
- [ ] Reconcile all remaining integration-only history and changed production files into the existing PR ledger, recording donor/follow-ups, upstream applicability, disposition, dependencies and validation for each feature/fix family. Track non-ancestor early donors and unmerged experiments accurately; no blanket cherry-pick of merge commits. Prepare the long/large-video baseline cases from the PR map without requiring the optional features.

**Done when:** the current upstream app runs independently of every excluded module and old runtime data is untouched.

### 1. Streaming Save As

**Files:** `openscrub_web.py`, `README.md`; new `tests/test_export_save_as.py`, with the tests from `2900930f` adapted to upstream.

**Interfaces:** `export_filenames(job) -> (video_name, report_name)`, additive `job_public` fields, `saveExportAs(kind, btn)`; retain existing download/report routes.

- [ ] Add regressions for actual MP4/MKV suffixes, report filename, picker cancellation causing no download, streaming rather than `blob()` buffering, and direct-download fallback.
- [ ] Port the small feature; capture the selected job before awaiting picker/network work so a job switch cannot change the export target.
- [ ] Include a progress bar and bytes written / total in this first PR, with elapsed time and estimated time remaining when meaningful. Count completed destination writes, preserve streaming, show waiting/finalizing states and mark success only after close. Follow [P01's detailed progress contract](upstream-delivery/01-core-ux-and-reliability.md#p01--streaming-save-as), including unknown-total, failed-write and browser-download fallback tests.
- [ ] Verify failed/locked downloads never display success, and browser fallback works without the picker API. Run `python -m pytest test_openscrub.py tests/test_export_save_as.py -q`, build and exercise the browser.
- [ ] Commit one self-contained feature, preserving donor attribution.

### 2. Make original review choices unambiguous

**Files:** `openscrub_web.py`; new `tests/test_review_choices.py`, derived from `39b4ed83`.

**Interface:** Keep upstream's `enabled` decisions and existing grouped-member propagation. Use explicit setters instead of toggles; no new persistence model.

- [ ] Add regressions for repeated Blur/Keep clicks, bulk choices, zone-dropped detections, existing person/track grouping, and keyboard/pressed-state behavior.
- [ ] Port action/current-state wording and idempotent controls into upstream's existing cards. Do not add training classifications or custom gallery filters.
- [ ] Verify save/reopen/render retains choices; run the upstream suite plus `tests/test_review_choices.py`, build and browser checks.
- [ ] Commit separately from Save As.

### 2a. Separate candidate confidence from automatic blur and choose uncertainty handling

**Files:** `zones_ui.py`, `openscrub_web.py`, narrowly scoped report/render checks in `openscrub.py`, relevant docs; new `tests/test_plate_confidence_policy.py` plus browser cases in `tests/test_review_choices.py`.

**Upstream scope:** This is a separate proposed option. Upstream's contribution guidance prioritizes conservative redaction and human review, so unchanged defaults alone do not establish acceptance. Keep it downstream unless Austin accepts the scope; generic fixes and their PRs remain independent.

**Existing upstream behavior:** [commit `c276e07`](https://github.com/austinmabry/OpenScrub/commit/c276e07290cbed50bfa4ce16b57ee9272e5c348f) adds Advanced → Plate threshold, default `0.35`, web range `0.05–0.95`, step `0.05`. This controls which YOLO detections survive at all; raising it can remove candidates before manual review. It is not a separate automatic-blur confidence setting.

**Proposed optional behavior:** Keep upstream's current behavior selected by default. Only on explicit selection, use a lower candidate floor and a separate automatic-blur cutoff greater than or equal to that floor. Add an optional per-job `uncertain_policy` with values `manual_review` (**Review uncertain**, the user's preferred assistance behavior) and `blur_candidates` (**Blur uncertain**, an aggressive alternative). An absent policy means the existing upstream path, including for old reports and unchanged CLI commands. These are output policies over the same candidates and tracking, not separate inference pipelines. Returning to upstream behavior must also be possible; neither opt-in policy silently becomes the application default.

Example only, not calibrated settings: candidate floor `0.35`, auto cutoff `0.80`:

| Candidate or target state | Review uncertain | Blur uncertain |
| --- | --- | --- |
| Eligible plate score at least `0.80`, usable current-frame region and supported continuity | Automatically blur | Automatically blur |
| Isolated detection with no supported continuity, even if its score is high | Retain as a suggestion; do not create an automatic flash | May blur its usable current-frame region |
| Eligible plate score `0.35` to below `0.80`, usable current-frame region | Retain unblurred as an optional suggestion | Automatically blur; a short false-positive flash is an accepted tradeoff |
| Score below `0.35` | Not retained by this detector; manual selection/OCR discovery remain available | Same; the policy cannot recover discarded detections |
| Explicit human Blur/Keep choice | Honor the choice for its reviewed segment | Honor the same choice |
| Lost target with no supported current location | Stop unsupported masks and mark the gap for correction | Still mark the gap; blurring an old position does not establish coverage |

An unhandled suggestion is not an explicit Keep decision and does not require an individual dismissal before export. Policy-generated blur is not human confirmation that the candidate is a plate. OCR-only/fragment search matches still require target selection; this switch does not automatically redact every matching piece of scene text. “Review uncertain” names an available action, not a compulsory workflow.

- [ ] Validate finite thresholds, `0.05 <= candidate_floor <= auto_cutoff <= 0.95`, boundary equality, policy enum and invalid input. Store settings and explicit policy selection in report provenance; reuse upstream's `plate_threshold` as the candidate floor, not a duplicate detector control. Test that fresh jobs, old reports and CLI commands without the option use unchanged upstream defaults.
- [ ] Retain uncertain detections with their evidence and decision provenance. In Review uncertain, provide a suggestions count/navigation and optional dashed overlays distinct from actual blur; keep clean preview free of suggestion boxes. Group supported sightings of the same candidate so dismissing one segment does not require repeated clicks on each frame. In Blur uncertain, show actual policy-applied blur while leaving candidates manually rejectable and distinguishable from human-confirmed targets.
- [ ] Allow export of the selected assistance policy's output with unhandled suggestions or tracking gaps; preserve their status in the report and expose a concise, nonblocking summary in the existing UI. Do not add per-candidate confirmations, a compulsory review queue, automatic “Blur remaining” or a new export gate. Keep web/CLI decisions and previews consistent. A rendered file is not a claim that all candidates were reviewed or every target was covered.
- [ ] For Review uncertain, combine the selected auto cutoff with validated geometry and temporal association before starting automatic blur. Retain isolated spikes as suggestions, including brief real plates; do not claim the rule eliminates all false positives. Continue a selected/established target through score fluctuations only while tracking supports its position. Validate continuity rules on fixed clips; do not smooth flicker by enlarging masks or holding stale boxes.
- [ ] Human Blur/Keep decisions take precedence over policy/threshold changes or refreshed OCR. Switching policies recomputes only undecided automatic output and preview, without requiring a rescan or overwriting human choices. Lowering the candidate floor requires rescanning because discarded detections are unavailable. Reopening a job must preserve its policy and decisions.
- [ ] In Blur uncertain, permit isolated current-frame candidate masks rather than deleting them solely for short duration; brief real appearances and false-positive flashes are both possible. If narrow geometry fails but a usable full-plate box exists, use that broader region. Do not invent a location, copy stale corners or freeze a lost track indefinitely. Any temporal smoothing must respect source-frame motion, cuts and explicit Keep choices.
- [ ] Let the user select a candidate or draw a missed region and start Task 7c's tracking from that exact frame. Apply Blur/Keep to the reviewed target segment, not merely the thumbnail row. Confirming identity does not clear weak/lost geometry spans or merge later ambiguous appearances automatically.
- [ ] Do not combine YOLO score, OCR confidence, text-match strength and segmentation score into one percentage. Partial-text/OCR-only search results default to pending even if one component has a high score. Geometrically invalid or mismatched-frame refinements never become automatic just because the detector score is high.
- [ ] Test short low- and high-confidence isolated sightings: unblurred suggestions in Review uncertain, eligible for blur in Blur uncertain. Also test a short real plate remaining selectable, mixed-confidence grouped sightings, a manually rejected high-score false positive, policy switching/reopening and a lost track that remains marked without stale masks. Verify export does not require individually dismissing unhandled suggestions.
- [ ] Run the upstream suite, `tests/test_plate_confidence_policy.py` and affected browser checks. Verify unchanged default behavior, explicit opt-in and agreement between actual rendered frames, preview and saved policy. On fixed synthetic/non-personal clips, compare unnecessary blurred area over time, false-positive flashes, missed targets and manual corrections/actions against upstream; the assistance mode must demonstrate reduced editing work, not just a different confidence percentage.

### 2b. Keep useful view-only filters without the workbench

**Files:** `openscrub_web.py`; new `tests/test_review_view_filters.py`; concise existing review documentation. PR-map P15 is independent of Task 2a.

**Interfaces:** Existing category/group metadata and `enabled` output choices. Filters change visibility only; they do not create training labels, save the report or add a new review-state database.

- [ ] Assess upstream's current controls and extract only useful missing type/output filters from `64afc3cc` and relevant draft/lazy-loading behavior from `c3a8c7a5`. Keep Show all as the default; expose only statuses the clean application actually has.
- [ ] Use local metadata for view changes. Preserve hidden choices, unsaved edits and group membership without timed save/refetch cycles; bound thumbnail work for the resulting visible cards. No learning sampler or similarity grouping.
- [ ] Test filter combinations, bulk-action scope, empty results, pending edits and job switches. Run upstream tests plus `tests/test_review_view_filters.py`, browser checks and build; propose this separately from output-choice controls and assistance policy.

### 3. Recover progress polling and truthful recent ETA

**Files:** `openscrub_web.py`; adapted `tests/test_job_polling_node.py`, `tests/test_job_polling_browser.py`; new `tests/test_scan_eta.py`.

**Interfaces:** Existing job/log endpoints, `openJob`, `refresh`, `WebCallbacks.progress`; additive activity/preview metadata only where needed.

- [ ] Reproduce stale job-switch responses, suspended-tab recovery, a request body that ignores abort, log-cursor reset, and overlapping polling on upstream with controlled response delays.
- [ ] Extract request deadlines, view-generation checks, bounded log catch-up and lifecycle wake handling. Keep scan/post/render states only.
- [ ] Separately extract recent-rate ETA: fake-clock tests for startup, slowdown, stage transitions, no progress, completion and bounded sample history. Do not carry training telemetry or require the logging module.
- [ ] Run `python -m pytest test_openscrub.py tests/test_job_polling_node.py tests/test_job_polling_browser.py tests/test_scan_eta.py -q` with Node/browser prerequisites installed; build and test background-tab/job-switch behavior.
- [ ] Prefer two small commits/PRs if polling and ETA remain independent.

### 4. Fix concurrent live-preview responses

**Files:** `openscrub_web.py`; new `tests/test_live_preview.py`, using only the preview regressions from `test_review_save_confirmation.py`.

**Interface:** `_publish_preview_jpeg(path, image, quality) -> bool`, `WebCallbacks.scan_frame`, existing `job_preview` route.

- [ ] Reproduce a preview being replaced while an HTTP reader is consuming it; check JPEG integrity and agreement between Content-Length and response bytes using the production WSGI path.
- [ ] Publish through a temporary file and atomic replacement; serve a stable response snapshot. Preserve the prior preview when encoding/publication fails.
- [ ] Verify bounded memory and Windows replacement behavior; add revision-driven refresh only if it saves duplicate reads without stale display.
- [ ] Run the upstream suite and `tests/test_live_preview.py`, build, then commit the standalone bugfix.

### 5. Reproduce large-report saves and long-video thumbnail costs

**Files:** `openscrub_web.py`; focused `tests/test_large_report_io.py`, `tests/test_review_save_failures.py`, `tests/test_thumbnail_io.py` and browser cases as required by each PR; `benchmark/review_io.py`. Split test files by coherent behavior as they grow, not one file per minor patch.

**Interfaces:** Preserve current detection/save/thumb/frame endpoints and JSON compatibility. Keep a small `_write_job_report_atomic(path, document)` beside its sole caller initially; if checkpoints/search also need it, extract `openscrub_internal.reports.atomic_report(path, report)` in a focused commit and update callers together. Do not import the experimental review journal or make a leaf helper depend on web globals.

- [ ] Start with the baseline task, alongside small UX fixes. Generate synthetic upstream-format reports at 1k/10k/100k detections and an optional 250k stress case. Measure unchanged/sparse/bulk saves, response size, report I/O, peak memory and thumbnail time. Exclude custom training labels from the upstream workload. The fork's reported 20.5s/8.8s measurements are not upstream results.
- [ ] Reproduce partial/truncated writes under failure and lost-update behavior under concurrent saves. For a demonstrated save issue, port only bounded serialization, atomic durable publication and sparse changes; preserve manual/audio edits and allowlist suggestions. Confirm success only after persistence; do not acknowledge background work as saved.
- [ ] Use the detailed P06A/P06B/P06C split: atomic publication, complete transaction serialization and measured throughput are separate reviewable claims. The isolated probe establishes concrete failure cases, but full route tests remain required. Current upstream already parses/writes once and has no observed 15-second browser save deadline; do not transplant the fork's bottleneck explanation.
- [ ] Separately reproduce slow/failed-save UI behavior: a response lost after persistence, edits made during a save, retry, job switching and rendering. Preserve drafts/current choices and truthful status without the workbench's corner-conflict protocol; track P07 independently of server I/O optimization P06.
- [ ] Cover replay of manual additions as part of P07: the isolated upstream handler appends twice on an identical retry. A minimal additive stable-ID contract must preserve legitimate duplicate geometry and legacy-client compatibility; no journal/database.
- [ ] For decoding, use synthetic CFR and VFR/normalized clips with burned-in frame IDs and a long GOP. Measure cold versus warm requests near the beginning and end; assert returned pixels and overlay geometry correspond to the requested frame.
- [ ] Add bounded job-local report caching/thumbnail scheduling only if the reproduction justifies it. Invalidate on edits, reject stale writes, cap decoder concurrency, and test job deletion/vault behavior. Avoid a new SQLite index or full Findings cache.
- [ ] Preserve upstream's existing warm disk-thumbnail fast path, which does not parse the report. Measure/report cold-miss, listing, invalidation and DOM/request costs separately using the detailed performance plan.
- [ ] Treat report-read caching (P08), viewport/queue scheduling (P09), and exact/bounded decoding (P10) as separate PR candidates with their own before/after evidence. Include same-size atomic replacement, parallel requests, scroll jumps, source-frame identity and bounded retry; do not assume faster thumbnails are the correct thumbnails.
- [ ] Profile early/middle/late scan throughput and preview work for any remaining upstream history-dependent cost (P11). Keep upstream's improved PhiMemory implementation. Record the known fork-only `finding_previews.py` optimization as such; do not recreate that subsystem merely to port its speedup.
- [ ] Verify no-op requests avoid unnecessary rewrites, and decoder work does not block edits. Run the upstream suite plus the regression files relevant to each PR, the benchmark, build and affected browser/render tests.
- [ ] Prepare focused PRs P06–P11 only where upstream evidence supports them, with the PR map's measurements and platform limits. Record already-fixed/fork-only outcomes explicitly and keep unresolved cases visible. Performance fixes remain independent of new confidence/search/geometry features.

### 6. Preserve useful diagnostics and Docker improvements

These are independent work items, not one combined PR.

**Diagnostics files:** `openscrub_internal/diagnostics.py` extracted from the donor `openscrub_logging.py`, small hooks in `openscrub_web.py`, packaging, `docs/LOGGING.md`, adapted `tests/test_runtime_logging.py`. Introduce the private namespace only when this or another justified extraction needs it.

- [ ] Keep rotating runtime/error logs, job IDs/stages and bounded heartbeats; remove learning/subprocess-specific hooks. Review raw callback messages, exception paths and OCR content before making them persistent outside the vault.
- [ ] Test unwritable storage, redaction of sensitive values, bounded size, restart marker semantics and clean shutdown. Logging failure must not stop scanning. An unclean-exit marker must not claim an OOM diagnosis.

**Build files:** `.dockerignore`, `Dockerfile`, `Dockerfile.cuda`, `Dockerfile.intel`, applicable workflow, optional simplified Windows Compose/helper, `tools/check_cuda.py`, adapted `tests/test_docker_build_cache.py`.

- [ ] Port context exclusions and cache/layer-order changes. Preserve scheduled security refreshes; remove training-specific assertions and configuration.
- [ ] If retaining a Windows helper, use only CPU/CUDA inference overlays and test daemon/context/build handoff without depending on a pre-existing training image.
- [ ] Verify cold build, source-only rebuild and forced security refresh. Record which dependency layers were reused. Test startup and packaged imports for CPU/Intel/CUDA.
- [ ] Revalidate any ONNX Runtime pin against the actual base; do not assume the historical `1.20.2` pin remains the right compatibility choice. On NVIDIA hardware, execute the registered plate model and verify the provider actually runs inference; provider availability alone is insufficient.
- [ ] Run relevant tests, the upstream suite and build. Separate diagnostics, cache improvements and any GPU compatibility fix into independently reviewable commits.

### 6a. Extract generic preview/render fidelity fixes independently

**Files:** affected functions in `openscrub.py` / `openscrub_web.py`; new `tests/test_review_render_alignment.py` with synthetic clips. Corresponds to P16, which may become multiple independent bugfix PRs.

- [ ] Reproduce configured-padding, clipped-face ellipse, pending-edit, dense-track and frame/mask-readiness mismatches separately against upstream. Use the listed mask-fidelity donors as evidence; retain upstream's current face margins and identify already-fixed cases.
- [ ] Share a small rasterization/coordinate helper only where preview and render otherwise diverge. Keep it with its existing owner unless a coherent shared module is justified; do not import compound-mask or four-corner features to fix ordinary boxes/faces.
- [ ] Check preview pixels against real synthetic SDR/HDR output and test delayed/wrong-frame responses. Validate each fix on its declared upstream base, with the normal suite/build and relevant browser checks.

### 7. Tighter whole-plate geometry in upstream review

**Files:** `openscrub.py`, `openscrub_web.py`, `PLATES.md`; adapted `tests/test_plate_quad.py`, `tests/test_plate_quad_editor.py`; new `tests/test_plate_quad_render.py`.

**Interfaces:** Additive normalized `plate_quad` geometry bound to a specific source frame/box; preserve legacy `poly` reports. No `verified_label`, training crop or findings dependency is required for rendering a manually adjusted mask.

- [ ] Use the early four-corner renderer/editor as donor code, not the final full recovery UI. Start with a YOLO box; let the user adjust four corners within the existing editor.
- [ ] Share geometry between preview, report reload, SDR and HDR output. Test skew/rotation, out-of-frame/degenerate/nonfinite coordinates, legacy reports, padding and existing person/face masks. Preserve the default path's conservative full-box fallback. In Review uncertain, flag failed geometry and offer a broader region without applying it automatically; a failed edit must leave the last valid saved edit intact.
- [ ] Bind corrections to the inspected source frame and use Task 7c to propagate them with measured motion/geometry evidence. Do not copy one frame's relative corners across changing track frames. When precise propagation fails, follow the selected policy: known full-plate fallback in the default/aggressive path, a marked gap and optional correction in Review uncertain. A stale box is not evidence of the object's location. The original generic tracker provides boxes, not perspective-corner tracking.
- [ ] Inspect the unmerged source-frame-boundary work in fork PR #70 as design/test evidence only; do not present it as part of the inspected integration snapshot or import the workbench it depends on.
- [ ] Port only necessary shared rasterization/review-alignment helpers from the compound-mask work. Do not add occluder-hole features or claim automatic segmentation merely because the renderer supports polygons.
- [ ] Run geometry/editor/render tests plus the upstream suite, build, and actual synthetic SDR/HDR renders. Demonstrate the manual nature and temporal limits in the PR.

### 7a. Retain full/partial plate-number search without training

**Files:** refactor the donor `plate_text_hints.py`, `plate_text_web.py`, `plate_text_subprocess.py` into cohesive `openscrub_internal/plate_search/matching.py`, `jobs.py`, `worker.py`; small hooks in `openscrub_web.py`; adapted `tests/test_plate_text_hints.py`, `tests/test_plate_text_web.py`, `tests/test_plate_text_subprocess.py`; new `docs/PLATE_SEARCH.md`. Keep matching, orchestration and process supervision separate without importing web state or the removed Findings documentation/system.

**Interfaces:** Keep the pure `search_frame(frame_bgr, hints, regions=None, reader=None, cancelled=None)` concept. Separate OCR observations (text, polygon, OCR score, frame identity), query matches (full number/fragment/uncertain), and physical-boundary proposals. The search worker uses ordinary job progress/cancellation and atomic report I/O from Task 5, with no training, Findings or section imports. Search does not depend on automatic segmentation passing its evaluation.

- [ ] Add a fixture where both vehicle and plate detectors return zero detections but OCR sees a synthetic registration on a wall or the ground. Find it from whole-frame text alone. Include arbitrary rotation, perspective, 4K small text, two-line plates, multiple plates and short appearances.
- [ ] Provide explicit whole-number and fragment queries. Normalize case and presentation separators; distinguish equality from a query occurring inside a longer OCR string. Retain bounded partial evidence for incomplete readings of a full query, but label it as a possible match. Proposed baseline: at least three literal characters, no silent O/0 or I/1 substitution; very short fragments have an explicit limit rather than invented certainty.
- [ ] Fix the current donor restriction: `search_frame` rejects non-exact matches for `full_frame_text` and `text_contour`. Allow fragment/partial candidates in those paths without requiring a plate-shaped contour. Preserve text-line geometry and adjacency so matching never concatenates unrelated signs or words across the frame.
- [ ] Use two independent candidate sources: existing YOLO detections and whole-frame OCR/text polygons. Union and deduplicate by source-frame overlap, keeping provenance for both. Do not discard all non-YOLO text before matching.
- [ ] Prefer existing `OnnxOcrBackend`/PaddleOCR or Tesseract first. Preserve an adapter boundary for RapidOCR or optional `fast-plate-ocr` crop recognition. PP-OCR text detection alone cannot read numbers; it needs a recognizer. A crop recognizer alone cannot discover text elsewhere in the frame.
- [ ] Search a user-selected interval with bounded decode/inference concurrency and explicit sampled-frame coverage. Avoid mandatory 1280px whole-frame downscaling that makes small 4K text unreadable: evaluate overlapping tiles or full-resolution text detection with coordinate mapping. A negative sampled search is not evidence that the plate never appears.
- [ ] Replace `learning_session.verify_source`/telemetry and `video_learning` geometry helpers with small neutral equivalents; remove sections and Findings publication. Adapt process isolation without importing the web app's removed model stack. Test source changes, cancellation, resource limits, subprocess exit, concurrent report edits and unchanged reports on failure.
- [ ] Present candidate timestamps/text regions in the existing job/review flow, using Task 2a's pending decision state when that mode is enabled. Let a selected OCR result seed Task 7c's tracker without needing a car/plate detection. Adding redaction to an OCR-only/partial candidate must be an explicit user action and must cover the whole selected number/plate candidate, not just the matched fragment. No query or OCR failure may automatically disable another plate's redaction. Unknown physical boundaries remain explicitly unresolved.
- [ ] Keep queries, OCR results and transient crops local and job-scoped; exclude numbers from general logs and process arguments. Test vault locking, retention and job deletion. Do not create a persistent recognized-plate library.
- [ ] Run `python -m pytest test_openscrub.py tests/test_plate_text_hints.py tests/test_plate_text_web.py tests/test_plate_text_subprocess.py -q`, build and browser/end-to-end checks. Measure recall and false matches separately on held-out synthetic/non-personal detached-plate clips. Retain as an optional downstream feature until upstream explicitly accepts plate OCR.

### 7b. Evaluate automatic boundaries using published pretrained tools

**Research files:** isolated downstream `benchmark/experiments/pretrained_plate_refinement/` harness and fixtures; reuse old fixture definitions/results as comparison evidence. No production imports until a candidate earns them. If successful, propose a small `openscrub_internal/plate_boundary.py` inference adapter with per-frame geometry consumed by Task 7's renderer/editor.

- [ ] Freeze checkpoints, preprocessing, prompts and model-selection rules before comparing outputs. Start with existing OpenCV contour/quad proposals as a cheap baseline and one EfficientViT-SAM variant as the first new box-prompted candidate. Use SAM 2 as an alternative if its video capabilities justify the extra runtime cost. None requires our own training.
- [ ] For YOLO hits, supply a contextual crop and plate box. For OCR-only hits, search around the text polygon for a surrounding object boundary, then evaluate those proposals. A tight text box does not itself establish the outer plate; a segmenter may select only letters, a wall, or a frame around the plate.
- [ ] Measure whole-plate geometry and text-region geometry separately. Evaluate detached plates on ground/walls, skew, glare, blur, tiny plates, occlusion, disconnected fragments and changing frames. Count exposed identifier pixels and false masks as well as ordinary IoU and excess coverage. Never select masks using ground truth or treat the model's score as a correctness guarantee.
- [ ] Carry the previous EfficientSAM/Light HQ-SAM/GrabCut failure cases into the evaluation rather than rerunning them as unexplored solutions. Do not tune against those cases and describe the resulting score as held-out evidence.
- [ ] Measure crop latency, total video time, CPU/GPU memory and repeated-frame stability. Fit a quadrilateral only when it preserves the relevant boundary; do not force disconnected or occluded masks into a misleading rectangle. Mask propagation must be checked for drift, not equated with repeating the initial corners.
- [ ] Keep manual adjustment and a known-box fallback option when refinement fails. Apply it automatically only under the default/aggressive policy; Review uncertain offers correction or broader coverage without silently applying extra blur. With OCR-only evidence and no trustworthy plate outline, retain the complete text region as a suggestion; do not claim unseen/occluded parts of a plate are fully protected.
- [ ] Test the actual distributable inference path. EfficientViT-SAM offers ONNX export, but its example ONNX runner still imports Torch/TorchVision. Replacing that preprocessing with an equivalent NumPy/OpenCV adapter is engineering work, not a provided dependency-free package. SAM 2's official runtime also uses PyTorch/Python >=3.10. Preserve the core Python >=3.9 install, using an optional isolated inference adapter only if worthwhile; no trainer or dataset endpoints.
- [ ] If no pretrained candidate meets the quality/runtime bar, retain search and manual tighter masks and record the automatic-boundary feature as unsupported. Do not resolve that outcome by starting custom training.

### 7c. Track the target the user selects, with recoverable geometry loss

**Status:** Required for the completed assisted workflow, not an optional replacement for manual work and not a training feature.

**Files:** existing `openscrub.py::track_manual_region` and report/render helpers, `openscrub_web.py::job_track_object` and editor/timeline controls; new `tests/test_manual_target_tracking.py`, `tests/test_manual_target_tracking_browser.py`; relevant user documentation. Reuse existing track IDs and job reports rather than adding a Findings store or SQLite database.

**Verified baseline:** In upstream `5d3a15a`, `track_manual_region(video, box, t_ref, t0, t1, ...)` already follows a drawn region in both directions using pretrained `cv2.TrackerVit` when available, otherwise multi-scale template matching. The web route appends dense per-time boxes and groups them for review. It also supports a detector-driven person path. Generic tracking yields boxes, not plate corners or arbitrary masks. On weak/lost tracking the generic path can widen or freeze a box, emitting score-zero samples. That is a concrete mechanism for lingering blur, not a diagnosis of the user's footage.

**User flow:** opt into assistance → select an uncertain detection, OCR match or manually drawn region → choose Blur/Keep and a time interval → track backward/forward from the inspected frame → inspect the overlay and any gaps → optionally correct at a new frame or trim/split the target segment → regenerate only the affected span → render the chosen output. Unhandled suggestions and gaps remain available without becoming compulsory tasks.

- [ ] Accept an exact-frame seed from any candidate source or a manual box/quad. Keep the original source identity, seed frame, selected region, chosen interval and explicit output intent. If the decoder cannot return the seed frame, report the problem instead of initializing with the same coordinates on a different nearby frame.
- [ ] Reuse upstream's small pretrained VitTrack/template implementation as the box baseline; initialization and temporary image templates do not train model weights or create a reusable dataset. A plate/text seed must not be silently redirected to a person tracker just because a person overlaps it. Preserve upstream's existing person-aware behavior outside that explicit target path.
- [ ] Produce per-frame/per-sample positions linked to one target segment; keep detector, OCR, tracker and geometry-quality evidence distinct. An object can remain tracked when it is briefly unreadable or absent from YOLO results, provided visual continuity is supported. Do not require the queried text to be recognized on every frame.
- [ ] For planar plate/text quads, evaluate OpenCV feature tracking plus a robust perspective transform, with forward/backward consistency, sufficient well-distributed inliers and geometric validity checks. For arbitrary or changing silhouettes, evaluate pretrained SAM 2 propagation if Task 7b justifies it. Bounding-box motion alone does not prove shape accuracy; no fixed normalized quad stretched onto every future box.
- [ ] Record reliable, uncertain and lost intervals separately. Task 2a's policy controls uncertain candidate classification; it does not certify tracker positions. Blur uncertain may use a supported current-frame outer region when precise shape is uncertain, but weak/frozen samples alone are diagnostic proposals, not approved moving masks. Stop accepting propagation across scene cuts, implausible motion/scale changes or ambiguous object switches; expose the first failing frame on the timeline. Preserve existing upstream behavior outside this opt-in feature.
- [ ] In the opt-in assistance path, stop unsupported mask propagation when location is lost, visibly mark the interval and preserve the target/decision for correction or retracking. Offer trimming or an explicitly chosen broader region; do not freeze, enlarge or switch objects automatically. The user may leave the gap unhandled and export the actual chosen result, with gap status preserved rather than falsely marked covered. Neither Blur uncertain nor a bulk blur action establishes an unknown location. Leave upstream's current tracking/export behavior unchanged when assistance is off.
- [ ] Allow another user correction to add a source-frame keyframe and recompute the affected span without overwriting other explicit keyframes, output choices or completed work. Permit splitting and trimming a track. After occlusion or a cut, proposed reacquisition must pass continuity checks or be explicitly linked by the user; matching plate text alone does not prove spatial identity.
- [ ] Keep rejected false-positive segments rejected without repeatedly adding their same sightings, but do not propagate Keep to unrelated lookalikes or unverified later appearances. An object that changes from uncertain to human-confirmed remains subject to tracking-loss checks.
- [ ] Bound forward/backward decoding, cancellation and memory; checkpoint only job-owned tracking results if needed. Source/report changes invalidate pending publication. Reopen/re-render must preserve target identity, keyframes, unresolved intervals and decisions. Preserve exact source coordinates through normalization, scroll transforms and SDR/HDR output.
- [ ] Test a user-drawn target with zero YOLO detections, a detached plate during camera motion, changing scale/perspective, partial occlusion, brief unreadable text, two similar crossing objects, departure/reentry, hard cuts, lost lock/frozen samples, failed source-frame read, correction/retracking, cancellation and restart. Assert no silent ID switch, stale mask, automatic widening or falsely covered gap in assistance mode; verify optional correction and export with preserved unhandled-gap status. Compare actual synthetic rendered masks against moving target truth and retain unchanged upstream-default regressions.
- [ ] Run `python -m pytest test_openscrub.py tests/test_manual_target_tracking.py tests/test_manual_target_tracking_browser.py -q`, build and an end-to-end select → track → lose → correct → resume → render browser test. Publish measured box/quad/mask capabilities separately; unsupported shape tracking must remain explicit.

### 8. Optional lettering-only mode without training

**Branch:** `optional/lettering-only`; exclude it from upstream PR branches.

**Files:** `openscrub.py`, `openscrub_web.py`, `PLATES.md`; new `tests/test_narrow_plate.py`; adapt donor `tools/benchmark_narrow_guard.py` into `benchmark/narrow_guard.py` with concise relevant documentation.

**Interfaces:** `--plate-coverage full|narrow`, `--plate-narrow-margin`; `TextRegionDetector.find_plate(frame, box)` and `_narrow_from_probability(crop, prob)`; additive frame/mask metadata.

- [ ] Extract the existing narrow algorithm and one-pass component counting, reusing the selected YOLO model and pinned PP-OCRv5 detector. No model training, number recognition, Findings capture or learned checker.
- [ ] Preserve full mode as default, explicit nonnegative margin and exact frame alignment. Retain full-plate fallback on model/geometry/contrast uncertainty under the default/aggressive policy; when Review uncertain is explicitly selected, expose failed refinement as a gap/suggestion and offer the broader region without applying it automatically. No stale narrow mask on unobserved or interpolated frames.
- [ ] When a user selects/corrects a lettering region, use Task 7c's target identity and keyframes while refreshing text geometry per frame or using a validated transform. A tracked outer box is insufficient to certify lettering coverage; failed refinement follows the selected fallback policy, with uncertainty and actual output visible in preview.
- [ ] Keep the existing SDR-only limitation and VFR normalization requirement explicit until separately implemented and verified. Test missing/corrupt text models, multiple text rows, low contrast, motion, fallback padding and report reload.
- [ ] Adapt the guard benchmark so its documented reference is reproducible from the cleaned branch or explicitly names the archived donor ref. Preserve exact polygons/fallbacks when comparing optimized and baseline guards; do not carry an implicit dependency on inaccessible fork history.
- [ ] Run synthetic mask tests and actual pretrained inference on representative non-personal clips. Report whole-video cost, fallback frequency and missed coverage separately. The earlier evidence reported 11/12 difficult synthetic cases falling back: do not claim universal precision or performance.
- [ ] Document the unresolved recoverability concern from #21. Do not label lettering-only output equivalent to whole-plate anonymization or submit it as an already welcomed upstream feature.

### 9. Optional resumable scans as a separate feature

**Files:** `openscrub_internal/checkpoints.py` extracted from donor `stop_review.py`, shared `openscrub_internal/reports.py` only when reuse justifies it, small hooks in `openscrub.py` / `openscrub_web.py`, packaging, `docs/STOP_REVIEW.md`, adapted `tests/test_stop_review.py`.

**Interfaces:** `atomic_report`, `with_checkpoint`, `validate_resume`, `join_reports`; distinct stop/resume actions integrated with the current upstream worker.

- [ ] Start from the small checkpoint/report helpers, removing checker audit history and dependencies on sections, learning and custom review. Save ordinary review choices in the report.
- [ ] Test exact committed frame, persisted settings/source identity, restart, failed seek, overlap merging, remapped track IDs, audio/manual edits and unchanged reviewed prefix.
- [ ] Preserve upstream queue generations, cancellation/retry behavior and worker exception containment. A paused/incomplete scan cannot render or download as a fully redacted video.
- [ ] Run checkpoint/worker tests plus the upstream suite, build, and a real synthetic stop → review → restart → resume → render exercise. Submit only as its own later feature.

## Final verification and cutover

- [ ] Inspect each PR's diff against its declared upstream base. No unrelated version changes, experimental docs, runtime media, new training packages or removed-feature imports.
- [ ] Install the built wheel in a clean environment and start CLI/web without the excluded modules. Exercise scan, ordinary review, render, export, retry/cancel, retention and vault behavior.
- [ ] Run current upstream regression tests after each extraction, plus relevant browser/render checks. Re-run integrated checks once on the assembled clean branch; do not rely on the old integration CI or broad historical pass counts.
- [ ] Collect the new `tests/` cases as well as existing `test_openscrub.py`; validate new runtime packages in wheel/sdist, Docker, updater and Windows packaging as applicable. Verify clean source/installed CLI and web imports; no helper may depend circularly on web globals.
- [ ] Reconcile the PR ledger with the full donor history/file inventory before cutover. Every relevant performance/bug/UX candidate must have a disposition and reason; generic fixes must not depend on optional assistance, OCR or segmentation. Include baseline and before/after evidence for long/large-video claims.
- [ ] Check the cleaned production sources, packaging and workflows for imports/routes/configuration involving `learning_session`, `video_learning`, `learned_models`, `findings_training`, `findings_web`, `review_journal`, `OPENSCRUB_ENABLE_TRAINING` and `openscrub-training`. The refactored `openscrub_internal.plate_search` feature is allowed, but must import none of those removed systems. Distinguish ordinary/pretrained inference dependencies and historical text from active training functionality.
- [ ] Keep source/model caches and compatibility handling within upstream's privacy lifecycle. Existing experimental jobs require explicit migration validation or rescanning; do not silently reuse learned decisions as trusted upstream output.
- [ ] After the cleaned application is accepted, choose whether to replace the local working integration branch or keep the new name. Do not force-push/rewrite the old branch or delete old runtime datasets as an implicit cleanup step.
- [ ] Publish only separately requested/authorized PRs. Start **Save As**, **clear review choices** and independent **progress/preview reliability** alongside clean-upstream scale reproductions. Prepare each demonstrated long/large-video fix as its own PR using the PR map; optional features do not block this contribution work.

## Review focus

- Late responses after a job switch: covered by Task 3 generation/deadline tests.
- A successful-looking save that is not durable, or concurrent edits that disappear: covered by Task 5 failure/concurrency tests.
- Correct geometry on the wrong frame, including resumed/VFR footage: covered by Tasks 5, 7, 8 and 9 source/frame tests.
- New raw-data retention or training dependencies hidden inside a useful patch: covered by Tasks 0, 5, 6 and final packaging/lifecycle checks.
- Regression of newer upstream privacy defaults or misleading narrow-mode claims: covered by baseline/upstream-suite checks and Tasks 7–8 render/inference evidence.
- Detached plates with zero YOLO detections, partial text and uncertain boundaries: covered by Tasks 7a–7b; a failed OCR/refinement stage never disables existing redaction.
- Unwanted automatic boxes, flashes and review work: covered by Task 2a; assistance requires explicit selection, uncertain sightings remain optional suggestions, isolated high-score spikes do not directly create masks, and saved choices survive. Measure extra area, flashes and correction effort as well as missed targets.
- User-selected targets that rotate, disappear or cross another object: covered by Task 7c; per-frame geometry remains separate from identity confirmation, assistance marks lost spans without stale/widened masks or compulsory export gates, and the default upstream path remains unchanged.

## Pretrained-tool research supporting Tasks 7a–7b

Research date: 2026-11-16. These are source/documentation findings, not new inference benchmarks or a claim of tested accuracy on the user's footage.

| Tool | Useful role | Integration limits / recommendation |
| --- | --- | --- |
| Existing OpenScrub PaddleOCR/ONNX backend and Tesseract | Whole-frame text detection/recognition and query matching without a car detector | First baseline: already available, and the existing `plate_text_hints.py` core is training-free. Preserve polygon/crop coordinate transforms and evaluate small/rotated scene text. |
| [RapidOCR](https://github.com/RapidAI/RapidOCRDocs/blob/main/docs/quickstart.en.md) using pretrained PaddleOCR models | Local OCR returning text-line four-point boxes, recognized strings and scores; ONNX Runtime path | A reasonable alternative adapter if it improves usability/quality over the existing backend. Text-line boxes are not physical plate corners. Its [source/model licensing statement](https://github.com/RapidAI/RapidOCR/blob/main/README.md#%EF%B8%8F-license) distinguishes Apache-2.0 code and derived PaddleOCR weights. Pin a specific model/version rather than tracking defaults. |
| [fast-plate-ocr](https://github.com/ankandrew/fast-plate-ocr/blob/9ce7a5b64a939aa421c243b331d42e6bc25ffd44/README.md) | Pretrained ONNX recognition on plate crops, e.g. `cct-s-v2-global-model`; optional character confidence | `LicensePlateRecognizer.run` returns text/optional character probabilities, not masks. Can corroborate a YOLO or OCR-discovered crop; cannot replace whole-frame discovery. At inspected revision `9ce7a5b`, Python >=3.10 and `opencv-python-headless` are required; training is a separate extra. Avoid silently raising OpenScrub's floor or overwriting its CUDA OpenCV. The [author explicitly confirms MIT weights](https://github.com/ankandrew/fast-plate-ocr/issues/99#issuecomment-6303999259), resolving the initial README-only licensing uncertainty. |
| [FastALPR](https://github.com/ankandrew/fast-alpr/blob/c5a94706f175590b2bc09aa86f46182d4c267fae/README.md) | Reference composition of open-image-models YOLO detection and fast-plate-ocr | Useful reference, but importing its complete detection-gated pipeline would duplicate OpenScrub's detector and fail the independent OCR-discovery requirement. Prefer its OCR component if needed. |
| [OpenCV contour/shape routines](https://docs.opencv.org/4.13.0/d3/dc0/group__imgproc__shape.html) | Edge/contour proposals, polygon approximation and perspective geometry without a new model | Low-dependency baseline, not guaranteed semantic segmentation. Ground texture, framed wall displays and shadows can produce convincing wrong rectangles. The existing GrabCut evaluation already failed tougher visibility cases. |
| [EfficientViT-SAM](https://github.com/mit-han-lab/efficientvit/blob/de7d7733/applications/efficientvit_sam/README.md) | Published box-prompted segmentation weights with documented ONNX/TensorRT deployment | First new automatic-boundary candidate to screen. The official [model card](https://huggingface.co/mit-han-lab/efficientvit-sam) lists Apache-2.0 weights; its L0 variant has 34.8M parameters. Published GPU throughput is not evidence of this application's speed or plate accuracy. The [ONNX runner](https://github.com/mit-han-lab/efficientvit/blob/de7d7733/applications/efficientvit_sam/run_efficientvit_sam_onnx.py) supports box prompts but still uses Torch/TorchVision preprocessing/postprocessing. |
| [SAM 2 / SAM 2.1](https://github.com/facebookresearch/sam2) | Published image masks and prompted video-mask propagation | Alternative for changing boundaries over time; no fine-tuning is required to use checkpoints. Official docs specify Python >=3.10, Torch >=2.5.1 and TorchVision >=0.20.1, and license checkpoints under Apache-2.0. Heavier runtime; a candidate for evaluation, not a promise of plate-specific precision. |
| Upstream `track_manual_region` / pretrained VitTrack | Generic user-seeded box tracking forward and backward, already part of OpenScrub | Reuse rather than invent a new model system. Its weak/lost-position samples need explicit handling in the assisted workflow; boxes do not establish plate corners. |
| [OpenCV optical flow](https://docs.opencv.org/4.13.0/d4/dee/tutorial_optical_flow.html) and [feature-based homography](https://docs.opencv.org/4.13.0/d1/de0/tutorial_py_feature_homography.html) | Track image features and estimate planar perspective changes without training | Candidate for propagating a manually specified plate/text quadrilateral. Needs sufficient correct correspondences, robust outlier rejection and drift checks; it does not guarantee tracking under occlusion or discover arbitrary visible-object silhouettes. |

The [WPOD-NET paper](https://openaccess.thecvf.com/content_ECCV_2018/papers/Sergio_Silva_License_Plate_Detection_ECCV_2018_paper.pdf) and [IWPOD-NET implementation](https://github.com/claudiojung/iwpod-net) provide a relevant alternative for plate corners/rectification, but their described pipelines typically start from vehicle crops. They are not selected as the first approach for detached plates; a four-corner model also does not provide arbitrary visible fragments/occluder exclusions. No license or current-runtime compatibility conclusion was established for adopting those implementations.

Existing research in `origin/research/precise-backend-candidates` must remain visible in the decision: `experiments/precise_plate_masks/results_20261105/README.md` reports Light HQ-SAM missing an isolated visible fragment and failing an interior occluder, and classical GrabCut variants losing glyph pixels under stress. Earlier EfficientSAM evidence also recorded an interior-hole failure. These are historical measurements, not fresh tests, and they disqualify claims that adding any SAM-family model automatically solves precise plate masking.

**Recommended data flow when assistance is selected:** whole-frame OCR and YOLO run as independent discovery paths; their source-bound candidates feed literal/partial query matching and optional crop OCR; matched regions may feed a separate boundary refiner; original review lets the user accept/correct a target and seed bidirectional tracking over an interval; corrections can resolve lost/uncertain spans; rendering follows the selected policy and per-frame supported geometry, leaving unhandled suggestions/gaps visible as status rather than adding blur. OCR-only/manual discovery and box tracking remain usable when the shape refiner is absent or fails. No stage trains a model, collects a reusable dataset or disables another plate's redaction because a query did not match. The ordinary upstream workflow remains the default.
