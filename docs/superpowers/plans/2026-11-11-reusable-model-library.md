# Reusable Learned Model Library Implementation Plan

> **For agentic workers:** Use the subagent-driven-development and verification-before-completion workflows. Keep commits on feat/reusable-learned-model-library, targeting integration/all-prs.

**Goal:** Save, select, export and import reusable learned plate-mask models through the UI.

**Architecture:** A bounded model library handles accepted artifacts, portable packages and immutable per-job snapshots. The web app integrates selection into fresh scan chunks and exposes the existing UI patterns for management.

**Tech Stack:** Python, Flask, ONNX Runtime, NumPy, OpenCV, ZIP/JSON, embedded JavaScript.

**Spec:** docs/superpowers/specs/2026-11-11-reusable-model-library-design.md

## Global Constraints

- Models are manually selectable for any video; no source-video or absolute-path requirement.
- Keep original proposal detectors and conservative fallback; never import human labels/corners from another video.
- Default selection is none; save/import must not activate.
- Preserve existing jobs, checkpoints, training history and vault rules.
- No PyTorch checkpoint loading or new runtime dependencies.
- Changes stay on the feature branch; do not merge, deploy or release.
- Execution environment is unavailable; source edits use GitHub's Git API and verification uses repository CI.

## Review Focus

- Renamed/different source files and arbitrary recipient data roots: accepted for model reuse.
- Malformed, corrupt or incompatible packages: reject before publishing any model. Model execution assumes a trusted source; see the design's trust boundary.
- Paused scans and prior human masks: refine only new chunks within the scanned timeline.
- Deleted library entry: existing job snapshots still work after restart.
- Failed import or inference: explicit failure and no partial report/model publication.

## Task 1: Portable model library

Files: learned_models.py, test_learned_models.py.
- [x] Add failing behavioral tests and run focused CI.
- [x] Implement list/save/import/export/delete and immutable job snapshots.
- [x] Validate real ONNX inference and package/metadata integrity.
- [ ] Review and run focused tests.

Interfaces: ModelError(ValueError); list_models(root); save_model(root,job_dir,name,description=''); import_model(root,archive,name=None); export_model(root,model_id)->bytes; delete_model(root,model_id); snapshot_model(root,model_id,job_dir)->manifest; load_snapshot(job_dir)->(manifest,bytes).

## Task 2: Per-video inference and UI

Files: openscrub_web.py, zones_ui.py, video_learning.py, learning_session.py, test_learned_models_web.py, test_learned_models_browser.py.
- [x] Add failing tests for endpoints, explicit selection, fresh-chunk refinement, checkpoint safety and rendered audit persistence.
- [x] Add model endpoints under /api/jobs/learned-models, protected by existing auth/vault handling.
- [x] Pin snapshots when creating jobs; set exact plate proposals; refine fresh chunks before merging.
- [x] Bound decoder work to the scanned timeline; preserve cancellation and original coverage.
- [x] Add model save controls, settings library, import/export/remove, and Scan Setup selector.
- [x] Preserve report metadata and pinned model use across resume/restart/render; exclude library from retention.
- [ ] Verify real desktop/mobile UI and synthetic inference.

## Task 3: Packaging, documentation and final verification

Files: pyproject.toml, Dockerfile, Dockerfile.cuda, Dockerfile.intel, docs/REUSABLE_MODELS.md, .github/workflows/learned-model-library.yml.
- [x] Package the new module in wheel, sdist and all Docker variants.
- [x] Document save/select/transfer and inference-only model scope.
- [ ] Run focused tests, browser checks, build and installed-wheel check, and existing full suite.
- [ ] Independently review the complete diff; resolve material findings.
- [ ] Update the draft PR with exact verified results and limitations; leave unmerged.

## Verification record

- Initial tests-first run (29c1adba) exposed missing functionality: 94 failed, 60 passed.
- Core regression run (259543cf) demonstrated redundant ONNX validation: six sessions instead of one.
- Import/cache fixes (7f4999c4) passed their regressions. Added review regressions reproduced stale selection, out-of-order refresh, locked-vault controls, pre-report restart recovery and older Flask request-property issues.
- Final results and completion status are recorded in https://github.com/tahv0/OpenScrub/pull/36 after CI validates the fixes. Six existing OCR-fixture failures are separately established on the identical base tree by run42869891599.
