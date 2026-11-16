# B03 core semantic supplement

Pinned comparison: upstream `5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f`
to donor `b4d0c75f25d91510fe1692f901d11853dc7db005`, 2026-11-16.
This extends [the preservation audit](preservation-audit.md); it does not
reclassify whole commits from partial function evidence.

Read the complete final engine diff and changed Python web worker, render,
report, save, queue, vault, lifecycle and preview-helper deltas. The exact
function/class table contains **45 engine and 115 web definitions**, each with
old/new line ranges, destination, split/removal reason and relevant lineage:
[core-functions.csv](core-functions.csv). The exact zero-context hunk index is
[core-hunks.csv](core-hunks.csv): 142 engine hunks and 296 web hunks. Of these,
297 intersect the source-compared definitions. A subsequent source pass now
gives the remaining **141 module/constants/embedded UI hunks explicit task,
split, retain-upstream or removal decisions**. This is source evidence, not an
application reproduction or endorsement of donor behavior. Exact per-hunk
reasons are in [core-module-hunks.csv](core-module-hunks.csv); finer embedded
ownership records are in [core-ui-sections.csv](core-ui-sections.csv).

New findings are N07–N10 below; N06 is strengthened from the initial report.
The major outstanding scope remains unreviewed intermediate commits,
non-core production modules and runtime reproduction of candidate behavior.
Source-reading all final core hunks does not resolve those independent gates.
B03 and S01–S06 remain incomplete.

| Finding | Exact owner and source evidence | Disposition / destination |
| --- | --- | --- |
| **N06: rendering projects away Keep rows and changes row indices** | Upstream `load_report` (6336) explicitly skips disabled rows; `run_pipeline` (8505) passes those enabled objects to `run_render`, whose `write_report` (6287) rewrites the same report from that projection. Training-titled `db9a142` adds `learning_session.preserve_render_review` (donor 918) and worker restoration of the original complete detection list, source/timeline checked. | Generic P06/P07 preservation candidate. Keep ordinary review rows/identities while updating render provenance; do not add training state/helper. Actual render/reopen test still required. The isolated real-function probe below confirms the projection loss. |
| **N07: thumbnail pre-generation removal depends on removed Findings cache** | Upstream `_run_job` starts `_pregen`, then selects normalized `job['video']` from provenance. Donor worker (857) deletes that second pass because `WebCallbacks.scan_findings` supplies cached pictures during scan. | Preserve upstream ordinary pre-generation until P08/P09/P10 supplies a validated replacement. Do not delete both caches. Investigate a source-selection race: `_pregen` may read the upload before `job['video']` switches to the normalized scan source. This is source-backed possibility, not reproduced wrong-frame output. |
| **N08: malformed/non-object scan options receive HTTP 400** | `cd17868`, titled reusable learned models, adds `create_job` donor 1188 JSON decode/type guard before narrow-specific checks. Upstream 903 directly decodes form data. | Generic reliability candidate requiring a small separate disposition if reproduced; outside existing P01–P18 task boundaries rather than silently expanding a polling/save PR. Test malformed JSON, `[]`, `null`, scalars and valid objects with synthetic requests. Keep just the generic guard, excluding model selection/narrow validation. |
| **N09: close HDR decoder stdout during cancellation cleanup** | Section-titled `08f432b` adds the decoder-side `pr.stdout.close()` branch inside `render_hdr.cleanup_partial`; it is unconditional for ordinary HDR cleanup too. Final donor 3958; upstream 3972 cleanup only explicitly closes encoder stdin. | Small generic decoder-lifecycle candidate for investigation alongside P10/P16 evidence. Verify actual child/descriptor cleanup on cancel/error; section-specific short-read/return-code checks remain excluded. No new section feature or whole renderer transplant. |
| **N10: publish tracked rows against the latest report** | `08f432b` changes `job_track_object._run` final publication: acquire edit lock, load latest report, append only new rows, atomically publish. Current upstream overwrites the independently loaded report after potentially long tracking. | Concrete P06 writer-coverage candidate: preserve concurrent ordinary Blur/Keep/manual/audio edits. Donor allocates `tid` before reloading latest state; test concurrent track additions/ID collisions and source/report replacement before adopting. Remove journal and section guards. |

