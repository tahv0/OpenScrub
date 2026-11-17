# Optional Assistance Implementation Plan

> **For agentic workers:** Use `superpowers:executing-plans` when implementation is requested. These tasks start downstream; do not silently add them to generic upstream PRs. Checkboxes are future work.

**Goal:** Help the user achieve the intended redaction with fewer unnecessary boxes/flashes and fewer repeated edits, using pretrained inference and manual control.

**Architecture:** Preserve Austin's current path as the default. An explicitly selected assistance policy uses the same detection evidence but separates suggestions, output choices and geometry reliability. User-selected candidates seed tracking. Whole-frame OCR can discover detached plates independently of YOLO; boundary refinement remains a separate optional stage.

**Tech stack:** Existing YOLO/PP-OCRv5/OpenCV/VitTrack and current OCR adapters first. Published pretrained recognition/segmentation tools may be evaluated separately; no model creation, fine-tuning, dataset collection or training extras.

**Spec:** [Conversation decisions D02–D13 and research R10–R11](decisions-and-research.md), [delivery cycle](README.md), earlier [tool comparison](../2026-11-16-upstream-extraction.md).

## Global constraints

Upstream defaults stay unchanged when the option is absent/off. The user's preferred optional behavior leaves uncertain candidates as suggestions, permits them to remain unhandled and does not impose a new export gate. Explicit choices survive policy changes. A lost location does not justify a frozen/widened mask. No inference score is a calibrated guarantee. Optional queries/crops/caches belong to the job and its existing deletion/vault/retention lifecycle. Austin has not accepted these policy/OCR/narrow-mode scopes merely because they are opt-in.

## O01 — assistance policy and stable automatic activation

**What:** Add opt-in Review uncertain and Blur uncertain output policies, a separate automatic-blur cutoff, and temporal support before automatic activation in the user's preferred mode.

**Why:** Raising the existing detector threshold discards candidates before the user can inspect them. Conversely, treating every uncertain hit as a mask creates cleanup work and flashes. The option should retain useful evidence while limiting automatic output.

**When:** W4 after ordinary review/save behavior is stable. Integrate with O02 before presenting a complete select-once-and-follow workflow. Branch separately from upstream fixes; seek scope agreement before any upstream proposal.

**Files / contract:** Existing settings/review/render checks, `tests/test_plate_confidence_policy.py`, affected browser tests. Optional per-job `uncertain_policy` values remain `manual_review` and `blur_candidates`; absence means current upstream behavior. Reuse upstream `plate_threshold` as candidate floor. Validate finite `0.05 <= candidate_floor <= auto_cutoff <= 0.95`; `0.35/0.80` remains an illustrative pair, not a calibrated accuracy claim.

Record only the additive state needed to distinguish explicit human choice from policy output and unhandled suggestions, using existing job reports/track groups. Suggested internal decision inputs: explicit output choice, candidate evidence, per-frame geometry validity, temporal support and selected policy. Produce effective blur/visible output plus suggestion/gap status. Keep detector, OCR, tracker and shape evidence separate.

- [ ] **E/S:** Implement a policy truth-table test before UI work: default/off equals upstream; explicit Blur/Keep wins; low-score retained candidates remain suggestions in manual_review; blur_candidates may render usable low-score regions; missing location remains a gap in both.
- [ ] **E:** Use fixed clips containing isolated false positives, short real appearances, stable targets and confidence fluctuations. Choose the optional mode's initial activation parameters from measured behavior and document them. Proposed starting continuity rule is two associated valid observations; human selection can seed a target immediately. Do not require OCR/YOLO success on every subsequent frame when a tracker supports the target.
- [ ] **I:** Add `test_optional_policy_preserves_default_masks`, `test_isolated_high_score_is_suggestion`, `test_explicit_keep_survives_policy_switch`, `test_unhandled_suggestion_does_not_block_export` and a switch/reopen case. A policy change recomputes automatic decisions, not human choices; lowering the candidate floor needs a rescan because discarded candidates are absent.
- [ ] **I:** Keep suggestions as optional overlays/counts in existing review/timeline controls. Clean preview shows actual output. Add no compulsory queue, per-candidate approval dialog, automatic Blur remaining or new database. In blur_candidates, short extra masks are a deliberate tradeoff; show their policy origin without calling them human-confirmed plates.
- [ ] **V:** Run `python -m pytest test_openscrub.py tests/test_plate_confidence_policy.py -q`, build and browser/CLI policy round-trips. Measure unwanted masked area/time, false-positive flash events, missed intended targets and correction actions against the baseline. No promise of eliminating every false positive.
- [ ] **D/R/L:** Document the optional behavior, preserved default, limitations and measured work reduction. Prepare an upstream scope discussion separately if requested; keep generic fixes independent if Austin declines.

