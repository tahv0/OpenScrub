# Task 64: P06D preserve review data through rendering

## Global constraints

Preserve Austin upstream defaults, Python >=3.9, report/API compatibility, source-frame accuracy, privacy/vault behavior and distribution paths. No custom training, Findings/journal/sections workbench, dependency/version changes or new root helpers. Tests belong in tests/. Use synthetic data and isolated runtime paths. Do not change the original checkout or user runtime data. No remote publication or subagents.


**What:** Keep every review row and its original position when an existing report is rendered, including Keep choices, zone-dropped rows, manual shapes, tracking/group identifiers and additive fields. Preserve audio suggestions/transcript alongside redaction spans.

**Why:** A real synthetic render on Austin's baseline changed ten review rows into seven by discarding disabled detections. All remaining row indices shifted, and the saved audio suggestions/transcript disappeared. Reopening the actual detections route confirmed the loss. A render should consume the enabled subset without replacing the user's full review document with that subset.

**When:** W2, after P06A if using its publisher; before P06B's final writer integration where useful. This is a focused content-preservation PR, separate from transaction locking, request replay and serialization performance. It extracts the generic requirement discovered in mixed training donor `db9a142`, without importing its training/session helper.

**Files / contract:** Existing engine report read/decode/write and from-report rendering in `openscrub.py`, plus `tests/test_report_roundtrip.py`. Keep the existing public `load_report(path)` return contract and its enabled-only render semantics. Retain raw review data separately from the decoded render subset. Preserve additive fields without interpreting them as new behavior. Newly calculated output provenance and explicit CLI audio overrides must remain accurate; do not copy stale output metadata over the new render's result.

- [ ] **E/I:** Add a failing real render/reopen regression based on the confirmed ten-row fixture. Include disabled ordinary and zone-dropped rows, enabled/disabled manual geometry, dense track/person values, additive row/top-level metadata, audio suggestions/transcript and spans. Assert original row order/choices/fields survive while only enabled rows reach rendering.
- [ ] **I:** Read a coherent report snapshot for from-report rendering, retain the complete review representation for report publication, and update only fields that this render legitimately owns. Preserve the ordinary scan-to-report path and legacy plain-list loading behavior; a legacy list still lacks render state and must receive the existing actionable error for render-only use.
- [ ] **I:** Cover empty metadata, different source/destination report paths, explicit audio override, successive renders, and failures before report publication. Keep source bytes unchanged when rendering to a separate report. Do not add training identifiers or deduplicate/reorder rows.
- [ ] **V:** Run the existing suite plus the new regressions and full sdist-to-wheel build. Render synthetic footage through `run_pipeline`, verify the resulting video frames, then reopen the saved report through the actual Flask route in a fresh process. Record that metadata preservation alone does not establish audible mute/bleep quality or concurrent-writer safety.
- [ ] **D/R/L:** PR lead: Keep choices and review grouping should survive rendering and reopening. Include the concrete 10→7 before / 10→10 after case and audio metadata checks. Declare P06A dependency when used; P06B owns overlaps with edits/tracking/vault/deletion.

## Supervisor evidence and scope

Read report-baseline-research/README.md in this same SDD workspace for actual before evidence, before/after JSON and the reproducible synthetic engine/render/fresh-route script. P06A has a separate shared atomic_report helper; this task's dispatch supplies its reviewed base and branch. Preserve its publisher and tests. P06B transaction/lifecycle coordination is a later task; don't silently add locking or claim concurrent edits are solved.

Source evidence: load_report drops disabled rows by design. Keep that public rendering contract. run_pipeline from-report reads the document repeatedly, tries to add audio metadata to rstate, then drops it when constructing state. write_report currently rebuilds enabled-only rows. One coherent source document can supply decoding and retained review representation; no broad repository layer or unrelated performance changes. Build a fresh output report from correct current render provenance while retaining the full review data. Avoid changing scan-generated report semantics. Unknown additive data is preserved opaquely, never interpreted as a trusted learned decision or new feature.

Keep enabled/disabled manual row and geometric fields exact; don't introduce manual_id (P07 owns replay). Same source/destination path is normal, distinct paths must preserve source. Document any JSON meaning vs byte-format difference. Explicit CLI audio spans may legitimately update audio_redactions; don't overwrite explicit options with old saved data. No claim of audio playback verification unless performed. Existing legacy list behavior and no-render-state error remain. Tests should prove disabled geometry is not rendered, not merely that row count survives.

Use /tmp/openscrub-baseline-20261116/env-opencv4.sh; source it for synthetic isolation and compatible dependencies. Full suite/build, exact command/log evidence, self-review and local commit required. Write task-64-report.md and task-64-pr.md under this SDD workspace. Report concise status/commit/verification/limits.