The N06 synthetic probe uses upstream's actual `Detection`, `load_report` and
`write_report` AST with a harmless settings shim. Three synthetic rows
`[Blur row 0, Keep row 1, Blur row 2]` become two enabled rows, and old row 2
becomes index 1. This isolates the projection used by the source render chain;
it does not execute video decoding, Flask, HTTP or browser reopening.

```sh
python3 .superpowers/sdd/README/probe_render_review_projection.py
```

[Raw projection results](render-review-projection-results.json) and
[probe source](probe_render_review_projection.py). Retain upstream's intentional
enabled-only renderer input; the candidate concerns what replaces the web
review report after rendering, not applying Keep rows to output.

The newly identified generic changes are not all ready PRs. N08/N09 have no
clean existing task boundary and remain explicit investigate candidates. N06,
N07 and N10 refine the existing report/performance contracts. No existing P/O
card was expanded or product behavior changed during this audit.

## Function-level extraction decisions

The CSV is the complete named-definition table. These grouped rows explain
the material splits; exact source positions and individual owners are in the
CSV, so a mixed large function is not implicitly approved in full.

| Exact owner group | Decision and source reason | Destination / lineage |
| --- | --- | --- |
| Engine OCR normalization, `PhiMemory`, phrase helpers, `detect_phi`, `_speech_suggestions`, `FaceDetector`, `text_scan_stride` | Keep Austin. Donor removes current slash/all-engine normalization, compiled fuzzy matching, phrases/cross-word regex and close-up face expansion. | Already upstream; `a0b50a5`, `1f01433`, `7556ff9`, `f807d85`, `9f71cd2`. |
| `Detection`, `load_report` | Add only fields earned by adopted geometry; keep positional compatibility. Training labels/section ownership/compound holes are not generic prerequisites. Disabled-row dropping exists in both versions; N06 belongs to web report preservation. | P17/O05; `8697c28`, `ccff62f`, `1fe4e34`, `08f432b`. |
| `smooth_dense_tracks` | Separate the N01 generic initial seek from exact narrow plate interpolation and section/frame ownership. Unsuccessful seek fallback must still be positioned correctly; existing fake-decoder probe does not prove that property. | P11/P18, optional O05; `ccff62f`. |
| `rasterize_region_mask`, `blur_region`, `rasterize_mask`, `blur_silhouette`, `_blur_silhouette_yuv10` | Share only necessary ordinary mask calculation. N02 touched-chroma union and N03 finite-input fallback are separate generic investigations; preserve upstream border extension and compare dilation semantics. Rejecting box-relative coordinates outside 0..1 must not accidentally invalidate P17's legitimate quad contract. | P16, essential P17 helper only; `8697c28`, `a056dff`. |
| `audio_ffmpeg_args`, `_section_frame_bounds`, `_restore_section_intake` | Added trimming, rebasing and source validation serve section export. Ordinary no-trim audio path stays upstream. | Removed-system-only, `08f432b`. |
| `render`, `render_hdr`, `run_render` | Quads P17; actual contour-preview P16; exact sample/padding O05. Section frame ranges, audio trims and section short-read guards excluded; isolate N09 instead of adopting all section error handling. | P16/P17/O05; `8697c28`, `ccff62f`, `08f432b`. |
| `_narrow_from_probability`, `TextRegionDetector.find_plate`, `_restore_plate_settings`, `_detection_pad`, `_validate_narrow_frame_alignment` | Keep optional lettering-only detector/guard/settings behavior downstream. The donor uses exact-frame plate samples as a reason to reject HDR; do not impose that O05 limitation on P17 manual whole-plate HDR support. | O05, `1fe4e34`, `a6419cc`. |
| Engine `Callbacks`, `run_scan.scan_findings` hooks | Remove persistent Findings preview capture hook; ordinary frame callback survives. Do not discard the existing thumbnail strategy as a consequence (N07). | Removed system, `aaeb71a`. |
| Engine `run_scan`, parser/prep, `write_report`, `run_pipeline` | P18 stop/resume/checkpoint source/timeline only; O05 narrow settings only. Keep current phrases, plate-threshold warning, normalization and face margins. Original-input hashes are necessary only where adopted source contracts need them; section validation is not a default policy change. | P18/O05; `ccff62f`, `08f432b`, `1fe4e34`. |
| Web `new_job`, `build_args`, `_plate_threshold`, `_sanitize_argv`, queue/worker/watchdog functions, `job_cancel`, `job_retry`, `job_render`, `rehydrate_jobs` | Preserve Austin's option persistence/sanitization, parser exception conversion, worker survival/watchdog and queue generations. Add only Stop/Resume state through those current interfaces. Donor final source removes these newer protections. | Current upstream guardrail `4f863f3`; P18/P12 adaptations only. |
| Web `worker` render branch | Preserve ordinary report projection before/after render (N06), then update output metadata. Exclude learning, journal and section fields. Keep source/timeline mismatch failure handling without losing edits or deleting earlier valid output. | P06/P07; `db9a142`. |
| `job_public`, `WebCallbacks`, `job_log`, `_publish_preview_jpeg`, `job_preview` | Metadata for filenames, progress, recent-rate ETA, bounded logs, stable JPEG producer/response and checkpoints have existing owners. Training/section status and scan-image retention removed. | P01/P03/P04/P05/P12/P18. |
| Diagnostics request hooks, `_web_settings`, model/install/update/waveform hooks, `main`, `_serve` | Retain bounded diagnostics only. Preserve upstream watchdog and TLS noise handling; donor reroutes formerly suppressed TLS noise into persistent warning logs. Raw response reasons/stderr/exception strings are not automatically allowed telemetry. | P12; `b7bc417`. |
| `_load_job_report`, `_review_journal_snapshot`, `_fast_review_choices` | The delta is journal overlay/publication/deferred durability, excluded. Keep normal JSON report authority; use P06 transactions and P07 replay safety. No journal ACK copied. | Removed system; `9f0df99`, `6de072b`, `f5195fe`. |
| `_preview_report_identity`, `_load_preview_report_base`, `_warm_review_listing_index`, `job_detections` | Preserve source/report revision discipline and stale-worker safety only where an ordinary cache is measured. New index/journal/training fields are excluded. | P08; `9ea3fae`, `98e5d9b`, `6ce3406`, `d66ae10`. |
| `_review_process`, `_review_probe`, `_read_review_frame`, `_read_exact_frame`, `_frame_at` | Bound process concurrency/deadline, validate PTS and exact crop geometry, convert RGB before crop. Equality of average/nominal FPS alone is not universal proof of CFR; preserve tolerant timestamp previews separately. | P10; `b68634d`, `5d55f8e`, `496e017`. |
| `_SavedPictureGate`, `_serialize_review_read`, `_serialize_review_edit`, `_vault_lock_now`, `job_delete` | Adopted cache/read/write lifetimes must exclude encryption and purge plaintext on lock/delete. A global reader/writer gate or nonblocking 503 protocol is not automatically necessary for upstream. Preserve current writer ownership/order. | P06/P08/P10; `f5ffdb0`, `6d5e8fd`, `a833e3e`. |
| `_review_detections`, `_review_mask_data`, `_review_mask`, `_apply_detection_edits`, `job_detframe`, `job_boxes_at` | Generic render-settings/coverage, pending-edit preview, dense winner selection and frame identity. Strip learned override/confirmation, compound and section fields unless their separate feature is adopted. | P16; `539432c`, `a056dff`, `c79cb29`, `4a6675f`, `98c3231`. |
| `_plate_editor_crop`, preview key/store/cache/helpers, `_plate_frame_bounds`, `job_plate_quad` | Minimal manual source-bound quad editing only. Float roundoff tolerance is useful; training sample saving, confirmed Findings routes, blanket track-quad copying and journal/section protocol are excluded. | P17 with P08/P10 contracts; `7c0688f`, `5c0782f`, `d75ef73`. |
| `job_thumb` | Donor moves `_load_preview_report` before every hit and sets no-store/revision suffix. Upstream already serves existing warm JPEGs without parsing report. Preserve that shortcut while proving invalidation; do not treat donor warm-path change as a speedup. | P08/P10, P17 plate editor subset. |
| `_reconcile_compact_previews`, `_warm_legacy_preview_reconciliation` | Functions only relink removed persistent Findings image cache. Keep revision-fencing lesson, not this infrastructure. | Removed system; `667b88e`, `6c41f74`. |
| Training/model/checker/example routes and helpers, `_save_verified_plate_sample`, `_human_plate_override` | Remove dedicated routes, samples, learned decisions and archive behavior. Shared ordinary changes in their introducing commits remain separately mapped above. | Removed system; `db9a142`, `cd17868`, `1a101f6`, `aaeb71a`. |
| `retention_sweep`, learning busy-state additions, `enforce_vault_lock`, upload guard deltas | New reserved/model/section/reference-graph conditions serve removed systems. Preserve current ordinary retention, upload and vault behavior; cache cleanup follows adopted cache owners. | Removed system delta; `08f432b`, `aaeb71a`, `cd17868`. |
| `_regex_min_width`, `custom_cats` | Retain Austin's static regex width rejection; donor deletes it. | Already upstream `f2573f2`/`f807d85`. |