**Source handoff and decided boundaries:** The [O01 source investigation](execution/evidence/research/optional-policy-contract-research.md), including its superseding supervisor amendment, traces retained detector observations, synthetic smoothing, frozen tracker samples, report writers and explicit-choice acknowledgements on reviewed C01 `4b9bd7e`. Synthetic rows can inherit detector confidence, so row count and representative confidence cannot establish independent observations or location support. This remains source-only evidence; no policy implementation, parameter calibration or accuracy result is claimed.

- [ ] **E/I:** In `manual_review`, require two independent cutoff-eligible observations before automatic activation; in `blur_candidates`, permit one retained floor-eligible hit with supported location. The latter deliberately tolerates extra short masks/flashes. Neither mode invents geometry through a gap. Freeze the exact time window, onset rule and initial cutoff only after the bounded clip evaluation.
- [ ] **S/I:** Keep optional evidence and explicit intent inside a provenance-capable report. Ordinary/legacy reports retain their schema and saved enabled output, with no automatic conversion or invented human history. They can still save/render/export; a fresh optional scan does not promise transfer of old choices. Previously optional reports retain their evidence/intent when switched off.
- [ ] **S/V:** Capture observation origin/frame before smoothing and preserve it through the actual creation, copy, encoding and hydration boundaries. Existing `Detection` instances offer a possible internal owner, but `asdict` and primitive argument serialization can leak optional defaults into ordinary reports; verify absent/off byte equivalence explicitly. Reuse P06/P07 transactions and value-equality acknowledgements. Final internal metadata representation remains an implementation decision, with no parallel observation registry.

## O02 — track the target selected by the user

**What:** Extend existing bidirectional manual tracking with exact seed-frame identity, correction keyframes and explicit uncertainty/loss handling for plates, text and arbitrary regions.

**Why:** Finding or correcting one frame is not enough. The user wants that selection to reduce repeated edits throughout a chosen interval, including targets the detector never recognizes.

**When:** W4 alongside O01. The box baseline can ship downstream before automatic shape refinement; O04 is not required. P10/P16 frame correctness may be prerequisites if their contracts are used.

**Files / contract:** Existing `track_manual_region`, `job_track_object`, track/timeline UI and per-sample report data; `tests/test_manual_target_tracking.py`, browser counterpart. Reuse track IDs and source-bound observations. Seed inputs: exact source/frame, box or quad, chosen interval and output intent. Outputs: timed geometry samples with reliability plus uncertain/lost intervals. A correction adds a keyframe and retracks only the affected span.

- [ ] **E/I:** Add tests for a manually drawn target with zero YOLO hits, a detached plate, camera motion, scale/perspective change, unreadable text, two similar crossing objects, a cut, exit/reentry and occlusion. Assert no automatic switch to a person tracker just because a person overlaps the selected plate/text.
- [ ] **I:** Start from pretrained VitTrack/template tracking for boxes. If the seed frame cannot be read exactly, report that failure instead of reusing coordinates on a nearby fallback frame. Continue through OCR/detector gaps only while visual continuity remains supported.
- [ ] **I:** Treat weak/frozen upstream tracker samples as uncertain evidence in the optional path. On lost position stop unsupported mask propagation and mark the interval. Offer correction, trimming or an explicitly selected broader region; do not freeze/widen/switch automatically. Keep the target and chosen intent for later correction.
- [ ] **I:** Make keyframes, splits and retracking idempotent and source-bound; preserve other corrections and output decisions. Text equality alone must not link an ambiguous later appearance. Keep rejected false-positive segments rejected without suppressing unrelated lookalikes.
- [ ] **E/I:** Evaluate planar-quad propagation with OpenCV feature tracking and robust homography only if box-only motion is insufficient. Require distributed inliers, forward/backward consistency and valid geometry; do not stamp one normalized quad onto all boxes. Arbitrary changing silhouettes need separately validated mask propagation from O04.
- [ ] **V:** Run `python -m pytest test_openscrub.py tests/test_manual_target_tracking.py tests/test_manual_target_tracking_browser.py -q`, build and actual synthetic mask/render comparisons. Test cancellation, restart, source changes and export with preserved gap status; unchanged default tracker behavior must also pass.
- [ ] **D/R/L:** State box/quad/mask capabilities separately, including where the user must correct. Show one seed → movement → loss → correction example and measured edit reduction. This is pretrained inference/tracking, not training a new model.

