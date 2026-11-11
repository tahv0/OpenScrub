# Confirmed Findings Implementation Plan

> **For agentic workers:** Use subagent-driven development for disjoint modules and verification-before-completion. Root owns integration, commits, review and delivery.

**Goal:** Preserve explicit video-linked human examples with compact images, make review fast and unambiguous, and train/select named models from accumulated examples.

**Architecture:** A durable confirmed-findings store owns immutable JPEGs and revisioned metadata; a job-local compact-preview store captures representative scan crops and supports image-only editing; training consumes frozen confirmed-example snapshots and optionally a preserved local parent checkpoint. Flask and the existing embedded UI connect these components.

**Tech Stack:** Python/Flask, SQLite or atomic JSON, OpenCV JPEG, current training subprocess/ONNX, embedded JavaScript.

**Spec:** docs/superpowers/specs/2026-11-12-confirmed-findings-design.md

## Global constraints

- Worktree `/workspace/scratch/89b8b88338d5/openscrub-findings`, base `12aad0c`, target `integration/all-prs`.
- Explicit classification only; Blur/Keep, machine judgments and unconfirmed geometry do not create examples.
- JPEG longest side <=640 px, quality 65; source-coordinate metadata always accompanies it.
- Preserve existing model-package schema/exports and user choices; no new production dependency.
- Root owns `openscrub_web.py`, `zones_ui.py`, packaging, UI integration, docs and all Git mutations. Module implementers own only their assigned files.
- Shared Python: `/workspace/scratch/89b8b88338d5/openscrub-secondary-venv/bin/python`; TMPDIR `/workspace/scratch/89b8b88338d5/openscrub-test-tmp`; `OPENSCRUB_NO_AUTOFETCH=1 OPENSCRUB_CPU_DNN=1`.
- Local Chromium cannot create sockets; real browser and Docker checks run in GitHub Actions. Do not retry local browser launch.

## Review focus

- Same source under a different path, but an incompatible normalized timeline: associate video without replaying wrong coordinates.
- Positive -> negative -> unconfirmed/revoked, and concurrent jobs: no resurrected/stale label or falsely acknowledged save.
- Missing original video and missing source job: stored-image browsing, correction and selected-example training still work.
- Unreviewed/output-only/machine-propagated findings: never silently become training evidence.
- New training parent/split history, and a failed mask gate: no validation leakage or silent fallback to the wrong checkpoint.

## Task 1 — Durable confirmed example module

Files: new `confirmed_findings.py`, `test_confirmed_findings.py`.

Interfaces (notify root before changing):
- `record(root, video, finding, jpeg_bytes) -> dict`: video `{sha256, variant_sha256, name, fps, width, height, total_frames}`; finding `{category,label:'positive'|'negative',frame,box,points,crop,job_id,explicit:True,shape_confirmed:bool,id?:str}`. Derive time from frame/fps. Return public entry with id/revision/image metadata. Enforce content IDs and geometry, explicit-only, bounded JPEG, atomic durability and dedup/upsert.
- `list_findings(root, video_id=None, category=None, label=None, offset=0, limit=60) -> {items,total,videos}`; public records never expose absolute paths.
- `get_finding(root,id) -> dict`, `image_path(root,id) -> Path`, `update_finding(root,id,label=None,points=None,expected_revision=None) -> dict`, `forget(root,id,expected_revision=None)`.
- `training_snapshot(root, ids=None, video_ids=None, category='plate') -> list[dict]`: verified immutable records plus internal image path, image hash, crop transform and explicit label, no automatic entries. Freeze values, and include revision.
- `apply_to_report(root,doc) -> (doc,stats)`: only exact variant/timeline/source matches; use conservative matching and preserve later explicit human choices.

- [x] Write and observe failing behavior tests for confirmation-only, source/link persistence, compact image, revisions/forgetting, copied paths, incompatible timelines, selection/frozen snapshots and conservative replay.
- [x] Implement the public API and run focused tests.

## Task 2 — Compact job preview and live queue module

Files: new `finding_previews.py`, `test_finding_previews.py`; minimal callback hook in `openscrub.py` only if required. Root adds web/callback wiring.