## Focused embedded UI source checks and intermediate lineage

These checks supplement the Python table. The final module/UI hunk coverage is
now source-read throughout, with runtime/intermediate-history limits retained.
Positions below refer to the pinned donor web file.

| Exact JS owner | Source evidence / disposition |
| --- | --- |
| `loadJobs` 4362, `openJob` 4410, `stopJobPolling` 4424, `refresh` 4475, `refreshJob` 4507, `renderWorkProgress` 4657 | P03 request/job/view fencing, one active refresh, wake-up/hidden-tab recovery, bounded log rendering, backoff and stall-aware ETA. Remove section/learning branches, preserving ordinary UI state. The hidden-tab synchronous completion comment describes a donor follow-up that must survive a shortened extraction. |
| `saveExportAs` 4449 | P01 picker invoked before fetch; streaming/fallback and captured job ID. Donor still has only static Saving state, so P01 byte counter/finalization feedback remains new work. |
| `reviewRequest` 5371 | Promise.race bounds both transport and body-read occupancy; abort alone can leave a suspended body owning the single-flight slot. P03/P07/P09 reuse must keep separate metadata/save/download deadlines. |
| `clearReviewPreviews` 5396, `loadReviewPreview` 5517, `reviewPreviewRank` 5644, `pumpReviewPreviews` 5657, `initReviewPreviews` 5682, `appendReviewPage` 5705 | P09 cache-first queue, visible reranking, 3 saved-image reads/1 cold decoder, cancellation/job-view cleanup and lazy DOM. Preserve only bounded generic scheduling; remove Findings/quad-confirmation/similarity hooks. Verify actual peak metadata/HTML memory: lazy DOM alone does not prove bounded whole-report browser memory. |
| `sampleReviewGroups` 6753 | Learning-sampler policy excluded. Its local, non-saving filter mechanism can inform P15; do not keep sampler/training states. |
| `reviewGroupStatus` 6786, `reviewOutputFlags` 6802, `setReviewViewFilter` 6827, `applyReviewGroupFilter` 6857 | P15 view-only grouping/type/output/pending predicates. Strip classification/learning-only states and preserve hidden drafts. Count groups from complete metadata, not mounted DOM. |
| `reviewChoiceDelta` 7175, `saveAndRender` 7874, `persistReview` 7921 | P06/P07 sparse output changes, save acknowledgement and job/view/baseline fencing. Remove journal defer flag/confirmation chains/labels. Donor still clears all `BE.adds/ov/times` and `MAN` after acknowledgement; newer box/manual edits need their own snapshot/version test, not reliance on card `REVIEW_VERSION` alone. |