**Source handoff and adopted boundaries:** The [selected-target contract](execution/evidence/research/selected-target-tracking-contract-research.md), including its final supervisor disposition, maps the actual C01 owners and supersedes its initial geometry-anchor proposal. Current target controls belong in the same optional raw report, while supported geometry stays in ordinary detection rows. An all-gap target retains its identity and Blur/Keep intent without forced keyframes, fabricated boxes or an export gate.

- [ ] **S/I:** Add only capability-gated current target controls, typed identity/source admission, control-only touched-state publication and full raw save/reopen preservation. Keep ordinary/legacy schema and default tracking unchanged.
- [ ] **I/V:** Start with verified box tracking that stops on unsupported continuation and resumes through an explicit exact correction. Use the one-latest-receipt/predecessor contract; a delayed old correction conflicts after a newer one instead of overwriting it. Preserve row-context drafts and current choices/audio. Unknown regenerated metadata needs an explicit owner or an unchanged-report failure.
- [ ] **E/V:** Prove the P10/O01/P16D prerequisites and subsequent frame-reader behavior, then calibrate continuity on bounded clips. Source contracts alone establish no identity reliability, edit reduction, throughput or optional runtime acceptance.

## O03 — training-free full/partial plate-number search

**What:** Retain the donor's pure OCR/matching core while replacing training/workbench orchestration, and support whole-frame discovery without a vehicle/plate detection.

**Why:** A plate lying on the ground or displayed on a wall may be missed by YOLO. The user wants to search known full/partial text and then select/track the resulting region.

**When:** W4 as a separate downstream feature; candidate search can work before O04 boundaries pass. Integrate selected results with O02 for follow-through. Upstream acceptance remains unresolved because Austin questioned reading plate numbers.

**Files / contract:** `openscrub_internal/plate_search/matching.py`, `jobs.py`, `worker.py` derived from `plate_text_hints.py`, `plate_text_web.py`, `plate_text_subprocess.py`; small UI hooks; `tests/test_plate_text_hints.py`, `tests/test_plate_text_web.py`, `tests/test_plate_text_subprocess.py`; concise `docs/PLATE_SEARCH.md`. Preserve `search_frame(frame_bgr, hints, regions=None, reader=None, cancelled=None)` with OCR observations and match/geometry evidence separate.

- [ ] **E/I:** Add zero-YOLO/zero-vehicle fixtures with synthetic plates on a wall/ground, rotated or perspective skewed, small in 4K and partly unreadable. The full-frame path must find explicit fragments, unlike the donor's current rejection of partial `full_frame_text` / `text_contour` matches.
- [ ] **I:** Define full-number equality versus explicit fragment versus uncertain OCR interpretation. Proposed baseline: uppercase/separator normalization and at least three literal query characters; reject unsupported/empty normalized queries clearly. Do not silently substitute O/0 or I/1, join unrelated words or call a substring match full-number equality.
- [ ] **I:** Union/deduplicate independent YOLO and full-frame OCR candidates by source/time overlap. Prefer current Paddle/ONNX/Tesseract adapters. Preserve tiling/full-resolution evaluation for small text rather than forcing all frames to 1280px. Bound sampling and report which interval/frames were searched.
- [ ] **I:** Remove imports of learning/sections/Findings and replace them with ordinary job cancellation/progress and P06 report publication where appropriate. Preserve bounded subprocess work, source validation and stale-publication rejection; the worker must not import the whole web app or initialize training dependencies.
- [ ] **I:** Present results as suggestions; selecting one creates a target for O02. Redact the whole chosen number/plate region, not only the matching substring. A failed/nonmatching query never disables another plate's existing redaction. Unknown physical boundaries stay a visible limitation.
- [ ] **V:** Run `python -m pytest test_openscrub.py tests/test_plate_text_hints.py tests/test_plate_text_web.py tests/test_plate_text_subprocess.py -q`, build and a search → select → track → render exercise. Test worker timeout/cancel/restart, raw query exclusion from logs/process arguments and deletion/vault behavior.
- [ ] **D/R/L:** Document retained inference tools/checkpoint versions, query semantics, sampled search coverage, false matches, runtime and privacy lifecycle. If a new recognizer is added, isolate dependencies and verify its license/runtime; published recognition accuracy is not local detached-plate accuracy.

## O04 — pretrained/classical boundary evaluation