Interfaces:
- `capture(job_dir, frame_bgr, frame_index, fps, detections, source=None) -> stats`: accept Detection objects or documented plain rows; never decode video, sample bounded representative objects, store one context crop per tracked group with metadata. Max 640px JPEG, quality65; bound cache to 2,000 representative items/64MiB, report truncation honestly. Stable frame/box keys. Capture only from unpainted source pixels.
- `lookup(job_dir,row,render_state) -> (meta,jpeg_bytes)|None`: exact frame/region or explicitly mapped representative; do not silently use another frame's geometry.
- `pending(job_dir,offset=0,limit=60) -> {items,total,truncated}` and `image(job_dir,key) -> (meta,jpeg_bytes)` with confinement checks.
- `store(job_dir,row,render_state,meta,pixels) -> (meta,jpeg_bytes)`: cache a single legacy CPU decode; source/image sizes and transform are explicit.

- [x] Write and observe failures for bounded capture, duplicate objects, no decoder access, source geometry mapping, stale lookup and safe paths.
- [x] Implement capture/cache/queue; document exact root hooks and tests.

## Task 3 — Named training from stored examples and local lineage

Files: new `findings_training.py`, `test_findings_training.py`; owned changes `learning_session.py`, `learned_models.py`, `learning_candidates.py` and focused existing tests.

Interfaces:
- `default_name(video_names, now=None) -> str`; max80 characters, deterministic timestamp/name, display metadata only.
- `run(job, findings_root, model_root, settings, log=None, train=None) -> dict`: settings `{name?,example_ids?,video_ids?,parent_model_id?,license_accepted}`; consumes `confirmed_findings.training_snapshot`; runs real existing trainer via injected hook for synthetic tests; publishes named schema2 checker with separately bound assessment; never changes a running scan's selection.
- Preserve parent trainable checkpoint plus cumulative frozen examples/split history under `model_root.parent/'learned_model_training'/model_id`; same directory reserved from retention by root. A parent lacking trusted local checkpoint gives a clear choice/error; no ONNX-to-PT guess.
- Expose `training_info(model_root,model_id) -> {trainable,reason,parent_model_id?,example_count?}`; `resolve_parent(...)` as needed. Keep inference-package contents unchanged.
- Existing `run_session` accepts `learning_request.name`, persists candidate display name and auto-saves a completed evaluated candidate through a root publication hook or documented job settings. Do not break injected test trainers.
- Preflight validates the resolved parent checkpoint, rather than requiring base env weights in all cases.

- [x] Write and observe failing tests for names, explicit selected examples across videos, missing source, inherited corpus/split exposure, imported inference-only parent, failed mask gate versus independent verifier assessment, and immutable named model publication.
- [x] Implement and run focused tests; return precise integration requirements to root.

## Task 4 — Web API, review UI and durable workflow

Owner root. Files `openscrub_web.py`, `zones_ui.py`, new API/UI tests, package files/docs.

- [x] Test new explicit confirmation/archive API; ensure default/output-only/quad draft never archives.
- [x] Add confirmed-findings browsing/filtering, image editing and selected-example training UI, plus named train input and progress result.
- [x] Make neutral unreviewed cards; Is/Not actions autosave explicit decisions; existing Blur/Keep controls remain output-only and visually secondary.
- [x] Use compact cached imagery for classification/area editing and archive publication; preserve full-resolution explicit fallback.
- [x] Wire live pending queue/counter to scan callbacks and polling without pausing the scan; reconcile confirmed decisions with final reports.
- [x] Reserve new stores in recovery/retention/vault; retain same-video corrections across jobs and sections; package modules everywhere.

## Task 5 — Review, verification and integration

- [x] Independent component and whole-change review; resolve concrete findings.
- [ ] Focused real ONNX/video/Node tests; combined JS syntax; sdist/wheel/import.
- [ ] PR against `integration/all-prs`; actual desktop/mobile browser, Docker and training CI; compare full-suite failures with known base.
- [ ] Merge per standing instruction; verify branch ancestry/tree and explain actual behavior/limits.

## Added task — Known plate text candidate search

- [x] Bounded local literal text matching, partial/exact evidence, rotated/mirrored/perspective views, geometric proposals and inverse source mapping.
- [x] Explicit worker operation, one CPU source decoder, exact sampled timeline and section guards, progress/cancel, atomic report publication and compact caching.
- [x] Review form and evidence, full-number protection guidance, no automatic training labels or narrow-fragment protection.
- [ ] Final independent review and real browser/CI validation.