History matters where tip behavior reflects a replacement, not a simple fix:

- `429319f` made cache-first previews; `276532f` then disabled automatic cold
  decoding; `aeb24ce` reintroduced automatic visible loading plus pagination.
  Preserve bounded current scheduling under P09/P10, not both contradictory
  cold-load policies or the discarded workaround as an independent fix.
- `aaeb71a` removed upstream thumbnail pre-generation after introducing
  scan-time compact previews. That dependency makes N07 visible only when the
  original worker and cache-introduction diff are read together.
- `db9a142` introduced report row restoration for training-rich review, but
  the ordinary enabled-only report projection is already upstream (N06).
- `08f432b` mixed section export, generic polling, HDR descriptor cleanup,
  source identity and latest-report tracker publication. These now have
  separate dispositions instead of one section-only exclusion.
- `4fd88af` first-parent changes preserve no-op/sparse save/timing behavior;
  later `6de072b`/`f5195fe` replace publication with an opt-in journal ACK for
  render intent. Preserve the earlier ordinary transaction lessons while
  excluding the later journal dependency.

## Remaining module/UI hunks: new preservation risks

| Finding / dependency | Exact source evidence | Required disposition |
| --- | --- | --- |
| **N11: job filenames must remain text** | Findings/training introduction `aaeb71a` changes `loadJobs` and `shellHtml` from raw `j.name` interpolation to `sectionEscape(j.name)`. Upstream `create_job` retains the uploaded basename after removing path components; it does not HTML-escape it. W138/W147 and the generic `sectionEscape` helper in W165 locate the fix. | Investigate a small generic HTML output-boundary fix, independently of Findings or section UI. Use synthetic markup-bearing filenames and verify list/title display literally. Do not infer an executed exploit or publish a security issue from source evidence alone. No existing P card naturally owns this fix; retain it as a separate candidate. |
| **N12: preserve current mobile help placement/tap behavior** | Donor W130–W132 remove variable tooltip width/offset and below-placement CSS. W236/W237 remove upstream `qmPlace`, its hover hook and `preventDefault` when tapping a help tip inside a checkbox label. | Retain Austin's current viewport positioning and tap guard when extracting nearby P02/P15/P17 listeners/CSS. These are upstream guardrails, not new donor fixes. |
| **N13: do not replace ordinary enlargement with a Findings JPEG** | `zoomDet` W208 now displays `thumb<i>.src` or the Findings preview route instead of the ordinary `detframe` image. The old endpoint shows the full source frame and effective-mask context; a cached small/representative crop is a different view. | Retain ordinary upstream enlargement unless a P10/P16 replacement reproduces both detail and correct source/coverage identity. Source identity alone does not establish view equivalence. No new feature requested. |
| **N14: plate-only guards do not protect every ordinary draft** | W212/W213 `showPanel`/`loadCompare` and W246 `vaultDoLock` await only `flushPlateSaves`; `openJob` checks card `reviewChoicesPending`, while ordinary box/audio changes do not increment that revision (explicitly documented in donor `saveSectionReview`). | P07 must cover navigation to Compare/standalone editor, job switching and vault lock with output/manual/box/time/audio drafts. Reuse only the minimal P17 gesture flush where adopted; do not copy the removed section workflow to get general dirty-state protection. |
| **P15 status dependency** | `reviewGroupStatus` computes handled from `OUTPUT_CHOICES` or removed human classification labels. Type/output predicates use complete group membership, including unmounted pages. | Build retained Needs review/Handled state from P02 ordinary explicit output choices if available; otherwise close/defer that status filter. Do not reconstruct it from default enabled=true or retain Is/Not training labels. Type/output filtering remains independently useful. |

