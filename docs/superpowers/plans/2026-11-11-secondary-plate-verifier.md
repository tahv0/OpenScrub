# Secondary Plate Verifier Implementation Plan

> **For agentic workers:** Use subagent-driven development and verification-before-completion. Root owns commits, PR and integration; agents own disjoint files below.

**Goal:** Make retained crop-trained candidates useful as explicitly selected secondary reviewers or validated false-positive filters.

**Architecture:** A verifier evaluates proposal-associated scores independently of mask coverage. Candidate provenance and schema-2 portable models carry that assessment. The existing worker and UI apply the checker to current proposals or new scans while preserving human review and section boundaries.

**Tech Stack:** Existing Python/Flask, ONNX Runtime, OpenCV/NumPy, embedded JavaScript; no new production dependencies.

**Spec:** docs/superpowers/specs/2026-11-11-secondary-plate-verifier-design.md

## Global constraints

- Target the current `integration/all-prs`; preserve concurrent progress/section/logging changes.
- Default is suggestions; filtering requires explicit selection and separate held-out assessment.
- Model output never becomes `verified_label`; human edits win and are never exported.
- Keep legacy mask refinement and schema-1 packages compatible.
- Persist model use mode before queueing; imports do not activate automatically.

## Review focus

- A nearby real plate must not substitute for a hand's own proposal score.
- A failed mask gate must not discard a usable candidate or certify filtering.
- Every held-out positive counts, including no-prediction cases.
- Model-suppressed rows must not contaminate later human feedback or become permanent manual keeps.
- Recovery, section cloning and report rendering must preserve selected mode and machine provenance.

## Task 1: Proposal scoring, assessment and inference

Owner: model_library_core. Files: video_learning.py, new plate_verifier.py, new test_plate_verifier.py.

Interfaces:
- `CropRefiner.predict_proposal(image, box)` returns `(mask, plate_score)` for boxes associated with proposal pixel coordinates in that crop; legacy `predict` remains unchanged.
- `plate_verifier.assess(model, dataset, cancelled=None, progress=None)` returns assessment `{schema:1,status:'validated'|'review_only',threshold,held_out_positive,held_out_negative,retained_positive,rejected_positive,rejected_negative,reason}`. Validated requires >=4 positives, >=2 negatives, zero rejected positives and >=1 rejected negative.
- `plate_verifier.validate_assessment(value)` returns a canonical validated metadata dictionary or raises ValueError.
- `plate_verifier.review_report(video, doc, model, assessment, mode='review', cancelled=None, progress=None, frame_range=None)` returns `(doc,stats)`. Stats include model_calls, checked, suggested, suppressed, kept, human_preserved, decoded_frames. Per-row field is `plate_verification` with decision, score, threshold, mode, applied and previous_enabled; never human verified_label.

- [x] Add and observe failing tests for separation, missing positives, nearby boxes, explicit modes, human preservation and exclusion of machine-only decisions from capture_constraints.
- [x] Implement score association and independent assessment.
- [x] Implement bounded report pass and reversible machine-only decisions; preserve section frame bounds/cancellation.
- [x] Run focused unit/real-ONNX tests.

## Task 2: Retained candidates and portable verifier models

Owner: review_reusable_models. Files: new learning_candidates.py, learned_models.py, new test_learning_candidates.py, test_learned_models.py additions.

Interfaces:
- `learning_candidates.list_candidates(job_dir)` returns safe descriptors `{id,version,created_at,model_sha256,assessment,mask_assessment}`; candidate ID names an exact pass/version, never an input path.
- `learning_candidates.load_candidate(job_dir,id)` verifies confinement/artifact hash and returns internal paths/metadata including model_path, model_sha256, dataset, folder, id.
- `learning_candidates.evaluate(job_dir,id,cancelled=None,progress=None)` uses verified ONNX bytes and plate_verifier.assess; persists and returns assessment bound to the model digest.
- `learning_candidates.record_mask_assessment(job_dir,folder,status,message)` records mask outcome for that exact candidate, separately from learning.active.
- `learned_models.save_candidate(root,job_dir,candidate_id,name,description='')` requires a stored verified assessment, creates schema-2 kind `openscrub-plate-verifier`, contract1 with common metadata and the assessment in validation. Threshold matches validation.threshold. Schema1 stays unchanged.
- `learned_models.snapshot_model(root,id,job_dir,mode=None)` additionally persists selection in `plate_model_selection.json` outside the two-file snapshot. Default refine for schema1, review for schema2. Filtering requires validated assessment.
- `learned_models.load_selection(job_dir,manifest=None)` returns refine/review/filter; legacy schema1 snapshots without a mode file mean refine, schema2 missing/corrupt mode fails clearly.

- [x] Add and observe failing tests for historical retained candidates, hash/path refusal, honest assessment metadata, schema compatibility, transfers and persisted modes.
- [x] Implement candidate discovery/evaluation and mask assessment persistence.
- [x] Extend portable models with the verifier kind and mode persistence, using existing bounded/atomic validation.
- [x] Run relevant module tests.

## Task 3: Worker, review and Scan Setup integration

Owner: root. Files: learning_session.py, openscrub_web.py, zones_ui.py, section_workflow.py only as needed, packaging/docs/tests.

- [x] Inspect current candidate/training tests and write endpoint/worker regressions first.
- [x] Persist mask assessment and expose retained candidates after quality rejection; preserve default transactional gate behavior.
- [x] Add explicit candidate-check worker operation and API, requiring no training setup, while preserving prior reports on failure.
- [x] Show candidate/mode controls and per-finding machine decisions; save evaluated candidate to the library.
- [x] Branch reusable-model inference by kind, store/restore modes, preserve metadata through render/sections, clear machine-only markers on explicit human changes.
- [x] Update package inclusion, docs and synthetic browser coverage.

## Task 4: Verification and integration

- [x] Run focused tests, evaluated combined JavaScript syntax and build/import checks.
- [x] Independent review; resolve material findings. Model replacement, resumed audit history, and partial-section checkpoints have regression coverage.
- [ ] Push feature branch and PR against integration/all-prs; run existing full/Docker/training CI as applicable, distinguish baseline failures.
- [ ] Merge completed work into integration/all-prs per standing user instruction; verify final refs/tree and report actual results.