**What:** Evaluate whether an existing detector/OCR candidate can be refined into useful boundaries without custom training.

**Why:** YOLO gives boxes and OCR gives text regions. Neither guarantees the visible physical plate boundary, especially under occlusion. The user specifically asked for a separate boundary-finding step.

**When:** W4 research branch; no production dependency or upstream PR until quality/runtime evidence supports adoption. It must not delay generic fixes or usable manual tracking/search.

**Files / contract:** `benchmark/experiments/pretrained_plate_refinement/` and synthetic held-out fixture recipes. Only after acceptance, a small optional `openscrub_internal/plate_boundary.py` with inputs `(frame, candidate_region, source_identity)` and result `{geometry, method, quality_evidence, fallback_reason}`. Do not expose a single uncalibrated confidence as proof of coverage.

- [ ] **E:** Freeze the candidate checkpoint, preprocessing, prompt and mask-selection rule before evaluation. Start with existing OpenCV contours as baseline and one EfficientViT-SAM variant as the first new tool; consider SAM 2 separately if temporal masks justify its heavier runtime. Record code/weight licenses and hashes.
- [ ] **E/V:** Carry forward the GrabCut/EfficientSAM/Light HQ-SAM failure fixtures and evaluate held-out wall/ground, glare, tiny text, perspective, motion, occluders and disconnected visible fragments. Count missed identifier pixels, excess masked pixels, unstable flashes, latency and memory; IoU/model score alone is insufficient.
- [ ] **E/V:** Verify the actual distributable runtime. EfficientViT-SAM's ONNX example still needs Torch/TorchVision preprocessing; any replacement adapter requires numerical equivalence checks. Preserve the core Python floor with an optional isolated runtime where necessary.
- [ ] **S/I:** If a candidate passes, expose a small optional adapter and source-bound results. Under default/aggressive behavior retain usable full-box fallback; in Review uncertain, offer correction/broader coverage rather than silently applying extra blur. A text polygon must not be labeled a physical plate outline.
- [ ] **D/R/L:** Write an evidence-led adoption/no-adoption decision. If none passes, keep search/manual geometry/box tracking and mark automatic refinement unsupported; do not start custom training to rescue the experiment. A successful downstream trial still needs its own upstream scope discussion.

## O05 — optional lettering-only mode

**What:** Preserve the existing pretrained YOLO plus PP-OCRv5 text-region path and its narrow-mask guard optimization as a downstream option.

**Why:** The user wants tighter lettering coverage where supported, while Austin raised a distinct privacy concern about recoverable character geometry. Technical localization fallback does not resolve that policy concern.

**When:** W4, separate `optional/lettering-only` layer. Manual selection/correction uses O02 where tracking is offered; O03 recognition is not required just to detect text regions. Donors: `1fe4e34`, `a6419cc`.

**Files / contract:** Existing `TextRegionDetector.find_plate` / `_narrow_from_probability`, render/report hooks, `tests/test_narrow_plate.py`; `benchmark/narrow_guard.py` adapted from the donor; concise mode documentation. Keep `--plate-coverage full|narrow` / nonnegative narrow margin with full coverage as default.

- [ ] **E/I:** Extract the inference algorithm and one-pass component counting without Findings, recognition, learned models or training. Add missing/corrupt model, low contrast, multiple text rows, clipping and exact-frame tests.
- [ ] **I:** Refresh geometry per supported frame; do not propagate stale narrow masks across unknown/interpolated frames. Full-box fallback applies under default/aggressive policy when its location is supported; the selected Review uncertain policy exposes a gap/correction option instead of silently broadening.
- [ ] **V:** Run `python -m pytest test_openscrub.py tests/test_narrow_plate.py -q`, full build, representative pretrained inference and actual synthetic renders. Retain the existing SDR-only and VFR-normalization limitations until separately implemented and verified.
- [ ] **V/D:** Reproduce the component-guard benchmark with identical polygons/fallbacks, then report whole-video cost and fallback frequency separately. Historical difficult fixtures mostly fell back; do not turn a guard microbenchmark into a universal speed/precision claim.
- [ ] **D/R/L:** Document localization limits and the unresolved recoverability concern. Keep this option downstream unless Austin accepts it independently; it must not block whole-plate geometry or other generic PRs.

## Review focus

Unselected suggestions are not explicit Keep decisions; human identity confirmation does not certify future geometry; a query match is not physical-object identity; an OCR polygon is not a plate outline; a published model is not measured local accuracy. Default and optional behavior must be tested separately in each task and together in C01.
