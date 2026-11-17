# OpenScrub upstream PR map and preservation ledger

**Detailed execution/PR documentation:** [Delivery overview](upstream-delivery/README.md), [research and decisions](upstream-delivery/decisions-and-research.md) and [PR evidence template](upstream-delivery/pr-evidence-template.md). The task plans supply what, why, dependencies, validation and delivery-cycle timing for every P family, optional O task and baseline/cutover task.

This is the contribution breakdown for [the extraction plan](2026-11-16-upstream-extraction.md). **Upstream** is [austinmabry/OpenScrub](https://github.com/austinmabry/OpenScrub); the user's **remote** is [tahv0/OpenScrub](https://github.com/tahv0/OpenScrub), currently `origin`. The inspected integration snapshot is `b4d0c75f25d91510fe1692f901d11853dc7db005`; the inspected upstream baseline is `5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f`. Refresh the upstream baseline before submitting each candidate.

**Purpose:** Preserve every relevant performance improvement, bug fix and useful UX change while making independently reviewable contributions to Austin's repository. Long and large video handling is a primary deliverable, alongside the small UX changes. It must not wait for OCR search, segmentation research or the optional assistance workflow. Upstream's existing redaction defaults remain unchanged.

**Status:** Local implementation and independent review are in progress. The [execution record](upstream-delivery/execution/status.md) identifies completed isolated candidates, three reviewed intermediate integration batches, their actual application/browser/video evidence and remaining gates. Source investigations and proposed cards below are not implementation acceptance. The preserved donor/source inventory is recorded under [preservation and scale evidence](upstream-delivery/execution/status.md#preservation-and-scale-evidence). No PRs/issues have been published, and Austin has not accepted these local candidates merely because they pass review.

## Austin's requested contribution shape

- In [#21's response](https://github.com/austinmabry/OpenScrub/issues/21#issuecomment-6902779771), Austin asked for individual long-recording/4K issues with synthetic or non-personal reproductions, separate from the workbench.
- In [#22's response](https://github.com/austinmabry/OpenScrub/issues/22#issuecomment-6903629797), he specifically welcomed separate Save As, explicit review decisions, four-corner masks and Stop & Review PRs. He requested report sizes/timings for large saves and long-4K thumbnail decoding. The fork's 409/503 recovery, SQLite journal and off-frame redraw system need no upstream action now.
- PhiMemory and the two reported OCR privacy fixes already have upstream implementations. Preserve Austin's current versions; do not submit duplicate fixes or restore the earlier fork versions.
- Lettering-only masking and reading plate numbers have separate reservations in [#21](https://github.com/austinmabry/OpenScrub/issues/21). Keep those optional downstream features independent of every generic fix.
- Upstream's inspected `CONTRIBUTING.md` also prioritizes conservative redaction and human review. The optional assistance policy needs its own upstream scope discussion; preserving defaults does not establish that Austin will accept that option. It can remain downstream without blocking any generic PR.

## Preservation rule

Every candidate receives one disposition: **proposed PR**, **already upstream**, **downstream option**, **removed-system-only**, or **needs investigation**. Mixed commits are split by behavior, not discarded wholesale because they touch training/review code. Removal of the workbench is not a reason to lose a generic reliability improvement.

This ledger covers all 28 commit references in issue #22 plus additional identified history. It is not a claim that all 500 integration-only commits have received a fresh line-by-line audit. Before cutover, the baseline task must reconcile the remaining history and changed-file inventory against this ledger; unresolved candidates stay visible as needs investigation.

For each candidate, record donor SHA and follow-ups, affected upstream path, reproduction/feature scenario, disposition and reason, proposed PR ID, dependencies, exact upstream SHA tested, validation results and any platform limitations. Track the behavior separately from whether the named donor SHA is an ancestor: early features were sometimes integrated through different commits.

## Small, justified structure improvements

The user wants coherent modules and a tidy repository as the work proceeds. This is authorization for local structure improvements that help the affected change, not a whole-project reorganization. Austin's inspected upstream deliberately has a flat engine/web layout and explicit package file lists. Preserve the existing CLI/import entry points and keep structural changes reviewable.

| Kind of change | Proposed placement / rule |
| --- | --- |
| Small fix owned by an existing component | Keep it beside the affected function. A helper used once does not automatically justify a new module or abstraction. |
| New regression tests | `tests/test_<behavior>.py`, with synthetic fixtures/support under `tests/` when shared. Keep existing `test_openscrub.py` in place; do not scatter the fork's many new `test_*.py` files at root. |
| Performance measurements | Reuse upstream's existing `benchmark/`, e.g. `benchmark/review_io.py`. Use `tools/` for developer/build utilities, `docker/` for container support and `docs/` for concise feature notes. |
| Runtime helpers that earn a module boundary | Introduce one private namespace, proposed `openscrub_internal/`, only when needed. Cohesive modules such as `reports.py`, `diagnostics.py` and `checkpoints.py` keep new root files bounded. Do not create generic `utils`, service/repository layers or empty scaffolding. |
| Optional search / refinement | Keep matching, job orchestration and bounded worker responsibilities together under `openscrub_internal/plate_search/`; any adopted boundary adapter lives under the same private namespace. These are downstream feature files, not required dependencies of generic fixes. |
| Large engine or embedded UI | Extract only a coherent piece touched by the task when it materially reduces coupling or makes behavior testable. Do not convert the entire app to a package, move all embedded JavaScript or introduce a frontend build stack during a small fix. |

The namespace name is a concrete proposal, not an upstream convention. Do not create an `openscrub/` package that shadows the existing `openscrub.py` entry point. A leaf module accepts plain inputs/callbacks and must not import `openscrub_web` to access global job state. Avoid circular dependencies and speculative public APIs.

For a useful extraction, keep a separately reviewable behavior-preserving commit before the fix/feature. Use a standalone prerequisite PR only when the structural change is substantial and independently useful; a small local helper extraction can stay in the same focused PR. Explain the removed duplication/coupling rather than arguing for abstract cleanliness. No mass formatting, unrelated renames or moving stable files merely for consistency.

Each new shipped module/package must be included in both wheel and sdist, relevant Docker COPY instructions, updater handling and Windows packaging where applicable. Validate source execution, clean installed CLI/web imports and the full sdist-to-wheel build. Add new tests to the actual verification command/CI; upstream's existing `python -m pytest test_openscrub.py -q` does not collect a new `tests/` directory by itself. Packaging and tests accompany the owning feature instead of becoming forgotten follow-ups.

## Proposed independently reviewable PRs

Each row names one review unit. Split a row further if its reproductions reveal independent bugs. A candidate that does not apply upstream closes with a recorded reason; it must not be padded into a feature just to use its donor code.

| ID | Proposed PR and scope | Donor / implementation-plan task | Required evidence and dependency boundary |
| --- | --- | --- | --- |
| P01 | Stream Save As for videos and reports, with byte progress | `2900930f`; Task 1 | Bar, written/total bytes, elapsed/estimated remaining time, waiting/finalizing states; actual suffix, cancel/fallback and job switching. Multi-gigabyte output does not become a browser `blob()`. Progress ships in this first PR. Independent of new review features. Save As explicitly welcomed. |
| P02 | Make Blur / Keep choices explicit and idempotent | `39b4ed83`; Task 2 | Repeated actions, groups and bulk actions, save/reopen/render. No classification/training schema. Explicitly welcomed. |
| N08 | Reject malformed/non-object scan options before creating jobs | Generic guard in `cd17868`; separate core reliability card | Actual 36-case upload/server-path baseline: malformed JSON 500, non-object JSON accepted/persisted/enqueued, direct argument preparation fails. Preserve omitted/object defaults and unknown-key policy; no learned/narrow validation or permanent-leak claim. |
| N09 | Close HDR decoder stdout on existing cancellation/error cleanup | Generic close in `08f432b`; separate rendering reliability card | Actual full-module cancellation/write-error cases retain the decoder pipe with an exception traceback even after children are reaped. Explicit close and successful frame/tag controls; no section dependency, permanent-leak claim or native-call deadline. Broader output lifecycle remains P16C. |
| N11 | Display ordinary job filenames literally | Generic output-boundary subset found in `aaeb71a`; separate core UX card | Source audit identifies accepted basenames and raw list/title interpolation. Verify benign punctuation/Unicode and normal job selection; no executed exploit or completed browser-probe claim. Independent of Findings and P02 decisions. |
| N12 | Keep first-scan OCR sanity valid with backtracking disabled | Newly exposed unchanged upstream owner; separate reliability card | Controlled-OCR failure plus pinned `--no-backtrack`/first result below three words source trigger. Lazy local sanity image, preserved warning/threshold/report behavior, exact-base RED/GREEN and floor/package evidence required. No index dependency. |
| P03 | Recover job progress polling after stalls or tab suspension | Polling subset of `08f432b6`; Task 3 | Request deadlines, hung response body, log cursor, job switches and bounded retries. No video sections or learning status. |
| P04 | Make long-scan ETA reflect recent throughput | `0b2e3d1d`, `367148d`; Task 3 | Startup, slowdown, stage change, stalled progress and bounded samples. No dependency on persistent logging or preview caching. |
| P05 | Publish complete live-preview JPEGs under concurrent reads | `90e67b6`, `5e967404`; Task 4 | Real HTTP response length and JPEG integrity during replacement; failed encode keeps last complete preview. Separate from thumbnail extraction. |
| P06 | Correct report publication/transactions and reduce measured save I/O | `4fd88af9` / implementation `d9a96c3`; Task 5; detailed P06A/B/C | Source probes expose interrupted-write and overlapping-edit loss; reproduce through real routes. Split atomic publication, complete transaction serialization and measured throughput as needed. Upstream already supports sparse keys and parses/writes once; no SQLite journal. |
| P07 | Preserve pending choices and make slow/failed-save retry safe | Save-state subset of `90e67b6`, `5e967404`, `test_release_reliability.py`; Task 5 | Real failed/slow save, newer edits, job switches and rendering; source probe also shows duplicated manual additions on replay. May use P06's transaction contract; no corner-conflict workbench. |
| P08 | Bound cold-miss report reads and invalidate derived thumbnails | `d15c69f`, `9ea3fae`, `98e5d9b`; Task 5 | Warm upstream disk hits already skip JSON parsing. Measure cold/parallel reads, memory, same-size replacement, geometry/source invalidation and deletion/vault lifecycle. No custom row-index/database requirement. |
| P09 | Prioritize visible thumbnails and bound browser/decoder queues | `d265c34`, `aeb24ce`, `312d91f`, `52274f32`; Task 5 | Large groups, scroll jumps, cancellation/job switch, visible request latency and peak queued work. Pagination/prefetch must preserve every choice. Adapt to upstream's current UI without requiring Findings or similarity grouping. |
| P10 | Bound expensive 4K decoding while returning the correct frame/crop | Generic subset of `5d55f8ea` and follow-ups; Task 5 | Burned-in frame IDs, PTS/crop coordinates, long GOP, CFR and normalized VFR, cold request and explicit bounded retry. Work cannot block unrelated edits. No custom 409/503 confirmation protocol. |
| P11 | Reduce demonstrated dense-smoothing and final-aggregation work | `a11a3926`, cache subset of `0b2e3d1d`, generic late-window work; Task 5 profiling | The old preview cache is removed-system-only and current forward PhiMemory stays authoritative. P11A retrieval, P11B tail-history and P11C reverse-recall improvements are independently reviewed. P11D’s tested sorted-left merge index failed all eight total-cost cases and was declined without a product diff; remaining merge cost stays documented. No cache restoration or inference-speed claim. |
| P12 | Add bounded runtime diagnostics for long jobs | `b7bc4172`, `50e3816`; Task 6 | Rotation, restart/unclean-exit marker, bounded heartbeats, unwritable storage, no raw OCR/crop/number retention. Strip learning hooks; no assertion that every unclean exit was an OOM. |
| P13 | Reuse Docker dependency layers and package downloads | `36636c4`, `8fb396a`, `7063167`, `bcda47f`; Task 6 | Cold build, source-only rebuild and intentional security refresh for CPU/Intel/CUDA. No trainer overlays, dependency-image redesign or version bump. |
| P14 | Fix Windows/NVIDIA inference setup where still applicable | `9f63f6e`, minimal subset of `7c47815`; Task 6 | Compose/build handoff and actual registered-model GPU execution on supported hardware. Keep separate from build-cache optimization; no training-image dependency. Record untested platforms explicitly. |
| P15 | Add useful view-only review filters without changing decisions | `64afc3cc`, `c3a8c7a5`, `8209a82`, `a80a85d`; Task 2b | Show all by default; type/output filters preserve pending edits, hidden choices and group membership. Filtering does not save/refetch the report or flood the thumbnail queue. Adapt only states that upstream actually has; no learning sampler, journal status or similarity workbench. New proposal, not explicitly promised acceptance. |
| P16 | Fix individual preview/render coverage or frame-alignment mismatches | `539432c`, `a056dff`, `c79cb29`, `4a6675f`, `e15c5eb`, `98c3231`, `77755f0`; Task 6a | First reproduce each mismatch in current upstream: configured padding, clipped faces, pending edits, dense tracks and matching frame/mask readiness. Keep each actual independent bug in its own PR and preserve upstream's newer face margins. Do not require compound masks or plate quads for generic fixes. |
| P17 | Add manual four-corner whole-plate masks | Early `617c9ac7` / editor `5c0782f`, integrated equivalents; Task 7 | Minimal editor/renderer, exact source frame, SDR/HDR and report reload. Can depend on an essential P16 fix. No training, automatic segmentation or lettering-only mode. Explicitly welcomed. |
| P18 | Add Stop & Review and resume using ordinary reports | Early `72efeb02`, `ffb4ed9e`, integrated equivalents; Task 9 | Synthetic interrupted scan, postprocessing checkpoint, restart, suffix merge and preserved reviewed prefix. Reuse P06 atomic helper only if needed; no journal, sections or learned rescans. Explicitly welcomed. |

P01–P16 must not depend on the optional confidence/assistance mode, OCR search or pretrained boundary research. The map does not mandate 18 submissions: reproduction can close candidates as already fixed/fork-only, or split a genuinely mixed item. Avoid a single large performance PR spanning unrelated endpoints and UI changes.

## Long/large-video evidence shared by the relevant PRs

Start this evidence work with the clean baseline, alongside the small UX ports. Each PR includes only the fixture/script and evidence needed for its behavior; a giant benchmark framework is not a prerequisite.

- **Report scale:** deterministic upstream-format reports with 1k, 10k, 100k and optionally 250k detections; ordinary groups/manual/audio edits; unchanged, single-change, sparse and bulk saves. Do not transplant the fork's 37k custom training/classification labels into an upstream reproduction. Its published 20.5s/8.8s save timings are historical fork evidence, not an upstream speedup claim.
- **Video scale:** small deterministic CI clips with moving frame IDs, plus opt-in long 4K/high-bitrate fixtures large enough to expose long seeks and resource pressure. Include long GOP, start/middle/end seeks, CFR and VFR normalized through upstream. Separate duration, resolution, encoded file size and detection count so each bottleneck is attributable.
- **Measurements:** elapsed save/decode time, p50/p95 request latency where repeated measurements are meaningful, report parses/serializations/writes, browser/server peak memory, decoder concurrency and queued work, initial thumbnail time, scroll responsiveness and total scan throughput. Compare the same inputs/settings/hardware at the recorded upstream SHA before and after.
- **Correctness under load:** exact pixels/frame/crop coordinates, atomic same-size report replacement, failed disk write, request timeout after server persistence, newer edits during an older save, job switch, cancellation, restart, source change, deletion and vault lock. An optimization must not lose choices or display the wrong source frame.
- **Reproducibility:** record OS, CPU/GPU/provider, RAM, storage, codec, frame rate, GOP, duration, dimensions, report rows/bytes and application cache state. Keep timing benchmarks outside fragile CI pass/fail thresholds; CI asserts bounded work and correct results. Never commit personal footage or multi-gigabyte fixtures.

## Coverage of every commit referenced in issue #22

Commit IDs locate evidence, not instructions to cherry-pick a whole change. Merge commits need their first-parent changes/constituent commits examined. The early quad/confirmation/checkpoint SHAs below are not ancestors of the inspected integration tip, although related behavior exists in integrated code; use the actual integrated implementation and small donor diff together. The four explicitly experimental PR references also remain outside that tip.

| Issue #22 donor | Disposition / destination | What must be retained or why it is excluded |
| --- | --- | --- |
| `a11a3926` | P11 investigation; current implementation removed-system-only | Constant-cost work principle retained; changed file is fork-only `finding_previews.py`. |
| `0b2e3d1d` | P04 plus P11 investigation | Split recent-rate ETA from duplicate Findings-preview I/O. |
| `4fd88af9` | P06/P07 | Merge commit; examine `d9a96c3`, atomic writer and relevant browser failure cases. |
| `d9e5d124` | P08/P09 evidence; custom index implementation excluded | Keep request latency/background invalidation lessons where applicable; no new SQLite/Findings row-index prerequisite. |
| `52274f32` | P09 | Bounded visible/ahead-of-scroll work, preserving drafts and choices. |
| `5d55f8ea` | P10 | Exact-frame/crop and bounded decode/retry behavior; assess independently of confirmation recovery. |
| `5e967404` | P05/P07 | Split live-preview publication from general failed-save choice preservation. |
| `ac241072` | Removed-system-only | Custom corner-save 409 recovery; retain as donor evidence for future minimal geometry editing, not a current upstream fix. |
| `818a9054` | Removed-system-only; P10 correctness evidence | JPEG lease/cache-eviction confirmation retry belongs to the removed workflow. Exact displayed-source identity remains a requirement where applicable. |
| `0d41b31d` | Removed-system-only; P10/P17 evidence | Do not bring the explicit confirmation-repair protocol; preserve exact-frame editing requirements. |
| `a0486e3d` | Removed-system-only | Austin expressly did not request the off-frame redraw system. Ordinary manual geometry editing remains in P17. |
| `b7bc4172` | P12 | Extract diagnostics without learning hooks or raw personal-data retention. |
| `0610cd57` | Already upstream | Austin's localized-change fix is in `a0b50a5`; keep that implementation. |
| `d6e9efc5` | Already upstream; initial donor unsafe in isolation | Austin's `a0b50a5` normalization covers all OCR engines/transcripts; the fork's initial regex required `c874ade`. |
| `2900930f` | P01 | Streaming Save As. |
| `39b4ed83` | P02 | Explicit idempotent output choices. |
| `617c9ac7` | P17; early donor not an integration ancestor | Manual quad renderer behavior; examine integrated equivalent and later source-frame fixes. |
| `a3520d7e` | Optional later minimal human-label proposal | Early donor not an integration ancestor; output Keep must not imply a negative training label. Training/example collection is excluded. Not a prerequisite for P02 or P17. |
| `64afc3cc` | P15 | Detection-type and output filters that only change the view. |
| `c3a8c7a5` | P15 subset | Preserve drafts/lazy cards; only expose statuses supported by the clean app. |
| `72efeb02` | P18; early donor not an integration ancestor | Atomic checkpoint and review-preserving suffix merge, without training. |
| `ffb4ed9e` | P18; early donor not an integration ancestor | Checkpoint after postprocessing; preserve reviewed prefix. |
| `f4f75a14` | Removed-system-only | SQLite classification/corner journal excluded. P06/P07 address demonstrated upstream persistence problems without it. |
| `8b9098d2` | Removed-system-only | Similarity workbench excluded. Preserve upstream's existing track grouping and efficient ordinary review. |
| `d6fef963` (fork PR #68) | Unmerged research evidence for P09 | Do not require preparing every thumbnail before review or add an unbounded scan-end delay. Compare visible-only scheduling first. |
| `a3dcc156` (fork PR #69) | Unmerged; exclude initial scope | Plate-free range workflow is not a generic performance fix and changes redaction decisions. |
| `005b7f38` (fork PR #70) | Unmerged correctness evidence for P17 and optional tracking | A manually edited quad must not be blindly propagated across changing frames. No learned-mask dependencies. |
| `9e0257f0` (fork PR #66) | Unmerged UX evidence for P02/P09 | Evaluate representative choice and group output clarity using only upstream evidence; no learned plate checker. |

Additional candidates already in the main plan stay tracked here: resilient polling, atomic JPEG publication, generic failed-save handling, recent ETA, report-cache invalidation, viewport scheduling, build caching, inference setup, diagnostics, preview/render fidelity and ordinary local filters. `74edee0`'s bounded OCR subprocess belongs to the separate downstream search feature; `a6419cc`'s narrow-mask optimization belongs to downstream lettering-only mode. Neither is silently lost or folded into a generic upstream PR.

## Branches, dependencies and handoff

1. Preserve the integration snapshot and inspect remaining history before deleting/replacing any working branch. Reconcile every changed production file and every feature/fix family into this ledger; new discoveries receive a disposition and validation owner.
2. Branch each upstream PR from Austin's current `main`, e.g. `upstream/streaming-save-as`, `upstream/large-report-writes`, `upstream/thumbnail-report-cache`. The user's remote hosts these branches. A direct upstream base is preferred; when a tested helper is genuinely shared, declare the small dependency explicitly and update/rebase the dependent PR after it lands.
3. Keep `integration/upstream-focused` as the user's assembled testing branch. It is not a PR base or a proposed merge into Austin's repository. Never make generic fixes depend on downstream-only features or on removing the entire fork first.
4. For each PR, provide one concrete problem/feature scenario, baseline SHA, focused change, reproduction command, before/after behavior or measurements, relevant regression tests and platform limits. Include donor attribution and the relevant issue #22 reference. Explain any justified helper extraction and validate its packaging. Drop unrelated version changes, experiments, historical logs and private input data.
5. Validate each PR on its declared base, then validate the assembled branch. Keep default-behavior regressions; performance success cannot come from disabling checks, changing redaction policy, skipping requested frames or silently losing decisions.
6. First delivery batch: P01/P02 and independently proven P03–P05, while reproducing P06–P11 against clean upstream. Move confirmed large-video bugs into their own PRs as evidence becomes available; do not wait for the optional feature work. P12–P18 follow their own readiness and dependencies.
7. Prepare reviewable branches and PR descriptions locally. Publishing issues/PRs is a separate explicitly requested action; none is authorized merely by this planning map.

**Cutover acceptance:** All issue #22 entries and remaining relevant history have an explicit disposition; every retained upstream fix has independent validation; unresolved applicability is visible; long-video performance is measured rather than assumed; no custom training or workbench dependencies enter the cleaned app; Austin's defaults remain the defaults.