The large mixed additions now have fine ownership records: generic
`reviewRequest` body deadlines, job/view fencing, visible-priority preview
queues, lazy pages, explicit output actions and local filters have P owners;
OCR/narrow badges have O03/O05 owners. Dedicated `openPlateRepair`, Is/Not
confirmation/archive recovery, learned model/checker UI, training sampler,
section actions and similarity hooks have explicit removal decisions. Minimal
manual quad input/version/gesture cleanup remains P17, with its source binding
and P07 acknowledgement contracts kept distinct from training approval.

Two small extraction details matter despite having no new task ID. The donor
moves `SHELLPH` publication until after successful guarded review loading, so a
failed transition remains retryable (P03). The generic polling tail and wake
listeners occur after learned-model UI helpers in W248; deleting the whole
training-looking block would lose focus/pageshow/online/visibility recovery.
Likewise, the module-bottom section wrapper loop W296 serializes ordinary
writers as a side effect; remove section registration while retaining explicit
P06 writer coverage, rather than silently removing both.

The 141 decisions are reproducible source mappings, not a statement that 141
bugs were fixed or that all generic candidates are applicable. All 438 final
core hunks now have a nonempty owner, destination, disposition and reason.
`core-ui-sections.csv` names 150 embedded JS owners with pinned source starts
and split/removal rationale. Giant hunks remain explicitly mixed; a task name
in one row never authorizes copying the whole hunk.

No whole-commit status was upgraded from these function/hunk checks. The original
500-row ledger remains the ancestry inventory with conservative evidence
levels. Recreate the tables with
`python3 .superpowers/sdd/README/collect_core_semantics.py`; the script asserts
every changed top-level engine/web Python definition and every previously
unowned final module/UI hunk has an explicit mapping. Remaining closure work
includes actual route/browser/render reproductions, intermediate-only semantic
changes, non-core production modules and S01–S06.
